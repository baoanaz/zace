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
| [TASK-015A](TASK-015-Bakeoff与校准.md) | embedding bake-off（**仅模型选型**；rerank 校准推迟至 TASK-050） | TASK-013 | — | `benches/bakeoff/` | pending |
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
| [TASK-030](TASK-030-service骨架.md) | service 骨架（FastAPI / 配置 / JSON 日志 / 错误信封 / healthz / CF-05 路径快照） | — | `service/zace_service/{app,config,logging,errors,__main__}.py`、`routers/` | review |
| [TASK-031](TASK-031-core接入.md) | core 接入（EngineManager + BlobSource + 项目 API + `ingest(source=)` 契约实现） | TASK-030 | `service/zace_service/{runtime,blobstore,sync_state,deps}.py`、`core/zace_core/engine.py` | review |
| [TASK-032](TASK-032-查询API.md) | 查询 API（search 渲染 + ask 降级包 + `meta` 字段集冻结给 client） | TASK-031 | `service/zace_service/{routers/query,packmeta}.py` | review |
| [TASK-033](TASK-033-同步API.md) | 同步 API（batch-upload / checkpoint / deletions / status；CF-05 幂等语义） | TASK-032 | `service/zace_service/routers/sync.py` | pending |

| 波次 | 泳道 | 任务卡 | 说明 |
|---|---|---|---|
| M2a-1 | `zace-lane-a` | TASK-030 → TASK-031 → TASK-032 → TASK-033 | service 骨架 + core 接入 + 查询/同步 API |
| M2a-2 | `zace-lane-b` | TASK-034（本地单用户模式） | **demo 关键**：免鉴权一键起服务 |
| M2a-3 | `zace-lane-c` | TASK-040 → 041 → 042 → 043 | Rust client：MCP stdio + 懒同步 + 分发 |
| M2b | 视情况 | TASK-023 → TASK-050；TASK-015A 可并行 | 真实数据采集 → 质量调优 |
| M2c | 视情况 | TASK-060 → 061 → 062 → 063 | 多用户 + 部署（要给朋友用时才做） |

> **当前质量参数冻结**（R30）：`docs_ratio=0.10`、`CONSENSUS_SCORE_RATIO=2.15`、`rerank` 权重等
> 均为 smoke 集上的拟合值，**未经真实数据校准**，在 TASK-050 前不再调整。

### 开卡批次历史（并行安全）

1. 批 1（W1）：TASK-001、002、005、008、009 → 002 之后接 003、004
2. 批 2（W2）：TASK-006 → 007；TASK-010 → 011 → 012
3. 批 3（W3a）：TASK-016（BM25 修复）、TASK-017（行序修复）、TASK-013（CLI + eval）
4. 批 4（W3c）：TASK-018（lane A）、TASK-019（lane C）—— **已完成**（阻断解除）
5. 批 5（W3d）：TASK-020（lane B，零成本版）、TASK-014（lane F，基线）—— 已完成
6. 批 6（W4a，**质量修复**）：TASK-021 → TASK-022（lane A，同文件串行）—— 基线暴露的头号质量问题
7. 批 8（W5a，Phase 2 M2a-1）：TASK-030 → 031 → 032 → 033（lane A 串联；service 外壳 + core 接入 + 查询/同步 API）—— **当前波次**
8. 批 9（W5b/M2a-2）：TASK-034（本地单用户模式，demo 关键）；M2a-3 = TASK-040..043（Rust client）

> 教训：W3a 的 TASK-013 自举直接暴露了两个缺陷（U1 阻断、U2 预算浪费）——**“能跑通全仓测试”不等于“能在真实仓库跑通”**，
> 自举（dogfooding）从现在起列入每波收尾动作。

### 已指定的评测靶场

| repo_hint | 路径 | commit | 用途 |
|---|---|---|---|
| `aibox-super-sdk` | `/home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk` | `debf8a32` | TASK-014 外部评测主靶场（文档密度高，spec 检索）；种子用例 `benches/golden/aibox-super-sdk/aibox-seed.jsonl`（TASK-014 移入仓库子目录，内容未改） |

详情（规模、负例口径、为何选它）见 `benches/README.md` 的“已指定的评测仓库”节。

可复制提示词、用户操作循环与报告模板见 `docs/plan/dispatch.md`。
