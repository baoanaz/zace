# TASK-001：存储层（SQLite schema / FTS5 / jieba 预分词）

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：无 ｜ soft 依赖：无
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

（实施 AI 在此填写。）
