# 索引基线 v1（VPS 冻结配置 · 2026-09-15）

> 状态：**已实测**｜设备：`vps-la-2c2g`（洛杉矶 2 vCPU / 1.9 GiB）｜口径：`ingest_probe.py`（探针）
> 用途：**后续调「维度 / chunk 切分」的对照点** —— 改配置后拿同一张表比，看能优化多少。
> 姊妹文档：`index-cost-model-vps.md`（耗时模型与口径定义）、`results/README.md`（报告索引）。

## 0. 一句话

配置已冻结为 `voyage-4-lite / 1024 维 / 并发 4 / batch 500 / budget 300000 / maxTok 32000`；
**同配置两次跑批实测有 ±20% 抖动（langchain 141.9s → 168.3s），且抖动全落在本地段** ——
所以对比新配置时：**要么每配置跑 ≥2 次取中位，要么只认 >20% 的差异**。

## 1. 冻结配置（"基础"）

| 配置项 | 冻结值 | 入口 | 备注 |
|---|---|---|---|
| 模型 | `voyage-4-lite` | `EMBED_MODEL` | registry 已登记；base_url = `https://api.voyageai.com` |
| 维度 | **1024** | `EMBED_DIM` | **当前对 API 模式无效**，见 §5-1；实际由 registry 决定 |
| 并发 | **4** | `EMBED_CONCURRENCY` | registry 厂商推荐是 8；这台机器用 4（链路已 96% 饱和 + 2 GiB 内存安全线） |
| 批大小 | 500 | `EMBED_BATCH_SIZE` | 1000 会因响应体过大被对端断连 |
| 批预算 | 300000 | `EMBED_BATCH_TOKEN_BUDGET` | |
| 截断上限 | 32000 | `EMBED_MAX_INPUT_TOKENS` | 不进指纹，只影响单条截断 |
| **嵌入窗口** | 2000 chunk | 派生 | = `batch_size × concurrency`（`MAX_EMBED_WINDOW=4000` 封顶） |
| Chunk 策略 | 当前实现默认口径 | 无开关 | `splitter.py` 常量，`parser_config_hash = 76741bca6f8e` |

生效位置（两处，都已改）：
1. `benches/embed-bench/build_indexes.sh` 默认值 `EMBED_CONCURRENCY=8 → 4`；
2. **生产服务** `/etc/zace/zace.env` 新增 `EMBED_CONCURRENCY=4` / `EMBED_BATCH_SIZE=500` /
   `EMBED_BATCH_TOKEN_BUDGET=300000` / `EMBED_MAX_INPUT_TOKENS=32000`（改前回落 registry 的 8，
   正是 §4.2 事故那档窗口），已 `systemctl restart zace-service`（健康检查 200 / `auth: required`）。
   备份：`/etc/zace/zace.env.bak-20260915`。

## 2. v1 实测（三靶场，全量重建）

| 靶场 | chunks | **墙钟** | **峰值 RSS** | 嵌入窗口 | **网络在飞** | 本地段 | **Response MB** | **Total Tokens** | **API→本机 MB/s** | **TPM**（在飞口径） | upsert |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `leveldb` | 1,898 | 12.69s | 765.5 MB | 4.98s | 3.05s | 9.64s | 23.09 | 207,083 | 7.57 | 4.07 M | 0.88s / 1 次 |
| `HelloAgents` | 2,729 | 25.79s | 831.5 MB | 10.37s | 5.03s | 20.76s | 33.21 | 738,653 | 6.60 | 8.81 M | 0.77s / 2 次 |
| `langchain` | 20,673 | 168.32s | **1125.0 MB** | 75.78s | 42.53s | 125.79s | 251.52 | 3,634,688 | 5.91 | 5.13 M | 5.10s / 11 次 |

- 状态码全 `200`（无 429），复用/新增：三个靶场都是 `chunks_new = 全部`（全量重建）；
- 网络段占比 24% / 20% / 25%，其余是本地 CPU（与 `index-cost-model-vps.md` §3.1 的 70/30 同结论）；
- 无网络地板（`local_only_probe.py`）：leveldb 5.4s / HelloAgents 11.3s / langchain 84.6s。

## 3. 产物落点（**不要动**）

| 路径 | 内容 |
|---|---|
| `/root/.zace/bench/baseline-v1/voyage-4-lite-d1024` | **本基线的索引快照**（219 MB，三靶场齐全）——未来 A/B 里"before"的那一侧 |
| `/root/.zace/bench/voyage-4-lite-d1024` | canonical 持久索引（同配置），**日常基准跑分复用这个** |
| `benches/results/raw/baseline-v1/*.json` | 上表的原始证据（每靶场一份，含机器指纹与负载快照） |
| `/root/.zace/bench/baseline-v1/run.sh` | 复现脚本 |

## 4. 波动与对比纪律（重要）

同配置、相隔约 1 小时的两次跑批（都是探针口径、`conc=4`）：

| 靶场 | 第一次（05:08–05:12） | 本次（06:11–06:15） | 差 | 网络段差 | 本地段差 |
|---|---|---|---|---|---|
| `leveldb` | 9.93s | 12.69s | +28% | 3.01 → 3.05s | 6.9 → 9.6s |
| `HelloAgents` | 20.90s | 25.79s | +23% | 5.07 → 5.03s | 15.8 → 20.8s |
| `langchain` | 141.92s | 168.32s | **+18.6%** | 37.05 → 42.53s | 104.9 → 125.8s |

- **网络段几乎不变，涨的全是本地段** ⇒ 不是网络/配额问题，是这台共享 VPS 的 CPU/内存抖动
  （同时常驻 `zace-service` / `postgres` / `docker` / `codex`，swap 已用 300–420 MB）；
- `ingest_probe.py` 现在会记录 `machine.loadavg` / `mem_available_mb` / `swap_used_mb`（本次之后生效），
  **对比两个数字前先看这三项**；
- 因此对比新配置的判据：**≥2 次取中位**，或**只认 >20% 的差异**。小靶场（leveldb 13s / 23 MB）适合反复试。

## 5. 你下一步要改的两项，目前"不可配"（需动 core）

1. **维度**：`EMBED_DIM` 对 API 模式**不生效**。请求体只有 `{"model", "input"}`，没有 `output_dimension`
   （`core/zace_core/embedding/api.py:294`）；设 `EMBED_DIM=512` 会让 `profile.dim=512` 而 API 仍回 1024 维 →
   校验直接报错（同文件 ~L320）。要支持需在 payload 透传 `output_dimension`（Voyage 支持 256/512/1024/2048），
   属 core 改动 + 需要回归检索质量。
2. **Chunk 策略**：`splitter.py` 里是常量（`EMBEDDING_BODY_MAX_CHARS = 8000`、`_SIGNATURE_MAX_LINES = 40`、
   `FALLBACK_MAX_*`），**没有 env 入口**；且它们进 `parser_config_hash` → 改了触发 `full_reparse`。
   ⚠️ **必须换数据根**（例：`ZACE_BENCH_ROOT=~/.zace/bench/exp-chunk-v2`），否则 v1 索引被原地覆盖，
   A/B 的"before"就没了。
3. 还有一个质量前置：三靶场**没有 golden 用例**（`index-cost-model-vps.md` §7-1）。
   调维度/切片会同时影响 recall —— 只比耗时是"跑得快但搜不到"，建议先给三靶场补一套最小用例
   （格式见 `benches/README.md`）。

## 6. 复现命令

```bash
# 环境（密钥不进 Git）
set -a; . /etc/zace/zace.env; set +a

# 单靶场（全量重建到指定根）——注意 --data 指向的目标根：
systemd-run --scope --quiet -p MemoryHigh=1200M -p MemoryMax=1500M -p MemorySwapMax=512M -- \
  uv run python benches/embed-bench/ingest_probe.py \
    --repo /root/xuwenzheng/ACE/benchmark/langchain \
    --data /root/.zace/bench/baseline-v1/voyage-4-lite-d1024 \
    --tag baseline-v1/conc4 \
    --out benches/results/raw/baseline-v1/langchain.json

# 三靶场一把跑（本基线用的就是这个脚本）
systemd-run --scope --quiet -p MemoryHigh=1200M -p MemoryMax=1500M -p MemorySwapMax=512M -- \
  /root/.zace/bench/baseline-v1/run.sh

# 复用（不重嵌）：日常基准用 canonical 根
uv run zace-core search "<query>" --project-id ca2050db0db5b1e2 \
  --repo /root/xuwenzheng/ACE/benchmark/langchain --data /root/.zace/bench/voyage-4-lite-d1024
```

## 7. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-15 | **v1** | 首次冻结：`voyage-4-lite` / 1024 维 / 并发 4 / batch 500 / budget 300000 / maxTok 32000；三靶场全量重建留档；生产 `zace-service` 同步改配置并重启 |
