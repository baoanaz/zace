# TASK-010：检索通道（Exact / BM25 / Vector）+ RRF + 降级

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-001 ｜ soft 依赖：TASK-008、TASK-009（可先用 fake provider / 内存向量桩，合并前切真实实现）
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

（实施 AI 在此填写。各通道配额与 tier 赋值的最终口径必须记录，TASK-011/012 依赖它。）
