# TASK-022：answerable / confidence 判定收紧（负例诚实性）

> 状态：pending ｜ 阶段：Phase 1+（质量修复）｜ 硬依赖：TASK-021（同文件，必须**串行**）｜ soft 依赖：无
> 建议分支：`feature/task-022_<你的缩写><MMDD>`（从 TASK-021 合并后的 main）
> 交付物所有权：`core/zace_core/contextpack/assembly.py`（仅 `_assess` 及其辅助）、`core/tests/contextpack/`、`benches/results/`
> 不改 `retrieval/`、不改 CF-03 契约。

## 背景（基线实测暴露的产品级问题，2026-09-10）

`answerable` 是**产品诚实性的开关**：D-24 规定 `answerable=false` 时 Deep 模式**不调 LLM**，
直接返回"证据不足 + 改问建议"。但 TASK-014 实测：

```text
负例通过率 2/6（4 条失败，均为 answerable=True）
  aibox-0008  "Kubernetes operator 的部署协调逻辑在哪里实现？"     → answerable=True
  aibox-0020  "RabbitMQ 的消息确认（ack）机制在哪里实现？"          → answerable=True
  （另 2 条为 zace/cameraservice 的 dogfood 负例，见 R17）
```

### 机制（已核实）

`assembly.py::_assess` 现行规则（照 Module/03 §4.4 实现）：

```python
answerable = explicit_hits >= 1 or consensus >= 2 or structural_result
# consensus = 拥有 ≥2 个通道命中的候选数
```

在文档密集仓库里，查询里的常用词（`实现`/`逻辑`/`协调`/`部署`…）会命中大量文档，
而文档天然同时命中 BM25 与 Vector → **`consensus >= 2` 几乎恒为真** → `answerable` 恒为 True。

**后果**：ask_project 永不短路 → 对仓库根本无法回答的问题也会调用 LLM 强行作答，
违背 Task.md §16「证据不足时输出 Missing Evidence」与 D-24 的诚实失败设计。

## 修复要求

**本卡是数据驱动的口径收紧，不是加规则**。要求：

### A. 候选规则必须逐条实测对比

至少评估以下候选（可自行增补，但每条都要有数据）：

| # | 候选规则 | 说明 |
|---|---|---|
| C1 | `answerable` 仅当 **Explicit 命中** 或 **structural_result** | 删除 `consensus>=2` 一条（最保守） |
| C2 | `consensus>=2` 保留，但要求共识候选的**最高 rerank 分 ≥ 池中位数 × K** | 需定 K（数据选） |
| C3 | 要求**意图覆盖**：top-N 证据中必须含有查询"内容词"的一定比例 | 内容词判定需确定性（不可引 IDF，R20 已否决） |
| C4 | C1 与 C3 组合 | — |

### B. 判定口径（DoD 的量化目标）

- **负例（6 条）**：`answerable=false` 且 `missingEvidence` 非空 的条数 **≥5**（当前 2/6）；
  —— 注意其中 2 条是 R17 提到的 dogfood 负例（zace 自身），它们在当前索引范围下**结构上不可能通过**
  （golden 文件自身被索引命中）；这 2 条**不计入**本条，需在报告里单独说明。
- **正例（54 条）**：`answerable=True` 的条数 **不得低于基线**（当前正例几乎全 True；
  收紧后若正例 answerable 掉得过多，说明规则过严，需回退或改用 C4）。
- 两条约束必须**同时满足**；只满足一条视为未达成。

### C. confidence 判定同步复核

现行：`high` 需 explicit≥1 且 consensus≥3；`medium` 为 (consensus>0 且 explicit==0) 或 spec_only。
若 §A 调整了 `consensus` 的定义或门槛，confidence 需同步保持单调合理
（`answerable=false` 时 confidence 应为 `low`）——写清最终口径。

## 验收标准（DoD）

- [ ] **规则对比表**（执行记录必须含）：每候选规则在 6 负例 / 54 正例上的 `answerable` 统计，
      以及整体 recall@5/@10/MRR（确认收紧不伤害召回）。
- [ ] 选定规则的**单测**：负例场景（构造"高频词命中多文档但无实质内容"的查询）→ `answerable=false`；
      正例场景（Explicit 命中 / 双通道真共识）→ `answerable=true`；`answerable=false` 时 `confidence=low`。
- [ ] **基线复跑**：用同一 golden 与索引重跑 eval，负例通过率与正例 answerable 率如实报告；
      `benches/results/phase1-baseline.md` 追加"修复后复测"章节。
- [ ] 全仓 `uv run pytest` 全绿；`uv run ruff check .`、`check_dependency_direction.py` 通过。
- [ ] 执行记录回填 + 任务板状态改 review。

## 明确不做

- **不做停用词表 / 词性过滤 / IDF**（R20/R24 已否决；C3 的"内容词"须用确定性、可解释的判据）；
- 不改检索、排序、装填配额（TASK-021 范围）；
- 不改 Module/03 §4.4 的设计条文本身——若你认为必须改，按 L3 流程提交编排者（写进"未决问题"）；
- 不追求 6/6 负例通过（dogfood 负例受 R17 影响，属索引范围问题）。

## 参考

- `docs/design/Module/03-上下文组装.md` §4.4（answerable/confidence 规则）、§5（MissingEvidence 合同）
- `docs/design/Module/04-AI总结.md` §3（answerable=false 短路）
- `docs/plan/contracts.md` §3.5 R22（负例弱点裁定）、R17（dogfood 负例口径）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；**执行记录必须含候选规则对比表**。

## 执行记录

（实施 AI 在此填写。）
