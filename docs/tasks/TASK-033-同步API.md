# TASK-033：同步 API（batch-upload / checkpoint / deletions / sync status）

> 状态：pending ｜ 阶段：Phase 2（M2a-1）｜ 硬依赖：TASK-031 ｜ soft 依赖：无
> 建议分支：`feature/task-033_<你的缩写><MMDD>`（从 TASK-032 分支串联）
> 交付物所有权：
> - `service/zace_service/routers/sync.py`（替换占位实现）
> - `service/zace_service/blobstore.py`、`service/zace_service/sync_state.py`（**仅允许追加** §D 需要的辅助方法；TASK-031 建立的既有语义不得改）
> - `service/tests/test_sync_api.py`（新建）
>
> 清单外文件不得改（尤其 `core/zace_core/**`、`docs/contracts/**`）。

## 目标

把 Module/05 §3.3 的同步协议在**服务端**落地，让 TASK-040 的 client 有可对接的目标：
客户端扫描/对账/上传，服务端接收 blob、维护同步账本、触发增量索引、响应删除与状态查询。

这是 D-27（懒同步）里"服务端那一半"。

## 输入文档（按序读，只读所需章节）

1. `docs/design/Module/05-MCP与同步.md` §3.1-§3.6（协议时序、缓存与幂等、checkpoint、首同步、freshness）
2. `docs/contracts/openapi.yaml`（CF-05：sync 四条路径与"幂等语义"说明）
3. `docs/plan/contracts.md` §3.8（R35 状态存储、R36 source、R37 projectId 可省略）
4. `docs/tasks/TASK-031-core接入.md`（账本与 blob 镜像的既有语义——本卡在其上做 HTTP 面）
5. `core/zace_core/hashing.py`（`blob_hash(path, content)`：**含 path**，用于校验客户端上报）

## 冻结接口（本卡不得变更）

- **消费**：CF-05 四条路径与"batch-upload 重复 blobHash 返回 accepted / deletions 幂等"语义；CF-02 `blob_hash`；CF-07 `ingest(..., source=)`。
- **产出**：`batch-upload` 的响应扩展字段（client TASK-040 依赖）：
  ```
  { accepted: [blobHash], skipped: [path], report: {added, modified, deleted, chunksNew,
    chunksReused, chunksRemoved, filesParsed, errors: [str], skippedFiles: [path]} }
  ```

## 端点行为（必须逐条实现）

### `POST /api/sync/batch-upload`

- 入参：`{projectId?, branch?, commit?, blobs: [{path, blobHash, contentB64}]}`
- 校验（全部走 CF-05 错误信封，**不要 500**）：
  - 单批解码后总字节 ≤ 1 MiB（Module/05 §4）→ 否则 **413 `batch_too_large`**；
  - `path` 安全（无绝对路径 / 无 `\` / 无 `..`）→ 否则 400 `invalid_path`；
  - `base64` 解码失败 → 400 `invalid_content_encoding`；
  - **`blobHash` 必须等于 `blob_hash(path, content)`**（CF-02 含 path 语义）→ 不一致 400 `blob_hash_mismatch`（宁可拒绝，也不让账本被污染）；
  - 空 `blobs` → 400 `empty_batch`。
- 幂等：`(path, blobHash)` 已存在 → **仍计入 `accepted`**（CF-05 明确），且不重复写字节。
- 落盘 + 更新账本 → 调 `engine.ingest(project_id, ChangeSet(added=..., branch=..., commit_id=...), source=blob_source)`（R36）。
- `skipped` = 本次 core 报告的 `skipped_files`（二进制/不可解码，如实上报，D-30 诚实性）；
  注意语义：**`accepted` 表示"服务端已持久化 blob"，不等于"已索引成功"**——索引失败明细在 `report.errors`，
  客户端不得据此判定检索可用（Module/05 §3.6）。
- 空 project（第一次上传）也要正常工作（账本从空开始）。

### `POST /api/sync/checkpoint`

- 入参：`{projectId?, blobHashes: [str]}` → `{checkpointId}`（CF-05）。
- `checkpointId = "cp_" + sha256("\n".join(sorted(set(blobHashes))))[:16]` → **内容寻址，天然幂等**（同集合必同 id）。
- 账本里保留最近 3 个 checkpoint（LRU 淘汰），淘汰不影响已有查询。
- 本卡**不做** checkpoint 与检索请求的强校验（那是 client 侧优化：checkpoint 只用于减少重复上传）；
  若后续要校验，`search` 只读取不强制。

### `POST /api/sync/deletions`

- 入参：`{projectId?, paths: [str]}` → 200 `{deleted: [path], unknown: [path]}`（CF-05 只说 200，本结构是扩展）。
- 幂等：重复删除 → `unknown` 里返回，不报错（Module/05 §9-3 的口径）。
- 动作（顺序固定）：账本移除 path → blob 镜像删除（若该 hash 不再被任何 path 引用）→ `engine.ingest(ChangeSet(deleted=paths), source=blob_source)`。
- 删除后 `search` 不得再返回该文件的证据（DoD 里有端到端断言）。

### `GET /api/sync/status/{projectId}`

- 返回 `core.sync_status()` 的全字段 + 本卡追加 `{branch, commit, blobs: {count, bytes}, checkpoints: int}`。
- `indexingFiles` / `pendingJobs` 在 M2a 恒为空/0 是**正确的**（同步索引：每个上传请求内完成）；不要伪造。

## §D 允许对 TASK-031 文件的追加

- `blobstore.py`：如需按 hash 引用计数或 `iter_hashes()`，可**追加**方法；
- `sync_state.py`：如需 `checkpoints_lru()` / `remove_paths()`，可**追加**方法；
- 若发现既有语义必须修改（不是追加），**停下来**写进"未决问题"，不要改。

## 验收标准（DoD）

- [ ] 上传幂等：同一批上传两次 → 两次 `accepted` 相同、`store.counts()["chunks"]` 不翻倍。
- [ ] hash 校验：篡改 `blobHash` → 400 `blob_hash_mismatch`，且**账本与索引未被修改**（断言 counts 不变）。
- [ ] 批大小与路径：>1MiB → 413；`../evil.py`、`/etc/passwd`、`a\\b.py` → 400 `invalid_path`。
- [ ] 删除端到端：上传 A（含独有符号 `alpha_only_symbol`）与 B → `search` 命中 A → 删 A → `search` 不再返回 A 的证据，且 `status.blobs.count` 下降、`unknown` 幂等（第二次删除返回 unknown）。
- [ ] checkpoint：同 hash 集合两次 → 同 `checkpointId`；不同集合 → 不同；第 4 个 checkpoint 后最早的被淘汰（断言账本里 ≤3）。
- [ ] status：`filesIndexed/chunks/symbols/edges` 与 `Store.counts()` 一致；`blobs.bytes` 与实际文件大小之和一致。
- [ ] 空批 / 非法 base64 / 未知 project（404）三类错误形态正确。
- [ ] 与 TASK-032 的联动：上传后立即 `POST /api/query/search` 能检索到新上传的文件（一条端到端断言，证明"上传→索引→检索"闭环）。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] 任务卡"执行记录"已回填（**必须贴一条真实的上传→检索闭环输出**）；任务板对应行状态改 `review`。

## 性能参考（不设硬门禁）

单批 1MiB 的索引耗时 ≈ 该批文件的解析 + 嵌入（aibox 规模全量约 17 分钟，分批后每批秒级）。
**不要**在本卡引入后台线程/队列（那是 TASK-062）；但要在执行记录里给出**实测单批耗时**，作为 TASK-062 的输入。

## 明确不做

- 不做 gzip 上传（Module/05 §8/§9-2：先验证裸传输）。
- 不做异步 job / 进度上报 / 首同步 120s 转后台（TASK-062 与 TASK-042）。
- 不做差分协议（只传 hash 差集）（Module/05 §8）。
- 不做 `.gitignore` 解析（客户端职责，TASK-041）。
- 不做鉴权与租户（M2c）。
- 不改 `blob_hash` 语义、不改账本 JSON 结构与既有字段语义。

## 参考源码锚点（只读）

- `docs/design/Module/05-MCP与同步.md` §3.3 的时序图（①-⑥ 六步，本卡实现服务端侧）
- `core/zace_core/engine.py::Engine.ingest`（本卡唯一的 core 写入口）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写。）
