# TASK-033：同步 API（batch-upload / checkpoint / deletions / sync status）

> 状态：review ｜ 阶段：Phase 2（M2a-1）｜ 硬依赖：TASK-031 ｜ soft 依赖：无
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

- **日期 / 分支**：2026-09-10 ｜ `feature/task-033_xwz0910`（从 `feature/task-032_xwz0910` 串联）
- **关键产物**：`service/zace_service/routers/sync.py`（替换占位）、`service/tests/test_sync_api.py`。
  `blobstore.py` / `sync_state.py` **未改动**（§D 是“允许追加”；TASK-031 已建的
  `remove_paths` / `blob_hashes` / `record_checkpoint` 已足够，无需新方法）。

### 验收命令与结果

```text
$ uv run ruff check .
All checks passed!
$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
$ uv run pytest
594 passed, 2 skipped, 2 warnings        # 032 后为 575+2 → 本卡新增 19 条
$ uv run pytest service/tests
90 passed
```

### 真实的“上传 → 索引 → 检索”闭环输出

```text
① POST /api/sync/batch-upload  (2 文件：1 py + 1 markdown, branch=main, commit=abc123)
HTTP 200 {"accepted": ["ebe1e3b3...2725", "50d48d8e...e5c3"], "skipped": [],
 "report": {"added": 2, "modified": 0, "deleted": 0, "chunksNew": 5, "chunksReused": 0,
            "chunksRemoved": 0, "filesParsed": 2, "errors": [], "skippedFiles": []}}

② GET /api/sync/status/{pid}
{"projectId": "dd8dc3d4356a3483", "filesIndexed": 2, "chunks": 5, "symbols": 2, "edges": 0,
 "pendingJobs": 0, "indexingFiles": [], "lastIndexedAt": 1789045661, "branch": "main",
 "commit": "abc123", "blobs": {"count": 2, "bytes": 414}, "checkpoints": 0}

③ POST /api/query/search {"query": "TokenService.refresh_token"}
meta: answerable=true confidence=high channelsUsed=[exact,bm25,vector] candidateCount=5
evidenceCount=1 docsCount=1 budget={576/10000, truncated=false}
## Relevant Context
### Code
[E1] TokenService.refresh_token — src/token_service.py:1-9
     1 | """令牌服务模块。"""
     ... （省略 1 行）
     4 | class TokenService:
     6 |     def refresh_token(self) -> str:
```

### checkpoint / deletions 实测

```text
checkpoint 幂等: {'checkpointId': 'cp_9839a2f17d7c9b41'} {'checkpointId': 'cp_9839a2f17d7c9b41'}
deletions: {'deleted': ['src/token_service.py'], 'unknown': []}
再删:        {'deleted': [], 'unknown': ['src/token_service.py']}
blobs after delete: {'count': 1, 'bytes': 175} | 检索仍返回该文件? False
```

### 实测单批耗时（TASK-062 的输入）

```text
单批 332 文件 / 1045606 字节（顶到 1MiB 上限）→ 6.56s
  report: added=332 chunksNew=13612 filesParsed=332 errors=[]
单测内的 20 小文件批（870 字节）→ 0.077s
```

**诚实的限定**：上述数字用的是 service 测试的**确定性假 provider**（哈希桶伪向量，无模型推理），
真机 ONNX 嵌入会明显更慢；卡内参考值（aibox 全量 ~17 min）才是真实量级。本数据只用作
TASK-062（后台 job/进度上报）的**相对**输入（单批秒级 → 保留同步上传可接受）。

### 契约影响

无契约文件改动。消费 CF-05（四条路径与幂等语义）、CF-02（``blob_hash`` 含 path）、
CF-07（``ingest(..., source=)``）。**新增产出面**：``batch-upload`` 的响应扩展字段
（``skipped`` + ``report``，形态见卡内冻结段），client（TASK-040）依赖。

### 与设计偏差

1. **`blobstore.py` / `sync_state.py` 零改动**：§D 是“允许追加”而非“必须追加”，
   TASK-031 建立的 ``remove_paths`` / ``blob_hashes`` / ``record_checkpoint`` 已经够用。
2. **“同一 hash 被多 path 引用”在真实上传中不会发生**：CF-02 的 ``blob_hash`` **含 path** →
   同内容不同 path = 两个 blob。引用计数分支（删镜像前查是否仍被引用）实际服务于
   将来差分协议/历史账本；单测用直接写账本的方式确定性覆盖该分支，另有一条测试记录真实
   语义（同内容两 path → 2 blob，删一个少一个），不把假设当事实。
3. **校验顺序固定为：空批 → 解码（累计超限立即 413）→ 路径安全 → hash 一致**：
   只有一个错误的请求各得对应机器码；混合错误时以靠前者为准（已在模块 docstring 写明）。
   实测：脚本生成 “~1MiB + 一个文件越界” 的批确实得到 413，上限真的生效。
4. **``deletions`` 对非法路径不做 400**（与 ``batch-upload`` 的 ``invalid_path`` 不同）：
   删除通知的语义是“告知哪些 path 不在了”，不在账本里的一律走 ``unknown`` 幂等口径
   （Module/05 §9-3）；对此报 400 会把幂等客户端逼进错误分支。
5. **``checkpoint`` 不校验 blob 是否存在**：卡内明确“checkpoint 只用于减少重复上传”，
   校验属 client 侧优化。

### 未决问题

1. **单批耗时的绝对量级尚未用真 provider 测**（本卡只给了假 provider 的相对值）：真实数据下
   建议在 TASK-062 用 aibox 仓库实测；若单批 >30s（client 侧 batch-upload 超时 D-32），
   需调整批次大小或转后台。
2. **checkpoint 存的是完整 hash 列表**（3 个 × 全量 scope）：大仓库（38k blobs）下账本可能
   到 MB 级。若成为瓶颈，可改存 ``sha256(名单)`` 的摘要而非名单本身（需改账本 schema，
   属 L2 范围，需编排者拍）。
3. **``skipped`` 完全等同 core 的 ``report.skippedFiles``**（服务端裁决，客户端尊重执行 S4）；
   尚未出现需要服务端额外裁决的跳过类别（如 .gitignore 命中——那是 client 职责）。
4. 删除后残留的“跨进程孤儿向量”仍按 core 的既有口径处理（TASK-007 已登记，检索侧会跳过，
   下次全量重建清理）；本卡不越界修 core。

### 建议复核点

① 校验顺序与各错误机器码是否与 CF-05/卡内一致；② ``accepted ≠ 已索引`` 的语义是否
在响应与文档里都说清了；③ 删除链路的固定顺序（账本 → 镜像引用计数 → ingest）与幂等断言；
④ checkpoint 的内容寻址与 LRU 上限；⑤ status 与 ``Store.counts()``/实际字节数的一致性断言。
