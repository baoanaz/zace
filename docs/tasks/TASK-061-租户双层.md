# TASK-061：租户双层（token → user → owns project）

> 状态：review（2026-09-13，补做完成）｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-060、**TASK-085（已合并 `735bfc3`）** ｜ soft 依赖：无
> 建议分支：`feature/task-061-tenancy_<你的缩写><MMDD>`（**从 `main` 开，已含 TASK-085**）
> 交付物所有权：
> - `service/zace_service/metadb.py`（追加 `projects` 归属表与查询）
> - `service/zace_service/deps.py`（`require_project_id` 增加归属校验）
> - `service/zace_service/routers/{projects,sync,query,ops}.py`（归属校验接入点）
> - `service/tests/test_tenancy.py`（**新建**）
>
> 清单外文件不得改。

## 目标

把 D-36 的**逻辑授权层**落地：每个请求强制校验 `projectId` 归属当前用户。
当前 `deps.py::require_project_id` 只做"项目是否存在"，**任何登录用户可以访问任何 projectId**——
在单用户本地模式下无所谓，上云即越权读取他人源码。

```text
service 层（本卡）：token → user → owns project?   每个请求强制校验
core 层（已有）    ：project_id → {data_root}/projects/{id}/   物理隔离（D-03）
```

## 输入文档（按序读，只读所需章节）

1. `docs/design/Module/06-服务化与部署.md` §2.3（租户隔离双层，含"只有逻辑层 → SQL 漏写 WHERE 即泄露"的教训）
2. `docs/design/Index.md` §3 的 D-36（两层缺一不可）
3. `docs/contracts/openapi.yaml`（所有带 `projectId` 的端点）
4. `service/zace_service/deps.py`（`require_project_id` 现状）
5. `TASK-060` 的任务卡（User / metadb 形态）

## 冻结接口（本卡不得变更）

- 消费：TASK-060 产出的 `require_user` / `metadb`。
- 产出：
  - `zace_service.metadb.owns_project(user_id, project_id) -> bool`
  - `zace_service.metadb.list_projects(user_id) -> list[str]`
  - `zace_service.metadb.claim_project(user_id, project_id, display_name)`（幂等）
  - `require_project_id(request, raw)`：**签名不变**，语义扩展为"存在 + 归属当前用户"

## §A 数据模型（追加到 `zace-meta.db`）

```sql
CREATE TABLE IF NOT EXISTS projects (
  project_id   TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL DEFAULT '',
  created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
```

## §A0 当前基线（2026-09-23 编排者核实，**先读**）

TASK-085 已合并（`735bfc3`），它**已经把本卡的一部分做掉了**，你要接着做剩余部分：

| 已有（TASK-085 做的，**不要重做**） | 剩余（**本卡要做的**） |
|---|---|
| `metadb.claim_project/owns_project/list_projects` 已实现（TASK-060 产出） | `require_project_id` 的**归属校验**（§C） |
| `POST /api/projects/resolve` 已补 `_claim_project`（写归属行） | `POST /api/projects/attach` 的 claim（§B 第二行） |
| `_claim_project` 的边界口径已定：**已被他人 claim 时不报错**（理由见下） | `batch-upload` 未归属 → 403（§B 第三行） |
| `GET /api/projects` 已被 `ops.py` 按 `list_projects(user_id)` 过滤 | `routers/{projects,sync,query,ops}.py` 的**逐端点**归属校验（§C 穷举） |
| — | `service/tests/test_tenancy.py`（新建） |

> **重要：TASK-085 已改过 `routers/projects.py`**，你从它的分支串联即可，不要重写 `_claim_project`。

### 已被裁定的一件事（不要推翻）

TASK-085 在 `resolve` 处**刻意不实现** §B 的「已被他人 claim → 403 `project_owned_by_other`」，
理由是：`require_project_id` 当时没有归属校验，报错会把"多人共用同一仓库的第二人"直接卡死（回归）。

**本卡的任务就是把那个前提补上**：一旦归属校验（§C）落地，共用仓库的第二人本来就会在检索时拿到 404，
此时是否要在 `resolve` 处报 403 就变成了一个**产品选择**——两种口径都自洽：

- **口径 A（保守，推荐）**：`resolve` 保持 TASK-085 的行为（不报错），越权一律由 §C 的 404 拦；
- **口径 B（严格，按卡内 §B 原文）**：`resolve` 报 403，让"抢注"在第一时间被拒。

**你必须在报告里明确写了哪个口径及理由**，并在 "未决问题" 里把另一口径的成本写清楚，交编排者复核。

## §B 归属的产生（谁"认领"一个 projectId）

三个入口，**全部改为 claim 语义**（幂等）：

| 入口 | 行为 |
|---|---|
| `POST /api/projects/resolve` | resolve 出 projectId 后 claim 给当前用户；**若已被他人 claim → 403 `project_owned_by_other`** |
| `POST /api/projects/attach`（本地模式） | claim 给本地用户（TASK-060 的 `is_local=1`） |
| `POST /api/sync/batch-upload` | **不得**隐式 claim（避免"知道 id 就能抢"）：projectId 未归属当前用户 → 403 |

`projectId` 是 `sha256(identity)`（D-29），**可被同仓库的其他人算出**。因此"谁是第一个 claim 的人"
决定了归属——这是 V1 的既定简化（Module/06 §2.3 表留 `org_id` 列，V2 才做共享）。
**本卡必须在报告中明确写出这个简化及其含义**（跨用户共享同一 repo 时第二人会被拒），供编排者判定是否接受。

## §C 校验接入点（穷举，漏一个就是越权）

所有消费 `projectId` 的端点改为经 `require_project_id`：

- `GET /api/projects` → 只返回当前用户的项目（**不是** `EngineManager.list_projects()` 的全量）
- `GET /api/projects/{id}` / `DELETE /api/projects/{id}`
- `GET /api/sync/status/{projectId}`、`POST /api/sync/{batch-upload,checkpoint,deletions}`
- `POST /api/query/{search,ask}`
- `GET /api/usage/projects/{id}`（TASK-064 实现时会用）
- `service/zace_service/mcp.py` 的 `_project_id_for`：MCP 面同样要过归属校验

**越权响应用 404 还是 403**：卡内定 **404 `project_not_found`**——403 会泄露"该 projectId 存在"。
（与 Module/06 §2.2 "不给探测面"一致。）

## §D 与本地模式的相容

`local_mode=True` 时：TASK-060 的隐式本地用户自动 claim 一切，行为与今天逐字一致（R34）。
**所有既有测试必须原样通过**，这是本卡的第一验收项。

## 验收标准（DoD）

- [ ] `uv run pytest service/tests/test_tenancy.py -q` 全绿，**必须覆盖**：
  - [ ] 用户 A 创建的项目，用户 B 用该 projectId 访问 `search`/`projects/{id}`/`sync/status`/`batch-upload`/MCP → **全部 404**（逐端点断言，不许只测一个）；
  - [ ] 用户 B 的 `GET /api/projects` 看不到 A 的项目；
  - [ ] resolve 已被他人 claim 的 identityKey → 403 `project_owned_by_other`；
  - [ ] `batch-upload` 到未归属 projectId → 403（**不得**隐式 claim）；
  - [ ] 同一用户重复 resolve 同一 identityKey → 幂等（不产生第二行、不报错）；
  - [ ] 本地模式：既有全部测试通过（回归保护）。
- [ ] 行为验收（两个真实用户、同一服务实例端到端，贴输出）：
      A 建项目并索引 → B 登录 → B 检索 A 的 projectId 得 404 → B 自己的项目正常。
- [ ] 基线三条命令全绿。
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- 不做 org / 团队 / 共享（`org_id` 列 V1 恒 NULL，V2 预留）
- 不做项目转移/所有权变更
- 不做 per-user 配额与计费
- 不改 core（物理隔离已存在；core 字典里只有 project，D-34 不可破坏）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写，**必须逐条列出 §C 的每一个端点及其测试用例名**。

## 执行记录

### 2026-09-13 ｜ 分支 `feature/task-061-tenancy_xwz0913` ｜ 状态 → review

**基线**：从 `main` @ `83b221a`（含 TASK-085 `735bfc3`）开分支。开工时本工作区是
新泳道 worktree（detached @ `460dc28`，main 的祖先），按卡内建议 `git switch -c ... main` 落到
`83b221a`。

**范围**：只做 §A0“剩余”列 —— `require_project_id` 归属校验、`attach` 的 claim、
`batch-upload` 归属拦截、`routers/{projects,sync,query,ops}.py` 逐端点接入、
`service/tests/test_tenancy.py`。TASK-085 已做掉的部分（`metadb` 三个接口、`resolve` 的 claim）
一行未改。

### 验收命令与结果

```console
$ uv run pytest service/tests/test_tenancy.py -o addopts="" -q
22 passed, 1 warning in 3.09s

$ uv run ruff check .
All checks passed!

$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。

$ uv run pytest -o addopts="" -q
804 passed, 2 skipped, 1 warning in 23.64s
```

**既有 206 个 service 测试改动前后逐字一致**（改动前 `206 passed`，改动后 `206 passed`）：
R34 的第一验收项成立。

### 行为验收（两个真实用户、同一服务实例、真实 HTTP）

`ZACE_LOCAL_MODE=false` + 真 uvicorn（`127.0.0.1:8931`）+ 真实本地 embedding provider：

```console
[A] bootstrap            -> 201 alice
[A] resolve              -> 200 projectId=88e3d9b6eb684542
[A] batch-upload         -> 200 chunksNew=5
[A] search(A.project)    -> 200 markdown=794B
[B] register             -> 201 bob
[B] list projects        -> 200 ids=[]                      ← B 看不到 A 的项目
[B] GET  /api/projects/88e3…             -> 404 project_not_found
[B] GET  /api/sync/status/88e3…          -> 404 project_not_found
[B] GET  /api/usage/projects/88e3…       -> 404 project_not_found
[B] GET  /api/projects/88e3…/index-runs  -> 404 project_not_found
[B] GET  /api/projects/88e3…/index-stats -> 404 project_not_found
[B] POST /api/sync/batch-upload          -> 404 project_not_found
[B] POST /api/sync/checkpoint            -> 404 project_not_found
[B] POST /api/sync/deletions             -> 404 project_not_found
[B] POST /api/query/search               -> 404 project_not_found
[B] POST /api/query/ask                  -> 404 project_not_found
[B] own upload           -> 200
[B] search(B.project)    -> 200 evidence_hit=True          ← B 自己的项目正常
RESULT: PASS
```

**无探测面实证**：不存在的 id 与他人的 id 响应**逐字相同**（同为
`{"error":{"code":"project_not_found","message":"项目不存在：<id>"}}`）。
**A1 未回归**：无凭据访问 `/api/projects` 仍 401。

**本地模式真实进程回归（R34）**：`ZACE_LOCAL_MODE=true` 起真服务，不带任何凭据 ——
resolve=200、attach=200、list=200、get=200、sync_status=200、index-stats=200、search=200（证据命中），
且 dataRoot 下**只有 `projects/`、未创建 `zace-meta.db`**。

### §C 端点清单 × 测试用例名（逐端点对照）

| §C 端点 | 接入点 | 越权用例 | 结果 |
|---|---|---|---|
| `GET /api/projects` | `routers/projects.py::list_projects` + `_owned_ids` | `test_list_projects_only_shows_owned` | 只返回自己的 |
| `GET /api/projects/{id}` | `routers/projects.py::get_project` | `test_cross_user_endpoints_are_404[GET /api/projects/{pid}]` | 404 |
| `DELETE /api/projects/{id}` | `routers/projects.py::delete_project` | `test_cross_user_delete_is_404` | 404 且 A 的项目仍在 |
| `GET /api/sync/status/{projectId}` | `routers/sync.py::sync_status` | `test_cross_user_endpoints_are_404[GET /api/sync/status/{pid}]` | 404 |
| `POST /api/sync/batch-upload` | `require_project_id`（原已有）+ 新归属校验 | `test_cross_user_endpoints_are_404[POST /api/sync/batch-upload]`、`test_batch_upload_never_claims` | 404，**不隐式 claim** |
| `POST /api/sync/checkpoint` | `require_project_id`（原已有） | `test_cross_user_endpoints_are_404[POST /api/sync/checkpoint]` | 404 |
| `POST /api/sync/deletions` | `require_project_id`（原已有） | `test_cross_user_endpoints_are_404[POST /api/sync/deletions]` | 404 |
| `POST /api/query/search` | `require_project_id`（原已有） | `test_cross_user_endpoints_are_404[POST /api/query/search]` | 404 |
| `POST /api/query/ask` | `require_project_id`（原已有） | `test_cross_user_endpoints_are_404[POST /api/query/ask]` | 404 |
| `GET /api/usage/projects/{id}` | `routers/ops.py::project_usage` | `test_cross_user_endpoints_are_404[GET /api/usage/projects/{pid}]` | 404 |
| `POST /api/projects/{id}/rescan` | `routers/projects.py::rescan_project` | `test_cross_user_rescan_is_local_mode_403_not_a_leak` | 403（非本地，非越权面） |
| `GET /api/projects/{id}/index-runs` | `routers/ops.py::project_index_runs` | `test_cross_user_endpoints_are_404[GET /api/projects/{pid}/index-runs]` | 404 |
| `GET /api/projects/{id}/index-stats` | `routers/ops.py::project_index_stats` | `test_cross_user_endpoints_are_404[GET /api/projects/{pid}/index-stats]` | 404 |
| `mcp.py::_project_id_for` | **未接**（清单外 + 无可达身份） | `test_mcp_face_ownership_is_not_wired_yet`（只钉实现事实） | 未决问题 1 |

> 此外：归属**产生**入口 `attach`→`test_attach_claims_to_the_local_user`、
`resolve`→`test_resolve_claims_and_is_idempotent`；R34 回归→`test_local_mode_ignores_ownership_entirely`；
归属者不受影响→`test_owner_access_is_unaffected`；上传后能否检索→`test_upload_by_owner_indexes_and_is_searchable`。

**测试有效性的负对照**：临时摘掉 `deps._require_ownership` 的调用后，
`pytest service/tests/test_tenancy.py` → **13 failed**（其余 9 个与归属无关的用例仍过）。
证明这批用例真能抓住旧行为，而不是“改了也过”。

### resolve 403 的口径选择（§A0 要求明确写出）

**选了口径 A（保守）：`resolve` 不报 403 `project_owned_by_other`**，保持 TASK-085 的行为，
越权一律由 §C 的 404 拦。理由：

1. **反探测面一致性**：卡内 §C 已裁定“越权响应用 404，不用 403（403 泄露 projectId 存在）”。
   若 `resolve` 对“已被他人 claim”报 403，那么攻击者只需 `POST /resolve` 一个**猜测的 identityKey**
   就能看出“这个仓库已被别人建过”——刚好把 §C 刚堵上的探测口开回来。
2. **共用仓库是既成事实**（Module/06 §2.3 的 V1 简化）：报 403 会把“同仓库的第二人”卡死在 resolve，
   连“看得到自己的东西”都做不到，而是回归。
3. **口径 B 的成本**（未选，见未决问题）：仅当将来把“共享”显式建模（`org_id`）后才有意义。

> 卡内 DoD §118“resolve 已被他人 claim → 403”按口径 A **未实现**，属预期内的偏离，已列在“与设计偏差”。

### 共用仓库简化的含义（卡内 §B 要求明确写出）

`projectId = sha256(identity)`（D-29），**同仓库的其他人算得出同一个 id**。本卡维持
“**先到先得**”：第一个 `resolve`/`attach` 的人拥有它，后来者 resolve **不报错也不获得归属**
（以 `test_shared_repo_second_user_resolves_but_does_not_take_over` 钉住）。含义：

- 第二人 resolve 成功（拿到同一个 projectId）但项目**不在其名下** → 其 `GET /api/projects`、
  仪表盘与全部检索类端点均看不到它（一律 404）；
- 这不是 bug 而是 V1 的既定简化：`projects` 表预留 `org_id` 列（Module/06 §2.3），V2 才做共享；
- **代价**：V1 下“多人共用同一仓库”实际只能由**第一个认领者**使用。编排者需判定是否接受。

### 契约影响

**无**。未改 `docs/contracts/**`、`core/zace_core/{types,interfaces,hashing}.py`。
归属校验未新增端点、未改响应形状（仍是 CF-05 信封）、未改冻结路径集合
（`service/tests/test_skeleton.py` 的路径快照测试原样通过）。`require_project_id` **签名不变**
（冻结接口 §），只扩展语义。

### 与设计偏差

1. **`resolve` 不报 403**（口径 A）：偏离卡内 §B 原文与 DoD §118，理由见上。属 §A0 明确授权
   实施者在两口径间选择并说明。
2. **`batch-upload` 越权用 404 而非 403**：偏离 §B §88 与 DoD §119 的字面（两处要求 403），
   遵循 §C 的统一口径 404。**已获用户明确拍板**（选“统一 404”）。
3. **`ensure_local_user` 是清单内文件的新增接口**：卡内只点名 `metadb.py`“追加 `projects` 归属表与
   查询”，本卡新增一个 `ensure_local_user`。必要性：`attach` 要按 §B 认领给“本地用户（`is_local=1`）”，
   而 `auth.local_user()` 是**不落库的幻影**，`projects.user_id` 有指向 `users(id)` 的外键 ——
   没有真实行就写不进归属。默认本地（无库）仍 no-op，R34 不受影响。
4. **`attach` 的 claim 只在 app 级已有 MetaDB 时生效**：卡内 §B 只说“claim 给本地用户”，未说
   “若本地模式无库怎么办”。默认本地模式不建库（R34），所以无库时保持 no-op；
   `zace-service local` 与测试那条“显式注入 MetaDB”的路径才写归属。
5. **§A0 的“已于 TASK-085 完成”列有一行与实测不符**：§A0 写“`GET /api/projects` 已被 `ops.py`
   按 `list_projects(user_id)` 过滤”，但 `projects.py::list_projects` 当时**仍返回全量**
   （`ops.py` 里被过滤的是 `/api/account/overview`，不是 `GET /api/projects`）。本卡按 §C 补齐。

### 未决问题

1. **MCP 面（`mcp.py::_project_id_for`）仍未接归属校验 —— 卡内自相矛盾，本卡未扩范围。**
   §C 点名“MCP 面同样要过归属校验”，但“交付物所有权”清单**不含** `mcp.py`，§A0 的“剩余”列
   也只列了 `routers/{projects,sync,query,ops}.py`。更关键的是技术上**拿不到身份**：
   `app.py` 的鉴权中间件把用户写在 `request.state.zace_user`，而 MCP 工具没有 `Request`
   （见 `mcp.py::manager_for_app` 的注释）。要接上，需先给 MCP 面一条身份通道。
   **可选解法**：（a）中间件里把已认证用户存进 `contextvars`（与 `logging.py` 的 requestId 同一手法），
   工具内读它；（b）工具内按 `ctx.headers` 的 Bearer 重解析（`mcp` SDK 提供了 `Context.headers`）。
   两者都属跨卡改动（新增身份传递机制），建议单独开卡。**当前云端 MCP 面仍是越权面**
   （知道 `project_root` 者可检索他人项目），上线前必须补。
2. **口径 B 的成本**：若编排者改选“`resolve` 报 403”，则需接受：(a) 反探测面上与 §C 冲突；
   (b) 共用仓库第二人彻底用不了（resolve 就失败）；(c) 需给 CF-05 补一个错误码
   （`project_owned_by_other`，属 L2 契约扩展，本卡不能自行落）。
3. **`/healthz` 免鉴权且列出全部 `projectId`**（`ops.py::_project_progress`）：云端形态下
   这是与 `GET /api/projects` 同级的信息泄露面（敌人可枚举项目 id）。但它不在 §C 清单，
   且响应形状属公共契约（`test_skeleton` 锁定），本卡**未改**。建议编排者判定是否单独开卡。
4. **`project_usage`（`/api/usage/projects/{id}`）的归属使“从未归属的项目”审计数据不可见**：
   审计行（`query_audit`）在 `record_query` 里可能先于归属写入（如请求先落审计再 404），
   此时该项目对任何人都不可见 —— `usage_summary` 按 projectId 聚合，不按 user。属已有口径，
   本卡未动；若将来要“按用户看自己的查询历史”，需在审计里落 `user_id` 并改聚合（已有该列
   `query_audit.user_id`，但 `usage_summary` 未用它过滤）。
5. **`GET /api/projects` 的过滤依赖 `projects` 表的完整性**：历史上由旧版本上传、或在归属
   功能引入前 `attach` 的项目没有归属行，会在列表里“消失”（对归属者也是）。这是“fail closed”
   的题中之义，但若存在存量数据迁移需求，需另开卡补一个回填脚本。

