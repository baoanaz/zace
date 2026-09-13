# zace 任务板

> 这是实施 AI 的唯一入口清单。状态值：`pending / in_progress / review / done / blocked`。
> 规则：认领与回填流程见 `docs/plan/orchestration.md` §2；完成报告模板见同文 §3；契约纪律见 §4。
> 更新要求：改状态必须同时改本表与对应任务卡文头"状态"行。

## Phase 0 — 公共底座（编排者执行）

| # | 内容 | 状态 |
|---|---|---|
| P0-1 | monorepo 骨架 + 工具链 + CI（含依赖方向检查脚本） | done |
| P0-2 | 设计文档迁入 `docs/design/`（MANIFEST.sha256 防漂移）+ 决策登记（D-39 定稿 / D-44 / D-45） | done |
| P0-3 | 契约冻结（`docs/contracts/*` + `zace_core/{types,interfaces,hashing}.py`） | done |
| P0-4 | 编排体系（orchestration / roadmap / contracts / 本任务板 / 任务卡） | done |
| P0-5 | benches 骨架（格式定义 + 样例） | done |

## Phase 1 — zace-core 最小闭环（M1）

| 卡 | 标题 | 硬依赖 | soft 依赖 | 文件所有权根 | 状态 |
|---|---|---|---|---|---|
| [TASK-001](TASK-001-存储层.md) | 存储层：SQLite schema / FTS5 / jieba 预分词 | — | — | `core/zace_core/{storage,text}/` | done |
| [TASK-002](TASK-002-Parser基座与Python.md) | Parser 基座 + Python 抽取器 | — | — | `core/zace_core/parsing/` | done |
| [TASK-003](TASK-003-C抽取器.md) | C 抽取器（include / static / 函数指针 / 宏） | TASK-002 | — | `core/zace_core/parsing/c.py` 等 | done |
| [TASK-004](TASK-004-Cpp抽取器.md) | C++ 抽取器（尽力而为 + 诚实标注） | TASK-003 | — | `core/zace_core/parsing/cpp.py` 等 | done |
| [TASK-005](TASK-005-Markdown-SpecBlock.md) | Markdown SpecBlock 抽取（doctype / 标题树 / mentioned） | — | — | `core/zace_core/parsing/markdown.py` 等 | done |
| [TASK-006](TASK-006-Chunk模型与解析.md) | Chunk 模型 + unresolved 两阶段解析 + 配置指纹 | TASK-001 | TASK-002..005 | `core/zace_core/chunking/` | done |
| [TASK-007](TASK-007-索引流水线.md) | 索引流水线：ChangeSet → 增量失效 → 向量对账 | TASK-001, TASK-006 | TASK-008, TASK-009 | `core/zace_core/pipeline/` | done |
| [TASK-008](TASK-008-Embedding双实现.md) | Embedding Provider 双实现（本地 ONNX 默认 + API） | — | — | `core/zace_core/embedding/` | done |
| [TASK-009](TASK-009-向量存储.md) | 向量存储（LanceDB）+ hash 复用对账 | — | — | `core/zace_core/vectors/` | done |
| [TASK-010](TASK-010-检索通道与RRF.md) | 检索通道（Exact/BM25/Vector）+ RRF + 降级 | TASK-001 | TASK-008, TASK-009 | `core/zace_core/retrieval/{exact,bm25,vector,rrf,fusion}.py` | done |
| [TASK-011](TASK-011-图扩展与Rerank.md) | 图扩展（calls + spec_references）+ 确定性 rerank | TASK-010 | — | `core/zace_core/retrieval/{expand,rerank}.py` | done |
| [TASK-012](TASK-012-ContextPack组装.md) | ContextPack 组装 + Markdown 渲染 | TASK-010, TASK-011 | — | `core/zace_core/contextpack/` | done |
| [TASK-013](TASK-013-CLI与Eval.md) | core CLI + engine 装配 + golden runner | TASK-007, TASK-012 | — | `core/zace_core/{cli,engine}.py`、`benches/run.py` | done |
| [TASK-014](TASK-014-Golden集与基线.md) | golden set 扩充 + 基线报告（中英混合 50+） | TASK-013 | — | `benches/golden/`、`benches/results/` | done |
| [TASK-015A](TASK-015-Bakeoff与校准.md) | embedding bake-off（**仅模型选型**；禁碰排序与装填参数） | TASK-013 | — | `benches/bakeoff/` | review |
| [TASK-016](TASK-016-BM25多词召回修复.md) | BM25 多词召回语义修复（OR + 列权重）+ 跨模块 E2E 回归 | — | — | `core/zace_core/storage/store.py`(fts_search)、`core/zace_core/retrieval/bm25.py`、`core/tests/{storage,retrieval,integration}` | done |
| [TASK-017](TASK-017-证据块行序修复.md) | ContextPack 证据块行序单调与 elided 计数修复（R12） | TASK-012 | — | `core/zace_core/contextpack/` | done |
| [TASK-018](TASK-018-兜底行号与ID唯一性修复.md) | 兜底切分行号修复（U1，阻断 M1）+ chunk id 唯一性防御 + 单文件失败隔离 | — | — | `parsing/fallback.py`、`chunking/`、`pipeline/` | done |
| [TASK-019](TASK-019-spec保底重复装填修复.md) | spec 保底块重复装填修复（U2） | TASK-017 | — | `core/zace_core/contextpack/` | done |
| [TASK-020](TASK-020-BM25判别力修复.md) | BM25 查询侧噪声 token 过滤（IDF 重排已实测否决） | TASK-016 | — | `retrieval/bm25.py` | done |
| [TASK-021](TASK-021-装填层Code-Docs平衡.md) | 装填层 Code/Docs 平衡（R21，基线头号质量问题） | TASK-014 | — | `core/zace_core/contextpack/assembly.py` | done |
| [TASK-022](TASK-022-answerable判定收紧.md) | answerable/confidence 判定收紧（负例诚实性，R22） | TASK-021（同文件串行） | — | `core/zace_core/contextpack/assembly.py` | done |

## Phase 2 — MCP 端到端闭环（M2）

> 顺序依据：用户拍板 R32「先搭整体，再基于真实数据优化检索」。
> 详细分解见 `docs/plan/phase2-roadmap.md`（M2a 本地跑通 → M2b 质量数据 → M2c 多用户）。

| 卡 | 标题 | 硬依赖 | 文件所有权根 | 状态 |
|---|---|---|---|---|
| [TASK-030](TASK-030-service骨架.md) | service 骨架（FastAPI / 配置 / JSON 日志 / 错误信封 / healthz / CF-05 路径快照） | — | `service/zace_service/{app,config,logging,errors,__main__}.py`、`routers/` | done |
| [TASK-031](TASK-031-core接入.md) | core 接入（EngineManager + BlobSource + 项目 API + `ingest(source=)` 契约实现） | TASK-030 | `service/zace_service/{runtime,blobstore,sync_state,deps}.py`、`core/zace_core/engine.py` | done |
| [TASK-032](TASK-032-查询API.md) | 查询 API（search 渲染 + ask 降级包 + `meta` 字段集冻结给 client） | TASK-031 | `service/zace_service/{routers/query,packmeta}.py` | done |
| [TASK-033](TASK-033-同步API.md) | 同步 API（batch-upload / checkpoint / deletions / status；CF-05 幂等语义） | TASK-032 | `service/zace_service/routers/sync.py` | done |
| [TASK-035](TASK-035-provider健康与错误映射.md) | provider 健康与错误映射（503 语义 + 409 误导修复 + 私有调用收敛） | TASK-033 | `service/zace_service/{errors,runtime,routers}/*.py`、`core/zace_core/engine.py` | review |
| [TASK-034](TASK-034-本地单用户模式.md) | 本地单用户模式（attach 本地仓库 + 一键起 + 后台索引进度 + 懒重扫） | TASK-035 | `service/zace_service/{runtime,indexer,__main__,config}.py` | review |
| [TASK-040](TASK-040-service侧MCP端点.md) | **service 侧 MCP 端点**（Streamable HTTP）+ 编辑器配置输出（**demo 收口**） | TASK-034 | `service/zace_service/{mcp,cli_hint,app,__main__}.py` | review |
| [TASK-045](TASK-045-M2a验收手册.md) | M2a 验收手册与彩排脚本（用户照做即可跑起来） | TASK-040 | `docs/plan/m2a-acceptance.md`、`scripts/demo-rehearsal.sh` | review |

| 波次 | 泳道 | 任务卡 | 说明 |
|---|---|---|---|
| M2a-1 | `zace-lane-a` | TASK-030 → TASK-031 → TASK-032 → TASK-033 | service 骨架 + core 接入 + 查询/同步 API —— **已完成** |
| M2a-2 | `zace-lane-a` | TASK-035 → TASK-034 → TASK-040 → TASK-045 | 错误映射 → 本地模式 → **MCP 端点（demo 收口）** → 验收手册 —— **已完成** |
| M2b-1 | `zace-lane-b` | TASK-015A | embedding 模型选型（长任务，可与 M2a 并行）—— **已完成**（结论：沿用 e5-small） |
| M2b-2 | `zace-lane-c` | TASK-036 | 多仓库规模自举 —— **已完成** |
| **W6（已完成）** | `zace-lane-{a,b,c}` | A: TASK-037 ｜ B: TASK-046 ｜ C: TASK-047 | **环境切换后重定向**：索引范围修复 / 云端 embedding 接入 / 新靶场 hello-agents —— **三张卡已合并进 main**；性能基准见 `benches/results/index-performance-w6.md` |
| **W7（已完成）** | `zace-lane-a` | TASK-049 | **embedding 架构整理**：参数配置化（批/并发/上限按模型）+ provider 解耦，换模型只改配置 |
| M2b-3 | 视情况 | TASK-023 → TASK-050 | 真实数据采集 → 质量调优 |
| M2c | 视情况 | TASK-040R（Rust client）+ TASK-060 → 063 | 远端场景：Rust client（扫描/哈希/上传）+ 多用户 + 部署 |
| **M2c 前置** | `zace-lane-d` | [TASK-051](TASK-051-云端MCP就绪度与远端身份预研.md) | 云端 MCP 就绪度盘点 + 远端身份预研（只出文档，为 TASK-040R 开卡）—— **review（2026-09-13）** |
| **M2c** | `zace-lane-d` | [TASK-040R](TASK-040R-client骨架与同步代理.md) | **zace-client（Rust MCP stdio + 本地同步代理）**——MCP 最终形态（R38）；含跨语言身份一致性与端到端验收 —— **review（2026-09-13）** |
| **M2c** | `zace-lane-d` | [TASK-052](TASK-052-npm分发.md) | **npm 分发**（`npx zace-client`）+ 二进制级 stdio 测试 + 五平台 release CI——供 Codex/Claude Code/pi 接入 —— **review（2026-09-13）** |
| **Phase 3/4（本波，2026-09-13 开卡）** | `docs/cards-phase3_xwz0913` | TASK-060 → 061 → 062 → 064 ‖ **TASK-070（web，并行）** | 用户拍板：WebUI 先行。后端缺口（鉴权/token、租户、索引统计、查询用量）开成卡交编排者派活；`web/` 由本会话独占实现。**TASK-070 只依赖已 done 的端点，可与 060-064 并行**。详见下文「Phase 3 后端缺口卡片」与「Phase 4 卡片」 |

> **当前质量参数冻结**（R30）：`docs_ratio=0.10`、`CONSENSUS_SCORE_RATIO=2.15`、`rerank` 权重等
> 均为 smoke 集上的拟合值，**未经真实数据校准**，在 TASK-050 前不再调整。

### Phase 3 后端缺口卡片（2026-09-13 开卡，为 WebUI 的登录/统计/用量页提供后端）

> 背景：用户要求 Web 具备「登入 / 注册 / 初始化账户 / API Key 管理 / 索引成功与失败次数 / 平均耗时 / 用量」等能力。
> 现状盘点（`main` @ `42587cf`）：`/api/auth/*` 与 `/api/usage/projects/{id}` **全部是 501 占位**，
> 索引统计**只存在于内存**（无 job 表、无历史），CF-05 **没有任何初始化账户入口**。
> 另据 TASK-051 实测（`docs/plan/cloud-mcp-readiness.md` §1 A1）：非本地模式下**完全无鉴权**——
> 这是 Rust client 上云的**阻断级前置**，与本组卡片是同一件事。

| 卡 | 标题 | 硬依赖 | 文件所有权根 | 状态 |
|---|---|---|---|---|
| [TASK-060](TASK-060-鉴权与token.md) | **鉴权**（session + API token + 首个用户 bootstrap + `/healthz` 诚实性自检）；**修 TASK-051 A1** | TASK-030 | `service/zace_service/{auth,routers/auth,metadb}.py` | pending |
| [TASK-061](TASK-061-租户双层.md) | 租户双层：token→user→owns project（D-36 逻辑授权层） | TASK-060 | `service/zace_service/{metadb,deps,routers}/*.py` | **review**（2026-09-13，补做完成；MCP 面归属未接，见卡内未决问题 1） |
| [TASK-062](TASK-062-索引job与统计.md) | **索引 job 落库与统计**（成功/失败次数、平均耗时、历史） | TASK-034, TASK-060 | `service/zace_service/{metadb,indexer,runtime,routers}/*.py` | **review**（2026-09-23，TASK-085 补做完成） |
| [TASK-064](TASK-064-查询审计与用量.md) | **查询审计与用量端点**（`/api/usage/**` 替换 501） | TASK-060 | `service/zace_service/{audit,metadb,routers}/*.py` | **review**（读取口/建表/聚合已合并；写入侧 `audit.py`+接线由 [TASK-084](TASK-084-查询审计接线.md) 补做，见卡内“补做记录”） |

> **串行约束**：060 → 061 → 062 → 064。**060、061、062、064 均改 `service/zace_service/metadb.py`**（新建后共用），
> 同一时间只允许一张 in_progress；061 必须从 060 的分支串联创建。
> **契约影响均为 L2**：需新增 `/api/auth/me`、`/api/auth/bootstrap`、`/api/meta`、`/api/projects/{id}/index-{runs,stats}`、
> `/api/index-stats`、`/api/usage/**`，并补全 `/api/auth/*` 的请求/响应形状——**由编排者先更新 `docs/contracts/openapi.yaml`**，
> 实施 AI 不得直接改契约（各卡内已逐条列明）。

### Phase 4 卡片（WebUI）

| 卡 | 标题 | 硬依赖 | 文件所有权根 | 状态 |
|---|---|---|---|---|
| [TASK-070](TASK-070-web骨架与Playground.md) | **zace-web 账户 console**（登录/注册/初始化 + 账户面板 + API Key + 历史记录 + Playground + 三按键接入指南） | 无（依赖 TASK-060/062/064 已合并） | `web/**` | **done**（已合并 `7e51802`；746 pytest + 29 单测 + lint/build 全绿） |
| [TASK-080](TASK-080-接入指南两卡牌.md) | **接入指南重做**：两卡牌（npm 下载 + Agent 接入）+ 配置必带 `--token` | 无 | `web/src/app/connect-info.{ts,test.ts}`、`web/src/pages/ConnectPage.tsx`、`npm/README.md` | **review**（`feature/task-080-connect_xwz0923`；已合并） |
| [TASK-081](TASK-081-密码长度放宽.md) | 密码长度下限 8 → **3**（含测试与文案同步） | 无 | `service/zace_service/routers/auth.py`、`service/tests/test_auth.py`、`web/src/api/client.ts` | **review**（`feature/task-081-password_xwz0923`；已合并） |
| [TASK-082](TASK-082-删除Playground与项目页.md) | **删除 Playground 与项目管理页**（导航/路由/死链/测试一并清理；仪表盘保留项目列表） | 无 | `web/src/app/{App,Layout}.tsx`、`web/src/pages/{Playground,Projects,ProjectDetail}*`、`DashboardPage.tsx`、`HistoryPage.tsx`、`e2e.test.tsx`、`web/src/api/client.ts` | **review**（`feature/task-082-remove-pages_xwz0923`；lint/test/build 全绿，26 passed） |
| [TASK-083](TASK-083-空态与错误态.md) | **空态/加载态/错误态统一**（`EmptyState` 组件 + 各页替换） | **TASK-082** | `web/src/components/ui.tsx`、`HistoryPage.tsx`、`DashboardPage.tsx`、`ApiKeysPage.tsx` | **review**（`feature/task-083-empty-states_xwz0913`；lint 绿、34 passed、build 绿；另修 3 处“把故障伪装成空数据”） |
| [TASK-084](TASK-084-查询审计接线.md) | **查询审计接线**（补 TASK-064）：`record_query` 零调用 → `/api/usage/**` 有真实数据 | TASK-060 | `service/zace_service/audit.py`(新建)、`routers/query.py`、`service/tests/test_usage_api.py`(新建) | **review**（本地模式端到端 `total` 0→3；云端 summary 待 TASK-061 归属写入，见卡内未决问题） |
| [TASK-085](TASK-085-索引统计接上传路径.md) | **索引统计接上客户端上传路径**（补 TASK-062）：`npx zace-client` 索引后面板不再恒为 0 | TASK-060/062 | `service/zace_service/runtime.py`、`service/tests/test_index_stats.py`(新建) | **review**（2026-09-23） |
| [TASK-086](TASK-086-导航与首页重排.md) | **导航与首页重排 + 全局背景纹理**（接入指南移到第二位；账户→控制台；删「最近索引记录」；浅蓝灰网格底） | 无 | `web/src/app/Layout.tsx`、`web/src/pages/DashboardPage.tsx`、`web/src/index.css`、`web/tailwind.config.js` | review |

> **TASK-084/085 的由来**（编排者实测，2026-09-13）：TASK-062/064 的**建表与方法已实现**，
> 但（a）`record_query()` 全仓零调用、`audit.py` 不存在；（b）索引 run 记录只覆盖本地 attach 路径，
> 客户端上传路径（Agent 实际用的）不记录。两张卡要求的验收测试文件也不存在。
> 因此 WebUI 的「使用记录」与「索引统计」在真实场景下**恒为空**——本波是补做，不是新功能。

> TASK-070 的未就绪页（登录/注册/初始化/token/用量/设置）**显式标注依赖卡号**，不用假数据填充；
> 后端落地后另开 TASK-071 补齐这六页（卡内已列为 soft 依赖）。
> 参考项目只借信息架构（LiteLLM Keys/Usage/Logs、Supabase 清单+抽屉、E2B 引导流），**代码全部自研**（用户 2026-09-13 拍板；E2B `dashboard-ee` 为专有许可，仅只读参考产品形态）。

### M2b 卡片

| 卡 | 标题 | 硬依赖 | 文件所有权根 | 状态 |
|---|---|---|---|---|
| [TASK-015A](TASK-015-Bakeoff与校准.md) | embedding bake-off（模型选型） | TASK-013 | `benches/bakeoff/` | done |
| [TASK-036](TASK-036-多仓库规模自举与健壮性.md) | 多仓库规模自举与索引健壮性（六靶场 / 崩溃修复 / 一致性自检） | — | `benches/results/robustness-scale.md`、`core/zace_core/{parsing,chunking,pipeline}/` | done |
| [TASK-037](TASK-037-索引范围策略.md) | 索引范围策略（三层忽略规则 + 大小/二进制阈值，R42/R43） | — | `core/zace_core/pipeline/{ignore,source,indexer}.py` | **done（W6-lane A，已合并；§C/§D 测量缺口见备注）** |
| [TASK-046](TASK-046-云端embedding接入.md) | **云端 embedding 接入与配置对齐**（硅基流动 bge-m3；修 registry 模型名不可用 + 上限默认值 + api 截断/分批；`docs/handbook/云端embedding接入.md`） | TASK-008 | `core/zace_core/embedding/{registry,factory,api}.py`、`core/tests/embedding/` | **done（W6-lane B，已合并）** |
| [TASK-047](TASK-047-新靶场与golden重建.md) | **新靶场建立与 golden 重建**（hello-agents）+ M2a 一键冒烟脚本 | — | `benches/golden/hello-agents/`、`scripts/m2a-smoke.sh`、`docs/handbook/` | **done（W6-lane C，已合并）** |
| [TASK-048](TASK-048-批参数环境变量入口.md) | 批参数环境变量入口（`EMBED_BATCH_TOKEN_BUDGET`）—— TASK-046 漏接的配置路径 | TASK-046 | `core/zace_core/embedding/factory.py`、`core/tests/embedding/` | done（编排者直接完成） |
| [TASK-049](TASK-049-embedding架构整理.md) | **embedding 架构整理**（参数按模型配置化 + provider 解耦 + 并发 + 切换手册） | TASK-046 | `core/zace_core/embedding/{registry,api,factory}.py`、`docs/handbook/embedding-provider切换.md` | **done（核心已合并；手册与 `.env.example` 待补）** |
| [TASK-048](TASK-048-批参数环境变量入口.md) | 批参数环境变量入口（`EMBED_BATCH_TOKEN_BUDGET`）—— **已由编排者直接完成**（TASK-046 漏接的配置路径） | TASK-046 | `core/zace_core/embedding/factory.py`、`core/tests/embedding/` | done |
| [TASK-038](TASK-038-本地embedding截断钳制.md) | 本地 embedding 的 `max_input_tokens` 钳制与友好报错（**降级**：本地路线暂缓，`min` 语义并入 TASK-046 §B） | — | `core/zace_core/embedding/**` | deferred（W6 不派活） |
| [TASK-023](TASK-023-真实场景用例采集.md) | 真实场景用例采集（埋点 + 反馈信号） | TASK-031 | `service/zace_service/telemetry/` | pending |
| TASK-050 | 质量调优（R21/R24/rerank/装填参数，**必须基于 TASK-023 真实数据**） | TASK-023 | — | 未开卡 |

> **TASK-037 的硬依赖已改**：原卡写 `TASK-036`（要求用其规模数字做前后对照），但 TASK-036 已完成
> 且其靶场（hmi / systemservice / Trellis）**在当前环境不存在**；改以 `hello-agents` + `zace` 自身
> 作前后对照靶场（理由与替代口径见 `docs/plan/phase2-m2b-w6.md` §3.1）。
> **TASK-037 的已知缺口（编排者评审记录，2026-09-13）**：代码与语义对齐已验证（725 passed；
> 与 ripgrep / `ignore` crate 语义一致），但实施 AI **未回填任务卡“执行记录”、未落盘 §C 前后对照表与 §D 检索回归**。
> 编排者已独立复核：忽略规则在新靶场上使候选文件 1862 → 1825（-37），阈值层另跳过 389 个二进制/超限文件；
> 完整 ingest 实测 1436 文件 / 9389 chunks / 230.9s。**一个已确认的语义分歧**：对 git **已跟踪**文件，
> zace 与 `git check-ignore` 不一致（36 个 / 1.9%，因 zace 按 `ignore` crate 语义、不豁免 tracked 文件）；
> 契约（R42 / Module 05 §3.1）要求的是 `ignore` crate 语义，故**实现合规**，但该差异需在产品文档中说明。
> **TASK-038 的降级依据**：用户 2026-09-13 拍板当前全程用云端 embedding、本地 ONNX 暂缓（U1/U2），
> 保留卡但不派活。

### 开卡批次历史（并行安全）

1. 批 1（W1）：TASK-001、002、005、008、009 → 002 之后接 003、004
2. 批 2（W2）：TASK-006 → 007；TASK-010 → 011 → 012
3. 批 3（W3a）：TASK-016（BM25 修复）、TASK-017（行序修复）、TASK-013（CLI + eval）
4. 批 4（W3c）：TASK-018（lane A）、TASK-019（lane C）—— **已完成**（阻断解除）
5. 批 5（W3d）：TASK-020（lane B，零成本版）、TASK-014（lane F，基线）—— 已完成
6. 批 6（W4a，**质量修复**）：TASK-021 → TASK-022（lane A，同文件串行）—— 基线暴露的头号质量问题
7. 批 8（W5a，Phase 2 M2a-1）：TASK-030 → 031 → 032 → 033（lane A 串联；service 外壳 + core 接入 + 查询/同步 API）—— **已完成**
8. 批 9（W5b，M2a-2，**demo 收口波**）：TASK-035 → TASK-034 → TASK-040 → TASK-045（lane A 串行）—— **已完成**
9. 批 10（W5c，**整夜并行三泳道**）：lane A TASK-034→040→045（demo 收口）；lane B TASK-015A（模型选型）；lane C TASK-036（规模自举）—— **均已完成**（夜里机器重启，成果未丢）
10. 批 11（W6，**环境切换后重定向**，`docs/plan/phase2-m2b-w6.md`）：lane A TASK-037（索引范围）；lane B TASK-046（云端 embedding 接入）；lane C TASK-047（新靶场 hello-agents + golden 重建 + 冒烟脚本）—— **已完成并合并**
11. 批 12（W7，**embedding 架构整理**）：lane A TASK-049（参数配置化 + provider 解耦 + 并发）—— **已完成并合并**
12. 批 13（**云端 MCP 波次**，lane D）：TASK-051（就绪度盘点）→ TASK-040R（Rust client）→ TASK-052（npm 分发）—— **均 review**
13. 批 14（**WebUI 波次**，用户拍板）：lane A TASK-060 → 061 → 062 → 064（后端缺口：鉴权/租户/索引统计/查询用量，串行共用 `metadb.py`）；lane W **TASK-070**（`web/**` 独占，与 lane A **零文件重叠**，可完全并行）—— **开卡完成，待派活**
14. 批 15（M2b）：TASK-023（真实数据采集）→ TASK-050（质量调优）

> **用户方向（2026-09-13）**：**不妥协，直奔最终版本**——MCP 的最终形态是本地 Rust client（stdio + 远端 sync，
> 依 `docs/design/Background/01-notace-tool-rs.md`），本地 MCP（service 直出 Streamable HTTP，R38）**仅作短期验证**。
> TASK-051 是其前置诊断，TASK-040R 已交付可用的 `client/`（33 单测 + 真实 service 端到端）。
> **上线硬前置**：服务端鉴权（TASK-060/061，见就绪度报告 A1——当前非本地模式无鉴权）。

> **本波次的并行安全论证**：TASK-070 只消费已 done 的端点（projects/query/healthz），
> 文件所有权限定在 `web/**`；TASK-060..064 只改 `service/**`。两者无交集，且 web 端的
> 未就绪页已显式标注依赖卡号，不会把“后端已支持”写错。
>
> **两条波次的关系（2026-09-13 核对）**：批 13（云端 MCP，`zace-lane-d`）与批 14（WebUI）**互不重叠**：
> 前者只碰 `client/**`、`npm/**`、`server.json`、`scripts/check-version.sh`，后者只碰 `web/**`、`service/**`。
> **交集只有 `docs/tasks/README.md`（本文件）**，已在合并时两边保留。

> **编号说明（2026-09-13 修正）**：历史列表里出现过重复行（两次 W5b、两次 M2b 规划行），已去重；
> 原先“云端 embedding 接入（R44-R46）”的引用已改为具体卡号：**R44 被 TASK-034 的 attach 端点占用**
> （见 `docs/contracts/openapi.yaml`），且 R45/R46 **从未存在**；新增裁定的编号在 W6 收口时统一登记。

> 教训：W3a 的 TASK-013 自举直接暴露了两个缺陷（U1 阻断、U2 预算浪费）——**“能跑通全仓测试”不等于“能在真实仓库跑通”**，
> 自举（dogfooding）从现在起列入每波收尾动作。

### 已指定的评测靶场

| repo_hint | 路径 | commit | 用途 |
|---|---|---|---|
| `hello-agents` | `/home/xuwenzheng/github/hello-agents` | `4f7682c` | **当前主靶场**（W6 起）：Python Agent 教程项目，976 有效文件（227 md + 749 py），文档与代码逐章对应（中英双文档） |
| `aibox-super-sdk` | `/home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk` | `debf8a32` | TASK-014 外部评测主靶场（文档密度高，spec 检索）—— **靶场在当前环境不存在，用例保留但暂停** |
| `linux-mtk-mw-cameraservice` | `/home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice` | `3fb0b2d6` | TASK-014 自选 C++ 靶场 —— **同样不可得，用例保留但暂停** |

**靶场变更（2026-09-13）**：用户更换开发环境（家里 WSL2），上述两个旧外部靶场不在本机，
因此历史基线数字**无法复现**；新靶场与重建口径见 `docs/tasks/TASK-047-新靶场与golden重建.md`。
历史报告（`benches/results/*`）保留，但注意其靶场已不可得。

详情（规模、负例口径、为何选它）见 `benches/README.md` 的“已指定的评测仓库”节。

可复制提示词、用户操作循环与报告模板见 `docs/plan/dispatch.md`。
