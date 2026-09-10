"""``EngineManager``：core 引擎的进程内持有者（TASK-031 §C；D-34 薄壳）。

服务侧只做四件事：**项目登记（物理目录）**、**blob/账本访问**、**串行化**、**转调 core**；
检索、组装、索引的逻辑全部在 core（本文件不出现任何检索/组装代码）。

并发口径（§C）：core 是"单写者"假设（TASK-001/007/009），而 FastAPI 会把同步 handler 丢进
线程池 → **每 project 一把 ``threading.Lock``，同一 project 的 ingest / delete 串行**，
不同 project 可并行。锁表懒创建；``delete_project`` 也持锁。

不做 per-project 引擎实例缓存：``Store`` / ``VectorStore`` 都是 per-call 打开，
``Engine`` 本身无状态句柄（卡内明确"不要提前优化"）。

已知契约缺口（详见任务卡执行记录"未决问题"）：CF-07 的 ``ingest`` 只返回 ``job_id``，
而同步 API 需要 ``IngestReport``（added/skipped/errors 等）。为不在本卡改动 core 的公开面
（卡内只允许 §A 一处 core 改动），:meth:`EngineManager.ingest` 转调 ``Engine._ingest`` 取回
报告；建议后续在 core 侧把"ingest 并返回报告"纳入公开面。
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from zace_core.engine import PROJECT_META_FILENAME, Engine, EngineError, SearchTrace
from zace_core.pipeline import IngestReport
from zace_core.types import ChangeSet, ProjectHandle

from zace_service.blobstore import BlobSource, BlobStore
from zace_service.sync_state import SyncState

__all__ = ["EngineManager"]

logger = logging.getLogger("zace_service.runtime")

#: 引擎工厂（测试注入假 embedding provider 的接缝）。
EngineFactory = Callable[[Path], Engine]


class EngineManager:
    """一个进程一个实例：持有 ``Engine`` + per-project 锁表。"""

    def __init__(self, data_root: str | Path, engine: Engine) -> None:
        self._data_root = Path(data_root).expanduser()
        self._engine = engine
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    @classmethod
    def open(
        cls, data_root: str | Path, *, engine_factory: EngineFactory | None = None
    ) -> EngineManager:
        """打开管理器（provider 懒构造：起服务不加载模型；测试可注入假 provider）。"""
        root = Path(data_root).expanduser()
        factory: EngineFactory = engine_factory or Engine.open
        return cls(root, factory(root))

    # ------------------------------------------------------------------ 项目

    @property
    def data_root(self) -> Path:
        return self._data_root

    @property
    def engine(self) -> Engine:
        """底层引擎（TASK-032/033 需要 ``search_with_trace`` 等 core 公开方法时用；R33）。"""
        return self._engine

    def resolve_project(self, identity_key: str, display_name: str = "") -> ProjectHandle:
        """幂等解析/创建项目（D-29：identity_key 由调用方给出；物理层隔离在 core）。"""
        return self._engine.resolve_project(identity_key, display_name)

    def project_dir(self, project_id: str) -> Path:
        return self._engine.project_dir(project_id)

    def project_meta(self, project_id: str) -> dict[str, Any] | None:
        """读 ``project.json``；不存在或 id 非法 → ``None``（HTTP 层据此 404）。"""
        try:
            directory = self._engine.project_dir(project_id)
        except EngineError:
            return None
        path = directory / PROJECT_META_FILENAME
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("项目元数据不可读：%s", path)
            return None
        if not isinstance(raw, Mapping):
            return None
        created_at = raw.get("created_at")
        return {
            "projectId": project_id,
            "displayName": str(raw.get("display_name") or ""),
            "createdAt": created_at if isinstance(created_at, int) else 0,
        }

    def project_exists(self, project_id: str) -> bool:
        return self.project_meta(project_id) is not None

    def list_projects(self) -> list[dict[str, Any]]:
        """列出 ``{data_root}/projects/*/project.json`` 的摘要。

        本地模式（M2a）返回全部；M2c 才按 user 过滤。
        """
        projects_root = self._data_root / "projects"
        if not projects_root.is_dir():
            return []
        found: list[dict[str, Any]] = []
        for directory in sorted(projects_root.iterdir()):
            if not directory.is_dir():
                continue
            meta = self.project_meta(directory.name)
            if meta is not None:
                found.append(meta)
        return sorted(found, key=lambda item: (-item["createdAt"], item["projectId"]))

    def delete_project(self, project_id: str) -> bool:
        """级联删除（core 目录 rm -rf，含 ``blobs/`` 与 ``sync-state.json``）；不存在返回 False。"""
        with self._lock_for(project_id):
            if not self.project_exists(project_id):
                return False
            self._engine.delete_project(project_id)  # core：整个项目目录 rm -rf（D-03）
            with self._locks_guard:
                self._locks.pop(project_id, None)
        return True

    # ------------------------------------------------------------------ blob / 账本

    def blob_store(self, project_id: str) -> BlobStore:
        return BlobStore.open(self._engine.project_dir(project_id))

    def sync_state(self, project_id: str) -> SyncState:
        """从磁盘读同步账本（每次读盘：多进程/多次请求间不持有陈旧快照）。"""
        return SyncState.load(self._engine.project_dir(project_id))

    def blob_source(self, project_id: str) -> BlobSource:
        """构造给 core 的 ``SourceProvider``（账本快照 + blob 镜像）。"""
        return BlobSource(self.blob_store(project_id), self.sync_state(project_id))

    def project_paths(self, project_id: str) -> tuple[BlobStore, SyncState]:
        """``(blob 镜像, 同步账本)``——写路径共用同一份打开结果，避免重复读盘。"""
        directory = self._engine.project_dir(project_id)
        return BlobStore.open(directory), SyncState.load(directory)

    # ------------------------------------------------------------------ 数据面

    def ingest(self, project_id: str, changes: ChangeSet) -> IngestReport:
        """索引一次变更集（同 project 串行；source 用账本快照，见卡内 §A/§B）。"""
        with self._lock_for(project_id):
            source = self.blob_source(project_id)
            # ``_ingest`` 是 core 内部入口（返回 IngestReport）；CF-07 的 ``ingest`` 只回 job_id。
            # 见模块 docstring 的"已知契约缺口"。
            return self._engine._ingest(project_id, changes, full=False, source=source)  # noqa: SLF001

    def sync_status(self, project_id: str) -> dict[str, Any]:
        """core ``sync_status`` 全字段（camelCase，CF-05）+ 同步侧追加字段（TASK-033 口径）。"""
        status = self._engine.sync_status(project_id)
        state = self.sync_state(project_id)
        blob_count, blob_bytes = self.blob_store(project_id).usage()
        return {
            "projectId": status.project_id,
            "filesIndexed": status.files_indexed,
            "chunks": status.chunks,
            "symbols": status.symbols,
            "edges": status.edges,
            "pendingJobs": status.pending_jobs,
            "indexingFiles": list(status.indexing_files),
            "lastIndexedAt": status.last_indexed_at,
            "branch": state.branch,
            "commit": state.commit,
            "blobs": {"count": blob_count, "bytes": blob_bytes},
            "checkpoints": len(state.checkpoints),
        }

    def search(self, project_id: str, query: str, max_tokens: int = 10_000) -> SearchTrace:
        """Fast 模式检索（core ``search_with_trace``：通道健康度/候选计数给 meta 用，R33）。"""
        return self._engine.search_with_trace(project_id, query, max_tokens)

    def close(self) -> None:
        self._engine.close()

    # ------------------------------------------------------------------ 内部

    def _lock_for(self, project_id: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(project_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[project_id] = lock
            return lock
