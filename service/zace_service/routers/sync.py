"""``/api/sync/*`` 占位路由（TASK-030）；TASK-033 就地替换为真实实现。

四条路径（CF-05）：``POST /api/sync/batch-upload`` / ``POST /api/sync/checkpoint`` /
``POST /api/sync/deletions`` / ``GET /api/sync/status/{projectId}``。

注意最后一个的参数名是 ``projectId``（驼峰）——与 CF-05 逐字对齐，不得改成 ``id``。
"""

from __future__ import annotations

from fastapi import APIRouter

from zace_service.errors import not_implemented

router = APIRouter(tags=["sync"])

_TASK = "TASK-033"


@router.post("/api/sync/batch-upload")
async def batch_upload() -> None:
    """批量上传源码 blob（按 blobHash 幂等）。"""
    raise not_implemented("POST /api/sync/batch-upload（批量上传）", _TASK)


@router.post("/api/sync/checkpoint")
async def create_checkpoint() -> None:
    """提交 scope blob 集合换取 checkpointId。"""
    raise not_implemented("POST /api/sync/checkpoint（checkpoint）", _TASK)


@router.post("/api/sync/deletions")
async def deletions() -> None:
    """通知删除路径（按 (projectId, path) 幂等）。"""
    raise not_implemented("POST /api/sync/deletions（删除通知）", _TASK)


@router.get("/api/sync/status/{projectId}")
async def sync_status(projectId: str) -> None:  # noqa: N803 - 路径参数名与 CF-05 逐字对齐
    """同步/索引状态。"""
    _ = projectId
    raise not_implemented("GET /api/sync/status/{projectId}（同步状态）", _TASK)
