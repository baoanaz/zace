# zace golden eval 报告

- golden：benches/golden/zace（索引层口径：候选池序）（24 条用例）
- repo：.
- project：adfdd1a626db62b7
- 生成时间：2026-09-10 19:40:34
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 22 |
| recall@5 | 0.591 |
| recall@10 | 0.636 |
| MRR | 0.511 |
| 负例通过 | 1/2 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| en | 5 | 1.000 | 1.000 | 0.767 |
| mixed | 9 | 0.444 | 0.556 | 0.380 |
| zh | 8 | 0.500 | 0.500 | 0.500 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| behavior | 7 | 0.714 | 0.714 | 0.536 |
| path | 3 | 0.000 | 0.000 | 0.000 |
| spec | 5 | 1.000 | 1.000 | 1.000 |
| symbol | 7 | 0.429 | 0.571 | 0.357 |

## 失败清单（正例）

| id | lang | category | query | 期望 | top-3 |
|---|---|---|---|---|---|
| zace-0001 | zh | symbol | chunk_id 是怎么构成的？ | core/zace_core/types.py#ChunkDef | core/zace_core/chunking/splitter.py:74-76 (chunk_id) [inferred#1,vector#6] / core/zace_core/pipeline/indexer.py:347-367 (Indexer._embed_new) [bm25#5,vector#25] / benches/README.md:14-34 (benches — golden set 与基准回归 > 用例格式（JSONL，一行一条）) [bm25#2] |
| zace-0102 | zh | symbol | 没有语法结构可解析时，兜底切片是哪个函数生成的？ | core/zace_core/parsing/fallback.py#split_fallback | docs/design/Module/01-切片存储.md:171-174 (Module 01 — 切片存储（组件详细设计） > 2. 第一大类：切片策略（Chunking） > 2.2 各语言的切片难点与规则 > 兜底（所有语言）) [bm25#10,vector#1] / docs/design/Module/01-切片存储.md:89-98 (Module 01 — 切片存储（组件详细设计） > 2. 第一大类：切片策略（Chunking） > 2.2 各语言的切片难点与规则 > C（语义简单，工程坑多）) [bm25#3,vector#12] / docs/design/Module/01-切片存储.md:80-88 (Module 01 — 切片存储（组件详细设计） > 2. 第一大类：切片策略（Chunking） > 2.2 各语言的切片难点与规则 > Python（最简单，先做）) [bm25#8,vector#7] |
| zace-0103 | zh | behavior | 增量索引时怎么判断必须重建向量表？ | core/zace_core/chunking/fingerprint.py#check_fingerprint | docs/design/Module/01-切片存储.md:412-422 (Module 01 — 切片存储（组件详细设计） > 4. 贯穿机制：增量与失效 > 4.2 配置指纹与分层失效（关键，防"策略升级留下脏索引"）) [bm25#6,vector#35] / docs/tasks/TASK-007-索引流水线.md:82-85 (TASK-007：索引流水线（ChangeSet → 增量失效 → 向量对账） > 完成报告（回填）) [bm25#11,vector#1] / docs/tasks/TASK-009-向量存储.md:19-28 (TASK-009：向量存储（LanceDB）+ hash 复用对账 > 交付内容) [bm25#1,vector#11] |
| zace-0107 | zh | path | 切片落库时 FTS5 的写入是在哪个文件里处理的？ | core/zace_core/storage/store.py | docs/design/Background/06-core-engine-proposal.md:175-197 (zace 核心引擎技术方案：切片存储、混合检索与可选 AI 总结 > 2. 检索策略（核心） > 2.1 四路并行召回) [bm25#1,vector#26] / docs/design/Module/01-切片存储.md:14-40 (Module 01 — 切片存储（组件详细设计） > 0. 组件定位) [bm25#48,vector#9] / docs/tasks/TASK-001-存储层.md:47-57 (TASK-001：存储层（SQLite schema / FTS5 / jieba 预分词） > 验收标准（DoD）) [bm25#6,vector#7] |
| zace-0112 | mixed | behavior | 证据块的 E 编号（`E1`、`E2` …）是在哪里分配的？ | core/zace_core/contextpack/assembly.py | docs/design/Module/03-上下文组装.md:36-99 (Module 03 — 上下文组装（组件详细设计） > 2. ContextPack 正式合同（v1，D-21）) [bm25#2,vector#25] / docs/design/Module/04-AI总结.md:80-122 (Module 04 — AI 总结（组件详细设计） > 4. Grounded Prompt（正式版）) [bm25#31,vector#7] / docs/design/Module/03-上下文组装.md:227-239 (Module 03 — 上下文组装（组件详细设计） > 9. 与外部建议稿（本文覆盖前版本）的对照) [bm25#26,vector#13] |
| zace-0113 | mixed | symbol | Indexer.ingest 在什么情况下会触发 full_reparse？ | core/zace_core/pipeline/indexer.py#Indexer | core/zace_core/pipeline/indexer.py:190-197 (Indexer.ingest) [bm25#6,exact#1,vector#10] / core/zace_core/pipeline/indexer.py:199-201 (Indexer.full_reparse) [bm25#10,inferred#1,vector#1] / core/tests/pipeline/test_indexer.py:239-257 (test_tampered_parser_hash_triggers_full_reparse) [bm25#1,vector#2] |
| zace-0118 | mixed | path | MCP 工具 schema 的契约文件放在哪里？ | docs/contracts/mcp-tools.json | docs/design/Module/05-MCP与同步.md:42-56 (Module 05 — MCP 与同步（组件详细设计） > 2. MCP 适配层 > 2.1 工具 Schema（正式定义，保持简单——不暴露 rrf_k/graph_depth 等内部参数）) [bm25#1,vector#1] / docs/design/Background/02-codegraph.md:104-116 (CodeGraph 调研分析 > 6. MCP 工具面（8 个）) [bm25#7,vector#3] / docs/design/Background/04-gitnexus.md:108-116 (GitNexus 调研分析 > 9. MCP 工具面（16+）) [bm25#2,vector#13] |
| zace-0119 | mixed | path | 索引表结构的契约 SQL 是哪个文件？ | docs/contracts/index-schema.sql | docs/design/Background/02-codegraph.md:49-51 (CodeGraph 调研分析 > 2. 数据模型（src/db/schema.sql，v1 + 9 个 migration） > files 表) [bm25#3,vector#11] / docs/plan/contracts.md:6-21 (契约冻结清单（CF） > 1. 冻结清单) [bm25#8,vector#5] / docs/plan/contracts.md:101-107 (契约冻结清单（CF） > 4. 契约的验证方式（集成保障）) [bm25#11,vector#6] |

## 负例清单

| id | 通过 | query | answerable | missingEvidence |
|---|---|---|---|---|
| zace-0004 | 否 | PaymentGateway 的重试退避逻辑在哪里实现 | True | unresolved_reference, retrieval_truncated |
| zace-0106 | 是 | 支付网关的指数退避重试策略是在哪个文件里实现的？ | False | unresolved_reference, retrieval_truncated |
