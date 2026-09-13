# TASK-062：索引 job 与统计（成功/失败次数、耗时、历史）

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-034（review）、TASK-060（统计要归属用户）｜ soft 依赖：TASK-061
> 建议分支：`feature/task-062_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/metadb.py`（追加 `index_runs` 表与聚合查询）
> - `service/zace_service/indexer.py`（每次索引**落一次 run 记录**：成功/失败/耗时）
> - `service/zace_service/runtime.py`（聚合查询入口 `index_stats(project_id)`；**既有方法语义不改**）
> - `service/zace_service/routers/{projects,ops}.py`（统计读取端点）
> - `service/tests/test_index_stats.py`（**新建**）
>
> 清单外文件不得改。

## 目标

Web 上你想要的三个数字——**索引成功次数、失败次数、平均耗时**——今天**在后端根本不存在**：

- 只有内存态 `IndexProgress`（单项目、单次、服务重启即丢，`indexer.py`）；
- 无 job 表、无历史、无聚合端点（`docs/design/Module/06` §2.4 声明的 `project_index_jobs` 表尚未建）。

本卡把这些数字**如实**落到 `zace-meta.db` 并开一个读取口。V1 仍**不做** worker 池 / 队列 / 取消
（Module/06 §2.4 的"进程内 worker"已由 TASK-034 的 `ProjectIndexer` 线程满足），本卡只补"历史与统计"。

## 输入文档（按序读，只读所需章节）

1. `docs/design/Module/06-服务化与部署.md` §2.4（索引 job 与可观测；job 表字段的原始设想）
2. `service/zace_service/indexer.py`（现有 `IndexProgress` 与 `_finish` / `_fail` 两条结束路径）
3. `service/zace_service/runtime.py`（`index_progress` 现状；`attach`/`rescan` 入口）
4. `docs/handbook/M2a-验收手册.md` §2（为什么没有百分比；**本卡的统计口径不得与之矛盾**）
5. `core/zace_core/pipeline/indexer.py::IngestReport`（可落库的字段来源）

## 冻结接口（本卡不得变更）

- 消费：`IngestReport`、`IndexProgress`（TASK-034 产出，字段只增不改）。
- 产出（TASK-070 的统计页依赖）：
  - `metadb.record_index_run(project_id, *, started_at, finished_at, state, files_total, files_processed, chunks, errors, error_text) -> int`
  - `metadb.index_stats(project_id, *, limit_days: int = 30) -> IndexStats`
  - `IndexStats = { total, succeeded, failed, avgDurationMs, lastRunAt, lastState, recent: [IndexRun] }`
  - `EngineManager.index_stats(project_id) -> IndexStats`
  - 端点见 §A

## §A 端点（新增，属 CF-05 扩展，登记在卡内）

| 方法 | 路径 | 语义 |
|---|---|---|
| GET | `/api/projects/{id}/index-runs` | 单项目索引历史（默认最近 20 条，`?limit=` ≤ 200） |
| GET | `/api/projects/{id}/index-stats` | 聚合：成功/失败次数、平均耗时、最近一次状态 |
| GET | `/api/index-stats` | 跨项目汇总（当前用户的项目；供 web 总览页） |

响应形状（**冻结给 web**，字段只增不改）：

```json
// GET /api/projects/{id}/index-stats
{ "projectId": "e6fe…",
  "total": 12, "succeeded": 10, "failed": 2,
  "avgDurationMs": 41230,          // 只统计 succeeded（失败没有有意义的耗时）
  "minDurationMs": 800, "maxDurationMs": 230900,
  "lastRunAt": 1789096917, "lastState": "done",
  "recent": [ { "runId": 12, "state": "done", "startedAt": …, "finishedAt": …,
                "durationMs": …, "filesTotal": 1436, "filesProcessed": 1436,
                "chunks": 9389, "errors": 0, "error": null } ] }
```

## §B 数据模型（追加到 `zace-meta.db`）

```sql
CREATE TABLE IF NOT EXISTS index_runs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id      TEXT NOT NULL,
  state           TEXT NOT NULL,      -- done | failed（running 不落库：见 §C）
  started_at      INTEGER NOT NULL,
  finished_at     INTEGER NOT NULL,
  duration_ms     INTEGER NOT NULL,
  files_total     INTEGER NOT NULL DEFAULT 0,
  files_processed INTEGER NOT NULL DEFAULT 0,
  chunks          INTEGER NOT NULL DEFAULT 0,
  errors          INTEGER NOT NULL DEFAULT 0,
  error_text      TEXT                        -- 脱敏后的摘要（沿用 redact_text）
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON index_runs(project_id, finished_at DESC);
```

保留策略：每项目最近 500 条（插入后按 `finished_at` 裁剪），与 04 §8 审计的 1000 条口径一致。

## §C 记录时机（两条结束路径都要落，一条都不能漏）

`indexer.py` 今天有 `_finish`（成功，可能带 `report.errors`）与 `_fail`（异常）两条路径：

- **两条都必须写 run 记录**——只写成功会让"失败次数恒为 0"，正是你要的统计里最没用的那种；
- `state="done"` 且 `errors > 0` 时：**仍算 succeeded**（与手册 §2 的口径一致：那只是"部分文件有解析问题"），
  但 `errors` 字段如实记录条数，`error_text` 存摘要；
- `state="failed"` 时 `files_processed` 用失败前已处理数；`error_text` 走 `redact_text`；
- **`running` 不落库**（只在内存 `IndexProgress` 里）：否则服务被杀会留下永远不结束的幽灵记录。
  代价是"进行中的这一次"不计入 `total`——在报告里写清这个口径。
- **索引启动时若发现上一条 `running`（不可能，因为不落库）**：不需要处理，本注释即口径说明。

## §D `avgDurationMs` 的口径（必须写进响应与文档）

平均耗时**只统计成功的 run**，并明确标注：

- 失败 run 的耗时是"失败得多快"，混入平均会让人以为索引变快了（**误导性统计**）；
- 增量重扫（无文件变化、秒级返回）与全量索引（分钟级）会混在同一个平均里——
  `recent` 数组是给用户看真相的，聚合值只是概览。**建议 web 图例写明"含增量重扫"**；
- 时间窗口默认 30 天（`?days=` ≤ 365）。

## 验收标准（DoD）

- [ ] `uv run pytest service/tests/test_index_stats.py -q` 全绿，**必须覆盖**：
  - [ ] 一次成功索引 → `total=1, succeeded=1, failed=0`，`durationMs ≈ finished-start`；
  - [ ] 一次失败索引（注入解析异常/embedding 不可用）→ `failed=1` 且 `error_text` **不含** key/base_url（脱敏断言）；
  - [ ] `errors>0` 但正常的 run → 计入 `succeeded`，`errors` 字段如实；
  - [ ] `avgDurationMs` **不含**失败 run（构造一个极快的失败 run，断言平均值不受其影响）；
  - [ ] 超过 500 条时自动裁剪，最旧的先删；
  - [ ] `GET /api/index-stats` 只汇总当前用户的项目（与 TASK-061 联动）；
  - [ ] 服务重启后统计**仍在**（这是"落库"而非"内存"的证明，必须有用例）。
- [ ] 行为验收（贴真实输出）：对真实仓库跑两次索引（第二次无改动）→ 展示 stats 响应，
      并说明"第二次 `processedFiles=0` 但耗时仍被记录"的观感。
- [ ] 基线三条命令全绿。
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- 不做 job 队列 / worker 池 / 并发调度 / 取消（Module/06 §2.4 的进程内线程已够；真要排队另开卡）
- 不做百分比进度（core 无回调，**不许伪造**，见手册 §2）
- 不做成本/费用统计（embedding 用量另议）
- 不做统计图表的服务端渲染（web 侧做）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写，**必须写明 §C/§D 的口径选择及其代价**。

## 执行记录

### 补做记录（TASK-085，2026-09-23）

**背景**：TASK-062 卡标 done，但 `metadb.record_index_run` 只挂在**本地 attach** 路径的
`ProjectIndexer.on_finish` 上；客户端上传（`batch-upload` → `manager.ingest`）完全绕过它，
导致用 `npx zace-client` 接入后索引统计恒为 0。本卡（TASK-085）是**它的补做**：
记录点下沉到 `EngineManager.ingest`，并补齐卡内 DoD 要求但**当时从未写出来**的
`service/tests/test_index_stats.py`（13 → 15 个用例）。

**实际根因是两处，不是卡内写的两处里的一处**（详见「与设计的偏差」第 1 条）。

**验证**：`uv run pytest service/tests/test_index_stats.py -q` → 15 passed；
全仓 `761 passed, 2 skipped`；`ruff check .` 与 `check_dependency_direction.py` 均通过。

### 真实端到端凭证（2026-09-23，WSL2，云端模式 + 真实 `BAAI/bge-m3`）

**改动前**（编排者 2026-09-13 实测，非本地模式，`npx zace-client` 走完上传+查询后）：

```json
{"total":0,"succeeded":0,"failed":0,"avgDurationMs":null,"minDurationMs":null,
 "maxDurationMs":null,"lastRunAt":null,"lastState":null,"recent":[],"diskBytes":0}
```

**改动后**（本轮实测：起云端服务 → bootstrap → 建 token → `resolve` → `batch-upload` → 查询）：

| 步骤 | 命令 | 真实输出 |
|---|---|---|
| 1. resolve | `POST /api/projects/resolve` | `{"projectId":"a652645daaa29b0c","created":true}` |
| 2. 上传**前** | `GET /api/index-stats` | `total:0, recent:[]`（基线） |
| 3. batch-upload | `POST /api/sync/batch-upload` | `{"added":2,"chunksNew":5,"filesParsed":2,"errors":[]}` |
| 4. 上传**后** | `GET /api/index-stats` | **`total:1, succeeded:1, avgDurationMs:2000, lastState:"done"`** |
| 5. 概览 | `GET /api/account/overview` → `index` | **`succeeded:1, avgDurationMs:2000`（不再是 0/null）** |

```json
// 步骤 4 的真实响应（节选）
{"total":1,"succeeded":1,"failed":0,"avgDurationMs":2000,"minDurationMs":2000,
 "maxDurationMs":2000,"lastRunAt":1789310775,"lastState":"done",
 "recent":[{"runId":1,"projectId":"a652645daaa29b0c","state":"done",
   "startedAt":1789310773,"finishedAt":1789310775,"durationMs":2000,
   "filesTotal":2,"filesProcessed":2,"chunks":5,"errors":0,"error":null}],
 "diskBytes":159113}
```

**真实 `npx zace-client`（完整 Agent 路径，非 curl 替代）**：用 MCP SDK 的 `stdio_client`
拉起真 `npx -y zace-client`，`initialize` → `tools/call search_context`：

```text
MCP is_error: False
## Relevant Context
### Code
[E1] TokenService — src/token_service.py:1-9
     reason: bm25 rank 4 + vector 0.5033 + entry point / exported symbol +0.2 + 相邻区间合并
### Docs
[E2] docs.md > 令牌设计（guide）
     reason: bm25 -0.5322 + bm25 rank 1 + vector 0.7523 + vector rank 1
```

该调用同时触发 client 的懒同步（resolve → 扫描 → batch-upload），随后：

```json
// GET /api/index-stats（两条记录：① 手工 batch-upload ② 真实 client 上传）
{"total":2,"succeeded":2,"failed":0,"avgDurationMs":1000,
 "recent":[{"runId":2,"durationMs":0,"filesTotal":2,"filesProcessed":2,"chunks":5,"errors":0},
           {"runId":1,"durationMs":2000,"filesTotal":2,"filesProcessed":2,"chunks":5,"errors":0}]}
```

**两条路径口径一致性**（同一项目：本地 `zace-service local --repo` attach 一次 +
客户端 `batch-upload` 一次）：

```text
total 2 succeeded 2 failed 0 avgDurationMs 1500
  记录1（客户端上传） {'state':'done','durationMs':0,   'filesTotal':2,'filesProcessed':2,'chunks':5,'errors':0,'error':None}
  记录2（本地 attach） {'state':'done','durationMs':3000,'filesTotal':2,'filesProcessed':2,'chunks':5,'errors':0,'error':None}
```

两条记录的 `state` / `filesProcessed` / `chunks` / `errors` / `error` 字段形态一致；
差异只在 `durationMs` 的精度（见「与设计的偏差」第 3 条）与 `filesTotal` 的来源（见第 2 条）。

### 与设计的偏差

1. **卡内只识别了两处根因中的一处。** 卡内写的：记录点挂在 `ProjectIndexer.on_finish` 上，
   `batch-upload` 绕过它。**实测还发现第二处**：云端形态下 `EngineManager` 由
   `deps.get_engine_manager` / `mcp.manager_for_app` **懒构造**，从不 `attach_meta_db`
   （只有 `__main__._run_local` 那条路径 attach）→ 即使记录点写对了，`ingest` 里
   `self._meta_db is None` 仍直接 return，统计继续恒为 0。
   修法：两处懒构造点各补一行 `attach_meta_db(...)`。
   本机实测证据：手工接线后同一 `upload_files` 立刻出现 `[{...'done', 1000, 2, 2, 5, 0, None}]`。

2. **`chunks` 的口径由「本次新增」改为「项目总量」。** TASK-062 的响应样例是
   `filesTotal:1436` 配 `chunks:9389`，9393 那量级只能是**项目总 chunk 数**，不是本次新增。
   实现上本地 attach 路径原先记 0（`IndexProgress` 不带该字段），上传路径若记
   `chunks_new + chunks_reused` 则在**增量重扫/整批重传**时显示 0 —— 正是本卡要消灭的那种
   "看起来没工作"。现两条路径统一用 `_project_chunk_count()`（= `sync_status().chunks`，
   与项目页显示的 chunks 同源）。

3. **`durationMs` 保留 TASK-062 的整秒粒度，真实毫秒耗时进日志。** `record_index_run` 是
   冻结契约（只收秒级 `started_at`/`finished_at`，由它自己算 `durationMs`），**不得改签名**，
   因此上传路径的亚秒级索引会在 `durationMs` 上呈现为 0。选择：与本地 attach 路径保持
   **同一粒度**（卡内 §B 要求两条路径不得两套解释），而不是为上传路径另立毫秒口径。
   真实值从日志读：`上传索引完成：<pid>（added=2，modified=0，parsed=2，errors=0，实测耗时 370.3 ms）`。
   上面 E2E 的表里 2 秒/3 秒的差异也确实来自**调用点时间差与整秒进位**，不是索引慢。

4. **`files_total` 的口径写明并写清代价**：`IngestReport` 里**没有**"仓库共多少文件"字段，
   故上传路径记**本次请求送达的文件数**（`added + modified`）。它可能与 `filesProcessed`
   相等（重扫时），这与本地路径的 `total_files`（目录列举数）**不是同一来源**；两者都满足
   `filesTotal >= filesProcessed`，web 的"解析/总数"两列仍可解释。

5. **失败记录多脱敏一层 endpoint**：`redact_text` 会抹掉 key/token/Bearer，但**保留**
   `endpoint=https://host/...`。`index_runs` 是长期保留 + WebUI 展示的记录，公司内网部署时
   base_url 就是内网主机名，因此 `_persist_error_text()` 在 `redact_text` 之后再抹掉 URL。
   代价：从库里**看不出是哪个 provider 失败的**（HTTP 错误面 `errors.py` 仍保留 endpoint，
   那边是一次性响应，不长期留存）。卡内 DoD 要求的"不含 base_url"即按此实现。

6. **越出卡内「交付物所有权」清单的改动（已获用户批准）**：
   - `service/zace_service/deps.py`、`service/zace_service/mcp.py`：各 1 行接线（偏差 1）；
   - `service/zace_service/routers/projects.py`：`resolve` 后 claim（偏差 7）。
   卡内点名**不许改**的 `metadb.py`、`routers/sync.py` 均未改动。

7. **`resolve` 补上 claim —— 这是本卡 DoD 能通过的前提，同时暴露出 TASK-061 从未接线。**
   卡内 DoD 要求 `/api/index-stats` 的 `total >= 1`，但该端点经 `ops._visible_project_ids`
   只汇总"已归属当前用户"的项目，而上传路径按 TASK-061 §B **刻意不隐式 claim** ——
   两者叠加又变成"面板恒为 0"。实测确认：`resolve` + 上传后 `projects` 表**恒为空**，
   即 `metadb.claim_project()` 虽已实现，却**没有任何入口调用它**（TASK-061 标 done 但未接线）。
   修法：按 TASK-061 §B 原设计，在 `POST /api/projects/resolve` 后 claim 给当前用户（幂等），
   本地模式（无 `zace_user`）不写、也不因此建 `zace-meta.db`。
   这实际上补完了 TASK-061 的缺口，**请编排者据此重新判定 TASK-061 的状态**。

### 未决问题

1. **TASK-061 的其余接线仍未落地（本卡只补了 `resolve` 这一个入口）。**
   TASK-061 §B 还要求 `attach`（本地）claim、`batch-upload` 未归属则 403，
   以及 `deps.require_project_id` 真正做归属校验（§C 点名 `GET /api/projects`
   只返回当前用户项目）。**这些都还没接**：今天 `require_project_id` 仍只判"项目是否存在"，
   也就是 TASK-051 A1 的越权面**依然存在**。本卡刻意不扩大范围（会动 deps/sync/query/mcp
   的多个校验点，属 TASK-061）。
2. **多人共用同一仓库时，第二人的 resolve 不会报错、但也不会再 claim。**
   TASK-061 §B 原设计是"已被他人 claim → 403 `project_owned_by_other`"，我**没有**照做：
   本项目常见形态是多人共用同一 identityKey → 同一 projectId，而 `require_project_id`
   今天并不强制归属，在这里报错会把"共用仓库的第二人"直接卡死（回归）。
   代价：第二人 resolve 成功但项目不在其名下 → 其 WebUI 看不到该项目统计。
   正确做法（属 TASK-061）：要么把归属校验一并接上，要么把"共享"显式建模（Module/06 §2.3
   表预留的 `org_id`）。请编排者裁决。
3. **`/api/index-stats` 的 `diskBytes` 会为未归属项目累加**（`manager.index_stats(pid)["diskBytes"]`
   对 `ids` 求和，而 `ids` 是过滤后的列表，所以当前无碍）—— 但若将来 `all_index_stats`
   与 `diskBytes` 的 id 集合来源不一致，就会出现"数字对不上"。列在此处备查。
4. **真实 E2E 用的是本机单 target 小仓库（2 个文件）**，`durationMs` 落到整秒的边界很敏感；
   大仓库上"整秒粒度"的观感差异需要编排者再判定一次是否可接受（偏差 3）。

