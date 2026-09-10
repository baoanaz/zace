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
| [TASK-001](TASK-001-存储层.md) | 存储层：SQLite schema / FTS5 / jieba 预分词 | — | — | `core/zace_core/{storage,text}/` | review |
| [TASK-002](TASK-002-Parser基座与Python.md) | Parser 基座 + Python 抽取器 | — | — | `core/zace_core/parsing/` | review |
| [TASK-003](TASK-003-C抽取器.md) | C 抽取器（include / static / 函数指针 / 宏） | TASK-002 | — | `core/zace_core/parsing/c.py` 等 | review |
| [TASK-004](TASK-004-Cpp抽取器.md) | C++ 抽取器（尽力而为 + 诚实标注） | TASK-003 | — | `core/zace_core/parsing/cpp.py` 等 | review |
| [TASK-005](TASK-005-Markdown-SpecBlock.md) | Markdown SpecBlock 抽取（doctype / 标题树 / mentioned） | — | — | `core/zace_core/parsing/markdown.py` 等 | pending |
| [TASK-006](TASK-006-Chunk模型与解析.md) | Chunk 模型 + unresolved 两阶段解析 + 配置指纹 | TASK-001 | TASK-002..005 | `core/zace_core/chunking/` | pending |
| [TASK-007](TASK-007-索引流水线.md) | 索引流水线：ChangeSet → 增量失效 → 向量对账 | TASK-001, TASK-006 | TASK-008, TASK-009 | `core/zace_core/pipeline/` | pending |
| [TASK-008](TASK-008-Embedding双实现.md) | Embedding Provider 双实现（本地 ONNX 默认 + API） | — | — | `core/zace_core/embedding/` | pending |
| [TASK-009](TASK-009-向量存储.md) | 向量存储（LanceDB）+ hash 复用对账 | — | — | `core/zace_core/vectors/` | pending |
| [TASK-010](TASK-010-检索通道与RRF.md) | 检索通道（Exact/BM25/Vector）+ RRF + 降级 | TASK-001 | TASK-008, TASK-009 | `core/zace_core/retrieval/{exact,bm25,vector,rrf,fusion}.py` | pending |
| [TASK-011](TASK-011-图扩展与Rerank.md) | 图扩展（calls + spec_references）+ 确定性 rerank | TASK-010 | — | `core/zace_core/retrieval/{expand,rerank}.py` | pending |
| [TASK-012](TASK-012-ContextPack组装.md) | ContextPack 组装 + Markdown 渲染 | TASK-010, TASK-011 | — | `core/zace_core/contextpack/` | pending |
| [TASK-013](TASK-013-CLI与Eval.md) | core CLI + engine 装配 + golden runner | TASK-007, TASK-012 | — | `core/zace_core/{cli,engine}.py`、`benches/run.py` | pending |
| [TASK-014](TASK-014-Golden集与基线.md) | golden set 扩充 + 基线报告（中英混合 50+） | TASK-013 | — | `benches/golden/`、`benches/results/` | pending |
| [TASK-015](TASK-015-Bakeoff与校准.md) | embedding bake-off + rerank 初值校准 | TASK-013 | TASK-014 | `benches/bakeoff/` | pending |

### 建议开卡批次（并行安全）

1. **批 1**：TASK-001、TASK-002、TASK-005、TASK-008、TASK-009（互不依赖；002/005 可先合，003/004 接在基座上）
2. **批 2**：TASK-003 → TASK-004（同一条解析线串行，避免 include 逻辑冲突）；TASK-006（001 合入后）
3. **批 3**：TASK-007（006 合入后）；TASK-010（001+008+009 合入后，或先用 fake 并行开发）
4. **批 4**：TASK-011 → TASK-012 → TASK-013（末段收敛为串行，避免接口返工）
5. **批 5**：TASK-014 → TASK-015（需要 013 的 runner 就绪）

Phase 2+ 的任务卡等 M1 达成后由编排者细化（见 `docs/plan/roadmap.md` §2）。

## 泳道与波次（默认分发方式）

| 波次 | 泳道 | 工作区 | 任务卡（按序） | 可并行 |
|---|---|---|---|---|
| W1 | A 索引存储线 | `zace-lane-a` | TASK-001 | 是 |
| W1 | B 解析线 | `zace-lane-b` | TASK-002 → 003 → 004 | 是 |
| W1 | C 文档与向量线 | `zace-lane-c` | TASK-005 → 009 | 是 |
| W1 | D 向量线 | `zace-lane-d` | TASK-008 | 是 |
| W2 | A（继续） | `zace-lane-a` | TASK-006 → 007 | 需 W1 合并 |
| W2 | E 检索线 | `zace-lane-e` | TASK-010 → 011 → 012 | 需 W1 合并 |
| W3 | F 出口与评测 | `zace-lane-f` | TASK-013 → 014 → 015 | 需 W2 合并 |

可复制提示词、用户操作循环与报告模板见 `docs/plan/dispatch.md`。
