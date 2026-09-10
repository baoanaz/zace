# zace golden eval 报告

- golden：benches/golden/zace（24 条用例）
- repo：/home/xuwenzheng/2_github/AI/ACE/zace-lane-f
- project：adfdd1a626db62b7
- 生成时间：2026-09-10 19:39:53
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 22 |
| recall@5 | 0.636 |
| recall@10 | 0.682 |
| MRR | 0.529 |
| 负例通过 | 1/2 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| en | 5 | 1.000 | 1.000 | 0.767 |
| mixed | 9 | 0.556 | 0.667 | 0.422 |
| zh | 8 | 0.500 | 0.500 | 0.500 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| behavior | 7 | 0.714 | 0.714 | 0.571 |
| path | 3 | 0.000 | 0.333 | 0.033 |
| spec | 5 | 1.000 | 1.000 | 1.000 |
| symbol | 7 | 0.571 | 0.571 | 0.362 |

## 失败清单（正例）

| id | lang | category | query | 期望 | top-3 |
|---|---|---|---|---|---|
| zace-0001 | zh | symbol | chunk_id 是怎么构成的？ | core/zace_core/types.py#ChunkDef | core/zace_core/chunking/splitter.py:74-81 (chunk_id) / core/zace_core/pipeline/indexer.py:347-400 (Indexer._embed_new) / benches/README.md:1-72 (benches — golden set 与基准回归 > 用例格式（JSONL，一行一条）) |
| zace-0102 | zh | symbol | 没有语法结构可解析时，兜底切片是哪个函数生成的？ | core/zace_core/parsing/fallback.py#split_fallback | docs/design/Module/01-切片存储.md:41-217 (Module 01 — 切片存储（组件详细设计） > 2. 第一大类：切片策略（Chunking） > 2.2 各语言的切片难点与规则 > 兜底（所有语言）) / docs/design/Module/01-切片存储.md:80-98 (Module 01 — 切片存储（组件详细设计） > 2. 第一大类：切片策略（Chunking） > 2.2 各语言的切片难点与规则 > C（语义简单，工程坑多）) / docs/design/Background/06-core-engine-proposal.md:1-232 (zace 核心引擎技术方案：切片存储、混合检索与可选 AI 总结 > 1. 切片存储 > 1.1 核心原则：不要按行切，按符号切) |
| zace-0103 | zh | behavior | 增量索引时怎么判断必须重建向量表？ | core/zace_core/chunking/fingerprint.py#check_fingerprint | docs/design/Module/01-切片存储.md:391-437 (Module 01 — 切片存储（组件详细设计） > 4. 贯穿机制：增量与失效 > 4.2 配置指纹与分层失效（关键，防"策略升级留下脏索引"）) / docs/tasks/TASK-007-索引流水线.md:42-169 (TASK-007：索引流水线（ChangeSet → 增量失效 → 向量对账） > 完成报告（回填）) / docs/tasks/TASK-009-向量存储.md:1-110 (TASK-009：向量存储（LanceDB）+ hash 复用对账 > 交付内容) |
| zace-0107 | zh | path | 切片落库时 FTS5 的写入是在哪个文件里处理的？ | core/zace_core/storage/store.py | docs/design/Background/06-core-engine-proposal.md:27-232 (zace 核心引擎技术方案：切片存储、混合检索与可选 AI 总结 > 2. 检索策略（核心） > 2.1 四路并行召回) / docs/design/Module/01-切片存储.md:1-40 (Module 01 — 切片存储（组件详细设计） > 0. 组件定位) / docs/tasks/TASK-001-存储层.md:47-57 (TASK-001：存储层（SQLite schema / FTS5 / jieba 预分词） > 验收标准（DoD）) |
| zace-0112 | mixed | behavior | 证据块的 E 编号（`E1`、`E2` …）是在哪里分配的？ | core/zace_core/contextpack/assembly.py | docs/design/Module/03-上下文组装.md:36-117 (Module 03 — 上下文组装（组件详细设计） > 2. ContextPack 正式合同（v1，D-21）) / docs/design/Module/04-AI总结.md:1-197 (Module 04 — AI 总结（组件详细设计） > 4. Grounded Prompt（正式版）) / docs/design/Module/03-上下文组装.md:227-239 (Module 03 — 上下文组装（组件详细设计） > 9. 与外部建议稿（本文覆盖前版本）的对照) |
| zace-0113 | mixed | symbol | Indexer.ingest 在什么情况下会触发 full_reparse？ | core/zace_core/pipeline/indexer.py#Indexer | core/zace_core/pipeline/indexer.py:190-205 (Indexer.ingest) / core/tests/pipeline/test_indexer.py:239-286 (test_tampered_parser_hash_triggers_full_reparse) / core/tests/cli/test_cli_ingest.py:89-101 (test_full_flag_triggers_full_reparse) |
| zace-0119 | mixed | path | 索引表结构的契约 SQL 是哪个文件？ | docs/contracts/index-schema.sql | docs/design/Background/02-codegraph.md:1-148 (CodeGraph 调研分析 > 2. 数据模型（src/db/schema.sql，v1 + 9 个 migration） > files 表) / docs/plan/contracts.md:6-21 (契约冻结清单（CF） > 1. 冻结清单) / docs/plan/contracts.md:93-107 (契约冻结清单（CF） > 4. 契约的验证方式（集成保障）) |

## 负例清单

| id | 通过 | query | answerable | missingEvidence |
|---|---|---|---|---|
| zace-0004 | 否 | PaymentGateway 的重试退避逻辑在哪里实现 | True | unresolved_reference, retrieval_truncated |
| zace-0106 | 是 | 支付网关的指数退避重试策略是在哪个文件里实现的？ | False | unresolved_reference, retrieval_truncated |
