"""``/api/auth/*`` 占位路由（TASK-030）。

**本卡不实现鉴权**：M2a 为本地单用户模式（``docs/plan/contracts.md`` §3.8 R34），无鉴权、
无用户概念；token / session / 用户体系归 M2c（TASK-060/061）。

路径必须存在（CF-05 的路径集合是冻结合同，实现可以迟到、路径不能漂移），
因此这里只注册路径、统一返回 501 ``not_implemented``。

处理函数**不声明请求体模型**：占位语义是"未实现"，不得因为 body 不合法先返回 400/422
（那会与"路径存在但未实现"的语义混淆）。
"""

from __future__ import annotations

from fastapi import APIRouter

from zace_service.errors import not_implemented

router = APIRouter(tags=["auth"])

_TASK = "M2c（TASK-060/061）"


@router.post("/api/auth/register")
async def register() -> None:
    """注册（默认关闭；M2c 实现）。"""
    raise not_implemented("POST /api/auth/register（注册）", _TASK)


@router.post("/api/auth/login")
async def login() -> None:
    """登录（签发 session cookie；M2c 实现）。"""
    raise not_implemented("POST /api/auth/login（登录）", _TASK)


@router.post("/api/auth/logout")
async def logout() -> None:
    """登出（M2c 实现）。"""
    raise not_implemented("POST /api/auth/logout（登出）", _TASK)


@router.post("/api/auth/tokens")
async def create_token() -> None:
    """创建 API token（明文仅此一次返回；M2c 实现）。"""
    raise not_implemented("POST /api/auth/tokens（创建 token）", _TASK)


@router.get("/api/auth/tokens")
async def list_tokens() -> None:
    """列出 token（不含明文；M2c 实现）。"""
    raise not_implemented("GET /api/auth/tokens（token 列表）", _TASK)


@router.delete("/api/auth/tokens/{id}")
async def revoke_token(id: str) -> None:  # noqa: A002 - 路径参数名与 CF-05 逐字对齐
    """revoke token（软删；M2c 实现）。"""
    _ = id
    raise not_implemented("DELETE /api/auth/tokens/{id}（revoke token）", _TASK)
