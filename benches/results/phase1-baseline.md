# Phase 1 检索质量基线（TASK-014）

> 生成：2026-09-10 ｜ 分支：`feature/task-014_xwz0910`（jump 自 `main` @ `086d24e`）
> 原始报告：`benches/results/raw-*.md`（由 runner 直接产出，未加工）
> 一句话结论：**M1 检索质量基线 = e2e recall@5 0.574 / recall@10 0.611 / MRR 0.451，负例通过率 2/6。**
> 低分集中暴露三个已知/新增问题：文档证据挤占代码证据（R21）、排序判别力不足（R24）、
> `answerable` 判定在文档密集仓库上恒为真（本卡新增，见 §6）。

## 1. 索引状态（评测的前提，必须与用例 `commit` 一起读）

| repo_hint | 仓库路径 | commit | 索引文件数 | chunks | symbols | edges | 索引来源 |
|---|---|---|---|---|---|---|---|
| `zace` | 本仓（`--repo .`） | `self` = `086d24e`（main）+ 编排者既有 `benches/golden/{sample.jsonl,aibox-seed.jsonl}` | 217 | 2412 | 1467 | 7058 | `/tmp/zace-verify-main`（19:34 增量刷新，6s） |
| `aibox-super-sdk` | `/home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk` | `debf8a322aff7d2d21939bc6d09b4cfa985671ea` | 451 扫描 / 434 解析 | 5760 | 2632 | 13269 | `/tmp/zace-aibox`（19:34 增量刷新，1.2s，仅 `internal/maintenance.py` 漂移） |
| `linux-mtk-mw-cameraservice`（自选） | `/home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice` | `3fb0b2d69d81850a630eb5b6ced5d78f5461257c` | 281（+1101 个二进制/不可解码被跳过） | 6257 | 4614 | 2760 | `/tmp/zace-cam`（全新全量索引，559.6s） |

自选仓库的理由：任务卡建议补齐 C/C++ 维度；本机可得的中型 C++17 工程（250 个源文件 + 111 头文件），
含策略/状态机/DBus/Socket/共享内存/渲染多类结构，且**工作区里带 `.claude/skills/**`（50 份 md）与
`cmake-build-release/`**——正好覆盖"没有 ignore 规则时索引会吃什么"这一真实条件。

索引口径注意（写进 `benches/README.md`"用例编写指南"）：

- `DirectorySource` **不读 `.gitignore`**：未跟踪文件同样入库（aibox 多出 10 个 `egg-info/`、`bin/`、`tests/test_scripts/`；
  cameraservice 多出 `CLAUDE.md`、`.claude/**`、构建目录里的 12 个 `.cmake`/12 个 `.make` 等文本文件）。
- `identity_key = sha256(git remote + git 根内相对路径)`：**同一 remote 的不同 worktree 共用同一个 project 目录**
  （`/tmp/zace-verify-main` 里的索引曾经由 `zace` worktree 建立，本次由 `zace-lane-f` 刷新，project_id 不变）。
  报告因此必须写清"索引来自哪个工作区/commit"，不能凭目录名判断。

## 2. 用例集统计（DoD：≥50 条 + 维度达标）

脚本化统计（`load_cases(benches/golden)` + 分仓库 `load_cases`，输出见下）：

```text
=== 全量（benches/golden 目录）
条目数: 60
  lang:     {'en': 14, 'mixed': 20, 'zh': 26}
  category: {'behavior': 16, 'negative': 6, 'path': 10, 'spec': 12, 'symbol': 16}
  repo_hint:{'aibox-super-sdk': 20, 'cameraservice': 16, 'zace': 24}
=== 分仓库
[zace] 24 条 | lang={'en': 5, 'mixed': 9, 'zh': 10} | cat={'behavior': 7, 'negative': 2, 'path': 3, 'spec': 5, 'symbol': 7}
[aibox-super-sdk] 20 条 | lang={'en': 4, 'mixed': 5, 'zh': 11} | cat={'behavior': 5, 'negative': 2, 'path': 4, 'spec': 5, 'symbol': 4}
[cameraservice] 16 条 | lang={'en': 5, 'mixed': 6, 'zh': 5} | cat={'behavior': 4, 'negative': 2, 'path': 3, 'spec': 2, 'symbol': 5}
```

| 维度要求（任务卡） | 要求 | 实际 | 结论 |
|---|---|---|---|
| 条目数 | ≥50 | 60 | 达标 |
| 中文 | ≥15 | 26 | 达标 |
| 英文 | ≥10 | 14 | 达标 |
| 中英混合 | ≥15 | 20 | 达标 |
| 类型覆盖 | symbol/path/behavior/spec/negative | 16/10/16/12/6 | 达标 |
| 仓库数 | 3（zace + aibox-super-sdk + 1 自选） | 3 | 达标 |
| 编排者种子 | aibox 8 条不得删 | 8 条逐字节保留（`git status` 显示为 `R` 纯改名） | 达标 |

文件布局（按仓库分层，一次目录调用 = 一个仓库的完整集；`benches/README.md` 已追加说明）：

```text
benches/golden/{zace/{sample.jsonl,zace.jsonl}, aibox-super-sdk/{aibox-seed.jsonl,aibox.jsonl},
                linux-mtk-mw-cameraservice/cameraservice.jsonl}
```

> 相对 TASK-013 的唯一结构改动：`sample.jsonl` 与 `aibox-seed.jsonl` 移入各自的仓库目录（内容零改动，
> `git status` 为 rename）。原因：runner 一次只接受一个 `--golden` 路径且目录模式递归收集，
> 同目录混放多仓库用例时无法按仓库取指标。`benches/golden`（根）仍可整体跑通（id 全局唯一），
> 但跨仓库用例会对着单个索引跑出必然失败——只作 runner 冒烟，不作指标口径。

## 3. 基线指标

两段口径（TASK-014 冻结，细节见 `benches/README.md`）：

- **① 索引层**：排名来源 = `SearchTrace.candidates`（recall→expand→rerank 后的候选池序），不受 TASK-017/019 的装填影响；
- **② 端到端（e2e）**：`zace-core eval` 默认口径 = `ContextPack` 的 E 编号装填序（agent 实际读到的顺序）。

### 3.1 整体（每仓库一行）

| repo | 段 | 正例数 | recall@5 | recall@10 | MRR | 负例通过 | 向量降级 |
|---|---|---|---|---|---|---|---|
| zace（dogfood） | ① 索引层 | 22 | 0.591 | 0.636 | 0.511 | 1/2 | 0 |
| zace（dogfood） | ② e2e | 22 | 0.636 | 0.682 | 0.529 | 1/2 | 0 |
| aibox-super-sdk | ① 索引层 | 18 | 0.556 | 0.556 | 0.449 | 0/2 | 0 |
| aibox-super-sdk | ② e2e | 18 | 0.556 | 0.611 | 0.455 | 0/2 | 0 |
| linux-mtk-mw-cameraservice | ① 索引层 | 14 | 0.500 | 0.571 | 0.344 | 1/2 | 0 |
| linux-mtk-mw-cameraservice | ② e2e | 14 | 0.500 | 0.500 | 0.324 | 1/2 | 0 |
| **三仓库合并（正例 54）** | ① 索引层 | 54 | **0.556** | **0.593** | **0.447** | — | 0 |
| **三仓库合并（正例 54）** | ② e2e | 54 | **0.574** | **0.611** | **0.451** | **2/6** | 0 |

两段对比（e2e − 索引层）：
`zace +0.045/+0.046/+0.018`、`aibox 0.000/+0.055/+0.006`、`cameraservice 0.000/−0.071/−0.020`、
合并 `+0.018/+0.019/+0.004`。

结论：**装填层整体是"小幅正贡献、局部负贡献"**。正贡献的机制是可见的——`zace-0118`（契约文件
`docs/contracts/mcp-tools.json`）在候选池里排不进 top-10，但被 Docs 分列装填后进了 top-10（e2e 多出 1 条命中）。
负贡献的机制同样可见——`cameraservice-0007`（`MWPAvmPolicy.cpp::OnCarSpeedChanged`）在候选池里在 top-10，
进入 ContextPack 后被 10000 token 预算下的其他证据挤出（e2e 少 1 条命中）。这与 R21（装填失衡）一致：
**装填阶段不是"排序变好"，而是"把 spec/docs 证据抬进最终可见区"**。

### 3.2 按语言（② e2e）

| repo | lang | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|---|
| zace | en | 5 | 1.000 | 1.000 | 0.767 |
| zace | mixed | 9 | 0.556 | 0.667 | 0.422 |
| zace | zh | 8 | 0.500 | 0.500 | 0.500 |
| aibox | en | 4 | 0.750 | 0.750 | 0.750 |
| aibox | mixed | 5 | 0.400 | 0.600 | 0.422 |
| aibox | zh | 9 | 0.556 | 0.556 | 0.343 |
| cameraservice | en | 4 | 0.500 | 0.500 | 0.175 |
| cameraservice | mixed | 6 | 0.500 | 0.500 | 0.389 |
| cameraservice | zh | 4 | 0.500 | 0.500 | 0.375 |
| **合并（e2e）** | en | 13 | 0.769 | 0.769 | 0.580 |
| **合并（e2e）** | mixed | 20 | 0.500 | 0.600 | 0.412 |
| **合并（e2e）** | zh | 21 | 0.524 | 0.524 | 0.409 |
| **合并（①索引层）** | en | 13 | 0.692 | 0.692 | 0.564 |
| **合并（①索引层）** | mixed | 20 | 0.500 | 0.600 | 0.412 |
| **合并（①索引层）** | zh | 21 | 0.524 | 0.524 | 0.409 |

规律：**英文明显领先，中文与中英混合基本持平**（合并口径 e2e：en 0.769/0.769/MRR 0.580，
zh 0.524/0.524/0.409，mixed 0.500/0.600/0.412）。中文与 mixed 的差距很小，说明瓶颈不在"中英混杂"，
而在**中文自然语言无法落成代码符号/路径**——BM25 靠 jieba 分词只能命中文档措辞，
Exact-Inferred 又只抽英文驼峰/裸名，于是中文行为类查询被 Markdown 抢走（§5 前 4 条失败都是这个形态）。

### 3.3 按类型（② e2e）

| repo | category | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|---|
| zace | behavior | 7 | 0.714 | 0.714 | 0.571 |
| zace | path | 3 | 0.000 | 0.333 | 0.033 |
| zace | spec | 5 | 1.000 | 1.000 | 1.000 |
| zace | symbol | 7 | 0.571 | 0.571 | 0.362 |
| aibox | behavior | 5 | 0.600 | 0.600 | 0.600 |
| aibox | path | 4 | 0.000 | 0.000 | 0.000 |
| aibox | spec | 5 | 0.800 | 1.000 | 0.689 |
| aibox | symbol | 4 | 0.750 | 0.750 | 0.438 |
| cameraservice | behavior | 4 | 0.500 | 0.500 | 0.175 |
| cameraservice | path | 3 | 0.333 | 0.333 | 0.167 |
| cameraservice | spec | 2 | 0.500 | 0.500 | 0.167 |
| cameraservice | symbol | 5 | 0.600 | 0.600 | 0.600 |
| **合并（e2e）** | behavior | 16 | 0.625 | 0.625 | 0.481 |
| **合并（e2e）** | path | 10 | 0.100 | 0.200 | 0.060 |
| **合并（e2e）** | spec | 12 | 0.833 | 0.917 | 0.732 |
| **合并（e2e）** | symbol | 16 | 0.625 | 0.625 | 0.455 |
| **合并（①索引层）** | behavior | 16 | 0.688 | 0.688 | 0.497 |
| **合并（①索引层）** | path | 10 | 0.100 | 0.100 | 0.050 |
| **合并（①索引层）** | spec | 12 | 0.750 | 0.833 | 0.704 |
| **合并（①索引层）** | symbol | 16 | 0.563 | 0.625 | 0.453 |

规律：**`path` 类是最弱的一类（10 条里只有 1 条进 top-5，e2e 2 条进 top-10；索引层只有 1 条）**；
`spec` 在文档密集仓库（zace 1.000、aibox 0.800-1.000）很稳，但在文档稀薄的 C++ 仓库（0.500）不稳；
`symbol` 类锁定在 0.57-0.75——失败主因不是"找不到文件"，而是符号断言口径（§5 #6）。

## 4. 负例口径与 R17 实测（本卡定的口径 + 实测证据）

口径（已写入 `benches/README.md` 用例编写指南第 3-4 条）：

1. 负例概念必须用 `grep -ril` 在**被索引的文件集**（含未跟踪文件、构建目录文本文件，排除 `.git`/`.venv`）上核验 0 命中；
2. zace dogfood 的负例，因为 `benches/golden/**`、`benches/results/**` 都在被索引仓库内，**查询原文必然被自身命中**，
   只能以"该 query 在 `core/`、`docs/` 中无对应实现"为前提，并在报告里标注本次索引是否包含 golden 文件；
3. 判定以运行结果为准：`answerable=False` 且 `missingEvidence` 非空（runner 的 `CaseResult.passed`）。

### 4.1 种子负例 `aibox-0008` 的前提已过期（不删题，记录归因）

任务卡/README 记的是"kubernetes/ArgoCD/PaymentGateway 在该仓库源码中 0 命中"。实测：
`grep -ril "Kubernetes"` 得到 4 个命中，但**全部是仓库根 `README.md` 与未跟踪的
`src/aibox_sdk.egg-info/PKG-INFO`**（GitLab 模板样板文"Deploy to Kubernetes…"），源码目录内确实 0 命中
（ArgoCD、PaymentGateway 全仓库 0 命中）。结论：**"源码 0 命中"仍然成立，"被索引文件集 0 命中"不成立**——
核验口径必须以 `DirectorySource` 的实际文件集为准（README 指南已改成这一条）。该题按运行结果计为"不通过"，
不删不改（保留作为"负例口径受索引范围影响"的回归样本）。

### 4.2 R17 对照实验：把本轮新增的 golden 文件加进索引，负例通过率 1/2 → 0/2

| 运行 | zace 索引是否含本轮新增 `benches/golden/*.jsonl` | 正例 recall@5/@10/MRR | 负例通过 |
|---|---|---|---|
| `raw-baseline-zace-e2e.md`（**主基线**） | 否（索引停留在 19:34 的 217 文件状态） | 0.636 / 0.682 / 0.529 | **1/2**（`zace-0106` 通过） |
| `raw-baseline-zace-e2e-golden-indexed.md`（对照） | 是（+13 个文件：3 个新代码集文件 + 移位的 2 个 + 5 个 raw 报告） | 0.636 / 0.636 / 0.524 | **0/2**（`zace-0106` 转为 `answerable=true`） |

对照实验中 `zace-0106`（"支付网关的指数退避重试策略是在哪个文件里实现的？"）被自己的题目文本命中：
`benches/results/raw-baseline-zace-e2e.md` + `benches/golden/zace/zace.jsonl` 进入候选两侧通道
（BM25 + Vector 双通道 = `consensus>=2`）→ `answerable=true` → 负例判定失败。
**同一现象在编排者样例题 `zace-0004` 上已经稳定复现**（两次运行都失败），`zace-core search` 的 top-2 是：

```text
[E1] GOLDEN_CASES — core/tests/cli/eval.py:29-57                              reason: bm25 rank 1 + vector rank 1 ...
[E2] (module) — benches/golden/sample.jsonl:1-4                               reason: bm25 rank 2 + vector rank 3 ...
```

结论：**R17 在 dogfood 仓库上是结构性的**，只要 `benches/**` 在索引内，任何 self-dogfood 负例都不可通过；
TASK-015 校准前需要二选一（见 §6 未决问题 1）：runner 加 `--exclude` 口径排除 `benches/**`，
或在 eval 前用一个不含 `benches/` 的 data root 建索引。

### 4.3 外部仓库负例：4 条里 3 条失败，失败原因是 `answerable` 判定而非召回

| id | 仓库 | query | 通过 | answerable | missingEvidence |
|---|---|---|---|---|---|
| aibox-0008 | aibox | Kubernetes operator 的部署协调逻辑在哪里实现？ | 否 | true | unresolved_reference, retrieval_truncated |
| aibox-0020 | aibox | RabbitMQ 的消息确认（ack）机制在哪里实现？ | 否 | true | unresolved_reference, retrieval_truncated |
| cameraservice-0005 | cameraservice | Terraform 的资源依赖图是在哪个文件里构建的？ | 否 | true | unresolved_reference, retrieval_truncated |
| cameraservice-0010 | cameraservice | Where is the gRPC service definition for the parking assist module? | 是 | false | unresolved_reference, retrieval_truncated |

这 4 条都**没有**所谓"强相关证据"（`missingEvidence` 都如实报了 `unresolved_reference`），但 3 条仍被判 `answerable=true`。
根因见 §5 #10。

## 5. 失败 Top10 归因（② e2e；括号内为①索引层的差异）

| # | 用例 | 现象 | 归因（初判） |
|---|---|---|---|
| 1 | `zace-0103` zh behavior（①也失败） | "增量索引时怎么判断必须重建向量表"期望 `chunking/fingerprint.py#check_fingerprint`，top-3 全是 `docs/design/Module/01-切片存储.md`、`docs/tasks/TASK-007/009` | **R21 文档压代码**：中文行为问题的 BM25 命中全在同义措辞的设计文档上；代码块只能靠 Vector 单通道进池，RRF 后被文档挤掉。属"docs 装填失衡 + 排序判别力"叠加 |
| 2 | `zace-0102` zh symbol（①也失败） | "兜底切片是哪个函数"期望 `parsing/fallback.py#split_fallback`，top-3 全是 Module/01 §2.2 的三段同章节切片 | 同上；且该 query 无英文标识符 → Exact-Inferred 空手，`fallback.py` 只能靠 Vector 进池 |
| 3 | `aibox-0004` / `aibox-0007` / `aibox-0009` / `aibox-0012`（①也失败） | 4 条中文查询的目标都在 `search/`、`add/strategies/`，返回的却是 `doc/车载记忆系统需求/`、`doc/V1.0/**/Phase-8/设计文档.md`、`doc/记忆系统调研/` | **文档密度 146 md vs 83 py 的直接后果**：同样的中文措辞在 md 里重复度高、在 py 里几乎没有对应词；`aibox-0009` 唯一命中的代码块（`planner.py:12-19 RetrievalPlan`）被两条 md 夹在中间 |
| 4 | `aibox-0011` / `aibox-0015` / `aibox-0017` | 三条 `path` 类查询（`storage/vector/qdrant_edge.py`、`internal/maintenance.py`、`delete/strategies/evidence.py`）top-3 里出现 `miner/README.md`、`docs/API.md`、`Phase-9/设计文档.md`、`tests/…/test_memory_lifecycle.py` | `path` 类全灭的典型形态：文件路径本身在查询里没有字面出现，语义相近的**文档与测试**先被召回。`aibox-0015` 还暴露"测试名包含目标文件名"的强干扰 |
| 5 | `zace-0107` zh path（①也失败） | "FTS5 写入在哪个文件"期望 `core/zace_core/storage/store.py`，top-3 是 `Background/06`、`Module/01`、`TASK-001` | 与 #1 同源：`FTS5` 这个字面量在**文档里出现次数多于代码**（代码里是 `chunks_fts` 表名），BM25 天然偏向文档 |
| 6 | `zace-0113` mixed symbol（①也失败） | 期望 `pipeline/indexer.py#Indexer`，**top-1 就是 `pipeline/indexer.py:190-205 (Indexer.ingest)`**，但仍判为失败 | **runner 符号口径问题**：`_mentions_symbol` 是单向匹配（证据符号须等于期望符号或以 `.symbol`/`::symbol` 结尾，或正文按词边界出现），`Indexer.ingest` 不满足 `Indexer`，"路径命中但符号不匹配"→ rank=None。属判定口径，不是召回失败（②的 recall@10 因此少 1 条） |
| 7 | `zace-0119` mixed path（①也失败） | "索引表结构契约 SQL 是哪个文件"期望 `docs/contracts/index-schema.sql`，top-3 是 `Background/02-codegraph.md`（含 `src/db/schema.sql`）、`plan/contracts.md` | 近名干扰：`schema.sql`（文档里讨论的 codegraph 文件、以及 `core/zace_core/storage/schema.sql`）比契约文件更"像"答案；契约类文件（`.sql`/`.json`）在 BM25 里几乎没有可命中的自然语言上下文 |
| 8 | `zace-0118` mixed path（**①失败 / ②通过**） | 期望 `docs/contracts/mcp-tools.json`，候选池进不了 top-10，e2e 进了 top-10 | 装填层的**正贡献**样本：Docs 分列 + spec 保底把契约文件抬进可见区（TASK-019 的保底去重在这里生效） |
| 9 | `cameraservice-0008` en spec（①也失败） | "two-process architecture" 期望 `CLAUDE.md`，top-3 全是 `.claude/skills/**/references/*.md` | **索引范围问题**：`.claude/` 是 gitignore 但不在 `DEFAULT_SKIP_DIRS`，50 份 skill 文档入库后成为最强的英文文档信号（同形态还出现在 `cameraservice-0006`） |
| 10 | `cameraservice-0007` en behavior（**①通过 / ②失败**） | 期望 `MWPAvmPolicy.cpp#OnCarSpeedChanged`，候选池在 top-10，e2e 掉出 | 装填层的**负贡献**样本：10000 token 预算下与 #1/#3 同源的文档证据优先装填，把代码块挤出去 |
| （附）`cameraservice-0001/0003/0013/0014/0015` | 中文/混合查询的目标是 `.h`/`.cpp`，返回 `common/Constants.h`、`Data/MWPCameraData.h`、`CLAUDE.md`、近似名 `libcamera/MWPLogoFile.h` | 与 #4 同源（C++ 头文件之间语义相似度高、宏/枚举块被当成高关联证据）；`cameraservice-0014` 是"同名回调在 4 个文件里都有实现"的歧义题，期望写成两条仍只命中 policy 头文件 |
| （附）`zace-0001`（编排者样例题，①也失败） | 期望 `types.py#ChunkDef`，top-1 是 `chunking/splitter.py::chunk_id` | **题面/期望分歧，不是检索失败**：`chunk_id` 的**构造**在 `splitter.py`，`types.py` 只有字段定义。建议 TASK-015 复核该题期望（不删题） |

**失败模式归纳（Top10 之外也适用）**：
`docs/spec 挤占 code`（#1/#2/#3/#5/#9）、`path 类无字面路径 → 靠语义竞争`（#4）、
`近名/同名干扰`（#7/#14）、`符号单向匹配口径`（#6）、`装填预算把代码块挤出`（#10）。

## 6. 契约影响 / 与设计偏差 / 未决问题

**契约影响**：无。本卡只新增/移动 `benches/golden/**`、新增 `benches/results/**`、追加 `benches/README.md` 一节；
未触碰 `core/**`、`docs/contracts/**`、`docs/design/**`、`docs/tasks/*`（除本卡执行记录与任务板状态行）。

**与设计偏差**：无。两段基线口径（索引层 / 端到端）与 Module/02 §7-1 的"golden set + 排序回归"一致；
`--golden` 目录语义（一次一个仓库）由 TASK-013 的 CLI 形态决定，本卡通过目录分层适配，未改代码。

**未决问题（建议编排者开卡）**：

1. **R17 需要口径级解法**：dogfood 负例在 `benches/**` 被索引时不可能通过（§4.2 实测 1/2 → 0/2，
   且 `bench` 报告产物自己也会被召回）。建议二选一：runner 增加 `--exclude '<glob>'`（并让报告记录排除项），
   或 TASK-015 规定"负例回归用不含 `benches/` 的 data root"。**在此之前，dogfood 负例不得作为 CI 门禁**。
2. **`answerable` 判定在文档密集仓库上恒为真**（§4.3）：`assembly._assess` 的
   `answerable = explicit_hits >= 1 or consensus >= 2 or structural_result`，其中 `consensus` 只数
   "≥2 通道共同命中"的候选数——任何中文 query 在 md 密集仓库上都能凑出 2 条 BM25+Vector 双命中，
   于是负例必然 `answerable=true`（哪怕 `missingEvidence` 已报 `unresolved_reference`）。
   建议 TASK-015/新卡讨论：`consensus` 是否应附加"与 query 实体同族"约束，或让 `missingEvidence`
   非空时对 `answerable` 有一票否决/降置信。**这属于 Module/03 §4.4 口径，实施 AI 不动。**
3. **runner 缺"索引层"开关**：本卡的①段用十行 `Engine.search_with_trace` 脚本实现（§7 附录），
   未入库（`benches/` 根属 TASK-013 所有权）。建议 TASK-015 在 `zace-core eval` 加 `--stage index|e2e`，
   让两段对比成为可回归的默认能力。
4. **符号断言口径**（§5 #6）：`Indexer.ingest` 不满足期望符号 `Indexer`，导致"路径命中"记失败。
   建议评估是否允许"期望符号是证据符号的前缀（父类/模块）"也算命中——目前只能在用例里写两条 `expected` 绕过。
5. **索引范围不含 ignore 规则**：`.claude/`、`egg-info/`、`cmake-build-*/**/*.cmake` 都进了索引
   （cameraservice 因此多出 6 万 token 级干扰，`cameraservice-0006/0008` 直接受害）。
   Module/05 §3.1 的 D-28 忽略规则三层还没在 `DirectorySource` 落地，建议排期（影响所有外部仓库基线）。
6. **用例期望待复核 2 条**：`zace-0001`（构造点 vs 定义点的分歧）、`aibox-0008`（负例前提口径）。
   两者都**不删题**，已按运行结果如实计入基线。

## 7. 复现步骤

```bash
# 0) 索引（可复用，本报告使用的 data root 与 commit 见 §1）
uv run zace-core ingest --repo . --data /tmp/zace-verify-main
uv run zace-core ingest --repo /home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk --data /tmp/zace-aibox
uv run zace-core ingest --repo /home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice --data /tmp/zace-cam

# 1) 端到端（②，runner 原生命令；逐仓库）
uv run zace-core eval --golden benches/golden/zace --repo . --data /tmp/zace-verify-main \
  --report benches/results/raw-baseline-zace-e2e.md
uv run zace-core eval --golden benches/golden/aibox-super-sdk \
  --repo /home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk --data /tmp/zace-aibox \
  --report benches/results/raw-baseline-aibox-e2e.md
uv run zace-core eval --golden benches/golden/linux-mtk-mw-cameraservice \
  --repo /home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice --data /tmp/zace-cam \
  --report benches/results/raw-baseline-cameraservice-e2e.md

# 2) runner 冒烟（DoD 的全量命令：60 条一次性跑通，指标无意义，只验解析与不中断）
uv run zace-core eval --golden benches/golden --repo . --data /tmp/zace-verify-main \
  --report benches/results/raw-smoke-all-repos-on-zace.md   # → 60 条全部执行，0 异常

# 3) 索引层（①，脚本见附录，未入库）
uv run python /tmp/zace_stage1.py --golden benches/golden/zace --repo . \
  --data /tmp/zace-verify-main --report benches/results/raw-baseline-zace-index.md
```

冒烟运行结果（`raw-smoke-all-repos-on-zace.md`）：60 条用例全部执行、`向量通道降级用例数=0`、
无 runner 异常；整体 recall@5 0.259 / recall@10 0.278 / MRR 0.215、负例通过 2/6 ——
**这组数字没有质量含义**（36 条用例的目标文件不在 zace 索引里），仅证明"用例集可被 runner 完整解析与执行"。

### 附录：①索引层脚本（未入库，~40 行）

```python
# /tmp/zace_stage1.py 核心：与 runner 的唯一区别是排名来源换成 SearchTrace.candidates
from zace_core.cli.eval import load_cases, CaseResult, GoldenReport, render_report, write_report
from zace_core.engine import Engine, resolve_data_root

def symbol_match(symbol_fqn, symbol):   # 候选池里没有正文，只能按符号字段判定（比 runner 略严）
    return bool(symbol_fqn) and (symbol_fqn == symbol or symbol_fqn.endswith(f".{symbol}")
                                 or symbol_fqn.endswith(f"::{symbol}"))

cases = load_cases(golden)
with Engine.open(resolve_data_root(data)) as engine:
    handle, _ = engine.resolve_repo(repo)
    results = []
    for case in cases:
        trace = engine.search_with_trace(handle.project_id, case.query, 10_000)
        rank = next((i for i, c in enumerate(trace.candidates[:10], 1)
                     if any(c.path == e.path and (e.symbol is None or symbol_match(c.symbol_fqn, e.symbol))
                            for e in case.expected)), None)
        results.append(CaseResult(case=case, rank=rank, top=(),
                                  answerable=trace.pack.answerable,
                                  missing_evidence=tuple(m.code for m in trace.pack.missing_evidence),
                                  degraded=trace.degraded, evidence_count=len(trace.candidates)))
report = GoldenReport(golden=golden + "（候选池序）", repo=repo, project_id=handle.project_id,
                      results=tuple(results), top_k=10)
print(render_report(report), end=""); write_report(report, report_path)
```
