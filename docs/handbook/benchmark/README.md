# 基准测试环境（改检索/排序代码后必须跑）

> **读者**：任何改动了 `core/zace_core/{retrieval,contextpack}/` 的人。
> **硬性要求**：**提交前必须跑**——否则无法知道改动是提升还是回退。
>
> 这是**跨仓库回归测试台**，不是可选的。

## 0. 三十秒版

```bash
cd ~/2_github/AI/ACE/zace
set -a; source ~/.config/zace/benchmark.env; set +a
export no_proxy='*'

for t in leveldb-v1 helloagents-v1 langchain-v1; do
  uv run python benches/run.py --target $t \
    --data ~/.zace/bench/voyage-4-lite-d1024 --report /tmp/bench-$t.md
done
```

对照 §4 的基线表；**低于基线就是回退**。

## 1. 它在哪里（两个都要记住）

| 东西 | 路径 | 说明 |
|---|---|---|
| **持久索引（数据）** | `~/.zace/bench/voyage-4-lite-d1024` | **长期资产**，不在仓库内，`git clean` 不会删 |
| **嵌入配置** | `~/.config/zace/benchmark.env` | Voyage key 等（`0600`），见 [`../privacy/资产清单.md`](../privacy/资产清单.md) |
| **用例集** | `benches/golden/<repo>/*.jsonl` | 在仓库内，跟代码一起版本化 |
| **靶场登记** | `benches/targets.json` | 靶场名 → projectId / golden 的映射 |
| **历史报告** | `benches/results/` | 历次基准结论 |

**为什么必须记住 `~/.zace/bench/voyage-4-lite-d1024`**：所有靶场的索引都在这里
（leveldb 152 文件 / HelloAgents 236 / langchain 2950 / cockpit-agents-py 287），
**重建一次要几分钟到几十分钟且要花 Voyage 额度**。它**不能放 `/tmp`**——重启就没了。

## 2. 靶场

| 靶场名 | 仓库 | 规模 | 用例 | role |
|---|---|---|---|---|
| `leveldb-v1` | C++（152 文件） | 2642 chunks | 20（含 1 负例） | primary |
| `helloagents-v1` | Python（236 文件） | 2729 chunks | 20（含 1 负例） | primary |
| `langchain-v1` | Python（2950 文件） | 20673 chunks | 20（含 1 负例） | primary |
| `cockpit-agents-py` | Python（287 文件） | 3416 chunks | **38**（含 2 负例） | internal |

前三个源码 checkout 在 `~/2_github/AI/ACE/benchmark/<repo>`；
`cockpit-agents-py` 在 `~/4_AIBOX/gitlab/minicpm/cockpit-agents-py`。

**默认流程只跑 `role=primary` 的三个**；`internal` 不进默认流程（索引含公司内部源码，
只能经内网获得，用 `scripts/bench-bundle.sh pack/unpack` 分发）。

> **路径陷阱（已踩过）**：`benchmark/cockpit-agents-server` 与
> `4_AIBOX/.../cockpit-agents-py` **共用同一个 git remote**，因此**共用同一 projectId 与索引**。
> 但前者 checkout 在更旧的 commit（`135ac28`，53 文件），**不含**该靶场需要的符号。
> **不要**用它 ingest——会覆盖索引。详见 `benches/golden/cockpit-agents-py/qa.md`。

## 3. 跑基准

### 3.1 常规（不重新索引）

见 §0。每份报告给出 `recall@5` / `recall@10` / `MRR` / 负例通过数。

### 3.2 零成本对比（调参时用）

改 `score_ratio`、rerank 权重这类参数时，反复调 embedding 很贵。
做法是**先采集一次候选池，之后纯本地重算**：

```bash
# ① 采集：把 query 向量与候选落盘（只跑一次，要 key；三仓约 60 题）
uv run python benches/ratio_bench.py --collect   # 产出 /tmp/zace-ab-pool.pkl

# ② 对比：改任意参数后纯本地重算（不需要 key，秒级）
uv run python benches/ratio_bench.py --eval --ratio 0.40,0.50
```

脚本在 `benches/ratio_bench.py`，复用官方 `run_golden`，**指标口径与 `run.py` 逐位一致**
（实测 ratio 0.40 重现基线 0.912/0.756/3-3）。

> **局限**：只覆盖**候选池之后**的改动（融合/rerank/组装）。
> 改了解析/切片/召回通道本身 → 重新 `--collect`；重建索引后也需重新采集。

### 3.3 基准包分发（把索引搬到另一台机器）

索引不在 git 里。跨机搬运用：

```bash
bash scripts/bench-bundle.sh pack      # 打包（含 golden 排除项说明）
bash scripts/bench-bundle.sh unpack <包>
```

## 4. 当前基线（要对比的基准值）

固定版本：leveldb `7ee830d`、HelloAgents `93e77ea`、langchain `41d3572`、
cockpit-agents-py `febac6d`；embedding `voyage-4-lite@1024`；maxTokens=10000。

| 靶场 | R@5 | R@10 | MRR | 负例 |
|---|---:|---:|---:|---:|
| leveldb | 1.000 | 1.000 | 0.721 | 1/1 |
| HelloAgents | 0.842 | 0.842 | 0.754 | 1/1 |
| langchain | 0.895 | 0.895 | 0.784 | 1/1 |
| **三仓合计** | **0.912** | 0.912 | **0.756** | **3/3** |
| cockpit-agents-py（internal） | 0.806 | 0.833 | 0.544 | 2/2 |

> `cockpit-agents-py` 的 MRR 低于三仓，是因为它含 3 道**架构链路题**（需要跨文件调用链，
> 当前召回覆盖不足——任务板记为 TASK-109）。它的价值是**真实失败现场**：
> 其中 2 题分别固化了「客户端契约 bug」与「召回覆盖不足」两个真实缺陷。

**低于这个值就是回退**，必须查清原因再提交。

> **假回退排查**（先排除这三项再怀疑代码）：没加载 env、没跑对数据根、
> `http_proxy` 未绕过。

## 5. 什么时候必须重建索引

索引只在 **core 的切片或嵌入指纹变化**时失效：

- `PARSER_CONFIG_VERSION` 升版（改了解析/切片逻辑）；
- `EMBED_MODEL` / `EMBED_DIM` 变更。

指纹不符时 `eval` 会**直接报错**（不会拿旧索引冒充同一口径）。重建：

```bash
uv run zace-core ingest --repo ~/2_github/AI/ACE/benchmark/<repo> \
  --data ~/.zace/bench/voyage-4-lite-d1024 --full
```

**换代码不用重建**（进程/路由/前端改动与索引无关）；
**只改 rerank/组装也不用重建**（那些发生在检索之后）。

## 6. 与接入验证环境的区别

两个环境**互不干扰**，别弄混：

| | 接入验证 | 基准测试（本篇） |
|---|---|---|
| 数据根 | `~/.zace/live` | `~/.zace/bench/voyage-4-lite-d1024` |
| 用途 | 真实 Agent 接入、看历史页 | 跨仓库回归，判改动增益 |
| 靶场 | 自选仓库（client 自动同步） | 固定四个，带 golden 用例 |
| 启停 | systemd 按需 | 命令行一次性跑 |

两者共用 `~/.config/zace/` 下的配置（`live.env` 与 `benchmark.env` 分开）。
接入验证环境见 [`../deployment/wsl-live.md`](../deployment/wsl-live.md)。

## 相关文档

- 隐私资产（benchmark.env） → [`../privacy/资产清单.md`](../privacy/资产清单.md)
- embedding 参数切换 → [`../operations/embedding-provider切换.md`](../operations/embedding-provider切换.md)
- 靶场索引白名单 → [`../operations/索引白名单.md`](../operations/索引白名单.md)
