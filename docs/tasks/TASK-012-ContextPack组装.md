# TASK-012：ContextPack 组装 + Markdown 渲染

> 状态：done ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-010、TASK-011 ｜ soft 依赖：无
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

### 2026-09-10 / feature/task-012_xwz0910（泳道 E，本地分支交付，基于 feature/task-011_xwz0910）

**完成报告**

- 分支：`feature/task-012_xwz0910`
- 验收：
  - `uv run pytest core/tests/contextpack -q` → 38 passed（预算/配额/去重三招/判定矩阵 7 组合/
    missingEvidence/nextQueries/schema 校验/渲染快照/性能）；
  - 性能：200 候选组装 < 50ms（单测计时断言，实测远低于阈值）；
  - 基线三条：`uv run ruff check .` → All checks passed；
    `uv run python scripts/check_dependency_direction.py` → 通过；`uv run pytest` → 366 passed, 2 skipped。
- 关键产物：`core/zace_core/contextpack/{__init__,assembly,render}.py`、
  `core/tests/contextpack/{conftest,test_assembly,test_render,test_schema}.py`、
  `core/tests/contextpack/snapshots/rich_pack.md`；
  `core/pyproject.toml` dev extra 按卡内授权新增 `jsonschema>=4.21`（同时更新 `uv.lock`）。
- 契约影响：无（CF-03 字段与 `docs/contracts/contextpack.schema.json` 逐项对齐并由 jsonschema
  正向校验；未动 `types.py` / `interfaces.py` / `docs/contracts/**`）。
- 与设计偏差：无实质偏差；预算/token 估算与缺失证据口径见下。
- 建议复核点：① `score = rrf_score × RRF_BASE_SCALE + Σ特征` 由 TASK-011 引入，本卡直接消费
  ``candidate.score``（不重算），确认排序责任归属；② tier3 配额按 §4.1 字面实现（下文）；
  ③ 渲染快照改用文件比对（避开 ruff E501/W291 对长中文行的误报）。

**Confidence / answerable 最终口径（照抄 Module/03 §4.4，判定基于**输入候选池**而非裁剪后证据）**

```
explicit_hits  = 池中 channel_ranks 含 'exact' 或 reasons 含 'explicit path' 的候选数
consensus      = 池中 channel_ranks 维度 ≥2 的候选数
answerable     = explicit_hits ≥ 1 OR consensus ≥ 2 OR structural_result（Phase 3 路由接口，默认 False）
confidence     = high   ：explicit_hits ≥ 1 且 consensus ≥ 3 且无 graph_boundary
                 medium ：(consensus > 0 且 explicit_hits == 0) 或 spec-only 命中（docs 非空且 evidence 空）
                 low    ：其余
```

`graph_boundary` 与 `structural_result` 作为命名参数留接口（Phase 3 数据源），默认 False；
Phase 1 不产生 graph_boundary 的 missingEvidence。

**missingEvidence 最终口径（Phase 1 可实现子集，按固定顺序输出）**

| code | 触发条件 | 数据源 |
|---|---|---|
| `index_stale` | `freshness.stale_files` 非空 | 01/05 同步层 |
| `indexing_pending` | `freshness.indexing_files` 非空 | 05 同步层 |
| `unresolved_reference` | `unresolved_refs(status=failed)` 计数 > 0 | Store |
| `stale_doc_reference` | 已装填 doc 的 `spec_refs_for_spec().stale` | Store（G4） |
| `retrieval_truncated` | 因容量（预算/单文件/ tier3 配额）裁剪 ≥1 候选 | 本组件 |
| `no_context_match` | 装填后 evidence+docs 均为空 | 本组件 |

`graph_boundary` / `symbol_ambiguous` 本卡不产生（留接口，Phase 3 数据源）；每条 message 均含
"缺什么 + 为什么缺"，自愈建议一律走 `nextQueries`。

**其他实现口径**

1. **spec 保底**：为最高分 spec 候选**预留预算**（`hard_limit = hardCap − reserve`），贪心后再补入——
   保住 Module/03 §4.1 的保底意图，同时让 "E 编号 = 装填顺序 = score 降序" 成立（不因保底插队）。
2. **tier3 配额**按 §4.1 字面：`tier3_used + est > 0.30 × used` 则跳过。池中若**只有** tier3 候选，
   `used=0` → 配额为 0 → 装填为空（用 `no_context_match` 如实报告）；生产路径不会出现
   （扩展候选总与其 seed 同时入池）。已记入未决问题。
3. **skeleton 降级**触发条件 = “>300 行”且（超单文件上限 或 超硬预算）；
   保留签名 + **切片起始行**（符号定义行，RRF 无 chunk 内命中行信息）起 15 行，其余计入 `elidedLines`。
4. **去重三招**：相邻区间合并仅在同文件、同为 spec/非 spec 且行距 ≤10 时发生（合并后重算 token 账）
   其余计入 `elidedLines` 并追加 reason；同符号聚合保留最高分并写 `同符号聚合×N`；
   三者均不计入 `retrieval_truncated`（只有容量裁剪才置 `truncated=true`）。
5. **内容与编号**：`EvidenceItem.content` = 带行号原文（`45 | def refresh(...)`，CF-03 定义）；
   evidence 与 docs 共用 E 编号（按装填顺序），flows 沿用 011 产出的 F 编号。
6. **渲染**：快照存为 `snapshots/rich_pack.md`（Python 内长中文行会撞 ruff E501/W291）；
   `render_evidence_for_prompt` 只输出 Code/Docs 两节（Phase 3 的 04 prompt 直接复用）。

**未决问题**

1. **tier3 配额的退化边界**（口径 2）：池内只有 tier3 候选时空包。生产不会发生，但若 TASK-013
   的装配路径可能单跑图扩展，建议编排者裁定是否给"首块豁免"。
2. **`files.generated` 仍无数据源**（同 TASK-010/011）：本卡不消费 generated 信号（rerank 已处理），
   但 Phase 2 的 `sync_status`/元数据若要展示 generated 统计，仍需 Store 读 API。
3. **flows 的 token 只计不争**：`budget.usedTokens` 含 flows 估算量，但 flows 不参与装填竞争，
   也不会被预算裁剪（Module/03 §4.1 "flows 直接收纳"）；若 Phase 2 需要在预算紧张时裁剪 flows，
   需回到 Module/03 重新裁定。

