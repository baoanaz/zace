"""``/healthz``、账户概览、索引历史与查询用量端点。

分工：

| 端点 | 卡 | 语义 |
|---|---|---|
| ``GET /healthz`` | TASK-030/034 | 存活 + 依赖检查 + 项目进度（**免鉴权**） |
| ``GET /api/account/overview`` | TASK-062/064 | 首页仪表盘：账户资料 + 索引成功/失败/平均耗时 |
| ``GET /api/projects/{id}/index-runs`` | TASK-062 | 单项目索引历史 |
| ``GET /api/projects/{id}/index-stats`` | TASK-062 | 单项目索引统计（当前进度 + 落库聚合） |
| ``GET /api/usage/projects/{id}`` | TASK-064 | 单项目查询用量（**替换 501 占位**） |
| ``GET /api/usage/summary`` | TASK-064 | 跨项目用量汇总 |
| ``GET /api/request-log/{requestId}`` | TASK-090 | 按 trace id 查请求日志（**只读**） |

口径见 ``docs/design/Module/04-AI总结.md`` §8（审计存档）与 ``docs/tasks/TASK-062`` §C/§D。
**诚实性**：无数据时一律 ``null``/``0``；``citationCoverageAvg`` 在 LLM 接入前恒为 ``null``
（"尚未测量"不是 0）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from zace_service.deps import get_engine_manager, get_settings, require_project_id
from zace_service.errors import ApiError
from zace_service.logging import get_logger, redact_text
from zace_service.metadb import MetaDB
from zace_service.requestlog import MAX_RELATED_LOGS, lookup_all
from zace_service.stats import account_overview

router = APIRouter(tags=["ops"])

logger = get_logger("zace_service.routers.ops")

#: 历史/用量端点的默认与上限查询条数。
DEFAULT_LIMIT = 20
MAX_LIMIT = 200
#: 用量窗口默认与上限（天）。
DEFAULT_DAYS = 30
MAX_DAYS = 365


@router.get("/healthz")
def healthz(request: Request, deep: int = 0) -> dict[str, Any]:
    """存活 + 依赖检查（``security: []``；``deep=1`` 追加 provider 探测）。"""
    settings = get_settings(request)
    core: dict[str, Any] = {"importable": _core_importable()}
    if deep:
        core.update(_probe_embedding_provider())
    return {
        "status": "ok",
        "version": settings.version,
        "dataRoot": str(settings.data_root),
        "localMode": settings.local_mode,
        # TASK-060：按**真实**鉴权状态报告（此前按 local_mode 硬编码，TASK-051 A1 记为诚实性缺陷）。
        "auth": "disabled(local)" if settings.local_mode else "required",
        "core": core,
        "projects": _project_progress(request),
    }


def _project_progress(request: Request) -> list[dict[str, Any]]:
    """本地模式的项目进度（TASK-034 §D）：**纯内存**，不触碰 core，不加载模型。

    索引进行中仍返回本字段（值就是当前 ``indexProgress``），``/healthz`` 仍 200——
    "服务是活的"与"索引没跑完"是两件事，不能混为一谈（卡内 §D）。
    """
    manager = getattr(request.app.state, "engine_manager", None)
    if manager is None:  # 尚未有请求碰过 core：不为了探活去构造 EngineManager
        return []
    projects: list[dict[str, Any]] = []
    try:
        listed = manager.list_projects()
    except Exception as exc:  # 探活端点自身不因 core 异常而 500（同上口径）
        return [{"error": redact_text(f"{type(exc).__name__}: {exc}")}]
    for item in listed:
        projects.append(
            {
                "projectId": item["projectId"],
                "attachedRoot": item.get("attachedRoot"),
                "indexProgress": item.get("indexProgress"),
            }
        )
    return projects


# --------------------------------------------------------------------------- 账户概览


@router.get("/api/account/overview")
def overview(request: Request, days: int = DEFAULT_DAYS) -> dict[str, Any]:
    """首页仪表盘（账户资料 + 索引成功/失败/平均耗时 + 查询用量）。

    身份与项目范围由 ``app.py`` 的鉴权依赖保证：这里只聚合**当前用户**的项目
    （未鉴权时按本地模式的全量项目）。
    """
    manager = get_engine_manager(request)
    db = _meta_db(request)
    user = getattr(request.state, "zace_user", None)
    window = max(1, min(int(days), MAX_DAYS))

    listed = manager.list_projects()
    user_id = getattr(user, "id", None)
    if user_id is not None and db is not None:
        owned = set(db.list_projects(user_id))
        # 未登记归属的项目（本地 attach 后尚未 claim）不计入概览，避免"看到不属于自己的项目"。
        listed = [item for item in listed if str(item["projectId"]) in owned]
    return account_overview(
        user_name=getattr(user, "name", "local"),
        user_created_at=getattr(user, "created_at", 0),
        is_local=bool(getattr(user, "is_local", True)),
        project_ids=[str(item["projectId"]) for item in listed],
        projects=listed,
        db=db,
        days=window,
    )


# --------------------------------------------------------------------------- 索引历史


@router.get("/api/projects/{id}/index-runs")
def project_index_runs(
    id: str, request: Request, limit: int = DEFAULT_LIMIT
) -> list[dict[str, Any]]:
    """单项目索引历史（最近 ``limit`` 条，按结束时间倒序）。"""
    db = _require_meta_db(request)
    # TASK-061 §C：消费 projectId 的端点经 require_project_id（存在 + 归属）。
    project_id = require_project_id(request, id)
    return [run.to_json() for run in db.index_runs(project_id, limit=_limit(limit))]


@router.get("/api/projects/{id}/index-stats")
def project_index_stats(id: str, request: Request, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """单项目索引统计：内存态当前进度 + 落库历史聚合 + 磁盘占用。"""
    manager = get_engine_manager(request)
    project_id = require_project_id(request, id)  # TASK-061 §C
    return manager.index_stats(project_id, limit=_limit(limit))


@router.get("/api/index-stats")
def all_index_stats(request: Request, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """跨项目索引汇总（当前用户的项目）。"""
    manager = get_engine_manager(request)
    db = _require_meta_db(request)
    ids = _visible_project_ids(request, manager)
    stats = db.all_index_stats(ids, limit=_limit(limit)).to_json()
    stats["diskBytes"] = sum(
        manager.index_stats(pid, limit=0)["diskBytes"] for pid in ids
    )
    return stats


# --------------------------------------------------------------------------- 查询用量


@router.get("/api/usage/projects/{id}")
def project_usage(id: str, request: Request, days: int = DEFAULT_DAYS) -> dict[str, Any]:
    """单项目查询用量（04 §8 审计存档的读取口；**替换 501 占位**）。"""
    db = _require_meta_db(request)
    project_id = require_project_id(request, id)  # TASK-061 §C：存在 + 归属
    summary = db.usage_summary([project_id], days=_days(days)).to_json()
    summary["projectId"] = project_id
    summary["days"] = _days(days)
    return summary


@router.get("/api/usage/summary")
def usage_summary(request: Request, days: int = DEFAULT_DAYS) -> dict[str, Any]:
    """跨项目用量汇总（当前用户的项目）。"""
    manager = get_engine_manager(request)
    db = _require_meta_db(request)
    ids = _visible_project_ids(request, manager)
    summary = db.usage_summary(ids, days=_days(days)).to_json()
    summary["days"] = _days(days)
    return summary


# --------------------------------------------------------------------------- 请求日志（trace 查询）


@router.get("/api/request-log/{requestId}")
def request_log(requestId: str, request: Request) -> dict[str, Any]:
    """按 ``requestId`` 查这次请求的结构化日志（TASK-090 §C；**只读**）。

    鉴权与归属（§C，本卡裁定）：

    - 路径**不在** ``app.PUBLIC_PATHS`` 内 → 云瑞形态必须带凭据（否则 401）：日志是信息泄露面，
      不能公开；
    - **只查自己的**：只有条目里的 ``userId`` 与调用者一致才返回；
    - 查别人的 / 不存在的 / 没有 owner 的（如未认证的 401 请求、路径未匹配到路由）
      一律 **404 ``request_log_not_found`` + 同一条文案**——与 Module/06 §2.2 的"不给探测面"一致
      （403 会泄露"这个 id 存在"）。本地模式（无账户）按 R34 放行。

    返回形状：主条目（``message == "request"`` 那一行，即 :func:`capture_request` 落的）+ 可选
    ``relatedLogs``（同一 requestId 下的其余日志行，新的在前）——**已处理**的 5xx 堆栈在后者里
    （见 :func:`zace_service.requestlog.lookup_all`），不带上它则"503 报错查日志"会看到空堆栈。

    路径参数用 ``{requestId}`` 而非 ``{id}``：本路由**不**消费 projectId，走的是日志归属判定，
    与 ``/api/projects/{id}`` 的 ``require_project_id`` 无关。
    """
    settings = get_settings(request)
    user = getattr(request.state, "zace_user", None)
    user_id = getattr(user, "id", None)
    entries = lookup_all(settings.request_log_path, requestId, user_id=user_id)
    primary = next((entry for entry in entries if entry.message == "request"), None)
    if primary is None:
        raise _request_log_not_found(requestId)
    payload = primary.to_json()
    payload["requestId"] = requestId
    related = [entry.to_json() for entry in entries if entry is not primary]
    payload["relatedLogs"] = related[:MAX_RELATED_LOGS]
    payload["relatedLogCount"] = len(related)
    return payload


def _request_log_not_found(request_id: str) -> ApiError:
    """统一的"查不到"错误（越权 / 不存在 / 无 owner 共用）。

    文案里**不回显** ``request_id``（也不含任何随入参变化的部分）：越权与真不存在的响应因此
    **逐字节一致**，调用方无法据此建立"这个 id 存在"的预言机（Module/06 §2.2）。
    传参只为类型自洽（也确实需要这个入参来构造语义），保留它以便将来需要时不必改签名。
    """
    _ = request_id
    return ApiError(
        code="request_log_not_found",
        message=(
            "请求日志不存在，或不属于当前账户，或已被窗口清理（可用 X-Request-Id 重新请求复现）"
        ),
        status=404,
    )


# --------------------------------------------------------------------------- 辅助


def _meta_db(request: Request) -> MetaDB | None:
    db = getattr(request.app.state, "meta_db", None)
    return db if isinstance(db, MetaDB) else None


def _require_meta_db(request: Request) -> MetaDB:
    """元数据库不可用 → 503（而不是返回空列表让人以为"从来没有索引过"）。"""
    db = _meta_db(request)
    if db is None:
        raise ApiError(
            code="meta_db_unavailable",
            message="元数据库未就绪（zace-meta.db）：请通过 create_app 启动服务",
            status=503,
        )
    return db


def _visible_project_ids(request: Request, manager: Any) -> list[str]:
    """当前用户可见的 projectId（未鉴权时退化为全量，本地模式口径）。"""
    all_ids = [str(item["projectId"]) for item in manager.list_projects()]
    db = _meta_db(request)
    user = getattr(request.state, "zace_user", None)
    user_id = getattr(user, "id", None)
    if db is None or user_id is None:
        return all_ids
    owned = set(db.list_projects(user_id))
    return [pid for pid in all_ids if pid in owned]


def _limit(value: int) -> int:
    return max(1, min(int(value), MAX_LIMIT))


def _days(value: int) -> int:
    return max(1, min(int(value), MAX_DAYS))


def _core_importable() -> bool:
    """``zace_core`` 顶层包是否可导入（不触发 embedding 模型加载）。"""
    try:
        import zace_core  # noqa: F401  （只验证可导入性）
    except Exception:  # pragma: no cover - 依赖缺失/损坏时如实报 False
        return False
    return True


def _probe_embedding_provider() -> dict[str, Any]:
    """探测 embedding provider（仅 ``deep=1``）：ok + profile，或 ok=false + reason。"""
    try:
        from zace_core.embedding import EmbeddingConfig, create_provider

        config = EmbeddingConfig.from_env()
        provider = create_provider(config)
        ensure_loaded = getattr(provider, "ensure_loaded", None)
        if callable(ensure_loaded):  # 本地 ONNX：加载模型文件（缺文件在此暴露）
            ensure_loaded()
        else:  # API provider：发一次最小请求
            provider.embed(["zace healthz probe"])
        profile = provider.profile
        return {
            "ok": True,
            "modelId": profile.model_id,
            "dim": profile.dim,
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": redact_text(f"{type(exc).__name__}: {exc}"),
        }
