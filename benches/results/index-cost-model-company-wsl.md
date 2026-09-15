# 索引冷启动耗时模型：设备绑定基准（company-wsl）

> 状态：**已实测**（2026-09-15）｜ 分支：`feature/task-102-embed-bench_xwz0915`
> 设备标识：**`company-wsl`**（公司 WSL2 开发机，本文件所有数字**只对该设备成立**）
> 靶场：`/home/xuwenzheng/2_github/AI/ACE/benchmark/{leveldb,HelloAgents,langchain}`
> 原始证据：`benches/results/raw/*.json`（吞吐）+ `~/.cache/zace-bench/ingest-run1/*.log`（端到端）
> 复现脚本：`benches/embed-bench/{profile_repo.py,throughput_probe.py,run_targets.sh}`

## 0. 一句话结论

> **冷启动耗时 ≈ chunk 数 × 21 ms，与 token 总数、与 TPM 配额基本无关。**
> 因为瓶颈是**下载向量响应体**（21 KB/chunk @1024 维），不是模型算力、也不是配额。
> 本机（company-wsl）实测有效下载带宽 **~1 MB/s**，这是唯一的主导变量。

## 1. 耗时模型（决策表）

| 指标 | 决定什么 | 是否本机瓶颈 |
|---|---|---|
| Total Tokens | API 计费、请求体大小 | ❌ 不影响耗时（请求体只占响应体 1/17） |
| **TPM** | API 允许的最高输入吞吐 | ❌ 本机只用到 46–53K/月配额的 ~10%，从未成为瓶颈 |
| **Chunks** | 要生成多少个向量 | ✅ **线性决定下载量** |
| **Response MB** | 实际需要下载多少数据 | ✅ **真正的主导项** |
| **API→本机 MB/s** | 向量下载需要多久 | ✅ **唯一瓶颈**（~1 MB/s） |

**公式**：

```text
索引耗时 ≈ (chunk 数 × 21.3 KB) ÷ 本机下载带宽   +  批数 × TTFB(≈1.6s)   +   本地解析(≈0.5%)
         ≈ chunk 数 × 21 ms                      （1024 维 @ 1 MB/s，串行）
```

**为什么会有 TPM 的错觉**：`token 总量 ÷ TPM` 算的是"配额允许你最快多久发完"，
是**限速牌**，不是发动机耗时。langchain 4.73M ÷ 16M TPM = 17.7s，而实测总耗时 589s——
那 17.7s **根本没有出现在加法里**，因为本机压根没发那么快。

## 2. 设备绑定基准（company-wsl）

```text
CPU 6 核 / 内存 15.6 GiB / 内核 5.15.167.4-microsoft-standard-WSL2
代理 http://127.0.0.1:7890（实测：代理与直连同为 ~0.78 MB/s，瓶颈在本机出口，不在代理）
实测下载带宽 ~0.76–1.01 MB/s（三种独立方法互证：批扫描 / TTFB 分解 / 端到端）
embedding：硅基流动 `BAAI/bge-m3`，1024 维，max_input_tokens=8192，batch=256，budget=75000
```

### 2.1 端到端 ingest 墙钟（三靶场 × 三配置）

| 配置 | leveldb（小） | HelloAgents（中） | langchain（大） |
|---|---|---|---|
| `conc=1` maxTok=8192 | **52.7s** ✓ | **83.9s** ✓ | **589.3s** ✓ |
| `conc=3` maxTok=8192 | **28.5s** ✓（1.85×） | **44.7s** ✓（1.88×） | **429 失败 ✗** |
| `conc=3` maxTok=2048 | 46.6s ✓（**反而变慢**） | **429 失败 ✗** | **429 失败 ✗** |

### 2.2 三靶场画像（本地统计，零 API 成本）

| 档 | 仓库 | 主语言 | 文件(listed/parsed) | **chunks** | **tokens** | tok/chunk | 响应体(≈chunk×21.3KB) |
|---|---|---|---|---|---|---|---|
| 小 | `leveldb` | C++ | 152 / 152 | **1,898** | 0.26M | 137 | 40 MB |
| 中 | `HelloAgents` | Python/MD | 240 / 236 | **2,729** | 0.89M | 328 | 58 MB |
| 大 | `langchain` | Python | 3,123 / 2,950 | **20,673** | 4.73M | 229 | **440 MB** |

> ⚠️ `langchain` 目录 644 MB 中 **593 MB 是 `.git`**，可索引范围只有 4.73M token。
> **仓库体积不是好指标，chunk 数才是**（实测耗时与 token 数无关、与 chunk 数线性）。

### 2.3 响应体：被忽略的主导项（langchain 4000 chunk 抽样）

| 配置 | 耗时 | 响应体 | 实测速率 | 429 |
|---|---|---|---|---|
| maxTok=8192 conc=1 batch=256 | 109.4s | **83.03 MB** | 0.76 MB/s | 0 |
| maxTok=8192 conc=1 batch=512 | 55.6s | 83.03 MB | 0.75 MB/s | 0 |
| maxTok=8192 conc=3 | 86.4s | **83.03 MB** | 0.96 MB/s | 0 |
| **maxTok=2048** conc=1 | **111.6s** | **83.03 MB** | 0.74 MB/s | 0 |

**响应体在所有配置下逐字节相同**——因为 `响应体 = chunk 数 × 维度 × ~21 B`，与输入长度无关。
单个 float 在 JSON 里约 20 字符（`-0.012345678901234`），比二进制 4 B 大 5 倍。

**请求体 vs 响应体（反直觉的根源）**：

| | 大小 |
|---|---|
| 请求体（1 个 300-token chunk） | ~1.2 KB |
| **响应体（1 个 1024 维向量）** | **21.3 KB** |
| **放大倍数** | **17×** |

### 2.4 TTFB 分解（httpx 流式探测，无截断）

| 请求条数 | 响应体 | TTFB（服务端算完） | 纯下载 | 下载速率 |
|---|---|---|---|---|
| 100 | 2.08 MB | 0.86s | 1.77s | 1.17 MB/s |
| 300 | 6.21 MB | 1.07s | 6.72s | 0.92 MB/s |
| 600 | 12.45 MB | 1.87s | 12.33s | 1.01 MB/s |

服务端**算完只要约 1 秒**，剩下全是下载。

### 2.5 TPM 实测：从未接近配额

| 场景 | 实测发送速率 | 占 500K TPM（免费档） |
|---|---|---|
| 并发 1（30 请求 × 3400 tok） | **46 K tok/min** | 9% |
| 并发 2 | 48 K tok/min | 10% |
| 并发 4 | **53 K tok/min** | 11% |

**并发不提高 token 速率**（~50K tok/min 恒定）——因为瓶颈在下载响应体，不在发送。
所以"靠并发吃满 TPM"在本机不成立。

### 2.6 并发安全边界（实测，关键）

| conc | leveldb | HelloAgents | langchain |
|---|---|---|---|
| 1 | ✓ 52.7s | ✓ 83.9s | ✓ 589.3s |
| **3** | ✓ 28.5s | ✓ 44.7s | **✗ 429** |

**并发 3 在大仓库上整次失败**：`ApiRateLimitError: TPM limit reached`，退避重试 2 次后抛出，
**无部分成功语义（vectors 全丢）**。根因是**瞬时尖峰**而非平均速率：单批 75000 token，
3 批同打 ≈225K token 撞窗。

**结论：免费 bge-m3 档位 `concurrency=1` 是唯一可保证成功的配置；conc=2 仅限中小仓库试。**

## 3. 规模 → 耗时换算表

| 档 | chunks | 本机 company-wsl（~1 MB/s） | VPS（10 MB/s，**待实测**） |
|---|---|---|---|
| 小 (<2K) | 1.9K | 40s | ~5s |
| 中 (~3K) | 2.7K | 58s | ~7s |
| 大 (~20K) | 20.7K | 440s | ~46s |
| 极大 (~100K) | 100K | ~35 min | ~3.5 min |

> VPS 列是按同一公式的**外推**（bandwidth ÷10 → 耗时 ÷10），**尚未实测**。
> 待实测项见 §5。

## 4. 被实测推翻的两个直觉（重要）

| 直觉 | 实测结果 | 原因 |
|---|---|---|
| "调小 `max_input_tokens=2048` 能省时间" | ❌ **省不到 3% token，耗时反而略慢**（111.6s vs 109.4s） | 响应体 = chunk 数 × 维度，与输入长度无关 |
| "并发 3 能提速 3×" | ❌ 小仓库仅 1.85×；**大仓库直接 429 失败** | 带宽上限 ~1 MB/s；并发 3 触发 TPM 尖峰 |

## 5. 未来优化空间（三条，按实测收益排序）

| 手段 | 实测/推算收益 | 状态 | 代价 |
|---|---|---|---|
| **① 降维**（1024→256） | 响应体 ÷4 → 大仓库 440s→110s | **需先开卡**：`output_dimension` 仅登记未接线（无 env、无消费方） | **改变向量空间** → 触发 D-07 全量重嵌；检索质量需评估 |
| **② 调整 chunk 数量**（更大切片） | 线性减少（chunk 数 ÷2 → 耗时 ÷2） | 未实测 | 检索粒度变粗，正撞 D-02 的切片设计 |
| **③ 网络（仅两种部署形态）** | 线性减少 | **VPS 侧待实测** | — |
| ~~④ 换 16M TPM 模型（Voyage）~~ | **仅约 1.28×** | 已推算 | 75% 时间是下载向量，换模型躲不掉 |

### ③ 网络：只有两种形态

| 形态 | 用途 | 实测带宽 | 状态 |
|---|---|---|---|
| **公司 WSL（company-wsl）** | 用户开发 | **~1 MB/s**（本文件全部数字） | ✅ 已实测 |
| **VPS 网络** | 公测 | 目标 10 MB/s | ⏳ **待实测**（用户计划） |

> 代理 vs 直连已实测**无差异**（同为 ~0.78 MB/s），瓶颈在本机出口链路，不在代理软件。
> 换链路（如公司直连 / 更快出口）是唯一不牺牲检索质量、也不改切片的提速手段。

## 6. 建议配置（company-wsl，实测支撑）

```bash
# 免费 bge-m3 安全档（推荐）
EMBED_CONCURRENCY=1               # 唯一保证不 429 的档位
EMBED_MODEL=bge-m3
EMBED_BASE_URL=https://api.siliconflow.cn
# EMBED_MAX_INPUT_TOKENS 保持默认 8192（实测调小无收益）
```

**两条纪律**：
1. **单 key 独占**（实测：两进程共用 key 会互相抢配额，表现为远低于配额就 429）；
2. **大仓库不要开并发**（langchain conc=3 必失败）。

## 7. 复现命令

```bash
cd <zace checkout>
export HF_ENDPOINT=https://hf-mirror.com NO_PROXY=127.0.0.1,localhost
set -a; source .env; set +a
export EMBED_MODE=api EMBED_MODEL=bge-m3 EMBED_BASE_URL=https://api.siliconflow.cn

# ① 画像（免 API，秒级）
uv run python benches/embed-bench/profile_repo.py \
  --repo /home/xuwenzheng/2_github/AI/ACE/benchmark/langchain --out /tmp/profile.json

# ② 吞吐矩阵（需 key，注意配额）
uv run python benches/embed-bench/throughput_probe.py \
  --repo /home/xuwenzheng/2_github/AI/ACE/benchmark/langchain \
  --sample 4000 --concurrency 1 --max-input-tokens 8192 --out /tmp/throughput.json

# ③ 端到端（三靶场 × 三配置，串行）
bash benches/embed-bench/run_targets.sh run1
```

## 8. VPS 验证清单（交接给 VPS 侧 AI）

> 目的：把本文 §3 的**外推列换成实测列**，并验证"耗时 ∝ 响应体字节/带宽"这一模型是否跨机器成立。
> 预期：若模型成立，VPS 上耗时 ≈ 本机耗时 × (1 / 带宽倍数)，即 10 MB/s → **约本机的 1/10**。

### 8.1 前置检查（3 条，缺一不可）

```bash
# ① 单 key 独占（最重要：共用 key 会互相抢配额，表现为远低于配额就 429）
pgrep -af "zace-core|ingest|pytest" || echo "独占 OK"

# ② 记录设备指纹（绑进报告，VPS 与 company-wsl 的数据不能混）
nproc; free -g | head -2; uname -r

# ③ 记录实际带宽（本模型的自变量，必须单独测）
#    用固定 500 条探测，读 MB/s 与 TTFB；这是与 company-wsl 对比的关键数字
```

### 8.2 三档靶场（**必须与本机同 commit**，否则不可比）

| 档 | 仓库 | commit | chunks | 本机实测（conc=1） | VPS 预期（@10MB/s） |
|---|---|---|---|---|---|
| 小 | `leveldb` | `7ee830d` | 1,898 | 52.7s | ~5s |
| 中 | `HelloAgents` | `93e77ea` | 2,729 | 83.9s | ~8s |
| 大 | `langchain` | `41d3572` | 20,673 | 589.3s | ~59s |

若 VPS 上没有这三个 checkout，可用**任意仓库**先验证模型（见 8.4 的判定式）。

### 8.3 执行（复用本卡脚本，三个入口）

```bash
cd <zace checkout，需含本卡提交>
export HF_ENDPOINT=https://hf-mirror.com NO_PROXY=127.0.0.1,localhost
set -a; source .env; set +a
export EMBED_MODE=api EMBED_MODEL=bge-m3 EMBED_BASE_URL=https://api.siliconflow.cn

# ① 画像（免 API）：确认 chunk 数与 token 数一致 —— 跨机器这两个数**必须完全相同**
uv run python benches/embed-bench/profile_repo.py --repo <路径> --out /tmp/prof.json

# ② 吞吐标定（需 key）：只需跑 conc=1，重点看 response_MB_per_s
uv run python benches/embed-bench/throughput_probe.py --repo <路径> \
  --sample 4000 --concurrency 1 --out /tmp/thr.json

# ③ 端到端（本卡靶场驱动；BENCH_ROOT 指向 VPS 上的三个 checkout）
BENCH_ROOT=<三个仓库的父目录> bash benches/embed-bench/run_targets.sh vps1
```

### 8.4 判定标准（模型成立 / 不成立）

| 项 | 期望值 | 若不成立说明 |
|---|---|---|
| `chunks` / `tokens`（画像） | **与本机逐位相同** | 解析口径有差异 → 先修口径再比耗时 |
| `response_mb`（吞吐） | **与本机逐位相同** | 维度或 chunk 数不同 → 同上 |
| `response_MB_per_s` | ≈ VPS 链路带宽（本机 0.76–1.01） | 这是**关键对比数**，直接给出带宽倍数 |
| `elapsed` | ≈ 本机耗时 ÷ 带宽倍数（±20%） | 偏差大 → 说明除下载外还有别的项（如 TTFB 占比变高） |
| `status_counts` | 全 200 | 出现 429 → 记录 conc 与仓库规模，作为边界证据 |

### 8.5 回报格式（最小集）

```text
设备：<VPS 规格 / 内核 / 带宽实测>
靶场 commit：<三个 hash>
conc=1 端到端：leveldb __s / HelloAgents __s / langchain __s
响应体速率：__ MB/s（本机为 0.76–1.01）
chunks 是否一致：是/否
429 情况：无 / 有（记录 conc 与仓库）
结论：模型成立 / 不成立（附偏差最大的那一项）
```

### 8.6 建议顺便验证的两项

1. **并发上限**：本机 conc=3 在 langchain 上 429，VPS 链路更快 → **是否也 429** 很关键
   （若是，说明 429 由**请求节奏**触发而非带宽；若否，说明本机并发受限有带宽因素）；
2. **降维（256 维）——注意：当前代码不支持，需先开卡**。
   `ApiModelSpec.output_dimension` 只是 `registry.py:116` 的**登记字段，无任何代码消费**，
   也没有 `EMBED_OUTPUT_DIMENSION` 环境变量（2026-09-15 核实：`rg output_dimension core/ service/` 只命中该定义）。
   要实测降维，必须先给 provider 加"请求体带 `output_dimension`"的支持（属 TASK-049 遗留项）。
   若将来做了，可同时拿到"提速倍数"与"响应体是否整除 4"两个数字。

## 9. 未决问题

1. **VPS 10 MB/s 待实测**：需在目标 VPS 上重跑 §7，把 §3 的外推列替换成实测列；
2. **降维质量代价未评估**：需用 golden 集对比 1024 vs 256 的 recall@5；
3. **chunk 数量调整未做**：与 D-02 切片设计相关，需架构评审；
4. **`max_input_tokens=2048` 的取舍**：对耗时无收益，但可能对**检索质量**有影响（减少长 chunk 截断噪声）——
   属另一维度，需 golden 评估，不能用"提速"作理由；
5. **D-05 的设计口径需更新**：Module/01 §2.4 写的是"embedding 截断 2048 token"，
   而实测 2048 既不省时间也不是当前生效值（实际受 `EMBEDDING_BODY_MAX_CHARS=8000` 字符上界约束）。
   **按 AGENTS.md §2，此偏差不改设计文档，交编排者裁决。**
