# zace golden eval 报告

- golden：/root/xuwenzheng/zace/benches/golden/hello-agents（31 条用例）
- repo：/root/.zace/repos/hello-agents
- project：e9ee9dd1d41a7d2c
- 生成时间：2026-09-14 16:09:21
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 29 |
| recall@5 | 0.586 |
| recall@10 | 0.655 |
| MRR | 0.388 |
| 负例通过 | 1/2 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| en | 7 | 0.714 | 0.714 | 0.536 |
| zh | 22 | 0.545 | 0.636 | 0.341 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| path | 1 | 0.000 | 0.000 | 0.000 |
| spec | 12 | 0.750 | 0.750 | 0.590 |
| symbol | 16 | 0.500 | 0.625 | 0.261 |

## 失败清单（正例）

| id | lang | category | query | 期望 | top-3 |
|---|---|---|---|---|---|
| helloagents-0001 | zh | symbol | ReAct 范式里“思考-行动-观察”循环是在哪个类里实现的？ | code/chapter4/ReAct.py#ReActAgent | Co-creation-projects/melxy1997-ColumnWriter/README.md:103-107 (专栏作家智能体 (Column Writer Agent) > ▸ 智能体模式 (Agent Patterns) > 2. ReAct (推理+行动)) / docs/chapter4/第四章 智能体经典范式构建.md:136-151 (第四章 智能体经典范式构建 > 4.2 ReAct) / Co-creation-projects/YYHDBL-HelloCodeAgentCli/agents/react_agent.py:1-52 (ReActAgent) |
| helloagents-0002 | zh | symbol | Plan-and-Solve 范式里，负责先规划再执行的那个 Agent 类是哪个？ | code/chapter4/Plan_and_solve.py#PlanAndSolveAgent | Co-creation-projects/melxy1997-ColumnWriter/README.md:98-102 (专栏作家智能体 (Column Writer Agent) > ▸ 智能体模式 (Agent Patterns) > 1. Plan-and-Solve (规划与求解)) / docs/chapter4/第四章 智能体经典范式构建.md:1226-1244 (第四章 智能体经典范式构建 > 4.5 本章小结) / Co-creation-projects/YYHDBL-HelloCodeAgentCli/agents/plan_solve_agent.py:124-136 (PlanAndSolveAgent) |
| helloagents-0003 | zh | symbol | 自我反思范式（Reflection）在示例代码里是哪个类？ | code/chapter4/Reflection.py#ReflectionAgent | Co-creation-projects/YYHDBL-HelloCodeAgentCli/agents/reflection_agent.py:75-89 (ReflectionAgent) / Co-creation-projects/melxy1997-ColumnWriter/agents.py:1052-1062 (ReflectionWriterAgent) / Co-creation-projects/melxy1997-ColumnWriter/orchestrator.py:199-223 (ColumnWriterOrchestrator._write_with_reflection) |
| helloagents-0004 | zh | symbol | 工具注册与调度（注册工具、按名字取工具）是哪套机制？ | code/chapter4/tools.py#ToolExecutor | Co-creation-projects/CC1227871-StockInsightAgent/tools.py:10-11 (ToolExecutor) / Co-creation-projects/YYHDBL-HelloCodeAgentCli/tools/registry.py:7-16 (ToolRegistry) / docs/chapter7/第七章 构建你的Agent框架.md:1360-1516 (第七章 构建你的智能体框架 > 7.5 工具系统 > 7.5.1 工具基类与注册机制设计) |
| helloagents-0012 | zh | symbol | 深度研究智能体里，把用户问题拆成 TODO 待办列表的服务类是哪一段代码？ | code/chapter14/helloagents-deepresearch/backend/src/services/planner.py#PlanningService | docs/chapter14/第十四章 自动化深度研究智能体.md:1099-1307 (第十四章 自动化深度研究智能体 > 14.5 服务层实现 > 14.5.1 任务规划服务) / Co-creation-projects/JJason-DeepCastAgent/backend/src/services/planner.py:24-74 (PlanningService) / Co-creation-projects/JJason-DeepCastAgent/backend/src/models.py:23-52 (SummaryState) |
| helloagents-0015 | en | spec | Which chapter explains how to give an agent long-term memory and a retrieval tool? | docs/chapter8/Chapter8-Memory-and-Retrieval.md | Co-creation-projects/huailishang-AgentPlatformBase/agents/rss_digest/config/sources.json:1-148 ((module)) / Co-creation-projects/YYHDBL-HelloCodeAgentCli/tools/builtin/memory_tool.py:13-22 (MemoryTool) |
| helloagents-0021 | zh | spec | Agentic RL 这一章对应的英文文档在哪里？ | docs/chapter11/Chapter11-Agentic-RL.md | docs/chapter11/第十一章 Agentic-RL.md:2556-2618 (第十一章 Agentic-RL > 11.8 本章小结) / code/chapter11/06_complete_pipeline.py:21-23 (AgenticRLPipeline) / Co-creation-projects/haoye2-UnivesalAgent/src/agents/__init__.py:1-7 ((module)) |
| helloagents-0022 | zh | spec | 中文教材里讲“智能体的构成与运行原理”的是哪一章文档？ | docs/chapter1/第一章 初识智能体.md | README.md:105-127 (💡 如何学习) / code/chapter6/AutoGenDemo/README.md:174-178 (AutoGen 软件开发团队协作案例 > 📚 扩展学习 > 相关章节) / code/chapter13/helloagents-trip-planner/backend/app/agents/__init__.py:1-1 ((module)) |
| helloagents-0027 | zh | symbol | RAG 工具做智能文档问答的完整演示代码在哪个文件？ | code/chapter8/07_RAGTool_Intelligent_QA.py#IntelligentQADemo | code/chapter8/10_RAG_Pipeline_Complete.py:803-854 (main) / docs/chapter8/第八章 记忆与检索.md:1974-2007 (第八章 记忆与检索 > 8.4 构建智能文档问答助手 > 8.4.5 运行效果展示) / code/chapter8/10_RAG_Pipeline_Complete.py:552-681 (RAGPipelineComplete.demonstrate_intelligent_qa) |
| helloagents-0029 | en | path | Which document walks through building a community project that guesses a character in a game? | Co-creation-projects/afei-GuessWhoAmI/README.md | Co-creation-projects/megg-ops-roleplay_agent/roleplay_agent.py:9-9 (CharacterRoleplayAgent) / docs/chapter15/Chapter15-Building-Cyber-Town.md:19-26 (Chapter 15: Building Cyber Town > 15.1 Project Overview and Architecture Design > 15.1.1 Why Build an AI Town) / README_EN.md:24-29 (🎯 Project Introduction) |

## 负例清单

| id | 通过 | query | answerable | missingEvidence |
|---|---|---|---|---|
| helloagents-0025 | 否 | hello-agents 里有没有实现 Kubernetes CRD 的 reconcile 调谐循环？ | True | unresolved_reference, retrieval_truncated |
| helloagents-0026 | 是 | Where does the framework implement a Redlock distributed lock with Redis? | False | unresolved_reference, retrieval_truncated |
