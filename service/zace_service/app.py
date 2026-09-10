"""FastAPI 应用装配（TASK-030 §交付物；后续卡只在此挂实现，不改装配面）。

冻结入口：``create_app(settings: Settings | None = None) -> FastAPI``——测试、``__main__``
与将来的 ASGI server 都走它（不提供模块级 ``app`` 全局单例，避免配置与进程状态纠缠）。

装配内容：

1. ``Settings`` 解析（缺省读环境变量）并写入 ``app.state.settings``；
2. JSON 日志（stderr）+ ``RedactingFilter``（见 ``zace_service.logging``）；
3. requestId middleware：每请求一个 id（尊重调用方传的 ``X-Request-Id``），
   响应头回写 ``X-Request-Id``，访问日志只记 method/path/status/耗时（不碰 headers/body）；
4. CF-05 错误信封处理器（见 ``zace_service.errors``）；
5. 全部路由（路径集合冻结，见 ``zace_service.routers``）。

``app.state.engine_manager`` 在本卡恒为 ``None``（TASK-030 不消费 core）；TASK-031 起由
``zace_service.deps.get_engine_manager`` 懒构造或由测试注入。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from zace_service.config import Settings
from zace_service.errors import install_error_handlers, internal_error_response
from zace_service.logging import bind_request_id, configure_logging, get_logger, reset_request_id
from zace_service.routers import all_routers

__all__ = ["REQUEST_ID_HEADER", "create_app"]

#: requestId 的传递头（请求可自带，响应必回写）。
REQUEST_ID_HEADER = "X-Request-Id"

logger = get_logger("zace_service.app")


def create_app(settings: Settings | None = None) -> FastAPI:
    """构造应用（唯一入口；同进程可创建多个实例，测试用临时 data_root 互不干扰）。"""
    resolved = settings if settings is not None else Settings.from_env()
    configure_logging(resolved.log_level)

    app = FastAPI(
        title="zace-service",
        version=resolved.version,
        description="zace 服务化外壳（Module/06）；检索/组装逻辑全部来自 zace-core。",
    )
    app.state.settings = resolved
    app.state.engine_manager = None  # TASK-031 懒构造/测试注入

    install_error_handlers(app)
    _install_request_context(app)
    for router in all_routers():
        app.include_router(router)
    return app


def _install_request_context(app: FastAPI) -> None:
    """requestId + 访问日志 + 兜底 500（保证异常不会逃出应用，响应始终是 CF-05 信封）。"""

    @app.middleware("http")
    async def _request_context(  # noqa: ANN202 - FastAPI middleware 的返回类型由框架决定
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        token = bind_request_id(request_id)
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:  # 兜底：日志留全量堆栈，响应只给通用文案（errors.py 同口径）
                logger.exception(
                    "unhandled request error",
                    extra={
                        "requestId": request_id,
                        "method": request.method,
                        "path": request.url.path,
                    },
                )
                response = internal_error_response()
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "request",
                extra={
                    "requestId": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "durationMs": duration_ms,
                },
            )
            return response
        finally:
            reset_request_id(token)
