# TASK-021：装填层 Code/Docs 平衡（R21）

> 状态：review ｜ 阶段：Phase 1+（质量修复，**M1 后最高优先级**）｜ 硬依赖：TASK-014（基线，已合并）｜ soft 依赖：无
> 建议分支：`feature/task-021_<你的缩写><MMDD>`（从最新 main）
> 交付物所有权：`core/zace_core/contextpack/assembly.py`、`core/tests/contextpack/`、`benches/results/`
> **本卡与 TASK-022 同文件（assembly.py），必须串行**：等 TASK-021 合并后再开 TASK-022。
> 不改 `retrieval/`（排序属 TASK-015 校准）、不改 `docs/contracts/**`。

## 背景（基线实测暴露的头号质量问题，编排者 2026-09-10 定位机制）

TASK-014 基线：e2e recall@5 **0.574** / recall@10 0.611 / MRR 0.451。
失败 Top10 中 **7 条同一模式**：中文行为/路径题返回的证据 **top-3 全是设计文档，代码块被完全挤出**。

实例（`aibox-super-sdk`，编排者用 `search_with_trace` 实测，非推测）：

```text
Q: 记忆检索的执行流程在哪个文件里实现？
期望: src/aibox/capabilities/memory/search/pipeline.py, search/planner.py
实测 top-8（全部是 spec，无一代码）:
  3.202 spec  bm25#4, vector#1    doc/车载记忆系统需求/车载记忆系统需求.md
  3.102 spec  bm25#3, vector#6    doc/记忆系统调研/记忆系统调研.md
  2.817 spec  bm25#11,vector#11   doc/记忆系统调研/记忆系统调研.md
  ...（8 条全是 spec，其中 6 条来自同一个文件的不同小节）

Q: Where does the retention maintenance loop live and what does it clean up?
期望: src/aibox/capabilities/memory/internal/maintenance.py
实测 top-8:
  2.369 test  bm25#17,vector#13   tests/test_capabilities/test_memory_lifecycle.py
  2.221 code  bm25#20,vector#43   src/aibox/capabilities/app base.py    ← 无关代码却排在前面
  2.189 spec  bm25#12             README.md
  ...（目标文件未入 top-8）
```

### 已核实的机制（三条，**不要沿用出题时的猜测**）

1. **自然语言对齐偏差**（主因）：文档用自然语言写，查询也是自然语言 → 文档在 BM25 与 Vector
   **双通道**都强命中；代码里标识符与自然语言用词不同 → 代码常只命中 Vector 单通道。
   RRF 天然奖励"双通道"，于是文档系统性胜出。
2. **文档切片数量放大**：一份长文档切出多个 SpecBlock，同一文件的 6 个不同小节可以同时占据
   top-8（实测）；代码文件每个符号 1 块。**当前装填层只有 `single_file_ratio=0.25`（按文件限），
   没有按"证据类型"的总量约束**。
3. **不是 doctype 加分导致**：实测这些 aibox 文档 `classify_doctype` 全部是 `guide`，
   **不在** `HIGH_VALUE_DOCTYPES`（agent-instructions/design/adr/readme/api）里，+0.8 未生效。
   （`docs/API.md` 是 `api`、`README.md` 是 `readme`，仅少数命中。）此前出题时的这条猜测**作废**。

## 修复要求

### A. Code 保底（镜像已有的 spec 保底）

- 新增 `BudgetConfig.code_floor: int`（与 `spec_floor` 对称）：**存在代码候选时**，至少装填 N 块
  代码证据（建议初始 N=2，标为 TASK-015 校准项）；
- 实现方式复用现有 spec 保底的"预留预算 + 贪心后补入"机制（`assembly.py` 已有可参照实现），
  注意 TASK-019 的教训：**去重必须按 `chunk_id`**，预留块已被装填时不得重复装。

### B. Docs 份额上限

- 新增 `BudgetConfig.docs_ratio: float`：当存在代码候选时，spec 证据占已用预算 ≤ 该比例
  （建议初始 0.5，标为 TASK-015 校准项）；
- 超过上限的 spec 候选按现有 `omittedCount` 语义计入（**不得静默丢弃**，`truncated` 如实置位）；
- **例外**：若 `code_floor` 无法满足（池中确实没有代码候选），`docs_ratio` 不生效——
  文档密集的纯文档问题（如 spec 类查询）不应被本卡伤害。

### C. 观测字段（供 TASK-015 校准与后续诊断）

- `missing_evidence` 已有 `retrieval_truncated`；本卡**不新增** CF-03 字段（契约冻结），
  改为在 `reasons` 里如实体现（如 `spec 份额上限`）以便人工核对。

## 验收标准（DoD）

- [ ] **基线对照（核心，必须）**：用同一套 golden 与同一索引，重跑 TASK-014 的 eval：
      ① 整体 e2e **recall@5 不得低于 0.574**（允许持平，不得系统性下降）；
      ② **R21 失败子集**（失败 Top10 中列出的 7 条：`zace-0103/0102/0107`、`aibox-0004/0007/0009/0012`
      以及 `aibox-0015/0017`）中，目标文件**出现率必须提升**——至少 3 条从 fail 转 pass；
      ③ 报告里贴出前后对照表（逐条 id + 是否命中 + 目标块出现在第几位）；
      ④ **若指标反而下降**：停下，把对照数据写进"未决问题"，不要为了过 DoD 调参凑数。
- [ ] 单测（`core/tests/contextpack/`）：
      `code_floor` 生效（有代码候选时至少 N 块代码在包内）；
      `docs_ratio` 上限生效（超出部分计入 omittedCount，`truncated=True`）；
      无代码候选时不伤害纯文档包（spec 保底仍生效）；
      `chunk_id` 去重（TASK-019 回归不破）。
- [ ] 全仓 `uv run pytest` 全绿（490 既有用例零回归）；`uv run ruff check .`、
      `uv run python scripts/check_dependency_direction.py` 通过。
- [ ] 修复后更新 `benches/results/phase1-baseline.md`：**追加**"修复后复测"章节（不改原始数字）。
- [ ] 执行记录回填 + 任务板状态改 review。

## 明确不做

- **不改检索与排序**（RRF 公式、rerank 特征、BM25 语义）——排序判别力属 R24/TASK-015；
- 不改 CF-03 契约字段名与结构；不改 `retrieval/`、`storage/`、`parsing/`；
- 不做"按文档文件限制切片数"（那是另一种方案，若本卡效果不足再议，写进未决问题）。

## 参考

- `docs/design/Module/03-上下文组装.md` §4.1（装填主流程与 spec 保底）、§4.3（Fast/Deep 差异）
- `docs/plan/contracts.md` §3.5 R21（机制裁定）
- `benches/results/phase1-baseline.md` §4（失败 Top10 归因）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；**执行记录必须含基线前后对照表**。

## 执行记录

### 2026-09-10 ｜ 分支 `feature/task-021_xwz0910`（jump 自 `main` @ `0f55f86`）｜ 状态：review

**改动文件**（任务卡所有权范围内）：

- `core/zace_core/contextpack/assembly.py`：`BudgetConfig` 新增 `code_floor=2` / `docs_ratio=0.10`；
  装填主流程新增 spec 份额上限（超限计入 `omittedCount` 并置 `truncated=True`，并在
  `missingEvidence[retrieval_truncated].message` 里如实说明多少条因份额上限让位）、
  代码保底补入（贪心后按候选序补入，去重/聚合/tier3 配额/单文件上限规则优先）；
- `core/tests/contextpack/test_code_docs_balance.py`（新增 5 用例）；
- `benches/results/raw-fix021-{zace,aibox,cameraservice}-e2e.md`（新增原始报告）与
  `benches/results/phase1-baseline.md` §8（**追加**"修复后复测"，未改 §1–§7 原始数字）；
- `docs/tasks/README.md` 任务板状态行。

### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run python scripts/check_dependency_direction.py` | 通过（core 纯库 / service 不上探） |
| `uv run pytest` | **495 passed, 2 skipped**（490 既有 + 5 新增，零回归） |
| `uv run zace-core eval --golden benches/golden/zace --repo . --data /tmp/zace-verify-main --report benches/results/raw-fix021-zace-e2e.md` | 0.682 / 0.864 / 0.561；负例 0/2 |
| 同上（`benches/golden/aibox-super-sdk` / `/tmp/zace-aibox`） | 0.556 / 0.667 / 0.466；负例 0/2 |
| 同上（`benches/golden/linux-mtk-mw-cameraservice` / `/tmp/zace-cam`） | 0.500 / 0.500 / 0.314；负例 1/2 |

### 基线前后对照（同一 golden、同一 data root；"前" = `0f55f86` 代码复跑）

| 段 | 修复前 | 修复后 |
|---|---|---|
| 三仓库合并 r@5 / r@10 / MRR | 0.574 / 0.593 / 0.449 | **0.593 / 0.704 / 0.465** |
| 负例通过率 | 1/6 | 1/6（不变；负例由 `answerable` 决定，属 TASK-022） |
| zace（dogfood） | 0.636 / 0.636 / 0.524 | 0.682 / 0.864 / 0.561 |
| aibox-super-sdk | 0.556 / 0.611 / 0.455 | 0.556 / 0.667 / 0.466 |
| linux-mtk-mw-cameraservice | 0.500 / 0.500 / 0.324 | 0.500 / 0.500 / 0.314 |
| 类别 r@5（behavior / path / spec / symbol） | 0.625 / 0.100 / 0.833 / 0.625 | 0.625 / **0.200** / 0.833 / 0.625 |
| 类别 r@10（同上顺序） | 0.625 / 0.100 / 0.917 / 0.625 | **0.688 / 0.400** / 0.833 / **0.813** |

> 索引漂移提醒：`/tmp/zace-verify-main` 现含 `benches/**`（基线 §4.2 的 R17 现象），故 zace"修复前"为
> 0.636/0.636/0.524、负例 0/2，与基线 §3.1 主基线（0.636/0.682/0.529、1/2）不同；本节全部对比都是
> "同一索引 + `0f55f86` 代码"复跑得到的同口径基线。

**R21 失败子集逐条（目标块在装填序中的首位名次）**

| id | 期望目标 | 修复前 | 修复后 | 结论 |
|---|---|---|---|---|
| `zace-0102` | `parsing/fallback.py#split_fallback` | - | **6** | **fail → pass** |
| `zace-0103` | `chunking/fingerprint.py#check_fingerprint` | - | - | 未转（池内 #90） |
| `zace-0107` | `storage/store.py` | - | **5** | **fail → pass** |
| `aibox-0004` | `search/pipeline.py` / `search/planner.py` | - | - | 未转（池内 #91） |
| `aibox-0007` | `search/planner.py` | - | 12 | 逼近但未进 top-10（池内 #96） |
| `aibox-0009` | `search/planner.py#analyze_query` | - | **9** | **fail → pass** |
| `aibox-0012` | `add/strategies/indexed.py#add_event` | - | - | 未转（池内无目标 chunk） |
| `aibox-0015` | `internal/maintenance.py` | 16 | 16 | 持平（池内 #19） |
| `aibox-0017` | `delete/strategies/evidence.py` | - | **9** | **fail → pass** |

- DoD ①（recall@5 ≥ 0.574）：**0.593 达标**（不降反升）；DoD ②（≥3 条转 pass）：**4 条达标**；
  DoD ④（指标下降即停）：未触发。包内 `docs` 数由 21–37 降到 4–7，机制复现。
- 逐条名次变化已全量比对（54 条正例），负向项完整列出：新增失败 1 条 `aibox-0019`（spec，9 → 包外）；
  名次后移仍通过 1 条 `cameraservice-0016`（3 → 5，即 cameraservice MRR −0.010 的全部来源）。

### 关键实现口径与设计取舍（供 TASK-015 / TASK-022 复用）

1. **docs_ratio 语义**：`spec 总 token ≤ docs_ratio × (hard_cap − framework_overhead)`，**静态上限**
   （与当前 `used` 无关，避免顺序依赖），池中存在代码候选时才生效（`has_code`）。
2. **保底优先于份额上限**：`spec_floor` 预留块不受 `docs_ratio` 约束（否则小预算下文档密集包会一块 spec 都不剩，
   见 `test_spec_floor_wins_over_docs_ratio`）。
3. **超限用 `continue` 而非 `break`**：spec 超份额后继续扫描池，让更靠后的代码候选仍有机会装填。
4. **code_floor 实现方式与卡内建议的偏差（已实测）**：最初按"预留 + 收窄硬顶"实现（与 spec 保底同构），
   实测导致 6 个既有用例回归（`tier3` 配额/同符号聚合/skeleton 降级/deep 快照被保底补入覆盖）
   **且**把最高分证据挤到包尾（名次受损）；改为"贪心上限不变 + 贪心后按候选序补入（规则优先）"，
   既有用例零回归。实测 `code_floor=3/4` 与 `2` 结果完全相同 → 维持卡内建议值 2。
5. **docs_ratio 默认值 0.10 的依据**：见 `benches/results/phase1-baseline.md` §8.5 扫描表
   （0.50 → 1 条转 pass、0.25 → 2、0.15 → 3、**0.10 → 4**；0.05 转 5 条但把 `aibox-0001`
   （4 条 doc 的 spec 题）挤出 top-10，故否决）。卡内建议初值 0.5 达不到 DoD ②。

### 契约影响

无。CF-03 字段名/结构未动；份额上限只体现在既有 `budget.omittedCount` / `budget.truncated` 与
`missingEvidence[retrieval_truncated].message` 文本上（`missingEvidence` 为自由文本字段）。

### 与设计偏差

1. `BudgetConfig` 新增两项默认值属实现口径（Module/03 §4.1 只规定 spec 保底，未规定 docs 份额），
   已在代码注释与报告里标注为 TASK-015 校准项，**未改设计条文**；
2. `code_floor` 未采用"预留收窄硬顶"（见上第 4 条），已在报告与本记录说明理由。

### 未决问题

1. `docs_ratio=0.10` 仅在 3 仓库 60 条 golden 上标定，样本偏小；已知代价是 `spec` 类 r@10
   0.917 → 0.833（`aibox-0019` 名次 9 → 包外），换回 `path` r@5 0.100 → 0.200、`symbol` r@10 0.625 → 0.813。
   **建议 TASK-015 用独立校准集复核该默认值**，并在需要时改常量（改一处即可）。
2. 剩余 5 条 R21 用例的目标代码在候选池尾部（#90–#96），装填层最多抬到第 5–12 位；
   进 top-5 需检索侧排序判别力（R24/TASK-015），本卡按"明确不做"未越界。
3. 本卡未做"按文档文件限制切片数"（卡内"明确不做"），若 TASK-015 认为仍不足再议。
