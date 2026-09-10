"""``/api/query/*`` 查询 API（TASK-032；CF-05 的 query 段 + D-21 服务端渲染 + D-26 降级）。

两个端点：

| 端点 | 语义 |
|---|---|
| ``POST /api/query/search`` | Fast 模式：检索 + 组装 + **服务端渲染 Markdown** |
| ``POST /api/query/ask`` | Deep 模式：Phase 2 **一律走 D-26 降级包**（LLM 属 Phase 3），返回 200 |

薄壳纪律（D-34）：本文件不出现检索/组装/渲染逻辑——检索走 ``EngineManager.search``
（转调 core ``search_with_trace``），渲染走 ``zace_core.contextpack.render_markdown``（D-21：
渲染规则与合同强耦合，只此一份）。

错误语义（CF-05 信封）：

- ``query`` 空白或 >2000 字符 → 400 ``invalid_query``；
- ``maxTokens`` ∉ (0, 20000] → 400 ``invalid_max_tokens``；
- 项目不存在 → 404 ``project_not_found``（含 R37 的"省略 projectId"解析）；
- **空索引（``chunks == 0``）→ 三岔口（TASK-035 §B，根因优先）**：
  1. provider 不可用（503 ``embedding_unavailable``，§A 探测）——**优先于**后两者；
  2. 从未同步过（账本为空）→ 409 ``index_in_progress``，指引"先同步"；
  3. 有账本但索引为空（上次索引失败）→ 500 ``index_failed``，**不得**再说"请先同步"
     （用户会以为没上传过，从而陷入"同步→重试"的无限循环）；
- ``ask`` **绝不 500**：Phase 2 没有 LLM，``Engine.ask()`` 抛 ``NotImplementedError``，
  本实现不调用它，而是返回带 ``status="degraded"`` 的检索包（诚实降级，D-26）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from zace_core.contextpack import render_markdown

from zace_service.deps import get_engine_manager, get_settings, require_project_id
from zace_service.errors import (
    CODE_EMBEDDING_UNAVAILABLE,
    PROVIDER_UNAVAILABLE_HINT,
    ApiError,
)
from zace_service.logging import get_logger, redact_text
from zace_service.packmeta import evidence_summary, pack_meta
from zace_service.runtime import EngineManager

router = APIRouter(tags=["query"])

logger = get_logger("zace_service.routers.query")

#: ``query`` / ``question`` 的最大字符数（卡内冻结；防超长输入拖垮检索）。
MAX_QUERY_CHARS = 2000
#: ``maxTokens`` 的默认值与上限（卡内冻结：(0, 20000]）。
DEFAULT_MAX_TOKENS = 10_000
MAX_MAX_TOKENS = 20_000

#: ``ask`` 的降级说明（D-26 要求写清"为什么不是答案"与"包可以直接用"）。
DEGRADED_NOTICE = (
    "Deep 模式（LLM 总结）尚未接入（Phase 3）；以下为检索与组装结果，可直接作为上下文使用。"
)


class SearchRequest(BaseModel):
    """``POST /api/query/search`` 的请求体（CF-05 + 可选的 ``includePack``）。"""

    projectId: str | None = None
    checkpointId: str | None = None
    query: str = ""
    maxTokens: int = DEFAULT_MAX_TOKENS
    includePack: bool = False


class AskRequest(BaseModel):
    """``POST /api/query/ask`` 的请求体（CF-05）。"""

    projectId: str | None = None
    checkpointId: str | None = None
    question: str = ""


@router.post("/api/query/search")
def search(payload: SearchRequest, request: Request) -> dict[str, Any]:
    """Fast 模式检索：返回服务端渲染的 Markdown 与 ``meta``（CF-05 SearchResponse）。"""
    manager = get_engine_manager(request)
    project_id = require_project_id(request, payload.projectId)
    query = _require_query(payload.query)
    _require_max_tokens(payload.maxTokens)
    _require_index(manager, project_id)

    rescan = _rescan_before_query(manager, request, project_id)
    trace = manager.search(project_id, query, payload.maxTokens)
    meta = pack_meta(
        trace.pack,
        project_id=project_id,
        channels=trace.channels_used,
        degraded=trace.degraded,
        # core 的降级原因会带上 provider 原始报错（TASK-035 §A 的同一纪律：secret 不进响应）。
        reason=redact_text(trace.degraded_reason) if trace.degraded_reason else None,
        candidate_count=trace.candidate_count,
        checkpoint_id=payload.checkpointId,
        include_pack=payload.includePack,
    )
    meta["freshness"] = _with_rescan_signal(meta["freshness"], rescan)
    return {"markdown": render_markdown(trace.pack), "meta": meta}


@router.post("/api/query/ask")
def ask(payload: AskRequest, request: Request) -> dict[str, Any]:
    """Deep 模式：Phase 2 固定返回**降级包**（200 + ``status="degraded"``），绝不 500。"""
    manager = get_engine_manager(request)
    project_id = require_project_id(request, payload.projectId)
    question = _require_query(payload.question, field="question", code="invalid_question")
    _require_index(manager, project_id)

    rescan = _rescan_before_query(manager, request, project_id)
    trace = manager.search(project_id, question, DEFAULT_MAX_TOKENS)
    pack = trace.pack
    meta = pack_meta(
        pack,
        project_id=project_id,
        channels=trace.channels_used,
        degraded=True,
        reason=DEGRADED_NOTICE,
        candidate_count=trace.candidate_count,
        checkpoint_id=payload.checkpointId,
    )
    meta["freshness"] = _with_rescan_signal(meta["freshness"], rescan)
    return {
        "status": "degraded",
        "answer": f"{DEGRADED_NOTICE}\n\n{render_markdown(pack)}",
        "evidenceSummary": evidence_summary(pack),
        "meta": meta,
    }


# --------------------------------------------------------------------------- 懒重扫（TASK-034 §C）


def _rescan_before_query(
    manager: EngineManager, request: Request, project_id: str
) -> str | None:
    """本地模式：检索前做一次增量懒重扫（TASK-034 §C）；返回**失败摘要**（成功/跳过 → None）。

    纪律（卡内 §C）：

    - **只在本地模式**且间隔 > 0 时；远端模式走客户端上传，不适用；
    - 重扫**失败不得让检索失败**：记日志 + 把失败摘要交给调用方写进 ``freshness``
      （作为 ``staleFiles`` 的补充信号，D-30 如实报告），照常返回既有索引的检索结果。
    """
    settings = get_settings(request)
    if not settings.local_mode:
        return None
    try:
        manager.rescan_if_due(project_id, min_interval_s=settings.local_rescan_interval_s)
    except Exception as exc:
        reason = redact_text(f"{type(exc).__name__}: {exc}")
        logger.warning("懒重扫失败（检索照常）：%s → %s", project_id, reason)
        return reason
    return None


def _with_rescan_signal(freshness: dict[str, Any], error: str | None) -> dict[str, Any]:
    """把懒重扫结果附在 ``meta.freshness`` 上（仅失败时多一个键；成功/跳过 → 原样）。

    为什么不改 CF-03：``freshness`` 的子键属 CF-03（``additionalProperties: false``），
    改 ``meta.pack`` 的形状会破契约；这里是**服务端 meta** 的附加子键（TASK-034 §C 要求），
    只在重扫失败时出现，且不改变任何既有字段的含义。
    """
    if error is None:
        return freshness
    return {**freshness, "rescanError": error}


# --------------------------------------------------------------------------- 校验


def _require_query(raw: str, *, field: str = "query", code: str = "invalid_query") -> str:
    value = raw.strip()
    if not value:
        raise ApiError(code, f"{field} 不能为空", 400)
    if len(raw) > MAX_QUERY_CHARS:
        raise ApiError(code, f"{field} 过长（上限 {MAX_QUERY_CHARS} 字符，收到 {len(raw)}）", 400)
    return value


def _require_max_tokens(value: int) -> None:
    if value <= 0 or value > MAX_MAX_TOKENS:
        raise ApiError(
            "invalid_max_tokens",
            f"maxTokens 必须落在 (0, {MAX_MAX_TOKENS}] 区间，收到 {value}",
            400,
        )


def _require_index(manager: EngineManager, project_id: str) -> None:
    """空索引（``chunks == 0``）→ 三岔口（TASK-035 §B；根因优先）。

    | 情况 | 响应 | 为什么 |
    |---|---|---|
    | provider 不可用 | 503 ``embedding_unavailable`` | 根因；否则客户端会去重试"同步"而永远好不了 |
    | 从未同步（账本空） | 409 ``index_in_progress`` | 现状正确：确实该先同步 |
    | 有账本但 chunks=0 | 500 ``index_failed`` | 上次索引失败；说"请先同步"是错误指引 |

    索引非空时不在这里拦：provider 真坏了会在检索链里以 §A 的 503 如实报出（
    不靠"故障记忆"提前拒绝——记忆可能是陈旧的，会阻断已经恢复后的检索）。
    索引进行中（TASK-034 的后台索引）落到第三岔，其 message 带进度（D-30 诚实性）。
    """
    status = manager.sync_status(project_id)
    if status["chunks"] > 0:
        return

    ok, reason = manager.provider_health()
    if not ok:
        raise ApiError(
            CODE_EMBEDDING_UNAVAILABLE,
            f"embedding provider 当前不可用（{reason}），索引无法建立："
            f"这不是「尚未同步」，请先修复依赖。{PROVIDER_UNAVAILABLE_HINT}",
            503,
        )

    ledger_files = len(manager.sync_state(project_id).files)
    if ledger_files == 0:
        raise ApiError(
            "index_in_progress",
            "该项目尚未索引（chunks=0，且没有任何已上传文件）：请先同步"
            "（client 会在 tool call 时自动上传，或调用 POST /api/sync/batch-upload），"
            "索引完成后再查询。",
            409,
        )
    progress = _progress_hint(manager, project_id)
    raise ApiError(
        "index_failed",
        f"该项目已收到 {ledger_files} 个文件但索引为空（chunks=0）：上次上传/索引未成功{progress}。"
        "请检查服务端日志（provider/解析错误会记在那里）后重新同步。",
        500,
    )


def _progress_hint(manager: EngineManager, project_id: str) -> str:
    """TASK-034 的索引进度提示（旧版本/非本地模式无进度时返回空串）。"""
    reader = getattr(manager, "index_progress", None)
    if not callable(reader):  # pragma: no cover - TASK-034 落地后恒为真
        return ""
    progress = reader(project_id)
    state = getattr(progress, "state", None)
    if state != "running":
        return f"，当前索引状态：{state}" if state else ""
    return (
        f"；当前仍在索引中（已处理 {getattr(progress, 'processed_files', 0)}/"
        f"{getattr(progress, 'total_files', 0)} 个文件），请稍后重试"
    )


__all__ = [
    "AskRequest",
    "DEGRADED_NOTICE",
    "DEFAULT_MAX_TOKENS",
    "MAX_MAX_TOKENS",
    "MAX_QUERY_CHARS",
    "SearchRequest",
    "ask",
    "search",
]
