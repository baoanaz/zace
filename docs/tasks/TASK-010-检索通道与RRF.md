# TASK-010：检索通道（Exact / BM25 / Vector）+ RRF + 降级

> 状态：review ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-001 ｜ soft 依赖：TASK-008、TASK-009（可先用 fake provider / 内存向量桩，合并前切真实实现）
> 建议分支：`feature/task-010_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/retrieval/exact.py`、`bm25.py`、`vector.py`、`rrf.py`、`fusion.py`、`core/tests/retrieval/`
> （`retrieval/expand.py`、`rerank.py` 归 TASK-011；本卡不得改这两个文件）

## 目标

交付 General 路径的三路召回与 RRF 融合，输出统一 `Candidate` 列表（CF-04）：
Exact 双档（D-15）→ BM25（FTS5 + CJK 预分词）→ Vector（ANN + 查询缓存 + 降级），
RRF(K=60) 纯融合、不加通道权重（D-16）。路由四分支属 Phase 3，本卡只做 General。

## 输入文档（按序读）

1. `docs/design/Module/02-检索策略.md` §4.2、§4.3、§5（时序与降级）、§1（R1 约束）
2. `core/zace_core/types.py`（`Candidate`）、`core/zace_core/interfaces.py`（`EmbeddingProvider`）
3. TASK-001 的 `Store` 读路径 API、TASK-008/009 的 provider/vector API

## 交付内容

| 通道 | 规则 |
|---|---|
| Exact-Explicit | 反引号包裹标识符 / 含扩展名路径 / `::` 与 `.` 标识符链 → `Store.exact_symbols` 精确/fqn 匹配，全量进池（≤20）；候选标记 `explicit=True` 语义（写在 `reasons`/`tier`） |
| Exact-Inferred | 正则抽取驼峰/蛇形/SCREAMING（codegraph 模式）→ top 20，普通种子；**它只是召回种子不是精确证据**（D-15） |
| BM25 | `Store.fts_search(segment(query), top 50)`；查询侧必须与索引侧同一分词器（D-45）；generated 文件不排除（rerank 降权） |
| Vector | query embedding —— **必须调用 `provider.embed_query()`**（CF-09 契约：e5 类模型 query/passage 前缀不同，用 `embed()` 会显著掉质量；同 query 60s 内复用，进程内 TTL 缓存）→ `vector_store.search(top 50)`；超时/异常 → 降级为 Exact+BM25 双通道并如实标记 `degraded=True`（Module/02 §5） |
| 融合 | `rrf_score = Σ 1/(60+rank)`；chunk_id 去重；输出 ~120 候选，含 `channel_ranks` / `tier`（Exact-Explicit=0、BM25=1、Vector=2）/ `reasons` |

- 三通道并行（可先串行实现，接口按并行语义设计：`recall_*` 返回列表，fusion 统一收集）。
- tier 语义遵守 D-17：tier 是元数据，不作为排序键；排序分 = `score`（此处初值 = rrf_score）。

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `core/zace_core/retrieval/__init__.py` | 导出 + `recall(query, limits) -> list[Candidate]` 主编排 |
| `core/zace_core/retrieval/exact.py` | Explicit/Inferred 判定与符号匹配 |
| `core/zace_core/retrieval/bm25.py` | FTS 通道 |
| `core/zace_core/retrieval/vector.py` | 向量通道（含缓存与降级） |
| `core/zace_core/retrieval/rrf.py` | RRF 实现（纯函数） |
| `core/zace_core/retrieval/fusion.py` | 去重与候选合并 |
| `core/tests/retrieval/` | 测试 |

## 可直接使用的上游实现（W1 已合并）

- `Store`（TASK-001）：`exact_symbols` / `fts_search(segmented_query, limit)` / `chunk_by_id` / `chunks_by_ids` / `edges_for` / `spec_refs_*` / `freshness`；FTS 返回 **bm25 原始分（越小越相关）**，转排名前留意方向。
- `zace_core.text.segment()`：CJK 预分词（查询侧必用，与索引侧同一分词器）。
- `EmbeddingProvider`（TASK-008）：`embed_query()` 用于检索侧；`profile.dim` 决定向量库维度。
- `VectorStore`（TASK-009）：`search(vector, top_k)` 返回**余弦相似度（越大越相关）**。

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/retrieval -q` 全绿，必须覆盖：
  - Explicit 判定：`` `refresh_token` `` / `src/auth/token_service.py` / `TokenService::refresh` 三形态；Inferred 抽取：`refreshToken` / `refresh_token` / `REFRESH_TOKEN`；
  - RRF 数学：手工构造两通道排名，断言分数与排序（含 K=60 常量断言）；
  - 共识优先：双通道命中候选排在单通道之前（构造数据）；
  - 中文查询：`segment` 后 BM25 命中（复用 TASK-001 的样例型）；
  - 降级：vector 通道抛异常 → 返回双通道结果 + `degraded` 标记，不抛异常；
  - 缓存：同一 query 30 秒内两次调用 → embedding 只调 1 次（计数 fake）。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/codegraph/src/context/`（NL query → 符号抽取 → FTS 路径；见 Background/02 §5）
- `source/GitNexus/gitnexus/src`（标准 RRF K=60 与多通道融合；见 Background/04 §5）
- `source/ragcode/src/retrieval/`（反面参考：不要 15 路专门化；只取"通道 + 融合"骨架）

## 明确不做

- 不做轻路由四分支（Phase 3）；不做图扩展与 rerank（TASK-011）；不做 ContextPack 组装（TASK-012）；
- 不引入加权 RRF / 分数归一化（D-16 明确否决）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

### 2026-09-10 / feature/task-010_xwz0910（泳道 E，本地分支交付，基于 main `abf9c00`）

**完成报告**

- 分支：`feature/task-010_xwz0910`
- 验收：
  - `uv run pytest core/tests/retrieval -q` → 64 passed（覆盖 Explicit 三形态 / Inferred 三形态 /
    RRF 数学与 K=60 / 共识优先 / 中文 BM25 / 向量降级 / TTL 缓存计数）；
  - 基线三条：`uv run ruff check .` → All checks passed；
    `uv run python scripts/check_dependency_direction.py` → 通过；`uv run pytest` → 284 passed, 2 skipped。
- 关键产物：`core/zace_core/retrieval/{__init__,exact,bm25,vector,rrf,fusion}.py`、
  `core/tests/retrieval/{conftest,test_exact,test_bm25,test_vector,test_rrf,test_fusion,test_recall}.py`。
- 契约影响：无（未动 `types.py` / `interfaces.py` / `pyproject.toml`，零新增依赖）。
- 与设计偏差：无实质偏差（Module/02 §4.2/§4.3/§5 逐项落地）；三处口径细化见下。
- 建议复核点：① 通道 key 与 tier 口径表（下）；② BM25 查询归一化是否接受；
  ③ 显式路径不做文件枚举的限制（未决问题 1）；④ `recall` 签名与卡内草稿的差异。

**通道配额与 tier 赋值口径（冻结，TASK-011/012 依赖）**

| 通道 key | 通道 | 配额（默认） | tier | 理由 |
|---|---|---|---|---|
| `exact` | Exact-Explicit | 20（全量进池上限） | 0 | 精确证据（D-15） |
| `inferred` | Exact-Inferred | 20 | 1 | 召回种子，非精确证据（D-15） |
| `bm25` | BM25（FTS5） | 50 | 1 | 词法；卡内明确为 1 |
| `vector` | Vector（ANN） | 50 | 2 | 语义；卡内明确为 2 |

- 卡内只规定了三通道 tier（Explicit=0 / BM25=1 / Vector=2）；**Inferred 未规定**，本卡定为
  **tier 1**（与 BM25 同为"词法级种子"）；合并后 `tier = min(各通道 tier)`（最可信档位）。
- `channel_ranks` 的 key 即上表通道名（Inferred 单列为 `inferred`，让 TASK-011 能区分
  "精确证据"与"召回种子"而无需解析 reasons）；rank 1-based，以候选自报排名为准。
- `reasons` 文本前缀：`explicit symbol` / `explicit path` / `inferred symbol` / `bm25` /
  `vector`，后跟具体值（如 `bm25 -3.1234`、`explicit symbol TokenService.refresh`）。
- `kind`：`spec_block` → spec；`fallback_block` → fallback；测试路径 → test；其余 code。

**实现口径细化（L1，未改契约）**

1. **BM25 查询归一化**（`bm25.bm25_query_text`）：MATCH 串用 `segment(query.replace("`"," ")
   .replace("::"," "))`。卡内写的是 `segment(query)`；但 jieba 会把 `` ` `` 与 `:` 切成正文
   给不出的 token，FTS5 隐式 AND 直接令 `TokenService::refresh` 这类查询**全通道失配**。
   归一化只作用于 BM25 的 MATCH 串，分词器与索引侧保持同一函数（D-45 不破）。
2. **Explicit 路径词元的池化**：`exact` 通道只对**符号**词元做 `exact_symbols`；路径词元
   不枚举文件（见未决问题 1），而是作为装填/rerank 信号：池内 `path` 命中该路径的候选
   升到 tier 0 并追加 `explicit path`。
3. **RRF 同分确定性 tie-break**：分降 → 通道数降（共识优先）→ 最佳单通道排名升 →
   chunk_id 字典序。tier **不参与排序**（D-17）。
4. **`recall` 签名**（卡内草稿为 `recall(query, limits)`）：实现为
   `recall(store, query, *, provider=None, vector_store=None, limits=None, cache=None)`,
   返回 `RecallResult(query, candidates, degraded, degraded_reason, channels_used)`——
   需要 store 与 soft 依赖（TASK-008/009）传入，且 DoD 要求暴露 `degraded`。
5. **向量超时**：`RecallLimits.vector_timeout_s`（默认 5.0s，`None` 关闭）在独立线程执行
   向量通道，超时抛 `VectorTimeoutError` → `recall` 统一降级。
6. **降级单点**：向量通道只抛 `VectorChannelError`（超时为其子类），降级决策与
   `degraded` 标记只在 `recall` 里做（缺失 provider/vector_store 也计入降级）。

**未决问题**

1. **显式路径无法枚举文件切片**：`Store` 无"按文件路径读切片/符号"的读 API（TASK-001 未交付，
   W2 的 TASK-006/007 也未补充），因此 "`src/auth/token_service.py` 里有什么" 这类查询的
   路径强种子只能作用于**已被其它通道召回**的同路径候选，不能全量进池。建议编排者裁决：
   在 TASK-006 或后续给 `Store` 增一个 `chunks_in_files(paths)` / `symbols_in_files(paths)`
   读 API（L2，属 TASK-001 文件所有权）；在此之前本卡保持"标记 + 已召回候选升档"口径。
2. **`files.generated` 无读 API 且 W1 恒为 0**：TASK-011 rerank 的 "−generated 文件" 特征
   目前既无读路径、也无真实数据源（`apply_file_change` 写死 `generated = 0`）。
   本卡不涉及；已在下游卡提示。
