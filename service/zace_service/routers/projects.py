"""``/api/projects/*`` 项目 API（TASK-031 §D；CF-05 的 projects 段）。

四个端点（路径与 CF-05 逐字对齐，本卡不得增删改名）：

| 端点 | 语义 |
|---|---|
| ``POST /api/projects/resolve`` | 按 ``identityKey``（D-29）幂等解析/创建项目 |
| ``GET /api/projects`` | 本地模式列出全部项目摘要（M2c 才按 user 过滤） |
| ``GET /api/projects/{id}`` | 项目详情 + ``sync``（core 状态）+ ``blobs`` 用量 |
| ``DELETE /api/projects/{id}`` | 级联删除（core 目录 rm -rf，含 blobs/账本）→ 204 |

薄壳纪律（D-34）：本文件不出现任何检索/组装/索引逻辑，全部转调 ``EngineManager``。
handler 一律用**同步 def**：core 是阻塞式实现，FastAPI 会把它放进线程池
（``EngineManager`` 的 per-project 锁正是为此准备）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from zace_service.deps import get_engine_manager
from zace_service.errors import ApiError

router = APIRouter(tags=["projects"])

#: ``identityKey`` 的长度上限（D-29 的 key 是 sha256 十六进制，留足余量给将来的其它形态）。
MAX_IDENTITY_KEY = 512
#: ``displayName`` 的长度上限。
MAX_DISPLAY_NAME = 200


class ResolveRequest(BaseModel):
    """``POST /api/projects/resolve`` 的请求体（CF-05）。"""

    identityKey: str = Field(min_length=1, max_length=MAX_IDENTITY_KEY)
    displayName: str = Field(default="", max_length=MAX_DISPLAY_NAME)


@router.post("/api/projects/resolve")
def resolve_project(payload: ResolveRequest, request: Request) -> dict[str, Any]:
    """幂等解析/创建项目（同 identityKey 两次 → 同 projectId，第二次 ``created=false``）。"""
    identity_key = payload.identityKey.strip()
    if not identity_key:
        raise ApiError("invalid_identity_key", "identityKey 不能为空白字符串", 400)
    manager = get_engine_manager(request)
    handle = manager.resolve_project(identity_key, payload.displayName.strip())
    return {"projectId": handle.project_id, "created": handle.created}


@router.get("/api/projects")
def list_projects(request: Request) -> list[dict[str, Any]]:
    """项目列表（本地模式：全部；按创建时间倒序）。"""
    return get_engine_manager(request).list_projects()


@router.get("/api/projects/{id}")
def get_project(id: str, request: Request) -> dict[str, Any]:  # noqa: A002 - 路径参数名与 CF-05 一致
    """项目详情：元数据 + ``sync``（core 状态 + 同步侧字段）+ ``blobs`` 用量。"""
    manager = get_engine_manager(request)
    meta = manager.project_meta(id)
    if meta is None:
        raise ApiError("project_not_found", f"项目不存在：{id}", 404)
    status = manager.sync_status(id)
    return {**meta, "sync": status, "blobs": status["blobs"]}


@router.delete("/api/projects/{id}")
def delete_project(id: str, request: Request) -> Response:  # noqa: A002 - 路径参数名与 CF-05 一致
    """级联删除（D-03：整个项目目录 rm -rf，含 index.db / vectors / blobs / 同步账本）。"""
    manager = get_engine_manager(request)
    if not manager.delete_project(id):
        raise ApiError("project_not_found", f"项目不存在：{id}", 404)
    return Response(status_code=204)
