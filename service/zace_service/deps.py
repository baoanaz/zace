"""FastAPI 依赖注入接缝（TASK-030 建；TASK-031 追加 engine_manager）。

为什么走 ``app.state`` 而不是模块级单例：测试要能用临时 ``data_root`` 与假 embedding
provider 覆盖整个应用配置（``create_app(app_state)`` 的一个属性即可），而不用打补丁
改全局状态。TASK-031 的 ``EngineManager`` 走同一接缝。
"""

from __future__ import annotations

from fastapi import Request

from zace_service.config import Settings
from zace_service.errors import ApiError

__all__ = ["get_settings"]


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
