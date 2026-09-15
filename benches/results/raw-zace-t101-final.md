# zace golden eval 报告

- golden：benches/golden/zace/zace.jsonl（20 条用例）
- repo：(未绑定仓库：--project-id 模式)
- project：8d6e127fc3a5f8c8
- 生成时间：2026-09-14 23:26:07
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 19 |
| recall@5 | 0.632 |
| recall@10 | 0.684 |
| MRR | 0.480 |
| 负例通过 | 0/1 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| en | 4 | 0.750 | 1.000 | 0.667 |
| mixed | 9 | 0.556 | 0.556 | 0.417 |
| zh | 6 | 0.667 | 0.667 | 0.450 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| behavior | 6 | 0.667 | 0.667 | 0.500 |
| path | 3 | 0.667 | 0.667 | 0.150 |
| spec | 4 | 1.000 | 1.000 | 0.875 |
| symbol | 6 | 0.333 | 0.500 | 0.361 |

## 失败清单（正例）

| id | lang | category | query | 期望 | top-3 |
|---|---|---|---|---|---|
| zace-0102 | zh | symbol | 没有语法结构可解析时，兜底切片是哪个函数生成的？ | core/zace_core/parsing/fallback.py#split_fallback | docs/design/Module/01-切片存储.md:76-174 (Module 01 — 切片存储（组件详细设计） > 2. 第一大类：切片策略（Chunking） > 2.2 各语言的切片难点与规则) / core/zace_core/parsing/cpp.py:92-104 (CppParser.parse) / core/zace_core/parsing/base.py:141-152 (TreeSitterParser) |
| zace-0103 | zh | behavior | 增量索引时怎么判断必须重建向量表？ | core/zace_core/chunking/fingerprint.py#check_fingerprint | docs/design/Module/01-切片存储.md:412-422 (Module 01 — 切片存储（组件详细设计） > 4. 贯穿机制：增量与失效 > 4.2 配置指纹与分层失效（关键，防"策略升级留下脏索引"）) / core/zace_core/engine.py:258-275 (_vector_index_gap) / core/zace_core/pipeline/indexer.py:238-244 (Indexer.full_reparse) |
| zace-0112 | mixed | behavior | 证据块的 E 编号（`E1`、`E2` …）是在哪里分配的？ | core/zace_core/contextpack/assembly.py | core/tests/contextpack/test_score_ratio_grouping.py:327-349 (test_grouping_does_not_renumber_or_reorder_evidence_ids) / core/zace_core/cli/eval.py:283-290 (ordered_evidence) / service/zace_service/packmeta.py:118-138 (evidence_summary) |
| zace-0113 | mixed | symbol | Indexer.ingest 在什么情况下会触发 full_reparse？ | core/zace_core/pipeline/indexer.py#Indexer | core/zace_core/pipeline/indexer.py:229-240 (Indexer.ingest) / core/zace_core/engine.py:578-588 (Engine._ingest) / core/tests/pipeline/test_indexer.py:239-257 (test_tampered_parser_hash_triggers_full_reparse) |
| zace-0114 | mixed | symbol | assemble() 里 SpecBlock 的保底配额是怎么处理的？ | core/zace_core/contextpack/assembly.py#assemble | docs/design/Module/03-上下文组装.md:120-137 (Module 03 — 上下文组装（组件详细设计） > 4. 预算装填算法（D-22） > 4.1 装填主流程) / docs/tasks/TASK-019-spec保底重复装填修复.md:8-39 (TASK-019：spec 保底块重复装填修复（U2）+ 预算不变量测试 > 背景（TASK-013 自举时发现并给出复现路径，编排者已核对代码）) / core/zace_core/contextpack/assembly.py:218-241 (BudgetConfig) |
| zace-0119 | mixed | path | 索引表结构的契约 SQL 是哪个文件？ | docs/contracts/index-schema.sql | docs/design/Background/02-codegraph.md:25-54 (CodeGraph 调研分析 > 2. 数据模型（src/db/schema.sql，v1 + 9 个 migration） > files 表) / docs/contracts/PROCESS.md:35-41 (契约冻结清单（CF） > 3. 规划期与实现期裁定（编排者；需在对应 Module 文档下次修订时回记） > 3.1 规划期裁定（2026-09-10）) / core/tests/storage/test_storage_schema.py:1-26 ((module)) |

## 负例清单

| id | 通过 | query | answerable | missingEvidence |
|---|---|---|---|---|
| zace-0106 | 否 | 支付网关的指数退避重试策略是在哪个文件里实现的？ | True | unresolved_reference, retrieval_truncated |
