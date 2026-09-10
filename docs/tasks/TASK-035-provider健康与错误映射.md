# TASK-035：provider 健康与错误映射（TASK-033 收尾观察立卡）

> 状态：review ｜ 阶段：Phase 2（M2a-1b）｜ 硬依赖：TASK-033 ｜ soft 依赖：无
> 建议分支：`feature/task-035_<你的缩写><MMDD>`
> 交付物所有权：
> - `service/zace_service/errors.py`（追加 provider/引擎错误到状态码的映射）
> - `service/zace_service/routers/{sync,query,ops}.py`（错误分支）
> - `service/zace_service/runtime.py`（`EngineManager` 的 provider 健康探测 + **§C** 公开面收敛）
> - `core/zace_core/engine.py`（**仅** §C 一处：新增公开方法或重命名内部调用）
> - `service/tests/test_error_mapping.py`（新建）、`core/tests/integration/test_engine_apply_changes.py`（新建）
>
> 清单外文件不得改。

## 背景（编排者实测复现，2026-09-10）

TASK-033 的报告里提了一条"未擅自改"的观察。编排者独立复现后确认**它比报告描述的更严重**，
因为它会掩盖真实故障并让客户端进入**无限重试循环**：

```text
# 复现（provider 指向不可达地址）
EMBED_MODE=api EMBED_BASE_URL=http://127.0.0.1:9
  POST /api/sync/batch-upload  → 500 internal_error["服务内部错误，请稍后重试"]
  POST /api/query/search       → 409 index_in_progress["该项目尚未索引，请先同步"]
```

第二个响应的建议是**错的**：索引为空不是因为"还没同步"，而是因为嵌入服务不可用导致上传失败。
客户端（TASK-042 的懒同步）会照 409 的指引反复"同步→重试检索"，**永远好不了**，且真正的错误
（provider 不可达）只留在服务端日志里。

更关键的是**首次体验**：TASK-033 实测 aibox 规模全量索引 ~17 分钟、首次 `batch-upload` 可能触发
ONNX 模型下载（编排者实测：新 data_root 下首次上传会去 HuggingFace 取模型）。
若那条路失败，用户看到的是"服务内部错误"和"请先同步"，无从判断该做什么。

## §A 错误映射（`errors.py` + 路由）

在 `errors.py` 增加一个映射：引擎/依赖类异常 → `ApiError(code, message, status)`。至少覆盖：

| 触发 | 现状 | 目标 |
|---|---|---|
| embedding provider 构造失败 / 不可用（`zace_core.engine.EngineError`、`EmbeddingConfigError`） | 500 | **503 `embedding_unavailable`**，message 含**可操作指引**（检查 `EMBED_*` 配置、模型缓存目录、是否需要联网首次下载） |
| embedding 调用超时 / 连接失败（httpx 异常） | 500 | **503 `embedding_unreachable`**（保留 provider 侧 error 摘要，**不泄露 API key**） |
| 磁盘/权限类 `OSError` | 500 | 507 `storage_error`（或 500，但 code 要具体） |
| 其它未预期异常 | 500 `internal_error` | 保持不变（兜底不得吞掉） |

**纪律**：映射必须**基于异常类型**，不要用字符串匹配 message。`ApiError` 之外不得新增响应形态。

## §B 修掉 409 的误导（`routers/query.py`）

空索引（`chunks == 0`）目前一律 409 `index_in_progress`。必须区分三种情况：

1. **从未同步过**（账本 `files` 为空，且 chunks=0）→ 409 `index_in_progress`，指引"先同步"（现状正确）。
2. **有账本但索引为空**（`sync-state.files` 非空、chunks=0）→ 说明上次索引失败了 →
   **500 `index_failed`**（或 503），message 指向"上次上传/索引未成功，请检查服务端日志或重新同步"
   ——**不得**再说"请先同步"（用户会以为没上传过）。
3. **provider 不可用**（§A 探测发现）→ **503 `embedding_unavailable`**，优先于前两者（根因优先）。

实现要求：`EngineManager` 暴露一个轻量 `provider_health() -> (ok: bool, reason: str | None)`
（**不得**加载模型做真实推理——用配置合法性 + 已加载状态判断；已加载过则直接 ok），
在 sync/query 的错误分支里使用。

## §C 收敛跨包私有调用（TASK-031 的未决问题 1）

TASK-031 的 `EngineManager.ingest` 目前直接调 `Engine._ingest`（**跨包调私有方法**）。
二选一，在卡内说明理由：

- 方案 1（推荐）：在 `core/zace_core/engine.py` 增加**公开方法**
  `apply_changes(project_id, changes, *, source=None, full=False) -> IngestReport`
  （即 `_ingest` 的公开包装），`_ingest` 保留为内部实现；service 改调它。
- 方案 2：把 `ingest` 的返回类型从 `job_id: str` 改为 `IngestReport`——**不改**：CF-07 已冻结
  `-> str`（异步 job 语义留给 TASK-062），改它要动契约。

选方案 1 时：新方法属 core 的**公开 API 但不在 CF-07 面内**（R33 允许），
在 docstring 里注明"服务端同步语义入口；CF-07 的 `ingest` 是异步 job 版"。
**不要**顺手把 `_ingest` 删掉或改签名（`ingest` 仍在用）。

## 验收标准（DoD）

- [ ] `EMBED_MODE=api EMBED_BASE_URL=http://127.0.0.1:9`（不可达）下：
      `batch-upload` → **503 `embedding_unavailable`**（不是 500）；`search` → **503**（不是 409）；
      message 里**不出现** API key；断言在 `service/tests/test_error_mapping.py` 里用 monkeypatch
      构造 provider 异常（**不要真的联网**，CI 必须离线可跑）。
- [ ] 三种空索引情况各一条断言（从未同步→409 / 有账本但空→500 `index_failed` / provider 坏→503）。
- [ ] 未预期异常仍是 500 `internal_error`（回归：不要因为加了映射把兜底吞掉）。
- [ ] §C：service 里不再出现 `engine._ingest`（grep 断言或直接删除该调用点）；`apply_changes` 有 core 侧测试。
- [ ] 行为验收（贴执行记录）：用 `EMBED_MODE=api` + 不可达地址起服务，`curl` 两个端点，贴出 503 响应与首行日志（证明根因进了日志、指引进了响应）。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- 不做重试/熔断/退避（V1 明确不做速率限制与重试策略，Module/06 §8）。
- 不做 provider 预热（`EmbeddingConfig.preload` 已有开关，何时预热归 TASK-042/062 决定）。
- 不改 `EmbeddingConfig` 或 provider 实现（那是 core 的 TASK-008 范围）。
- 不改 `/healthz` 的既有字段语义（`?deep=1` 已有探测；本卡只加 sync/query 的错误映射）。
- 不动 CF-05 的状态码集合以外的东西（新增 503 属**扩展**，在卡内登记并同步 `docs/plan/contracts.md`；
  **不要**自己改 `docs/contracts/openapi.yaml`——那是编排者的事）。

## 参考源码锚点（只读）

- `service/zace_service/errors.py`（现有 `ApiError` 与异常处理器）
- `core/zace_core/embedding/factory.py`（`EmbeddingConfigError` 的抛出点）
- `core/zace_core/engine.py::Engine.provider`（provider 懒构造与 `EngineError` 包装点）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；**必须包含 §B 三种空索引的响应对照**。

## 执行记录

### 2026-09-10 ｜ 分支 `feature/task-035_xwz0910` ｜ 状态：review

**改动范围（全部在卡内所有权清单内）**：
`service/zace_service/errors.py`（§A）、`routers/query.py`（§B）、`runtime.py`（§A 探测 + §C 收敛点）、
`core/zace_core/engine.py`（**仅** §C 一处：新增公开 `Engine.apply_changes`）、
`service/tests/test_error_mapping.py`（新建，15 条）、
`core/tests/integration/test_engine_apply_changes.py`（新建，3 条）。
`routers/sync.py` / `routers/ops.py` **未改**：§A 的映射用 `app.add_exception_handler` 在 `errors.py`
统一挂载（覆盖 sync/query 所有路由，比逐条路由 try/except 更难漏），两文件无需错误分支改动。

#### ① 验收命令与结果

```text
uv run ruff check .                                    → All checks passed!
uv run python scripts/check_dependency_direction.py    → 依赖方向检查通过（core 纯库 / service 不上探）。
uv run pytest                                          → 612 passed, 2 skipped, 2 warnings in 16.67s
uv run pytest service/tests/test_error_mapping.py       → 15 passed
uv run pytest core/tests/integration/test_engine_apply_changes.py → 3 passed
```

#### ② 行为验收（卡内复现命令，真实进程 + curl）

```bash
EMBED_MODE=api EMBED_BASE_URL=http://127.0.0.1:9 uv run zace-service --port 8798 --data-root /tmp/zace-035-live2
```

`POST /api/sync/batch-upload`（**改前 500 internal_error**）→ **503**：

```json
{"error":{"code":"embedding_unavailable","message":"embedding provider 不可用：EmbeddingConfigError: api 模式必须指定 model（EMBED_MODEL，例如 bge-m3）。请检查 embedding 配置（EMBED_MODE / EMBED_MODEL / EMBED_BASE_URL / EMBED_API_KEY）与模型缓存目录（EMBED_CACHE_DIR / EMBED_MODEL_DIR）：本地模式下首次使用可能需要联网下载模型，离线环境请预先放置模型文件或显式设置 EMBED_OFFLINE=1 与 EMBED_MODEL_DIR。"}}
HTTP=503
```

`POST /api/query/search`（**改前 409 index_in_progress「请先同步」**）→ **503**：

```json
{"error":{"code":"embedding_unavailable","message":"embedding provider 当前不可用（EmbeddingConfigError: api 模式必须指定 model（EMBED_MODEL，例如 bge-m3）），索引无法建立：这不是「尚未同步」，请先修复依赖。…"}}
HTTP=503
```

`GET /api/sync/status/<id>` → `filesIndexed:0, chunks:0`（证实改前必然走 409 分支）。

服务端日志首行（根因进日志，指引进响应）：

```json
{"ts": "2026-09-10T13:33:48.682+00:00", "level": "error", "logger": "zace_service.errors", "msg": "mapped engine error", "code": "embedding_unavailable", "excType": "EngineError", "method": "POST", "path": "/api/sync/batch-upload", "exc": "Traceback (most recent call last):\n  File \"core/zace_core/engine.py\", line 319, in provider\n    self._provider = create_provider(self._embedding_config)\n … zace_core.embedding.base.EmbeddingConfigError: api 模式必须指定 model（EMBED_MODEL，例如 bge-m3）"}
```

#### ③ §B 三种空索引的响应对照（实测）

| 情况 | 构造方式 | 改前 | 改后 | 测试 |
|---|---|---|---|---|
| ① 从未同步（账本空 + chunks=0） | `POST /api/projects/resolve` 后直接 search | 409 `index_in_progress` | **409 不变**（指引"先同步"正确） | `test_empty_index_never_synced_is_409` |
| ② 有账本但索引为空 | 只落账本/blob、不索引 | 409（**错误指引**） | **500 `index_failed`**（不说"请先同步"） | `test_empty_index_with_ledger_is_500_index_failed` |
| ③ provider 不可用 | provider 构造失败 / 已被故障记忆 | 409（**错误指引**） | **503 `embedding_unavailable`**，优先于①② | `test_empty_index_with_broken_provider_is_503`、`test_empty_index_provider_bad_beats_index_failed`、`test_provider_config_error_maps_to_unavailable` |

#### ④ 实测发现（两处，均已处理）

**发现 1（影响 §B 的边界，须编排者确认）**：`chunks == 0` 并不总是"上传失败"的结果。
把 `EMBED_MODEL` 补上（provider 构造成功、调用时才失败）后实测：分块先落库再嵌入，
失败后状态是 `filesIndexed:1, chunks:2`，此时检索**照常能跑**（BM25/exact 命中，
`degraded=true`、`channelsUsed=["exact","bm25"]`、`degradedReason` 写明向量通道根因）——
实测输出：

```json
{"markdown":"## Relevant Context\n### Code\n[E1] TokenService.refresh_token — src/token_service.py:4-9 …",
 "meta":{"degraded":true,"channelsUsed":["exact","bm25"],
         "degradedReason":"vector 通道降级：VectorChannelError: query embedding 失败：ApiResponseError: …",
         "answerable":true,"confidence":"low"}}
HTTP=200
```

因此本卡把 provider 探测**限定在 `chunks == 0` 分支**（即 §B 字面范围）：索引非空时不拦检索，
让 core 的通道降级如实上报（D-30）。理由：拿 503 把一份可用的 BM25/精确结果拦下来比"带降级原因
返回 200"更不诚实，且"故障记忆"可能陈旧（provider 恢复后仍拒绝，客户端会永远好不了）。
卡内复现命令（未给 `EMBED_MODEL`）下 `search` 仍是 **503**（上表③），DoD 字面满足；
补 `EMBED_MODEL` 的场景是**更进一步的诚实降级**，请编排者确认是否接受（TASK-042 懒同步的预期）。

**发现 2（secret 纪律，已修）**：core 的 `trace.degraded_reason` 会把 provider 原始报错
（含 `api_key=…` 形态文本）透传进 `meta.degradedReason`，而 **`meta` 是返回给编辑器的响应体**。
在 `routers/query.py` 传 `reason=` 时加了 `redact_text(...)`（同一文件、不新增字段），
断言见 `test_failed_upload_then_search_is_degraded_not_409`（`FAKE_API_KEY not in response.text` + `"***" in degradedReason`）。
真实 API provider 的 `_redact` 已自保，但"服务端不得依赖上游自保"——本卡顺手堵住。

#### ⑤ §C 收敛

选**方案 1**（卡内推荐）：core 加公开 `Engine.apply_changes(project_id, changes, *, source=None, full=False) -> IngestReport`，
`_ingest` 保留为内部实现、`ingest` 仍返回 `str`（CF-07 未动）。
`service/zace_service/runtime.py` 改调公开方法；回归断言 `test_service_does_not_call_private_engine_ingest`
用源码扫描锁定 `._ingest(` 不再出现（`_ingest` 只出现在 core 内）。

#### ⑥ provider 探测实现（`provider_health`）

两个信号，**不加载模型、不做推理**：①``Engine.provider`` 的构造（`EMBED_*` 合法性 + 本地模型文件
可定位；已构造过直接 ok）；②故障记忆（最近一次 ingest/search 是否因 provider 挂掉失败，
**成功的非降级检索**或**成功的 ingest** 才清除）。映射全部**按异常类型**（含 `__cause__` 故障链），
不做 message 字符串匹配：

| 异常 | 响应 |
|---|---|
| `EmbeddingConfigError` / `LocalModelUnavailableError` / `EmbeddingDimMismatchError` | 503 `embedding_unavailable` |
| `ApiAuthError` / `ApiNetworkError` / `ApiRateLimitError` / `ApiResponseError` / 裸 `httpx.HTTPError` | 503 `embedding_unreachable` |
| `EngineError` **故障链里含** embedding 异常 | 503 `embedding_unavailable` |
| `EngineError`（参数类，如"非法 project_id"） | 不映射 → 仍是 500 `internal_error` |
| `OSError`（含故障链） | 507 `storage_error` |
| 其它 | 不映射 → 500 `internal_error`（兜底未被吞，有回归断言） |

#### 契约影响（扩展，已在卡内登记；**未**改 `docs/plan/contracts.md`）

新增两个状态码属 CF-05 的**扩展**（状态码集合扩充，信封形态与路径不变）：
`503 embedding_unavailable` / `503 embedding_unreachable` / `507 storage_error`。
`docs/plan/contracts.md` **不在本卡文件所有权清单内**（清单写"清单外文件不得改"），
按仓库 `AGENTS.md` §2 的"公共文件先在执行记录里提出"办理，建议编排者在 §3.8 追加：

```text
| R39 | **CF-05 扩展：引擎/依赖错误的状态码**（TASK-035 §A） | 新增 503 `embedding_unavailable` /
503 `embedding_unreachable` / 507 `storage_error`（信封与路径不变）。理由：provider 不可用必须与
"服务内部错误"区分开，否则客户端把依赖故障当自身重试；507 用于区分磁盘/权限故障。
新增 503/507 属**扩展而非破坏**：显式语义，既有 4xx/500 行为不变；`docs/contracts/openapi.yaml`
由编排者同步 |
```

#### 未决问题

1. **`docs/plan/contracts.md` 未改（见上）**：所有权清单未列该文件，故只在卡内登记 + 给出可粘贴的 R39 行；
   若编排者认为该文件属"流程回填"而非"清单外文件"，可在评审时直接采纳上面那段。
2. **发现的 1 请裁定**：非空索引 + provider 故障 → 200（`degraded=true`）而不是 503。TASK-042 的懒同步
   若按"收到 503 才重试同步"实现，行为会与卡内 DoD 的直觉不一致；建议 TASK-042 改为"看 `meta.degraded`
   + `degradedReason` 提示依赖故障"。
3. **`EngineError` 是通用错误类**：本卡用"故障链里是否含 embedding 异常"来做精确区分，属权宜；
   若 core 将来加一个专门的 provider 不可用异常（`Engine.provider` 抛出），映射可以变简单
   （不在本卡范围：卡内只允许 §C 一处 core 改动）。
4. **故障记忆的边界**：它只在 `chunks == 0` 分支参与判断；非空索引检索成功后（`degraded=false`）
   会清除。陈旧的"坏记忆"可能在 provider 已恢复时把空索引检索报成 503（指引是"修依赖或重新同步"），
   不会阻断非空索引的检索。
5. **真实进程未验证 507**：`storage_error`（507）由单测（monkeypatch `OSError`）覆盖，
   未在真实进程制造磁盘故障（改权限会污染环境）；DoD 只要求 503 的真实进程验收。
6. **`/healthz?deep=1` 未改**（卡内明确不做）：它仍走 `create_provider + ensure_loaded` 的真实探测，
   与 `/api/sync|query` 的轻量探测是两套语义，未合并（合并会改 `/healthz` 的既有字段语义）。

