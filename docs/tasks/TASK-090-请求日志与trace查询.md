# TASK-090：请求日志持久化与 trace id 查询（用户报错可追溯）

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-084（审计表已建）｜ soft 依赖：无
> 建议分支：`feature/task-090-request-log_<你的缩写><MMDD>`
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

（实施 AI 在此填写。）
