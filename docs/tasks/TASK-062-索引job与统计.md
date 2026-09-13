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

（实施 AI 在此填写。）
