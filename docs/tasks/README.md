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
| [TASK-014](TASK-014-Golden集与基线.md) | golden set 扩充 + 基线报告（中英混合 50+） | TASK-013 | — | `benches/golden/`、`benches/results/` | pending |
| [TASK-015](TASK-015-Bakeoff与校准.md) | embedding bake-off + rerank 初值校准 | TASK-013 | TASK-014 | `benches/bakeoff/` | pending |
| [TASK-016](TASK-016-BM25多词召回修复.md) | BM25 多词召回语义修复（OR + 列权重）+ 跨模块 E2E 回归 | — | — | `core/zace_core/storage/store.py`(fts_search)、`core/zace_core/retrieval/bm25.py`、`core/tests/{storage,retrieval,integration}` | done |
| [TASK-017](TASK-017-证据块行序修复.md) | ContextPack 证据块行序单调与 elided 计数修复（R12） | TASK-012 | — | `core/zace_core/contextpack/` | done |
| [TASK-018](TASK-018-兜底行号与ID唯一性修复.md) | 兜底切分行号修复（U1，阻断 M1）+ chunk id 唯一性防御 + 单文件失败隔离 | — | — | `parsing/fallback.py`、`chunking/`、`pipeline/` | review |
| [TASK-019](TASK-019-spec保底重复装填修复.md) | spec 保底块重复装填修复（U2） | TASK-017 | — | `core/zace_core/contextpack/` | pending |

### 开卡批次历史（并行安全）

1. 批 1（W1）：TASK-001、002、005、008、009 → 002 之后接 003、004
2. 批 2（W2）：TASK-006 → 007；TASK-010 → 011 → 012
3. 批 3（W3a）：TASK-016（BM25 修复）、TASK-017（行序修复）、TASK-013（CLI + eval）
4. 批 4（W3c，**阻断修复，优先**）：TASK-018（lane A）、TASK-019（lane C）
5. 批 5（W3b，必须在批 4 合并后）：TASK-014 → TASK-015（基线/校准；基线必须建立在修复后的主干上）

> 教训：W3a 的 TASK-013 自举直接暴露了两个缺陷（U1 阻断、U2 预算浪费）——**“能跑通全仓测试”不等于“能在真实仓库跑通”**，
> 自举（dogfooding）从现在起列入每波收尾动作。

### 已指定的评测靶场

| repo_hint | 路径 | commit | 用途 |
|---|---|---|---|
| `aibox-super-sdk` | `/home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk` | `debf8a32` | TASK-014 外部评测主靶场（文档密度高，spec 检索）；种子用例 `benches/golden/aibox-seed.jsonl` |

详情（规模、负例口径、为何选它）见 `benches/README.md` 的“已指定的评测仓库”节。

可复制提示词、用户操作循环与报告模板见 `docs/plan/dispatch.md`。
