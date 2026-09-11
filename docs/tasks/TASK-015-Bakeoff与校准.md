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

**日期**：2026-09-11 ｜ **分支**：`feature/task-015a_xwz0910`（jump 自 `main` @ `ea4084d`）
**状态**：A1/A2(部分)/A3 完成，A4 未触发（结论支持沿用现状）｜ **报告**：`benches/results/phase2-bakeoff.md`

### 交付物

- `benches/bakeoff/embed_compare.py`（A1 对比脚本：list / fetch / run / aggregate / compare / clean）
- `benches/bakeoff/run_matrix.sh`（批量驱动）
- `benches/bakeoff/test_embed_compare.py`（22 条单元测试，不联网、不加载模型）
- `benches/results/phase2-bakeoff.md`（A3 报告：模型对比表 + 截断 A/B + 推荐 + 索引代价）
- **未改** `core/**`（结论支持沿用 `multilingual-e5-small`，A4 不触发，`git diff main -- core/` 为 0 行）

### 验收命令与结果

```bash
# DoD 1：--help 与报告中的完整命令可复现
uv run python benches/bakeoff/embed_compare.py --help            # → 6 个子命令，退出码 0
uv run python benches/bakeoff/embed_compare.py list              # → 4 个候选 + 缓存命中状态

# DoD 2：三模型 × 三仓库矩阵（每仓库一次目录调用）
uv run python benches/bakeoff/embed_compare.py run --model multilingual-e5-small \
  --repo . --repo-name zace --golden benches/golden/zace
#   → chunks=3218 vectors=5.3MB 索引=2359s
#   → r@5=0.591 r@10=0.818 MRR=0.539 neg=0/2 search_p50=0.856s
# （同命令换 --repo/--golden 与 --model 得到其余 8 行；完整表见报告 §3）

# DoD 3：脚本单测
uv run pytest benches/bakeoff/test_embed_compare.py -q            # → 22 passed
```

三仓库合并（54 正例，② e2e 口径）：

| 模型 | recall@5 | recall@10 | MRR | 向量库 | 索引耗时（zace/aibox/cam） |
|---|---|---|---|---|---|
| **multilingual-e5-small**（维持默认） | **0.556** | **0.685** | **0.457** | 5.3 / 9.4 / 10.1 MB | 2359 / 3686 / 2325 s |
| bge-small-zh-v1.5 | 0.537 | **0.685** | 0.398 | 6.9 / 12.4 / 13.3 MB | 1077 / 2247 / 1007 s |
| arctic-embed-xs | 0.463 | 0.574 | 0.355 | 5.3 / 9.4 / 10.1 MB | 1000 / 1928 / 1047 s |

### 结论摘要

1. **默认模型维持 `multilingual-e5-small`**（384D / 512 token）：r@5 与 MRR 双第一，
   向量库体积与最小模型持平（1638 B/chunk），代价是索引耗时约为对照的 1.5–2 倍。
2. **`max_input_tokens` 维持 512**：e5-small 与 bge-small-zh 的 ONNX 位置嵌入只有 512 行，
   `--max-input-tokens 2048` 直接崩溃（`Attempting to broadcast an axis by a dimension other
   than 1. 512 by 901`）；arctic 的"通过"是 tokenizer 静默截断。
   → **Module/01 §2.4 的 2048 假设在本地小模型上物理不可行**，截断 A/B 只能在原生上限 ≥2048
   的模型（本候选集只有 bge-m3）上做，因此 **A2 未获得数字**（详见报告 §4）。
3. **不选 bge-m3**：吞吐 0.38 chunk/s（e5 的 1/4）、单进程 3GB、单仓库外推 4.2 小时、
   向量库 2.5 倍，且质量收益**未获验证**（本机资源不足，未跑完——编排者裁定停跑）。
4. 索引耗时几乎全在嵌入（占墙钟 96–98%）；`index.db` 与模型无关；
   `bytes/chunk ≈ dim×4 + ~100`，可用于体积预估。

### 与设计的偏差

1. **数据根由 `/tmp` 改到 `~/.cache`**：任务卡指定的三个现成索引与模型缓存
   （`/tmp/zace-aibox`、`/tmp/zace-verify-main`、`/tmp/zace-cam`、`/tmp/zace-embedding-cache`）
   在本机 2026-09-11 00:07 重启后**已全部不存在**（`/tmp` 被清空）。
   处置：脚本默认路径改为 `~/.cache/zace-bakeoff{,/results}` 与 `~/.cache/zace-embedding-cache`，
   并**在同一数据根上重建三个仓库索引**——因此报告全部数字（含 e5-small 基线行）口径自洽，
   未混用 TASK-014 的旧索引数字。设计层面无偏差。
2. **A2 未完成**（原因见上第 2 条，非实现缺陷）。
3. **可选上界参考 bge-m3 未跑完**：因本机 WSL 仅 6 核 / 15.6 GiB、无 GPU，
   bge-m3 与另外两条泳道并发时触发内存事故，编排者裁定停跑。
   数据根 `~/.cache/zace-bakeoff/bge-m3-int8__t512/` 保留、可断点续跑。

### 回归护栏（R29/R30 的证明）

```bash
git diff main -- core/ core/zace_core/retrieval/ core/zace_core/contextpack/ | wc -l   # → 0
git diff --stat main     # 只含 benches/bakeoff/**、benches/results/phase2-bakeoff.md、
                         #      docs/tasks/TASK-015-*.md、docs/tasks/README.md
```

未碰 rerank 权重 / FTS 列权重 / 前缀匹配开关 / `RecallLimits` / `docs_ratio` /
`CONSENSUS_SCORE_RATIO`；脚本 `run` 子命令也没有这些参数的入口。

### 未决问题

1. **bge-m3 未跑完**（上界参考）：已完成 aibox 索引（未完质量），zace 两项未做。
   建议租 GPU 云服务器（A10/RTX4090，¥2–4/小时，1–2 小时可跑完全矩阵）用本卡脚本复现，
   取回 `~/.cache/zace-bakeoff/results/*.json` 后 `aggregate` 合并进报告即可。
2. **A2 截断 A/B 缺数字**：需 bge-m3（唯一支持 2048 的候选）在云端跑。
3. **provider 未校验截断上限**（配置超上限 → 运行期 ONNX 崩溃）：
   已由编排者立 **TASK-038**，本卡按指令未改代码。
4. **量化版本未测**（`model_qint8_avx512_vnni.onnx`）：若分发体积成为约束需另开卡，
   且量化会改变向量空间（触发 D-07 二级失效）。
5. **R29 复核提醒**：模型间 12 条命中翻转集中在 MRR 层面，差距不大，
   真实数据（TASK-023）到位后应复核本结论。
