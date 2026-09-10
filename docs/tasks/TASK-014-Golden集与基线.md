# TASK-014：golden set 扩充 + 基线报告

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-013 ｜ soft 依赖：无
> 建议分支：`feature/task-014_<你的缩写><MMDD>`
> 交付物所有权：`benches/golden/`、`benches/results/`、`benches/README.md`（仅追加"用例编写指南"节）

## 目标

把 M1 的"检索质量"变成可回归的数字：50+ 条中英混合 golden 查询 + 基线报告，
这是 TASK-015 校准与后续一切质量判断的地基（Module/02 §7-1）。

## 输入文档（按序读）

1. `benches/README.md`（用例格式定义）
2. `docs/design/Module/02-检索策略.md` §7-1、§4.5（特征校准需求）
3. `docs/design/Demo.md` §23（北极星：Context Acquisition Cost——本卡只出检索侧代理指标）

## 交付内容

- **前置（必须先在执行记录里确认）**：TASK-016（BM25 OR 语义）、TASK-017（证据块行序）、**TASK-018（兜底行号阻断修复）**、**TASK-019（spec 保底去重）** 均已合并。
  若未合并，任务将无法在真实多语言仓库上跑通（U1 会让 ingest 直接崩），或基线指标系统性偏低（BM25 通道全空）——先停下报告。
- **基线必须分两段跑并对比**：① 仅索引层质量（BM25/Exact 召回，不受行序影响）；
  ② 端到端（含装填渲染）。这也让后续校准能定位增益来自哪一层。
- **用例集**：`benches/golden/*.jsonl`，≥50 条，覆盖：
  | 维度 | 要求 |
  |---|---|
  | 语言 | 中文 ≥15、英文 ≥10、中英混合（中文问 + 代码标识符）≥15 |
  | 类型 | 符号定位（某函数/类在哪）、路径定位、行为问题（"X 在哪里被刷新/校验"）、spec/文档问题、负例（仓库中不存在 → 期望 no_context_match / answerable=false） |
  | 仓库 | zace 自身（dogfood）+ **`aibox-super-sdk`（已指定，见下）** + 另 1 个自选外部仓库（建议 C/C++，以本机可得为准） |

- **已指定的外部评测仓库（编排者 2026-09-10 定）**：`/home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk`
  @ `debf8a322aff7d2d21939bc6d09b4cfa985671ea`；元信息与负例口径见 `benches/README.md`。
  - 为什么选它：文档密度极高（memory 能力 146 md / 83 py），是 spec 检索（D-13/D-42）的主靶场；
    用户指定种子问题 `workflow 在记忆系统里是怎么定义和使用的？`——该词在代码中仅 1 处、在 Markdown 中 4 处，
    正而检验“文档+代码一起检索”这个差异点（只看代码会误判为不存在）。
  - **种子用例已备**：`benches/golden/aibox-seed.jsonl`（8 条，含 1 条负例，编排者已核验可落地）；
    你在此基础上扩充至满足上表维度要求，并在报告中记录实际 checkout 的 commit。
  - 该仓库的 `.venv/` 已在 `DEFAULT_SKIP_DIRS` 中（实测 451 个可索引文件），无需手工排除。
- **外部仓库纪律**：不 vendor 源码入库；用例中记录 `repo_hint` + `commit`；runner 由使用者 `--repo` 指向本地 checkout；README 补充"如何准备外部仓库"。
- **报告**：`benches/results/phase1-baseline.md`（由 `zace-core eval` 生成后整理），含：整体 recall@5/@10/MRR、分类指标（语言/类型/仓库）、失败清单与失败归因初判。
- 负例的判定口径：不强制 answerable=false（Phase 1 无 answerable 输出？—— 有，TASK-012 已产出），负例断言"top5 无强相关证据 + missingEvidence 非空"。

## 验收标准（DoD）

- [ ] `uv run zace-core eval --golden benches/golden --repo <zace自身> --report /tmp/r.md` 全量跑通，指标文件生成。
- [ ] 用例数量与维度按上表达标（脚本化统计：条目数 ≥50，各维度计数达标）；parse 校验：每行 JSON 可被 runner 读取。
- [ ] **`aibox-super-sdk` 至少包含编排者的 8 条种子用例**（`aibox-seed.jsonl`），
      并对其跑出可读的分类指标（该仓库单独一行）；种子用例若实测不可命中，先记录归因再考虑调整，**不得直接删题**。
- [ ] 基线报告已提交 `benches/results/phase1-baseline.md`（含外部仓库 commit 记录）。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/GitNexus/eval/`（评测集与 workflow bench 的组织方式）
- `source/codegraph/scripts/agent-eval/`（agent 侧评测脚本思路）

## 明确不做

- 不做 agent 端 A/B（zace vs 纯 grep/read 的完整对照属 Phase 4）；
- 不追求用例绝对完备（版本来回迭代，先建立"可回归"这一事实）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写：实际使用的仓库/commit、条目统计、基线指标摘要、失败 Top10 归因。）
