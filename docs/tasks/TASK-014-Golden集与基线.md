# TASK-014：golden set 扩充 + 基线报告

> 状态：done ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-013 ｜ soft 依赖：无
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

### 2026-09-10 ｜ 分支 `feature/task-014_xwz0910`（自 `main` @ `086d24e`）

**前置核验**：TASK-016（BM25 OR 语义）、TASK-017（证据块行序）、TASK-018（兜底行号/ID 唯一性）、
TASK-019（spec 保底去重）均已合并进 `main`（`git log --oneline` 可见 `9628e83`/`7fddd1c`/`1af6587` 等合并点），
`086d24e` 已含 TASK-020（BM25 判别力）。

**实际使用的仓库 / commit / 索引**：

| repo_hint | commit | 索引文件/chunks/symbols/edges | data root |
|---|---|---|---|
| `zace` | `self`（`086d24e` + 编排者既有 golden 文件） | 217 / 2412 / 1467 / 7058 | `/tmp/zace-verify-main`（复用，19:34 增量刷新 6s） |
| `aibox-super-sdk` | `debf8a322aff7d2d21939bc6d09b4cfa985671ea` | 451 扫描（434 解析）/ 5760 / 2632 / 13269 | `/tmp/zace-aibox`（复用，增量刷新 1.2s） |
| `linux-mtk-mw-cameraservice`（自选 C++17） | `3fb0b2d69d81850a630eb5b6ced5d78f5461257c` | 281（+1101 二进制跳过）/ 6257 / 4614 / 2760 | `/tmp/zace-cam`（全量新建，559.6s） |

**条目统计**：60 条（zace 24 含样例题 4、aibox 20 含编排者种子 8、cameraservice 16）；
lang：zh 26 / en 14 / mixed 20；category：symbol 16 / path 10 / behavior 16 / spec 12 / negative 6。
种子用例零改动（`git status` 为 `R` 纯改名，逐字节保留）；`sample.jsonl`、`aibox-seed.jsonl`
移入各自仓库目录（同目录混放多仓库用例时无法按仓库取指标）。

**基线指标摘要**（正例 54；详细数字与分类见 `benches/results/phase1-baseline.md`）：

- ①索引层（候选池序）：recall@5 **0.556** / recall@10 **0.593** / MRR **0.447**；
- ②端到端（ContextPack 装填序）：recall@5 **0.574** / recall@10 **0.611** / MRR **0.451**；负例通过 **2/6**；
- 分仓库 e2e：zace 0.636/0.682/0.529（负例 1/2）、aibox 0.556/0.611/0.455（0/2）、
  cameraservice 0.500/0.500/0.324（1/2）；向量通道零降级；
- 分类：spec 0.833 最稳、symbol/behavior 0.625、**path 仅 0.100 最弱**；en 0.769 > zh 0.524 ≥ mixed 0.500。

**失败 Top10 归因**（完整表见报告 §5）：docs/spec 挤占 code（zace-0103/0102/0107、aibox-0004/0007/0009/0012、
zace-0119 近名干扰）、path 类无字面路径（aibox-0011/0015/0017）、符号单向匹配口径（zace-0113 路径已中但符号不匹配）、
`.claude/` 未被忽略的 skill 文档抢位（cameraservice-0006/0008）、装填预算把代码块挤出（cameraservice-0007）、
装填正贡献样本（zace-0118 候选池外→e2e top-10）。种子负例 `aibox-0008` 前提已过期（`Kubernetes` 在
仓库根 README + 未跟踪 `egg-info/PKG-INFO` 各 1 处命中，源码目录仍 0 命中）——不删题，已记录归因。

**R17 实测（dogfood 负例）**：索引含本轮 golden 文件时 `zace-0106` 由通过转不通过（负例 1/2 → 0/2），
`zace-0004` 两次运行皆因 `core/tests/cli/eval.py` fixture + `benches/golden/sample.jsonl` 命中 top-2 而失败。
结论：`benches/**` 在索引内时 dogfood 负例不可能通过，已写入报告未决问题 1（需 `--exclude` 口径或独立 data root）。

**验收命令与结果**：

```text
uv run ruff check .                                → All checks passed!
uv run python scripts/check_dependency_direction.py → 依赖方向检查通过（core 纯库 / service 不上探）
uv run pytest                                      → 484 passed, 2 skipped in 12.27s
uv run zace-core eval --golden benches/golden --repo . --data /tmp/zace-verify-main \
  --report benches/results/raw-smoke-all-repos-on-zace.md
  → 60 条全部执行、0 异常、向量降级 0（跨仓库混跑，只作 runner 冒烟，不代表质量）
uv run zace-core eval --golden benches/golden/zace --repo . ...（另有 aibox / cameraservice 各一条，见报告 §7）
  → 三条分仓库 e2e 报告 + 三条索引层报告，落在 benches/results/raw-*.md
```

**契约影响**：无。**与设计偏差**：无。

**未决问题**（报告 §6 详述，需编排者裁决/开卡）：

1. R17 需口径级解法（runner `--exclude` 或负例回归专用 data root）；
2. `answerable` 判定在文档密集仓库上恒为真（`_assess` 的 `consensus>=2` 只数双通道命中数，
   外部 3 条负例 `missingEvidence` 已报 `unresolved_reference` 却 `answerable=true`）——属 Module/03 §4.4 口径；
3. runner 缺 `--stage index|e2e` 开关（本卡①段用 40 行脚本，未入库，建议 TASK-015 固化为 CLI 能力）；
4. 符号断言单向匹配（`Indexer.ingest` 不满足期望 `Indexer`），建议评估父类/模块前缀是否算命中；
5. `DirectorySource` 未落地 D-28 忽略规则（`.claude/`、`egg-info/`、构建目录文本文件都进索引）；
6. 期望待复核 2 条（`zace-0001` 构造点 vs 定义点、`aibox-0008` 负例前提），均不删题。
