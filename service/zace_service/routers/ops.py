"""``/healthz`` 与 ops 端点（TASK-030 §交付物；TASK-034 §D 追加 projects 进度）。

``GET /healthz``（CF-05，``security: []``）：存活 + 依赖检查。口径：

- **不加载 embedding 模型**（默认路径必须毫秒级返回）：只做一次 ``zace_core`` 顶层导入
  （纯 python 小模块），用于回答"内核是否可导入"；
- ``projects``（TASK-034）：本地模式已绑定项目的 ``{projectId, attachedRoot, indexProgress}``，
  **纯内存读取**（索引进行中也不变慢；不因索引中而返回非 200）；
- ``?deep=1`` 才探测 embedding provider（构造 + 预热/试嵌），失败时返回 **200** 且
  ``core.ok=false`` + ``reason``——探活端点自身不因依赖不可用而 500（否则监控无法区分
  "服务挂了"与"依赖没配好"）；
- reason 经 :func:`zace_service.logging.redact_text` 脱敏（provider 报错文本可能含 base_url/key）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from zace_service.deps import get_settings
from zace_service.errors import not_implemented
from zace_service.logging import redact_text

router = APIRouter(tags=["ops"])

_USAGE_TASK = "M2c/Phase 3（审计存档读取口）"


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
        # R34：M2a 本地单用户模式免鉴权；M2c 才接入 token/session。
        "auth": "disabled(local)" if settings.local_mode else "enabled",
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


@router.get("/api/usage/projects/{id}")
async def project_usage(id: str) -> None:  # noqa: A002 - 路径参数名与 CF-05 逐字对齐
    """查询审计（Module/04 §8 存档的读取口）。"""
    _ = id
    raise not_implemented("GET /api/usage/projects/{id}（查询审计）", _USAGE_TASK)


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
