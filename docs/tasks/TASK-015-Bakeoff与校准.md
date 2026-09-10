# TASK-015：embedding bake-off + rerank 初值校准

> 状态：pending（**范围已拆分为 A/B**，B 部分推迟到真实数据）｜ 阶段：Phase 2 ｜ 硬依赖：TASK-013 ｜ soft 依赖：TASK-014
> **拆分裁定（用户 2026-09-10，R30/R32）**：
> - **A 部分（embedding bake-off）保留**：模型选型是架构决策，影响索引成本与 VPS 资源，需要一次拍定；
> - **B 部分（rerank 权重与通道配额校准）推迟**：当前 golden 集为 smoke 级（R29），在其上调参属过拟合；
>   挪入 TASK-050（真实数据到位后再做）。
> 本卡只做 A。
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

### 0. 前置与校准清单（W3 补充，编排者；依据 contracts.md §3.3 R11）

- 前置：TASK-016（BM25 OR + 列权重）、TASK-017（行序）已合并，TASK-014 基线报告已出；未合并先停下报告。
- **校准维度（逐项给前后对比，不允许只报最终值）**：
  1. `Store` 的 FTS 列权重三元组（content / signature / docstring；TASK-016 初始 1.0/5.0/1.0）；
  2. **FTS 前缀匹配开关**（`"term"*` vs 精确 token；TASK-016 列为本卡校准项）；
  3. `RerankWeights` 各特征值（网格/坐标下降，只改默认值不改结构）；
  4. `RecallLimits` 各通道配额（top-N）—— 只作对照实验，改动需编排者裁定（可能触及 Module/02 配额口径）。
- 前两项结论若与 TASK-016 默认值不同，需在报告给出推荐值并说明是否建议改默认。

### A. embedding bake-off（`benches/bakeoff/embed_compare.py`）

- 候选：`multilingual-e5-small` / `bge-small-zh-v1.5` / `arctic-embed-xs`（对照）+（可选，若有 API key）`api:bge-m3`。
- 方法：固定 golden 子集（能用 50 条最好）+ 固定仓库，对每个模型**独立建索引**跑 eval；记录：
  recall@5/@10、MRR、索引期嵌入总耗时、单查询延迟 P50/P95、内存峰值（可选）。
- 截断 A/B：对最佳本地候选，比较 `max_input_tokens=512`（原生）vs `2048`（Module/01 假设）的效果与成本。
- 结论：推荐默认模型 + 截断值，写入 `benches/results/phase1-bakeoff.md`；**若推荐模型非 TASK-008 暂定默认，则在本 PR 同步更新默认值**（属于配置默认值，允许改）。

### B. ~~rerank 权重校准~~ —— **推迟到 TASK-050**（R30/R32）

原计划基于当前 golden 集调 `RerankWeights`。**不做**：当前用例集是编排者构造的 smoke 集（R29），
在其上做网格搜索会过拟合到 60 条而非真实分布。**TASK-021/022 已实施的参数**
（`docs_ratio=0.10`、`CONSENSUS_SCORE_RATIO=2.15` 等）同样标注"未经真实数据校准"，
在 TASK-050 统一重评，本卡不动它们。

## 验收标准（DoD）

- [ ] `uv run python benches/bakeoff/embed_compare.py --repo <PATH> --golden benches/golden --out /tmp/embed.json` 可复现（脚本参数以实际实现为准，报告内给出完整命令）。
- [ ] 报告 `benches/results/phase1-bakeoff.md`：**模型对比表 + 截断对比 + 明确推荐与理由**；所有数字带机器规格与命令。
- [ ] 默认值更新（若结论与暂定不同）：改动限于 `core/zace_core/embedding/local.py` 的默认 slug；
      embedding 改变 `index_config` 指纹，重建流程的实测记录必须附上。
- [ ] 基线三条全绿；全仓 `uv run pytest` 全绿。
- [ ] **明确不做 B 部分**（rerank 权重与通道配额校准）——那是 TASK-050，依赖 TASK-023 的真实数据。

## 参考源码锚点（只读）

- `source/GitNexus/eval/`（评测跑分组织）
- `source/ragcode/src/document/evaluation/`（评测与调参思路）

## 明确不做

- 不接 cross-encoder（V1.5）；不做多模型 Ensemble；
- **不调 rerank 权重与通道配额**（推迟到 TASK-050，需真实数据）；
- 不为了指标好看而调通道配额结构（那是 L3，需走编排者流程）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写：机器规格、各模型指标、最终推荐与默认值改动清单。）
