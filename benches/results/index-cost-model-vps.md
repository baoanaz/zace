# 索引基线：设备绑定基准（VPS / voyage-4-lite）

> 状态：**已实测**（2026-09-15）｜设备标识：**`vps-la-2c2g`**（洛杉矶 2 vCPU / 1.9 GiB VPS，
> 内核 5.15.0-191-generic）｜本文件所有数字**只对该设备与本档配置成立**。
> 姊妹文档：`index-cost-model-company-wsl.md`（公司 WSL / 硅基流动 bge-m3）。
> 靶场：`/root/xuwenzheng/ACE/benchmark/{leveldb,HelloAgents,langchain}`
> 原始证据：`benches/results/raw/ingest-vps/*.json`（每次 ingest 的计量）、
> `raw/ingest-vps-phases/*.json`（同配置的阶段分解复现）、`raw/local-only-vps.json`（零网络地板）、
> `raw/ttfb-vps.json`（单请求 TTFB 分解）、`raw/throughput-vps-*.json`（带宽标定）、
> `raw/repo-profile-vps.json`（画像）
> 复现入口：`bash benches/embed-bench/build_indexes.sh --dry-run`

## 0. 一句话结论

> **冷启动 ≈ 本地 CPU（2/3）+ 网络（1/3）——瓶颈是这台机器的 CPU，不是带宽。**
> 网络侧另有硬上限：这条链路（裸链路 11.6 MB/s、API 聚合实测 9.2 MB/s）**永远喂不满 16 M TPM**，
> 因为配额要求 ~18.5 MB/s 的持续下行（§3.2）。内存是唯一风险项（§4）。

四条与 WSL 侧不同的实测事实：

1. **冷启动耗时归因（§3.1）**：三个靶场都是「本地 64–70% + 网络 26–36%」，两段近似串行叠加；
   langchain 用零网络替身 provider 的**纯本地耗时 84.6s**，而原生 ingest 是 115.9s；
2. **单向量响应 12.46 KB**（WSL 硅基流动是 20.76 KB）——Voyage 的 JSON 浮点位数更少，
   同样 chunk 数**响应体只有 WSL 的 60%**；
3. **TPM/RPM 用不满是结构性的**：langchain 峰值 3.66 M tok/min（嵌入窗口口径，配额 23%）、
   64 RPM（配额 2000 RPM 的 3%）；加大并发也不是解法——链路聚合 ~9 MB/s 就饱和（§3.3）、
   本机 2 vCPU 也吃不下更多窗口（§3.2 / §4.2）；
4. **内存是唯一风险项**：修复前 langchain 单次 ingest 峰值 ~1.5 GB，直接把这台 2 GiB 机器
   拖到失联（2026-09-15 04:06 事故）；修复后 928 MB / 115.9s。详见 §4。

> **口径提醒**：留档里还能看到 137.6s / 141.9s 两个墙钟，那是**计量探针**（`ingest_probe.py`）的值——
> 探针自己会按 bge-m3 口径 tokenize 全量 chunk，多 ~21.7s。**不是另一台机器，也不是优化前**。三者关系见 §3.0。

## 1. 五项留档指标（用户 2026-09-15 要求）

前置口径：`voyage-4-lite` / 1024 维 / `batch=500` / `budget=300000` / `maxTok=32000` /
`EMBED_CONCURRENCY=4`（该机器建议值，理由见 §4）；TPM 配额 **16,000,000 TPM / 2,000 RPM**（账号档位，由用户提供）。

| 靶场 | commit | **Chunks** | **Total Tokens**（bge-m3 口径） | Total Tokens（API 计费） | **TPM**（网络在飞 / 嵌入窗口） | **Response MB**（实测） | **API→VPS MB/s**（网络在飞口径） |
|---|---|---|---|---|---|---|---|
| `leveldb` | `7ee830d` | 1,898 | 260,328 | 207,083 | **4.13 M / 2.82 M** | 23.09 MB | **7.68** |
| `HelloAgents` | `93e77ea` | 2,729 | 894,705 | 738,653 | **8.74 M / 4.67 M** | 33.21 MB | **6.54** |
| `langchain` | `41d3572` | 20,673 | 4,725,916 | 3,634,688 | **5.89 M / 3.66 M** | 251.52 MB | **6.79** |

补充口径：

- **Chunks / Total Tokens 与 company-wsl 逐位相同**（1,898 / 2,729 / 20,673；260,328 / 894,705 /
  4,725,916）——跨机器一致性成立，解析与切分口径没有漂移；
- **API 计费 token 比 bge-m3 口径少 20–21%**（Voyage tokenizer 与 XLM-R 词表不同），
  计费按 API 口径、跨机器对照按 bge-m3 口径，两者**不要混用**；
- `Response MB` 是 provider 侧实测响应字节（`12.46 KB/chunk`，三个仓库一致）；
- `API→VPS MB/s` = 响应字节 ÷ **网络在飞时间并集**（`network_busy_s`：至少有一个请求在飞的
  墙钟并集，并发下不重复计时）。**早期版本此处曾用「÷ 嵌入窗口」口径**（结果 5.25 / 3.50 / 4.22），
  该口径把同一窗口内的 `upsert` 与批次准备时间也算进了分母，会系统性低估速率，**已作废**；
- `TPM（网络在飞 / 嵌入窗口）`：前者 = API 计费 token ÷ `network_busy_s`（回答"API 忙的时候跑多快"），
  后者 = ÷ 嵌入窗口墙钟（与 WSL 报告可比）。整段墙钟摊平则更低——详见 §3.2；
- 全部请求 `HTTP 200`，**无 429**。

## 2. 持久索引产物（本机未来测试的唯一索引来源）

数据根按「模型-维度」分目录：`/root/.zace/bench/voyage-4-lite-d1024/`。
**换模型或换维度即换数据根**，互不污染，也不会因指纹不符触发 D-07 重嵌。

| 靶场 | projectId | 索引目录 | 体积 | 内容 |
|---|---|---|---|---|
| `leveldb` | `3ed886ce58bc0e47` | `projects/3ed886ce58bc0e47` | 13 MB | 1,898 chunk / 1,556 symbol / 3,009 edge |
| `HelloAgents` | `06078cc80c7ce7d7` | `projects/06078cc80c7ce7d7` | 28 MB | 2,729 chunk / 1,082 symbol / 7,242 edge |
| `langchain` | `ca2050db0db5b1e2` | `projects/ca2050db0db5b1e2` | 179 MB | 20,673 chunk / 15,735 symbol / 71,330 edge |

三个索引的 embedding 指纹一致：`api:voyage-4-lite@1024`，`parser_config_hash=76741bca6f8e…`。
> **遗留目录**：`~/.zace/bench/projects/`（扁平布局，179 MB）里是更早建的 `zace` dogfood（`adfdd1a626db62b7`）
> 与 `datawhalechina/hello-agents`（`e9ee9dd1d41a7d2c`）两个索引，配置同为 1024 维 voyage。
> 它们**不在本次三靶场范围内**，未迁移（迁移会牵动 `benches/README.md` / `targets.json` 里
> `--data ~/.zace/bench` 的既有说明）；要统一成「模型-维度」分目录时再整体搬迁即可。
**projectId 只由 D-29 身份（git remote + 仓库内相对路径）决定**，因此换 checkout 路径不变。

复用（**不索引、不重嵌**，仅查询向量走一次 API）：

```bash
uv run zace-core search "<query>" \
  --project-id ca2050db0db5b1e2 \
  --repo /root/xuwenzheng/ACE/benchmark/langchain \
  --data /root/.zace/bench/voyage-4-lite-d1024
```

**"不再索引"的实测证据**（`raw/ingest-vps/reuse-*.json`）：对已建索引重跑增量 ingest，
`chunks_new=0`、`requests_embeddings=0`、`api_total_tokens=0`（leveldb 0.2s / langchain 3.8s，
后者耗时全部是 2,950 个文件的哈希扫描）。

## 3. 墙钟与内存（原生 CLI，`/usr/bin/time -v`）

| 靶场 | ingest 墙钟 | 峰值 RSS | 其中嵌入窗口 | 备注 |
|---|---|---|---|---|
| `leveldb` | 8.9s | 504.6 MB | 4.4s | 整仓不足一个窗口（被单次窗口覆盖） |
| `HelloAgents` | 16.9s | 554.9 MB | 9.5s | — |
| `langchain` | 115.9s | **928.0 MB** | 59.6s | 修复前约 1.5 GB（外推），见 §4 |

- 进程空载基线只有 **129 MB**（裸解释器 28 MB + 向量/解析依赖）；小仓库也要 500 MB，
  说明大头是**索引期的向量副本 + 入库缓冲**，不是解释器；
- `ingest 墙钟 − 嵌入窗口` 是解析/切分/入库/建图（langchain 约 56s，占 48%——比 WSL 侧
  占比高，因为这台机器只有 2 vCPU）；
- 计量脚本 `benches/embed-bench/ingest_probe.py` 会按 bge-m3 口径逐条数 token，
  峰值比原生 CLI 高约 270 MB（leveldb：774.6 MB vs 504.6 MB），**留档峰值请用 CLI 口径**。

### 3.0 三个"总时间"口径（引用前先对齐，别混用）

同一台机器、同一份 langchain 索引，留档里出现过 3 个墙钟数字：

| 口径 | langchain 墙钟 | 出处 | 组成 |
|---|---|---|---|
| **原生 CLI** `zace-core ingest`（**引用默认用这个**） | **115.9s** / 928 MB | §1/§2 留档值 | 84.6s 本地 + 37.1s 网络在飞（−5.7s 重叠残差，§3.1） |
| 计量探针 `ingest_probe.py` | 137.6s / 1.18 GB | `raw/ingest-vps/langchain.json` | 同上 + **~21.7s 探针自身开销** |
| 计量探针（阶段分解复跑） | 141.9s / 1.21 GB | `raw/ingest-vps-phases/langchain.json` | 同上 + 同机复跑抖动 3~4s |

探针开销不是噪声，是**探针真的在数 token**：它按 bge-m3 口径逐条 tokenize 全量 chunk ≈ **4.5 µs/token**，
三靶场线性吻合（0.26M → +1.2s；0.89M → +4.1s；4.73M → +21.7s，`raw/ingest-vps/INDEXES.json` 同时记了 CLI 与探针两套值）。

- 引用 **"冷启动多久 / 能不能接受"** → 用 `115.9s`（原生 CLI）；
- 引用 **阶段比例（本地 vs 网络）** → 用探针口径（比例本身不受探针开销影响，仍 70/30）；
- 引用 **内存** → 用 CLI 口径 928 MB；探针口径 1.21 GB 含 tokenizer 与计量包装。

### 3.1 冷启动阶段分解：本地 ≈ 2/3，网络 ≈ 1/3

用户问题（2026-09-15）："langchain 冷启动偏久，和什么有关，瓶颈是网速吗？"——
用两组独立对照回答（`raw/local-only-vps.json` / `raw/ingest-vps-phases/*.json`）：

- **纯本地**：把 provider 换成**零网络、零计算**的替身（`benches/embed-bench/local_only_probe.py`，
  直接返回零向量），量的是「解析 + 切分 + SQLite/FTS + 建图 + 向量入库」；
- **网络在飞**：`ingest_probe.py` 的 `network_busy_s`（所有请求在飞区间的**并集**）。

| 靶场 | 原生 ingest 墙钟 | 纯本地下限 | 网络在飞 | 本地占比 | 每 chunk 本地 | 每 chunk 网络 |
|---|---|---|---|---|---|---|
| `leveldb` | 8.9s | 5.4s | 3.0s | 64% | 2.8 ms | 1.6 ms |
| `HelloAgents` | 16.9s | 11.3s | 5.1s | 69% | 4.2 ms | 1.9 ms |
| `langchain` | 115.9s | **84.6s** | **37.1s** | **70%** | **4.1 ms** | **1.8 ms** |

- 「本地 + 网络」比原生墙钟高 3–6%（8.4 / 16.4 / 121.6 vs 8.9 / 16.9 / 115.9），
  说明两段**近似串行叠加**：当前实现是「窗口 N 嵌入 → 窗口 N 入库 → 窗口 N+1 解析/切分」，
  本地算的时候网络闲着，网络在飞时 CPU 基本只等；
- 所以**"瓶颈是网速吗"的答案是否定的**：即使 API 瞬时返回，langchain 冷启动仍要 ~85s；
  反之若本地瞬时完成，仍需 ~37s（251.52 MB ÷ 实测聚合 6.8 MB/s）；
- 纯本地下限**不含** API provider 的 `_prepare`（逐 chunk tokenizer 截断 + 预算分批）与
  响应体 JSON 解码，因此真实本地开销 ≥ 该值，**本地占比只会更高**；
- 两段的单位成本都随 chunk 数线性（本地 ~4 ms/chunk、网络 ~1.8 ms/chunk），与仓库大小无关；
  大仓库"久"是因为 chunk 多，不是因为网络差。

### 3.2 为什么 TPM 只跑到 23%（不是"并发没开够"）

先把口径说清（langchain，API 计费 3,634,688 token / 64 请求 / 251.52 MB）：

| 分母 | 折算 TPM | 占 16 M 配额 |
|---|---|---|
| 网络在飞 37.05s | **5.89 M tok/min** | 37% |
| 嵌入窗口 59.6s（§1 / WSL 可比口径） | **3.66 M tok/min** | **23%** |
| 整段墙钟 115.9s（原生 CLI） | 1.88 M tok/min | 12% |

三个数字的差就是答案：**API 只有 1/3 的时间在跑**（langchain 网络在飞 37.1s / 墙钟 115.9s，
其余 2/3 是 §3.1 的本地串行段），而"跑起来"的时段里也只到 37%——因为下面这条**结构性上限**：

| 目标速率 | 需要的持续下行 | 实测可能 |
|---|---|---|
| 16 M TPM（配额跑满） | **18.5 MB/s** | ✗ 见下 |
| 本机裸链路（Cloudflare 测速 11.57 MB/s） | — | 10.0 M TPM（**63%**） |
| API 聚合下载上限（conc=4/8：8.88 / 9.23 MB/s，§3.3） | — | 8.0 M TPM（**50%**） |
| langchain ingest 实际（6.79 MB/s） | — | 5.9 M TPM（**37%**） |

换算用的是实测值：`12.46 KB/chunk`（响应体）与 `175.8 token/chunk`（API 计费），
即 **1 MB 响应体 ≈ 14,446 token**。结论：

> **在 `voyage-4-lite` 的响应体格式下，跑满 16 M TPM 需要 18.5 MB/s 的持续下行，
> 而这台 VPS 的链路物理上限只有 9.2–11.6 MB/s——TPM 配额在这台机器上永远用不满，
> 与限流无关（全程无 429）。**

RPM 同理：langchain 全程只有 64 个请求（500 条/批的下限），最短 60s 窗口内 ~64 RPM = 配额的 **3%**。

**"加大并发"为什么不是解法**（两组独立实测）：

- **网络侧**：并发 1 → 4 → 8，聚合只有 4.97 → 8.88 → **9.23 MB/s** 就饱和，
  单连接速率反而从 11.32 掉到 1.86 MB/s、TTFB 从 0.66s 涨到 1.41s（§3.3）——共享同一条出口；
- **本地侧**：`raw/throughput-vps-conc-scan.json` 里 conc=4 / 8 / 32 的嵌入阶段吞吐都在
  4.46–4.48 MB/s，conc=16 因为 2 vCPU 争抢反而掉到 1.06 MB/s；再加上窗口 = 批大小 × 并发，
  并发翻倍会让峰值内存翻倍（§4.2）——**这台机器上并发 4 已是甜点**。
- **4 → 8 的账（langchain 口径，全部来自已有实测，未新增跑批）**：

  | 项 | conc=4（当前） | conc=8 | 差 |
  |---|---|---|---|
  | 网络在飞 / 聚合吞吐 | 8.88 MB/s | 9.23 MB/s | **+3.9%** |
  | langchain 网络段 | 37.05s | 35.7s（外推） | **−1.4s** |
  | 整仓墙钟 | 141.9s | ~140.5s | **−1%** |
  | TPM（网络在飞口径） | 5.89 M（37%） | 6.13 M（38%） | +1 pt |
  | 嵌入窗口 | 2,000 chunk | 4,000 chunk | ×2 |
  | 峰值 RSS | 928 MB / 1.21 GB（探针口径） | **~1.19 GB 且 7 分钟未完成**（§4.2） | 不可用 |

  代价这一栏的机理：窗口 = 批大小 × 并发，常驻向量 `窗口 × 33 KB`；
  纯本地地板（零网络替身 provider）langchain 峰值 502.8 MB（`raw/local-only-vps.json`），
  即"网络在飞"那部分约 700 MB / 4 个槽 ≈ **175 MB 每个并发槽**，
  推到 8 槽外推 ~1.9 GB ≈ 整机内存 —— 这就是 §4.1 失联事故的配方。

### 3.3 TTFB 分解：一个连接就能吃满出口，聚合在 9 MB/s 饱和

`benches/embed-bench/ttfb_probe.py`（WSL 报告 §2.4 的 VPS 对应物）：
同一份 langchain chunk 文本、每档 8 个 500 条批量请求、流式读取，
**只调 `/v1/embeddings`、不落盘、不建索引**（`raw/ttfb-vps.json`）：

| 并发 | 聚合 MB/s | TTFB 中位（服务端算完） | 纯下载中位 | 单连接中位 |
|---|---|---|---|---|
| 1 | 4.97 | 0.66s | 0.54s | **11.32 MB/s** |
| 4 | 8.88 | 0.82s | 1.29s | 4.75 MB/s |
| 8 | **9.23** | 1.41s | 3.26s | 1.86 MB/s |

- **单连接**纯下载 11.32 MB/s ≈ 裸链路 11.57 MB/s → 一个连接就能吃满出口，本机不是慢的一端；
- **聚合**在 ~9 MB/s 饱和：加并发只是把同一条管子的速率摊薄，并把排队时间变成 TTFB；
- 服务端算完（TTFB 0.66–1.41s / 6.4 MB 响应）不是主导项；WSL 侧形态正好相反
  （TTFB 1.87s、纯下载 12.33s，带宽是瓶颈）；
- 所以本机**网络侧的硬上限 ≈ 11.6 MB/s（单连接）/ 9.2 MB/s（多连接聚合）**，
  这是 §3.2 里"TPM 跑不满"的直接原因。

## 4. 内存：这台机器的真实约束（含 2026-09-15 事故）

### 4.1 事故与根因

2026-09-15 04:06，`langchain` 首次 ingest 把机器拖到失联（journal 无 OOM 记录、直接断，
属内存耗尽 + 换页抖动的硬重启；04:14 恢复）。根因在代码形态，不在网络/配额：

- `Indexer._embed_and_upsert()` 把**整仓 chunk** 一次性交给 `embed()`，随后又 `list(vector)`
  复制成 `VectorRow`，`VectorStore.upsert()` 内部再复制一份 → 1024 维向量在 CPython 里
  约 33 KB/条（24 B/float + 8 B/指针 + 列表头），20,673 chunk **仅向量就 ~1 GB、复制后 ~1.4 GB**；
- 本机 1.9 GiB，其他常驻服务已占 ~0.4–0.8 GB → 必然触发换页乃至失联；
- WSL 那台 15.6 GiB 从未暴露该问题。

### 4.2 修复（`core/zace_core/pipeline/indexer.py`）

向量阶段按**窗口**分批：`窗口 = 批大小 × 并发`（并用 `MAX_EMBED_WINDOW=4000` 封顶），
逐窗 `embed + upsert`。窗口取「批大小 × 并发」是为了**刚好跑满一轮并发**——既不牺牲吞吐，
又把常驻向量压到 `窗口 × 33 KB`（实测 conc=4 → 窗口 2000 → 峰值降到 928 MB）。

| 配置 | 窗口 | langchain 峰值 RSS | 结果 |
|---|---|---|---|
| 修复前（单次全量） | 20,673 | ~1.5 GB（外推） | 机器失联 |
| 修复后 conc=8 | 4,000 | ~1.19 GB（探针口径，触发 cgroup 回收，7 分钟未完） | 过慢，弃用 |
| **修复后 conc=4** | **2,000** | **928 MB（CLI 口径）** | **115.9s 完成，swap 无增长** |

**本机建议 `EMBED_CONCURRENCY=4`**（不是 registry 默认的 8）：吞吐几乎无损
（标定：conc=4 → 4.46 MB/s，conc=8 → 4.48 MB/s，见 `raw/throughput-vps-conc-scan.json`），
但窗口减半、峰值降 ~250 MB。这是"配置项"，不是代码默认值——换更大内存的机器可回调到 8。

### 4.3 运行纪律（避免再次失联）

```bash
systemd-run --scope --quiet -p MemoryHigh=1200M -p MemoryMax=1500M -p MemorySwapMax=512M -- \
  timeout 7200 uv run python benches/embed-bench/ingest_probe.py ...
```

- `MemoryMax` 是**保命线**：真出事只杀索引进程，不拖死机器；
- `MemoryHigh` 不要设太低（设 700M 时 cgroup 回收会让 langchain 7 分钟跑不完）；
- 建索引前先 `free -m`：本机可用内存 < 1 GB 时先把并发降到 2。

## 5. 带宽标定（与 WSL 的对照）

| 口径 | company-wsl | vps-la-2c2g |
|---|---|---|
| 单向量响应 | 20.76 KB（bge-m3） | **12.46 KB（voyage-4-lite）** |
| 裸链路下载 | ~1 MB/s（出口受限） | **11.57 MB/s**（Cloudflare 测速）／11.32 MB/s（API 单连接，§3.3） |
| 嵌入响应实测 | 0.76–1.01 MB/s | **6.54–7.68 MB/s**（网络在飞口径，conc=4） |
| 网络侧上限（多连接聚合） | 1 MB/s 即上限 | **9.23 MB/s**（conc=8，§3.3） |
| langchain 冷启动 | 589.3s（conc=1，bge-m3） | **115.9s（conc=4，voyage）= 本地 84.6s + 网络 37.1s** |
| TPM 实耗 / 配额 | ~10% | 23%（嵌入窗口口径）／37%（网络在飞口径，§3.2） |
| 429 | conc=3 起在 langchain 上出现 | **无**（conc 4/8/16/32 全部 200） |

结论：**WSL 报告的核心结论"耗时 ∝ 响应体 ÷ 带宽"在 VPS 上不再成立**——
WSL 那台 1 MB/s 的出口是唯一瓶颈；VPS 这边网络只占 1/3 墙钟，实测速率（6.5–7.7 MB/s）
离链路上限（9.2–11.6 MB/s）还有余量，**约束换成了 2 vCPU 的本地处理能力（§3.1）与内存（§4）**。
跨机器唯一仍然通用的部分是"响应体 = chunk 数 × 单向量大小"这一项：
1024 维下 12.46 KB/chunk，降维到 512/256 能让网络与入库**同时**减半（见 §7）。

## 6. 复现 / 复用

```bash
# 只查看要建什么、建到哪（不调用 API）
bash benches/embed-bench/build_indexes.sh --dry-run

# 缺哪个建哪个；已建的直接跳过（"不再索引"由脚本强制）
bash benches/embed-bench/build_indexes.sh

# 单仓库 / 强制重建 / 换并发
BENCH_REPOS=langchain EMBED_CONCURRENCY=4 bash benches/embed-bench/build_indexes.sh
bash benches/embed-bench/build_indexes.sh --force

# §3.2/§3.3 的两个分测量（都不写索引、都是只读的 API 调用）
uv run python benches/embed-bench/ttfb_probe.py --repo /root/xuwenzheng/ACE/benchmark/langchain \
  --requests 8 --concurrency 1 --concurrency 4 --concurrency 8 --out benches/results/raw/ttfb-vps.json
uv run python benches/embed-bench/local_only_probe.py --repo /root/xuwenzheng/ACE/benchmark/langchain \
  --data "$(mktemp -d)" --out benches/results/raw/local-only-vps.json   # 零网络，免费
```

配置项与默认值（env 覆盖，脚本不写死）：`EMBED_MODEL=voyage-4-lite`、
`EMBED_CONCURRENCY=8`（本机建议 4）、`EMBED_BATCH_SIZE=500`、`EMBED_BATCH_TOKEN_BUDGET=300000`、
`EMBED_MAX_INPUT_TOKENS=32000`、`ZACE_BENCH_ROOT=~/.zace/bench`。
**Chunk 策略按当前实现默认口径，不提供开关**（改切片规则属 core 变更，会触发 `full_reparse`）。

## 7. 未决与建议

1. **无 golden 用例**：三个靶场只测了索引耗时，未测检索质量；要回归质量需按
   `benches/README.md` 的 JSONL 格式出题（`expected[].path` 用仓库相对路径）；
2. **未进 `targets.json`**：该文件的 schema 要求 `golden` 字段，三靶场暂无用例集，故登记在本文件；
3. **本地/网络流水线（本轮最大的单点优化机会）**：先纠一个常见误读——**这台机器的现行上限不是 141s**：
   141.9s 是探针口径（含 21.7s 计量开销），**不动 core 的前提下的现行数字是 115.9s**，
   而本地零网络地板是 84.6s（§3.1）⇒ 所以还能动的只有"让本地和网络重叠"。
   §3.1 显示两段严格串行叠加——
   窗口 N 在飞时，CPU 只在等网络；窗口 N+1 解析/切分时，网络完全空闲。
   若把"下一批解析/切分/入库"与"当前窗口在飞"重叠，langchain 的理论墙钟从 115.9s 降到
   `max(84.6, 37.1) ≈ 86s`（**−26%**）；代价是内存峰值上升，本机需先把窗口调小并挂 `MemoryMax` 保护；
4. **本地开销未再细分**：84.6s 里有多少是 API provider 的 `_prepare`（逐 chunk tokenizer 截断 + 预算分批）、
   多少是响应体 JSON 解码、多少是 SQLite/FTS/建图，本轮未单独计时。要继续压本地就得先拆这三项；
5. **降维（256/512 维）未实测**：当前代码不支持 `output_dimension`（详见 WSL 报告 §8.6）；
   若实现，本机收益是响应体减半 → 网络与入库同时减半（本地解析部分不变），
   对"网络 + 内存"两项都有效；
6. **`upsert` 的第三份复制仍可省**（`VectorStore.upsert` 内部 `[float(v) for v in row.vector]`），
   属可选优化，未在本轮改动范围内；
7. **旁证**：`warp-svc` 历史上会涨到 670–805 MB 并被 OOM（`/root/xuwenzheng/OOM-optimization-2026-09-01.md`），
   与本轮索引无关，但它是本机内存预算里最大的一块不确定项。
