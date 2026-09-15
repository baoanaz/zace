# TASK-090：请求日志持久化与 trace id 查询（用户报错可追溯）

> 状态：**review** ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-084（审计表已建）｜ soft 依赖：无
> 分支：`feature/task-090-request-log_xwz0914`（泳道 D，已完成待合并）
> 交付物所有权：
> - `service/zace_service/logging.py`（文件 sink + 轮转）
> - `service/zace_service/requestlog.py`（**新建**：结构化请求日志的落库与查询，若选 DB 方案）
> - `service/zace_service/metadb.py`（新增 `request_log` 表与查询，若选 DB 方案）
> - `service/zace_service/routers/ops.py`（**新增** trace 查询只读端点）
> - `service/zace_service/config.py`（日志配置项）
> - `service/tests/test_request_log.py`（**新建**）
> - `.env.example`（补配置说明）
>
> 清单外文件不得改。

## 背景（用户 2026-09-14 明确要求）

> 加上各个用户的请求 LOG 缓存窗口机制，方便其他人报错后，能按照 trace id 查询 LOG，
> 知道问题是什么，保存在服务端那边。

**现状**（编排者核实）：

| 已有 | 缺 |
|---|---|
| `requestId` 中间件：每请求生成、响应头 `X-Request-Id` 回写 | **日志只输出到 stdout**，无持久化、无轮转、无查询 |
| `logging.py` 用 `contextvars` 传 `requestId` | 服务重启后日志随进程消失 |
| 审计表 `query_audit`（TASK-084） | 它只记**查询语义**，不记**请求级错误与耗时链路** |

**用户场景**：使用者报错 → 把 `X-Request-Id` 发给管理员 → 管理员按 id 查到这次请求的完整日志
（路径、状态、耗时、错误栈、涉及的 projectId）。

## §A 存储方案（**你需评估并选一个，报告说明理由**）

| 方案 | 优点 | 缺点 |
|---|---|---|
| A. 文件 sink + 轮转（`logging.handlers.RotatingFileHandler`） | 简单、无 DB 依赖、天然适合"日志"；grep 即可查 | 查询要读文件；多进程轮转需注意；窗口靠文件数控制 |
| B. SQLite 表 `request_log`（与 metadb 同库） | 查询结构化、可按 user/project/时间过滤、与审计同源 | 写放大；DB 体积增长需保留策略 |
| C. 两者结合：文件存全量，DB 存索引（id→文件位置） | 查询快且全量可查 | 复杂度最高 |

**推荐的取舍依据**："缓存窗口机制"意味着**有界保留**（如最近 N 天 / N 条 / N MB），
超界自动清理。选一个能自然表达"窗口"的方案，并在 `.env.example` 里给出窗口配置项。

## §B 记录内容（**必须脱敏**）

每次请求至少记：

| 字段 | 说明 |
|---|---|
| `requestId` | 已是主键语义（中间件生成或调用方传入） |
| `ts` / `method` / `path` / `status` / `durationMs` | 已有（stdout 里就是这么打的） |
| `userId` / `projectId` | 有则记（便于按用户/项目排查） |
| `errorCode` / `errorMessage` | CF-05 信封里的 code（如 `unauthorized`、`project_not_found`） |
| `traceback` | 仅 5xx 记录（4xx 是业务预期，不记栈） |

**硬纪律**：

- **绝不记录**：API key、`Authorization` 头、session cookie、embedding/LLM 的 key、源码内容；
- 复用既有 `redact_text`（若它不覆盖裸 key，本卡内自建兜底，参考 TASK-084 的 `redact_query_text`）；
- 5xx 的堆栈要记（这是排查的核心价值），但**响应里仍只给通用文案**（既有 `errors.py` 口径不变）。

## §C 查询端点（只读）

新增类似 `GET /api/request-log/{requestId}`（路径与形状由你定，但要在报告说明）：

- **鉴权**：进 `PUBLIC_PATHS` 之外的受保护区域（**不能公开**，否则日志是信息泄露面）；
  - **归属规则**：普通用户只能查**自己发起的**请求（`userId` 匹配）；
    管理员（若有）可查全部——**V1 没有角色体系**，所以先做"只能查自己的"，
    他人 id → 与"不存在"同样的 404（不给探测面，Module/06 §2.2）；
- 返回：该请求的结构化日志条目（**截断**长字段，避免响应过大）；
- **同时提供**：响应头里回写的 `X-Request-Id` 要有文档说明（用户怎么拿到这个 id 报给你）——
  写进 `docs/handbook/`（**新增一节**，不要重写既有手册）。

## 验收标准（DoD）

- [ ] `uv run pytest service/tests/test_request_log.py -q` 全绿，**必须覆盖**：
  - [ ] 一次成功请求 → 能按 `requestId` 查到（状态/路径/耗时/ userId 齐全）；
  - [ ] 一次 5xx → 记录里有 `errorCode` 与堆栈；
  - [ ] **脱敏断言**：造一个带 `Authorization: Bearer sk-live-xxx` 的请求，
        查到的记录里**搜不到**该 key（真形态假 key）；
  - [ ] 窗口生效：超过配置上限后，最旧的记录被清理（贴前后计数）；
  - [ ] **越权**：用户 B 查 A 的 `requestId` → 404（与"不存在 id"响应一致）；
  - [ ] 服务**重启后**日志仍在（落库/落盘而非纯内存）。
- [ ] 行为验收（贴真实输出）：起服务 → 发一个失败请求（如未认证的 `/api/projects`）→
      拿响应头里的 `X-Request-Id` → 用该 id 查到日志。
- [ ] 文档：`docs/handbook/` 新增一节说明"用户如何拿到 requestId 并报给管理员"。
- [ ] 基线三条命令全绿（用 `-o addopts=""` 看数字）。
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- 不做日志聚合/ELK/Loki 集成（VPS 单机场景，SQLite/文件足够）；
- 不做实时日志流（WebSocket/SSE）；
- 不做管理员角色体系（V1 无角色，只做"查自己的"）；
- 不改 CF-05 的错误信封形状。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：§A 方案选择与理由、窗口配置项与实测清理效果、
脱敏断言、以及"用户如何拿到 requestId"的操作路径。

## 执行记录

**日期**：2026-09-14 ｜ **分支**：`feature/task-090-request-log_xwz0914` ｜ **泳道**：D

### §A 方案选择与理由：**文件轮转 sink（方案 A）**

| 方案 | 裁定 |
|---|---|
| A. 文件轮转 sink | ✅ **选它** |
| B. SQLite `request_log` 表 | ✗ |
| C. 文件 + DB 索引 | ✗ |

决定性的那条证据：`app.py` 只在非本地模式建 `zace-meta.db`（`meta_db = ... if
resolved.auth_required else None`），且 `test_tenancy.py:361` 明确钉住"本地模式不该创建
zace-meta.db"（R34）。**表方案下本地模式（默认形态、也是绝大多数单机场景）将完全没有日志**——
恰好把用户诉求打掉一半。文件方案两种形态都持久化，且与 metadb 零耦合。

两点与卡内假设的偏差（已在报告说明）：

1. 卡内担心"`_ensure_schema` 只跑 `executescript`，旧库不会自动加新表"——**实测不成立**：
   `executescript` 每次 `MetaDB.open` 都执行，`CREATE TABLE IF NOT EXISTS` 对旧库是纯追加，
   不会破坏现有库。也就是说 B 方案的兼容性障碍其实不存在；我们不选 B 是因为 R34，不是兼容性。
2. 本卡**未修改** `metadb.py`（交付物清单里它是"若选 DB 方案"才需要），因此与
   TASK-088/094 抢 `metadb.py` 的冲突面直接归零。

### 窗口配置项与实测清理效果

新增三个环境变量（`.env.example` 已补说明）：

| 变量 | 默认 | 含义 |
|---|---|---|
| `ZACE_LOG_MAX_BYTES` | 8388608（8 MiB） | 单文件上限；写满即轮转（`RotatingFileHandler`） |
| `ZACE_LOG_BACKUP_COUNT` | 9 | 轮转备份数（连同当前文件共 10 个） |
| `ZACE_LOG_RETENTION_DAYS` | 14 | 保留天数；启动时 `prune_log_files` 清理超期文件 |

两个维度各管一件事（也是"有界保留"的完整表达）：**体积**管上界（低流量下不涨），**天数**
管陈旧（低流量下不触发轮转也能过期）。默认上界 ≈ 80 MiB / 14 天。

实测清理（真实跑过，前后计数）：

```text
prune 前: ['request.log']                     | 计数 = 1
造出超期备份后: ['request.log', '.1', '.2', '.3'] | 计数 = 4
删除文件数 = 3
prune 后: ['request.log']                     | 计数 = 1
```

解析行为也实测：默认 `(8388608, 9, 14)`；覆盖 `(1024, 2, 3)` 生效；非法值 `'abc'` / `'-5'`
**显式报错**（与 `config.py` 既有 `_as_bool`/`_as_float` 同纪律，不静默取默认）。

### 脱敏断言结果

- 带 `Authorization: Bearer sk-live-SHOULD-NOT-LEAK-abc123XYZ` 的请求：**落盘文件里该 key
  出现 0 次**，查询响应里也是 0 次；
- 记录里**不存在**请求头字段（"Authorization" 字样只在错误文案里出现，且其中的 `Bearer` 已被抹成
  `***`）；
- 裸 `sk-` / `zace_` 串由 `requestlog.redact_request_text` 兜底（与 TASK-084 的
  `audit.redact_query_text` 同形态），单测钉住 `redact_request_text("sk-live-...") == "***"`；
- 5xx 堆栈照记（排查核心价值），但**响应仍只给通用文案**：单测断言 500 响应既不含异常文本也不含
  `Traceback`（`errors.py` 口径未动）。

### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run pytest service/tests/test_request_log.py -q` | **20 passed** |
| `uv run pytest -o addopts="" -q` | **824 passed, 2 skipped**（基线 804 → 新增 20，无回归） |
| `uv run ruff check .` | All checks passed |
| `uv run python scripts/check_dependency_direction.py` | 通过 |

行为验收（真实起服务于 `:9600`，`ZACE_LOCAL_MODE=false`，真实 curl）：

```text
① 未认证 GET /api/projects
   HTTP/1.1 401 Unauthorized
   x-request-id: 7e785acda9974b93          ← 修好了：此前该路径不回写 id
   {"error":{"code":"unauthorized",...}}

② 带凭据的失败请求 GET /api/projects/nope-project
   HTTP/1.1 404 Not Found
   x-request-id: 6f75ad9a71fe4bb5
   {"error":{"code":"project_not_found","message":"项目不存在：nope-project"}}

③ 用该 id 查日志 GET /api/request-log/6f75ad9a71fe4bb5
   {"requestId":"6f75ad9a71fe4bb5","ts":"2026-09-14T04:44:04.106+00:00",
    "method":"GET","path":"/api/projects/nope-project","status":404,
    "durationMs":20.87,"userId":"6ab7c0436f8abb97d39d20a1389d21ec",
    "projectId":"nope-project","errorCode":"project_not_found",
    "errorMessage":"项目不存在：nope-project","traceback":null,
    "relatedLogs":[],"relatedLogCount":0}

④ 重启验证（本卡存在的意义）
   重启前 status=200；kill 服务 → 重新起同 data_root → **仍查得同一条记录**：
   requestId: 6f75ad9a71fe4bb5 | status: 404 | errorCode: project_not_found
```

### 与卡内示例的一处必要偏差（已经编排者拍板）

卡内行为验收写的是"未认证的 `/api/projects`"，但按裁定后的**严格归属**规则，未认证请求没有
`userId`（无 owner），**任何人都查不到**（与不存在同 404）——否则 path 里的 projectId 会成为
信息泄露面。因此行为验收改用"带凭据的失败请求"（`project_not_found`），其 owner 明确、可查；
未认证 401 的 `X-Request-Id` 回写仍被单测与真实 curl 双重覆盖。

### 顺带修好的一个真实缺陷（写在 `app.py` 注释里）

原中间件装配顺序使 `_install_auth` 位于 `_install_request_context` **外层**，于是鉴权短路返回的
401 **绕过**了 requestId 中间件：响应没有 `X-Request-Id`、日志里也没有那次失败请求。实测证据：
云瑞形态 `curl -D - /api/projects` → 无 `x-request-id` 头。本卡把 `_install_request_context`
改为最后注册（最外层）后修复——这正是"报错后按 trace id 查"的前提。

### 查询端点形状（说明）

`GET /api/request-log/{requestId}`（**受保护区域**，不在 `PUBLIC_PATHS`）：

- 返回主条目（method/path/status/durationMs/userId/projectId/errorCode/errorMessage/traceback）
  + `relatedLogs`（同一 requestId 下的旁路日志：**已处理的 5xx** 的堆栈由 `errors.py` 处理器打在
  另一行，不带它则 503 报错会查到空堆栈）+ `relatedLogCount`；
- 越权 / 不存在 / 无 owner 一律 `404 request_log_not_found`，**文案不回显 requestId**，
  三种情况响应**逐字节一致**（不给探测面）；
- 长字段截断：普通字段 2000 字符，`traceback` 8000 字符且**保头保尾**（异常链根因在尾部）。

### 契约影响

无。未改 `docs/contracts/**`、`core/**`、`core/zace_core/{types,interfaces,hashing}.py`。
新增路径 `/api/request-log/{requestId}` 属 CF-05 **扩展**，已按 TASK-090 登记进
`service/tests/test_skeleton.py::TASK_EXTENSION_PATHS`（与 TASK-062/064 同做法）；
`docs/contracts/openapi.yaml` 的同步由编排者执行。

### 与设计偏差

无（方案选择在卡内授权范围内；中间件顺序修正属实现细节，L1）。

### 未决问题

1. **越权面的既有限制**：只有"查自己的"，**管理员无法帮用户查 401 日志**（V1 无角色体系，
   卡内明确不做）。用户报错若只给一个未认证请求的 id，只能请 TA 带凭据重试。若将来要支持
   "管理员代查"，需要引入角色判定（本轮已向编排者确认按严格归属处理）。
2. **本地模式的跨用户可见性**：本地模式 `zace_user is None`，归属按"放行"（R34 行为一致），
   因此本地单机上任何进程都能查到全部请求日志。单机单用户场景可接受，VPS 多用户场景应跑非本地模式。
3. **日志不读请求体**：POST body 里的 projectId 不记（避免 token/源码内容进入日志面），
   因此 `POST /api/query/*` 的日志只有路径参数、没有项目归属。若排查需要，可在
   `routers/query.py` 另行显式传 projectId（不推荐直接从 body 取）。
4. **与 TASK-088/094 的合并**：`config.py` / `routers/ops.py` / `.env.example` 为共同改动面，
   本卡已按约定"只在自己的区块追加、不重排既有顺序"；`metadb.py` 本卡未动。

### 回填清单

- [x] 本执行记录
- [x] `docs/tasks/README.md` 中 TASK-090 行 → `review`
- [x] 新增手册 `docs/handbook/operations/请求日志与trace-id报错手册.md`（未改动既有四份手册）
- [x] 本地提交（`task-090: ...`），**未 push**

