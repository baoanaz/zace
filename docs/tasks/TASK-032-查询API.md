# TASK-032：查询 API（`/api/query/search` + `/api/query/ask` 降级包）

> 状态：review ｜ 阶段：Phase 2（M2a-1）｜ 硬依赖：TASK-031 ｜ soft 依赖：无
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

- **日期 / 分支**：2026-09-10 ｜ `feature/task-032_xwz0910`（从 `feature/task-031_xwz0910` 串联）
- **关键产物**：`service/zace_service/packmeta.py`（meta 的唯一转换点）、
  `service/zace_service/routers/query.py`（替换占位）、`service/tests/test_query_api.py`。

### 验收命令与结果

```text
$ uv run ruff check .
All checks passed!
$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
$ uv run pytest
575 passed, 2 skipped, 2 warnings in 14.69s   # 031 后为 552+2 → 本卡新增 23 条
$ uv run pytest service/tests
71 passed                                     # 030/031 的 48 条 + 本卡 23 条
```

### 真实 markdown 输出（HTTP 端点的实测响应片段）

```text
HTTP 200
meta: {"projectId": "a10cece14ec01e49", "query": "令牌过期后在哪里刷新", "mode": "fast",
 "checkpointId": null, "answerable": true, "confidence": "medium",
 "channelsUsed": ["bm25", "vector"], "degraded": false, "degradedReason": null,
 "candidateCount": 5, "freshness": {"indexedAt": 1789045325, "staleFiles": [], "indexingFiles": []},
 "budget": {"usedTokens": 578, "hardCap": 10000, "truncated": false, "omittedCount": 0},
 "evidenceCount": 1, "docsCount": 1, "flowsCount": 0, "missingEvidence": []}
--- markdown ---
## Relevant Context
### Code
[E2] TokenService — src/token_service.py:1-9
     reason: bm25 rank 4 + vector 0.3175 + vector rank 4 + entry point / exported symbol +0.2 + 相邻区间合并
     1 | """令牌服务模块。"""
     ... （省略 1 行）
     4 | class TokenService:
     7 |     def refresh_token(self) -> str:
     8 |         """续期令牌：过期后由本方法负责刷新，签发细节见设计文档。"""
     9 |         return "old"
### Docs
[E1] docs/design/token.md > 令牌设计（design）
     reason: bm25 rank 1 + vector 0.5470 + vector rank 1 + high-value doctype +0.8 + 相邻区间合并
     1 | # 令牌设计
     3 | 令牌过期时由 `refresh_token` 刷新。
--- ask ---
status: degraded | answer 前 3 行:
Deep 模式（LLM 总结）尚未接入（Phase 3）；以下为检索与组装结果，可直接作为上下文使用。

## Relevant Context
evidenceSummary[0]: {"id": "E1", "type": "code", "path": "src/token_service.py", "lines": [1, 9], "tier": 0, "score": 8.33}
```

（证据行确实是 ``path:行号`` 形态（``src/token_service.py:1-9`` 标题 + ``7 | def refresh_token`` 正文），
行号与源文件逐行对应：可直接给 agent 对齐 Edit。）

### 契约影响

无。未改 `docs/contracts/**`；消费 CF-05（两路径与响应字段）与 CF-03（``to_json`` 后送 schema 校验）。
本卡**产出**的 `meta` 字段集是 TASK-040 的输入契约（已冻结在 `packmeta.py` 的 ``meta_field_names()``，
测试断言字段集与实现一致）。

### 与设计偏差

1. **`meta` 增加 `checkpointId`**：卡内“端点行为”明确要求“checkpointId 只透传记录进 meta”，
   但卡内的 meta 字段清单漏列该字段。按“只增不改”处理（对 TASK-040 是加法，不破坏冻结集）。
2. **`ask` 的 `meta.mode` = `"fast"`**（取 ``pack.mode``，即实际组装模式），而非 `"deep"`：
   降级由 `status="degraded"` + `meta.degraded=true` 表达。Phase 2 确实只跑了 Fast 组装，
   写 `"deep"` 会掩盖实际行为（D-26 的诚实性要求）。
3. **“必然缺失的查询”测试换了实现口径（重要）**：实测“查询仓库里不存在的符号”
   （`ZzqxwvNotARealSymbol` / `NonexistentSymbolXYZ123` / 自然语言负例）在 M1/M2a **恒**返回
   1 evidence + 1 docs、`missingEvidence` 为空——向量通道总会给出候选，`no_context_match`
   在组装层不可达（正是 R22 登记的诚实性缺口）。因此改用**可复现**的缺失来源：删掉被文档引用的
   代码文件（G4）→ `stale_doc_reference`；另加一条 `retrieval_truncated`（极小 maxTokens）。
   未越界修检索/组装（R30 参数冻结）。
4. **空索引判定**用 `sync_status()["chunks"] == 0`（core 的 ``Store.counts()``），不另做统计。
5. **`ask` 的检索预算**固定用 `DEFAULT_MAX_TOKENS`（10K）：CF-05 的 ask 入参没有 `maxTokens`。
6. `includePack` 只在 search 上支持（ask 的响应里没有 pack 字段位；CF-05 亦然）。

### 未决问题

1. **`no_context_match` 在真实链路不可达**（负例诚实性，R22/R24 已登记）：属检索质量范畴，
   需真实数据到位后评估（TASK-023 → TASK-050），本卡不碰参数（R30）。
2. **`jsonschema` 由 core 的 dev extra 提供**（卡内明确允许 service 测试直接用）。若将来
   service 单独建 CI（只装 service extras）会缺该依赖；建议编排者决定是否将其加入 service dev extra
   （本卡不擅自新增依赖）。
3. `checkpointId` 目前只记录不校验（TASK-033 登记 checkpoint；与检索的强校验属 client 侧优化）。
4. `answerable=false` 时 `ask` 仍返回 `status="degraded"`（而非 `insufficient_evidence`）：
   Phase 2 根本没有 LLM，把“无 LLM”写成“证据不足”是误导；Phase 3 接入后再区分。

### 建议复核点

① `packmeta.pack_meta` 是否真是唯一转换点（路由里不得再拼 meta 字段）；
② `ask` 的降级文案与“绝不 500”的断言；③ 409 空索引语义（不返回 200 空包）；
④ `meta` 字段集的冻结方式（`meta_field_names()` + 测试断言）。
