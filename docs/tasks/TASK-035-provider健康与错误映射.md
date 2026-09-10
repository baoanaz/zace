# TASK-035：provider 健康与错误映射（TASK-033 收尾观察立卡）

> 状态：pending ｜ 阶段：Phase 2（M2a-1b）｜ 硬依赖：TASK-033 ｜ soft 依赖：无
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

（实施 AI 在此填写。）
