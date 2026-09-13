"""FastAPI 应用装配（TASK-030 §交付物；后续卡只在此挂实现，不改装配面）。

冻结入口：``create_app(settings: Settings | None = None) -> FastAPI``——测试、``__main__``
与将来的 ASGI server 都走它（不提供模块级 ``app`` 全局单例，避免配置与进程状态纠缠）。

装配内容：

1. ``Settings`` 解析（缺省读环境变量）并写入 ``app.state.settings``；
2. JSON 日志（stderr）+ ``RedactingFilter``（见 ``zace_service.logging``）；
3. requestId middleware：每请求一个 id（尊重调用方传的 ``X-Request-Id``），
   响应头回写 ``X-Request-Id``，访问日志只记 method/path/status/耗时（不碰 headers/body）；
4. CF-05 错误信封处理器（见 ``zace_service.errors``）；
5. 全部路由（路径集合冻结，见 ``zace_service.routers``）；
6. **MCP 端点**（TASK-040）：``/mcp`` 挂 MCP Streamable HTTP（见 ``zace_service.mcp``）。
   MCP 不是 CF-05 的 REST 路径（挂载不进 ``openapi()["paths"]``），因此路径快照测试不受影响。

``app.state.engine_manager`` 在本卡恒为 ``None``（TASK-030 不消费 core）；TASK-031 起由
``zace_service.deps.get_engine_manager`` 懒构造或由测试注入；TASK-040 的 MCP 工具走
``zace_service.mcp.manager_for_app``（同一口径，只是入口没有 ``Request``）。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from zace_service.auth import authenticate
from zace_service.config import Settings
from zace_service.errors import error_envelope, install_error_handlers, internal_error_response
from zace_service.logging import bind_request_id, configure_logging, get_logger, reset_request_id
from zace_service.mcp import build_mcp, manager_for_app, mount, session_lifespan
from zace_service.metadb import MetaDB
from zace_service.routers import all_routers

__all__ = ["PUBLIC_PATHS", "REQUEST_ID_HEADER", "create_app"]

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
    # TASK-060：云瑞形态才需要元数据库；本地模式不建库（R34：无账户体系）。
    app.state.meta_db = MetaDB.open(resolved.meta_db_path) if resolved.auth_required else None

    install_error_handlers(app)
    _install_request_context(app)
    _install_auth(app, resolved)
    for router in all_routers():
        app.include_router(router)
    _install_mcp(app, resolved)
    return app


#: 免鉴权路径（前缀匹配）：探活、部署形态、登录/注册/初始化/登出。
PUBLIC_PATHS = (
    "/healthz",
    "/api/meta",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/bootstrap",
    "/api/auth/logout",
)


def _install_auth(app: FastAPI, settings: Settings) -> None:
    """鉴权中间件（TASK-060；Module/06 §2.2）。

    为什么用中间件而不是逐个路由的 ``Depends``：**鉴权是全局不变量**，逐个挂靠人工维护，
    漏一个就是越权面（TASK-051 A1 的 `auth: enabled` 自述已经在骗人）；中间件只判"能不能进"，
    业务侧的归属校验（TASK-061）仍在依赖里。

    本地模式（默认）**完全放行**：行为与今天逐字一致（R34）。

    ``request.state.zace_user`` 写入已认证用户：下游（归属校验、概览聚合、审计归属）读它，
    避免重复解析凭据。
    """

    @app.middleware("http")
    async def _authenticate(  # noqa: ANN202 - FastAPI middleware 的返回类型由框架决定
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if settings.local_mode:
            request.state.zace_user = None  # 本地模式无账户；下游按 None 走全量口径
            return await call_next(request)

        path = request.url.path
        if path.startswith(PUBLIC_PATHS):
            return await call_next(request)

        principal = authenticate(request)
        if principal is None:
            # 401 不区分细节（无效/已撤销/过期同一文案）：不给探测面。
            return JSONResponse(
                status_code=401,
                content=error_envelope(
                    "unauthorized",
                    "缺少或无效的凭据：请在 Authorization: Bearer 头带上 API Key，或先登录",
                ),
            )
        request.state.zace_user = principal.user
        return await call_next(request)


def _install_mcp(app: FastAPI, settings: Settings) -> None:
    """挂载 MCP 端点并启用 session manager 的 lifespan（TASK-040）。

    ``build_mcp`` 收的是**懒解析函数**：/healthz 与占位路由不得因为挂了 MCP 就去构造引擎
    （TASK-030 的"起服务不加载模型"纪律，`test_healthz_without_touching_core` 守着这一点）。

    lifespan 的接管方式：TASK-030 的 app 没有自己的 lifespan（无既有逻辑可被覆盖），因此这里
    直接设 ``router.lifespan_context``；将来若有了别的 lifespan，改到 :func:`session_lifespan`
    里嵌套组合。
    """
    server = build_mcp(lambda: manager_for_app(app), settings=settings)
    mount(app, server)
    app.router.lifespan_context = session_lifespan(server)


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
