# TASK-087：ContextPack 渲染补齐（next_queries + answerable 短路）

> 状态：review ｜ 阶段：Phase 3（M2c）｜ 硬依赖：无 ｜ soft 依赖：TASK-088（LLM 接入，可并行）
> 建议分支：`feature/task-087-pack-render_<你的缩写><MMDD>`
> 交付物所有权：
> - `core/zace_core/contextpack/render.py`（补渲染节）
> - `core/tests/contextpack/`（新增/更新断言）
> - `service/zace_service/routers/query.py`（**仅** `ask` 端点的分支与返回形状）
> - `service/tests/test_query_api.py`（补用例）
>
> 清单外文件不得改。**特别提醒：不要改 `packmeta.py` 的字段集（CF-05 冻结）；不要改 `assembly.py`
> 的装填/打分逻辑（R29/R30 参数冻结）；不要改 `ask` 的 LLM 部分（那是 TASK-088）。**

## 目标

编排者实测发现 **ContextPack 产出的信号没有被 Agent 看到**，架构能力被浪费。本卡补齐两处：

| 信号 | 现状 | 本卡要做 |
|---|---|---|
| `pack.next_queries` | **已生成，但 `render_markdown` 不输出**（只在 `meta.nextQueries` 字段里） | 渲染进正文 |
| `pack.answerable == False` | 只在 `meta` 里，`ask` 仍走同一条路 | 短路为结构化降级包（D-24） |

**实测证据**（`HelloAgents` 仓库，查询「流式输出在哪个文件实现」）：

```
next_queries: ['docs/streaming-sse-guide.md 里还有哪些与查询相关的符号',
               '流式输出与 SSE 指南（Streaming & SSE） > 📖 概述 对应的实现代码在哪里']
missing_evidence: 2 条（unresolved_reference 70 个符号、retrieval_truncated 省略 57 候选）
```

`next_queries` 生成得很有用（直接告诉 Agent 下一步问什么），但当前**被丢弃**。

## §A 渲染 `next_queries`（core 侧）

`render_markdown` 的输出当前只有四节：

```
## Relevant Context
### Code
### Docs
### Missing Evidence
### Meta
```

**新增一节**（位置在 `Missing Evidence` 之后、`Meta` 之前，符合"先给证据、再给缺口、再给下一步"的阅读顺序）：

```markdown
### Suggested Next Queries
- docs/streaming-sse-guide.md 里还有哪些与查询相关的符号
- 流式输出与 SSE 指南（Streaming & SSE） > 📖 概述 对应的实现代码在哪里
```

要求：

- **`next_queries` 为空时不渲染该节**（空节不占 token）；
- 文案用英文节名（与现有 `### Code` / `### Docs` / `### Missing Evidence` 一致）；
- 每条形如 `- <query>`，**不要**加编号（编号会与 `[E*]` 证据编号混淆）；
- **不改变既有四节的任何内容与顺序**（有回归测试守着）。

> 为什么要做：`next_queries` 是 D-24 设计的"有用的失败"核心——Agent 拿到它就知道
> 该用什么措辞再问一次，而不是自己瞎猜。设计依据见 `docs/design/Module/04-AI总结.md` §3。

## §B `answerable=false` 短路（service 侧）

设计文档 §3（D-24）要求：`answerable=false` 时**不调 LLM**，直接返回结构化降级包：

```
{
  status: "insufficient_evidence",
  bestEffortContext: <ContextPack 的 Markdown 渲染>,
  missingEvidence: [...],
  nextQueries: [...]
}
```

本卡**只做这一条分支**（LLM 接入是 TASK-088）：

- `manager.search()` 拿到 `trace.pack` 后，**先看 `pack.answerable`**；
- `answerable == False` → 返回 `status="insufficient_evidence"`，含：
  - `bestEffortContext`：`render_markdown(pack)`（有什么给什么）；
  - `missingEvidence`：来自 `pack.missing_evidence` 的**可读文本列表**；
  - `nextQueries`：来自 `pack.next_queries`；
  - `meta`：照旧（`pack_meta`）。
- `answerable == True` → **本卡保持现状**（`status="degraded"` + 现有文案），
  因为 LLM 还没接；TASK-088 会替换这条路径。

**审计要求**（`_audited` 上下文）：短路路径也要落一条审计，
`degraded=true`、`answerable=false` 如实记录（TASK-084 已有此机制，接上即可）。

**契约注意**：CF-06 冻结的是 **MCP 工具 schema**（输入参数），不是 `ask` 的响应体形状。
但 `meta` 字段集是给 client 的输入契约（TASK-032）——**不要改 `pack_meta` 的字段名或删字段**，
本卡只是**新增** `status` 取值与几个响应字段。

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/contextpack -q` 全绿，**必须覆盖**：
  - [ ] `next_queries` 非空 → 渲染出 `### Suggested Next Queries` 且每行是 `- <query>`；
  - [ ] `next_queries` 为空 → **不出现该节**（断言 `"Suggested Next Queries" not in md`）；
  - [ ] 既有四节的标题与顺序**逐字未变**（回归保护，可用快照式断言）。
- [ ] `uv run pytest service/tests/test_query_api.py -q` 全绿，**必须覆盖**：
  - [ ] `answerable=false` 的 pack → `status="insufficient_evidence"`，含
        `bestEffortContext` / `missingEvidence` / `nextQueries` 三个键，且 `bestEffortContext` 非空；
  - [ ] `answerable=true` 的 pack → 行为与今天一致（`status="degraded"`，不回归）；
  - [ ] 短路路径**也落审计**（查库断言有一条 `mode=deep` 的记录）。
- [ ] 行为验收（贴真实输出）：对 `HelloAgents`（或任意已索引仓库）发一个**证据不足**的问题
      （如「这个仓库的量子计算模块在哪」），确认返回 `insufficient_evidence` 且 `nextQueries` 有值。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、
      `uv run pytest -o addopts="" -q`
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- **不接 LLM**（TASK-088 的领地）；
- **不改** `pack_meta` 的既有人工字段（CF-05 契约）；
- **不改** `assembly.py` 的装填/打分/阈值（R29/R30 冻结）；
- **不改** `search_context` 的渲染（只在 `render_markdown` 里加一节，两个工具共用它）；
- 不做 Citation 回验（TASK-088）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：渲染前后的 Markdown 对照片段
（证明新增节且旧节未变）。

## 执行记录

### 2026-09-14 ｜ 泳道 A ｜ 分支 `feature/task-087-pack-render_xwz0914`

**状态：review**（验收命令全部跑通；行为验收用真实 Voyage embedding + 真实仓库测得）

#### 1. 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run pytest core/tests/contextpack -q` | **62 passed**（新增 4 个断言用例，见下） |
| `uv run pytest service/tests/test_query_api.py -q` | **26 passed**（新增 3 个用例） |
| `uv run ruff check .` | **All checks passed!** |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过（core 纯库 / service 不上探） |
| `uv run pytest -o addopts="" -q` | **810 passed, 2 skipped**（基线 804 + 本卡新增 6） |

> 环境注记：lane-a 工作区的 `.venv` 缺 dev 组，已用 `uv sync --frozen --all-packages --all-extras`
> 补齐 `pytest`/`ruff`（`--frozen` 不改 `uv.lock`，无依赖变更）。另：跑基线时必须 `env -u EMBED_MODE`，
> 否则 `.env` 的 `EMBED_MODE=api` 会让 `test_default_is_local_onnx_provider` 因环境而红（与本卡无关）。

新增断言（§A / §B 逐条对应 DoD）：

- `test_next_queries_section_lists_each_query_without_numbering`：非空 → 出节，每行 `- <query>` 且**无编号**；
- `test_next_queries_empty_omits_the_section`：空 → `"Suggested Next Queries" not in md`；
- `test_existing_sections_are_byte_identical_to_the_snapshot`：**快照式回归**，Meta 之前的旧节逐字未变；
- `test_render_evidence_for_prompt_has_no_meta_or_flow`：追加一条断言，**prompt 分节不含新节**；
- `test_ask_insufficient_evidence_returns_structured_package`：`status="insufficient_evidence"` +
  `bestEffortContext` / `missingEvidence` / `nextQueries` 三键齐全且 `bestEffortContext` 非空（用一个**可复现**的
  缺失来源构造 `missingEvidence` 非空：删掉被文档引用的代码 → `stale_doc_reference`）；
- `test_ask_when_answerable_keeps_the_degraded_package`：`answerable=true` → 仍 `status="degraded"`（不回归）；
- `test_ask_short_circuit_is_audited_as_deep_mode`：短路路径查库得一条 `mode=deep` / `degraded=1` / `answerable=0`。

#### 2. 渲染前后对照（Markdown 片段）

**旧节逐字未变**：下面对照取自 `core/tests/contextpack/snapshots/rich_pack.md` 的快照 diff——
除新增 4 行外**零改动**（`git diff` 只显示这 4 行 `+`，无 `-`）：

```diff
  - [stale_doc_reference] (LegacyToken.rotate) 文档 docs/design/auth.md 引用了已删除或改名的符号（LegacyToken.rotate），该文档可能已过时；需要以代码为准并更新文档。
+ ### Suggested Next Queries
+ - refresh 的调用方有哪些
+ - src/auth/token_service.py 里还有哪些与查询相关的符号
+ - 认证 > Token Refresh 对应的实现代码在哪里
  ### Meta
  confidence: high | index: stale (1 files) | budget: 574/10.0K
```

渲染后完整节顺序（`## Relevant Context` → Code / Flow / Docs / Missing Evidence /
Suggested Next Queries / Meta）由 `test_render_section_order_and_details` 用 `text.index()` 顺序断言守住。

**真实仓库的渲染效果**（同上 index 的 `HelloAgents`，查询「这个仓库的量子计算模块在哪」——该问题在本仓库
`answerable=true`，故用 `zzzz qqqq…` 作真·证据不足样本，两者只差 `answerable` 分支）：

```markdown
### Missing Evidence
- [unresolved_reference] 70 个符号引用无法解析（unresolved_refs status=failed），涉及这些符号的调用关系可能缺失。
- [retrieval_truncated] 候选池被预算裁剪：省略 63 个候选（其中 51 个因 spec 份额上限让位给代码证据），可能有相关但未展示的证据；可提高预算或收窄查询。
### Suggested Next Queries
- skills/podcast-generate/readme.md 里还有哪些与查询相关的符号
- Podcast Generate Skill（TypeScript 线上版本） 对应的实现代码在哪里
### Meta
confidence: low | index: fresh (1 min ago) | budget: 8.4K/10.0K
```

#### 3. 行为验收（真实 Voyage embedding + 真实仓库，非假 provider）

- 靶场：`/home/xuwenzheng/2_github/Agent开发/hello-agents/HelloAgents`（**只读，未在其中建任何文件**）；
- 索引：`zace-core ingest --repo … --data /tmp/zace-087-data` → 237 文件 / 2730 chunks / 2730 vectors（57.2s，`EMBED_MODE=api` / `voyage-4-lite`）；
- `POST /api/query/ask`（TestClient 驱动真实服务，`question="zzzz qqqq 与语料完全无关的主题"`）：

```text
HTTP 200 | status = insufficient_evidence
keys: ['status', 'bestEffortContext', 'missingEvidence', 'nextQueries', 'meta']
meta.answerable = False | degraded = True
meta.degradedReason = 证据不足（answerable=false）：按 D-24 不调用 LLM，返回尽力而为的上下文与补齐建议。

--- missingEvidence ---
["[unresolved_reference] 70 个符号引用无法解析（unresolved_refs status=failed），涉及这些符号的调用关系可能缺失。",
 "[retrieval_truncated] 候选池被预算裁剪：省略 63 个候选（其中 51 个因 spec 份额上限让位给代码证据），可能有相关但未展示的证据；可提高预算或收窄查询。"]

--- nextQueries ---
["skills/podcast-generate/readme.md 里还有哪些与查询相关的符号",
 "Podcast Generate Skill（TypeScript 线上版本） 对应的实现代码在哪里"]

--- bestEffortContext（末 5 行） ---
### Suggested Next Queries
- skills/podcast-generate/readme.md 里还有哪些与查询相关的符号
- Podcast Generate Skill（TypeScript 线上版本） 对应的实现代码在哪里
### Meta
confidence: low | index: fresh (1 min ago) | budget: 8.4K/10.0K
```

对照（同一仓库、同一服务，`question="流式输出在哪个文件实现"`）：

```text
HTTP 200 | status = degraded | answerable = True
keys: ['status', 'answer', 'evidenceSummary', 'meta']
Deep 模式（LLM 总结）尚未接入（Phase 3）；以下为检索与组装结果，可直接作为上下文使用。

## Relevant Context
### Code
[E3] StreamBuffer — hello_agents/core/streaming.py:74-82
```

审计落库（同一次真实运行，查 `zace-meta.db`）：

```text
{'mode': 'deep', 'degraded': 1, 'answerable': 0, 'confidence': 'low',    'query': 'zzzz qqqq 与语料完全无关的主题', 'latency_ms': 2073}
{'mode': 'deep', 'degraded': 1, 'answerable': 1, 'confidence': 'medium', 'query': '流式输出在哪个文件实现',       'latency_ms': 525}
```

即：**短路路径确实落了一条 deep / degraded / answerable=false 的记录**（DoD 最后一条）。

#### 4. 交付物

- `core/zace_core/contextpack/render.py`：新增 `_next_queries_section`，插在
  `_missing_section` 与 `_meta_section` 之间（`render_markdown` 调用链）；**未动** `render_evidence_for_prompt`；
- `core/tests/contextpack/test_render.py` + `snapshots/rich_pack.md`：新增断言与快照新节；
- `service/zace_service/routers/query.py`：`ask` 增 `answerable` 分支 + `INSUFFICIENT_NOTICE` + `_insufficient_package`；
- `service/tests/test_query_api.py`：3 个新用例。

#### 5. 与设计的偏差

1. **短路包不含 `evidenceSummary`**。Module/04 §3 列的三个键（`status` / `bestEffortContext` /
   `missingEvidence` / `nextQueries`）全部照做；`evidenceSummary` 是 Phase 2 降级包（D-26）的既有扩展字段，
   本卡的 DoD 未要求它。判断依据：「证据不足」时给 Agent 一份"证据概览"是自相矛盾的信号，
   而 `bestEffortContext` 里已含全部证据。TASK-088 若需要，可零成本加上。
2. **`meta.degradedReason` 在短路路径取 `INSUFFICIENT_NOTICE`**（而非沿用 `DEGRADED_NOTICE`）。
   两者语义不同（"有 LLM 也答不了" vs "没有 LLM"），用户看 meta 时更需要前者。字段名与字段集未变（只改值）。
3. **`meta.mode` 仍为 `pack.mode`（实际组装模式，Fast）**，未改成 `"deep"`——这是 `packmeta.py` 的既有口径
   （TASK-032 注释已写明：如实描述实际发生了什么），字段集冻结，本卡不动。

以上均属"新增取值/新增键"，不改 `pack_meta` 字段名、不删字段（CF-05 / TASK-040 契约不受影响）。

#### 6. 未决问题

1. **CF-05 的 `AskResponse` schema 未同步**（`docs/contracts/openapi.yaml`：`status` enum 已含
   `insufficient_evidence`，但 `bestEffortContext` / `missingEvidence` / `nextQueries` 三个响应字段未登记）。
   契约文件不在本卡文件所有权清单内，**未改**。请编排者同步 openapi.yaml（或在 TASK-088 一并做）。
   注：现有测试只校验**路径与方法集合**（`test_skeleton.py`），故本卡未破坏任何测试。
2. **阈值观察（非缺陷，属校准范畴）**：「这个仓库的量子计算模块在哪」在真实仓库下 `answerable=true`
   （confidence=medium），即"问题与仓库无关"未必判为证据不足——这是 R22/`_assess` 的口径
   （向量通道总有候选 + ≥2 通道共识即算可回答）。R22 已登记该诚实性缺口，归 TASK-050 校准，本卡不越界。
3. 客户端（TASK-040）与 WebUI 尚未消费新形状：`status` 多了一个取值、响应多了三个键。
   属"只增不改"，向后兼容；是否要在 TASK-040 里加展示，由编排者定。
