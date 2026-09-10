# TASK-032：查询 API（`/api/query/search` + `/api/query/ask` 降级包）

> 状态：pending ｜ 阶段：Phase 2（M2a-1）｜ 硬依赖：TASK-031 ｜ soft 依赖：无
> 建议分支：`feature/task-032_<你的缩写><MMDD>`（从 TASK-031 分支串联）
> 交付物所有权：
> - `service/zace_service/routers/query.py`（替换占位实现）
> - `service/zace_service/packmeta.py`（新建：ContextPack → meta 字典的**唯一**转换点）
> - `service/tests/test_query_api.py`（新建）
>
> 清单外文件不得改（尤其 `core/zace_core/contextpack/**` 的渲染与组装逻辑）。

## 目标

跑通 M2a 的核心承诺：**服务端返回渲染好的 Markdown 上下文**，供 MCP client 直接透传给编辑器。
同时把 Deep 模式在"LLM 未接入（Phase 3）"期间的**降级行为**做诚实、可预期（D-26），
绝不因为 `Engine.ask()` 未实现而 500。

## 输入文档（按序读，只读所需章节）

1. `docs/design/Module/05-MCP与同步.md` §5（渲染在服务端、两个工具的链路）、§3.6（freshness 语义）
2. `docs/design/Module/03-上下文组装.md` §2（ContextPack 结构与字段）、§5（`missingEvidence` 七类）、§6（渲染格式）
3. `docs/contracts/openapi.yaml`（CF-05：`SearchResponse {markdown, meta}` / `AskResponse {answer, status, evidenceSummary, meta}`）
4. `docs/contracts/contextpack.schema.json`（CF-03，`includePack=true` 时返回）
5. `core/zace_core/contextpack/{render.py,assembly.py}`（`render_markdown` / `to_json`；`assemble` 的 `_assess`）
6. `docs/plan/contracts.md` §3.6 R29/R30/R31（**不得为了指标调参**）

## 冻结接口（本卡不得变更）

- **消费**：CF-03（`to_json`）、CF-05（两个路径与响应字段）、`ContextPack` 全部字段（CF-04）。
- **产出**：本卡定义的 `meta` 字段集是 **TASK-040（client）的输入契约**，写出后不得随意改：
  ```
  search.meta = {
    projectId, query, mode,
    answerable: bool, confidence: "high"|"medium"|"low",
    channelsUsed: [str], degraded: bool, degradedReason: str|null,
    candidateCount: int,
    freshness: {indexedAt: int|null, staleFiles: [str], indexingFiles: [str]},
    budget: {usedTokens: int, hardCap: int, truncated: bool, omittedCount: int},
    evidenceCount: int, docsCount: int, flowsCount: int,
    missingEvidence: [{code, message, symbol|null}],
    pack: object|null          # includePack=true 时，CF-03 的完整 JSON
  }
  ask.meta = 同 search.meta；ask.evidenceSummary = [{id, type, path, lines, tier, score}]（≤10 条）
  ```

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `service/zace_service/packmeta.py` | `pack_meta(pack, *, project_id, channels=None, degraded=False, reason=None, candidate_count=None, include_pack=False) -> dict`；**所有字段转换只在这里发生**，路由保持薄 |
| `service/zace_service/routers/query.py` | 两个端点 + 入参校验 + 错误语义（见下） |
| `service/tests/test_query_api.py` | 见 DoD |

## 端点行为（必须逐条实现）

### `POST /api/query/search`

- 入参：`{projectId?, checkpointId?, query: str, maxTokens?: int = 10000, includePack?: bool = false}`
  （`projectId` 可省略见 R37 本地模式；本卡先按"省略 → 用 local project"实现，`EngineManager` 未提供时返回 501——不要在 TASK-033 之前实现 checkpoint 校验，`checkpointId` 只**透传记录进 meta**，值不参与检索。）
- 校验：`query` 非空且 ≤ 2000 字符 → 否则 400 `invalid_query`；`maxTokens` ∈ (0, 20000] → 否则 400 `invalid_max_tokens`；project 不存在 → 404 `project_not_found`。
- **空索引**（`sync_status().chunks == 0`）→ **409 `index_in_progress`**，`message` 含"尚未索引/请先同步"的 hint（D-30 的例外条款；**不返回 200 空包**，那会让 agent 误以为仓库里没有相关代码）。
- 正常 → 200 `{markdown, meta}`；`markdown = zace_core.contextpack.render_markdown(pack)`（**不重新实现渲染**，D-21）。
- `channelsUsed` / `degraded` / `candidateCount`：来自 `Engine.search_with_trace`（R33 允许用 core 的具体类）。

### `POST /api/query/ask`

- 入参：`{projectId?, checkpointId?, question: str}`
- **Phase 2 M2a 无 LLM**（`Engine.ask()` 抛 `NotImplementedError`，Phase 3 才实现）→ 一律返回 200：
  ```json
  { "status": "degraded",
    "answer": "<降级说明 + 空行 + render_markdown(pack)>",
    "evidenceSummary": [{...}],
    "meta": {...} }
  ```
  降级说明必须写清：**"Deep 模式（LLM 总结）尚未接入（Phase 3）；以下为检索与组装结果，可直接作为上下文使用。"**
- 同样适用空索引 409、校验 400、project 404。
- **禁止**：抛 500、返回空 `answer`、静默退回 search 而不标注 `status`。

## 验收标准（DoD）

- [ ] 小仓库 fixture（temp data_root + 假 embedding provider + 2 个含中文注释的 py 文件 + 1 个 markdown）：
      search 200；`meta.answerable/confidence` 与 `pack` 一致；`meta.evidenceCount/docsCount/flowsCount` 与 pack 的长度一致；markdown 含 `path:行号` 形态的证据行。
- [ ] `missingEvidence` 透传：构造一个必然缺失的查询（如仓库里不存在的符号），断言 `meta.missingEvidence` 非空且每项含 `code` + `message`。
- [ ] 空索引：**409 `index_in_progress`**（search 与 ask 各一条断言）。
- [ ] ask 降级：200 + `status="degraded"` + `answer` 非空且包含 markdown 正文 + `evidenceSummary` ≤10（**断言不抛 500**）。
- [ ] `includePack=true`：`meta.pack` 通过 CF-03 schema 校验（用 `jsonschema`；core 的 dev extra 已有，service 测试可直接用）。
- [ ] 校验与错误：缺 query→400；`maxTokens=0` 与 `99999`→400；未知 project→404；错误 body 均为 CF-05 信封。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] 任务卡"执行记录"已回填（**必须贴一段真实的`markdown` 输出片段**，证明渲染与行号正确）；任务板对应行状态改 `review`。

## 性能参考（不设硬门禁）

M1 实测检索 ~0.5s 级；client 侧整体超时 15s（D-32）。`meta` 里**不要**加入昂贵的统计查询
（如逐文件计数）——需要就给 `sync_status`。

## 明确不做

- 不接 LLM / 不做 citation 回验（Phase 3 Module/04）。
- 不做 Module/02 §4.5 的 Deep 二轮检索（G 表二轮）——随 Phase 3 一起。
- 不做 checkpoint 校验（TASK-033）、不做鉴权（M2c）。
- **不改 core 的渲染格式、不改装填与排序参数**（R30 冻结；渲染格式变更会破坏 client 的透传假设）。
- 不做 SSE / 流式响应。

## 参考源码锚点（只读）

- `core/zace_core/cli/app.py::_cmd_search`（CLI 如何调用引擎与打印，形态参考）
- `core/zace_core/contextpack/assembly.py::to_json`（CF-03 序列化）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写。）
