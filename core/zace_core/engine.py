"""``ContextEngine`` 装配（TASK-013 / CF-07 / D-29）。

把 TASK-007（索引流水线）、TASK-010/011（检索与图扩展/rerank）、TASK-012（组装）装配成
进程内引擎；Phase 2 的 service 与 Phase 3 的 ask 复用同一装配，不另写一份检索链。

设计依据：``docs/design/Module/06-服务化与部署.md`` §1（core 纯库边界：CLI 是调试形态）、
``docs/design/Module/05-MCP与同步.md`` §3.4（D-29 project identity）；
契约：``core/zace_core/interfaces.py`` 的 ``ContextEngine``（CF-07）与
``docs/contracts/contextpack.schema.json``（CF-03）。

卡内实现口径（TASK-013，"同步调用"）：

- ``ingest`` / ``resolve_project`` / ``sync_status`` / ``search`` / ``delete_project`` 为
  同步调用；异步 job 与进度上报是 Phase 2 service 的事，本卡 ``ingest`` 直接跑完流水线并返回
  一个 job id 字符串（形态与 CF-07 一致，语义是"已完成"）。
- ``ask`` 抛 ``NotImplementedError``（Phase 3 / Module/04），不静默返回空包。
- **本卡扩展（不在 CF-07 内）**：``Engine.open`` 之外的本地目录辅助入口（``resolve_repo`` /
  ``ingest_repo`` / ``search_with_trace`` / ``project_dir``）供 CLI 与测试使用；
  它们只做"仓库 → ChangeSet"的本地适配，检索链与契约方法完全共用。

D-29 project identity（本卡实现基础版）：

```text
有 git remote → identity_key = sha256(remote_url + repo 在 git 根内的相对路径)
无 git        → identity_key = sha256(canonical 绝对路径)
project_id    = sha256(identity_key) 前 16 位十六进制
数据目录      = {data_root}/projects/{project_id}/
```

冻结接口 ``resolve_project(identity_key, display_name)`` 由调用方给出 identity_key（CF-07 原样）；
D-29 的计算放在模块级 :func:`repo_identity`，CLI 走 :meth:`Engine.resolve_repo` 组合两者。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path

from zace_core.contextpack import (
    MODE_FAST,
    BudgetConfig,
    assemble,
    budget_for,
    collect_index_signals,
)
from zace_core.embedding import EmbeddingConfig, create_provider
from zace_core.hashing import blob_hash, file_content_hash
from zace_core.interfaces import ContextEngine, EmbeddingProvider
from zace_core.pipeline import DirectorySource, Indexer, IngestReport
from zace_core.retrieval import RecallLimits, recall
from zace_core.retrieval.expand import ExpansionLimits, expand
from zace_core.retrieval.rerank import collect_signals, rerank
from zace_core.storage import Store
from zace_core.types import (
    AskResult,
    BlobInput,
    Candidate,
    ChangeSet,
    ContextPack,
    ProjectHandle,
    SyncStatus,
)
from zace_core.vectors import VectorStore

__all__ = [
    "DATA_ROOT_ENV",
    "DEFAULT_DATA_ROOT",
    "PROJECTS_DIRNAME",
    "PROJECT_META_FILENAME",
    "SCAN_MANIFEST_FILENAME",
    "Engine",
    "EngineError",
    "RepoIdentity",
    "SearchTrace",
    "git_remote_url",
    "plan_scan",
    "project_dir_for",
    "project_id_for",
    "repo_identity",
    "resolve_data_root",
]

#: 默认数据根（Module/06 §1：core 只管 ``projects/``）。
DEFAULT_DATA_ROOT = Path.home() / ".zace"
#: 覆盖数据根的环境变量（CLI ``--data`` 优先）。
DATA_ROOT_ENV = "ZACE_DATA_ROOT"
#: 项目目录所在子目录（D-03）。
PROJECTS_DIRNAME = "projects"
#: 项目元数据文件名（本卡扩展：identity_key/display_name 的落盘记录，也是"创建"标记）。
PROJECT_META_FILENAME = "project.json"
#: 本地扫描状态文件名（本卡扩展：CLI 侧增量对账；Phase 2 由 client 的 scan 状态取代）。
SCAN_MANIFEST_FILENAME = "scan_manifest.json"

_PROJECT_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_GIT_TIMEOUT_S = 5.0


class EngineError(RuntimeError):
    """引擎的使用/配置错误（CLI 映射为退出码 1）。"""


# ---------------------------------------------------------------------------
# D-29 project identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RepoIdentity:
    """一个本地仓库目录的 D-29 身份（``repo_path`` 是它在 git 根内的相对路径）。"""

    identity_key: str
    display_name: str
    remote_url: str | None = None
    git_root: str | None = None
    repo_path: str = ""


def project_id_for(identity_key: str) -> str:
    """``project_id = sha256(identity_key)`` 前 16 位十六进制。"""
    if not identity_key:
        raise EngineError("identity_key 不能为空")
    return hashlib.sha256(identity_key.encode("utf-8")).hexdigest()[:16]


def project_dir_for(data_root: str | Path, project_id: str) -> Path:
    """``{data_root}/projects/{project_id}/``；顺带拦掉路径穿越的非法 id。"""
    if not _PROJECT_ID_RE.match(project_id):
        raise EngineError(f"非法 project_id：{project_id!r}（期望 16 位小写十六进制）")
    return Path(data_root).expanduser() / PROJECTS_DIRNAME / project_id


def resolve_data_root(data: str | Path | None = None, env: Mapping[str, str] | None = None) -> Path:
    """数据根解析顺序：显式参数 → ``$ZACE_DATA_ROOT`` → ``~/.zace``。"""
    if data is not None:
        return Path(data).expanduser()
    source = os.environ if env is None else env
    raw = source.get(DATA_ROOT_ENV)
    return Path(raw).expanduser() if raw else DEFAULT_DATA_ROOT


def _git(args: list[str], cwd: Path) -> str | None:
    """跑一条 git 命令；git 缺失/超时/非仓库一律返回 ``None``（D-29 的"无 git"分支）。"""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def git_remote_url(root: str | Path) -> str | None:
    """仓库的 git remote URL：优先 ``origin``，否则取第一个 remote；无 git/无 remote → ``None``。"""
    path = Path(root).expanduser()
    origin = _git(["config", "--get", "remote.origin.url"], path)
    if origin:
        return origin
    names = _git(["remote"], path)
    if not names:
        return None
    first = names.splitlines()[0].strip()
    if not first:
        return None
    return _git(["config", "--get", f"remote.{first}.url"], path)


def repo_identity(root: str | Path) -> RepoIdentity:
    """按 D-29 计算仓库身份（有 remote 用 remote+相对路径，无则用绝对路径 hash）。"""
    path = Path(root).expanduser().resolve()
    git_root = _git(["rev-parse", "--show-toplevel"], path)
    remote = git_remote_url(path) if git_root else None
    if remote and git_root:
        resolved_git_root = Path(git_root).expanduser().resolve()
        try:
            relative = path.relative_to(resolved_git_root).as_posix()
        except ValueError:  # show-toplevel 不是 path 的祖先（符号链接等）：退回仓库自身
            relative = ""
        material = remote + (relative if relative != "." else "")
        return RepoIdentity(
            identity_key=hashlib.sha256(material.encode("utf-8")).hexdigest(),
            display_name=path.name,
            remote_url=remote,
            git_root=str(resolved_git_root),
            repo_path="" if relative == "." else relative,
        )
    return RepoIdentity(
        identity_key=hashlib.sha256(str(path).encode("utf-8")).hexdigest(),
        display_name=path.name,
        remote_url=None,
        git_root=str(Path(git_root).resolve()) if git_root else None,
    )


# ---------------------------------------------------------------------------
# 检索 trace（本卡扩展：CF-03 无 degraded 字段，降级信息不进 ContextPack）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SearchTrace:
    """一次 ``search`` 的完整结果（ContextPack + 通道健康度 + 候选池）。

    ``candidates`` = 送进组装的最终候选序（rerank 后），带 ``channel_ranks``——组装会做
    同符号聚合/相邻区间合并，通道命中信息在 ContextPack 里不再完整可读，E2E 断言需要它。
    """

    pack: ContextPack
    channels_used: tuple[str, ...] = ()
    degraded: bool = False
    degraded_reason: str | None = None
    candidates: tuple[Candidate, ...] = ()

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    def candidate_for(self, symbol_fqn: str) -> Candidate | None:
        """按符号 fqn 取候选（E2E 断言/Debug 用；同符号只返回候选池里的首次出现）。"""
        for candidate in self.candidates:
            if candidate.symbol_fqn == symbol_fqn:
                return candidate
        return None


class _EmptySource:
    """无本地目录绑定的占位 source（service 形态：内容全在 ChangeSet 里）。

    ``full_reparse`` 需要枚举文件；ChangeSet-only 调用下没有可枚举的本地文件，
    因此返回空清单（Phase 2 service 会传入自己的 blobs source）。
    """

    def read(self, path: str) -> bytes:
        raise FileNotFoundError(path)

    def list_files(self) -> tuple[str, ...]:
        return ()


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class Engine:
    """``ContextEngine`` 的过程化实现（per 进程；进程内单写者假设，同 TASK-001/009）。"""

    def __init__(
        self,
        data_root: str | Path,
        *,
        provider: EmbeddingProvider | None = None,
        embedding_config: EmbeddingConfig | None = None,
        limits: RecallLimits | None = None,
        expansion_limits: ExpansionLimits | None = None,
    ) -> None:
        self._data_root = Path(data_root).expanduser()
        self._provider = provider
        self._embedding_config = embedding_config
        self._limits = limits or RecallLimits()
        self._expansion_limits = expansion_limits or ExpansionLimits()
        self._repo_roots: dict[str, Path] = {}

    # ------------------------------------------------------------------ 生命周期

    @classmethod
    def open(
        cls,
        data_root: str | Path,
        *,
        provider: EmbeddingProvider | None = None,
        embedding_config: EmbeddingConfig | None = None,
    ) -> Engine:
        """打开引擎（``data_root`` 下的 ``projects/`` 按需创建；provider 懒构造）。"""
        return cls(
            data_root,
            provider=provider,
            embedding_config=embedding_config
            if embedding_config is not None
            else EmbeddingConfig.from_env(),
        )

    def close(self) -> None:
        """释放引擎持有的资源（provider 句柄；Store/VectorStore 是 per-call 打开的）。"""
        self._repo_roots.clear()

    def __enter__(self) -> Engine:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def data_root(self) -> Path:
        return self._data_root

    @property
    def provider(self) -> EmbeddingProvider:
        """embedding provider（懒构造：默认本地 ONNX，D-44）。"""
        if self._provider is None:
            try:
                self._provider = create_provider(self._embedding_config)
            except Exception as exc:  # EmbeddingConfigError 等配置类错误显式暴露
                raise EngineError(
                    f"embedding provider 不可用：{type(exc).__name__}: {exc}"
                ) from exc
        return self._provider

    # ------------------------------------------------------------------ 项目（CF-07）

    def project_dir(self, project_id: str) -> Path:
        """项目数据目录 ``{data_root}/projects/{project_id}/``（本卡扩展，供 CLI/测试）。"""
        return project_dir_for(self._data_root, project_id)

    def resolve_project(self, identity_key: str, display_name: str = "") -> ProjectHandle:
        """幂等解析/创建项目（D-29：identity_key 由调用方给出）。"""
        project_id = project_id_for(identity_key)
        directory = self.project_dir(project_id)
        directory.mkdir(parents=True, exist_ok=True)
        meta_path = directory / PROJECT_META_FILENAME
        created = not meta_path.exists()
        if created:
            meta = {
                "project_id": project_id,
                "identity_key": identity_key,
                "display_name": display_name,
                "created_at": int(time.time()),
            }
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        return ProjectHandle(project_id=project_id, created=created)

    def resolve_repo(self, root: str | Path) -> tuple[ProjectHandle, RepoIdentity]:
        """本地仓库目录 → (项目句柄, D-29 身份)，并绑定该目录供后续 ``ingest`` 使用。"""
        identity = repo_identity(root)
        handle = self.resolve_project(identity.identity_key, identity.display_name)
        self._repo_roots[handle.project_id] = Path(root).expanduser().resolve()
        return handle, identity

    def ingest(self, project_id: str, changes: ChangeSet) -> str:
        """写入变更集并完成索引（本卡同步语义），返回 job id（已完成的 job）。"""
        self._ingest(project_id, changes, full=False)
        return f"job-sync-{uuid.uuid4().hex[:12]}"

    def ingest_repo(self, project_id: str, root: str | Path, *, full: bool = False) -> IngestReport:
        """本地目录摄入（CLI 入口）：扫描 → 与上次扫描对账 → 索引增量 → 落扫描状态。"""
        repo = Path(root).expanduser().resolve()
        if not repo.is_dir():
            raise EngineError(f"仓库路径不是目录：{repo}")
        self._repo_roots[project_id] = repo
        scan = plan_scan(repo, self.read_manifest(project_id))
        report = self._ingest(project_id, scan.changes, full=full)
        if scan.errors:
            report = replace(report, errors=report.errors + scan.errors)
        self.write_manifest(project_id, repo, scan.hashes)
        return report

    def sync_status(self, project_id: str) -> SyncStatus:
        """索引现状（Phase 1 全同步：``pending_jobs`` 恒 0、``indexing_files`` 恒空）。"""
        with Store.open(self.project_dir(project_id)) as store:
            counts = store.counts()
            freshness = store.freshness()
        return SyncStatus(
            project_id=project_id,
            files_indexed=counts["files"],
            chunks=counts["chunks"],
            symbols=counts["symbols"],
            edges=counts["edges"],
            pending_jobs=0,
            indexing_files=(),
            last_indexed_at=freshness.indexed_at,
        )

    def search(self, project_id: str, query: str, max_tokens: int = 10_000) -> ContextPack:
        """Fast 模式：检索 + 组装（TASK-010 → 011 → 012），不调 LLM。"""
        return self.search_with_trace(project_id, query, max_tokens).pack

    def ask(self, project_id: str, question: str) -> AskResult:
        """Deep 模式：Phase 3（Module/04 AnswerProvider）实现，本卡不提供。"""
        raise NotImplementedError(
            "ask（Deep 模式）属 Phase 3（Module/04 AnswerProvider）；"
            "本版本请用 search 取 ContextPack 后自行交给调用方 LLM。"
        )

    def delete_project(self, project_id: str) -> None:
        """级联删除（D-03：整个项目目录 rm -rf，含 index.db / vectors / 扫描状态）。"""
        directory = self.project_dir(project_id)
        self._repo_roots.pop(project_id, None)
        if directory.exists():
            shutil.rmtree(directory)

    # ------------------------------------------------------------------ 检索链（本卡扩展）

    def search_with_trace(
        self, project_id: str, query: str, max_tokens: int = 10_000
    ) -> SearchTrace:
        """``search`` 的带 trace 版本（通道健康度/候选计数；CLI 与测试用）。"""
        if not query.strip():
            raise EngineError("query 不能为空")
        if max_tokens <= 0:
            raise EngineError(f"max_tokens 必须为正整数，收到 {max_tokens}")
        with self._open_project(project_id) as (store, vectors, provider):
            recalled = recall(
                store,
                query,
                provider=provider,
                vector_store=vectors,
                limits=self._limits,
            )
            expansion = expand(store, recalled.candidates, limits=self._expansion_limits)
            pool = [*recalled.candidates, *expansion.candidates]
            ranked = rerank(pool, collect_signals(store, query, pool))
            pack = assemble(
                store,
                query,
                ranked,
                flows=expansion.flows,
                freshness=store.freshness(),
                mode=MODE_FAST,
                config=self._budget(max_tokens),
                signals=collect_index_signals(store, ranked),
            )
        return SearchTrace(
            pack=pack,
            channels_used=recalled.channels_used,
            degraded=recalled.degraded,
            degraded_reason=recalled.degraded_reason,
            candidates=tuple(ranked),
        )

    # ------------------------------------------------------------------ 扫描状态（本卡扩展）

    def read_manifest(self, project_id: str) -> dict[str, str]:
        """读上次本地扫描的对账状态（缺失/损坏 → 空表 = 全量摄入）。"""
        path = self.project_dir(project_id) / SCAN_MANIFEST_FILENAME
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        files = payload.get("files") if isinstance(payload, dict) else None
        if not isinstance(files, Mapping):
            return {}
        return {str(key): str(value) for key, value in files.items()}

    def write_manifest(
        self, project_id: str, root: Path, hashes: Mapping[str, str]
    ) -> None:
        """原子写扫描状态（先写临时文件再 replace，避免半截 json 被当成有效状态）。"""
        directory = self.project_dir(project_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / SCAN_MANIFEST_FILENAME
        payload = {
            "version": 1,
            "root": str(root),
            "scanned_at": int(time.time()),
            "files": dict(sorted(hashes.items())),
        }
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)

    # ------------------------------------------------------------------ 内部

    def _budget(self, max_tokens: int) -> BudgetConfig:
        base = budget_for(MODE_FAST)
        return base if max_tokens == base.hard_cap else replace(base, hard_cap=max_tokens)

    def _source_for(self, project_id: str):
        root = self._repo_roots.get(project_id)
        return DirectorySource(root) if root is not None else _EmptySource()

    def _ingest(self, project_id: str, changes: ChangeSet, *, full: bool) -> IngestReport:
        with self._open_project(project_id) as (store, vectors, provider):
            indexer = Indexer(store, provider, vectors, self._source_for(project_id))
            return indexer.full_reparse(changes) if full else indexer.ingest(changes)

    @contextmanager
    def _open_project(
        self, project_id: str
    ) -> Iterator[tuple[Store, VectorStore, EmbeddingProvider]]:
        directory = self.project_dir(project_id)
        directory.mkdir(parents=True, exist_ok=True)
        store = Store.open(directory)
        try:
            provider = self.provider
            vectors = VectorStore.open(directory, provider.profile.dim)
        except BaseException:
            store.close()
            raise
        try:
            yield store, vectors, provider
        finally:
            vectors.close()
            store.close()


# ---------------------------------------------------------------------------
# 本地扫描（ChangeSet 构造）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ScanResult:
    changes: ChangeSet
    hashes: dict[str, str] = field(default_factory=dict)
    errors: tuple[str, ...] = ()


def plan_scan(root: str | Path, previous: Mapping[str, str]) -> _ScanResult:
    """仓库目录 + 上次扫描状态 → 增量 ``ChangeSet``（Phase 2 client 的同步逻辑本地版）。

    - ``added`` = 上次状态里没有的路径；``modified`` = content_hash 变化的路径；
    - ``deleted`` = 上次有、本次磁盘上没有的路径；
    - **未变化的文件不进 ChangeSet**（不重解析、不重嵌入）；
    - 读取失败的文件计入 ``errors`` 并从状态中剔除（下次会重试）。
    """
    source = DirectorySource(root)
    hashes: dict[str, str] = {}
    added: list[BlobInput] = []
    modified: list[BlobInput] = []
    errors: list[str] = []
    for path in source.list_files():
        try:
            data = source.read(path)
        except OSError as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
            continue
        digest = file_content_hash(data)
        hashes[path] = digest
        if previous.get(path) == digest:
            continue
        blob = BlobInput(path=path, content=data, blob_hash=blob_hash(path, data))
        (added if path not in previous else modified).append(blob)
    deleted = tuple(sorted(set(previous) - set(hashes)))
    return _ScanResult(
        changes=ChangeSet(added=tuple(added), modified=tuple(modified), deleted=deleted),
        hashes=hashes,
        errors=tuple(errors),
    )


#: 编译期自证：``Engine`` 的方法面覆盖 CF-07（``interfaces.ContextEngine``）。
_ENGINE_PROTOCOL: type[ContextEngine] = Engine
