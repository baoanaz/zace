"""``/api/projects/*`` 项目 API（TASK-031 §D；TASK-034 §A 追加本地模式三个面）。

端点（CF-05 路径与 TASK-034 §A 的新增路径，不得增删改名）：

| 端点 | 语义 |
|---|---|
| ``POST /api/projects/resolve`` | 按 ``identityKey``（D-29）幂等解析/创建项目 |
| ``POST /api/projects/attach`` | **TASK-034**：绑定本地仓库目录 + 后台索引（**仅本地模式**） |
| ``POST /api/projects/{id}/rescan`` | **TASK-034**：手动触发增量重扫（202；已在跑 → 409） |
| ``GET /api/projects`` | 本地模式列出全部项目摘要（含 ``attachedRoot`` / ``indexProgress``） |
| ``GET /api/projects/{id}`` | 项目详情 + ``sync``（core 状态）+ ``blobs`` 用量 + 本地模式字段 |
| ``DELETE /api/projects/{id}`` | 级联删除（core 目录 rm -rf，含 blobs/账本）→ 204 |

薄壳纪律（D-34）：本文件不出现任何检索/组装/索引逻辑，全部转调 ``EngineManager``。
handler 一律用**同步 def**：core 是阻塞式实现，FastAPI 会把它放进线程池
（``EngineManager`` 的 per-project 锁正是为此准备）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from zace_service.deps import get_engine_manager, get_settings
from zace_service.errors import ApiError
from zace_service.indexer import LocalRootError

router = APIRouter(tags=["projects"])

#: ``identityKey`` 的长度上限（D-29 的 key 是 sha256 十六进制，留足余量给将来的其它形态）。
MAX_IDENTITY_KEY = 512
#: ``displayName`` 的长度上限。
MAX_DISPLAY_NAME = 200
#: ``root`` 的长度上限（本地路径，留足 Windows/WSL 长路径余量）。
MAX_ROOT_CHARS = 4096


class ResolveRequest(BaseModel):
    """``POST /api/projects/resolve`` 的请求体（CF-05）。"""

    identityKey: str = Field(min_length=1, max_length=MAX_IDENTITY_KEY)
    displayName: str = Field(default="", max_length=MAX_DISPLAY_NAME)


class AttachRequest(BaseModel):
    """``POST /api/projects/attach`` 的请求体（TASK-034 §A）。"""

    root: str = Field(min_length=1, max_length=MAX_ROOT_CHARS)
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


@router.post("/api/projects/attach")
def attach_project(payload: AttachRequest, request: Request) -> dict[str, Any]:
    """绑定本地仓库目录并后台索引（TASK-034 §A）：**立即返回**，不等索引完成。

    - 非本地模式 → 403 ``local_mode_required``（R34：远端模式靠客户端上传，没有共同文件系统）；
    - ``root`` 不存在/不是目录 → 400 ``invalid_root``；
    - 已在索引中 → **不重入**，返回当前进度（不报错：attach 本身是幂等的）。
    """
    if not get_settings(request).local_mode:
        raise ApiError(
            "local_mode_required",
            "POST /api/projects/attach 仅在本地单用户模式（ZACE_LOCAL_MODE=true）可用："
            "服务与代码不在同一文件系统时，请用客户端上传（/api/sync/batch-upload）。",
            403,
        )
    manager = get_engine_manager(request)
    try:
        result = manager.attach_local(
            payload.root, display_name=payload.displayName.strip(), index=True
        )
    except LocalRootError as exc:
        raise ApiError("invalid_root", str(exc), 400) from None
    return result.to_json()


@router.post("/api/projects/{id}/rescan")
def rescan_project(  # noqa: A002 - 路径参数名与 CF-05 一致
    id: str, request: Request
) -> JSONResponse:
    """手动触发增量重扫（TASK-034 §A）：202 + 当前 ``indexProgress``；已在跑 → 409。"""
    if not get_settings(request).local_mode:
        raise ApiError(
            "local_mode_required", "POST /api/projects/{id}/rescan 仅在本地单用户模式可用", 403
        )
    manager = get_engine_manager(request)
    if not manager.project_exists(id):
        raise ApiError("project_not_found", f"项目不存在：{id}", 404)
    if manager.attached_root(id) is None:
        raise ApiError(
            "local_root_unknown",
            "该项目在本服务实例里没有绑定本地目录（重启后未 attach）："
            "请用 zace-service local --repo <path> 启动，或先 POST /api/projects/attach",
            409,
        )
    if not manager.start_index(id):
        raise ApiError(
            "index_running",
            f"该项目已有索引任务在跑（{_progress_text(manager, id)}），不重复触发；"
            "请稍后查看 GET /api/projects/{id} 的 indexProgress",
            409,
        )
    return JSONResponse(
        status_code=202, content={"indexProgress": manager.index_progress(id).to_json()}
    )


@router.get("/api/projects")
def list_projects(request: Request) -> list[dict[str, Any]]:
    """项目列表（本地模式：全部；按创建时间倒序；含 ``attachedRoot`` / ``indexProgress``）。"""
    return get_engine_manager(request).list_projects()


@router.get("/api/projects/{id}")
def get_project(id: str, request: Request) -> dict[str, Any]:  # noqa: A002 - 路径参数名与 CF-05 一致
    """项目详情：元数据 + ``sync``（core 状态 + 同步侧字段）+ ``blobs`` + 本地模式字段。"""
    manager = get_engine_manager(request)
    meta = manager.project_meta(id)
    if meta is None:
        raise ApiError("project_not_found", f"项目不存在：{id}", 404)
    status = manager.sync_status(id)
    described = manager.describe_project(id, meta)
    return {**described, "sync": status, "blobs": status["blobs"]}


@router.delete("/api/projects/{id}")
def delete_project(id: str, request: Request) -> Response:  # noqa: A002 - 路径参数名与 CF-05 一致
    """级联删除（D-03：整个项目目录 rm -rf，含 index.db / vectors / blobs / 同步账本）。"""
    manager = get_engine_manager(request)
    if not manager.delete_project(id):
        raise ApiError("project_not_found", f"项目不存在：{id}", 404)
    return Response(status_code=204)


def _progress_text(manager: Any, project_id: str) -> str:
    """进度的一句话描述（错误文案用；不伪造百分比，D-30）。"""
    progress = manager.index_progress(project_id)
    return (
        f"state={progress.state}，已处理 {progress.processed_files}/{progress.total_files} 个文件"
    )
