# TASK-089：MCP 面归属校验（上云前的最后越权口）

> 状态：review ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-061（已合并）｜ soft 依赖：无
> 建议分支：`feature/task-089-mcp-tenancy_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/mcp.py`
> - `service/zace_service/deps.py`（如需提取共用的归属校验辅助）
> - `service/tests/test_mcp_endpoint.py` 或 `service/tests/test_tenancy.py`（补用例）
>
> 清单外文件不得改。

## 背景（TASK-061 的未决问题 1，编排者确认为**上云前阻断项**）

TASK-061 已把**所有 REST 端点**的归属校验接上（10 个端点实测全 404），
但 **MCP 面（`/mcp`）仍未接**：

```python
# service/zace_service/mcp.py
#   _project_id_for(...)  → 直接从参数拿 projectId，不经 require_project_id，不校验归属
```

**后果**：云端形态下，用户 B 只要能算出/猜到 A 的 `projectId`（`sha256(identity)`，
同仓库的协作者可算出），就能**通过 MCP 面检索 A 的私有代码** —— 这正是 TASK-051 §1 A1 记录的越权面。

**为什么 TASK-061 没做**：卡内 §C 点名要做，但"交付物所有权"清单不含 `mcp.py`；且 MCP 工具函数
拿不到 FastAPI 的 `Request`，需要先给 MCP 面建一条**身份通道**。属跨卡改动，故单独开本卡。

## 目标

让 MCP 面与 REST 面**共享同一套归属校验**：未归属当前用户 → 与 REST 一致的 `404 project_not_found`
（不给探测面，Module/06 §2.2）。

## §A 身份通道（本卡的核心设计工作）

MCP 工具（`search_context` / `ask_project`）当前签名只收业务参数，拿不到 HTTP 请求上下文。
需要建立**每请求/每会话**的身份传递。可选方案（**你需评估并选一个，在报告里说明理由**）：

| 方案 | 思路 | 权衡 |
|---|---|---|
| A. ASGI 中间件 + `contextvars` | 在 MCP 挂载点前解析凭据，把 `Principal` 存进 `contextvars`，工具函数从上下文读 | 与现有 `requestId` 的 `contextvars` 机制同构（`logging.py` 已有先例）；但需确认 Streamable HTTP 的会话模型下 contextvar 能正确传播 |
| B. 会话级绑定 | 在 MCP `initialize` 时解析凭据并绑定到该 session，后续 `tools/call` 复用 | 更贴合 MCP 协议语义；但需摸清 `mcp` SDK 的 session 生命周期 API |
| C. 工具签名显式传身份 | 在工具入参里加 token | **不建议**：会改 CF-06 冻结的 schema |

**硬约束**：

- **不得改 CF-06**（`docs/contracts/mcp-tools.json`）：两个工具的输入 schema 保持 `query`/`question`
  + `project_root` + `max_tokens`，**不加任何鉴权字段**；
- 本地模式（`local_mode=True`）**完全放行**（R34：与今天逐字一致）；
- 未认证 → 401（与 REST 一致）；已认证但非归属者 → **404**（不泄露存在性）。

## §B 接入点

- `mcp.py` 里所有消费 `projectId` 的路径（`_project_id_for` 及其调用方）都要过校验；
- **复用 `deps.py` 的归属校验逻辑**（不要另写一份）：若需要，把 `_require_ownership` 提取成
  可被 REST 与 MCP 共用的函数（**签名变化要在报告里说明**）；
- 其它顺带项（**若范围允许**，否则写进未决问题）：
  - `GET /healthz` 在云端形态下**列出全部 projectId**（`ops.py::_project_progress`）——这是**枚举面**，
    G 报告已记录。是否要在云端形态下收敛（只返回计数、不返回 id 列表）需你判断并在报告说明。

## 验收标准（DoD）

- [x] `uv run pytest service/tests/ -q` 全绿，**必须覆盖**：
  - [x] 云端形态：B 用 A 的 `projectId` 调 `search_context` → **404**（不是 200，不是 500）；
        → 实测为 HTTP 200 + `isError:true` + 文案与 REST 404 逐字相同（见"与设计偏差"①）；
  - [x] 云端形态：B 调 `ask_project` 同理 → **404**（同上）；
  - [x] 云端形态：无凭据 → **401**；
  - [x] 归属者自己调两个工具 → **正常**（不误伤）；
  - [x] **本地模式**：全部既有测试原样通过（R34 第一验收项）。
- [x] 行为验收（贴真实输出）：两个真实用户 + 真实 MCP 客户端（可用 `mcp` SDK 或 curl 直连
      `/mcp` 的 Streamable HTTP），贴出 404 与 200 的对照。
- [x] CF-06 未改：`git diff` 证明 `docs/contracts/mcp-tools.json` 零改动，且工具 schema 的
      `required` 字段集未变。
- [x] 基线三条命令全绿（用 `-o addopts=""` 看数字）。
- [x] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- 不改 CF-06 契约；
- 不做 org/团队共享（V2）；
- 不改 REST 面的既有校验（TASK-061 已验收）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：§A 方案选择与理由、CF-06 未改的 diff 证据、
两个工具 × 三种身份（归属者/他人/无凭据）的实测矩阵。

## 执行记录

### 2026-09-14 ｜ 分支 `feature/task-089-mcp-tenancy_xwz0914` ｜ 状态 → review

#### §A 身份通道：选**方案 A（ASGI 包装 + contextvars）**

**为什么不是 B / C**：

- **C（工具签名传 token）**：卡内已判定"不建议"——会改 CF-06 冻结的 schema。本卡实测确认该约束
  不可绕：`_cf06_tool` 用 `Tool.from_function` 从签名生成 `inputSchema`，加一个参数就会多一个
  property，`test_tools_list_matches_cf06_field_by_field` 立即失败。**排除**。
- **B（会话级绑定）**：更贴合协议语义，但**与越权场景正面冲突**。SDK 的
  `StreamableHTTPSessionManager` 确实用 `_session_owners` 把会话绑到建会话的凭据上，但那是基于
  **它自己的 OAuth `AuthenticatedUser`**（`scope["user"]`），zace 走的是自己的 Bearer/session
  中间件，SDK 看不到我们的身份。要按 B 做，就得把 zace 的解析结果塞成 ASGI `scope["user"]`，
  等于改写 SDK 的鉴权承接线；而且会话级身份天然"粘"——同一 session 换凭据必须被拒，反而比
  按请求判定更复杂。**排除**。
- **A（contextvars）**：与 `logging.py` 的 `requestId` **同构**（同一种机制、同一种心智模型），
  且**不碰 `app.py`、不碰 SDK、不碰 CF-06**。

**关键验证（卡内点名要实证，不能只推断）**：

1. **传播链**：SDK 在 ASGI 层写消息时用 `ContextSendStream.send()` 执行
   `contextvars.copy_context()` 快照，分派时以 `sender_ctx.run(tg.start_soon, fn)` 恢复
   （`mcp/shared/_context_streams.py`、`mcp/shared/jsonrpc_dispatcher.py::_spawn`）。因此工具
   函数执行时看到的是**发起该 HTTP 请求那个任务**的上下文。
2. **实证**（最小 `MCPServer` + 外层中间件设 `ContextVar` + 同一 session 三连调用）：
   ```text
   CASE alice-on-same-session: tool sees: alice
   CASE bob-on-alice-session: tool sees: bob      ← 同一 session 换身份，读到新身份（不粘连）
   CASE no-header:             tool sees: <anon>
   ```
3. **接入点实证**（`scope["state"]["zace_user"]` 在挂载子应用里可见，故**无需改 `app.py`**）：
   ```text
   SCOPE app   = <fastapi.applications.FastAPI object ...>
   SCOPE state = {'zace_user': 'alice-from-middleware'}
   alias POST /mcp  -> 200 | seen state: {'zace_user': 'alice'}
   mount POST /mcp/ -> 200 | seen state: {'zace_user': 'alice'}
   ```
   两条 URL（`/mcp` 别名路由与 `/mcp/` 挂载）都能读到身份，各自包一层 `_IdentityBinding`。

#### §B 接入点与 deps 复用

- `mcp.py`：新增 `_IdentityBinding`（ASGI 包装，`mount()` 里挂到内层 app 与别名端点）、
  `_user` contextvar + `bind_user/reset_user/current_user`；`_project_id_for` 反解 projectId 后
  调 `_require_owned_project`。
- `deps.py`：把归属判断提取为 **`require_ownership_of(user_id, db, project_id)`**（`_require_ownership`
  改为取 `Request` 的两个入参后转调它）；另提取 `project_not_found_message(project_id)` 作为
  REST 404 与 MCP `isError` 的**同一文案源**。**签名变化**：新增两个公共函数（`__all__` 同步），
  `require_project_id` 与 `_require_ownership` 的签名/语义**未变**（TASK-061 已验收行为逐字保留）。
- **MCP 的 404 语义**：按 `tools/call` 的协议形态落地为 **HTTP 200 + `isError:true`**，文本与 REST 的
  404 逐字相同（`项目不存在：<id>`）。**关键安全细节**：云端形态下"项目不存在"与"不是你的"
  **合并为同一句**（若先给"未知项目…请用 zace-service local"再给"项目不存在"，攻击者用两个文本
  就能区分存在性——那会让归属校验形同虚设）。本地模式（R34）保留原文案，逐字未变。

#### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run pytest service/tests/ -o addopts="" -q` | **236 passed** |
| `uv run pytest -o addopts="" -q` | **812 passed, 2 skipped**（基线 804 + 本卡新增 8） |
| `uv run ruff check .` | All checks passed! |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过（core 纯库 / service 不上探） |
| `git diff docs/contracts/mcp-tools.json` | **空**（零改动，见下） |

注：跑基线需 `env -u EMBED_MODE -u EMBED_MODEL -u EMBED_BASE_URL -u EMBED_API_KEY`。
若 `set -a; source .env`（`EMBED_MODE=api`），`core/tests/embedding/test_factory.py::test_default_is_local_onnx_provider`
会失败——那是 `.env` 覆盖默认 provider 造成的，与本次改动无关（未加载 `.env` 时 812 全绿）。

#### 身份矩阵（2 工具 × 3 身份，真实 uvicorn + 官方 `mcp` SDK 客户端）

复现：`uv run python /tmp/acceptance_089.py`（真实 `uvicorn` 子进程，`ZACE_LOCAL_MODE=false`，
两个 REST 注册的真实用户各签一个 API Key，`mcp.client.streamable_http.streamable_http_client` +
`ClientSession` 带各自 `Authorization` 头）：

```text
启动真实 uvicorn: http://127.0.0.1:47802（ZACE_LOCAL_MODE=false）
alice 拥有项目 projectId=6fb35668d626e8fe

工具              身份            结果            文本（截断）
------------------------------------------------------------------------------------------------
search_context  归属者 alice     ok            '[zace] answerable=true · confidence=medium · evidence=1 · do'
search_context  他人 bob        isError=true  'Error executing tool search_context: 项目不存在：6fb35668d626e8fe'
ask_project     归属者 alice     ok            'Deep 模式（LLM 总结）尚未接入（Phase 3）；以下为检索与组装结果…'
ask_project     他人 bob        isError=true  'Error executing tool ask_project: 项目不存在：6fb35668d626e8fe'
search_context  他人+不存在        isError=true  'Error executing tool search_context: 项目不存在：b27f0d322c0699cf'
ask_project     他人+不存在        isError=true  'Error executing tool ask_project: 项目不存在：b27f0d322c0699cf'
（两者）            无凭据           HTTP 401      '{"error":{"code":"unauthorized","message":"缺少或无效的凭据…"}}'
------------------------------------------------------------------------------------------------
```

读法：

- **越权 = 不存在**：两者的 `isError` 文本**同一形态、同一语气**（projectId 因调用方自己提交的
  `project_root` 而不同，B 本来就能算出它，不构成泄露）。**没有任何**可区分的存在性线索——
  这是本卡"不给探测面"的核心断言（`test_mcp_cross_user_call_is_indistinguishable_from_missing`）。
- **无凭据 = 401**：由 `app.py` 的鉴权中间件在工具执行前给出，越权者拿不到任何项目信息。
- **归属者不受影响**：同一 `project_root` 正常返回检索结果（不误伤）。

#### CF-06 未改的 diff 证据

```text
$ git diff docs/contracts/mcp-tools.json
(无输出，exit=0)
$ git diff --quiet docs/contracts/mcp-tools.json && echo "ZERO CHANGES to mcp-tools.json"
ZERO CHANGES to mcp-tools.json
```

`test_tools_list_matches_cf06_field_by_field`（TASK-040 建的逐字段比对）+ 断言
`search.required == ["query", "project_root"]`、参数集合 `{query, project_root, max_tokens}`
未变，`ask.required == ["question", "project_root"]`——**两个工具的输入 schema 保持
query/question + project_root + max_tokens，未加任何鉴权字段**。

#### 契约影响

**无。** 未改 `docs/contracts/**`、`docs/design/**`、`core/zace_core/{types,interfaces,hashing}.py`。

#### 与设计偏差

1. **工具级 404 的承载形态**：卡内 DoD 原文写"→ **404**（不是 200，不是 500）"，但 MCP 协议下
   `tools/call` 的工具执行错误是 **HTTP 200 + `isError:true`**（Module/05 §2.2 明文：参数错误 →
   -32602；工具执行错误 → 正常响应 + isError）。HTTP 404 在 Streamable HTTP 里另有语义
   （会话不存在）。经与用户确认，落为 **`isError` + 与 REST 404 逐字同文案**——保住卡内
   "不给探测面"的**目的**，同时不违反协议。若编排者要求字面 HTTP 404，需在 ASGI 层解析
   JSON-RPC body 并重写归属校验（无法复用 `deps`，与 §B 第 5 行"复用不要另写"冲突）。
2. **云端"不存在"文案收敛**：见上文 §B 最后一条（安全必需，非风格选择）。

#### 未决问题

1. **`GET /healthz` 在云端列出全部 projectId（枚举面）**：`ops.py::_project_progress` 会把
   `list_projects()` 的全部 id 放进 `/healthz`。云端形态下任何**未认证**方（`/healthz` 在
   `PUBLIC_PATHS` 里）都能枚举全部 projectId——虽然 projectId 单独不足以越权（本卡后仍需归属），
   但它是一个可被用于针对性尝试的信息面。**未改**：`ops.py` 属泳道 D（TASK-090）的文件所有权，
   按纪律只登记，交编排者裁决（建议：云端形态下 `/healthz` 只返回计数，不返回 id 列表）。
2. **`projectId` 的可猜测性**：D-29 的 `projectId = sha256(identity_key)[:16]`，而 identity_key 对
   非 git 目录就是绝对路径的 hash。共用仓库的协作者能算出同一 id——这正是本卡把归属校验接上的
   原因（"知道 id"不再等于"能访问"）。但 `resolve` 对已被他人认领的 projectId **不报错**
   （TASK-061 §A0 口径 A），因此协作者仍能 resolve 成功却拿不到数据——V1 既定简化，V2 的 `org_id`
   共享才会改变这一点。本卡未动该口径。

#### 建议复核点

1. `_IdentityBinding` 只**读** `scope["state"]["zace_user"]`，**不做**任何鉴权解——确保它不是第二道
   鉴权，也就不会与 `app.py` 的中间件产生口径分歧（未认证请求在中间件层已被 401 拦掉）。
2. `_require_owned_project` 的两形态分支（无账户 vs 有账户）与本地模式 R34 文案逐字保留；
   `test_mcp_local_mode_unknown_project_keeps_actionable_hint` 断言了"本地文案不被云端文案顶替"。
3. `test_mcp_identity_is_per_request_not_sticky`：同一 session 上换凭据必须看到新身份。

