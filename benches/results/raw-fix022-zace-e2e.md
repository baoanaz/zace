# zace golden eval 报告

- golden：benches/golden/zace（24 条用例）
- repo：/home/xuwenzheng/2_github/AI/ACE/zace-lane-a
- project：adfdd1a626db62b7
- 生成时间：2026-09-10 20:29:14
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 22 |
| recall@5 | 0.682 |
| recall@10 | 0.864 |
| MRR | 0.561 |
| 负例通过 | 0/2 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| en | 5 | 1.000 | 1.000 | 0.767 |
| mixed | 9 | 0.556 | 0.778 | 0.446 |
| zh | 8 | 0.625 | 0.875 | 0.561 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| behavior | 7 | 0.714 | 0.857 | 0.592 |
| path | 3 | 0.333 | 0.667 | 0.122 |
| spec | 5 | 1.000 | 1.000 | 1.000 |
| symbol | 7 | 0.571 | 0.857 | 0.404 |

## 失败清单（正例）

| id | lang | category | query | 期望 | top-3 |
|---|---|---|---|---|---|
| zace-0103 | zh | behavior | 增量索引时怎么判断必须重建向量表？ | core/zace_core/chunking/fingerprint.py#check_fingerprint | docs/design/Module/01-切片存储.md:391-437 (Module 01 — 切片存储（组件详细设计） > 4. 贯穿机制：增量与失效 > 4.2 配置指纹与分层失效（关键，防"策略升级留下脏索引"）) / docs/tasks/TASK-009-向量存储.md:19-28 (TASK-009：向量存储（LanceDB）+ hash 复用对账 > 交付内容) / docs/tasks/TASK-007-索引流水线.md:58-85 (TASK-007：索引流水线（ChangeSet → 增量失效 → 向量对账） > 完成报告（回填）) |
| zace-0113 | mixed | symbol | Indexer.ingest 在什么情况下会触发 full_reparse？ | core/zace_core/pipeline/indexer.py#Indexer | core/zace_core/pipeline/indexer.py:190-205 (Indexer.ingest) / core/tests/pipeline/test_indexer.py:239-286 (test_tampered_parser_hash_triggers_full_reparse) / core/tests/cli/test_cli_ingest.py:89-101 (test_full_flag_triggers_full_reparse) |
| zace-0119 | mixed | path | 索引表结构的契约 SQL 是哪个文件？ | docs/contracts/index-schema.sql | docs/design/Background/02-codegraph.md:49-51 (CodeGraph 调研分析 > 2. 数据模型（src/db/schema.sql，v1 + 9 个 migration） > files 表) / docs/plan/contracts.md:6-21 (契约冻结清单（CF） > 1. 冻结清单) / docs/plan/contracts.md:101-107 (契约冻结清单（CF） > 4. 契约的验证方式（集成保障）) |

## 负例清单

| id | 通过 | query | answerable | missingEvidence |
|---|---|---|---|---|
| zace-0004 | 否 | PaymentGateway 的重试退避逻辑在哪里实现 | True | unresolved_reference, retrieval_truncated |
| zace-0106 | 否 | 支付网关的指数退避重试策略是在哪个文件里实现的？ | True | unresolved_reference, retrieval_truncated |
