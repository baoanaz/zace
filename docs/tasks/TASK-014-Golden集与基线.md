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

- **用例集**：`benches/golden/*.jsonl`，≥50 条，覆盖：
  | 维度 | 要求 |
  |---|---|
  | 语言 | 中文 ≥15、英文 ≥10、中英混合（中文问 + 代码标识符）≥15 |
  | 类型 | 符号定位（某函数/类在哪）、路径定位、行为问题（"X 在哪里被刷新/校验"）、spec/文档问题、负例（仓库中不存在 → 期望 no_context_match / answerable=false） |
  | 仓库 | zace 自身（dogfood）+ ≥2 个外部真实仓库（建议：Python=flask 或 requests；C=redis；C++=fmt；以本机可得为准） |
- **外部仓库纪律**：不 vendor 源码入库；用例中记录 `repo_hint` + `commit`；runner 由使用者 `--repo` 指向本地 checkout；README 补充"如何准备外部仓库"。
- **报告**：`benches/results/phase1-baseline.md`（由 `zace-core eval` 生成后整理），含：整体 recall@5/@10/MRR、分类指标（语言/类型/仓库）、失败清单与失败归因初判。
- 负例的判定口径：不强制 answerable=false（Phase 1 无 answerable 输出？—— 有，TASK-012 已产出），负例断言"top5 无强相关证据 + missingEvidence 非空"。

## 验收标准（DoD）

- [ ] `uv run zace-core eval --golden benches/golden --repo <zace自身> --report /tmp/r.md` 全量跑通，指标文件生成。
- [ ] 用例数量与维度按上表达标（脚本化统计：条目数 ≥50，各维度计数达标）；parse 校验：每行 JSON 可被 runner 读取。
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
