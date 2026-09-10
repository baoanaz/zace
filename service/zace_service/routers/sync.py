"""``/api/sync/*`` 同步 API（TASK-033；Module/05 §3.3 的服务端一半，D-27 懒同步）。

四个端点（路径与 CF-05 逐字对齐）：

| 端点 | 语义 |
|---|---|
| ``POST /api/sync/batch-upload`` | 批量上传 blob（每批解码后 ≤1MiB；按 blobHash 幂等）+ 增量索引 |
| ``POST /api/sync/checkpoint`` | 提交 scope blob 集合 → 内容寻址的 ``checkpointId``（保留 3 个） |
| ``POST /api/sync/deletions`` | 通知删除路径（按 (projectId, path) 幂等；级联删索引与镜像） |
| ``GET  /api/sync/status/{projectId}`` | core ``sync_status`` 全字段 + 同步侧追加字段 |

口径（本卡冻结）：

- **``accepted`` 表示“服务端已持久化 blob”，不等于“已索引成功”**（Module/05 §3.6）：索引失败明细在
  ``report.errors``，二进制/不可解码文件在 ``report.skippedFiles``；客户端不得据此判定检索可用；
- **校验顺序固定**（每种错误都能单独复现）：空批 → 逐条 base64 解码（累计超限立即 413）→
  路径安全 → ``blobHash`` 与 CF-02 的 ``blob_hash(path, content)`` 一致（宁可拒绝，
  也不让账本被污染）；
- **同步索引**（M2a）：每个上传请求内跑完索引并由 ``report`` 如实回报；后台 job/进度上报是
  TASK-062；
- ``indexingFiles`` / ``pendingJobs`` 恒为空/0 是**正确的**（不伪造，D-30）。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from zace_core.hashing import blob_hash
from zace_core.pipeline import IngestReport
from zace_core.pipeline.source import SourcePathError
from zace_core.types import BlobInput, ChangeSet

from zace_service.blobstore import validate_repo_path
from zace_service.deps import get_engine_manager, require_project_id
from zace_service.errors import ApiError

router = APIRouter(tags=["sync"])

#: 单批解码后的字节上限（Module/05 §4：≤1MB/批，notace 实测参数）。
MAX_BATCH_BYTES = 1024 * 1024


class BlobPayload(BaseModel):
    """一个待上传的源码 blob（CF-05：``contentB64`` = base64(文件原始字节)）。"""

    path: str
    blobHash: str
    contentB64: str


class BatchUploadRequest(BaseModel):
    """``POST /api/sync/batch-upload`` 的请求体。"""

    projectId: str | None = None
    branch: str | None = None
    commit: str | None = None
    blobs: list[BlobPayload] = []


class CheckpointRequest(BaseModel):
    """``POST /api/sync/checkpoint`` 的请求体。"""

    projectId: str | None = None
    blobHashes: list[str] = []


class DeletionsRequest(BaseModel):
    """``POST /api/sync/deletions`` 的请求体。"""

    projectId: str | None = None
    paths: list[str] = []


@router.post("/api/sync/batch-upload")
def batch_upload(payload: BatchUploadRequest, request: Request) -> dict[str, Any]:
    """批量上传：blob 镜像 → 账本 → 一次增量 ``ingest``（同 project 串行，见 EngineManager）。"""
    manager = get_engine_manager(request)
    project_id = require_project_id(request, payload.projectId)
    if not payload.blobs:
        raise ApiError("empty_batch", "blobs 不能为空（空批不发请求）", 400)

    decoded = _decode_blobs(payload.blobs)
    _blobs, state = manager.project_paths(project_id)
    known = set(state.files)

    accepted: list[str] = []
    added: list[BlobInput] = []
    modified: list[BlobInput] = []
    for item in decoded:
        # 幂等：同 (path, blobHash) 已落盘则不再写字节，但仍计入 accepted（CF-05 明确）。
        _blobs.put(item.path, item.blob_hash, item.content)
        state.record_file(item.path, item.blob_hash, len(item.content))
        accepted.append(item.blob_hash)
        (modified if item.path in known else added).append(item)

    state.set_head(payload.branch, payload.commit)
    state.save()

    report = manager.ingest(
        project_id,
        ChangeSet(
            added=tuple(added),
            modified=tuple(modified),
            branch=payload.branch,
            commit_id=payload.commit,
        ),
    )
    return {
        "accepted": accepted,
        "skipped": list(report.skipped_files),
        "report": report_json(report),
    }


@router.post("/api/sync/checkpoint")
def create_checkpoint(payload: CheckpointRequest, request: Request) -> dict[str, str]:
    """内容寻址的 checkpoint（同集合必同 id；账本保留最近 ``MAX_CHECKPOINTS`` 个）。"""
    manager = get_engine_manager(request)
    project_id = require_project_id(request, payload.projectId)
    checkpoint_id = checkpoint_id_for(payload.blobHashes)
    state = manager.sync_state(project_id)
    state.record_checkpoint(checkpoint_id, sorted(set(payload.blobHashes)))
    state.save()
    return {"checkpointId": checkpoint_id}


@router.post("/api/sync/deletions")
def report_deletions(payload: DeletionsRequest, request: Request) -> dict[str, list[str]]:
    """删除通知（固定顺序）：账本移除 → 无引用的 blob 镜像删除 → 一次 ``ingest(deleted=...)``。

    幂等：重复删除的路径进 ``unknown`` 且不报错（Module/05 §9-3 口径）；账本里没有的路径
    不做任何索引动作（``deleted`` 为空时不触发 ingest）。
    """
    manager = get_engine_manager(request)
    project_id = require_project_id(request, payload.projectId)
    blobs, state = manager.project_paths(project_id)

    before = state.files  # 快照（remove_paths 之后就查不到 hash 了）
    deleted, unknown = state.remove_paths(payload.paths)
    still_referenced = set(state.blob_hashes())
    for path in deleted:
        digest = before[path].blob_hash
        if digest not in still_referenced:  # 内容寻址：多个 path 可能共享同一 blob
            blobs.delete(digest)
    state.save()

    if deleted:
        manager.ingest(project_id, ChangeSet(deleted=deleted))
    return {"deleted": list(deleted), "unknown": list(unknown)}


@router.get("/api/sync/status/{projectId}")
def sync_status(projectId: str, request: Request) -> dict[str, Any]:  # noqa: N803 - CF-05 路径参数名
    """同步/索引状态（core 全字段 + 同步侧追加字段）。"""
    manager = get_engine_manager(request)
    if not manager.project_exists(projectId):
        raise ApiError("project_not_found", f"项目不存在：{projectId}", 404)
    return manager.sync_status(projectId)


# --------------------------------------------------------------------------- 校验与工具


def checkpoint_id_for(blob_hashes: Sequence[str]) -> str:
    """``"cp_" + sha256("\\n".join(sorted(set(hashes))))[:16]``（内容寻址 → 天然幂等）。"""
    material = "\n".join(sorted(set(blob_hashes)))
    return "cp_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _decode_blobs(items: Sequence[BlobPayload]) -> list[BlobInput]:
    """逐条解码 + 校验（顺序固定：base64 → 累计批大小 → 路径安全 → hash 一致）。"""
    decoded: list[BlobInput] = []
    total = 0
    for item in items:
        try:
            content = base64.b64decode(item.contentB64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ApiError(
                "invalid_content_encoding",
                f"blob {item.path!r} 的 contentB64 不是合法 base64：{exc}",
                400,
            ) from None
        total += len(content)
        if total > MAX_BATCH_BYTES:
            raise ApiError(
                "batch_too_large",
                f"单批解码后总字节超过上限 {MAX_BATCH_BYTES}（客户端需分批上传）",
                413,
            )
        try:
            validate_repo_path(item.path)
        except SourcePathError as exc:
            raise ApiError("invalid_path", str(exc), 400) from None
        expected = blob_hash(item.path, content)
        if expected != item.blobHash:
            raise ApiError(
                "blob_hash_mismatch",
                f"blob {item.path!r} 的 blobHash 与 CF-02 的 blob_hash(path, content) 不一致"
                "（拒绝写入，避免污染账本）",
                400,
            )
        decoded.append(BlobInput(path=item.path, content=content, blob_hash=expected))
    return decoded


def report_json(report: IngestReport) -> dict[str, Any]:
    """``IngestReport`` → 同步 API 的报告字段（client（TASK-040）依赖的形态）。"""
    return {
        "added": report.added,
        "modified": report.modified,
        "deleted": report.deleted,
        "chunksNew": report.chunks_new,
        "chunksReused": report.chunks_reused,
        "chunksRemoved": report.chunks_removed,
        "filesParsed": report.files_parsed,
        "errors": list(report.errors),
        "skippedFiles": list(report.skipped_files),
    }


__all__ = [
    "MAX_BATCH_BYTES",
    "BatchUploadRequest",
    "CheckpointRequest",
    "DeletionsRequest",
    "batch_upload",
    "checkpoint_id_for",
    "create_checkpoint",
    "report_deletions",
    "report_json",
    "sync_status",
]
