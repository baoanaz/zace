# Phase 2 新靶场基线：hello-agents（TASK-047）

> **历史报告（2026-09-14 归档）**：本文引用的 `aibox-super-sdk` / `linux-mtk-mw-cameraservice` 旧靶场及其用例已于 2026-09-14 清理（见 `benches/README.md`「靶场变更」），文中命令与路径不可再执行；数字仅作决策依据留档，**与当前靶场不可比**。

> 本文件 = **手工元信息（§0-§4）** + **`zace-core eval` 的原始产物（§5 起）**。
> §5 起的数字由 runner 生成、未手工改动；§0-§4 是重跑命令、索引范围与本报告的适用边界。
> 注意：**重跑 eval 会覆盖整份文件**（runner 直接写本路径），届时需把 §0-§4 重新贴回。

## 0. 被测对象

| 项 | 值 |
|---|---|
| 靶场路径 | `<本地检出>/hello-agents`（外部**只读**靶场，不属于 zace 仓库） |
| 上游 | `https://github.com/datawhalechina/hello-agents.git`（datawhalechina/hello-agents，Python Agent 教程） |
| commit | `4f7682ceafe573d07cd8a7d0b89908500e83227d`（`git rev-parse HEAD`） |
| projectId | `e9ee9dd1d41a7d2c`（D-29 git remote 身份；同 remote 的不同工作区会共用这个目录） |
| golden | `benches/golden/hello-agents/helloagents.jsonl`（31 条：29 正例 + 2 负例） |
| 排名口径 | `ContextPack` 装填序（E 编号），`top-k=10`，预算 `maxTokens=10000` |
| 生成时间 | 2026-09-13 15:02:56（本机 WSL2 Ubuntu / Python 3.12） |

## 1. 完整可复现命令

```bash
# 0) 依赖（MCP 客户端与 service 都在这一组里）
uv sync --all-packages --all-extras

# 1) 云端 embedding 配置（W6 拍板：硅基流动 bge-m3；key 不入库、不入报告）
KEY=$(sed -n 's/^export zace_embeding_API_KEY=//p' ~/.bashrc | tr -d '"' | tr -d "'")
export EMBED_MODE=api EMBED_MODEL=BAAI/bge-m3 EMBED_DIM=1024 \
       EMBED_MAX_INPUT_TOKENS=8192 EMBED_BATCH_SIZE=4 \
       EMBED_BASE_URL=https://api.siliconflow.cn EMBED_API_KEY="$KEY"

# 2) 索引靶场（数据根在 /tmp，不写进靶场仓库）
uv run zace-core ingest --repo <本地检出>/hello-agents --data /tmp/zace-ha

# 3) 跑 golden 并写本报告
uv run zace-core eval --golden benches/golden/hello-agents \
  --repo <本地检出>/hello-agents --data /tmp/zace-ha \
  --report benches/results/phase2-helloagents-baseline.md
```

**两处与本环境强相关的参数（不是可选优化）**：

- `EMBED_BATCH_SIZE=4`：API 默认批大小是 64，本机实测会在全量索引时撞 provider 的 TPM 限流
  （HTTP 429）；而当前实现里**一次 429 会让整次 ingest 失败**（见 §4 观察 1）。8 是本机跑通的保守值。
- `EMBED_MODEL=BAAI/bge-m3`（**带厂商前缀**）：裸名 `bge-m3` 会被硅基流动拒绝（`20012 Model does not exist`）。

> **关于 `max_input_tokens` 的如实说明**：本次索引时 TASK-046 尚未合入 main，走的是「未登记模型」分支，
> profile 里的 `max_input_tokens` 因此是 `UNKNOWN_API_MAX_INPUT_TOKENS = 2048`（**不是我显式设的 8192**——
> `EMBED_MAX_INPUT_TOKENS=8192` 会覆盖它，但本机实际入库的指纹以 `api:bge-m3` 为准）。
> 也就是说：**本基线的向量是在 2048 token 截断假设下产生的**。TASK-046 合入后 `max_input_tokens` 应变为 8192，
> 届时若重建索引，本报告的数字**需要重跑**（截断变化会改变长 chunk 的向量）。

## 2. 索引范围实测

`zace-core ingest --repo <本地检出>/hello-agents` 的真实输出（elapsed 364.1s）：

```text
files: added=1482 modified=0 deleted=0 parsed=1482
chunks: new=9971 reused=0 removed=0
vectors: upserted=9971 deleted=0
graph: edges_retargeted=3768 unresolved_resolved=69 spec_refs=20358 ambiguous=4081
skipped: 380 个二进制/不可解码文件
elapsed: 364.1s
```

| 口径 | 数字 | 说明 |
|---|---|---|
| 目录列举（`DirectorySource.list_files()`） | **1862** | 只受 `DEFAULT_SKIP_DIRS` 约束（`venv/`、`__pycache__/` 等已被跳过） |
| 实际解析（`files_parsed`） | **1482** | 1862 − 380 个二进制 |
| 跳过的二进制（`skipped_files`） | **380** | 345 `.png` + 20 `.jpg` + 少量 `.db/.mp3/.pdf/.docx/.xlsx/.ogg/.ico` 等（含 NUL 字节 → `_decode` 返回 `None`） |
| chunks | **9971** | |
| 向量 | **9971** | 与 chunks 一一对应（无降级：`向量通道降级用例数：0`） |
| 解析语言分布（`files.language`） | python **749** ｜ markdown **227** ｜ fallback **506** | fallback = 无专用抽取器的扩展名（`.json/.txt/.vue/.ts/.ipynb/.html/.js/.css` 与 58 个无扩展名文件） |
| 解析错误 | **0** | `files.parse_errors` 全为 `[]`（1482/1482） |
| 未解析引用 | `refs_failed=0`、`refs_pending` 收尾后为 0 | （索引中段快照曾见 178 pending / 153 failed，收尾后归零） |

**与 TASK-037 的接口（本卡只提供数字，不实现忽略规则）**：272 个文件 >128KB、其中 239 个 `.png`；
`skipped` 的 380 个里绝大部分是这类大二进制——它们是「读进来才发现是二进制」的，**在 `list_files()` 阶段仍被列举**。
这正是 TASK-037（索引范围策略）要量化对照的基线。

## 3. 与历史的可比性声明

**本报告是全新基线，与 `benches/results/` 下的任何历史数字都不可比。**

- 旧三靶场（`aibox-super-sdk` / `linux-mtk-mw-cameraservice` / `linux-mtk-hmi`）在本机**全部不存在**，
  其 commit 与工作区都已丢失，历史数字无法复现（详见 `benches/README.md` 的「靶场变更」节）；
- `expected[].path` 是**仓库相对路径**，语义绑定到各自仓库，**旧 golden 不可复用**；
- embedding 路径也不同（旧基线多为本地 e5-small / 384 维，本次是云端 bge-m3 / 1024 维）。

因此不要用本报告的数字去判断「检索质量变好还是变差」——它的作用是**新靶场的回归护栏**。

## 4. 观察与未决（如实记录，不据此调参）

**R29/R30 仍然有效**：本报告的指标**不是优化目标**。要动检索质量参数（R21 / rerank / 装填）
属于 TASK-050，且必须先有 TASK-023 的真实数据。下面只记录现象与归属，**本卡不做任何参数调整**。

1. **F4（阻断级，属泳道 B / TASK-046 §D）**：provider 有 TPM 限流，实测约 **200K tokens/分钟**
   （单查询 114ms；连续小批请求 150 次 / 540K tokens 未触发；大请求累计约 72 万 token 时必现 429）。
   当前 `api.py` **不按 token 截断**且按**条数**分批，且**一次 429 就让整次 ingest 失败**：
   实测复现了「chunks=9971 但 vectors=0」的形态（数据库有内容、检索静默降级到仅 BM25）。
   **本报告的基线与本卡的冒烟脚本都以 `EMBED_BATCH_SIZE=4` 规避该问题**，未改任何 core 代码。
2. **`symbol` 类（0.562）明显低于 `spec` 类（0.750）**：典型失败模式是「文档被排在代码前」——
   `helloagents-0001/0002/0003`（ReAct / Plan-and-Solve / Reflection）的 top-3 全部是
   第三方共创项目的 README 与章节目录，目标实现文件未进 top-10。这与 R21（装填层 Docs/Code 失衡）
   是同一现象在**新靶场的再现**，可作为 TASK-050 的真实素材（**不作为本卡的调参依据**）。
3. **`helloagents-0017`（BFCL/GAIA）失败**：命中的是 `code/chapter12/**`（示例代码）而非
   `docs/chapter12/Chapter12-...md`。题目问的是「哪一章讲这两个基准」，文档目标被同章代码挤掉——
   同类现象，归属 TASK-050。
4. **同名符号在 `Co-creation-projects/` 下的多份副本**是符号类用例的固有噪声源
   （如 `PlanningService` 在 `JJason-DeepCastAgent` 与 `huailishang-AgentPlatformBase` 各有一份）。
   本次用 `symbol` 收窄判定，但**没有**把副本路径列进 `expected`——因为题目问的是「教材那一份」，
   把副本算命中会人为抬高指标（R29/R30 纪律）。
5. **索引可复用性**：`/tmp/zace-ha` 是本次基线的数据根；重新 `ingest` 时**不要并发跑两个进程指向同一数据根**
   （实测会导致向量表被 rebuild 清零——这是 `benches/README.md` 出题规则第 6 条警告的同一问题）。

### 需要编排者裁定的未决项

- **本报告完成于 TASK-046 之前**：`max_input_tokens` 的自述能力是 2048（§1 末）。TASK-046 合入后，
  若要把本基线当作长期护栏，需要**决策「是否重跑一次」**：重跑会让数字变化（长 chunk 的向量不同），
  但能让基线落在最终配置上。本卡不擅自重跑，留待编排者裁决。
- **`spec`/`path` 类用例与 TASK-037 的索引范围耦合**：若 TASK-037 落地 128KB 阈值与二进制跳过，
  `list_files()` 会从 1862 降到约 976（py+md 量级），本报告的「索引范围实测」需要按其后对照更新。

---

# zace golden eval 报告（runner 原始产物）

- golden：benches/golden/hello-agents（31 条用例）
- repo：<本地检出>/hello-agents
- project：e9ee9dd1d41a7d2c
- 生成时间：2026-09-13 15:02:56
- 预算：maxTokens=10000｜排名口径=ContextPack 装填序｜top-k=10
- 向量通道降级用例数：0

## 总体（正例）

| 指标 | 值 |
|---|---|
| 正例数 | 29 |
| recall@5 | 0.655 |
| recall@10 | 0.690 |
| MRR | 0.460 |
| 负例通过 | 2/2 |

## 按语言（lang）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| en | 7 | 0.714 | 0.714 | 0.571 |
| zh | 22 | 0.636 | 0.682 | 0.424 |

## 按类别（category）

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| path | 1 | 1.000 | 1.000 | 0.500 |
| spec | 12 | 0.750 | 0.750 | 0.625 |
| symbol | 16 | 0.562 | 0.625 | 0.333 |

## 失败清单（正例）

| id | lang | category | query | 期望 | top-3 |
|---|---|---|---|---|---|
| helloagents-0001 | zh | symbol | ReAct 范式里“思考-行动-观察”循环是在哪个类里实现的？ | code/chapter4/ReAct.py#ReActAgent | Co-creation-projects/melxy1997-ColumnWriter/README.md:103-107 (专栏作家智能体 (Column Writer Agent) > ▸ 智能体模式 (Agent Patterns) > 2. ReAct (推理+行动)) / docs/chapter4/第四章 智能体经典范式构建.md:136-174 (第四章 智能体经典范式构建 > 4.2 ReAct > 4.2.1 ReAct 的工作流程) / docs/chapter4/第四章 智能体经典范式构建.md:1226-1244 (第四章 智能体经典范式构建 > 4.5 本章小结) |
| helloagents-0002 | zh | symbol | Plan-and-Solve 范式里，负责先规划再执行的那个 Agent 类是哪个？ | code/chapter4/Plan_and_solve.py#PlanAndSolveAgent | Co-creation-projects/melxy1997-ColumnWriter/README.md:98-102 (专栏作家智能体 (Column Writer Agent) > ▸ 智能体模式 (Agent Patterns) > 1. Plan-and-Solve (规划与求解)) / Co-creation-projects/czxgg0630-ProductAnalysisAgent/README.md:231-262 (智能竞品分析Agent > 📖 使用示例 > 运行结果对比 > PlanAndSolveAgent 输出示例：) / Co-creation-projects/czxgg0630-ProductAnalysisAgent/README.md:37-51 (智能竞品分析Agent > ✨ 核心功能 > 两种Agent范式对比) |
| helloagents-0003 | zh | symbol | 自我反思范式（Reflection）在示例代码里是哪个类？ | code/chapter4/Reflection.py#ReflectionAgent | Co-creation-projects/melxy1997-ColumnWriter/README.md:108-112 (专栏作家智能体 (Column Writer Agent) > ▸ 智能体模式 (Agent Patterns) > 3. Reflection (反思)) / docs/chapter4/第四章 智能体经典范式构建.md:904-976 (第四章 智能体经典范式构建 > 4.4 Reflection > 4.4.2 案例设定与记忆模块设计) / Co-creation-projects/YYHDBL-HelloCodeAgentCli/agents/reflection_agent.py:75-89 (ReflectionAgent) |
| helloagents-0004 | zh | symbol | 工具注册与调度（注册工具、按名字取工具）是哪套机制？ | code/chapter4/tools.py#ToolExecutor | docs/chapter7/第七章 构建你的Agent框架.md:1360-1516 (第七章 构建你的智能体框架 > 7.5 工具系统 > 7.5.1 工具基类与注册机制设计) / Co-creation-projects/YYHDBL-HelloCodeAgentCli/tools/registry.py:7-32 (ToolRegistry) / code/chapter8/08_Agent_Tool_Integration.py:20-101 (AgentIntegrationDemo.demonstrate_tool_registry_pattern) |
| helloagents-0012 | zh | symbol | 深度研究智能体里，把用户问题拆成 TODO 待办列表的服务类是哪一段代码？ | code/chapter14/helloagents-deepresearch/backend/src/services/planner.py#PlanningService | docs/chapter14/第十四章 自动化深度研究智能体.md:1099-1307 (第十四章 自动化深度研究智能体 > 14.5 服务层实现 > 14.5.1 任务规划服务) / Co-creation-projects/JJason-DeepCastAgent/backend/src/models.py:23-52 (SummaryState) / Co-creation-projects/JJason-DeepCastAgent/backend/src/services/planner.py:24-74 (PlanningService.plan_todo_list) |
| helloagents-0017 | en | spec | Which chapter covers BFCL and GAIA benchmarks for agent evaluation? | docs/chapter12/Chapter12-Agent-Performance-Evaluation.md | code/chapter12/README.md:1-279 (第十二章示例代码) / code/chapter12/04_run_bfcl_evaluation.py:67-113 (run_evaluation) / code/chapter12/03_bfcl_custom_evaluation.py:1-60 ((module)) |
| helloagents-0021 | zh | spec | Agentic RL 这一章对应的英文文档在哪里？ | docs/chapter11/Chapter11-Agentic-RL.md | docs/chapter11/第十一章 Agentic-RL.md:149-241 (第十一章 Agentic-RL > 11.1 从 LLM 训练到 Agentic RL > 11.1.5 快速上手示例) / code/chapter11/06_complete_pipeline.py:1-23 (AgenticRLPipeline) / Co-creation-projects/huailishang-AgentPlatformBase/backend/agents/registry.py:12-12 (AgentRegistry) |
| helloagents-0027 | zh | symbol | RAG 工具做智能文档问答的完整演示代码在哪个文件？ | code/chapter8/07_RAGTool_Intelligent_QA.py#IntelligentQADemo | code/chapter8/10_RAG_Pipeline_Complete.py:803-854 (main) / docs/chapter8/第八章 记忆与检索.md:1974-2007 (第八章 记忆与检索 > 8.4 构建智能文档问答助手 > 8.4.5 运行效果展示) / docs/chapter8/第八章 记忆与检索.md:1656-1688 (第八章 记忆与检索 > 8.4 构建智能文档问答助手) |
| helloagents-0028 | en | spec | Who is the graduation-project chapter written for, and how do I pick a topic? | docs/chapter16/Chapter16-Graduation-Project.md | README_EN.md:105-126 (💡 How to Learn) / docs/chapter16/第十六章 毕业设计.md:35-38 (第十六章 毕业设计：构建属于你的多智能体应用 > 16.2 项目选题指南 > 16.2.1 选题原则) / Co-creation-projects/Apricity-InnocoreAI/utils/text_processor.py:18-32 (TextProcessor._load_stop_words) |

## 负例清单

| id | 通过 | query | answerable | missingEvidence |
|---|---|---|---|---|
| helloagents-0025 | 是 | hello-agents 里有没有实现 Kubernetes CRD 的 reconcile 调谐循环？ | False | unresolved_reference, retrieval_truncated |
| helloagents-0026 | 是 | Where does the framework implement a Redlock distributed lock with Redis? | False | unresolved_reference, retrieval_truncated |
