# TASK-001：存储层（SQLite schema / FTS5 / jieba 预分词）

> 状态：done ｜ 阶段：Phase 1 ｜ 硬依赖：无 ｜ soft 依赖：无
> 建议分支：`feature/task-001_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/storage/`、`core/zace_core/text/`、`core/tests/storage/`、`core/tests/text/`
> **本卡是全 Phase 1 的关键路径首卡，目标是"API 先冻结、实现随后"，第一个 commit 就要把公开 API 定下来。**

## 目标

交付 per-project 的索引存储层：按 CF-01 建库、读写 chunks/symbols/edges/FTS/增量对账/级联删除；
交付 CJK 预分词模块（D-45：索引与查询双侧同一分词器）。消费方：TASK-006/007/010/011。

## 输入文档（按序读）

1. `docs/design/Module/01-切片存储.md` §2.4、§3.2、§3.3、§4.1、§4.2
2. `docs/contracts/index-schema.sql`（DDL 冻结，含文件头两处规划期裁定）
3. `core/zace_core/types.py`（ChunkDef / FileDelta / SymbolDef / ParsedFile）
4. `core/zace_core/hashing.py`（hash 语义）
5. `docs/design/Module/02-检索策略.md` §4.2-b（CJK 分词要求）

## 冻结接口（本卡不得变更）

- 消费：CF-01 DDL、CF-02 hash 函数、CF-08 数据类型。
- 产出：`Store` 类（你设计签名，但必须覆盖以下动词，且首个 commit 后签名即为下游契约）：
  - `open(project_dir)` / `close()`；WAL；启动时校验 `index_config.schema_version`。
  - 写路径：`apply_file_change(parsed: ParsedFile, chunks: Sequence[ChunkDef], file_content_hash, commit=None) -> FileDelta`；
    `apply_deletions(paths: Sequence[str]) -> None`；
    `upsert_unresolved(refs)` / `resolve_refs(...)` 的存储原语（生命周期算法归 TASK-006）。
  - 读路径（检索侧）：`exact_symbols(name, limit)`、`chunk_by_id(id)`、`chunks_by_ids(ids)`、
    `fts_search(segmented_query, limit) -> list[tuple[chunk_id, bm25_score]]`、
    `edges_for(fqn, kinds)`、`spec_refs_for_symbols(ids)`、`spec_refs_for_spec(spec_block_id)`、`freshness()`。
  - 配置：`get_config(key)` / `set_config(key, value)`。
- `FileDelta` 语义：`new_chunk_ids`（content_hash 新增/变化）＋ `reused_chunk_ids`（hash 未变）＋ `removed_chunk_ids`（旧 hash 消失），
  由本卡按 chunk.content_hash 对账计算；TASK-007 依赖此语义做向量增量。

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `core/zace_core/text/segmenter.py` | `segment(text: str) -> str`（jieba，空格连接；惰性初始化；查询/索引同一函数） |
| `core/zace_core/storage/schema.sql` | DDL 副本，**必须与 `docs/contracts/index-schema.sql` 逐字节一致**（测试强制） |
| `core/zace_core/storage/db.py` | 连接管理、建库、PRAGMA、事务上下文 |
| `core/zace_core/storage/store.py` | `Store` 实现（上述动词） |
| `core/zace_core/storage/__init__.py` | 导出 |
| `core/tests/storage/`、`core/tests/text/` | 测试 |

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/storage core/tests/text -q` 全绿，必须覆盖：
  - DDL 落地：临时目录建库成功；`schema.sql` 与契约文件一致；
  - 增量对账：同一文件两次写入（改 1 个函数）→ `FileDelta.reused` 含未变 chunk、`new` 只含变更 chunk、`removed` 正确；
  - 级联删除：删文件 → files/chunks/symbols/edges/FTS 行全清，且引用被删符号的 `spec_references.stale=1`；
  - **中文 FTS**：写入含中文 docstring 的 chunk，用 `segment("刷新令牌")` 查询命中；同一查询不分词时**不得**命中（证明预分词生效，不是 tokenizer 巧合）；
  - `fts_search` 返回 bm25 分（可用 `bm25(chunks_fts)` 排序）。
- [ ] 行为验收（本机可复现）：`python -c` 脚本对临时库重复执行"建库→写文件→改函数→删除"四步，打印 FileDelta 与级联结果，无异常。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/codegraph/src/db/`（schema.sql + queries + WAL 管理；见 Background/02 §2）
- `source/codegraph/src/extraction/…` 中 FTS5 external content 触发器模式（注意：zace 已裁定独立 FTS 表，不要照抄）
- `source/ragcode/src/indexing/`（generation 对账思想；见 Background/03）

## 明确不做

- 不做向量（TASK-009）、不写解析逻辑（TASK-002..005）、不做二阶段解析算法（TASK-006）；
- 不做跨项目/全局元数据库（属 service，Phase 2）；
- 不引入 ORM（直接 sqlite3）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

### 完成报告（2026-09-10）

- 分支：`feature/task-001_xwz0910`
- 验收：
  - `uv run pytest core/tests/storage core/tests/text -q` → **43 passed**（DDL 落地 / 增量对账 / 级联删除 / 中文 FTS + bm25 / 读路径与解析原语全覆盖）；
  - 行为验收（临时库四步"建库→写文件→改函数→删除"，`python -c`）：无异常，输出见下；
  - 基线：`uv run ruff check .` clean；`uv run python scripts/check_dependency_direction.py` 通过；`uv run pytest` → **44 passed**。
- 关键产物：`core/zace_core/text/{__init__,segmenter}.py`、`core/zace_core/storage/{__init__,db,store,schema}.py`、`core/tests/{storage,text}/`；`schema.sql` 与 CF-01 逐字节一致（md5 `4728a9bdd65990687c59e1c2be4e6e33`）。
- 契约影响：无（CF-01/CF-02/CF-08 均为消费；未改任何契约文件）。
- 与设计偏差：无。
- 未决问题：无。

#### 行为验收输出（临时库四步）

```text
1) 写文件 FileDelta: new=('src/a.py:f:1','src/a.py:g:5') reused=() removed=()；counts={files:1,chunks:2,symbols:2,edges:1,refs_pending:1}；中文命中 1 条
2) 改函数 FileDelta: new=('src/a.py:f:1',) reused=('src/a.py:g:5',) removed=()
3) 重放 FileDelta:   new=() reused=(f,g) removed=()          # 幂等
4) 删除后 counts 全 0，FTS 空，unresolved 空（refs 级联删除）
```

### 冻结 API（首个 commit 即下游契约，TASK-006/007/010/011/012 消费）

`Store.open(project_dir)`（classmethod、WAL、启动校验 `index_config.schema_version`、支持 `with`）/ `close()`；
写：`apply_file_change(parsed, chunks, file_content_hash, commit=None) -> FileDelta`、`apply_deletions(paths)`；
读：`exact_symbols(name, limit=20)`、`chunk_by_id(id)`、`chunks_by_ids(ids)`、`fts_search(segmented_query, limit=50) -> list[(chunk_id, bm25)]`、`edges_for(fqn, kinds=None)`（双向）、`spec_refs_for_symbols(ids)`、`spec_refs_for_spec(spec_block_id)`、`freshness()`；
配置：`get_config/set_config`；行类型：`SymbolRow/EdgeRow/UnresolvedRefRow/SpecRef`；辅助：`counts()`。

卡外补充的存储原语（服务 TASK-006 算法与 TASK-007/013 统计，均已在 docstring 记录）：

- `upsert_unresolved(refs, file_path, language)` / `unresolved_refs(status, file_path)`（去重键 from_fqn+name+kind+IFNULL(line,-1)）；
- `resolve_refs([RefResolution(ref_id, target_fqn, kind?, provenance)])`（写边 + 删行，同事务；kind 缺省 call→calls/import→imports/reference→references）；
- `mark_refs_failed(ref_ids)`（置 failed + 写 name_tail，保留重试）；
- `unresolved_edges(kinds)` / `retarget_edges([EdgeTargetUpdate])`（二阶段解析 `parsed.edges` 的裸 target_name → fqn，落地 types.py EdgeDef 的"由 TASK-006 解析成 fqn"）；
- `add_spec_refs([(spec_block_id, symbol_id)])`（provenance 恒 inferred，D-06；幂等）。

### 裁量记录（卡内授权范围，供评审确认）

1. **FileDelta 三集合两两不重叠**：`new`＝本次 chunk 的 content_hash 不在旧集合；`reused`＝hash 在旧集合（id 可能因行号漂移变化，**复用键是 hash 不是 id**）；`removed`＝旧 id 在本次写入后不再存在。变化 id 只进 `new` 不进 `removed`，保证下游 `upsert(new)`/`delete(removed)` 任意顺序不丢向量。
2. **边按 source 侧归属文件**：变更/删除只清 `source ∈ 旧符号 fqn ∪ 本次 parsed.edges.source_fqn` 的行，不按 target 反删（否则会误删其它文件未重解析的合法边）；跨文件 fqn 化归 TASK-006。
3. **spec_references 级联**：符号 fqn 消失（删除/改名）→ stale=1（多符号同 fqn 全标）；同 fqn 仅行号漂移 → refs 从旧 id 重挂到新 id（保持引用有效）；本文件 spec 块的引用行随文件重写整体删除，等 TASK-006 重匹配重建（二次 ingest 不累积）。
4. **apply_file_change 同时重写** `parsed.edges`（原样入库，裸名待解析）与 `parsed.unresolved`（status 归 pending）；另写 spec_blocks 双表行与 jieba 预分词 FTS 行（D-20/D-45；渲染读 chunks.content 原文）。
5. `freshness()` 只如实报 `indexed_at`（files 最大时间戳）；`stale_files/indexing_files` 属同步层（Module 05）知识，本层无数据源，恒空不猜测（值 D-30）。未引入 ORM，未新增依赖。
6. 新增测试文件名带 `storage_`/`text_` 前缀，避免与其它泳道测试模块重名（pytest 无 `__init__.py` 目录下的 import 冲突）。

### 建议复核点

- `removed_chunk_ids` 的 id 口径是否与 TASK-007 的向量对账实现一致（卡文"旧 hash 消失"在"同文件重复内容 chunk 被删"场景的精确化）；
- `unresolved_edges`/`retarget_edges` 这两个补充原语是否与 TASK-006 计划的两阶段解析实现吻合（若不吻合，TASK-006 可不使用，不影响已冻结动词）；
- `apply_file_change` 的 edges 归属与 FTS 同事务重建是否需在 TASK-007 卡内补充说明。
