"""查询审计的写入侧（TASK-084 §A，补 TASK-064 漏建的 ``audit.py``）。

职责只有一件事：把一次 ``/api/query/*`` 的结果**如实**落进 ``zace-meta.db`` 的
``query_audit`` 表。读取与聚合在 :meth:`zace_service.metadb.MetaDB.usage_summary`
与 ``routers/ops.py``（TASK-064 已交付），本模块不重复实现。

三条硬约束（TASK-064 §C / TASK-084 §A）：

1. **绝不让检索因审计失败而失败**——两个公开入口 :func:`record_query` /
   :func:`record_query_error` 都**不抛异常**：内部 try/except 兜底，失败只记 WARN。
   审计是旁路：记不上账不该让用户拿不到检索结果（单测钉住这一点）。
2. **不存源码内容**——只落 ``id/path/lines/tier/score``（Module/04 §8 冻结"不含源码内容"），
   见 :func:`evidence_meta`。
3. **脱敏**——``query`` 文本与失败摘要都过 :func:`zace_service.logging.redact_text`，
   **在写库之前**完成（不是只在日志层）：用户可能把 API key 粘进查询框，落库即留痕。

口径（"数字可比"的前提，只写在这里，各 handler 不再各写一套）：

- ``latency_ms`` 只包住检索/组装那一段（``EngineManager.search``），**不含**懒重扫与渲染，
  与 TASK-064 §C-3 一致；
- ``mode`` 取 ``fast``（``/api/query/search``）/ ``deep``（``/api/query/ask``），
  与 ``metadb.py`` 的 DDL 注释（``-- fast | deep``）及 WebUI 的 ``fast | deep`` 词汇一致；
  ``ask`` 另有 ``degraded=true`` 标记 Phase 2 的降级包（D-26）。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from zace_service.logging import get_logger, redact_text
from zace_service.metadb import MetaDB

__all__ = [
    "EVIDENCE_FIELDS",
    "MODE_ASK",
    "MODE_SEARCH",
    "evidence_meta",
    "redact_query_text",
    "record_query",
    "record_query_error",
]

logger = get_logger("zace_service.audit")

#: 两个端点的审计 ``mode``（DDL 注释冻结：``fast | deep``）。
MODE_SEARCH = "fast"
MODE_ASK = "deep"

#: ``evidence_json`` 的允许字段（Module/04 §8：**不含源码内容**）。
EVIDENCE_FIELDS: tuple[str, ...] = ("id", "path", "lines", "tier", "score")

#: 常见 API Key 的**裸串**形态（前面没有 ``api_key=`` 这类键名，``redact_text`` 的既有规则
#: 罩不住）。用户完全可能把 key 直接粘进查询框，而查询文本要落 ``query_audit``——于是本模块
#: 自己再加一道：``zace_`` 是本服务签发的 API Key（``auth.TOKEN_PREFIX``），``sk-`` 是
#: embedding 供应商的 key（OpenAI-compatible 家族，见 ``core/embedding/api.py``）。
#:
#: 为什么不直接改 :func:`zace_service.logging.redact_text`：那会改到本卡文件所有权清单外的
#: 公共模块（对所有日志/响应的脱敏面生效），已在执行记录的"未决问题"里向编排者提出。
_BARE_SECRET_RE = re.compile(r"\b(?:zace_|sk-)[A-Za-z0-9_\-]{8,}")


def redact_query_text(text: str) -> str:
    """审计文本脱敏（``redact_text`` + 裸 key 兜底）；**在写库前**调用。"""
    return _BARE_SECRET_RE.sub("***", redact_text(text))


def evidence_field_names() -> Sequence[str]:
    """``evidence_json`` 的字段名（冻结字段的自证入口；测试直接断言实现与之一致）。"""
    return EVIDENCE_FIELDS


def evidence_meta(pack: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
    """``ContextPack`` → evidence 元数据（**只取** :data:`EVIDENCE_FIELDS`）。

    ``evidence`` 与 ``docs`` 共用 E 编号空间（D-21），编号即装填顺序，因此合并后按编号排序
    才是真正的"最相关在前"（与 :func:`zace_service.packmeta.evidence_summary` 同一口径）。
    """
    items = [*(getattr(pack, "evidence", None) or ()), *(getattr(pack, "docs", None) or ())]
    items.sort(key=_evidence_order)
    if limit is not None:
        items = items[:limit]
    return [
        {
            "id": item.id,
            "path": item.path,
            "lines": list(item.lines) if item.lines is not None else None,
            "tier": item.evidence_tier,
            "score": item.score,
        }
        for item in items
    ]


def record_query(
    db: MetaDB | None,
    *,
    project_id: str,
    mode: str,
    query: str,
    pack: Any,
    latency_ms: float,
    degraded: bool = False,
    user_id: str | None = None,
) -> None:
    """把一次**成功返回**的查询落库（旁路：任何失败只记 WARN，不影响检索）。

    字段全部取自 ``pack`` / 调用方给出的**真实值**，不编造；``citation_coverage`` 一律留
    ``None``：Phase 3 之前 ``ask`` 走降级包（D-26），根本没有 citation 可言——
    "尚未测量"不是 0（TASK-064 §A 的诚实性纪律）。
    """
    if db is None:
        return
    try:
        budget = getattr(pack, "budget", None)
        db.record_query(
            project_id=project_id,
            mode=mode,
            query=redact_query_text(query),
            latency_ms=_millis(latency_ms),
            answerable=bool(pack.answerable),
            confidence=pack.confidence,
            degraded=bool(degraded),
            evidence_count=len(getattr(pack, "evidence", None) or ()),
            docs_count=len(getattr(pack, "docs", None) or ()),
            used_tokens=int(budget.used_tokens) if budget is not None else 0,
            citation_coverage=None,
            evidence=evidence_meta(pack),
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001 - 旁路：任何失败都不得让检索失败
        _warn_swallowed(project_id, mode, exc)


def record_query_error(
    db: MetaDB | None,
    *,
    project_id: str,
    mode: str,
    query: str,
    latency_ms: float,
    reason: str,
    user_id: str | None = None,
) -> None:
    """把一次**没走到检索结果**的请求落库（业务失败与未预期异常共用）。

    为什么失败路径也要记（TASK-084 §B）：不记的话 ``usage.failed`` 恒为 0，
    "失败次数"这个数就成了谎话——与 TASK-062 对索引统计的口径一致（成功与失败都落）。

    ``answerable`` 留 ``None`` 表示"没走到判定那一步"（与 ``False``"证据不足"是两件事），
    配合 ``degraded=True`` 归入 :meth:`MetaDB.usage_summary` 的 ``failed`` 计数。
    """
    if db is not None:
        try:
            db.record_query(
                project_id=project_id,
                mode=mode,
                query=redact_query_text(query),
                latency_ms=_millis(latency_ms),
                answerable=None,
                confidence=None,
                degraded=True,
                evidence_count=0,
                docs_count=0,
                used_tokens=0,
                citation_coverage=None,
                evidence=(),
                user_id=user_id,
            )
        except Exception as exc:  # noqa: BLE001 - 旁路
            _warn_swallowed(project_id, mode, exc)
    _log_failure(project_id, mode, reason)


def _log_failure(project_id: str, mode: str, reason: str) -> None:
    """失败摘要进日志（**脱敏后**：provider 报错可能带 key 片段）。"""
    try:
        logger.warning(
            "查询审计：%s（mode=%s）失败一次：%s", project_id, mode, redact_query_text(reason)
        )
    except Exception:  # noqa: BLE001 - 连日志都不该拖垮请求 # pragma: no cover
        pass


def _warn_swallowed(project_id: str, mode: str, exc: BaseException) -> None:
    try:
        logger.warning(
            "查询审计写入失败（检索照常）：%s（mode=%s）→ %s",
            project_id,
            mode,
            redact_query_text(f"{type(exc).__name__}: {exc}"),
        )
    except Exception:  # noqa: BLE001 # pragma: no cover
        pass


def _millis(latency_ms: float) -> int:
    """毫秒耗时 → 非负整数（``query_audit.latency_ms`` 是 INTEGER NOT NULL）。"""
    try:
        return max(0, int(round(float(latency_ms))))
    except (TypeError, ValueError):  # pragma: no cover - 调用方恒传数字
        return 0


def _evidence_order(item: Any) -> int:
    raw = str(getattr(item, "id", ""))[1:]
    return int(raw) if raw.isdigit() else 0
