"""``/api/projects/*`` 占位路由（TASK-030）；TASK-031 就地替换为真实实现。

路径与 CF-05 逐字对齐（``/api/projects/{id}``：参数名必须与合同一致，否则路径字符串漂移）。
本卡不声明请求体模型（占位语义见 ``routers/auth.py`` 的说明）。
"""

from __future__ import annotations

from fastapi import APIRouter

from zace_service.errors import not_implemented

router = APIRouter(tags=["projects"])

_TASK = "TASK-031"


@router.post("/api/projects/resolve")
async def resolve_project() -> None:
    """按 ``identityKey``（D-29）幂等解析/创建项目。"""
    raise not_implemented("POST /api/projects/resolve（解析/创建项目）", _TASK)


@router.get("/api/projects")
async def list_projects() -> None:
    """项目列表（本地模式：全部）。"""
    raise not_implemented("GET /api/projects（项目列表）", _TASK)


@router.get("/api/projects/{id}")
async def get_project(id: str) -> None:  # noqa: A002 - 路径参数名与 CF-05 逐字对齐
    """项目详情 + 同步状态。"""
    _ = id
    raise not_implemented("GET /api/projects/{id}（项目详情）", _TASK)


@router.delete("/api/projects/{id}")
async def delete_project(id: str) -> None:  # noqa: A002 - 路径参数名与 CF-05 逐字对齐
    """级联删除（rm -rf 项目目录 + blobs + 同步账本）。"""
    _ = id
    raise not_implemented("DELETE /api/projects/{id}（级联删除）", _TASK)
