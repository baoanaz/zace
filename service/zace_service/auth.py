"""鉴权原语与会话/Key 解析（TASK-060；Module/06 §2.2）。

三条纪律：

1. **本地模式（默认）完全放行**（R34）：行为与今天逐字一致——本地单用户模式不该被迫登录。
   普通 ``serve`` 始终鉴权；只有显式 ``local`` 命令的本地形态免鉴权；
2. **401 不区分细节**（Module/06 §2.2）：token 无效 / 已撤销 / 会话过期一律 ``unauthorized``，
   不给探测面；
3. **明文不留存**：密码用 argon2id 单向哈希；API Key 只存 ``sha256``，明文仅创建时返回一次。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Request

from zace_service.config import Settings
from zace_service.deps import get_settings
from zace_service.errors import ApiError
from zace_service.logging import get_logger
from zace_service.metadb import META_DB_FILENAME, MetaDB, User

__all__ = [
    "LOCAL_USER_NAME",
    "SESSION_COOKIE",
    "TOKEN_PREFIX",
    "authenticate",
    "create_api_token",
    "get_meta_db",
    "hash_api_token",
    "hash_password",
    "issue_session",
    "llm_owner",
    "llm_owner_optional",
    "local_user",
    "require_user",
    "revoke_session",
    "verify_password",
]

logger = get_logger("zace_service.auth")

#: 会话 cookie 名（CF-05 的 ``sessionCookie``）。
SESSION_COOKIE = "zace_session"
#: API Key 前缀（``zace_`` + 随机串；库里只存哈希）。
TOKEN_PREFIX = "zace_"
#: 本地模式的隐式账户名（不落 users 表：本地模式无账户概念，R34）。
LOCAL_USER_NAME = "local"
#: 会话有效期（30 天，卡内默认）。
SESSION_TTL_S = 30 * 86400

#: argon2id 参数取 argon2-cffi 默认（RFC 9106 的推荐档：time=3, memory=64MiB, parallelism=4）。
_hasher = PasswordHasher()

#: 懒构造 ``MetaDB`` 的互斥（多线程首个请求可能同时到达，与 ``deps`` 同口径）。
_meta_db_lock = threading.Lock()


@dataclass(frozen=True, slots=True)
class Principal:
    """当前请求的身份（本地模式的隐式账户 ``is_local=True``）。"""

    user: User
    via: str  # "session" | "token" | "local"


# --------------------------------------------------------------------------- 密码


def hash_password(password: str) -> str:
    """密码 → argon2id 编码串（含随机盐与参数，可直接存库）。"""
    return _hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    """校验密码（算法/参数不匹配或密码错误 → ``False``，不抛异常）。"""
    try:
        return _hasher.verify(encoded, password)
    except VerifyMismatchError:
        return False
    except Exception:  # 编码串损坏/参数非法：按校验失败处理，不把异常抛给调用方
        return False


# --------------------------------------------------------------------------- API Key


def hash_api_token(raw: str) -> str:
    """API Key → ``sha256``（Key 是 256 位随机串，不需要慢哈希）。"""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_api_token() -> tuple[str, str, str]:
    """生成 ``(明文, 哈希, 前缀)``；明文只在创建响应里出现一次。"""
    raw = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    return raw, hash_api_token(raw), raw[: len(TOKEN_PREFIX) + 6]


# --------------------------------------------------------------------------- 会话

def issue_session(db: MetaDB, user_id: str, *, now: int | None = None) -> str:
    """签发会话 id（cookie 里放的**就是**这个 id；库里存同一值）。"""
    return db.create_session(user_id, ttl_s=SESSION_TTL_S, now=now)


def revoke_session(db: MetaDB, session_id: str) -> None:
    db.delete_session(session_id)


# --------------------------------------------------------------------------- 身份解析


def local_user(*, now: int | None = None) -> User:
    """本地模式的隐式账户（**不落库**：本地模式没有账户体系，R34）。"""
    return User(
        id="local",
        name=LOCAL_USER_NAME,
        created_at=int(now if now is not None else time.time()),
        is_local=True,
    )


def authenticate(request: Request) -> Principal | None:
    """解析请求凭据：``Authorization: Bearer`` 优先，其次 session cookie。

    返回 ``None`` = 没有有效凭据（由调用方决定是否放行——本地模式放行）。
    """
    settings = get_settings(request)
    if settings.local_mode:
        return Principal(user=local_user(), via="local")

    header = request.headers.get("Authorization", "")
    scheme, _, raw = header.partition(" ")
    if scheme.lower() == "bearer" and raw.strip():
        db = get_meta_db(request)
        user = db.find_user_by_token_hash(hash_api_token(raw.strip()))
        if user is not None:
            return Principal(user=user, via="token")
        return None

    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        db = get_meta_db(request)
        user = db.resolve_session(session_id)
        if user is not None:
            return Principal(user=user, via="session")
    return None


def require_user(request: Request) -> Principal:
    """要求身份（非本地模式下无有效凭据 → 401）。

    **401 文案统一**：不区分"无效/已撤销/过期/无权限"（Module/06 §2.2 的探测面纪律）。
    """
    principal = authenticate(request)
    if principal is None:
        raise ApiError(
            code="unauthorized",
            message="缺少或无效的凭据：请在 Authorization: Bearer 头带上 API Key，或先登录",
            status=401,
        )
    return principal


def llm_owner(request: Request) -> User:
    """\"这个请求该把用户级 LLM 配置算在谁头上\"的**唯一口径**（TASK-099 §C）。

    - 本地模式：**总是**有一个隐式账户（``authenticate`` 已返回它，但鉴权中间件在本地模式把
      ``zace_user`` 置为 ``None``）——因此这里回落到 :func:`local_user`，否则本地模式下的
      设置页保存成功了、``ask`` 却找不到那份配置；
    - 云端：走 :func:`require_user`（无凭据 → 401），与其余账户级端点一致。

    为什么必须集中：保存（``PUT /api/auth/llm-config``）、展示（``GET /api/meta``）与消费
    （``POST /api/query/ask`` / MCP ``ask_project``）**三处必须算出同一个 user_id**，
    否则会出现"设置页显示已配置、实际没用上"这类静默失灵——那正是本卡要消灭的问题。
    """
    settings = get_settings(request)
    if settings.local_mode:
        user = getattr(request.state, "zace_user", None)
        return user if isinstance(user, User) else local_user()
    return require_user(request).user


def llm_owner_optional(request: Request) -> User | None:
    """**免鉴权路径**上的 LLM 归属人（``GET /api/meta``）：无凭据时返回 ``None``。

    为什么不能直接用 :func:`llm_owner`：``/api/meta`` 是公开端点（web 首屏就知道该显示登录
    还是控制台），在那里要求鉴权会把它变成 401。未鉴权的云端调用回 ``None`` → 解析层
    回落服务端默认，与 TASK-088 §F 的"未鉴权只看得到配了没"逐字一致。
    """
    settings = get_settings(request)
    if settings.local_mode:
        user = getattr(request.state, "zace_user", None)
        return user if isinstance(user, User) else local_user()
    user = getattr(request.state, "zace_user", None)
    if isinstance(user, User):
        return user
    # `/api/meta` 是公开路径，鉴权中间件会直接放行，因此已登录浏览器的 user 不会预先写进
    # request.state。这里做一次可选认证：有合法 cookie/key 就返回详情，没有则仍保持公开响应。
    principal = authenticate(request)
    return principal.user if principal is not None else None


def get_meta_db(request: Request) -> MetaDB:
    """取当前应用的 ``MetaDB``（``create_app`` 写入 ``app.state``；测试可覆盖）。"""
    db = getattr(request.app.state, "meta_db", None)
    if isinstance(db, MetaDB):
        return db
    settings: Settings = get_settings(request)
    with _meta_db_lock:
        db = getattr(request.app.state, "meta_db", None)
        if not isinstance(db, MetaDB):
            db = MetaDB.open(settings.data_root / META_DB_FILENAME)
            request.app.state.meta_db = db
    return db


def constant_time_equals(left: str, right: str) -> bool:
    """定时安全比较（会话 id 等敏感串比较时用，避免逐字符短路）。"""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def integrity_is_unique(exc: sqlite3.IntegrityError) -> bool:
    """``sqlite3.IntegrityError`` 是否是唯一约束冲突（``name`` 已被占用 → 409）。"""
    return "UNIQUE" in str(exc).upper()
