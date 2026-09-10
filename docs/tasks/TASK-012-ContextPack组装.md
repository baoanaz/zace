# TASK-012：ContextPack 组装 + Markdown 渲染

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-010、TASK-011 ｜ soft 依赖：无
> 建议分支：`feature/task-012_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/contextpack/`、`core/tests/contextpack/`
> 允许并在卡内预期：在 `core/pyproject.toml` 的 `dev` extra 增加 `jsonschema`（schema 校验测试用），其余依赖不动。

## 目标

把候选证据组装成预算内、结构化、可引用的 ContextPack（CF-03），并交付对外 Markdown 渲染
（与 04 的 prompt 渲染共用 formatter，D-21 双层合同）。这是 search_context 的产品形态本身。

## 输入文档（按序读）

1. `docs/design/Module/03-上下文组装.md` 全篇（§2 合同 / §3 去重三招 / §4 装填与预算 / §5 MissingEvidence / §6 渲染 / §7 性能）
2. `docs/contracts/contextpack.schema.json`（字段冻结）
3. `docs/design/Module/02-检索策略.md` §4.6（tier 作为装填资格线）、§4.7（G4/G5 的信号来源，Phase 1 只接 G4/stale 与预算信号）

## 交付内容

### A. 组装（`assembly.py`）

```text
输入：candidates（已 rerank）+ flows + freshness + 索引信号
预算：hardCap = Fast 默认 10K（可配 8-12K；Deep 12K 在 Phase 3 接入，本卡实现 config）
框架开销 ≈500 token（query/freshness/missing 元数据）
装填：分数降序贪心；单文件 ≤25%；tier3 配额 ≤30% 已用预算；spec 保底 1-2 块（存在相关 spec 时）
去重三招（Module/03 §3）：相邻区间合并（同文件行距 ≤10）；同符号聚合（留最高分，其余 omittedCount++）；
  skeleton 降级（单 chunk >300 行且超预算 → 签名 + 命中行 ±15 + elidedLines 计数）
tier 不作为排序键（D-17）：只做配额与资格线
```

- **answerable / confidence**（确定性规则，Module/03 §4.4）：answerable = Explicit 命中 ≥1 或双通道共识 ≥2 或（Phase 3 的结构路由非空，本卡留接口）；confidence 三档规则照抄实现。
- **missingEvidence**：Phase 1 落地可实现子集：`index_stale` / `indexing_pending`（来自 freshness）、`unresolved_reference`（Store 提供）、`stale_doc_reference`（G4）、`retrieval_truncated`（预算裁剪）、`no_context_match`；`graph_boundary` / `symbol_ambiguous` 留接口（Phase 3 数据源）。
- **nextQueries**：确定性生成 2-3 条（从 top 候选符号/路径构造），禁止 LLM。
- **E/F 编号**：evidence 与 docs 共用 E 空间（占用顺序 = 装填顺序），flows 用 F。

### B. 渲染（`render.py`，Module/03 §6 格式）

- `render_markdown(pack) -> str`：节顺序 `## Relevant Context` → Code / Flow / Docs / Missing Evidence / Meta；
  代码带**行号**（agent 可直接对齐 Edit）；引用格式 `[E1]`/`[F1]`；stale 文档带 `⚠` 行；budget/confidence/index 状态入 Meta。
- **同一 formatter 输出 04 的 prompt evidence 分节子函数**（`render_evidence_for_prompt(pack)`），Phase 3 直接复用。
- `to_json(pack) -> dict`（字段名与 CF-03 完全一致，camelCase）。

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/contextpack -q` 全绿，必须覆盖：
  - 预算：构造超预算候选 → `truncated=true` 且 `omittedCount` 正确；框架开销计入；
  - 单文件 25% 上限：单文件候选群被限流，其他文件候选补位；
  - tier3 30% 配额生效；spec 保底 ≥1（有 spec 候选时）；
  - 去重三招各 1 例（区间合并 / 同符号聚合 / skeleton 降级 + elidedLines>0）；
  - answerable/confidence 判定矩阵（≥6 组合）；
  - **schema 校验**：`jsonschema` 对 `to_json()` 输出校验通过（用 `docs/contracts/contextpack.schema.json` 文件本体）；
  - 渲染快照：一个完整 pack 的 Markdown 输出与固定快照一致（行号、⚠、Meta 齐全）。
- [ ] 性能：组装函数在 200 候选规模下 <50ms（单测计时，非严格基准）。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/ragcode/src/context/` + `src/brief/`（ContextPack 合同最完整参考：budget trace / missing evidence / edit-readiness）
- `source/codegraph/src/context/`（源码分组输出 + "不要重新 Read" 的文案纪律；见 Background/02 §5）

## 明确不做

- 不做检索/排序（010/011）；不做 LLM 调用（Phase 3）；
- 不做 GRAPH RELATION 独立数组（V1 只进 reason 文本）；
- 不做 token 精确 tokenizer（chars/4 近似，Module/03 §2 合同要点 3）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写。Confidence/answerable 与 missingEvidence 的最终实现口径必须记录。）
