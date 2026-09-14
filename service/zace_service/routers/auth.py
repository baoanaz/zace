"""``/api/auth/*``：注册 / 登录 / 登出 / 首个用户初始化 / API Key 管理（TASK-060）。

设计依据：Module/06 §2.2（鉴权）、CF-05（``docs/contracts/openapi.yaml``）的 auth 段。

口径：

- **本地模式（默认）**：无账户体系（R34）。除 ``GET /api/meta`` 与 ``GET /api/auth/me``
  外，其余端点返回 403 ``local_mode``——**不假装有账户**，也不允许在本地模式建账户后
  以为自己受保护（诚实性优先）；
- **非本地模式**：``register`` 默认关闭（``ZACE_REGISTER_OPEN``），首次部署用
  ``POST /api/auth/bootstrap`` 建第一个账户（否则 ``register`` 关闭时**没有任何途径**产生用户）；
- **401 不区分细节**；``GET /api/auth/tokens`` **绝不含明文或哈希**；
- ``GET /api/meta``（TASK-088 §F）：免鉴权，因此**敏感面必须门禁**——
  未鉴权的云端调用只拿得到"配置了没"与"缺哪些环境变量名"，拿不到模型名/地址/参数。
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from zace_service.auth import (
    SESSION_COOKIE,
    authenticate,
    create_api_token,
    get_meta_db,
    hash_password,
    integrity_is_unique,
    issue_session,
    require_user,
    revoke_session,
    verify_password,
)
from zace_service.deps import get_settings
from zace_service.errors import ApiError
from zace_service.logging import get_logger

router = APIRouter(tags=["auth"])

logger = get_logger("zace_service.routers.auth")

#: 密码最短长度（TASK-081：用户要求放宽到 3 位；上限防 DoS：argon2 对超长输入要算很久）。
MIN_PASSWORD_CHARS = 3
MAX_PASSWORD_CHARS = 200
#: 账户名长度上限。
MAX_NAME_CHARS = 64


class Credentials(BaseModel):
    """注册/登录/初始化的请求体（CF-05 的 ``{name, password}``）。"""

    name: str = ""
    password: str = ""


class TokenRequest(BaseModel):
    """创建 API Key 的请求体（``name`` 可省略）。"""

    name: str = ""


@router.get("/api/meta")
def meta(request: Request) -> dict[str, Any]:
    """部署形态（**免鉴权**：web 首屏据此决定显示登录/初始化/直接进入）。

    只透出 ``needsBootstrap`` 这个**布尔**，不透出用户数量——那是人员信息。

    TASK-088 §F 追加 ``config``（设置页要展示生效中的 embedding / LLM 配置）：

    - **key 的任何部分（含前缀、长度、是否存在之外的任何信息）绝不返回**——
      LLM 侧只给 ``apiKeyConfigured`` 布尔；
    - 云端**未鉴权**时只给 ``configured`` / ``missingEnv``（环境变量**名**是公开信息，
      写文档里的就是它们），模型名与地址属内部拓扑，登录后才给。
    """
    settings = get_settings(request)
    user = getattr(request.state, "zace_user", None)
    needs_bootstrap = False
    user_count = 0
    if not settings.local_mode:
        db = get_meta_db(request)
        user_count = db.user_count()
        needs_bootstrap = user_count == 0
    return {
        "version": settings.version,
        "localMode": settings.local_mode,
        "authRequired": not settings.local_mode,
        "registerOpen": settings.register_open,
        "needsBootstrap": needs_bootstrap,
        "userCount": user_count if settings.local_mode else None,
        "config": effective_config(settings, details=settings.local_mode or user is not None),
    }


def effective_config(settings: Any, *, details: bool) -> dict[str, Any]:
    """生效中的服务配置（设置页展示用；**不含任何 secret**）。

    ``details=False``（云端未鉴权）：只回"配了没"与缺失的环境变量名；
    ``details=True``（本地模式或已登录）：额外回模型名/地址/超时等只读展示值。
    """
    return {
        "embedding": _embedding_config(details=details),
        "llm": _llm_config(settings, details=details),
    }


def _llm_config(settings: Any, *, details: bool) -> dict[str, Any]:
    """LLM（``ANSWER_*``）生效值。

    ``apiKeyConfigured`` 是**布尔**：连"key 有几个字符"都不给（长度也是信息）。
    """
    payload: dict[str, Any] = {
        "configured": bool(settings.answer_configured),
        "apiKeyConfigured": bool(settings.answer_api_key),
        "missingEnv": list(settings.answer_missing_env),
    }
    if not details:
        return payload
    payload.update(
        {
            "model": settings.answer_model,
            "baseUrl": settings.answer_base_url,
            "timeoutS": settings.answer_timeout_s,
            "maxTokens": settings.answer_max_tokens,
            "temperature": settings.answer_temperature,
        }
    )
    return payload


def _embedding_config(*, details: bool) -> dict[str, Any]:
    """embedding（``EMBED_*``）生效值（读 core 的工厂配置；**不调优、不加载模型**）。

    读不到（依赖缺失/配置非法）时如实回 ``error``——设置页宁可显示"读不到配置"，
    也不能凭空编一个模型名。
    """
    try:
        from zace_core.embedding import EmbeddingConfig

        config = EmbeddingConfig.from_env()
    except Exception as exc:  # noqa: BLE001 - 读配置失败不该让 /api/meta 挂掉
        return {"error": f"{type(exc).__name__}: {exc}"}
    payload: dict[str, Any] = {
        "mode": config.mode,
        "configured": bool(config.model) if config.mode == "api" else True,
        "missingEnv": _embedding_missing(config),
    }
    if details:
        payload.update(
            {
                "model": config.model,
                "provider": config.provider,
                "baseUrl": config.base_url,
                "dim": config.dim,
                "maxInputTokens": config.max_input_tokens,
                "offline": config.offline,
            }
        )
    return payload


def _embedding_missing(config: Any) -> list[str]:
    """api 模式缺哪个环境变量（本地模式无必填项）。"""
    if config.mode != "api":
        return []
    missing: list[str] = []
    if not config.model:
        missing.append("EMBED_MODEL")
    if not config.base_url:
        missing.append("EMBED_BASE_URL")
    return missing


@router.post("/api/auth/register", status_code=201)
def register(payload: Credentials, request: Request, response: Response) -> dict[str, Any]:
    """注册（默认关闭；``ZACE_REGISTER_OPEN`` 开启后可用）。"""
    settings = get_settings(request)
    _require_remote(settings.local_mode)
    if not settings.register_open:
        raise ApiError(
            code="register_disabled",
            message="注册已关闭：请用 ZACE_REGISTER_OPEN=true 开启，或用初始化接口建第一个账户",
            status=403,
        )
    name, password = _validate_credentials(payload)
    db = get_meta_db(request)
    try:
        user = db.create_user(name, hash_password(password))
    except sqlite3.IntegrityError as exc:
        if integrity_is_unique(exc):
            raise ApiError(
                code="name_taken", message=f"账户名已被占用：{name}", status=409
            ) from None
        raise
    _set_session_cookie(response, issue_session(db, user.id), settings)
    return {"userId": user.id, "name": user.name, "createdAt": user.created_at}


@router.post("/api/auth/bootstrap", status_code=201)
def bootstrap(payload: Credentials, request: Request, response: Response) -> dict[str, Any]:
    """首个用户初始化：``users`` 表为空时创建并直接登录，之后**自动关闭**。

    为什么必须有：``register`` 默认关闭（Module/06 §2.2），全新部署否则**没有任何途径**
    产生第一个账户。已有用户时返回 403，**不得**用它创建第二个账户，也不得覆盖第一个。
    """
    settings = get_settings(request)
    _require_remote(settings.local_mode)
    name, password = _validate_credentials(payload)
    db = get_meta_db(request)
    if db.user_count() > 0:
        raise ApiError(
            code="already_initialized",
            message="已存在账户，初始化接口已关闭：请改用登录，或由管理员开启注册",
            status=403,
        )
    try:
        user = db.create_user(name, hash_password(password))
    except sqlite3.IntegrityError as exc:  # 并发初始化：另一个请求已经建好了
        if integrity_is_unique(exc):
            raise ApiError(
                code="already_initialized", message="已存在账户，初始化接口已关闭", status=403
            ) from None
        raise
    logger.info("初始化首个账户：%s", user.name)
    _set_session_cookie(response, issue_session(db, user.id), settings)
    return {"userId": user.id, "name": user.name, "createdAt": user.created_at}


@router.post("/api/auth/login")
def login(payload: Credentials, request: Request, response: Response) -> dict[str, Any]:
    """登录（签发 httpOnly session cookie）。账户不存在与密码错误**同一文案**。"""
    settings = get_settings(request)
    _require_remote(settings.local_mode)
    name = payload.name.strip()
    db = get_meta_db(request)
    found = db.get_user_by_name(name)
    if found is None or not verify_password(payload.password, found[1]):
        raise ApiError(
            code="unauthorized", message="账户名或密码不正确", status=401
        )
    user = found[0]
    _set_session_cookie(response, issue_session(db, user.id), settings)
    return {"userId": user.id, "name": user.name, "createdAt": user.created_at}


@router.post("/api/auth/logout")
def logout(request: Request, response: Response) -> Response:
    """登出：清除 cookie + 服务端会话失效。"""
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        revoke_session(get_meta_db(request), session_id)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/api/auth/me")
def me(request: Request) -> dict[str, Any]:
    """当前身份（web 每次加载据此判断"登录了没、我是谁"）。

    本地模式返回隐式账户（``isLocal=true``），因此 web 首屏不必特判。
    """
    principal = require_user(request)
    user = principal.user
    return {
        "userId": user.id,
        "name": user.name,
        "createdAt": user.created_at,
        "isLocal": user.is_local,
        "via": principal.via,
    }


@router.post("/api/auth/tokens")
def create_token(payload: TokenRequest, request: Request) -> dict[str, Any]:
    """创建 API Key（**明文仅此一次返回**）。"""
    principal = require_user(request)
    _require_remote(get_settings(request).local_mode)
    raw, digest, prefix = create_api_token()
    db = get_meta_db(request)
    token_id = db.create_token(
        principal.user.id, token_hash=digest, prefix=prefix, name=payload.name.strip()
    )
    return {"id": token_id, "token": raw, "prefix": prefix, "name": payload.name.strip()}


@router.get("/api/auth/tokens")
def list_tokens(request: Request) -> list[dict[str, Any]]:
    """列出 API Key（**不含明文与哈希**；已撤销的不列）。"""
    principal = require_user(request)
    _require_remote(get_settings(request).local_mode)
    return get_meta_db(request).list_tokens(principal.user.id)


@router.delete("/api/auth/tokens/{id}")
def revoke_token(id: str, request: Request) -> Response:  # noqa: A002 - 路径参数名与 CF-05 逐字对齐
    """撤销 API Key（软删；只能撤销自己的）。"""
    principal = require_user(request)
    _require_remote(get_settings(request).local_mode)
    if not get_meta_db(request).revoke_token(principal.user.id, id):
        raise ApiError(code="token_not_found", message=f"API Key 不存在或已撤销：{id}", status=404)
    return Response(status_code=204)


# --------------------------------------------------------------------------- 辅助


def _require_remote(local_mode: bool) -> None:
    """本地模式没有账户体系（R34）：返回 403 而不是假装成功。"""
    if local_mode:
        raise ApiError(
            code="local_mode",
            message=(
                "本地单用户模式没有账户与 API Key（R34）：该端点在云端形态"
                "（ZACE_LOCAL_MODE=false）下才有意义"
            ),
            status=403,
        )


def _validate_credentials(payload: Credentials) -> tuple[str, str]:
    name = payload.name.strip()
    if not name or len(name) > MAX_NAME_CHARS:
        raise ApiError(
            code="invalid_name",
            message=f"账户名不能为空且不超过 {MAX_NAME_CHARS} 个字符",
            status=400,
        )
    if len(payload.password) < MIN_PASSWORD_CHARS:
        raise ApiError(
            code="invalid_password",
            message=f"密码至少 {MIN_PASSWORD_CHARS} 个字符",
            status=400,
        )
    if len(payload.password) > MAX_PASSWORD_CHARS:
        raise ApiError(
            code="invalid_password",
            message=f"密码不能超过 {MAX_PASSWORD_CHARS} 个字符",
            status=400,
        )
    return name, payload.password


def _set_session_cookie(response: Response, session_id: str, settings: Any) -> None:
    """写 session cookie：httpOnly + SameSite=Lax；``Secure`` 由部署形态决定。"""
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=30 * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


# 供 web/测试读取"当前身份"的同一入口（避免 routes 之外再写一份解析逻辑）。
__all__ = ["authenticate", "router"]
