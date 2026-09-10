# zace golden eval 报告

- golden：benches/golden/aibox-super-sdk（20 条用例）
- repo：/home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk
- project：8f39057792cf72e8
- 生成时间：2026-09-10 20:29:27
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 18 |
| recall@5 | 0.556 |
| recall@10 | 0.667 |
| MRR | 0.466 |
| 负例通过 | 1/2 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| en | 4 | 0.750 | 0.750 | 0.750 |
| mixed | 5 | 0.400 | 0.600 | 0.422 |
| zh | 9 | 0.556 | 0.667 | 0.364 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| behavior | 5 | 0.600 | 0.600 | 0.600 |
| path | 4 | 0.000 | 0.250 | 0.028 |
| spec | 5 | 0.800 | 0.800 | 0.667 |
| symbol | 4 | 0.750 | 1.000 | 0.486 |

## 失败清单（正例）

| id | lang | category | query | 期望 | top-3 |
|---|---|---|---|---|---|
| aibox-0004 | zh | path | 记忆检索的执行流程在哪个文件里实现？ | src/aibox/capabilities/memory/search/pipeline.py / src/aibox/capabilities/memory/search/planner.py | src/aibox/capabilities/memory/doc/车载记忆系统需求/车载记忆系统需求.md:91-101 (车载记忆系统需求 > 2. 系统架构 > 2.2 记忆四流程模型) / src/aibox/capabilities/memory/doc/记忆系统调研/记忆系统调研.md:644-666 (记忆系统调研 > 2. 各系统深度调研 > 2.4 LightMem > ③ 记忆四流程) / src/aibox/capabilities/memory/doc/记忆系统调研/记忆系统调研.md:63-84 (记忆系统调研 > 1. 评估框架：记忆四流程 > 1.3 提取（Retrieval）) |
| aibox-0007 | mixed | behavior | search planner 是怎么做检索策略规划的？ | src/aibox/capabilities/memory/search/planner.py | src/aibox/capabilities/memory/doc/车载记忆系统需求/车载记忆系统需求.md:554-595 (车载记忆系统需求 > 6. 记忆提取与调用 > 6.3 检索策略：混合检索 + 时间衰减 + 多样性) / src/aibox/capabilities/memory/doc/V1.0/任务文档/Phase-8/设计文档.md:78-89 (Phase 8：Evidence 检索——设计文档 > 9. 详细设计方案（已冻结） > 9.1 查询调用链) / src/aibox/capabilities/memory/doc/记忆系统调研/记忆系统调研.md:823-836 (记忆系统调研 > 2. 各系统深度调研 > 2.5 MemPalace > ⑤ 关键算法/机制) |
| aibox-0011 | zh | path | 记忆向量的 qdrant edge 索引实现在哪个文件？ | src/aibox/capabilities/memory/storage/vector/qdrant_edge.py | src/aibox/capabilities/memory/miner/README.md:11-20 (Miner 用户手册检索 > 索引包结构) / docs/API.md:646-668 (AIBox SDK 接口文档（v2.0） > 5. 各能力用法 > 5.8 Memory 持久化记忆 > 5.8.5 持久化配置) / src/aibox/capabilities/memory/doc/记忆系统调研/记忆系统调研.md:813-822 (记忆系统调研 > 2. 各系统深度调研 > 2.5 MemPalace > ④ 数据结构与存储后端) |
| aibox-0012 | zh | behavior | 记忆写入时的 indexed 策略流程做了什么？ | src/aibox/capabilities/memory/add/strategies/indexed.py#add_event | src/aibox/capabilities/memory/doc/V1.0/结构化记忆写入计划.md:42-77 (V1.0 结构化记忆写入计划（V0.1） > 2. 接口与写入流程 > 2.2 最小流程) / src/aibox/capabilities/memory/doc/V1.0/结构化记忆写入计划.md:28-41 (V1.0 结构化记忆写入计划（V0.1） > 1. 设计结论 > 1.1 不做什么) / src/aibox/capabilities/memory/doc/记忆系统调研/记忆抽取机制对照.md:31-50 (记忆抽取机制对照 > V1 抽取与更新规则 > 写入流程) |
| aibox-0015 | en | path | Where does the retention maintenance loop live and what does it clean up? | src/aibox/capabilities/memory/internal/maintenance.py | tests/test_capabilities/test_memory_lifecycle.py:66-98 (test_maintenance_ttl_soft_deletes_and_purges_evidence) / src/aibox/capabilities/base.py:437-449 (CapabilityRegistry.cleanup_all) / README.md:47-93 (Editing this README) |
| aibox-0019 | mixed | spec | 记忆系统的性能验收指标记录在哪个文档里？ | src/aibox/capabilities/memory/doc/P11性能验收报告.md | src/aibox/capabilities/memory/doc/记忆系统1.0详细设计.md:519-522 (记忆系统 1.0 详细设计 > 11. 性能与验收口径) / src/aibox/capabilities/memory/doc/V1.0/V1.0开发计划进展.md:718-723 (记忆系统 V1.0 开发计划与进展 > 13. 初始化记录 > 2026-07-21（Phase 11：硬件无关软件验收口径确认）) / src/aibox/capabilities/memory/doc/V1.0验收报告.md:1-42 (记忆系统 V1.0 验收报告 > 1. 当前结论) |

## 负例清单

| id | 通过 | query | answerable | missingEvidence |
|---|---|---|---|---|
| aibox-0008 | 是 | Kubernetes operator 的部署协调逻辑在哪里实现？ | False | unresolved_reference, retrieval_truncated |
| aibox-0020 | 否 | RabbitMQ 的消息确认（ack）机制在哪里实现？ | True | unresolved_reference, retrieval_truncated |
