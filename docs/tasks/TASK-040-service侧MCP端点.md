# TASK-040：service 侧 MCP 端点（Streamable HTTP，编辑器直连）+ 编辑器配置输出

> 状态：review ｜ 阶段：Phase 2（M2a-2，**demo 收口卡**）｜ 硬依赖：TASK-034 ｜ soft 依赖：无
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

- [x] 协议冒烟（`service/tests/test_mcp_endpoint.py`，用 httpx + 真实 ASGI 应用，**不联网**）：
      `initialize` → 200 且返回 `mcp-session-id`；`notifications/initialized` → 202；
      `tools/list` → 恰好两个工具且**参数名/schema 与 CF-06 逐字段一致**（名字、类型、默认值、上限都断言）；
      `tools/call search_context` → 返回文本含 `render_markdown` 的证据行（`路径:行号`）。
- [x] 恶意 Origin → 403（回归断言：不得为了跑通而关掉防护）。
- [x] 错误面：空 query → `isError=true` 且文本可读；未知 projectId → `isError=true`；空索引 → `isError=true` + 重试提示。
- [x] `json_response` 与 SSE 两种响应形态至少各有一条测试（或说明为何只测一种）。
- [x] **真实进程 + 真实编辑器协议客户端**（贴执行记录）：起服务后用一个最小 MCP 客户端脚本走完
      initialize → tools/list → tools/call，贴出返回的 Markdown 片段（**这是 demo 的真实凭证**）。
- [x] 真实仓库端到端（**必做**）：用已索引的 aibox 数据根
      （`--data-root /tmp/zace-aibox`，project `8f39057792cf72e8`）或走 TASK-034 的 attach 起服务，
      用**用户种子问题**「workflow 在记忆系统里是怎么定义和使用的？」调用 `tools/call`，
      贴出返回文本的开头若干行与 `answerable/confidence`（**这就是 M2 的验收实测**）。
- [x] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [x] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

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

### 2026-09-11 · 实施 AI · 分支 `feature/task-040_xwz0911`（从 `feature/task-034_xwz0910` 串联）

**改动文件**（全部在卡内“交付物所有权”清单内）：

| 文件 | 内容 |
|---|---|
| `service/zace_service/mcp.py`（新建） | `build_mcp` / `mount` / `session_lifespan` / `manager_for_app`；两个工具 + 错误面 |
| `service/zace_service/cli_hint.py`（新建） | `editor_config_snippets` / `format_snippets` / `mcp_url` |
| `service/zace_service/app.py`（追加） | `_install_mcp`：挂载 + 接管 lifespan |
| `service/zace_service/__main__.py`（追加） | `mcp-config` 子命令；`local`/`serve` 起服务前打印配置片段 |
| `service/pyproject.toml`（修改） | 新增唯一依赖 `mcp>=2.2`（带注释） |
| `service/tests/test_mcp_endpoint.py`（新建） | 29 条协议/契约/错误面测试 |

**编排者的“已验证的实现要点”全部照做**（未重新摸索）：导入 `mcp.server.mcpserver.MCPServer`；
`streamable_http_path="/"`；`session_manager.run()` 的 lifespan；Origin 防护**保留**；SSE 为默认形态。

**验收命令与结果**

```text
$ uv run ruff check .
All checks passed!
$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
$ uv run pytest
656 passed, 2 skipped, 1 warning in 63.01s     # 其中 test_mcp_endpoint.py: 29 passed
```

协议冒烟（httpx + 真实 ASGI 应用，不联网）逐条对应卡内 DoD：

| DoD | 测试 |
|---|---|
| `initialize` → 200 + `mcp-session-id`；`notifications/initialized` → 202 | `_connected()` 被全部用例使用（断言 200 + session id + 202） |
| `tools/list` 恰好两个工具且 **schema 与 CF-06 逐字段一致** | `test_tools_list_matches_cf06_field_by_field`（`_schema_diff` 逐字段比 `docs/contracts/mcp-tools.json`） |
| `tools/call search_context` → 含 `路径:行号` 证据行 | `test_search_context_returns_rendered_evidence` / `..._uses_doc_evidence_too` |
| 恶意 Origin → 403 | `test_malicious_origin_is_rejected`（403 + 无 Origin 200 + 本机 Origin 200） |
| 空 query / 未知 projectId / 空索引 → `isError` | `test_whitespace_query_*` / `test_empty_query_is_rejected` / `test_unknown_project_root_is_actionable` / `test_empty_index_returns_progress_and_retry_hint` |
| 两种响应形态各一条 | `test_default_response_is_sse` / `test_json_response_mode_is_available` |
| async + 线程池（不在事件循环里跑阻塞调用） | `test_blocking_core_call_runs_in_threadpool`（monkeypatch `run_in_threadpool` 断言走的就是它） |
| 复用 TASK-032 的 meta 与 render_markdown | 代码里只 import `packmeta.pack_meta` 与 `zace_core.contextpack.render_markdown`，无第二份实现 |

**真实进程 + 真实编辑器协议客户端（官方 SDK，Streamable HTTP）**

```console
$ uv run zace-service local --repo /home/xuwenzheng/zace-scratch/demo-repo \
      --data-root ~/zace-scratch/data-demo --port 8792
zace-service local 已启动（127.0.0.1:8792）
  projectId : e6fe81dbaebfb65d
  MCP       : http://127.0.0.1:8792/mcp（Streamable HTTP）

Cursor（项目内 .cursor/mcp.json 或全局 ~/.cursor/mcp.json）：
{ "mcpServers": { "zace": { "url": "http://127.0.0.1:8792/mcp" } } }

$ NO_PROXY=127.0.0.1,localhost uv run python mcp_client_demo.py \
    http://127.0.0.1:8792/mcp /home/xuwenzheng/zace-scratch/demo-repo "refresh_token 是怎么刷新会话的？"
== initialize == server=zace protocol=2025-11-25
== tools/list == (2 个)
  - search_context(query, project_root, max_tokens) required=['query', 'project_root'] additionalProperties=False
  - ask_project(question, project_root, max_tokens) required=['question', 'project_root'] additionalProperties=False
== tools/call search_context == isError=False
[zace] answerable=true · confidence=medium · evidence=1 · docs=1 · mode=fast · channels=inferred,bm25,vector · degraded=false

## Relevant Context
### Code
[E1] SessionStore.refresh_token — session.py:1-13
     reason: inferred symbol refresh_token + inferred rank 1 + bm25 -1.3818 + bm25 rank 1 + vector 0.9333 + vector rank 1 + query symbol == chunk symbol +1.0 + 3-channel consensus +0.5 + 相邻区间合并
    11 |     def refresh_token(self, token: str) -> str:
    12 |         """刷新会话 token：过期后由本方法负责续期。"""
    13 |         return token + "-refreshed"
```

新增代码后再问（MCP 侧的懒重扫入口，TASK-034 §C 的第二个触发点）：

```text
$ # 向 session.py 追加 revoke_token() 后 sleep 4
$ ... "revoke_token 吊销会话是怎么实现的？"
== tools/call search_context == isError=False
[zace] answerable=true · confidence=medium · evidence=1 · docs=1 · mode=fast · channels=inferred,bm25,vector
[E1] revoke_token — session.py:1-18
```

`ask_project`（Phase 2 降级包，实测首行就写明“未接入”）：

```text
Deep 模式（LLM 总结）尚未接入（Phase 3）；以下为检索与组装结果，可直接作为上下文使用。

[zace] answerable=true · confidence=medium · evidence=1 · docs=1 · mode=fast · channels=bm25,vector · degraded=true
```

**错误面（真实进程，非 TestClient）**

```text
# 空索引（--no-index 起的服务）
Error executing tool search_context: 项目 79043b7afde92ac6 暂无可用索引（chunks=0），当前索引状态：idle（本进程还没为它跑过索引）。
如果刚启动本地服务，后台索引可能还在跑：**稍后重试本查询**，或用 GET /api/projects/79043b7afde92ac6 查看 indexProgress；

# 未知 project_root
Error executing tool search_context: 未知项目：/home/xuwenzheng/zace-scratch/no-such-indexed-dir 对应的 projectId df94e7b4d795324b 在本服务里没有索引记录（D-29 身份）。本地模式请用 `zace-service local --repo ...` 起服务，或先 POST /api/projects/attach；远端模式请先同步（POST /api/sync/batch-upload）。

# 恶意 Origin
$ curl -s --noproxy '*' -o /tmp/o.txt -w "status=%{http_code}\n" --max-redirs 0 -X POST http://127.0.0.1:8792/mcp \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -H 'Origin: http://evil.example' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
status=403          # 响应体：Invalid Origin header
# 同一请求：本机 Origin → 200；不带 Origin → 200
```

**真实仓库端到端（aibox，用户种子问题）**

```text
$ uv run zace-service local --repo /home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk \
      --data-root ~/zace-scratch/data-aibox --port 8794
zace-service local 已启动（127.0.0.1:8794）
  projectId : 8f39057792cf72e8      # 与卡内 /tmp/zace-aibox 那个 projectId **一致**（git remote 身份，D-29 可重现）
  MCP       : http://127.0.0.1:8794/mcp（Streamable HTTP）
}
{"logger": "zace_service.indexer", "msg": "开始索引：8f39057792cf72e8（root=…/aibox-super-sdk，files=451）"}
{"logger": "zace_service.indexer", "msg": "索引完成：8f39057792cf72e8（parsed=434/451，added=434，modified=0，deleted=0，errors=2）"}
# startedAt=1789093437 / finishedAt=1789096917 → 共 58 分钟（本机同时有另两个泳道在跑 benchmark，CPU 争用）
```

**用户种子问题**（`tools/call search_context`，官方 SDK 客户端，真实进程）：

```console
$ MCP_PRINT_LIMIT=0 NO_PROXY=127.0.0.1,localhost uv run python mcp_client_demo.py \
    http://127.0.0.1:8794/mcp /home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk \
    "workflow 在记忆系统里是怎么定义和使用的？"
== initialize == server=zace protocol=2025-11-25
== tools/list == (2 个)
  - search_context(query, project_root, max_tokens) required=['query', 'project_root'] additionalProperties=False
  - ask_project(question, project_root, max_tokens) required=['question', 'project_root'] additionalProperties=False
== tools/call search_context == isError=False
[zace] answerable=true · confidence=medium · evidence=6 · docs=5 · mode=fast · channels=bm25,vector · degraded=false

## Relevant Context
### Code
[E5] MEMORY_TOOLS — src/aibox/capabilities/memory/example/chatbot/agent.py:90-195
     reason: bm25 -16.7298 + bm25 rank 1 + 相邻区间合并
     90 | MEMORY_TOOLS: list[dict[str, Any]] = [
     91 |     {
     92 |         "type": "function",
     94 |             "name": "add",
     95 |             "description": (
     96 |                 "存储用户的重要信息到记忆系统。"
     98 |                 "content 必须是用户原话（第一人称），不要改写成「用户/他/她…」。"
     …（中略：113–121 行是 search 工具的声明）
[E7] MemoryRepl — src/aibox/capabilities/memory/example/repl/session.py:49-51
[E8] AddEventRequest — src/aibox/capabilities/memory/types/evidence.py:89-98
[E9] BaseCapability — src/aibox/capabilities/base.py:86-98
[E10] MemoryService — src/aibox/capabilities/memory/service.py:56-60
[E11] ErrorCode — src/aibox/models/errors.py:11-42
### Docs
[E1] src/aibox/capabilities/memory/doc/记忆系统1.0详细设计.md > 记忆系统 1.0 详细设计 > 5. 长期记忆语义边界（guide）
[E2] src/aibox/capabilities/memory/doc/记忆系统1.0详细设计.md > 记忆系统 1.0 详细设计 > 7. 异步抽取、队列和恢复 > 7.1 SQLite Job 是唯一事实队列（guide）
[E3] src/aibox/capabilities/memory/doc/记忆系统调研/记忆系统调研.md > … > 2.6 ByteRover > ⑧ 对车载场景的启发（guide）
[E4] src/aibox/capabilities/memory/doc/记忆系统调研/记忆系统设计精要.md > (preamble)（guide）
[E6] src/aibox/capabilities/memory/doc/V1.0/V1.0开发计划进展.md > … > 2.1 最小闭环（guide）
### Missing Evidence
- [unresolved_reference] 62 个符号引用无法解析（unresolved_refs status=failed），涉及这些符号的调用关系可能缺失。
- [retrieval_truncated] 候选池被预算裁剪：省略 83 个候选（其中 82 个因 spec 份额上限让位给代码证据），可能有相关但未展示的证据；可提高预算或收窄查询。
### Meta
confidence: medium | index: fresh (1 h ago) | budget: 2.8K/10.0K
```

判读：`workflow` 是个词面上不存在的词（这个仓库把它表达为 tool 声明与设计文档里的「流程」），
但 6 条代码证据 + 5 条设计文档证据都落在 `capabilities/memory/**`，**且 `Missing Evidence` 如实报出
了两条局限**（62 个引用未解析、83 个候选被预算裁掉）——这正是 M2 想要的形态：
给可得的最好证据 + 明说自己缺什么，而不是编一个看起来完整的答案。

**索引期间检索也是可用的（如实但不完整）**：在同一次运行的**索引未完成时**问同一句：

```text
[zace] answerable=false · confidence=low · evidence=1 · docs=6 · mode=fast · channels=bm25 · degraded=false
```

对比点：`channels` 只剩 `bm25`（向量还没写完）、`answerable=false`。即：**服务不假装就绪**，
但也不把已有结果丢掉——编辑器看到的是“当前能拿到的最好证据 + 尚未就绪的可信标记”。

### 与设计偏差 / 需登记的改动

1. **`mount` 额外注册了一条同端点别名路由（无重定向）。** Starlette 的 `Mount` 只匹配
   `/mcp/...`，因此 `POST /mcp` 会先 307 到 `/mcp/`，而是否跟随重定向取决于编辑器用的 HTTP 客户端。
   真实进程实测（`--max-redirs 0`）：修前 `POST /mcp` → `307`，修后 → `200`（两个 URL 都直接可用）。
   测试 `test_advertised_url_works_without_redirect`（`follow_redirects=False`）守住这一点。
2. **建工具时补 `additionalProperties: false`。** SDK 从签名生成的 schema 不含该键，而 CF-06 声明了它。
   补这个键是纯声明性的（多余参数本来就被 pydantic 忽略），但它是卡里“逐字段一致”的硬要求。
3. **`ask_project` 的服务端 `max_tokens` 上限（20000）。** CF-06 只给 `minimum: 1`（无上限），而
   套餐预算直接把它当 `hard_cap`，所以服务端必须兵底；这是服务端限制，**不是 schema 变更**（未动 CF-06）。
4. **工具返回值首行多了 `[zace] answerable=… confidence=…` 摘要。** `render_markdown` 只渲染
   `confidence`，不含 `answerable`，而 Module/03 §4.4 要求工具返回值如实反映 answerable 的语义。
   正文仍逐字来自 `render_markdown(pack)`，本行只是 TASK-032 `pack_meta` 输出的一行摘要（不重新推导值）。
5. **MCP 侧的懒重扫入口（TASK-034 §C 的第二个触发点）。** 卡内 §C 指定的触发点是 HTTP query 路由；
   但编辑器走的是 `/mcp`，不补这一处就会出现“启动那一刻的索引”永不刷新。失败仍不得使检索失败。

### 未决问题

1. **`initialize` 协商到的协议版本是 `2025-11-25`**（卡内提到 SDK 支持 2025-11-25 / 2026-07-28）。
   客户端传什么就用什么（SDK 自管），本卡不干预；若某编辑器要求特定版本再议。
2. **响应形态只有 SSE 被真实编辑器验证过**。`json_response=True` 有单测覆盖但没在真实编辑器上跑；
   若某编辑器不兼容 SSE，可用这个开关（`mount(..., json_response=True)`），**届时要改 `app.py` 的装配**——
   属于一行改动，但未验证过其它编辑器的行为，故默认不开。
3. **工具结果没有统计/审计**（谁调了、花了多少预算）。Module/04 §8 的存档口属后续卡，本卡未涉及。
4. **aibox 全量索引 58 分钟**（451 文件，本机 CPU 被另两个泳道占满）。M2a 的 demo 体验可接受（后台跑、
   期间服务可用），但如果要反复重建索引，`.gitignore` 解析（D-28 缺口）与 embedding 提速值得排卡。
5. **`project_root` 必须是 D-29 能反解出 projectId 的路径**：如果用户在多台机器/多路径 attach 同一仓库，
   路径不同但 projectId 相同（git remote 身份），这符合预期；但**非 git 目录**换路径就换 projectId，
   工具会报“未知项目”并给出重启命令（已实测）。

