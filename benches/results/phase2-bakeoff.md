# Phase 2 embedding bake-off（TASK-015A，只做模型选型）

> 生成：2026-09-11 ｜ 分支：`feature/task-015a_xwz0910`（jump 自 `main` @ `ea4084d`）
> 原始产物：`~/.cache/zace-bakeoff/results/*.json`（脚本落盘，含完整命令/数据根/commit）
> 一句话结论：**沿用 `multilingual-e5-small`（384D / 512 token）作为默认模型**——
> 三仓库合并 recall@5 0.556 / MRR 0.457 双双第一，向量库体积与最小模型持平（1638 B/chunk），
> 唯一代价是索引耗时约为对照模型的 1.5–2 倍（本机 61 分钟 / 451 文件 / 5760 chunks）。
> **不选更大模型**：bge-m3 的实测吞吐只有 e5-small 的 1/4（0.38 vs 1.46 chunk/s）、
> 内存 3GB、单仓库索引 1 小时+，本机跑不动，且收益未获验证（见 §7 未决问题 1）。
> **`max_input_tokens` 维持 512**：`Module/01 §2.4` 的 2048 假设在本地小模型上**物理不可行**
> （ONNX 位置嵌入矩阵只有 512 行，超长直接报错，见 §4）。

## 0. 本卡纪律与回归护栏（R29/R30）

卡内冻结：**不得**修改 rerank 权重 / FTS 列权重 / 前缀匹配开关 / `RecallLimits` /
`docs_ratio` / `CONSENSUS_SCORE_RATIO`。**唯一变量是 embedding provider。**

证明（`git diff --stat` 只含本卡交付物，无任何排序/装填参数文件）：

```text
$ git diff --stat main
 benches/bakeoff/embed_compare.py       | 1100 ++++++++++++++++++++++++++++++++
 benches/bakeoff/run_matrix.sh          |   60 +++
 benches/bakeoff/test_embed_compare.py  |  266 ++++++++
 benches/results/phase2-bakeoff.md      |  (本文件)
 docs/tasks/README.md                   |    2 +-   ← 任务板状态行 pending → review
 docs/tasks/TASK-015-Bakeoff与校准.md   |   40 +-     ← 本卡"执行记录"节
```

```text
$ git diff main -- core/ | wc -l
0                                        ← embedding 默认值未改（结论支持沿用 e5-small）
$ git diff main -- core/zace_core/retrieval/ core/zace_core/contextpack/ core/zace_core/storage/ | wc -l
0                                        ← 排序/装填/BM25 列权重一律未动
```

脚本侧同样是零参数改写：`run` 子命令只接受 `--model / --repo / --golden / --max-input-tokens`，
没有任何通道配额、权重或装填参数的入口（`--max-input-tokens` 只改 provider 的截断值）。

## 1. 环境与口径

### 1.1 机器与并发（读数字前必看）

| 项 | 值 |
|---|---|
| CPU | 12th Gen Intel(R) Core(TM) i9-12900H，**WSL 仅分配 6 逻辑核** |
| 内存 | 15.6 GiB（WSL 上限），无 GPU |
| onnxruntime | 1.29.0（CPU EP） |
| 检索预算 | `maxTokens=10000`（= `zace-core eval` 的 `DEFAULT_MAX_TOKENS`，未改） |
| 并发 | **1–2 路并行**（本机同时还有另外两条泳道的进程），故耗时数字是**受争用的墙钟值**，偏保守 |

**过程中本机重启 3 次**（09:17 / 09:21 / 10:20，最后一次与一次内存事故相关）。
因早期把数据根与模型缓存从 `/tmp` 迁到 `~/.cache`（见 §8 偏差 1），**全部产物零丢失**。
重启后 `content_hash` 复用使重跑接着走，未重复劳动。

### 1.2 被测对象（三仓库，与 TASK-014 基线同一套 golden，60 条）

| repo | 路径 | commit | 索引范围文件数 | chunks | golden 用例 |
|---|---|---|---|---|---|
| `zace`（dogfood） | 本仓 | `ea4084d9` | 279 | 3218 | 24（正例 22） |
| `aibox-super-sdk` | `/home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk` | `debf8a32` | 451 | 5760 | 20（正例 18） |
| `linux-mtk-mw-cameraservice` | `/home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice` | `3fb0b2d6` | 1382 | 6257 | 16（正例 14） |

**索引范围一致性（证明"唯一变量是 provider"）**：三个模型对同一仓库记录的
`scope.digest`（scan manifest 的 `路径:content_hash` 排序后 sha256）**逐字节相同**：

```text
zace   → e62c33aa546d6d62…  （279 文件）
aibox  → 0e2e7cacf22e…      （451 文件）
cam    → aedbfb85da22…      （1382 文件）
```

切分参数、解析器指纹（`parser_config_hash`）在三轮之间也完全一致——
`index.db` 侧的 `index_config` 只有 `embedding_model` / `embedding_dim` 两条不同。

### 1.3 数据根与模型缓存

- 数据根：`~/.cache/zace-bakeoff/<slug>__t<tokens>/`（**每模型独立**，可断点续跑）；
- 模型缓存：`~/.cache/zace-embedding-cache/`（1.2 GB，**未提交进仓库**）；
- 中间结果：`~/.cache/zace-bakeoff/results/*.json`。

## 2. 模型下载记录（首次联网 HuggingFace）

| slug | repo_id | onnx 文件 | 体积 | 下载耗时 |
|---|---|---|---|---|
| `multilingual-e5-small` | intfloat/multilingual-e5-small | `onnx/model.onnx` | 470.3 MB（+ tokenizer 17.1 MB） | 139.6 s |
| `bge-small-zh-v1.5` | Xenova/bge-small-zh-v1.5 | `onnx/model.onnx` | 94.9 MB（+ tokenizer 0.4 MB） | 29.2 s |
| `arctic-embed-xs` | Snowflake/snowflake-arctic-embed-xs | `onnx/model.onnx` | 90.4 MB（+ tokenizer 0.7 MB） | 41.5 s |
| `bge-m3-int8`（可选上界） | Xenova/bge-m3 | `onnx/model_quantized.onnx` | 569.7 MB（+ tokenizer 17.1 MB） | 247.3 s |

合计 1.2 GB，全部落在 `~/.cache/zace-embedding-cache/`，**未进入 git 工作区**。
复现命令：`uv run python benches/bakeoff/embed_compare.py fetch --model all`（命中缓存时为 0 秒）。

## 3. 模型对比表（A1 主结果）

口径：② e2e（`zace-core eval` 默认 = ContextPack 装填序），`max_input_tokens=512`（各自原生上限）。

### 3.1 质量（每仓库）

| 模型 | repo | 正例 | recall@5 | recall@10 | MRR | 负例通过 | 向量降级 | 查询 P50 | 查询 P95 | 查询嵌入 P50 |
|---|---|---|---|---|---|---|---|---|---|---|
| **e5-small** | zace | 22 | **0.591** | **0.818** | **0.539** | 0/2 | 0 | 0.856 s | 0.996 s | 0.055 s |
| **e5-small** | aibox | 18 | **0.556** | 0.667 | **0.466** | 1/2 | 0 | 1.575 s | 2.354 s | 0.040 s |
| **e5-small** | cam | 14 | 0.500 | 0.500 | 0.314 | 1/2 | 0 | 0.132 s | 0.206 s | 0.030 s |
| bge-small-zh-v1.5 | zace | 22 | 0.636 | 0.773 | 0.459 | 0/2 | 0 | 0.678 s | 1.064 s | 0.017 s |
| bge-small-zh-v1.5 | aibox | 18 | 0.500 | 0.667 | 0.385 | 1/2 | 0 | 2.269 s | 2.853 s | 0.037 s |
| bge-small-zh-v1.5 | cam | 14 | 0.429 | 0.571 | 0.318 | 1/2 | 0 | 0.182 s | 0.258 s | 0.041 s |
| arctic-embed-xs | zace | 22 | 0.455 | 0.591 | 0.334 | 2/2 | 0 | 0.682 s | 0.872 s | 0.018 s |
| arctic-embed-xs | aibox | 18 | 0.444 | 0.611 | 0.403 | 1/2 | 0 | 1.878 s | 2.842 s | 0.032 s |
| arctic-embed-xs | cam | 14 | 0.500 | 0.500 | 0.327 | 1/2 | 0 | 0.115 s | 0.152 s | 0.030 s |

**查询延迟口径提醒**：`查询 P50/P95` 含 BM25 + 图扩展 + rerank + 装填全链路（向量通道只是其中一环），
所以它主要反映仓库规模与机器争用，**不是模型速度**。模型速度看"查询嵌入 P50"一列
（纯 query 侧嵌入，采样 22 条正例 × 3 次）：三者 0.017–0.055 s，**差 3 倍但绝对值都可忽略**。

### 3.2 质量（三仓库合并，54 正例）

| 模型 | recall@5 | recall@10 | MRR | 负例通过 | 索引耗时 zace / aibox / cam | 向量库 zace / aibox / cam | 嵌入吞吐 |
|---|---|---|---|---|---|---|---|
| **multilingual-e5-small**（现默认） | **0.556** | **0.685** | **0.457** | 2/6 | 2359 / 3686 / 2325 s | 5.3 / 9.4 / 10.1 MB | 1.38–2.74 chunk/s |
| bge-small-zh-v1.5 | 0.537 | **0.685** | 0.398 | 2/6 | 1077 / 2247 / 1007 s | 6.9 / 12.4 / 13.3 MB | 3.04–6.44 chunk/s |
| arctic-embed-xs | 0.463 | 0.574 | 0.355 | 4/6 | 1000 / 1928 / 1047 s | 5.3 / 9.4 / 10.1 MB | 3.06–6.19 chunk/s |

### 3.3 按语言 / 按类别（合并，单元格 = 正例数 / r@5 / r@10 / MRR）

| 分组 | e5-small | bge-small-zh-v1.5 | arctic-embed-xs |
|---|---|---|---|
| en (13) | **0.769 / 0.769 / 0.567** | 0.615 / 0.692 / 0.294 | 0.462 / 0.615 / 0.393 |
| mixed (20) | 0.450 / 0.600 / 0.403 | **0.600 / 0.750 / 0.455** | 0.500 / 0.600 / 0.348 |
| zh (21) | **0.524 / 0.714 / 0.440** | 0.429 / 0.619 / 0.407 | 0.429 / 0.524 / 0.339 |
| behavior (16) | 0.625 / 0.688 / **0.519** | 0.625 / 0.688 / 0.394 | 0.562 / 0.688 / 0.379 |
| path (10) | 0.100 / 0.400 / 0.092 | **0.200 / 0.500** / 0.085 | 0.000 / 0.200 / 0.025 |
| spec (12) | **0.833** / 0.833 / 0.656 | 0.750 / 0.750 / **0.750** | 0.750 / 0.750 / 0.562 |
| symbol (16) | **0.562 / 0.750 / 0.473** | 0.500 / **0.750** / 0.333 | 0.438 / 0.562 / 0.382 |

**读法**：
- e5-small 在 **en / zh / behavior / symbol** 四组领先，且 MRR 全面最高（判别力最强）；
- bge-small-zh-v1.5 强在 **mixed 与 path**（r@10 0.500 vs e5 的 0.400）——中文定位模型把
  路径类查询的语义匹配做得更好，但整体 MRR 低 0.06；
- arctic-embed-xs（英文）中文表现最差（zh r@5 0.429），符合预期；其**负例通过 4/6 最高**是
  因为"更弱的相关性让它更倾向说不确定"——不是质量优势，是负例口径受 answerable 判定影响（R22）。

### 3.4 逐用例翻转（模型之间差异落在哪些题上）

54 条正例里，**12 条存在模型间命中翻转**（名次取自逐用例名次对比，表格为 rank，`-` = 未命中）。

| 形态 | 用例 | e5 | bge-zh | arctic |
|---|---|---|---|---|
| **只有 e5 命中** | `aibox-0009` | 9 | - | - |
| | `zace-0107` | 6 | - | - |
| | `zace-0110` | 3 | - | - |
| **只有 bge-small-zh 命中** | `aibox-0015` | - | 7 | - |
| | `cameraservice-0015` | - | 7 | - |
| | `zace-0114` | - | 4 | - |
| **e5 与 bge 命中、arctic 全部落空** | `cameraservice-0009` | 2 | 5 | - |
| | `zace-0001` | 8 | 10 | - |
| | `zace-0102` | 6 | 6 | - |
| | `zace-0112` | 10 | 10 | - |
| **e5 落空、bge 与 arctic 命中** | `cameraservice-0014` | - | 2 | 2 |
| **e5 与 arctic 命中、bge 落空** | `cameraservice-0007` | 5 | - | 3 |

读法：
- **e5 独有 3 条、bge 独有 3 条**，正好对称——即两者在"能不能找到"上不分伯仲；
- **arctic 在 4 条上落空而 e5/bge 都能找到**（`cameraservice-0009`、`zace-0001/0102/0112`），
  是三者中唯一被系统性甩开的一个；
- 其余差距体现在同名次的高低（MRR），而不是命中与否。

即：**没有一个候选在"命中/不命中"的二值面上压倒性领先**，差异主要在 MRR（名次质量）——
这是 smoke 集（R29）上的预期现象，也再次说明本卡不应据此调排序参数。

## 4. 截断 A/B（A2）：**本地小模型上物理不可行**

### 4.1 现象（完整报错）

对推荐模型 e5-small 用 `--max-input-tokens 2048` 建索引时，ONNX 会话直接失败：

```text
$ uv run python benches/bakeoff/embed_compare.py run \
    --model multilingual-e5-small --repo . --repo-name zace-t2048 \
    --golden benches/golden/zace --max-input-tokens 2048

EmbeddingError: 本地 ONNX 推理失败（model=local:multilingual-e5-small）：
Fail("[ONNXRuntimeError] : 1 : FAIL : Non-zero status code returned while running Add node.
Name:'/embeddings/Add_1' Status Message: .../element_wise_ops.h:583 void
onnxruntime::BroadcastIterator::Append(ptrdiff_t, ptrdiff_t) axis == 1 || axis == largest
was false. Attempting to broadcast an axis by a dimension other than 1. 512 by 901")
```

`512 by 901` = 位置嵌入矩阵 512 行 **vs** 输入序列 901 token——即**模型的
`max_position_embeddings` 就是 512**，`max_input_tokens=2048` 让 provider 把 901 个 token
原样喂进去，广播失败。

### 4.2 上限矩阵（探针实测，`~/.cache` 脚本，未入库）

对每个候选 × 每个截断值，输入一段 4000 字的超长文本（原始 token 4000+）：

| 模型 | t=512 | t=1024 | t=2048 | tokenizer 自身行为 |
|---|---|---|---|---|
| `multilingual-e5-small` | ✅ 2.01 s | ❌ `512 by 1024` | ❌ `512 by 2048` | 不截断，原样输出 4003 token |
| `bge-small-zh-v1.5` | ✅ 0.80 s | ❌ `512 by 1024` | ❌ `512 by 2048` | 不截断，原样输出 4002 token |
| `arctic-embed-xs` | ✅ 0.80 s | ✅ 0.86 s | ✅ 1.02 s | **自带截断到 512**（始终输出 512） |
| `bge-m3-int8` | ✅ 7.24 s | ✅ 11.32 s | ✅ 27.61 s | 不截断，输出 4003 token |

三个本地小候选的 ONNX 位置嵌入都是 **512 行**（与 `registry.py` 的登记注释一致）；
arctic 之所以"通过"是因为它的 `tokenizer.json` 自带 `model_max_length=512` 截断，
**并它没有真的处理 2048 token**，只是静默丢掉。

### 4.3 结论

1. **`Module/01 §2.4` 的"2048 token 截断上界"在本地 ONNX 小模型上不可实现**——不是性能问题，
   是模型架构上限。截断 A/B（512 vs 2048）**只能在原生上限 ≥2048 的模型上做**
   （本候选集里只有 `bge-m3`）；
2. 因此本卡**无法**给出推荐模型的截断 A/B 数字。基于 §3 的 token 分布，"2048 是否值得"这个问题
   对本候选集的实际意义也有限：aibox 上 e5-small 只有 **169/5760（2.9%）** chunk 超过 2048 token、
   **650/5760（11.3%）** 超过 512；即在 512 截断下，**约 11% 的 chunk 尾部被丢掉**；
3. **`max_input_tokens=512` 应维持**——它等于模型原生上限，是唯一可行值；
4. **provider 缺少上限校验**：当前实现按配置值硬截断，**不检查是否超过模型原生上限**，
   于是配置错误变成运行期 ONNX 崩溃（错误信息对使用者不友好）。编排者已立 **TASK-038** 修复
   （钳制到原生上限 + 友好报错）；**本卡按指令未改代码**。

## 5. 索引代价（VPS 选型与 TASK-041R 分发体积的输入）

### 5.1 实测（每模型 × 仓库）

| 模型 | repo | 文件 | chunks | 索引墙钟 | 其中嵌入 | 嵌入吞吐 | 向量库 | **字节/chunk** | index.db | 项目总计 |
|---|---|---|---|---|---|---|---|---|---|---|
| e5-small | zace | 279 | 3218 | 2359 s | 2330 s | 1.38 /s | 5.3 MB | 1641 | 19.7 MB | 25.1 MB |
| e5-small | aibox | 451 | 5760 | 3686 s | 3620 s | 1.59 /s | 9.4 MB | 1638 | 38.2 MB | 47.7 MB |
| e5-small | cam | 1382 | 6257 | 2325 s | 2281 s | 2.74 /s | 10.1 MB | 1610 | 14.6 MB | 24.9 MB |
| bge-small-zh | zace | 279 | 3218 | 1077 s | 1059 s | 3.04 /s | 6.9 MB | 2152 | 19.7 MB | 26.7 MB |
| bge-small-zh | aibox | 451 | 5760 | 2247 s | 2186 s | 2.63 /s | 12.4 MB | 2149 | 38.2 MB | 50.7 MB |
| bge-small-zh | cam | 1382 | 6257 | 1007 s | 972 s | 6.44 /s | 13.3 MB | 2122 | 14.6 MB | 28.1 MB |
| arctic-xs | zace | 279 | 3218 | 1000 s | 968 s | 3.33 /s | 5.3 MB | 1641 | 19.7 MB | 25.1 MB |
| arctic-xs | aibox | 451 | 5760 | 1928 s | 1883 s | 3.06 /s | 9.4 MB | 1638 | 38.2 MB | 47.7 MB |
| arctic-xs | cam | 1382 | 6257 | 1047 s | 1011 s | 6.19 /s | 10.1 MB | 1610 | 14.6 MB | 24.9 MB |

**索引耗时几乎全在嵌入**（占总墙钟 96–98%），解析+入库+建图只占 2–4%。
**`index.db` 与模型无关**（同仓库三条完全相同：19.7 / 38.2 / 14.6 MB）——它只存切片与图。

### 5.2 归一化：bytes/chunk 与 s/chunk

| 模型 | dim | 理论向量字节 | 实测 bytes/chunk | 实测 s/chunk（按仓库） |
|---|---|---|---|---|
| e5-small | 384 | 1536 | **1638–1641** | 0.72（zace）/ 0.63（aibox）/ 0.36（cam） |
| bge-small-zh | 512 | 2048 | **2122–2152** | 0.33 / 0.38 / 0.16 |
| arctic-xs | 384 | 1536 | **1610–1641** | 0.30 / 0.33 / 0.16 |

- **体积可精确预测**：`bytes/chunk ≈ dim × 4 + ~100`（LanceDB 的 chunk_id/hash 列开销）；
- **耗时随 chunk 长度而非数量变化**：cam 的 chunks 最多但最快，因为它的 C++ 切片更短
  （token p50 = 23–33，而 aibox/zace 的 p50 = 152–181）。**估算耗时必须用 token 总量，不能只用文件数。**

### 5.3 外推：真实仓库（434 文件 / 5760 chunks 量级）

以 aibox（451 扫描 / 434 解析，5760 chunks）为基准，e5-small：

```text
全量索引耗时 ≈ 3686 s ≈ 61 分钟（6 核 CPU、无 GPU）
向量库磁盘   ≈ 9.4 MB            （5760 × 1638 B）
index.db     ≈ 38.2 MB
项目总计     ≈ 47.7 MB / 仓库
```

对照：bge-small-zh ≈ 37 分钟 / 12.4 MB；arctic-xs ≈ 32 分钟 / 9.4 MB。

**对 VPS 选型的含义**：
1. **首次索引是 CPU 密集的长任务**（61 分钟 / 中型仓库 / 6 核），VPS 选型必须按
   "单次全量索引 1 小时量级"预留资源，或接受"首次索引慢、之后增量快"（增量索引稳态
   只处理变更文件，TASK-014 实测 1.2s）；
2. **存储压力很小**（每 1000 chunks 约 1.6 MB 向量 + 6.6 MB 图），磁盘不是瓶颈；
3. **模型文件本身 470 MB**（e5-small fp32 ONNX）是**分发体积的主要项**——若要缩小分发体积，
   registry 注释里已给出量化版本（`model_qint8_avx512_vnni.onnx`）作为后续优化项，
   本卡未测（不在候选清单内，且量化会改变向量空间，需重新走本卡流程）。

## 6. 推荐（A3）

### 6.1 结论

| 项 | 推荐值 | 理由 |
|---|---|---|
| 默认模型 slug | **`multilingual-e5-small`**（维持现状，不改） | 三仓库合并 r@5 / MRR 双第一；en/zh/behavior/symbol 四组领先；体积与最小模型持平 |
| `max_input_tokens` | **512**（维持现状，不改） | 等于模型原生上限；2048 不可行（§4）；arctic 是静默截断而非真支持 |
| 默认 provider | `local`（ONNX）不变 | 隐私（源码不出本机）+ 分发（无需联网）|

**本卡因此不改任何代码**——结论支持沿用 TASK-008 的暂定默认。A4「默认值调整」不触发，
D-07 二级失效重建流程无需实测（无变更）。这是最省的结局：默认值经数据验证，而非凭直觉。

### 6.2 不选更大模型（bge-m3）的原因

| 维度 | e5-small | bge-m3-int8 | 差距 |
|---|---|---|---|
| 参数 / 向量维度 | 118M / 384D | 568M / 1024D | 4.8× / 2.7× |
| 模型文件 | 470 MB | **570 MB**（int8）/ 2270 MB（fp32） | 1.2× / 4.8× |
| 嵌入吞吐（实测） | 1.46 chunk/s | **0.38 chunk/s** | **3.8× 慢** |
| 单进程内存 | ~400 MB | **~3 GB** | 7.5× |
| 单仓库索引（5760 chunks）外推 | 61 min | **~4.2 小时** | 4.1× |
| 向量库（5760 chunks） | 9.4 MB | **23.6 MB** | 2.5× |
| 质量收益 | — | **未获验证**（本机资源不足，未跑完） | — |

三项代价（时间 ×4、内存 ×7.5、分发体积 ×4.8）全部显著，而收益**没有数据支持**；
且它在本机**根本无法完成一轮三仓库索引**（单进程 3GB、单仓库 1 小时+、跑三仓库需 4+ 小时，
期间机器已两次重启）。**在"质量收益未验证 + 代价显著"的前提下，不应切换默认模型。**

## 7. 未决问题

1. **bge-m3（可选上界参考）未完成**（本机资源不足，编排者已裁定停跑）。
   已完成：aibox 索引进行中被中止（数据根 `~/.cache/zace-bakeoff/bge-m3-int8__t512/` 可续跑）。
   未完成：aibox 质量数字、zace 质量数字、zace 截断 A/B。
   **建议**：租 GPU 云服务器（A10/4090，¥2–4/小时，1–2 小时可跑完整矩阵）复现本卡脚本，
   把 `~/.cache/zace-bakeoff/results/*.json` 拿回来重新 `aggregate` 即可合并进本报告。
   复现命令见 §9。
2. **截断 A/B 缺失**（§4）：本地三候选均无法做 2048 截断。若要回答"2048 是否值得"，
   必须用 bge-m3（唯一支持者）在云端跑 A/B。**当前 512 的正确性由架构上限担保，不由实验担保。**
3. **provider 未校验截断上限**：配置超过模型原生上限 → 运行期 ONNX 崩溃（§4.1）。
   已由编排者立 **TASK-038**（钳制 + 友好报错），本卡未改代码。
4. **量化版本的代价/质量未测**：registry 注释列出的 `model_qint8_avx512_vnni.onnx`
   （e5-small）与 `model_quantized.onnx` 未纳入候选。若 VPS 分发体积成为约束，应另开卡做
   "量化 vs fp32"的对照（需确认量化不破坏向量空间，会触发 D-07 二级失效）。
5. **R29 口径提醒**：本卡全部数字来自 60 条 smoke 集。据其选**模型**（一次性架构决策）是
   卡内允许的；但**不得**据此调排序/装填参数（R30，归 TASK-050）。
   模型间 12 条命中翻转集中在 MRR 层面，说明差距不大，**真实数据（TASK-023）到位后应复核本结论**。
6. **cam 仓库的 `zace` 负例口径**：cam 在 §3.1 的负例通过 1/2，与 §3.3 的 e5/arctic 差异
   同源（`answerable` 判定受 R22 口径影响），不是模型质量差异。

## 8. 契约影响 / 与设计偏差

**契约影响：无。** 未改 `docs/contracts/**`、`core/zace_core/{types,interfaces,hashing}.py`；
未改任何 CF 字段；未改 embedding 默认值（结论支持沿用），因此 D-07 二级失效流程未被触发。

**与设计偏差：无设计层面偏差**，但有两条实现侧记录：

1. **数据根从 `/tmp` 迁到 `~/.cache`（任务卡给的现成资源失效）**。
   任务卡指定"已有索引：`/tmp/zace-aibox`、`/tmp/zace-verify-main`、`/tmp/zace-cam`（可直接读，
   换模型的索引必须重建）"与"模型缓存 `/tmp/zace-embedding-cache`"。实况：本机在
   2026-09-11 00:07 重启，**`/tmp` 被整体清空**，三类现成资源全部不存在（已核实目录为空）。
   处置：脚本默认路径改为 `~/.cache/zace-bakeoff` + `~/.cache/zace-embedding-cache`，
   **并在同一数据根上重建三个仓库的索引**——因此本报告所有数字（含"基线"e5-small 一行）
   都出自同一批新建索引，**口径自洽，未混用 TASK-014 的旧数字**。
   （副作用：zace 索引范围包含 `benches/**`，与 TASK-014 §4.2 的 R17 现象相同，
   负例口径同样受影响；本报告的负例列仅作对照，不作结论。）
2. **并发与中断**：为压缩墙钟时间曾开 1–2 路并行（后经编排者裁定收紧为"大模型 1 路串行、
   小模型 ≤2 路"）。期间本机重启 3 次，因产物在 `~/.cache` 且索引可断点续跑，**无重复劳动**。
   报告的耗时数字是**受争用的墙钟值**，在独占机器上应更快（实测探针单模型 e5-small
   0.686 s/chunk，与受争用时的 0.63–0.72 s/chunk 基本一致，说明争用影响有限）。

## 9. 复现命令（DoD：完整命令）

```bash
# 0) 候选清单与缓存状态
uv run python benches/bakeoff/embed_compare.py list

# 1) 预下载模型（记录体积与耗时；命中缓存 0 秒）
uv run python benches/bakeoff/embed_compare.py fetch --model all

# 2) 每模型 × 每仓库：建索引 + 跑 golden（幂等，可断点续跑）
#    也可用 benches/bakeoff/run_matrix.sh lane1 / lane2 批量驱动
uv run python benches/bakeoff/embed_compare.py run \
  --model multilingual-e5-small --repo . --repo-name zace --golden benches/golden/zace

uv run python benches/bakeoff/embed_compare.py run \
  --model multilingual-e5-small \
  --repo /home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk \
  --repo-name aibox --golden benches/golden/aibox-super-sdk

uv run python benches/bakeoff/embed_compare.py run \
  --model multilingual-e5-small \
  --repo /home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice \
  --repo-name cam --golden benches/golden/linux-mtk-mw-cameraservice

# （把 --model 换成 bge-small-zh-v1.5 / arctic-embed-xs 重复三次即得对照行）

# 3) 汇总原始数字（Markdown，本报告 §3/§5 的表格即由此产出）
uv run python benches/bakeoff/embed_compare.py aggregate \
  --report ~/.cache/zace-bakeoff/raw-agg.md

# 4) 逐用例名次对比（模型之间差异定位）
uv run python benches/bakeoff/embed_compare.py compare \
  --left multilingual-e5-small__t512 --right bge-small-zh-v1.5__t512
```

**产物落点**：`~/.cache/zace-bakeoff/results/<key>__<repo>.{index,eval}.json`
（+ runner 原件 `<key>__<repo>.eval.raw.md`）。每条 JSON 都记录完整命令、数据根、
仓库 commit、索引范围摘要、指纹（model_id/dim/max_input_tokens）——本报告每个数字都可追溯到它。

**验证**：`uv run pytest benches/bakeoff/test_embed_compare.py`（脚本逻辑，不联网/不加载模型）。
