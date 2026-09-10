# zace golden eval 报告

- golden：benches/golden（60 条用例）
- repo：/home/xuwenzheng/2_github/AI/ACE/zace-lane-f
- project：adfdd1a626db62b7
- 生成时间：2026-09-10 19:45:02
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 54 |
| recall@5 | 0.259 |
| recall@10 | 0.278 |
| MRR | 0.215 |
| 负例通过 | 2/6 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| en | 13 | 0.385 | 0.385 | 0.295 |
| mixed | 20 | 0.250 | 0.300 | 0.190 |
| zh | 21 | 0.190 | 0.190 | 0.190 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| behavior | 16 | 0.312 | 0.312 | 0.250 |
| path | 10 | 0.000 | 0.100 | 0.010 |
| spec | 12 | 0.417 | 0.417 | 0.417 |
| symbol | 16 | 0.250 | 0.250 | 0.158 |

## 失败清单（正例）

| id | lang | category | query | 期望 | top-3 |
|---|---|---|---|---|---|
| aibox-0001 | zh | spec | workflow 在记忆系统里是怎么定义和使用的？ | src/aibox/capabilities/memory/doc/记忆系统调研/记忆系统设计精要.md / src/aibox/capabilities/memory/doc/记忆系统调研/记忆系统调研.md / src/aibox/capabilities/memory/doc/车载记忆系统需求/车载记忆系统需求.md / src/aibox/capabilities/memory/doc/V1.0/任务文档/归档/Phase-3/MEM-V1-P3-001/设计文档.md / src/aibox/capabilities/memory/internal/maintenance.py#maintenance | docs/tasks/TASK-020-BM25判别力修复.md:1-159 (TASK-020：BM25 查询侧噪声 token 过滤（原 IDF 重排方案已被实测否决） > 背景（编排者在真实 demo 仓库上实测，2026-09-10）) / docs/plan/contracts.md:79-92 (契约冻结清单（CF） > 3. 规划期与实现期裁定（编排者；需在对应 Module 文档下次修订时回记） > 3.5 真实靶场实测裁定（编排者在 aibox-super-sdk 上实测，2026-09-10）) / benches/golden/aibox-seed.jsonl:1-8 ((module)) |
| aibox-0002 | en | behavior | what does the retention maintenance workflow do? | src/aibox/capabilities/memory/internal/maintenance.py | core/tests/contextpack/test_assembly.py:69-82 (test_flow_tokens_count_but_do_not_compete) / docs/design/Background/02-codegraph.md:1-148 (CodeGraph 调研分析 > 6. MCP 工具面（8 个）) / core/tests/pipeline/test_indexer.py:289-323 (test_reembed_does_not_write_sqlite_rows) |
| aibox-0003 | zh | symbol | MemoryService 提供了哪些能力？ | src/aibox/capabilities/memory/service.py#MemoryService | docs/design/Module/01-切片存储.md:391-450 (Module 01 — 切片存储（组件详细设计） > 4. 贯穿机制：增量与失效 > 4.2 配置指纹与分层失效（关键，防"策略升级留下脏索引"）) / docs/design/Background/00-overview.md:1-66 (source/ 参考项目调研总览 > 4. 关键能力矩阵) / docs/design/Module/06-服务化与部署.md:141-173 (Module 06 — 服务化与部署（组件详细设计） > 4. 部署形态（D-38） > B. 本地单机（V2）：client 直嵌 core) |
| aibox-0004 | zh | path | 记忆检索的执行流程在哪个文件里实现？ | src/aibox/capabilities/memory/search/pipeline.py / src/aibox/capabilities/memory/search/planner.py | docs/plan/orchestration.md:1-106 (zace 多 AI 编排流程（任务分发手册） > 4. 契约变更协议（重要）) / docs/design/Background/03-ragcode.md:1-126 (RagCode 调研分析) / benches/golden/aibox-seed.jsonl:1-8 ((module)) |
| aibox-0005 | zh | spec | 记忆模块的目录结构和依赖方向是怎么规定的？ | src/aibox/capabilities/memory/ARCHITECTURE.md | docs/design/Module/06-服务化与部署.md:174-199 (Module 06 — 服务化与部署（组件详细设计） > 5. 仓库组织（D-35）：monorepo，不拆 git) / README.md:1-58 (zace > 仓库布局（monorepo，D-35）) / docs/design/Module/01-切片存储.md:76-174 (Module 01 — 切片存储（组件详细设计） > 2. 第一大类：切片策略（Chunking） > 2.2 各语言的切片难点与规则) |
| aibox-0006 | zh | spec | 开发 Agent 的事实来源和完成门禁是什么？ | src/aibox/capabilities/memory/AGENT.md | docs/design/Background/05-implications-for-zace.md:1-146 (四项目调研对 zace 的综合启示 > 3. MCP 工具切片：调研给出的证据) / docs/design/Background/01-notace-tool-rs.md:6-31 (notace-tool-rs 调研分析 > 1. 它是什么) / docs/design/Module/06-服务化与部署.md:209-217 (Module 06 — 服务化与部署（组件详细设计） > 7. 开发优先级（吸收外部建议，与 Background/06 §6 落地顺序合并）) |
| aibox-0007 | mixed | behavior | search planner 是怎么做检索策略规划的？ | src/aibox/capabilities/memory/search/planner.py | docs/design/Background/06-core-engine-proposal.md:173-232 (zace 核心引擎技术方案：切片存储、混合检索与可选 AI 总结 > 2. 检索策略（核心） > 2.4 重要反面教材：不要做规则引擎) / docs/design/Background/03-ragcode.md:1-126 (RagCode 调研分析 > 3. 检索流水线（重点 + 主要反面教材） > 3.3 教训（zace 必须避开的路径）) / docs/design/Module/02-检索策略.md:257-291 (Module 02 — 检索策略（组件详细设计） > 9. 决策登记（已同步 INDEX.md §3）) |
| aibox-0009 | zh | symbol | 记忆检索的规划（RetrievalPlan）是在哪个函数里生成的？ | src/aibox/capabilities/memory/search/planner.py#analyze_query | docs/design/Background/03-ragcode.md:1-126 (RagCode 调研分析 > 3. 检索流水线（重点 + 主要反面教材） > 3.3 教训（zace 必须避开的路径）) / docs/design/Module/02-检索策略.md:41-65 (Module 02 — 检索策略（组件详细设计） > 1. 设计约束) / docs/design/Background/03-ragcode.md:108-111 (RagCode 调研分析 > 6. Memory 系统（独有特性）) |
| aibox-0010 | zh | symbol | 基于 SQLite FTS5 的关键词检索通道是哪个类？ | src/aibox/capabilities/memory/storage/vector/sqlite_fts5.py#SqliteFts5Index | docs/design/Background/06-core-engine-proposal.md:27-232 (zace 核心引擎技术方案：切片存储、混合检索与可选 AI 总结 > 2. 检索策略（核心）) / docs/design/Module/02-检索策略.md:41-50 (Module 02 — 检索策略（组件详细设计） > 1. 设计约束) / docs/design/Module/02-检索策略.md:108-160 (Module 02 — 检索策略（组件详细设计） > 4. 各阶段详细设计 > 4.2 召回通道) |
| aibox-0011 | zh | path | 记忆向量的 qdrant edge 索引实现在哪个文件？ | src/aibox/capabilities/memory/storage/vector/qdrant_edge.py | docs/design/Background/06-core-engine-proposal.md:27-172 (zace 核心引擎技术方案：切片存储、混合检索与可选 AI 总结 > 1. 切片存储 > 1.3 向量存储) / docs/design/Module/01-切片存储.md:391-437 (Module 01 — 切片存储（组件详细设计） > 4. 贯穿机制：增量与失效 > 4.2 配置指纹与分层失效（关键，防"策略升级留下脏索引"）) / docs/tasks/TASK-007-索引流水线.md:7-69 (TASK-007：索引流水线（ChangeSet → 增量失效 → 向量对账） > 验收标准（DoD）) |
| aibox-0012 | zh | behavior | 记忆写入时的 indexed 策略流程做了什么？ | src/aibox/capabilities/memory/add/strategies/indexed.py#add_event | docs/design/Module/02-检索策略.md:257-267 (Module 02 — 检索策略（组件详细设计） > 6. V1 明确不做) / docs/design/Module/02-检索策略.md:161-188 (Module 02 — 检索策略（组件详细设计） > 4. 各阶段详细设计 > 4.4 图扩展（双角色，D-18）) / docs/design/Background/06-core-engine-proposal.md:173-232 (zace 核心引擎技术方案：切片存储、混合检索与可选 AI 总结 > 2. 检索策略（核心） > 2.4 重要反面教材：不要做规则引擎) |
| aibox-0013 | en | symbol | Which class provides the deterministic hash embedding fallback? | src/aibox/capabilities/memory/embeddings/hash.py#HashEmbedding | core/tests/parsing/test_fallback.py:78-80 (test_deterministic) / core/zace_core/embedding/base.py:27-36 (EmbeddingError) / core/zace_core/chunking/fingerprint.py:71-112 (IndexFingerprint.build) |
| aibox-0014 | en | behavior | How are documents split into memory chunks before indexing? | src/aibox/capabilities/memory/miner/chunker.py#build_chunks | core/tests/pipeline/test_indexer.py:172-191 (test_repeated_change_set_is_idempotent) / core/tests/pipeline/test_indexer.py:260-304 (test_reembed_does_not_write_sqlite_rows) / core/tests/chunking/test_splitter.py:255-289 (test_ingest_of_split_chunks_writes_consistent_rows) |
| aibox-0015 | en | path | Where does the retention maintenance loop live and what does it clean up? | src/aibox/capabilities/memory/internal/maintenance.py | core/zace_core/parsing/markdown.py:74-129 (_clean_title) / core/tests/pipeline/test_indexer.py:289-323 (test_reembed_does_not_write_sqlite_rows) / docs/design/Demo.md:655-681 (15. 数据安全) |
| aibox-0016 | mixed | behavior | budget 策略里 apply_budget() 是怎么按 token 预算截断内容的？ | src/aibox/capabilities/memory/search/strategies/budget.py#apply_budget | docs/design/Background/05-implications-for-zace.md:107-121 (四项目调研对 zace 的综合启示 > 6. ContextPack：三份合同的合并建议) / core/zace_core/contextpack/assembly.py:124-129 (budget_for) / docs/tasks/TASK-019-spec保底重复装填修复.md:50-64 (TASK-019：spec 保底块重复装填修复（U2）+ 预算不变量测试 > 验收标准（DoD）) |
| aibox-0017 | mixed | path | evidence 的级联删除策略在哪个文件里？ | src/aibox/capabilities/memory/delete/strategies/evidence.py | core/tests/contextpack/snapshots/rich_pack.md:24-27 (Relevant Context > Missing Evidence) / core/zace_core/interfaces.py:62-64 (ContextEngine.delete_project) / core/zace_core/engine.py:402-407 (Engine.delete_project) |
| aibox-0018 | mixed | spec | 记忆模块的分层架构（storage/sqlite 与 storage/vector 的依赖方向）在哪个文档里描述？ | src/aibox/capabilities/memory/ARCHITECTURE.md | docs/design/Background/03-ragcode.md:1-126 (RagCode 调研分析 > 6. Memory 系统（独有特性）) / docs/design/Module/01-切片存储.md:186-377 (Module 01 — 切片存储（组件详细设计） > 3. 第二大类：存储方案（Storage） > 3.2 决策分析：为什么是"per-project 目录树") / docs/design/Demo.md:712-816 (17. 推荐工程分层) |
| aibox-0019 | mixed | spec | 记忆系统的性能验收指标记录在哪个文档里？ | src/aibox/capabilities/memory/doc/P11性能验收报告.md | AGENTS.md:1-45 (zace 仓库协作规则（实施 AI 必读） > 6. 与设计文档冲突时) / benches/golden/aibox-seed.jsonl:1-8 ((module)) / docs/tasks/TASK-014-Golden集与基线.md:1-68 (TASK-014：golden set 扩充 + 基线报告 > 验收标准（DoD）) |
| cameraservice-0001 | zh | symbol | 摄像头通道切换的状态机类在哪个头文件里？ | cameraservice/stateMc/MWPStateMcManager.h#MWPStateMcManager | docs/design/Module/02-检索策略.md:106-240 (Module 02 — 检索策略（组件详细设计） > 4. 各阶段详细设计 > 4.1 轻路由（Lightweight Routing）【吸收外部 AI 建议，D-14】) / docs/design/Module/01-切片存储.md:186-217 (Module 01 — 切片存储（组件详细设计） > 2. 第一大类：切片策略（Chunking） > 2.4 Chunk 细节设计) / docs/design/Background/06-core-engine-proposal.md:129-172 (zace 核心引擎技术方案：切片存储、混合检索与可选 AI 总结 > 1. 切片存储 > 1.3 向量存储) |
| cameraservice-0002 | zh | symbol | 策略管理器 MWPPolicyManager 是在哪里定义的？ | cameraservice/policy/MWPPolicyManager.h#MWPPolicyManager | docs/design/Module/02-检索策略.md:41-65 (Module 02 — 检索策略（组件详细设计） > 1. 设计约束) / docs/design/Module/01-切片存储.md:60-174 (Module 01 — 切片存储（组件详细设计） > 2. 第一大类：切片策略（Chunking） > 2.2 各语言的切片难点与规则 > C++（最大风险项，V1 定位"尽力而为 + 诚实标注"）) / docs/design/Module/02-检索策略.md:241-267 (Module 02 — 检索策略（组件详细设计） > 6. V1 明确不做) |
| cameraservice-0003 | zh | path | 倒车影像（RVC）策略的实现文件是哪一个？ | cameraservice/policy/MWPRvcPolicy.cpp | docs/design/Module/01-切片存储.md:14-75 (Module 01 — 切片存储（组件详细设计） > 2. 第一大类：切片策略（Chunking） > 2.1 业界方案盘点) / docs/design/Module/01-切片存储.md:89-185 (Module 01 — 切片存储（组件详细设计） > 2. 第一大类：切片策略（Chunking） > 2.3 四层模型（正式定义）) / docs/design/Module/07-WebUI.md:1-53 (Module 07 — WebUI（组件详细设计） > 0. 组件定位) |
| cameraservice-0004 | zh | behavior | socket 帧的校验和 checkSum 是怎么算的？ | common/socket/MWPSocket.cpp#checkSum / common/socket/MWPSocket.h#checkSum | docs/design/Background/06-core-engine-proposal.md:1-210 (zace 核心引擎技术方案：切片存储、混合检索与可选 AI 总结 > 2. 检索策略（核心） > 2.1 四路并行召回) / docs/design/Background/06-core-engine-proposal.md:29-57 (zace 核心引擎技术方案：切片存储、混合检索与可选 AI 总结 > 1. 切片存储 > 1.1 核心原则：不要按行切，按符号切) / docs/design/Demo.md:1-58 (zace Architecture Design Task > 1. 背景) |
| cameraservice-0006 | en | symbol | Which class parses CAN bus frames and dispatches speed/gear changes to listeners? | cameraservice/policy/can/MWPCanInfo.h#MWPCanInfo | core/zace_core/engine.py:523-527 (_ScanResult) / core/tests/pipeline/test_indexer.py:172-191 (test_repeated_change_set_is_idempotent) / core/tests/chunking/test_resolver.py:163-182 (test_bare_call_edge_is_retargeted_to_unique_symbol) |
| cameraservice-0007 | en | behavior | How does the AVM policy react when vehicle speed changes? | cameraservice/policy/MWPAvmPolicy.cpp#OnCarSpeedChanged | core/tests/retrieval/test_rerank.py:225-231 (test_weights_override_does_not_change_feature_structure) / docs/design/Background/02-codegraph.md:1-148 (CodeGraph 调研分析 > 6. MCP 工具面（8 个）) / core/tests/retrieval/test_vector.py:92-109 (test_recall_degrades_when_provider_missing) |
| cameraservice-0008 | en | spec | What processes make up this repository's two-process architecture and how do they communicate? | CLAUDE.md | docs/design/Background/04-gitnexus.md:1-133 (GitNexus 调研分析 > 1. 架构总览 > Pipeline Phase DAG（ARCHITECTURE.md，设计最系统的部分）) / docs/design/Background/02-codegraph.md:104-116 (CodeGraph 调研分析 > 6. MCP 工具面（8 个）) / docs/design/Demo.md:577-654 (14. 用户与鉴权) |
| cameraservice-0009 | en | path | Where is the DBus interface definition for camera control? | ipc/com.cvte.linux.camera.xml / ipc/camera_dbus.c | core/zace_core/parsing/cpp.py:511-562 (CppParser._scan_calls) / core/zace_core/parsing/c.py:230-247 (CParser._scan_calls) / docs/design/Background/06-core-engine-proposal.md:274-289 (zace 核心引擎技术方案：切片存储、混合检索与可选 AI 总结 > 4. AI 总结层（可选，可配置） > 4.1 Provider 抽象) |
| cameraservice-0011 | mixed | symbol | MWPAudioPlayer 的 StartPlay() 是怎么按音区播放提示音的？ | common/audio/MWPAudioPlayer.cpp#StartPlay / common/audio/MWPAudioPlayer.h#StartPlay | docs/design/Module/07-WebUI.md:1-53 (Module 07 — WebUI（组件详细设计）) / docs/design/Background/05-implications-for-zace.md:1-146 (四项目调研对 zace 的综合启示 > 6. ContextPack：三份合同的合并建议) / docs/design/Module/01-切片存储.md:76-174 (Module 01 — 切片存储（组件详细设计） > 2. 第一大类：切片策略（Chunking） > 2.2 各语言的切片难点与规则 > Markdown / 文档（SpecBlock — 一等检索公民）【自研，原则源自 Task.md §9】) |
| cameraservice-0012 | mixed | symbol | 环形缓冲区 RingBuffer 的实现放在哪个头文件里？ | include/park/RingBuffer.h#RingBuffer | docs/tasks/TASK-003-C抽取器.md:55-131 (TASK-003：C 抽取器（include / static / 函数指针 / 宏） > 执行记录 > 未决问题（交编排者裁决）) / docs/design/Background/05-implications-for-zace.md:25-44 (四项目调研对 zace 的综合启示 > 2. C/C++/Python 场景的专门结论 > 2.1 C/C++ 解析是 zace 最大的技术风险，但有明确路线) / core/zace_core/pipeline/source.py:1-27 ((module)) |
| cameraservice-0013 | mixed | behavior | 共享内存 InitShmem 是在哪里初始化的？ | cameraservice/policy/can/MWPCanInfo.cpp#InitShmem | docs/design/Module/03-上下文组装.md:214-217 (Module 03 — 上下文组装（组件详细设计） > 7. 时序与性能) / core/zace_core/parsing/c.py:491-507 (_initializer_targets) / core/zace_core/storage/store.py:236-251 (Store.open) |
| cameraservice-0014 | mixed | behavior | 雷达状态回调 OnRadarStsChanged() 是怎么往下分发的？ | cameraservice/proxy/MWPCameraProxy.cpp#OnRadarStsChanged / cameraservice/policy/MWPRvcPolicy.cpp#OnRadarStsChanged | docs/design/Background/02-codegraph.md:1-148 (CodeGraph 调研分析 > 3. Rust Kernel（codegraph-kernel/）) / docs/tasks/TASK-016-BM25多词召回修复.md:163-176 (TASK-016：BM25 多词召回语义修复（OR + 列权重）+ 跨模块 E2E 回归 > 执行记录 > 2026-09-10 ｜ 分支 `feature/task-016_xwz0910` ｜ 状态：review（待编排者评审） > 7. 未决问题) / docs/design/Module/05-MCP与同步.md:173-177 (Module 05 — MCP 与同步（组件详细设计） > 6. 客户端形态与 CLI) |
| cameraservice-0015 | mixed | path | 泊车页 logo 的绘制实现在哪个文件？ | park/render/MWPLogo.cpp | docs/tasks/TASK-008-Embedding双实现.md:144-167 (TASK-008：Embedding Provider 双实现（本地 ONNX 默认 + API 可选） > 执行记录 > 真机发现并修复的回归（重要，TASK-015 请留意）) / docs/design/Background/02-codegraph.md:52-54 (CodeGraph 调研分析 > 2. 数据模型（src/db/schema.sql，v1 + 9 个 migration） > name_segment_vocab 表（NL→符号 的桥）) / docs/design/Background/03-ragcode.md:1-126 (RagCode 调研分析 > 1. 架构总览（分层严格，接口在 core，实现在外层）) |
| cameraservice-0016 | mixed | spec | HMI 与 CameraService 之间的 socket 兼容性改动记录在哪个文件里？ | cimsg.txt | AGENTS.md:1-45 (zace 仓库协作规则（实施 AI 必读） > 2. 硬性边界) / docs/tasks/TASK-019-spec保底重复装填修复.md:163-182 (TASK-019：spec 保底块重复装填修复（U2）+ 预算不变量测试 > 执行记录 > 完成报告) / docs/tasks/TASK-017-证据块行序修复.md:178-186 (TASK-017：ContextPack 合并区间的行号单调性与 elided 计数修复 > 执行记录 > 6. 契约影响（L1 说明，不需要 L2/L3 流程）) |
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
| aibox-0008 | 否 | Kubernetes operator 的部署协调逻辑在哪里实现？ | True | unresolved_reference, retrieval_truncated |
| aibox-0020 | 是 | RabbitMQ 的消息确认（ack）机制在哪里实现？ | False | unresolved_reference, retrieval_truncated |
| cameraservice-0005 | 否 | Terraform 的资源依赖图是在哪个文件里构建的？ | True | unresolved_reference, retrieval_truncated |
| cameraservice-0010 | 否 | Where is the gRPC service definition for the parking assist module? | True | unresolved_reference, retrieval_truncated |
| zace-0004 | 否 | PaymentGateway 的重试退避逻辑在哪里实现 | True | unresolved_reference, retrieval_truncated |
| zace-0106 | 是 | 支付网关的指数退避重试策略是在哪个文件里实现的？ | False | unresolved_reference, retrieval_truncated |
