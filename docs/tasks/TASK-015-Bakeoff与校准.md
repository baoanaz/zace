# TASK-015：embedding bake-off + rerank 初值校准

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-013 ｜ soft 依赖：TASK-014（golden 用例集；可先用 3-5 条临时样例起步）
> 建议分支：`feature/task-015_<你的缩写><MMDD>`
> 交付物所有权：`benches/bakeoff/`、`benches/results/phase1-bakeoff.md`；默认值改动仅限 `core/zace_core/retrieval/rerank.py`（`RerankWeights` 数值）与 `core/zace_core/embedding/local.py`（默认模型 slug）

## 目标

用数据钉死两件事：默认 embedding 模型（D-44 遗留的"具体模型"）与 rerank 权重初始值（Module/02 §4.5 的校准义务）。
产出可复现的对比报告 + 默认值调整 PR。

## 输入文档（按序读）

1. `docs/design/Module/01-切片存储.md` §2.4（2048 截断假设）、§6-4（截断 A/B 待办）
2. `docs/design/Module/02-检索策略.md` §4.5（特征表与"分值需 benchmark 校准"）、§7-1
3. `benches/README.md`、TASK-014 的基线报告、TASK-008 的模型注册表

## 交付内容

### A. embedding bake-off（`benches/bakeoff/embed_compare.py`）

- 候选：`multilingual-e5-small` / `bge-small-zh-v1.5` / `arctic-embed-xs`（对照）+（可选，若有 API key）`api:bge-m3`。
- 方法：固定 golden 子集（能用 50 条最好）+ 固定仓库，对每个模型**独立建索引**跑 eval；记录：
  recall@5/@10、MRR、索引期嵌入总耗时、单查询延迟 P50/P95、内存峰值（可选）。
- 截断 A/B：对最佳本地候选，比较 `max_input_tokens=512`（原生）vs `2048`（Module/01 假设）的效果与成本。
- 结论：推荐默认模型 + 截断值，写入 `benches/results/phase1-bakeoff.md`；**若推荐模型非 TASK-008 暂定默认，则在本 PR 同步更新默认值**（属于配置默认值，允许改）。

### B. rerank 权重校准（`benches/bakeoff/rerank_tune.py`）

- 方法：golden 集按仓库/语言切训练/验证子集（防过拟合单集）；对 `RerankWeights` 做粗粒度网格/坐标下降（每特征 ±50% 范围，只动默认值，不动特征结构）。
- 结论：提报新默认值 + 前后指标对比表；权重改动随本卡合并（L1，不改特征结构）。
- 纪律：报告必须包含**反例检查**——Explicit 弱相关 vs 三通道共识强相关（Module/02 §4.6 场景）在新权重下的排序正确。

## 验收标准（DoD）

- [ ] 两个脚本可复现：`uv run python benches/bakeoff/embed_compare.py --repo <PATH> --golden benches/golden --out /tmp/embed.json`（脚本参数以实际实现为准，报告内给出完整命令）。
- [ ] 报告 `benches/results/phase1-bakeoff.md`：模型对比表 + 截断对比 + 权重前后对比 + 明确推荐与理由；所有数字带机器规格与命令。
- [ ] 默认值更新（若结论与暂定不同）：代码默认值 + `docs/plan/contracts.md` §2 无涉及（embedding 默认属配置，不需契约变更）；embedding 变更会改变 `index_config` 指纹——重建流程的实测记录必须附上。
- [ ] 基线三条命令全绿。
- [ ] `uv run pytest core/tests -q` 全绿（权重默认值改变后既有测试不得回归；必要时同步调整测试期望并在卡内说明）。

## 参考源码锚点（只读）

- `source/GitNexus/eval/`（评测跑分组织）
- `source/ragcode/src/document/evaluation/`（评测与调参思路）

## 明确不做

- 不接 cross-encoder（V1.5）；不做多模型 Ensemble；
- 不为了让指标好看而调通道配额结构（那是 L3 决策，需走编排者流程）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写：机器规格、各模型指标、最终推荐与默认值改动清单。）
