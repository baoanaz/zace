# TASK-015A：embedding bake-off（只做模型选型）

> 状态：pending ｜ 阶段：Phase 2（M2b，**可与 M2a 并行**）｜ 硬依赖：TASK-013 ｜ soft 依赖：TASK-014
> **范围裁定（用户 2026-09-10，R30/R32）**：
> - **A 部分（embedding bake-off）保留**：模型选型是**一次性的架构决策**（影响索引体积、嵌入成本、
>   中文/混合查询质量、V2 分发体积），不能推迟到有真实数据之后再拍；
> - **B 部分（rerank 权重、FTS 列权重、前缀匹配、通道配额校准）全部推迟到 TASK-050**：
>   当前 golden 集是 smoke 级（R29），在其上做网格搜索属过拟合。
> 本卡**只做 A**，且**不得**修改任何排序/装填参数。
> 建议分支：`feature/task-015a_<你的缩写><MMDD>`
> 交付物所有权：`benches/bakeoff/`（新建）、`benches/results/phase2-bakeoff.md`（新建）、
> `core/zace_core/embedding/registry.py` 或 `local.py`（**仅**默认模型 slug 一处，且仅在结论支持时）

## 目标

用数据钉死 D-44 遗留的"具体默认模型"，产出可复现的对比报告 + 默认值调整（如需）。

**这是一张"选型"卡，不是"调优"卡**：不碰 rerank 权重、不碰 FTS 权重、不碰装填配额。

## 输入文档（按序读）

1. `docs/design/Module/01-切片存储.md` §2.4（2048 截断假设）、§6-4（截断 A/B 待办）
2. `docs/design/INDEX.md` 的 D-44（embedding 双实现）、D-45（jieba 预分词）
3. `benches/README.md`、`benches/results/phase1-baseline.md`（TASK-014 基线）
4. `core/zace_core/embedding/`（`registry.py` / `local.py` / `api.py`：现有实现与模型注册表）
5. `docs/plan/contracts.md` §3.6（R29/R30：**为什么不能在本卡调参**）

## 交付内容

### A1. 对比脚本（`benches/bakeoff/embed_compare.py`）

- 对每个候选模型：**独立数据根**建索引 → 跑 golden → 记录
  `recall@5 / recall@10 / MRR`、**索引期嵌入总耗时**、**单查询延迟 P50/P95**、**向量库体积**。
- 候选（本地，ONNX）：
  - `multilingual-e5-small`（TASK-008 暂定默认，作为基线）
  - `bge-small-zh-v1.5`（中文定位）
  - `arctic-embed-xs`（对照）
  - **可选**：`bge-m3`（若体积/耗时可接受，作为上界参考——注意它是多语言大模型，重点看代价）
- **必须固定**：仓库、golden 用例、切分参数、检索参数（`RecallLimits` / `RerankWeights` / 装填配置全部用当前默认值，
  **一处都不许改**）。唯一变量是 embedding provider。
- 脚本要可断点续跑（模型下载/索引很慢，重复劳动不可接受）；中间结果落 JSON。

### A2. 截断 A/B

对**最终推荐模型**，比较 `max_input_tokens=512`（原生）vs `2048`（Module/01 §2.4 的假设）：
效果（recall/MRR）与代价（索引耗时、体积）。给结论：2048 是否值得。

### A3. 报告（`benches/results/phase2-bakeoff.md`）

- 模型对比表（含机器规格、完整命令、每行数字来源）；
- 截断对比表；
- **明确推荐**：默认模型 slug + `max_input_tokens` + 理由（含**不选较大模型的原因**，例如索引耗时/体积）；
- **索引代价章节**：按推荐模型推算真实仓库（434 文件 / 5760 chunks 量级）的全量索引耗时与磁盘占用
  ——这是 VPS 选型与 TASK-041R 分发体积的输入。

### A4. 默认值（仅当结论支持）

改动**只允许**在 embedding 默认型号一处。embedding 变更会写入 `index_config` 指纹（D-07 二级失效），
报告里必须附**重建流程实测记录**（改默认值后既有索引会走 `reembed`，说清耗时与结果）。

## 验收标准（DoD）

- [ ] `uv run python benches/bakeoff/embed_compare.py --help` 与报告里给出的完整命令可复现。
- [ ] 报告存在且含 A3 的四部分；所有数字可追溯到命令与数据根。
- [ ] **回归护栏**：跑 golden 前后，除 embedding provider 外无任何参数改动——
      在报告里贴出 `git diff` 证明唯一改动是脚本/报告（+ 可选默认 slug）。
- [ ] 基线三条全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- **不调** rerank 权重 / FTS 列权重 / 前缀匹配 / `RecallLimits` / `docs_ratio` / `CONSENSUS_SCORE_RATIO`
  （全部冻结，归 TASK-050，等 TASK-023 真实数据）。
- 不接 cross-encoder / 不做多模型 ensemble（V1.5）。
- 不为了指标好看而挑测试用例子集（**固定全集**，允许因耗时截断但要写明截断口径与理由）。
- 不提交模型文件到仓库（模型进缓存目录，报告里写路径与体积）。

## 参考源码锚点（只读）

- `core/zace_core/embedding/registry.py`（模型注册表与 slug）
- `core/tests/integration/conftest.py`（确定性假 provider——**不要**用它跑本卡，本卡要真实模型）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；**必须包含模型对比表与推荐理由**。

## 执行记录

（实施 AI 在此填写。）
