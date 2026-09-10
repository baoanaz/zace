"""FastAPI 依赖注入接缝（TASK-030 建；TASK-031 追加 engine_manager 与 projectId 解析）。

为什么走 ``app.state`` 而不是模块级单例：测试要能用临时 ``data_root`` 与假 embedding
provider 覆盖整个应用配置（``create_app(app_settings)`` 后写 ``app.state.engine_manager``），
而不用打补丁改全局状态。

``EngineManager`` 采用**懒构造**：首个真正访问 core 的请求才实例化（起服务不加载 embedding
模型，``/healthz`` 与占位路由保持毫秒级）。
"""

from __future__ import annotations

import threading

from fastapi import Request

from zace_service.config import Settings
from zace_service.errors import ApiError
from zace_service.runtime import EngineManager

__all__ = ["get_engine_manager", "get_settings", "require_project_id"]

#: 懒构造 EngineManager 的互斥（多线程首个请求可能同时到达）。
_manager_lock = threading.Lock()


def get_settings(request: Request) -> Settings:
    """取当前应用的 ``Settings``（由 :func:`zace_service.app.create_app` 写入 ``app.state``）。"""
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):  # pragma: no cover - 只有手工拼装 app 才会走到
        raise ApiError(
            code="service_not_configured",
            message="应用未初始化 Settings（请通过 create_app() 创建应用）",
            status=500,
        )
    return settings


def get_engine_manager(request: Request) -> EngineManager:
    """取 ``EngineManager``（测试可预热注入；否则按 ``Settings.data_root`` 懒构造一次）。"""
    manager = getattr(request.app.state, "engine_manager", None)
    if isinstance(manager, EngineManager):
        return manager
    with _manager_lock:
        manager = getattr(request.app.state, "engine_manager", None)
        if not isinstance(manager, EngineManager):
            manager = EngineManager.open(get_settings(request).data_root)
            request.app.state.engine_manager = manager
    return manager


def require_project_id(request: Request, project_id: str | None) -> str:
    """解析请求里的 ``projectId``（CF-05 扩展 R37：本地模式可省略）。

    - 显式给出：必须存在，否则 404 ``project_not_found``；
    - 省略：仅本地模式（``ZACE_LOCAL_MODE``）允许，取**唯一**的本地项目；
      本地 0 个项目 → 404（附"先 resolve"提示）；多于 1 个 → 409 ``ambiguous_project``
      （不猜、不隐式选一个：静默挑错项目比报错更糟）。
    """
    manager = get_engine_manager(request)
    if project_id:
        if not manager.project_exists(project_id):
            raise ApiError(
                code="project_not_found",
                message=f"项目不存在：{project_id}",
                status=404,
            )
        return project_id

    settings = get_settings(request)
    if not settings.local_mode:
        raise ApiError(
            code="project_id_required",
            message="非本地模式必须显式提供 projectId（R37 的省略仅限 ZACE_LOCAL_MODE）",
            status=400,
        )
    projects = manager.list_projects()
    if not projects:
        raise ApiError(
            code="project_not_found",
            message="本地还没有任何项目：请先用 POST /api/projects/resolve 或先同步一次",
            status=404,
        )
    if len(projects) > 1:
        raise ApiError(
            code="ambiguous_project",
            message=(
                f"本地存在 {len(projects)} 个项目，省略 projectId 有歧义："
                "请显式传入 projectId（本地单项目模式才允许省略）"
            ),
            status=409,
        )
    return str(projects[0]["projectId"])
