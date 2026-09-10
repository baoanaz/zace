"""``EngineManager``：core 引擎的进程内持有者（TASK-031 §C；D-34 薄壳）。

服务侧只做四件事：**项目登记（物理目录）**、**blob/账本访问**、**串行化**、**转调 core**；
检索、组装、索引的逻辑全部在 core（本文件不出现任何检索/组装代码）。

并发口径（§C）：core 是"单写者"假设（TASK-001/007/009），而 FastAPI 会把同步 handler 丢进
线程池 → **每 project 一把 ``threading.Lock``，同一 project 的 ingest / delete 串行**，
不同 project 可并行。锁表懒创建；``delete_project`` 也持锁。

不做 per-project 引擎实例缓存：``Store`` / ``VectorStore`` 都是 per-call 打开，
``Engine`` 本身无状态句柄（卡内明确"不要提前优化"）。

已知契约缺口（TASK-035 §C 已收敛）：CF-07 的 ``ingest`` 只返回 ``job_id``，而同步 API 需要
``IngestReport``（added/skipped/errors 等）。现改调 core 的**公开** ``Engine.apply_changes``
（TASK-035 §C 方案 1），service 侧不再出现 ``engine._ingest``。

provider 健康（TASK-035 §A/§B）：:meth:`EngineManager.provider_health` 供 sync/query 的
错误分支使用；它**不加载模型、不做推理**，只用两个信号：①最近一次 provider 故障记忆
（每次 ingest/search 后更新）②``Engine.provider`` 的构造（配置合法性 + 本地模型文件定位）。
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TypeVar

from zace_core.engine import PROJECT_META_FILENAME, Engine, EngineError, SearchTrace
from zace_core.pipeline import IngestReport
from zace_core.types import ChangeSet, ProjectHandle

from zace_service.blobstore import BlobSource, BlobStore
from zace_service.errors import embedding_failure_reason
from zace_service.logging import redact_text
from zace_service.sync_state import SyncState

__all__ = ["EngineManager"]

logger = logging.getLogger("zace_service.runtime")

#: 引擎工厂（测试注入假 embedding provider 的接缝）。
EngineFactory = Callable[[Path], Engine]

_T = TypeVar("_T")


class EngineManager:
    """一个进程一个实例：持有 ``Engine`` + per-project 锁表。"""

    def __init__(self, data_root: str | Path, engine: Engine) -> None:
        self._data_root = Path(data_root).expanduser()
        self._engine = engine
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        #: 最近一次 provider 故障摘要（脱敏）；成功后清空。见 provider_health。
        self._provider_error: str | None = None

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
            # TASK-035 §C：调 core 的公开 ``apply_changes``（不再跨包调 ``Engine._ingest``）。
            return self._observe_provider(
                lambda: self._engine.apply_changes(project_id, changes, source=source)
            )

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
        return self._observe_provider(
            lambda: self._engine.search_with_trace(project_id, query, max_tokens),
            # 降级（如向量通道失败）不是"provider 恢复了"：保留故障记忆，不谎报健康。
            recovered=lambda trace: not trace.degraded,
        )

    # ------------------------------------------------------------------ provider 健康（§A/§B）

    def provider_health(self) -> tuple[bool, str | None]:
        """provider 健康快照 ``(ok, reason)``（TASK-035 §A/§B）。

        **不加载模型、不做真实推理**，只用两个信号：

        1. 故障记忆：最近一次 ingest/search 是否因 provider 挂掉失败（成功即清空）——
           连接类故障（如 API 地址不可达）只有在真实调用时才暴露，光看配置看不出来；
        2. 配置合法性 + 已加载状态：``Engine.provider`` 的构造（``EMBED_*`` 合法？本地模型文件
           可定位？）。已构造过（``provider`` 属性已缓存）→ 直接 ok。

        调用方（query/sync 的错误分支）据此把根因放在首位：provider 坏了就要报 503，
        而不是让客户端看到"请先同步"去无限重试（TASK-035 §B）。
        """
        if self._provider_error is not None:
            return False, self._provider_error
        try:
            _ = self._engine.provider  # 构造（不推理）：配置非法/模型文件不可用在此暴露
        except Exception as exc:  # EngineError（包装 EmbeddingError）/ EmbeddingError
            reason = embedding_failure_reason(exc) or redact_text(
                f"{type(exc).__name__}: {exc}"
            )
            return False, reason
        return True, None

    def _observe_provider(
        self, call: Callable[[], _T], *, recovered: Callable[[_T], bool] | None = None
    ) -> _T:
        """执行一次可能触碰 provider 的 engine 调用，记录/清除 provider 故障记忆。

        ``recovered`` 判定"这次调用算不算 provider 正常"（缺省：没抛异常就算）；
        ``search`` 传 ``not trace.degraded``——向量通道降级时 provider 其实没恢复。
        """
        try:
            result = call()
        except Exception as exc:
            reason = embedding_failure_reason(exc)
            if reason is not None:
                self._provider_error = reason
                logger.warning("embedding provider 故障：%s", reason)
            raise
        if recovered is None or recovered(result):
            self._provider_error = None
        return result

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
