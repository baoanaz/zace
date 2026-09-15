# benches/results — 报告与原始证据索引

> **新 AI 请从本文件开始**：这里回答"哪份报告是当前口径、哪份是历史留档、数字由哪个原始文件支撑"。
> 报告全部是**设备绑定**的：同一个数字换设备不成立，引用时必须带上设备标识与日期。

## 0. 三十秒导航

| 你要做的事 | 去看 |
|---|---|
| 复用三靶场的**持久索引**跑基准（**不要重新索引**） | `../targets-benchmark.md` §持久索引 + `raw/ingest-vps/INDEXES.json` |
| 当前 VPS（生产）的索引耗时/内存/带宽/TPM 结论 | `index-cost-model-vps.md` |
| **要改维度 / chunk 切分，找对照点** | **`baseline-v1.md`**（冻结配置、基线数字、必须换数据根的原因） |
| **要看检索/问答质量**（三仓库 60 题） | **`qa-quality-v1.md`** + `../golden/<repo>/qa.md` |
| 公司 WSL 的同名结论（对照设备） | `index-cost-model-company-wsl.md` |
| 检索质量（recall/MRR）当前基线 | `../README.md`「相关报告」表 + `raw-*.md` |
| 计量脚本与各项指标口径定义 | `../embed-bench/README.md` |

## 1. 设备一览（数字只在各自设备成立）

| 设备标识 | 机器 | embedding | 数据根 | 主导报告 |
|---|---|---|---|---|
| `vps-la-2c2g` | 洛杉矶 VPS：2 vCPU / 1.9 GiB / 内核 5.15.0-191 | `voyage-4-lite` @1024（API） | `/root/.zace/bench/voyage-4-lite-d1024` | `index-cost-model-vps.md` |
| `company-wsl` | 公司 WSL2：6 核 / 15.6 GiB | 硅基流动 `BAAI/bge-m3` @1024 | `~/.cache/zace-bench` | `index-cost-model-company-wsl.md` |
| 旧开发机（已下线） | 历史工作区，靶场不可得 | 本地 ONNX / e5-small | — | `phase1/phase2/robustness/index-performance` |

## 2. 当前有效报告（可直接引用）

| 文件 | 设备 | 日期 | 一句话结论 |
|---|---|---|---|
| `index-cost-model-vps.md` | `vps-la-2c2g` | 2026-09-15 | 冷启动 = 本地 70% + 网络 30%；TPM 受链路限制永远跑不满 16M；并发 4 是甜点；内存是唯一风险 |
| **`baseline-v1.md`** | `vps-la-2c2g` | 2026-09-15 | **冻结配置 v1 + 三靶场基线**（后续调维度/chunk 的对照点）：含 ±20% 抖动纪律与两个「当前不可配」阻塞项 |
| **`qa-quality-v1.md`** | `vps-la-2c2g` | 2026-09-15 | **60 题质量首测**：search recall@5 0.64–0.77 / MRR 0.39–0.69；ask 全部作答且证据不足时如实拒绝；失败集中在符号级定位与负例阈值 |
| `index-cost-model-company-wsl.md` | `company-wsl` | 2026-09-15 | 耗时 ≈ chunk × 21 ms，瓶颈是下载响应体（~1 MB/s），与 TPM 无关 |
| `phase2-helloagents-baseline.md` | 旧机→当前 | 2026-09-14 | hello-agents 主靶场基线（recall@5 0.586 / recall@10 0.655 / MRR 0.388） |
| `raw-helloagents-baseline.md` | — | 2026-09-14 | 上表的 **runner 直出**原始产物 |
| `raw-cockpit-baseline.md` / `raw-cockpit-t101-final.md` | — | 2026-09-14 | 内部靶场 cockpit 修复前 / TASK-101 修复后 |
| `raw-zace-t101-final.md` | — | 2026-09-14 | zace dogfood 20 题（TASK-101 后） |

## 3. 历史报告（**决策依据留档**，与当前靶场不可比）

| 文件 | 日期 | 用途 |
|---|---|---|
| `phase1-baseline.md` | 2026-09-10 | Phase 1 M1 检索质量基线（旧靶场） |
| `phase2-bakeoff.md` | 2026-09-11 | embedding 选型 bake-off（D-44 依据） |
| `index-performance-w6.md` | 2026-09-13 | W6 合并后的索引耗时/增量/瓶颈归因 |
| `robustness-scale.md` | 进行中 | 多仓库规模与索引健壮性（TASK-036） |

这四份都引用了已下线的旧靶场（`aibox-super-sdk` / `linux-mtk-mw-cameraservice`），
文中命令与路径**不可再执行**；引用时请说明"历史数字"。

## 4. `raw/` 原始证据索引

| 文件/目录 | 产出脚本 | 支撑 |
|---|---|---|
| `ingest-vps/INDEXES.json` | `build_indexes.sh` | **持久索引清单**：projectId / chunks / 体积 / CLI 与探针两套墙钟与峰值 |
| `ingest-vps/{leveldb,HelloAgents,langchain}.json` | `ingest_probe.py` | `index-cost-model-vps.md` §1/§2 五项留档 |
| `ingest-vps/reuse-{langchain,leveldb}.json` | `ingest_probe.py --incremental` | 证明"复用不重嵌"（chunks_new=0 / api_tokens=0） |
| `ingest-vps-phases/*.json` | `ingest_probe.py` | §3.1 阶段分解的网络在飞时间（`network_busy_s`） |
| `local-only-vps.json` | `local_only_probe.py` | §3.1 纯本地耗地下限（零网络替身） |
| `ttfb-vps.json` | `ttfb_probe.py` | §3.3 并发 1/4/8 的聚合吞吐与 TTFB 分解 |
| `throughput-vps-conc-scan.json` | `throughput_probe.py` | §3.2/§4.2 并发扫描（4/8/16/32，16 因 2 vCPU 争抢崩塌） |
| `repo-profile-vps.json` | `profile_repo.py` | 三靶场画像（文件/chunk/token 分布，免 API） |
| `baseline-v1/*.json` | `ingest_probe.py` | `baseline-v1.md` 的全部数字（含机器负载快照） |
| `qa-probe/*.json` | `../golden/qa_probe.py` | `qa-quality-v1.md` 的逐题结果（search 排名 / ask 答案原文） |
| `ingest-run1/*.log` | `run_targets.sh`（WSL） | WSL 端到端墙钟与峰值（含 429 失败样本） |

> 命名约定：`*.json` = 脚本产出的**原始证据**（不改动）；`raw-*.md` = runner 直出的**报告**；
> 其余 `*.md` = 人工整理的结论。新增证据请沿用 `raw/` 下放 JSON、结论写 md 的分工。

## 5. 引用纪律

1. 引用任何数字都写清**设备 + 日期 + 口径**（CLI 墙钟 / 探针墙钟 / 网络在飞）；
2. `vps-la-2c2g` 上 **CLI 口径与探针口径差 ~19%**（探针自己在 tokenize 全量 chunk），别混用；
3. 改结论时**同时更新原始证据索引表**，否则下一次会话会找不到出处。
