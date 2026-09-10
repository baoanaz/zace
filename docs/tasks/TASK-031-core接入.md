# TASK-031：core 接入（EngineManager + BlobSource + 项目 API + `ingest(source=)` 实现）

> 状态：review ｜ 阶段：Phase 2（M2a-1）｜ 硬依赖：TASK-030 ｜ soft 依赖：无
> 建议分支：`feature/task-031_<你的缩写><MMDD>`（从 TASK-030 分支串联）
> 交付物所有权：
> - `service/zace_service/{runtime,blobstore,sync_state}.py`（新建）
> - `service/zace_service/deps.py`（新增 engine_manager 依赖）、`service/zace_service/routers/projects.py`（替换占位实现）
> - `core/zace_core/engine.py`（**仅** §A 的 `ingest(source=...)` 一处）
> - `service/tests/{conftest.py,test_engine_manager.py,test_projects_api.py}`、`core/tests/integration/test_ingest_source.py`（新建）
>
> 清单外文件不得改（尤其 `docs/contracts/**`、`core/zace_core/{types,interfaces,hashing}.py`）。

## 目标

让 service 能在**进程内**调用 core 引擎（D-34 薄壳），并让"客户端上传的 blob"成为索引的源码来源。
交付后 `POST /api/projects/resolve` 可用，且 service 侧已具备完整的上传→索引→检索的内部能力
（HTTP 面在 TASK-032/033 铺开）。

## 输入文档（按序读，只读所需章节）

1. `docs/plan/contracts.md` §3.8（**R33/R35/R36 直接约束本卡**）
2. `core/zace_core/interfaces.py`（CF-07；`ingest` 的 `source` 参数已由编排者冻结，见 R36）
3. `docs/design/Module/06-服务化与部署.md` §1（core 纯库边界）、§2.3（租户双层：本卡只做物理层的 project 目录）
4. `core/zace_core/engine.py`（`Engine` 的全部公开方法）、`core/zace_core/pipeline/source.py`（`SourceProvider` 协议）
5. `core/zace_core/pipeline/indexer.py` 的 `_collect_inputs` / `full_reparse` / `reembed`（理解 §A 的必要性）
6. `core/zace_core/hashing.py`（`blob_hash(path, content)` 语义，CF-02）

## 冻结接口（本卡不得变更）

- **消费**：CF-07（含新增的 `source` 参数）、CF-02（`blob_hash`）、`SourceProvider` 协议（`read` / `list_files`）。
- **产出**：
  - `zace_service.runtime.EngineManager`：`Engine` 单例持有者 + per-project 串行锁（见 §C）
  - `zace_service.blobstore.BlobStore`、`zace_service.sync_state.SyncState`
  - `zace_service.deps.get_engine_manager(request) -> EngineManager`

## §A（core 侧，必须先做）：`Engine.ingest` 支持外部 `source`

`core/zace_core/engine.py::Engine.ingest` 增加关键字参数 `source: SourceProvider | None = None`，
并把它传给 `_source_for` 的替代路径（`self._ingest(...)` 内部使用 `source or self._source_for(project_id)`）。

> **根因更正（2026-09-10，实施 AI 实测推翻编排者的初判）**：不是"chunks 被清空"——
> SQLite 的分块/符号**都还在**，被清空的是**向量索引**（`rebuild` 后重嵌 0 行）；而且
> **指纹会被改写成"一致"**，所以这个错误**不会被重试、也不会再被发现**，检索能力静默退化到不可用。
> 回归测试同时断言了这两点（`core/tests/integration/test_ingest_source.py`）。

**为什么必须做（本卡的立项理由，测试必须覆盖）**：`Indexer.ingest()` 在配置指纹一级/二级失效时会走
`full_reparse` / `reembed`，这两条路径**遍历 `source.list_files()` 重建**。上传模式下若 `_source_for`
返回 `_EmptySource`（无本地目录绑定），结果是：

```text
库里有文件 + 指纹缺失（异常中断）→ check_fingerprint 判 FULL_REPARSE
 → chunks 保留、向量索引清空（重嵌 0 行）
 → 指纹被改写为"一致" → 该错误永不重试、不可自愈
 → search 的 answerable 由 true 静默变为 false
```

最小复现（测试里要断言"清空"与"修复后不清空"两种结果）：

```python
# 1) 用 ChangeSet 正常 ingest 一个文件（source=None）
# 2) store.set_config(PARSER_CONFIG_KEY, "broken")   # 伪造指纹不一致
# 3) engine.ingest(pid, ChangeSet(), source=None)    → 索引被清空（错误行为）
# 4) engine.ingest(pid, ChangeSet(), source=blob_source) → 正常重解析（正确行为）
```

## §B（service 侧）：blob 镜像与同步状态（R35：落文件，不建 DB）

```text
{data_root}/projects/{project_id}/
├── index.db / vectors/ / project.json      ← core 拥有（不动）
├── blobs/{blob_hash[:2]}/{blob_hash}       ← service 拥有：内容寻址镜像（原始字节）
└── sync-state.json                         ← service 拥有：同步账本
```

`sync-state.json`（`version: 1`）：

```json
{ "version": 1, "branch": null, "commit": null,
  "files": { "src/a.py": { "blobHash": "...", "size": 123, "updatedAt": 1757500000 } },
  "checkpoints": { "<cid>": ["<hash>", "..."] } }
```

- 原子写（`tmp` + `replace`），损坏时**不抛异常**：返回空状态并记日志（与 core 的 `read_manifest` 同口径）。
- `BlobStore`：`put(path, blob_hash, data) -> bool`（已存在返回 False）、`get(blob_hash) -> bytes`（缺失抛 `FileNotFoundError`）、`exists(hash)`、`delete(blob_hash)`、`usage() -> (count, bytes)`。
- **路径安全**：拒绝绝对路径、`\`、`..`、空段（与 `zace_core.pipeline.source.SourcePathError` 同一口径，直接复用其校验思路）。

`BlobSource`（实现 `SourceProvider`，给 core 用）：

- `list_files()` = `sync-state.files` 的 key（稳定排序）——即"项目已知全部文件"；
- `read(path)` = 按 `files[path].blobHash` 从 `BlobStore` 取原始字节；账本缺失或 blob 缺失→ `FileNotFoundError`（core 会把它记进 `report.errors`，不中断整次 ingest）。

## §C（service 侧）：`EngineManager`

- `EngineManager.open(data_root: Path) -> EngineManager`：内部 `Engine.open(data_root)`（provider 懒构造，起服务不加载模型）。
- 方法：`resolve_project(identity_key, display_name="")`、`sync_status(project_id)`、`search(project_id, query, max_tokens)`（用 `Engine.search_with_trace`，R33）、`delete_project(project_id)`（清 core 目录 + blobs + sync-state）、`blob_source(project_id) -> BlobSource`、`sync_state(project_id) -> SyncState`、`project_paths(project_id) -> (blob_store, state)`。
- **并发**：FastAPI 会在线程池里跑同步 handler，而 core 是"单写者"假设（TASK-001/009/007 口径）→ 每 project 一把 `threading.Lock`，**同一 project 的 ingest / delete 串行**，不同 project 可并行。锁表随 project 懒创建；`delete_project` 也持锁。
- 不做 per-project 引擎实例缓存（core 的 `Store`/`VectorStore` 是 per-call 打开，`Engine` 本身无状态句柄）——**不要提前优化**。

## §D（HTTP 面）：项目 API（替换 `routers/projects.py` 的占位）

- `POST /api/projects/resolve`：body `{identityKey, displayName?}` → `{projectId, created}`（幂等，CF-05）。
- `GET /api/projects`：列出 `{data_root}/projects/*/project.json` 的摘要（本地模式：全部；M2c 才按 user 过滤）。
- `GET /api/projects/{id}`：`{projectId, displayName, createdAt, sync: SyncStatus, blobs: {count, bytes}}`。
- `DELETE /api/projects/{id}`：级联删除（core 目录 rm -rf + 清锁），204；不存在 → 404 `project_not_found`。

## 验收标准（DoD）

- [ ] **§A 的"静默清空"回归测试**（core 侧，`core/tests/integration/test_ingest_source.py`）：同一场景下 `source=None` 清空、`source=BlobSource` 正确重建，两条断言都要有；测试用确定性假 embedding provider（参考 `core/tests/integration/conftest.py`），**CI 不联网**。
- [ ] `BlobStore`：put/exists/get/delete/usage 单测；重复 put 同 hash 返回 False 且不覆盖字节。
- [ ] `SyncState`：写读往返、损坏 JSON → 返回空状态不抛、原子写（写入过程中断不留半截文件）。
- [ ] `BlobSource`：`list_files` 与账本一致；`read` 对缺失 blob 抛 `FileNotFoundError`；路径越界被拒。
- [ ] `EngineManager`：`resolve_project` 幂等（同 identityKey 两次 → 同 projectId，第二次 `created=False`）；**并发测试**：两个线程同时 `ingest` 同一 project 不互踩（断言不抛、最终 chunk 数正确）；`delete_project` 后目录消失。
- [ ] 项目 API（`service/tests/test_projects_api.py`，用 `httpx.ASGITransport`/`TestClient` + temp data_root）：
      resolve 幂等、list/get/delete、404 形态、`DELETE` 后 `GET` 返回 404。
- [ ] 端到端小闭环（贴执行记录）：通过 service 内部 API 上传 2 个文件（含 1 个 markdown）→ `sync_status` 数字正确 → `search` 能命中上传文件里的符号。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- 不做 `batch-upload` / `checkpoint` / `deletions` / `sync/status` 的 HTTP 面（TASK-033）。
- 不做查询 API（TASK-032）。
- 不实现鉴权与用户概念（M2c）。
- **不建第二套 DB**（R35：JSON 账本 + blob 镜像足够；M2c 再引入 `zace-meta.db`）。
- 不实现 D-28 的 `.gitignore` 解析（那是 client 侧 TASK-041 的职责；service 只接收客户端给的文件集）。
- 不改 `Engine` 的其它行为（尤其不顺手重构 `_source_for` / 扫描逻辑）。

## 参考源码锚点（只读）

- `core/zace_core/engine.py`（`_source_for` / `_open_project` / `ingest_repo`）
- `core/tests/integration/conftest.py`（确定性假 provider 的既有实现，直接复用模式）
- `core/zace_core/pipeline/source.py`（`SourcePathError` 的路径校验口径）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；**必须包含 §A 最小复现的前后对照输出**。

## 执行记录

- **日期 / 分支**：2026-09-10 ｜ `feature/task-031_xwz0910`（从 `feature/task-030_xwz0910` 串联）
- **关键产物**：`service/zace_service/{runtime,blobstore,sync_state}.py`、`service/zace_service/deps.py`（追加 engine_manager / require_project_id）、`service/zace_service/routers/projects.py`（替换占位）、`core/zace_core/engine.py`（仅 §A）、`core/tests/integration/test_ingest_source.py`、`service/tests/{conftest,test_engine_manager,test_projects_api}.py`。

### 验收命令与结果

```text
$ uv run ruff check .
All checks passed!
$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
$ uv run pytest
552 passed, 2 skipped, 2 warnings in 12.74s     # 030 后为 521+2 → 本卡新增 31 条
$ uv run pytest service/tests
48 passed                                       # 030 的 20 条 + 本卡 28 条
$ uv run pytest core/tests/integration/test_ingest_source.py -q
3 passed
```

### §A 最小复现的前后对照（实测输出）

```text
chunks(before): 5 vectors: 5
source=None   → chunks: 5 vectors: 0 answerable: False
source=Blob   → chunks: 5 vectors: 5 answerable: True
```

**对卡内描述的一处实测修正（重要）**：卡内写“_run 清掉全部 chunk”，实测并非如此——
FULL_REPARSE 下 SQLite 侧没有任何文件被重处理，所以 ``files``/``chunks``/``symbols`` **原样保留**；
真正的损失是 ``_rebuild_vectors()`` 先重建向量表、再因 ``list_files()`` 为空而重嵌 0 行，结果是
**向量索引被清空**（5 → 0），检索从 3 通道退化为单通道，``answerable`` 由 ``True`` 掉到 ``False``。
更坏的一点：结束后 ``write_fingerprint`` 把指纹改写成“一致”，因此**错误不会被重试也不会被发现**
——回归测试把这一点也断言在内（``test_fingerprint_invalidation_without_source_wipes_vector_index``）。
两条断言（清空 / 重建）都在 ``core/tests/integration/test_ingest_source.py``。

### 端到端小闭环（service 内部 API：上传 → 索引 → 检索）

```text
=== ① upload → ingest report ===
{'added': 2, 'chunks_new': 5, 'files_parsed': 2, 'vectors_upserted': 5, 'spec_refs': 2,
 'languages': ('markdown', 'python')}
=== ② sync_status ===
{"projectId": "2cfc521b099a1e37", "filesIndexed": 2, "chunks": 5, "symbols": 2, "edges": 0,
 "pendingJobs": 0, "indexingFiles": [], "lastIndexedAt": 1789045160, "branch": null,
 "commit": null, "blobs": {"count": 2, "bytes": 414}, "checkpoints": 0}
=== ③ search 命中上传文件里的符号 ===
channelsUsed: ('exact', 'bm25', 'vector') | candidates: 5 | answerable: True high
## Relevant Context
### Code
[E1] TokenService.refresh_token — src/token_service.py:1-9
     reason: explicit symbol TokenService.refresh_token + exact rank 1 + bm25 rank 2 + vector 0.5635 + explicit symbol/path hit +2.0 + query symbol == chunk symbol +1.0 + 3-channel consensus +0.5 + 相邻区间合并
     1 | """令牌服务模块。"""
     ... （省略 1 行）
     4 | class TokenService:
     6 |     def refresh_token(self) -> str:
     8 |         return "old"
```

（上传 2 个文件均为 service 内部路径：blob 镜像 → 账本 → ``ingest(source=BlobSource)``；
HTTP 面在 TASK-033。markdown 也进索引：``spec_refs: 2`` 证明 design 文档的 spec 块落库。）

### 越界改动声明（清单外文件 1 个）

`service/tests/test_skeleton.py`（TASK-030 的文件）：本卡把 `GET /api/projects` 从占位 501 换成了真实实现，
该文件的“占位路由 → 501”参数化列表因此必然失败。最小修改：列表改为“M2a-1 期间仍占位的端点”
（`/api/auth/*` 6 条 + `/api/usage/projects/{id}`），并在注释里指明 projects/query/sync 的真实行为由 031..033 的测试覆盖。
改动仅限该参数化列表，不影响 TASK-030 的任何断言语义（错误信封/requestId/脱敏/CF-05 路径快照全保留）。

### 契约影响

无契约文件改动（`docs/contracts/**` 未动）。按编排者在 main 上已冻结的 CF-07 新增参数实现 core 侧；
新增的 service 侧产出面（`EngineManager` / `BlobStore` / `SyncState` / `BlobSource` /
`deps.require_project_id`）属实现细节，TASK-032/033 依赖它们。

### 与设计偏差

1. **`EngineManager.ingest` 转调 `Engine._ingest`（私有方法）**：CF-07 的 ``ingest`` 只回 ``job_id``，
   而同步 API 的 ``batch-upload`` 必须如实上报 ``added/skipped/errors``（D-30）→ 非拿到
   ``IngestReport`` 不可。卡内只允许 §A 一处 core 改动，故未在 core 新增公开方法；
   已在模块 docstring 与“未决问题”里写明这个契约缺口。
2. **`deps.py` 追加 `require_project_id`**：R37（本地模式可省略 projectId）需要一个共享实现点，
   而 TASK-032/033 的文件清单里没有 ``deps.py``（它们的授权只含 routers/query.py、routers/sync.py 等），
   故在此落地，供后续两卡直接复用。
3. **`sync_status` 返回 camelCase dict**（core 字段 + ``branch/commit/blobs/checkpoints``）：
   直接对齐 CF-05 的 ``SyncStatus`` 与 TASK-033 的追加字段，避免路由层再做一次映射。
4. **`BlobStore` 目录用 ``blobs/{hash[:2]}/{hash}``**（与 §B 一致）；`put` 额外校验
   ``path`` 的仓库相对路径安全性（与 ``SourcePathError`` 同一口径），不只校验 hash。
5. **并发测试的锁断言方式**：不断言“真的发生过竞争”，而是断言“两线程同时 ingest 不抛异常且
   最终 chunk 数正确”（core 是单写者假设，锁是防止互踩而非提升吞吐）。

### 未决问题

1. **core 缺“ingest 并返回 IngestReport”的公开面**（建议编排者裁决）：当前 service 以
   `Engine._ingest` 取报告，属跨包访问私有方法。可选出路：① 在后续卡把 `Engine.ingest` 的返回值
   （或一个 `ingest_report()`）纳入 CF-07；② 长期不管（同 monorepo 同版本演进，R33 已允许用 core 公开类）。
2. **确定性假 provider 在 core 与 service 的测试里各有一份**（`core/tests/integration/conftest.py`
   与 `service/tests/conftest.py`）：`core/tests` 不是可导入包，service 测试不能反向依赖它。
   若后续出现第三处，建议把假 provider 提到 `zace_core.testing`（需单独评估是否污染生产包）。
3. **`checkpointId` 与检索的强校验不在本卡**（TASK-033 也只需登记，client 侧优化）；本轮无遗留缺陷。
4. 上传路径的 `.gitignore` 解析仍归 client（TASK-041）；service 只接收客户端给的文件集（D-28）。

### 建议复核点

① §A 的 core 改动是否真是“一行语义”（`source or self._source_for(project_id)`）+ 回归测试的两侧断言；
② `EngineManager` 的锁粒度与 `delete_project` 的锁内 rm -rf；③ `require_project_id` 的 R37 语义
（0 个项目 404 / 多项目 409，不隐式选一个）；④ `sync_state` 的损坏容忍与原子写测试。
