# TASK-087：ContextPack 渲染补齐（next_queries + answerable 短路）

> 状态：pending ｜ 阶段：Phase 3（M2c）｜ 硬依赖：无 ｜ soft 依赖：TASK-088（LLM 接入，可并行）
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

（实施 AI 在此填写。）
