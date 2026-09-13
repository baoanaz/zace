"""``zace-meta.db``：服务侧的账户、API Key、项目归属、索引历史与查询审计（TASK-060/061/062/064）。

**为什么单独一个库**：``~/.zace/projects/{id}/index.db`` 是 core 的（纯库纪律 D-34：core 字典里
只有 project，没有用户）；用户体系是**外壳**的概念，因此落在同级目录的 ``zace-meta.db``
（Module/06 §4-A 已声明该文件名）。

口径（本模块冻结）：

- **纯标准库**：``sqlite3`` 直写，不引 ORM、不引 pydantic-settings（与全仓风格一致）；
- **每进程一个连接表**（``threading.local``）：``sqlite3`` 连接不可跨线程共享，而 FastAPI 会把
  同步 handler 丢进线程池；因此按线程开连接，连接级别 ``WAL`` + ``foreign_keys=ON``；
- **时间一律 Unix 秒**（与全仓一致），测试用显式传入的 ``now`` 而非冻结时钟；
- **失败不影响主路径**：索引历史与查询审计都是**旁路**，调用方（``indexer`` / ``routers``）
  必须自己 try/except，不因为"记不上账"而让索引或检索失败。
"""

from __future__ import annotations

import secrets
import sqlite3
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "META_DB_FILENAME",
    "IndexRun",
    "IndexStats",
    "MetaDB",
    "QueryAuditRecord",
    "UsageSummary",
    "User",
]

#: 元数据库文件名（Module/06 §4-A：与 ``projects/`` 同级）。
META_DB_FILENAME = "zace-meta.db"

#: 每项目保留的索引历史条数（超出按 finished_at 裁掉最旧的）。
INDEX_RUN_KEEP = 500
#: 每项目保留的查询审计条数（Module/04 §8 冻结值）。
QUERY_AUDIT_KEEP = 1000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  is_local      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at   INTEGER NOT NULL,
  expires_at   INTEGER NOT NULL,
  last_seen_at INTEGER
);

CREATE TABLE IF NOT EXISTS api_tokens (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name         TEXT NOT NULL DEFAULT '',
  prefix       TEXT NOT NULL,
  token_hash   TEXT NOT NULL UNIQUE,
  created_at   INTEGER NOT NULL,
  last_used_at INTEGER,
  revoked_at   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tokens_user ON api_tokens(user_id);

CREATE TABLE IF NOT EXISTS projects (
  project_id   TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL DEFAULT '',
  created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);

CREATE TABLE IF NOT EXISTS index_runs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id      TEXT NOT NULL,
  state           TEXT NOT NULL,
  started_at      INTEGER NOT NULL,
  finished_at     INTEGER NOT NULL,
  duration_ms     INTEGER NOT NULL,
  files_total     INTEGER NOT NULL DEFAULT 0,
  files_processed INTEGER NOT NULL DEFAULT 0,
  chunks          INTEGER NOT NULL DEFAULT 0,
  errors          INTEGER NOT NULL DEFAULT 0,
  error_text      TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON index_runs(project_id, finished_at DESC);

CREATE TABLE IF NOT EXISTS query_audit (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id        TEXT NOT NULL,
  user_id           TEXT,
  mode              TEXT NOT NULL,
  query             TEXT NOT NULL,
  answerable        INTEGER,
  confidence        TEXT,
  degraded          INTEGER NOT NULL DEFAULT 0,
  latency_ms        INTEGER NOT NULL,
  evidence_count    INTEGER NOT NULL DEFAULT 0,
  docs_count        INTEGER NOT NULL DEFAULT 0,
  used_tokens       INTEGER NOT NULL DEFAULT 0,
  citation_coverage REAL,
  evidence_json     TEXT NOT NULL DEFAULT '[]',
  created_at        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_project ON query_audit(project_id, created_at DESC);
"""


@dataclass(frozen=True, slots=True)
class User:
    """账户（``is_local`` = 本地单用户模式的隐式账户，无密码可用）。"""

    id: str
    name: str
    created_at: int
    is_local: bool = False


@dataclass(frozen=True, slots=True)
class IndexRun:
    """一次索引的记录（``running`` 不落库：服务被杀不会留下永远不结束的幽灵行）。"""

    run_id: int
    project_id: str
    state: str
    started_at: int
    finished_at: int
    duration_ms: int
    files_total: int
    files_processed: int
    chunks: int
    errors: int
    error_text: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "projectId": self.project_id,
            "state": self.state,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "durationMs": self.duration_ms,
            "filesTotal": self.files_total,
            "filesProcessed": self.files_processed,
            "chunks": self.chunks,
            "errors": self.errors,
            "error": self.error_text,
        }


@dataclass(frozen=True, slots=True)
class IndexStats:
    """索引统计（``avgDurationMs`` **只统计成功的 run**——失败 run 的耗时是"失败得多快"）。"""

    total: int
    succeeded: int
    failed: int
    avg_duration_ms: int | None
    min_duration_ms: int | None
    max_duration_ms: int | None
    last_run_at: int | None
    last_state: str | None
    recent: tuple[IndexRun, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "avgDurationMs": self.avg_duration_ms,
            "minDurationMs": self.min_duration_ms,
            "maxDurationMs": self.max_duration_ms,
            "lastRunAt": self.last_run_at,
            "lastState": self.last_state,
            "recent": [run.to_json() for run in self.recent],
        }


@dataclass(frozen=True, slots=True)
class QueryAuditRecord:
    """一条查询审计（**不含源码内容**：04 §8 冻结"只存 evidence 元数据"）。"""

    query_id: int
    project_id: str
    mode: str
    query: str
    answerable: bool | None
    confidence: str | None
    degraded: bool
    latency_ms: int
    evidence_count: int
    docs_count: int
    used_tokens: int
    citation_coverage: float | None
    created_at: int

    def to_json(self) -> dict[str, Any]:
        return {
            "queryId": self.query_id,
            "projectId": self.project_id,
            "mode": self.mode,
            "query": self.query,
            "answerable": self.answerable,
            "confidence": self.confidence,
            "degraded": self.degraded,
            "latencyMs": self.latency_ms,
            "evidenceCount": self.evidence_count,
            "docsCount": self.docs_count,
            "usedTokens": self.used_tokens,
            "citationCoverage": self.citation_coverage,
            "createdAt": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class UsageSummary:
    """用量聚合（``citationCoverageAvg`` 在 LLM 接入前恒为 ``None``——"尚未测量"不是 0）。"""

    total: int
    succeeded: int
    insufficient: int
    failed: int
    avg_latency_ms: int | None
    p95_latency_ms: int | None
    confidence_distribution: Mapping[str, int]
    citation_coverage_avg: float | None
    top_queries: tuple[tuple[str, int], ...] = ()
    recent: tuple[QueryAuditRecord, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "insufficient": self.insufficient,
            "failed": self.failed,
            "avgLatencyMs": self.avg_latency_ms,
            "p95LatencyMs": self.p95_latency_ms,
            "confidenceDistribution": dict(self.confidence_distribution),
            "citationCoverageAvg": self.citation_coverage_avg,
            "topQueries": [{"query": q, "count": n} for q, n in self.top_queries],
            "recent": [record.to_json() for record in self.recent],
        }


class MetaDB:
    """``zace-meta.db`` 的访问层（每线程一个连接）。

    用法：``db = MetaDB.open(data_root / META_DB_FILENAME)``；连接按线程懒建，
    因此可以在 FastAPI 线程池与后台索引线程里直接用。
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).expanduser()
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._initialized = False

    # ------------------------------------------------------------------ 打开与连接

    @classmethod
    def open(cls, path: str | Path) -> MetaDB:
        """打开并确保 schema 就绪（幂等；并发首个请求由 ``_init_lock`` 串行）。"""
        db = cls(path)
        db._ensure_schema()
        return db

    @property
    def path(self) -> Path:
        return self._path

    def _ensure_schema(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
            self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._path), timeout=10.0, isolation_level=None)
            conn.row_factory = sqlite3.Row
            # WAL：读写并发（索引线程写 run、HTTP 线程读统计）不互相阻塞。
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=10000")
            self._local.conn = conn
        return conn

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ------------------------------------------------------------------ 账户（TASK-060）

    def create_user(
        self, name: str, password_hash: str, *, is_local: bool = False, now: int | None = None
    ) -> User:
        """创建账户（``name`` 冲突抛 :class:`sqlite3.IntegrityError`，HTTP 层转 409）。"""
        created = int(now if now is not None else time.time())
        user_id = secrets.token_hex(16)
        with self._write() as conn:
            conn.execute(
                "INSERT INTO users (id, name, password_hash, created_at, is_local)"
                " VALUES (?, ?, ?, ?, ?)",
                (user_id, name, password_hash, created, 1 if is_local else 0),
            )
        return User(id=user_id, name=name, created_at=created, is_local=is_local)

    def get_user_by_name(self, name: str) -> tuple[User, str] | None:
        """``(user, password_hash)``；不存在返回 ``None``。"""
        row = self._connect().execute(
            "SELECT id, name, password_hash, created_at, is_local FROM users WHERE name = ?",
            (name,),
        ).fetchone()
        if row is None:
            return None
        return _user(row), str(row["password_hash"])

    def get_user(self, user_id: str) -> User | None:
        row = self._connect().execute(
            "SELECT id, name, created_at, is_local FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return _user(row) if row is not None else None

    def user_count(self) -> int:
        row = self._connect().execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return int(row["n"])

    def ensure_local_user(self, name: str = "local", *, now: int | None = None) -> User:
        """取（或建）本地单用户模式的隐式账户（``is_local=1``）。

        为什么需要它：TASK-061 §B 要求 ``attach`` 把归属登记给本地用户，而
        :func:`zace_service.auth.local_user` 是**不落库的幻影**（R34）——``projects.user_id``
        有指向 ``users(id)`` 的外键，没有真实行就写不进归属。

        只在调用方已经决定要写归属时使用（即本地模式且 app 级 ``MetaDB`` 已存在，见
        ``routers/projects._claim_project``）；**不在此处建库**（R34：本地模式默认无
        ``zace-meta.db``）。
        ``password_hash`` 恒为空串：本地隐式账户**没有密码**，也不得能用密码登录
        （``verify_password`` 对非法编码串返回 ``False``）。
        """
        existing = self.get_user_by_name(name)
        if existing is not None:
            return existing[0]
        try:
            return self.create_user(name, "", is_local=True, now=now)
        except sqlite3.IntegrityError:  # 并发首次 attach：另一个线程刚建好，取回它
            raced = self.get_user_by_name(name)
            if raced is None:  # pragma: no cover - 仅当行被并发删除才会走到
                raise
            return raced[0]

    # ------------------------------------------------------------------ 会话（TASK-060）

    def create_session(self, user_id: str, *, ttl_s: int, now: int | None = None) -> str:
        created = int(now if now is not None else time.time())
        session_id = secrets.token_hex(32)
        with self._write() as conn:
            conn.execute(
                "INSERT INTO sessions (id, user_id, created_at, expires_at, last_seen_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (session_id, user_id, created, created + ttl_s, created),
            )
        return session_id

    def resolve_session(self, session_id: str, *, now: int | None = None) -> User | None:
        """有效则返回用户并刷新 ``last_seen_at``；过期则删除并返回 ``None``。"""
        current = int(now if now is not None else time.time())
        conn = self._connect()
        row = conn.execute(
            "SELECT s.user_id, s.expires_at, u.name, u.created_at, u.is_local"
            " FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        if int(row["expires_at"]) <= current:
            with self._write() as writer:
                writer.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return None
        with self._write() as writer:
            writer.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE id = ?", (current, session_id)
            )
        return User(
            id=str(row["user_id"]),
            name=str(row["name"]),
            created_at=int(row["created_at"]),
            is_local=bool(row["is_local"]),
        )

    def delete_session(self, session_id: str) -> None:
        with self._write() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    # ------------------------------------------------------------------ API Key（TASK-060）

    def create_token(
        self,
        user_id: str,
        *,
        token_hash: str,
        prefix: str,
        name: str = "",
        now: int | None = None,
    ) -> str:
        """登记一个 API Key 的哈希（明文只在创建响应里出现一次，**不落库**）。"""
        created = int(now if now is not None else time.time())
        token_id = secrets.token_hex(16)
        with self._write() as conn:
            conn.execute(
                "INSERT INTO api_tokens (id, user_id, name, prefix, token_hash, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (token_id, user_id, name, prefix, token_hash, created),
            )
        return token_id

    def list_tokens(self, user_id: str) -> list[dict[str, Any]]:
        """该用户的**有效** Key（已撤销的不列；**绝不含明文或哈希**）。"""
        rows = self._connect().execute(
            "SELECT id, name, prefix, created_at, last_used_at FROM api_tokens"
            " WHERE user_id = ? AND revoked_at IS NULL ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "prefix": str(row["prefix"]),
                "createdAt": int(row["created_at"]),
                "lastUsedAt": row["last_used_at"],
            }
            for row in rows
        ]

    def find_user_by_token_hash(
        self, token_hash: str, *, now: int | None = None
    ) -> User | None:
        """按哈希反查用户（仅有效 Key；命中即刷新 ``last_used_at``）。"""
        current = int(now if now is not None else time.time())
        row = self._connect().execute(
            "SELECT t.id, t.user_id, u.name, u.created_at, u.is_local FROM api_tokens t"
            " JOIN users u ON u.id = t.user_id"
            " WHERE t.token_hash = ? AND t.revoked_at IS NULL",
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        with self._write() as conn:
            conn.execute(
                "UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (current, row["id"])
            )
        return User(
            id=str(row["user_id"]),
            name=str(row["name"]),
            created_at=int(row["created_at"]),
            is_local=bool(row["is_local"]),
        )

    def revoke_token(self, user_id: str, token_id: str, *, now: int | None = None) -> bool:
        """软删（只撤销**自己的** Key；不存在/非本人 → ``False``）。"""
        revoked = int(now if now is not None else time.time())
        with self._write() as conn:
            cursor = conn.execute(
                "UPDATE api_tokens SET revoked_at = ?"
                " WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
                (revoked, token_id, user_id),
            )
            return cursor.rowcount > 0

    # ------------------------------------------------------------------ 项目归属（TASK-061）

    def claim_project(
        self, user_id: str, project_id: str, display_name: str = "", *, now: int | None = None
    ) -> tuple[bool, str | None]:
        """认领项目。返回 ``(ok, owner_user_id)``：``ok=False`` 时 ``owner`` 是**已有**归属者。

        幂等：同一用户重复认领同一 projectId → ``(True, user_id)``，不产生第二行。
        """
        created = int(now if now is not None else time.time())
        with self._write() as conn:
            row = conn.execute(
                "SELECT user_id FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            if row is not None:
                owner = str(row["user_id"])
                return owner == user_id, owner
            conn.execute(
                "INSERT INTO projects (project_id, user_id, display_name, created_at)"
                " VALUES (?, ?, ?, ?)",
                (project_id, user_id, display_name, created),
            )
        return True, user_id

    def owns_project(self, user_id: str, project_id: str) -> bool:
        row = self._connect().execute(
            "SELECT 1 FROM projects WHERE project_id = ? AND user_id = ?", (project_id, user_id)
        ).fetchone()
        return row is not None

    def list_projects(self, user_id: str) -> list[str]:
        rows = self._connect().execute(
            "SELECT project_id FROM projects WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [str(row["project_id"]) for row in rows]

    # ------------------------------------------------------------------ 索引历史（TASK-062）

    def record_index_run(
        self,
        project_id: str,
        *,
        state: str,
        started_at: int,
        finished_at: int,
        files_total: int = 0,
        files_processed: int = 0,
        chunks: int = 0,
        errors: int = 0,
        error_text: str | None = None,
    ) -> int:
        """写一条索引记录并裁剪到 :data:`INDEX_RUN_KEEP` 条（返回 ``run_id``）。"""
        duration_ms = max(0, int(finished_at - started_at)) * 1000
        with self._write() as conn:
            cursor = conn.execute(
                "INSERT INTO index_runs (project_id, state, started_at, finished_at,"
                " duration_ms, files_total, files_processed, chunks, errors, error_text)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    state,
                    int(started_at),
                    int(finished_at),
                    duration_ms,
                    int(files_total),
                    int(files_processed),
                    int(chunks),
                    int(errors),
                    error_text,
                ),
            )
            run_id = int(cursor.lastrowid or 0)
            conn.execute(
                "DELETE FROM index_runs WHERE project_id = ? AND id NOT IN"
                " (SELECT id FROM index_runs WHERE project_id = ?"
                "  ORDER BY finished_at DESC, id DESC LIMIT ?)",
                (project_id, project_id, INDEX_RUN_KEEP),
            )
        return run_id

    def index_stats(self, project_id: str, *, limit: int = 20) -> IndexStats:
        """聚合 + 最近 ``limit`` 条（``avgDurationMs`` **只统计 succeeded**）。"""
        conn = self._connect()
        rows = conn.execute(
            "SELECT state, duration_ms FROM index_runs WHERE project_id = ?", (project_id,)
        ).fetchall()
        succeeded = [int(row["duration_ms"]) for row in rows if row["state"] == "done"]
        failed = sum(1 for row in rows if row["state"] != "done")
        recent_rows = conn.execute(
            "SELECT * FROM index_runs WHERE project_id = ?"
            " ORDER BY finished_at DESC, id DESC LIMIT ?",
            (project_id, max(1, int(limit))),
        ).fetchall()
        last = recent_rows[0] if recent_rows else None
        return IndexStats(
            total=len(rows),
            succeeded=len(succeeded),
            failed=failed,
            avg_duration_ms=int(sum(succeeded) / len(succeeded)) if succeeded else None,
            min_duration_ms=min(succeeded) if succeeded else None,
            max_duration_ms=max(succeeded) if succeeded else None,
            last_run_at=int(last["finished_at"]) if last is not None else None,
            last_state=str(last["state"]) if last is not None else None,
            recent=tuple(_index_run(row) for row in recent_rows),
        )

    def all_index_stats(self, project_ids: Sequence[str], *, limit: int = 20) -> IndexStats:
        """跨项目汇总（当前用户的项目；``recent`` 按时间混排）。"""
        if not project_ids:
            return IndexStats(0, 0, 0, None, None, None, None, None)
        placeholders = ",".join("?" for _ in project_ids)
        params = list(project_ids)
        conn = self._connect()
        rows = conn.execute(
            f"SELECT project_id, state, duration_ms FROM index_runs"
            f" WHERE project_id IN ({placeholders})",
            params,
        ).fetchall()
        succeeded = [int(row["duration_ms"]) for row in rows if row["state"] == "done"]
        failed = sum(1 for row in rows if row["state"] != "done")
        recent_rows = conn.execute(
            f"SELECT * FROM index_runs WHERE project_id IN ({placeholders})"
            f" ORDER BY finished_at DESC, id DESC LIMIT ?",
            [*params, max(1, int(limit))],
        ).fetchall()
        last = recent_rows[0] if recent_rows else None
        return IndexStats(
            total=len(rows),
            succeeded=len(succeeded),
            failed=failed,
            avg_duration_ms=int(sum(succeeded) / len(succeeded)) if succeeded else None,
            min_duration_ms=min(succeeded) if succeeded else None,
            max_duration_ms=max(succeeded) if succeeded else None,
            last_run_at=int(last["finished_at"]) if last is not None else None,
            last_state=str(last["state"]) if last is not None else None,
            recent=tuple(_index_run(row) for row in recent_rows),
        )

    def index_runs(self, project_id: str, *, limit: int = 20) -> list[IndexRun]:
        rows = self._connect().execute(
            "SELECT * FROM index_runs WHERE project_id = ?"
            " ORDER BY finished_at DESC, id DESC LIMIT ?",
            (project_id, max(1, int(limit))),
        ).fetchall()
        return [_index_run(row) for row in rows]

    # ------------------------------------------------------------------ 查询审计（TASK-064）

    def record_query(
        self,
        *,
        project_id: str,
        mode: str,
        query: str,
        latency_ms: int,
        answerable: bool | None = None,
        confidence: str | None = None,
        degraded: bool = False,
        evidence_count: int = 0,
        docs_count: int = 0,
        used_tokens: int = 0,
        citation_coverage: float | None = None,
        evidence: Sequence[Mapping[str, Any]] = (),
        user_id: str | None = None,
        now: int | None = None,
    ) -> int:
        """写一条查询审计（``evidence`` 只存 ``{id,path,lines,tier,score}`` 元数据）。

        **调用方必须自己 try/except**：审计是旁路，记不上账不影响检索（TASK-064 §C）。
        """
        import json

        created = int(now if now is not None else time.time())
        with self._write() as conn:
            cursor = conn.execute(
                "INSERT INTO query_audit (project_id, user_id, mode, query, answerable,"
                " confidence, degraded, latency_ms, evidence_count, docs_count, used_tokens,"
                " citation_coverage, evidence_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    user_id,
                    mode,
                    query,
                    None if answerable is None else (1 if answerable else 0),
                    confidence,
                    1 if degraded else 0,
                    int(latency_ms),
                    int(evidence_count),
                    int(docs_count),
                    int(used_tokens),
                    citation_coverage,
                    json.dumps([dict(item) for item in evidence], ensure_ascii=False),
                    created,
                ),
            )
            query_id = int(cursor.lastrowid or 0)
            conn.execute(
                "DELETE FROM query_audit WHERE project_id = ? AND id NOT IN"
                " (SELECT id FROM query_audit WHERE project_id = ?"
                "  ORDER BY created_at DESC, id DESC LIMIT ?)",
                (project_id, project_id, QUERY_AUDIT_KEEP),
            )
        return query_id

    def usage_summary(
        self, project_ids: Sequence[str], *, days: int = 30, recent_limit: int = 20,
        now: int | None = None,
    ) -> UsageSummary:
        """用量聚合（``days`` 窗口；``succeeded`` = ``answerable`` 为真的次数）。"""
        if not project_ids:
            return UsageSummary(0, 0, 0, 0, None, None, {}, None)
        current = int(now if now is not None else time.time())
        since = current - max(1, int(days)) * 86400
        placeholders = ",".join("?" for _ in project_ids)
        params: list[Any] = [*project_ids, since]
        conn = self._connect()
        rows = conn.execute(
            f"SELECT answerable, confidence, latency_ms, degraded, citation_coverage, query"
            f" FROM query_audit WHERE project_id IN ({placeholders}) AND created_at >= ?",
            params,
        ).fetchall()

        total = len(rows)
        succeeded = sum(1 for row in rows if row["answerable"] == 1)
        insufficient = sum(1 for row in rows if row["answerable"] == 0)
        # "失败" = 降级且没有答案（检索链本身出错/D-26 降级），与"证据不足"是两件事。
        failed = sum(1 for row in rows if row["degraded"] == 1 and row["answerable"] is None)
        latencies = sorted(int(row["latency_ms"]) for row in rows)
        coverages = [
            float(row["citation_coverage"])
            for row in rows
            if row["citation_coverage"] is not None
        ]
        distribution: dict[str, int] = {}
        for row in rows:
            key = str(row["confidence"]) if row["confidence"] else "unknown"
            distribution[key] = distribution.get(key, 0) + 1
        counts: dict[str, int] = {}
        for row in rows:
            text = str(row["query"])
            counts[text] = counts.get(text, 0) + 1
        top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
        recent_rows = conn.execute(
            f"SELECT * FROM query_audit WHERE project_id IN ({placeholders}) AND created_at >= ?"
            f" ORDER BY created_at DESC, id DESC LIMIT ?",
            [*params, max(1, int(recent_limit))],
        ).fetchall()
        return UsageSummary(
            total=total,
            succeeded=succeeded,
            insufficient=insufficient,
            failed=failed,
            avg_latency_ms=int(sum(latencies) / len(latencies)) if latencies else None,
            p95_latency_ms=_percentile(latencies, 0.95),
            confidence_distribution=distribution,
            citation_coverage_avg=(
                round(sum(coverages) / len(coverages), 4) if coverages else None
            ),
            top_queries=tuple(top),
            recent=tuple(_audit_record(row) for row in recent_rows),
        )


def _percentile(sorted_values: Sequence[int], ratio: float) -> int | None:
    """最近秩法百分位（``sorted_values`` 必须已升序）；空序列 → ``None``。"""
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, max(0, int(round(ratio * len(sorted_values))) - 1))
    return int(sorted_values[index])


def _user(row: sqlite3.Row) -> User:
    return User(
        id=str(row["id"]),
        name=str(row["name"]),
        created_at=int(row["created_at"]),
        is_local=bool(row["is_local"]),
    )


def _index_run(row: sqlite3.Row) -> IndexRun:
    return IndexRun(
        run_id=int(row["id"]),
        project_id=str(row["project_id"]),
        state=str(row["state"]),
        started_at=int(row["started_at"]),
        finished_at=int(row["finished_at"]),
        duration_ms=int(row["duration_ms"]),
        files_total=int(row["files_total"]),
        files_processed=int(row["files_processed"]),
        chunks=int(row["chunks"]),
        errors=int(row["errors"]),
        error_text=row["error_text"],
    )


def _audit_record(row: sqlite3.Row) -> QueryAuditRecord:
    return QueryAuditRecord(
        query_id=int(row["id"]),
        project_id=str(row["project_id"]),
        mode=str(row["mode"]),
        query=str(row["query"]),
        answerable=None if row["answerable"] is None else bool(row["answerable"]),
        confidence=row["confidence"],
        degraded=bool(row["degraded"]),
        latency_ms=int(row["latency_ms"]),
        evidence_count=int(row["evidence_count"]),
        docs_count=int(row["docs_count"]),
        used_tokens=int(row["used_tokens"]),
        citation_coverage=row["citation_coverage"],
        created_at=int(row["created_at"]),
    )
