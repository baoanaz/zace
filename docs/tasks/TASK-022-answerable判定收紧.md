# TASK-022：answerable / confidence 判定收紧（负例诚实性）

> 状态：review ｜ 阶段：Phase 1+（质量修复）｜ 硬依赖：TASK-021（同文件，必须**串行**）｜ soft 依赖：无
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

### 2026-09-10 ｜ 分支 `feature/task-022_xwz0910`（jump 自 `feature/task-021_xwz0910`）｜ 状态：review

**改动文件**（所有权范围内）

- `core/zace_core/contextpack/assembly.py`：仅 `_assess` 及其辅助——新增常量
  `MIN_CONSENSUS_FILES=2` / `CONSENSUS_SCORE_RATIO=2.15` 与辅助函数
  `_is_inferred()` / `_consensus_files()` / `_consensus_peak()`；
- `core/tests/contextpack/test_answerable.py`（新增 6 用例）；
- `core/tests/contextpack/test_assembly.py`（口径变更必需的 3 条旧断言）；
- `benches/results/raw-fix022-{zace,aibox,cameraservice}-e2e.md`、`benches/results/phase1-baseline.md` §9；
- `docs/tasks/README.md` 任务板状态行。

**验收命令与结果**

| 命令 | 结果 |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run python scripts/check_dependency_direction.py` | 通过 |
| `uv run pytest` | **501 passed, 2 skipped**（490 既有 + 5（TASK-021）+ 6 新增；M1 集成与 CLI E2E 用例保持绿） |
| `zace-core eval`（zace / `/tmp/zace-verify-main`） | r@5 0.682 / r@10 0.864 / MRR 0.561；负例 0/2 |
| `zace-core eval`（aibox-super-sdk / `/tmp/zace-aibox`） | 0.556 / 0.667 / 0.466；负例 **1/2** |
| `zace-core eval`（linux-mtk-mw-cameraservice / `/tmp/zace-cam`） | 0.500 / 0.500 / 0.314；负例 1/2 |

**最终口径**（写入代码注释与基线报告 §9.1）

```text
answerable = explicit>=1 | inferred>=1 | structural_result | corroborated
corroborated = 共识候选跨 >=2 个文件 且（top-1 被 >=2 通道命中 或 共识峰值 >= 2.15×池中位数）
answerable=False → confidence 一律 low
```

**候选规则对比表**（同一 golden / 同一索引；`answerable` 不参与装填 → 召回不变）

| # | 规则 | 负例通过 /6 | 非 dogfood /4 | 正例 answerable /54 | 结论 |
|---|---|---|---|---|---|
| — | 基线 `explicit \| consensus>=2 \| structural` | 1 | 1 | 52 | 现状 |
| C1 | `explicit` only | 6 | 4 | **1**（不达标） | 53/54 正例无 explicit 命中 |
| C1′ | C1 + `inferred` | 6 | 4 | **13**（不达标） | 仍远低于正例下限 52 |
| C2 | `consensus>=2` 且 `peak >= 2.15×median` | 2 | 2 | 52 | 零正例损失 |
| C2′ | C2 + 共识跨 ≥2 文件 | 2 | 2 | 52 | 与 C2 结果相同 |
| C3 | 查询 token 在 top-10 证据中覆盖率 ≥0.9 | 4 | 4 | **20**（不达标） | 负例达标但误杀 32 条正例 |
| C4 | C1 + C3 | 4 | 4 | **21**（不达标） | 同上 |
| **选定** | `explicit \| inferred \| structural \| (top1 双通道 & 跨文件) \| C2′` | **2** | **2** | **52** | 正例达标、**负例未达标** |

召回（三仓库合并 ② e2e）：**0.593 / 0.704 / 0.465**，与 TASK-021 修复后逐项相同（收紧不伤召回）。

**DoD 结果**

- **负例：1/6 → 2/6（非 dogfood 1/4 → 2/4）。未达成目标（≥5 / 4）。**
  归因：① 53/54 正例无 explicit 命中，`consensus>=2` 事实上承担了几乎所有正例的可回答性，
  抬高门槛必然误杀正例（阈值 2.6 起开始丢正例）；② 剩余两条负例（`aibox-0020`、
  `cameraservice-0005`）在**所有确定性且不违反 R20/R24 禁项**的特征上落在可回答正例分布中段
  （共识文件数/峰值倍数/覆盖率/池规模/tier/top-10 代码占比均已逐条比对）；③ 真实根因在检索侧与
  索引侧——它们的 top 证据是 `README.md` 模板、`docs/API.md`、`CLAUDE.md` 等**样板文**，字面确实
  含查询词，属本卡"明确不做"范围。建议先推 D-28 忽略规则 + R24 排序判别力，再重评本口径。
- **正例：52/54（目标 ≥52），达标。** 见基线报告 §9.3/§9.4。
- **单测**：负例形态（文档密集 + 高频词，无突出共识 / 单文件伪共识）→ `answerable=false`、
  `confidence=low`；正例形态（Explicit / Inferred / 跨文件强共识 / 双通道印证的最高分）→
  `answerable=true`。
- **既有用例改动（口径变更必需，已逐条标注理由）**：`test_answerable_confidence_matrix` 两行期望值
  更新（`(0,1,1,0)`：不可回答且降为 low；`(0,2,0,0)`：仍 answerable，理由改为"跨文件双通道共识 +
  最强候选被双通道印证"）；`test_spec_only_hit_is_medium_confidence` 更名并断言 `low`。
  **非所有权文件（`core/tests/integration/`、`core/tests/cli/`）零改动且保持绿。**

**契约影响**：无。CF-03 字段名/结构/取值空间未变，仅判定口径收紧。

**与设计偏差**：与 `Module/03 §4.4` 条文文字不一致（条文写 `consensus >= 2`）。本卡按 C1–C4
逐条实测后收紧，**未改设计文档**，建议编排者按 L3 流程裁决（更新条文或回退本口径）。

**未决问题**

1. **负例 DoD 未达成**（非 dogfood 2/4）：建议按上述顺序（D-28 → R24）推进后重评；
   若要求本卡范围内继续收紧，需先裁定"正例口径 52"是否可交易（数据表已给出代价：
   C3 规则 4/4 负例但 20/54 正例）。
2. `CONSENSUS_SCORE_RATIO=2.15` 判别区间窄（`aibox-0008` 1.97 vs 最低正例 2.34），属 TASK-015 校准项；
   换 embedding/rerank 后需重标。
3. `inferred` 作为硬依据为新增口径：在 golden 上不改变任何判定（仅作 CLI/M1 集成口径护栏），
   但会随 Exact-Inferred 通道质量波动，建议 TASK-015 连带评估。
4. 合成单测中 `answerable=false` 的包 `missingEvidence` 可能为空（无 freshness/stale/unresolved 信号），
   而 runner 负例判定要求非空；实盘恒非空（`unresolved_reference` + `retrieval_truncated`），
   故不作为缺陷。若要为"无依据"补诚实缺口项，需新增 CF-03 code（契约变更，未做）。
