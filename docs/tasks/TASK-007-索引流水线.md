# TASK-007：索引流水线（ChangeSet → 增量失效 → 向量对账）

> 状态：done ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-001、TASK-006 ｜ soft 依赖：TASK-008、TASK-009（可先用 fake provider / 内存向量桩开发，合并前切换真实实现）
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

### 2026-09-10 ｜ 分支 `feature/task-007_xwz0910`（基于 `feature/task-006_xwz0910`）｜ 状态 review

**交付物**：`core/zace_core/pipeline/{__init__,indexer,source}.py`、
`core/tests/pipeline/{__init__,conftest,test_indexer,test_pipeline_real_stack}.py`（新增 19 个测试）。

**验收命令与结果**：

| 命令 | 结果 |
|---|---|
| `uv run pytest core/tests/pipeline -q` | 19 passed |
| `uv run pytest` | 281 passed, 2 skipped（W1 220 + TASK-006 42 + 本卡 19，无回归） |
| `uv run ruff check .` | clean |
| `uv run python scripts/check_dependency_direction.py` | 通过 |

**IngestReport 字段（供 TASK-013 / Phase 2 对齐，卡内要求记录）**

```text
卡内规定：added / modified / deleted / chunks_new / chunks_reused / chunks_removed /
          unresolved_resolved / errors
本卡补充（观测与自证）：invalidation（none|reembed|full_reparse）、files_parsed、
          vectors_upserted、vectors_deleted、edges_retargeted、spec_refs、ambiguous_refs、
          skipped_files（二进制跳过）、orphan_files（删除时无法枚举 chunk id）、languages（已见语言）
```

**SourceProvider 签名（pipeline 内部契约，卡内要求记录）**

```python
class SourceProvider(Protocol):
    def read(self, path: str) -> bytes: ...          # 仓库相对路径（正斜杠）
    def list_files(self) -> Sequence[str]: ...       # 稳定排序；全量重解析 / reembed 枚举的输入
```
卡内只列了 `read`；`list_files` 是卡内「遍历 SourceProvider 全部文件」的必需能力，故补齐。
`DirectorySource` 另含路径安全校验（拒绝绝对路径/``..``/反斜杠，抛 `SourcePathError`）。
Phase 2 service 必须提供 blobs 侧的 `list_files`（按上传目录/DB 列举）。

**实现口径（评审重点）**

1. **R1 语言抬升**：「仓库已见语言」持久化在 `index_config.indexed_languages`（JSON 数组，
   由 pipeline 维护；不改 registry、不改 DDL）。判定集 = 已持久化语言 ∪ 本次输入文件的 registry
   默认语言；含 `cpp` 时 `.h` 走 C++。C++ 扩展名集合取自 registry（`EXTENSION_LANGUAGE`，
   包含卡内 R1 清单全部项，外加 `.c++`/`.h++`）。测试覆盖「仅 .h → C」「.cpp 出现后 .h → C++」。
2. **增量嵌入判据（重要）**：不只按 `FileDelta.new`，而是「`VectorStore.get_hashes(new_id 集合)`
   与该 chunk 的 content_hash 不一致才嵌」。原因：`chunk_id` 含 `start_line`（D-04 不追求跨代稳定），
   删中间一个函数会让后面 chunk 的 id 漂移——这些 chunk 的 content_hash 在 `FileDelta` 里属
   `reused`，但向量库里没有新 id 的行。若不补嵌，这些 chunk 会永久失去向量（检索侧取不到）。
   R4 的「复用键是 hash 不是 id」在 TASK-009 的 ``VectorStore``（按 chunk_id 存行、无读回原语）下
   只能通过“重新嵌入同 hash 的新 id”落地（一次性代价）。这也是 `chunks_reused` 与
   `vectors_upserted` 可能不相等的原因。
3. **指纹两档执行**：`reembed` = `VectorStore.rebuild(dim)` + 重嵌存量（**不写 SQLite**；
   存量 chunk 通过「遍历 provider → 重解析切分拿 id → `Store.chunks_by_ids` 取回库内权威内容」枚举）；
   `full_reparse` = provider 全量重跑增量 + 重建向量表；两者末尾都刷新 {
   ``parser_config_hash``/``embedding_model``/``embedding_dim``}。首建时也写指纹。
4. **向量清理**：`FileDelta.removed_chunk_ids` 直接删；整文件删除用 Indexer 记录过的 chunk id 清；
   整表重建（reembed/full_reparse）天然清除历史孤儿。
5. **二阶段解析接入**：每次 ingest 末尾依次 `resolve_pending` → `retry_failed`（本次新符号名）→
   `resolve_edges`（裸名边 fqn 化）→ `link_spec_references`（本卡新增的调用点；卡内步骤 3 未列，
   但 TASK-006 §D 要求 spec 引用写库，且 `apply_file_change` 会先删本文件旧引用，必须在本步重建）。
6. **错误处理**：未知语言 / `ParserUnavailableError` / 抽取器异常 → 兜底 `ParsedFile`（不中断）；
   语法错误进 `report.errors`；含 NUL 的二进制文件跳过并进 `skipped_files`；扫描期读失败也进 `errors`。

**契约影响**：无（不改 `docs/contracts/**` 与冻结类型/接口；只读消费 `Store`/`VectorStore`/
`EmbeddingProvider`/TASK-006 原语）。新增 `index_config.indexed_languages` 键与 `SourceProvider.list_files`
属 L1（前者是 KV 表新增键，不动 DDL/列语义；后者是 pipeline 内部契约）。

**与设计偏差**：无功能性偏差；两条实现期解释已记录在第 2、5 条（id 漂移需补嵌；spec 引用重建时机）。

**未决问题**

1. **`Store` 缺「按文件列举 chunk id / 列举全部 chunk」原语**（本卡两处受阻）：
   (a) 整文件删除时无法枚举向量 → 跨进程删除会留孤儿向量（当前用进程内记录缓解 + `orphan_files`
   如实上报；孤儿向量在检索侧会被 `chunks_by_ids` 跳过，下一次整表重建清除）；
   (b) `reembed` 需要“不重解析”的廉价存量枚举（当前靠遍历 provider 重解析拿 id，CPU 成本等同
   一次全量解析）。建议 L2：`Store.chunk_ids_for_file(path)` / `Store.iter_chunks()` /
   `apply_deletions` 返回被删 id。
2. **`Store` 缺「列举全部文件（path + language + content_hash）」原语**：TASK-013 计算 ChangeSet、
   Phase 2 同步对账都需它（当前只能靠 provider 清单 + 逐文件重解析）；建议 L2 时一并考虑。
3. **`index_config.indexed_languages` 是否升格为契约键**：CF-01 表头只列举了 4 个键；若编排者
   认为该键属跨卡契约（Phase 2 service 也要读），建议补记到 `docs/plan/contracts.md` §3.2。
4. **`max_input_tokens` 不参与指纹**（同 TASK-006 未决问题 3），本卡按卡内口径未处理。

**建议复核点**：增量嵌入判据（第 2 条，影响正确性）、R1 抬升的键选择（未决 3）、
指纹两档的执行边界（第 3 条）、`orphan_files` 的诚实性（未决 1）。
