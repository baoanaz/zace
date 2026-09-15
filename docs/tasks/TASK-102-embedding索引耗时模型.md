# TASK-102：embedding 索引耗时模型与设备绑定基准

> 状态：review ｜ 阶段：Phase 2 / 运维基准 ｜ 硬依赖：无 ｜ soft 依赖：TASK-049（embedding 配置化）
> 建议分支：`feature/task-102-embed-bench_xwz0915`
> 交付物所有权：`benches/embed-bench/`、`benches/results/index-cost-model-company-wsl.md`、
> `benches/targets-benchmark.md`、`benches/results/raw/`
> （`docs/handbook/embedding-provider切换.md` 只做最小增量改动，见"执行记录"）

## 目标

把"索引一个仓库要多久"从经验判断变成**可换算的公式 + 设备绑定基准**，并回答三个具体问题：
① 耗时到底与什么相关；② 免费 bge-m3 的并发/截断参数能不能提速；③ 换 16M TPM 模型值不值。

被谁消费：运维/部署选型（`docs/plan/phase2-roadmap.md`）、embedding 参数默认值（TASK-049 后续标定）、
用户"该等多久"的预期管理。

## 输入文档

1. `docs/handbook/embedding-provider切换.md`（现行参数与实测数字）
2. `docs/tasks/TASK-049-embedding架构整理.md` §7–§8（编排者参数标定，本卡对其复核）
3. `benches/README.md`（靶场约定与报告格式）

## 冻结接口

- 消费：`EmbeddingConfig` / `create_provider` / `EmbeddingProvider.embed`（CF-09）、
  `split_file` / `embedding_text`（chunking）、`DirectorySource`（pipeline）
- 产出：**不改任何 core/service 代码**；只新增 benches 侧脚本与报告

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `benches/embed-bench/profile_repo.py` | 靶场画像（解析+切分+精确 token 统计，**免 API**） |
| `benches/embed-bench/throughput_probe.py` | 吞吐标定（真实 chunk 文本，带响应体/状态码记账） |
| `benches/embed-bench/run_targets.sh` | 三靶场 × 配置矩阵的端到端 ingest 驱动 |
| `benches/results/index-cost-model-company-wsl.md` | **主报告**：耗时模型 + 设备绑定基准 |
| `benches/targets-benchmark.md` | 三靶场登记（路径/commit/画像） |
| `benches/results/raw/*.json` | 原始证据（画像 + 吞吐） |

## 验收标准（DoD）

- [x] 三靶场画像跑通，token 统计与 indexer 口径一致（含 C++ `.h` 抬升）
- [x] 吞吐矩阵实测（batch / concurrency / max_input_tokens 三变量）
- [x] 端到端 ingest 实测（3 靶场 × 3 配置，串行）
- [x] 结论有原始证据可追溯（`raw/*.json` + `~/.cache/zace-bench/ingest-run1/*.log`）
- [x] 量化"响应体 = chunk 数 × 21.3 KB"这一主导项
- [ ] 基线三条全绿（本卡不碰 core/service，见执行记录）
- [ ] 编排者复核 + 裁决 §8 未决问题 5（D-05 口径）

## 明确不做

- 不改 `core/` / `service/` 任何代码；
- 不做降维（`output_dimension=256`）实测与质量评估（列为未来工作，需先有 golden 口径）；
- 不调整 chunk 切片规则（撞 D-02，需架构评审）；
- 不在 VPS 上实测（用户计划中，见报告 §5）。

## 执行记录

**日期**：2026-09-15 ｜ **实施**：AI（lane-b）｜ **状态**：实测完成，待编排者复核

### 结论（三条，均有实测支撑）

1. **耗时模型**：`索引耗时 ≈ chunk 数 × 21 ms`（1024 维 @ ~1 MB/s）。
   瓶颈是**下载向量响应体**（21.3 KB/chunk），不是模型算力、不是 TPM 配额。
2. **两个直觉被推翻**：`max_input_tokens=2048` 对耗时**无收益**（响应体与输入长度无关，实测反而略慢）；
   并发 3 在小仓库 1.85×，但**在 langchain 上 429 整次失败**。
3. **TPM 从未成为瓶颈**：本机实测发送 46–53K tok/min，仅为免费档配额的 ~10%；
   并发不提高 token 速率（瓶颈在下载侧）。

### 与设计/手册的偏差（**交编排者裁决，未自行修改**）

| # | 偏差 | 影响 | 建议 |
|---|---|---|---|
| 1 | **D-05 / Module-01 §2.4 写"embedding 截断 2048 token"**，但实测 2048 既不省时间，也不是当前生效的截断层（实际受 `EMBEDDING_BODY_MAX_CHARS=8000` 字符上界约束） | 设计文档口径与实测不符 | 由编排者决定是否更新 Module-01 §2.4 的措辞（本卡未改 `docs/design/**`） |
| 2 | `docs/handbook/embedding-provider切换.md` §4 写"加大 batch 可提速" | 实测 batch 256→768 耗时**无变化**（54.9s / 55.6s / 54.6s） | 已在本卡报告中记录；手册修订建议由编排者统一处理 |
| 3 | 同上手册把 `EMBED_MAX_INPUT_TOKENS` 列为"一般不用改" | 实测确认不该改（调小无收益）——**与手册一致，无需修订** | — |

### 未决问题

1. VPS(10 MB/s) 待实测 → 报告 §3 的外推列需替换为实测；
2. 降维（256 维）提速 ~4× 但质量代价未评估；
3. chunk 数量调整（撞 D-02）；
4. 上表偏差 1、2 待编排者裁决。

### 环境说明（重要）

- 全部实测在 **lane-b 工作区**执行，未触碰 `main`；参考仓库**只读**；
- 索引产物落在 `~/.cache/zace-bench/`（**不入仓库**）；`benches/results/raw/` 只留日志与 JSON（68 KB）；
- **单 key 独占**：实测期间无其他 ingest/eval 进程（用户已确认并会持续遵守）。

### 交接：VPS 验证（2026-09-15 用户决定）

后续验证由 **VPS 侧 AI** 执行。验证清单（前置检查 / 靶场 commit / 三个脚本入口 /
判定标准 / 回报格式）已写在主报告
`benches/results/index-cost-model-company-wsl.md` **§8**，无需额外交接文档。

**给 VPS 侧 AI 的三条要点**：
1. **别改本卡脚本**：三个入口（`profile_repo.py` / `throughput_probe.py` / `run_targets.sh`）
   已带设备自适应参数，直接跑即可；
2. **画像数字必须逐位一致**（`chunks` / `tokens`）——不一致就是解析口径问题，先修口径再比耗时；
3. **`response_MB_per_s` 是关键对比数**，它直接给出 VPS 相对 company-wsl 的带宽倍数，
   模型成立与否由它判定。

**我在文档里修正的一处自身错误**（供复核）：初稿把降维写成"zace 侧有 `output_dimension` 支持"，
核实后发现该字段仅在 `registry.py:116` 登记、**无消费方也无 env**，已改为"需先开卡"。
