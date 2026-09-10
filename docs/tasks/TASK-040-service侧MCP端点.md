# TASK-040：service 侧 MCP 端点（Streamable HTTP，编辑器直连）+ 编辑器配置输出

> 状态：pending ｜ 阶段：Phase 2（M2a-2，**demo 收口卡**）｜ 硬依赖：TASK-034 ｜ soft 依赖：无
> 建议分支：`feature/task-040_<你的缩写><MMDD>`（从 TASK-034 分支串联）
> 交付物所有权：
> - `service/zace_service/mcp.py`（新建：MCPServer 装配 + 两个工具 + 挂载）
> - `service/zace_service/app.py`（追加挂载与 lifespan 组合）
> - `service/zace_service/cli_hint.py`（新建：输出编辑器 MCP 配置片段）
> - `service/zace_service/__main__.py`（启动后打印配置片段）
> - `service/pyproject.toml`（新增 `mcp>=2.2` 依赖 + 注释）
> - `service/tests/test_mcp_endpoint.py`（新建）
>
> 清单外文件不得改。

## 目标

让编辑器（Cursor / Codex 等）**通过 URL 直连**本地 service，不再需要独立的 Rust 客户端：

```jsonc
// ~/.cursor/mcp.json  或项目内 .cursor/mcp.json
{ "mcpServers": { "zace": { "url": "http://127.0.0.1:8787/mcp" } } }
```

这是 M2a 的最后一张卡。做完即可用真实问题在编辑器里验证（demo 验收）。

## 架构裁定（用户 2026-09-10 拍板，见 contracts.md R38）

原设计（Module/05）把 MCP 放在 **Rust client** 里，前提是**服务在远端**——client 需要扫描本地代码、
算 hash、上传 blob。本地模式下 service 与代码同机同文件系统，这个前提不成立：
service 直接索引本地仓库（TASK-034），同步环节整体消失。

**故**：M2a 由 service 直接提供 MCP Streamable HTTP 端点；**Rust client 保留给远端场景**（M2c，
届时它才是必需的：在代码本地扫描/哈希/上传到 VPS）。

## 输入文档（按序读，只读所需章节）

1. `docs/contracts/mcp-tools.json`（**CF-06：工具名/参数名/类型/默认值/上限是冻结合同**，description 文案可打磨）
2. `docs/design/Module/05-MCP与同步.md` §2（工具语义）、§5（渲染在服务端——**客户端只透传 Markdown**）、§7（安全）
3. `docs/design/Module/03-上下文组装.md` §4.4（answerable 与 confidence 的语义，工具返回值要如实反映）
4. `docs/plan/contracts.md` §3.8（R34/R37：本地模式免鉴权、`projectId` 可省略）
5. `service/zace_service/routers/query.py` 与 `packmeta.py`（TASK-032：**复用**，不要重新实现检索与渲染）

## 冻结接口（本卡不得变更）

- **消费**：CF-06 工具 schema、TASK-032 的 `meta` 字段集、`render_markdown`（渲染只能在服务端发生一次）。
- **产出**：`zace_service.mcp.build_mcp(engine_manager) -> MCPServer`、`zace_service.mcp.mount(app, mcp)`、
  `zace_service.cli_hint.editor_config_snippets(port) -> dict[str, str]`。

## 已验证的实现要点（编排者实测，2026-09-10；**照做，别重新踩坑**）

> 以下结论来自编排者在 `mcp==2.2.0` 上的真实冒烟（FastAPI + MCPServer + initialize/tools list/tools call 全通过）。

1. **必须用 v2 的导入路径**：`from mcp.server.mcpserver import MCPServer`。
   `mcp.server.fastmcp` 在 2.x 已移除，导入会直接抛 `ModuleNotFoundError`（v2 把 FastMCP 更名为 MCPServer）。
2. **挂载必须传 `streamable_http_path="/"`**，否则内部路径与挂载前缀叠加成 `/mcp/mcp` → 全 404：
   ```python
   app.mount("/mcp", mcp.streamable_http_app(streamable_http_path="/"))
   ```
3. **session manager 的 lifespan 必须跑**，否则 initialize 无法建立会话：
   ```python
   @asynccontextmanager
   async def lifespan(app):
       async with mcp.session_manager.run():
           yield
   ```
   （注意：它要与 TASK-030 既有的 lifespan 组合，不要覆盖掉已有逻辑。）
4. **DNS-rebinding / Origin 防护默认已开且有效**：带 `Origin: http://evil.example` 的请求返回
   **403 `Invalid Origin header`**；不带 Origin 的请求（curl / 多数本地客户端）正常 200。
   **不要**为了"跑通"把 `enable_dns_rebinding_protection` 关掉；若特定编辑器带 Origin，用
   `TransportSecuritySettings(allowed_origins=[...])` 显式放行并在执行记录里写明放了哪个。
5. 响应默认是 **SSE 格式**（`event: message\ndata: {json}`）；`json_response=True` 可改成纯 JSON。
   若编辑器兼容性出问题可切换，但要在执行记录里说明理由。

## 两个工具（CF-06）

- `search_context(query, maxTokens?, projectId?)` → 文本内容 = `render_markdown(pack)`
  - 复用 TASK-032 的 `packmeta.pack_meta(...)`（**不要**另写一份 meta）
  - `answerable=false` 时**照常返回证据**，并在文本里保留 `missingEvidence` 段（D-30 诚实性；不要因为
    "不可回答"就返回空，编辑器需要看到已检索到什么）
  - 空索引 → 返回**可操作的错误文本**（`isError=true`），含 TASK-034 的进度信息与"稍后重试"提示
    （Module/05 §3.5 的 index_in_progress 语义）
- `ask_project(question, projectId?)` → Phase 2 走 TASK-032 的降级包（LLM 属 Phase 3）：
  文本 = 降级说明 + 渲染正文，**必须显式写出"Deep 模式未接入"**，不得让 agent 误以为是 LLM 总结

**并发纪律**：core 调用是阻塞的（检索 ~0.5s，大仓库可能更久），工具必须写成
`async def` 并用 `anyio.to_thread.run_sync`（或 `starlette.concurrency.run_in_threadpool`）执行，
**不得**在事件循环里直接跑阻塞调用。

**参数校验**：非法参数（空 query、超限 maxTokens）→ 返回 `isError=true` 的可读文本，
不要在工具里抛异常让协议层报 500。

## 编辑器配置输出（`cli_hint.py` + `__main__`）

启动时打印（也提供 `zace-service mcp-config --port 8787` 单独输出）：

```text
Cursor（项目内 .cursor/mcp.json 或全局 ~/.cursor/mcp.json）：
{ "mcpServers": { "zace": { "url": "http://127.0.0.1:8787/mcp" } } }

Claude Code / 其它支持 HTTP 的 harness：<同样给 URL 形态；不支持的写明"需要 stdio 代理（M2c 的 Rust client）">
```

**不要**在输出里写 token（本地模式无鉴权）或任何绝对隐私路径以外的敏感信息。

## 验收标准（DoD）

- [ ] 协议冒烟（`service/tests/test_mcp_endpoint.py`，用 httpx + 真实 ASGI 应用，**不联网**）：
      `initialize` → 200 且返回 `mcp-session-id`；`notifications/initialized` → 202；
      `tools/list` → 恰好两个工具且**参数名/schema 与 CF-06 逐字段一致**（名字、类型、默认值、上限都断言）；
      `tools/call search_context` → 返回文本含 `render_markdown` 的证据行（`路径:行号`）。
- [ ] 恶意 Origin → 403（回归断言：不得为了跑通而关掉防护）。
- [ ] 错误面：空 query → `isError=true` 且文本可读；未知 projectId → `isError=true`；空索引 → `isError=true` + 重试提示。
- [ ] `json_response` 与 SSE 两种响应形态至少各有一条测试（或说明为何只测一种）。
- [ ] **真实进程 + 真实编辑器协议客户端**（贴执行记录）：起服务后用一个最小 MCP 客户端脚本走完
      initialize → tools/list → tools/call，贴出返回的 Markdown 片段（**这是 demo 的真实凭证**）。
- [ ] 真实仓库端到端（**必做**）：用已索引的 aibox 数据根
      （`--data-root /tmp/zace-aibox`，project `8f39057792cf72e8`）或走 TASK-034 的 attach 起服务，
      用**用户种子问题**「workflow 在记忆系统里是怎么定义和使用的？」调用 `tools/call`，
      贴出返回文本的开头若干行与 `answerable/confidence`（**这就是 M2 的验收实测**）。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- 不做 Rust client / stdio transport（M2c；R38）。
- 不做 OAuth / 鉴权（本地模式无鉴权；远端归 M2c）。
- 不做 MCP prompts / resources / elicitation（只做 tools；D-12 的"少量高层工具"原则）。
- 不做 LLM / citation 回验（Phase 3）。
- 不改 CF-06 的 schema（工具名/参数/默认值/上限）。
- 不改 TASK-032 的 meta 字段集。

## 参考源码锚点（只读）

- 编排者的冒烟脚本结论见本卡"已验证的实现要点"（`mcp==2.2.0`）。
- `docs/contracts/mcp-tools.json`：工具 schema 的唯一事实来源。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；**必须包含用真实问题调用 search_context 的返回片段**。

## 执行记录

（实施 AI 在此填写。）
