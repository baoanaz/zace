# 索引基线：设备绑定基准（VPS / voyage-4-lite）

> 状态：**已实测**（2026-09-15）｜设备标识：**`vps-la-2c2g`**（洛杉矶 2 vCPU / 1.9 GiB VPS，
> 内核 5.15.0-191-generic）｜本文件所有数字**只对该设备与本档配置成立**。
> 姊妹文档：`index-cost-model-company-wsl.md`（公司 WSL / 硅基流动 bge-m3）。
> 靶场：`/root/xuwenzheng/ACE/benchmark/{leveldb,HelloAgents,langchain}`
> 原始证据：`benches/results/raw/ingest-vps/*.json`（每次 ingest 的计量）、
> `raw/throughput-vps-*.json`（带宽标定）、`raw/repo-profile-vps.json`（画像）
> 复现入口：`bash benches/embed-bench/build_indexes.sh --dry-run`

## 0. 一句话结论

> **VPS 上耗时 ∝ 响应体 ÷ 带宽（4.2–5.3 MB/s），实测带宽只用到裸链路（11.6 MB/s）的 4 成；
> 真正的硬约束是内存，不是 TPM、也不是链路。**

三条与 WSL 侧不同的实测事实：

1. **单向量响应 12.46 KB**（WSL 硅基流动是 20.76 KB）——Voyage 的 JSON 浮点位数更少，
   同样 chunk 数**响应体只有 WSL 的 60%**；
2. **TPM/RPM 远未成为瓶颈**：langchain 峰值 3.66 M tok/min（配额 16 M TPM 的 23%）、
   64 RPM（配额 2000 RPM 的 3%）；
3. **内存是唯一风险项**：修复前 langchain 单次 ingest 峰值 ~1.5 GB，直接把这台 2 GiB 机器
   拖到失联（2026-09-15 04:06 事故）；修复后 928 MB / 115.9s。详见 §4。

## 1. 五项留档指标（用户 2026-09-15 要求）

前置口径：`voyage-4-lite` / 1024 维 / `batch=500` / `budget=300000` / `maxTok=32000` /
`EMBED_CONCURRENCY=4`（该机器建议值，理由见 §4）；TPM 配额 **16,000,000 TPM / 2,000 RPM**（账号档位，由用户提供）。

| 靶场 | commit | **Chunks** | **Total Tokens**（bge-m3 口径） | Total Tokens（API 计费） | **TPM**（实耗峰值） | **Response MB**（实测） | **API→VPS MB/s** |
|---|---|---|---|---|---|---|---|
| `leveldb` | `7ee830d` | 1,898 | 260,328 | 207,083 | 2.82 M（4.4s 窗口） | 23.09 MB | **5.25** |
| `HelloAgents` | `93e77ea` | 2,729 | 894,705 | 738,653 | 4.67 M（9.5s 窗口） | 33.21 MB | **3.50** |
| `langchain` | `41d3572` | 20,673 | 4,725,916 | 3,634,688 | 3.66 M（59.6s 窗口） | 251.52 MB | **4.22** |

补充口径：

- **Chunks / Total Tokens 与 company-wsl 逐位相同**（1,898 / 2,729 / 20,673；260,328 / 894,705 /
  4,725,916）——跨机器一致性成立，解析与切分口径没有漂移；
- **API 计费 token 比 bge-m3 口径少 20–21%**（Voyage tokenizer 与 XLM-R 词表不同），
  计费按 API 口径、跨机器对照按 bge-m3 口径，两者**不要混用**；
- `Response MB` 是 provider 侧实测响应字节（`12.46 KB/chunk`，三个仓库一致）；
- `API→VPS MB/s` = 响应字节 ÷ **嵌入窗口**墙钟（剔除解析/入库），与 WSL 报告同口径；
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
| 裸链路下载 | ~1 MB/s（出口受限） | **11.57 MB/s**（Cloudflare 测速） |
| 嵌入响应实测 | 0.76–1.01 MB/s | **4.2–5.3 MB/s**（conc=1 时 1.45） |
| langchain 冷启动 | 589.3s（conc=1，bge-m3） | **115.9s（conc=4，voyage）** |
| TPM 实耗 / 配额 | ~10% | 23%（3.66 M / 16 M tok/min） |
| 429 | conc=3 起在 langchain 上出现 | **无**（conc 4/8/16/32 全部 200） |

结论：**WSL 报告的"耗时 ∝ 响应体 ÷ 带宽"在 VPS 上同样成立**，但 VPS 的瓶颈已从带宽
转移到内存——带宽只用掉裸链路的 4 成，说明 Voyage 侧的响应速率（或 TCP 窗口/边际）是上限，
不是本机出口。

## 6. 复现 / 复用

```bash
# 只查看要建什么、建到哪（不调用 API）
bash benches/embed-bench/build_indexes.sh --dry-run

# 缺哪个建哪个；已建的直接跳过（"不再索引"由脚本强制）
bash benches/embed-bench/build_indexes.sh

# 单仓库 / 强制重建 / 换并发
BENCH_REPOS=langchain EMBED_CONCURRENCY=4 bash benches/embed-bench/build_indexes.sh
bash benches/embed-bench/build_indexes.sh --force
```

配置项与默认值（env 覆盖，脚本不写死）：`EMBED_MODEL=voyage-4-lite`、
`EMBED_CONCURRENCY=8`（本机建议 4）、`EMBED_BATCH_SIZE=500`、`EMBED_BATCH_TOKEN_BUDGET=300000`、
`EMBED_MAX_INPUT_TOKENS=32000`、`ZACE_BENCH_ROOT=~/.zace/bench`。
**Chunk 策略按当前实现默认口径，不提供开关**（改切片规则属 core 变更，会触发 `full_reparse`）。

## 7. 未决与建议

1. **无 golden 用例**：三个靶场只测了索引耗时，未测检索质量；要回归质量需按
   `benches/README.md` 的 JSONL 格式出题（`expected[].path` 用仓库相对路径）；
2. **未进 `targets.json`**：该文件的 schema 要求 `golden` 字段，三靶场暂无用例集，故登记在本文件；
3. **降维（256/512 维）未实测**：当前代码不支持 `output_dimension`（详见 WSL 报告 §8.6）；
   若实现，本机预期收益是响应体减半 → 耗时减半 + 内存减半，对这台机器价值最大；
4. **`upsert` 的第三份复制仍可省**（`VectorStore.upsert` 内部 `[float(v) for v in row.vector]`），
   属可选优化，未在本轮改动范围内；
5. **旁证**：`warp-svc` 历史上会涨到 670–805 MB 并被 OOM（`/root/xuwenzheng/OOM-optimization-2026-09-01.md`），
   与本轮索引无关，但它是本机内存预算里最大的一块不确定项。
