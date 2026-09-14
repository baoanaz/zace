"""``/api/auth/*``：注册 / 登录 / 登出 / 首个用户初始化 / API Key 管理（TASK-060）。

设计依据：Module/06 §2.2（鉴权）、CF-05（``docs/contracts/openapi.yaml``）的 auth 段。

口径：

- **本地模式（默认）**：无账户体系（R34）。除 ``GET /api/meta`` 与 ``GET /api/auth/me``
  外，其余端点返回 403 ``local_mode``——**不假装有账户**，也不允许在本地模式建账户后
  以为自己受保护（诚实性优先）；
- **非本地模式**：首次部署用 ``POST /api/auth/bootstrap`` 建第一个账户，之后注册与登录始终可用；
- **401 不区分细节**；``GET /api/auth/tokens`` **绝不含明文或哈希**；
- ``GET /api/meta``（TASK-088 §F）：免鉴权，因此**敏感面必须门禁**——
  未鉴权的云端调用只拿得到"配置了没"与"缺哪些环境变量名"，拿不到模型名/地址/参数。

TASK-099 §C 追加 **用户级 LLM 配置**（``PUT`` / ``DELETE /api/auth/llm-config``）：
**这两个端点在本地模式也允许**（与 ``tokens`` / ``register`` 的 403 不同）。理由：
本地单用户自部署是本项目的主场景，而"让用户配自己的 LLM"正是该场景下最需要的功能；
为它强行要求开户 + 登录才能用，是把实现约束当成产品约束。实现上仍是**同一套**归属逻辑——
本地模式的隐式账户 ``auth.local_user()`` 提供一个真实 ``user_id``（``"local"``），
配置存在同一张 ``user_llm_config`` 表里（卡内 §C-2/§C-3）。
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
    llm_owner,
    llm_owner_optional,
    require_user,
    revoke_session,
    verify_password,
)
from zace_service.deps import get_settings
from zace_service.errors import ApiError
from zace_service.llmconfig import (
    SOURCE_SERVER,
    SOURCE_USER,
    ResolvedLlmConfig,
    resolve_llm_config,
)
from zace_service.logging import get_logger
from zace_service.metadb import MetaDB

router = APIRouter(tags=["auth"])

logger = get_logger("zace_service.routers.auth")

#: 密码最短长度（TASK-081：用户要求放宽到 3 位；上限防 DoS：argon2 对超长输入要算很久）。
MIN_PASSWORD_CHARS = 3
MAX_PASSWORD_CHARS = 200
#: 账户名长度上限。
MAX_NAME_CHARS = 64
#: LLM 配置字段的长度上限（防超长输入：URL/模型名/Key 都是小串）。
MAX_LLM_FIELD_CHARS = 2048


class Credentials(BaseModel):
    """注册/登录/初始化的请求体（CF-05 的 ``{name, password}``）。"""

    name: str = ""
    password: str = ""


class TokenRequest(BaseModel):
    """创建 API Key 的请求体（``name`` 可省略）。"""

    name: str = ""


class LlmConfigRequest(BaseModel):
    """``PUT /api/auth/llm-config`` 的请求体（TASK-099 §C-3）。

    ``apiKey`` 传空串（或不传）表示**保持不变**：用户只想改模型名时不必重新粘贴 key
    （key 从不回显，因此"留空 = 不改"是唯一能用的语义）。首次保存必须给 key。
    """

    model: str = ""
    baseUrl: str = ""
    apiKey: str = ""


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
    needs_bootstrap = False
    user_count = 0
    if not settings.local_mode:
        db = get_meta_db(request)
        user_count = db.user_count()
        needs_bootstrap = user_count == 0
    # TASK-099 §C-4：设置页要显示"**当前实际生效**的那一份"配置。用户配了 LLM 时（REST 面
    # 就会用它的）必须展示用户那份，否则页面会拿环境变量给人看，与实际行为相反。
    # ``/api/meta`` 免鉴权（web 首屏）→ 用 optional 版本：未登录的云端调用拿不到
    # 用户配置，回落服务端默认（TASK-088 §F 的同一门禁口径）。
    owner = llm_owner_optional(request)
    resolved = resolve_llm_config(
        settings, user_id=getattr(owner, "id", None), db=_optional_meta_db(request)
    )
    return {
        "version": settings.version,
        "localMode": settings.local_mode,
        "authRequired": not settings.local_mode,
        # 保留既有响应字段兼容旧 web/client；注册不再受部署配置控制。
        "registerOpen": True,
        "needsBootstrap": needs_bootstrap,
        "userCount": user_count if settings.local_mode else None,
        "config": effective_config(
            settings, details=settings.local_mode or owner is not None, resolved=resolved
        ),
    }


def effective_config(
    settings: Any, *, details: bool, resolved: ResolvedLlmConfig | None = None
) -> dict[str, Any]:
    """生效中的服务配置（设置页展示用；**不含任何 secret**）。

    ``details=False``（云端未鉴权）：只回"配了没"与缺失的环境变量名；
    ``details=True``（本地模式或已登录）：额外回模型名/地址/超时等只读展示值。

    ``resolved``（TASK-099 §C-4）：已解析出的**实际生效**配置；为 ``None`` 时按环境变量报。
    """
    return {
        "embedding": _embedding_config(details=details),
        "llm": _llm_config(settings, details=details, resolved=resolved),
        "storage": _storage_config(settings),
    }


def _storage_config(settings: Any) -> dict[str, Any]:
    """存储配额生效值（TASK-094 §B1/§B4；只读展示，**没有任何 secret 面**）。

    ``perProjectBytes`` / ``perUserBytes`` 为 ``0`` 表示**不限**（前端据此只显示已用、不画进度条）。
    这三个数与 :mod:`zace_service.quota` 的判定**同源**（都来自 ``Settings``），因此设置页显示的
    “上限”与实际告警阈值不会漂移。
    """
    return {
        "perProjectBytes": int(settings.storage_limit_per_project_bytes),
        "perUserBytes": int(settings.storage_limit_per_user_bytes),
        "warnRatio": float(settings.storage_warn_ratio),
        "enabled": bool(settings.storage_quota_enabled),
    }


def _llm_config(
    settings: Any, *, details: bool, resolved: ResolvedLlmConfig | None = None
) -> dict[str, Any]:
    """LLM 生效值（``ANSWER_*`` 或**用户配置**）。

    ``apiKeyConfigured`` 是**布尔**：连"key 有几个字符"都不给（长度也是信息）。
    TASK-099 §C-4 追加 ``source``（``user`` / ``server``）：设置页据此告诉用户
    "现在实际在用哪一份"；该用户的 key 本身**永不出现在任何字段**里（只有布尔）。
    """
    if resolved is not None and resolved.source == SOURCE_USER:
        return {
            "configured": resolved.configured,
            "apiKeyConfigured": bool(resolved.api_key),
            # 用户配置不来自环境变量 → 这里为空（前端据此不再显示"缺环境变量"那一句）。
            "missingEnv": [],
            "missingKeys": list(resolved.missing_keys),
            "source": SOURCE_USER,
            "model": resolved.model,
            "baseUrl": resolved.base_url,
            "timeoutS": resolved.timeout_s,
            "maxTokens": resolved.max_tokens,
            "temperature": resolved.temperature,
            **_llm_model_metadata(resolved.model),
        }
    payload: dict[str, Any] = {
        "configured": bool(settings.answer_configured),
        "apiKeyConfigured": bool(settings.answer_api_key),
        "missingEnv": list(settings.answer_missing_env),
        "missingKeys": [],
        "source": SOURCE_SERVER,
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
            **_llm_model_metadata(settings.answer_model),
        }
    )
    return payload


def _llm_model_metadata(model: str | None) -> dict[str, Any]:
    """已知 LLM 的只读展示元数据；未知模型不猜。"""
    if model == "deepseek/deepseek-v4.1-flash":
        return {"provider": "DeepSeek", "maxContextTokens": 128_000}
    if model and "deepseek" in model.lower():
        return {"provider": "DeepSeek"}
    return {}


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
        model = config.model
        provider = config.provider
        dim = config.dim
        max_input_tokens = config.max_input_tokens
        if config.mode == "local" and model:
            from zace_core.embedding.registry import get_local_spec

            spec = get_local_spec(model)
            provider = "Local ONNX"
            dim = dim or spec.dim
            max_input_tokens = max_input_tokens or spec.max_input_tokens
        elif config.mode == "api" and model:
            from zace_core.embedding.registry import find_api_spec, resolve_transport

            spec = find_api_spec(model)
            transport = resolve_transport(spec, base_url=config.base_url, provider=config.provider)
            provider = transport.provider
            if spec is not None:
                dim = dim or spec.output_dimension or spec.dim
                max_input_tokens = max_input_tokens or spec.max_input_tokens
        payload.update(
            {
                "model": model,
                "provider": provider,
                "baseUrl": config.base_url,
                "dim": dim,
                "maxInputTokens": max_input_tokens,
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
    """注册账户；完整服务模式始终可用。"""
    settings = get_settings(request)
    _require_remote(settings.local_mode)
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

    为什么保留：它为首个账户提供原子初始化语义，避免并发部署时产生多个首任账户。
    已有用户时返回 403，**不得**用它创建第二个账户，也不得覆盖第一个。
    """
    settings = get_settings(request)
    _require_remote(settings.local_mode)
    name, password = _validate_credentials(payload)
    db = get_meta_db(request)
    if db.user_count() > 0:
        raise ApiError(
            code="already_initialized",
            message="已存在账户，初始化接口已关闭：请改用登录或注册",
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


# --------------------------------------------------------------------------- 用户级 LLM 配置


@router.put("/api/auth/llm-config")
def put_llm_config(payload: LlmConfigRequest, request: Request) -> dict[str, Any]:
    """保存（或覆盖）**本用户**的 LLM 配置（TASK-099 §C-3）。

    三个字段语义：

    - ``model`` / ``baseUrl``：必填（空串 → 400 ``invalid_llm_config``）；
    - ``apiKey``：空串/省略 = **保持不变**（key 从不回显，"留空不改"是唯一可用语义）；
      首次保存必须给值，否则 400。

    **响应里不含 key 的任何部分**（含长度/前缀/哈希）：只给 ``apiKeyConfigured`` 布尔。
    日志只记 ``user_id`` 与 ``model``——``model`` 是用户自选的非敏感值（与 ``baseUrl`` 不同，
    后者是内部拓扑，只在已登录的 ``/api/meta`` 里出现）。

    本地模式也允许（见模块 docstring）：用隐式账户 ``auth.local_user()``，它提供一个稳定
    的 ``user_id``，因此配置同样能落到 ``user_llm_config`` 表里并被 ``ask`` 用上。
    """
    user = _llm_owner(request)
    model = payload.model.strip()
    base_url = payload.baseUrl.strip()
    api_key = payload.apiKey.strip()
    _validate_llm_config(model, base_url, api_key)
    db = _require_meta_db(request)
    try:
        saved = db.save_llm_config(
            user.id,
            model=model,
            base_url=base_url,
            # 空串 → None = 保持不变（见 :meth:`MetaDB.save_llm_config`）。
            api_key=api_key or None,
        )
    except ValueError as exc:
        # 唯一触发点：首次保存没给 key（没有旧值可继承）。
        raise ApiError(code="invalid_llm_config", message=str(exc), status=400) from None
    logger.info("用户 LLM 配置已更新：user=%s model=%s", user.id, saved.model)
    return {**saved.to_json(), "source": SOURCE_USER}


@router.delete("/api/auth/llm-config")
def delete_llm_config(request: Request) -> Response:
    """删除本用户的 LLM 配置 → 回落服务端默认（TASK-099 §C-3）。

    **幂等**：本来就没配也返回 204。删除的语义是"让它不在"，而"已经不在"就是目标状态；
    报 404 只会让前端多写一个无意义的分支（用户点两次"清除"不是错误）。

    返回 204（无响应体）：没有任何有意义的字段可回（key 不回显，source 固定是 server）。
    """
    user = _llm_owner(request)
    removed = _require_meta_db(request).delete_llm_config(user.id)
    logger.info("用户 LLM 配置已删除（回落服务端默认）：user=%s removed=%s", user.id, removed)
    return Response(status_code=204)


def _llm_owner(request: Request) -> Any:
    """LLM 配置的归属人（本地模式为隐式账户，云端为已认证用户）。

    直接转调 :func:`zace_service.auth.llm_owner`：保存 / 展示（``/api/meta``）/ 消费
    （``ask``）三处必须用**同一个** ``user_id``，否则会出现"设置页显示已配置、实际没用上"。
    """
    return llm_owner(request)


def _validate_llm_config(model: str, base_url: str, api_key: str) -> None:
    """字段校验（长度 + 非空 + URL 形态）。**不回显任何字段值**——key 可能就在里面。"""
    for name, value in (("model", model), ("baseUrl", base_url), ("apiKey", api_key)):
        if len(value) > MAX_LLM_FIELD_CHARS:
            raise ApiError(
                code="invalid_llm_config",
                message=f"{name} 过长（上限 {MAX_LLM_FIELD_CHARS} 字符）",
                status=400,
            )
    if not model:
        raise ApiError(code="invalid_llm_config", message="model 不能为空", status=400)
    if not base_url:
        raise ApiError(code="invalid_llm_config", message="baseUrl 不能为空", status=400)
    if not base_url.startswith(("http://", "https://")):
        raise ApiError(
            code="invalid_llm_config",
            message="baseUrl 必须以 http:// 或 https:// 开头（请填 OpenAI 兼容的 /v1 地址）",
            status=400,
        )


def _require_meta_db(request: Request) -> MetaDB:
    """LLM 配置必须有库可存：无库 → 503（而不是假装保存成功）。

    本地模式下 ``create_app`` 不建库（R34），因此这条分支在本地模式下是**可能的**——
    诚实优于便利：返回 503 并说明为什么，比"200 但其实什么都没存"好。
    """
    db = _optional_meta_db(request)
    if db is None:
        raise ApiError(
            code="meta_db_unavailable",
            message="元数据库未就绪（zace-meta.db），用户配置无处存放：请通过 create_app 启动服务",
            status=503,
        )
    return db


def _optional_meta_db(request: Request) -> MetaDB | None:
    """可缺失的元数据库（不在此处建库：本地模式按 R34 默认无账户库）。"""
    db = getattr(request.app.state, "meta_db", None)
    return db if isinstance(db, MetaDB) else None


# --------------------------------------------------------------------------- 辅助


def _require_remote(local_mode: bool) -> None:
    """本地模式没有账户体系（R34）：返回 403 而不是假装成功。"""
    if local_mode:
        raise ApiError(
            code="local_mode",
            message=(
                "本地单用户模式没有账户与 API Key（R34）：该端点在云端形态"
                "（普通 serve 模式）下才有意义"
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
