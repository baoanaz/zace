# TASK-021：装填层 Code/Docs 平衡（R21）

> 状态：pending ｜ 阶段：Phase 1+（质量修复，**M1 后最高优先级**）｜ 硬依赖：TASK-014（基线，已合并）｜ soft 依赖：无
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

（实施 AI 在此填写。）
