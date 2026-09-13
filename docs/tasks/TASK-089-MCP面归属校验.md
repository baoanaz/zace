# TASK-089：MCP 面归属校验（上云前的最后越权口）

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：TASK-061（已合并）｜ soft 依赖：无
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

- [ ] `uv run pytest service/tests/ -q` 全绿，**必须覆盖**：
  - [ ] 云端形态：B 用 A 的 `projectId` 调 `search_context` → **404**（不是 200，不是 500）；
  - [ ] 云端形态：B 调 `ask_project` 同理 → **404**；
  - [ ] 云端形态：无凭据 → **401**；
  - [ ] 归属者自己调两个工具 → **正常**（不误伤）；
  - [ ] **本地模式**：全部既有测试原样通过（R34 第一验收项）。
- [ ] 行为验收（贴真实输出）：两个真实用户 + 真实 MCP 客户端（可用 `mcp` SDK 或 curl 直连
      `/mcp` 的 Streamable HTTP），贴出 404 与 200 的对照。
- [ ] CF-06 未改：`git diff` 证明 `docs/contracts/mcp-tools.json` 零改动，且工具 schema 的
      `required` 字段集未变。
- [ ] 基线三条命令全绿（用 `-o addopts=""` 看数字）。
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- 不改 CF-06 契约；
- 不做 org/团队共享（V2）；
- 不改 REST 面的既有校验（TASK-061 已验收）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：§A 方案选择与理由、CF-06 未改的 diff 证据、
两个工具 × 三种身份（归属者/他人/无凭据）的实测矩阵。

## 执行记录

（实施 AI 在此填写。）
