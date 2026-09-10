"""统一错误信封与异常处理器（TASK-030 §交付物；CF-05 冻结合同）。

CF-05 冻结的 Error 形态（**不得改**）::

    {"error": {"code": "<稳定机器码>", "message": "<人类可读说明>"}}

转义规则（本卡冻结）：

- 业务/校验错误一律抛 :class:`ApiError`（含 HTTP 状态码），由处理器转成信封；
- 未知路径 404、方法不允许 405 也走同一信封（``not_found`` / ``method_not_allowed``）；
- 未捕获异常 → 500 ``internal_error``：**响应不含堆栈**，全量堆栈只进日志（Module/06 §3
  secret 纪律：错误响应不得泄漏实现细节与凭据）；
- 尚未实现的端点 → 501 ``not_implemented``（占位路由统一用它，见 TASK-030 §routers）。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

__all__ = [
    "INTERNAL_ERROR_MESSAGE",
    "ApiError",
    "error_envelope",
    "install_error_handlers",
    "internal_error_response",
    "not_implemented",
]

logger = logging.getLogger("zace_service.errors")

#: 500 的对外文案（不透露任何内部细节；细节在日志里）。
INTERNAL_ERROR_MESSAGE = "服务内部错误，请稍后重试；服务端日志含完整堆栈"


class ApiError(Exception):
    """带稳定机器码的业务错误（处理器按 ``status`` 返回 CF-05 信封）。"""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status


def error_envelope(code: str, message: str) -> dict[str, dict[str, str]]:
    """CF-05 的 Error 信封（唯一构造点）。"""
    return {"error": {"code": code, "message": message}}


def not_implemented(feature: str, task: str = "") -> ApiError:
    """占位路由的统一错误（501）：明说"未实现"与归属任务，不假装成功。"""
    suffix = f"（由 {task} 交付）" if task else ""
    return ApiError(
        code="not_implemented",
        message=f"{feature} 尚未实现{suffix}：本版本为 M2a 骨架，该端点为占位。",
        status=501,
    )


def internal_error_response() -> JSONResponse:
    """未捕获异常的统一响应（500 + 信封，无堆栈）。"""
    return JSONResponse(
        status_code=500, content=error_envelope("internal_error", INTERNAL_ERROR_MESSAGE)
    )


def install_error_handlers(app: FastAPI) -> None:
    """挂上 CF-05 的信封处理器（ApiError / HTTPException / 校验错误 / 兜底 Exception）。"""

    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content=error_envelope(exc.code, exc.message)
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(code, str(exc.detail) if exc.detail else code),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=error_envelope("invalid_request", _format_validation(exc)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # 日志留全量（含堆栈），响应只给通用文案（Module/06 §3：响应不泄漏实现细节）。
        logger.exception("unhandled error: %s %s", request.method, request.url.path)
        _ = exc
        return internal_error_response()


#: HTTP 状态码 → 稳定机器码（CF-05 只冻结信封形态；这里是本卡的映射口径）。
_HTTP_STATUS_CODES = {
    400: "invalid_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    501: "not_implemented",
}


def _format_validation(exc: RequestValidationError) -> str:
    """校验错误摘要（只含字段位置与原因，不含请求体内容）。"""
    details = []
    for error in exc.errors()[:5]:
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        details.append(f"{location or 'body'}: {error.get('msg', 'invalid')}")
    return "请求参数校验失败（" + "; ".join(details) + "）" if details else "请求参数校验失败"
