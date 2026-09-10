"""``/api/query/*`` 占位路由（TASK-030）；TASK-032 就地替换为真实实现。

两个端点（CF-05）：``POST /api/query/search``（Fast：服务端渲染 Markdown）与
``POST /api/query/ask``（Deep：Phase 2 走 D-26 降级包，绝不 500）。
"""

from __future__ import annotations

from fastapi import APIRouter

from zace_service.errors import not_implemented

router = APIRouter(tags=["query"])

_TASK = "TASK-032"


@router.post("/api/query/search")
async def search() -> None:
    """Fast 模式检索（返回服务端渲染的 Markdown 与 meta）。"""
    raise not_implemented("POST /api/query/search（Fast 检索）", _TASK)


@router.post("/api/query/ask")
async def ask() -> None:
    """Deep 模式问答（Phase 2 为降级包，Phase 3 接 LLM）。"""
    raise not_implemented("POST /api/query/ask（Deep 问答）", _TASK)
