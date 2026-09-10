# TASK-007：索引流水线（ChangeSet → 增量失效 → 向量对账）

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-001、TASK-006 ｜ soft 依赖：TASK-008、TASK-009（可先用 fake provider / 内存向量桩开发，合并前切换真实实现）
> 建议分支：`feature/task-007_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/pipeline/`、`core/tests/pipeline/`

## 目标

把"文件变更集"变成"索引更新"的完整流水线：增量解析/切块/入库/嵌入/对账/二阶段解析/新鲜度更新，
是 TASK-013（CLI）与 Phase 2（service 上传）共用的唯一索引入口。

## 输入文档（按序读）

1. `docs/design/Module/01-切片存储.md` §4.1、§4.2、§4.3（增量、指纹、时序）
2. `docs/design/Module/06-服务化与部署.md` §1（core 接口面：`ingest` 的定位；job 归 service，本卡只做同步实现）
3. `core/zace_core/types.py`（ChangeSet/BlobInput/FileDelta）、`core/zace_core/interfaces.py`
4. TASK-001 的 `Store` API、TASK-006 的 splitter/resolver/fingerprint

## 交付内容

- **语言识别策略（R1 口径，2026-09-10 编排者裁定）**：调 `detect_language(path)` 前先做仓库级抬升——若本仓库已见任意 C++ 扩展名文件（`.cc/.cpp/.cxx/.hpp/.hh/.hxx/.ipp/.tpp`；取"本次变更集 ∪ files 表已索引语言"的并集），则 `.h` 按 `cpp` 解析（C++ 仓库里 `.h` 语义上就是 C++ 头），否则沿用 registry 默认（`.h` → C）。判定实现放本卡（pipeline 是唯一知道仓库文件集的地方），registry 不改。

```text
ingest(changes: ChangeSet) -> IngestReport
  1. deleted   → store.apply_deletions（级联删 + spec_references.stale）
                 → vector_store.delete(相关 chunk_ids)
  2. added/modified → 解析（registry，未知语言 → fallback）
                 → splitter → store.apply_file_change → FileDelta
                 → embedding.embed(FileDelta.new 的 embedding_text)
                 → vector_store.upsert(new) / delete(removed)
  3. resolve_pending(store)（TASK-006）+ retry_failed(新符号名集合)
  4. 更新 files.indexed_at / index_config（首建时写指纹）
  5. 返回 IngestReport{added, modified, deleted, chunks_new, chunks_reused, chunks_removed, unresolved_resolved, errors}
```

- `SourceProvider` 协议（本卡自定，pipeline 内部契约）：`read(path) -> bytes`。CLI 提供 repo 目录实现；Phase 2 service 提供 blobs 实现（不提前实现）。
- 增量纪律：**改 1 个函数只重嵌入该 chunk**（content_hash 复用，Module/01 §4.1）。
- 指纹执行（消费 TASK-006 的检测）：`full_reparse` = 遍历 SourceProvider 全部文件重跑第 2 步；`reembed` = 只重算存量 chunks 向量；`none` = 常规增量。
- 单项目串行：本卡不引入并发；跨项目并行属 service 层职责。
- 幂等：同 ChangeSet 重复 ingest 不产生重复行/重复 embed（第二次应全部 reuse）。

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `core/zace_core/pipeline/__init__.py` | 导出 |
| `core/zace_core/pipeline/indexer.py` | `Indexer`（上述 ingest 流程 + 指纹执行） |
| `core/zace_core/pipeline/source.py` | `SourceProvider` 协议 + 目录实现 |
| `core/tests/pipeline/` | 测试（含 fake provider / 内存向量桩） |

## 已就绪的上下游接口（W1 已合并，直接使用，不要重写）

- `Store`（TASK-001）：`apply_file_change` 返回 `FileDelta`（语义见 R4：复用键是 **content_hash** 不是 id）；unresolved 原语 `upsert_unresolved` / `unresolved_refs` / `resolve_refs` / `mark_refs_failed` / `unresolved_edges` / `retarget_edges` / `add_spec_refs`、`counts()`、`freshness()`；`apply_deletions` 已含 spec 引用级联 stale（R5）。
- `splitter` / `resolver` / `fingerprint`（TASK-006）：本卡不重复实现。
- `EmbeddingProvider`：索引侧一律 `embed()`（不要用 `embed_query()`）。
- `VectorStore`（TASK-009）：`upsert/delete/get_hashes/search`；相似度语义见 R10。

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/pipeline -q` 全绿，必须覆盖：
  - 首次 ingest：2 个文件的小 fixture 仓库全量入库（chunks/symbols/edges/FTS 行数与预期一致）；
  - **增量**：改 1 个函数 → 用计数 fake embedding 断言只嵌 1 个 chunk；改注释 → 0 次嵌入；
  - 删除：删文件 → 索引行清空、向量删除、被删符号的 spec_references.stale=1；
  - 幂等：同变更集二次 ingest → 0 次嵌入、0 行新增；
  - 指纹：篡改 index_config 的 parser hash → 触发 full_reparse；改 embedding profile → 只重嵌；
  - 解析失败文件（语法错误）→ 不中断整个 ingest，进 fallback 并在 report.errors 中可见。
- [ ] 与 TASK-008/009 的真实实现集成或桩替换的边界在卡内写清（合并前必须切真实实现跑一遍）。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/ragcode/src/indexing/`（generation/对账机制；见 Background/03）
- `source/notace-tool-rs/src/index.rs`（blob 增量思想，Phase 2 会用到）
- `source/codegraph/src/sync/`（变更检测与重索引流程）

## 明确不做

- 不做 HTTP/上传/checkpoint（Phase 2 service/client）；
- 不做索引 job 表与进度上报（Phase 2 service）；
- 不做并发 worker 池（Module/01 §4.3 允许 V1 串行）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写。IngestReport 字段与 SourceProvider 签名在此记录，供 TASK-013/Phase 2 对齐。）
