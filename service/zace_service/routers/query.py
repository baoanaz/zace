"""``/api/query/*`` 查询 API（TASK-032；CF-05 的 query 段 + D-21 服务端渲染 + D-26 降级）。

两个端点：

| 端点 | 语义 |
|---|---|
| ``POST /api/query/search`` | Fast 模式：检索 + 组装 + **服务端渲染 Markdown** |
| ``POST /api/query/ask`` | Deep 模式：**一律 200，绝不 500**（D-24 短路 / D-26 降级 / LLM） |

``ask`` 的四条分支（TASK-087 §B + TASK-088 §C/§D），**证据优先**：

| 情况 | ``status`` | ``answer`` |
|---|---|---|
| ``answerable=false`` | ``insufficient_evidence`` | 短路包（不调 LLM） |
| 未配置 ``ANSWER_*`` | ``degraded`` | 前置说明 ＋ 渲染包 |
| 已配置但调用失败/超时 | ``degraded`` | 故障说明 ＋ 渲染包 |
| 成功 | ``answered`` | LLM 答案（已回验引用） |

短路包含 ``bestEffortContext`` / ``missingEvidence`` / ``nextQueries`` 三个键（D-24）。

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
- ``ask`` **绝不 500**：四种情况各自返回可用的 200 响应（D-24 短路 + D-26 降级 + TASK-088 LLM）。
  顺序是**证据优先**：``pack.answerable == False`` → **不调 LLM**，直接返回
  ``status="insufficient_evidence"`` 的结构化包（``bestEffortContext`` / ``missingEvidence`` /
  ``nextQueries``，D-24 的"有用的失败"）；否则未配置 LLM → 降级包；调用失败/超时 → 降级包；
  成功 → ``status="answered"``（Module/04 §3/§6）。

查询审计（TASK-084，旁路）：两个端点各自被 :func:`_audited` 包住，把本次查询落进
``query_audit``（``fast`` / ``deep``）。三条纪律：**记账失败不得让检索失败**、
**不存源码内容**、**query 文本与失败摘要先脱敏再落库**——实现集中在
``zace_service.audit``，本文件只负责"把真实值交出去"。TASK-088 §E 追加三个 LLM 观测值
（``llmLatencyMs`` / ``answerTokens`` / ``citationCoverage``），未走 LLM 时一律 ``None``。
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from zace_core.contextpack import render_markdown
from zace_core.types import ContextPack

from zace_service import audit
from zace_service.answer import AnswerError, answer_question, provider_for_app
from zace_service.deps import get_engine_manager, get_settings, require_project_id
from zace_service.errors import (
    CODE_EMBEDDING_UNAVAILABLE,
    PROVIDER_UNAVAILABLE_HINT,
    ApiError,
)
from zace_service.logging import get_logger, redact_text
from zace_service.metadb import MetaDB
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
#:
#: TASK-088 起 LLM 已接入，旧文案（"Phase 3 尚未接入"）会成为假话，因此拆成两条**按原因**的
#: 诚实说明：未配置（管理员该做什么）与调用失败（模型暂时不可用）。两条都保留"包可直接用"。
DEGRADED_NOTICE = (
    "未配置总结模型（ANSWER_BASE_URL / ANSWER_API_KEY / ANSWER_MODEL）：管理员配置后重试。"
    "以下为检索与组装结果，可直接作为上下文使用。"
)
#: 已配置但调用失败（超时/网络/5xx/密钥无效/响应形状不对）时的前置说明（Module/04 §6）。
LLM_FAILED_NOTICE = (
    "总结模型暂时不可用（已重试）；以下为检索与组装结果（含 Missing Evidence），"
    "可直接作为上下文使用。"
)

#: ``ask`` 的**证据不足**说明（D-24 短路，TASK-087 §B）。
#:
#: 与 :data:`DEGRADED_NOTICE` 分开：那条说的是"没有 LLM"，这条说的是"有 LLM 也答不了"。
#: ``answerable=false`` 时二者同时成立，但调用方（Agent / 编辑器）需要的是后者的语义——
#: 该怎么补证据由返回体里的 ``missingEvidence`` / ``nextQueries`` 说清。
INSUFFICIENT_NOTICE = (
    "证据不足（answerable=false）：按 D-24 不调用 LLM，返回尽力而为的上下文与补齐建议。"
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
    # 审计上下文最先建立：这样连 "项目不存在" "query 校验失败" 这类**在解析出 projectId
    # 之前**就抛出的业务失败也能落一条（TASK-084 §B"异常路径也要记"）。
    with _audited(request, mode=audit.MODE_SEARCH, query=payload.query) as ctx:
        project_id = require_project_id(request, payload.projectId)
        ctx["projectId"] = project_id
        query = _require_query(payload.query)
        _require_max_tokens(payload.maxTokens)
        _require_index(manager, project_id)

        with _timed() as elapsed:
            ctx["elapsed"] = elapsed
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
        ctx["pack"] = trace.pack
        ctx["degraded"] = trace.degraded
        return {"markdown": render_markdown(trace.pack), "meta": meta}


@router.post("/api/query/ask")
async def ask(payload: AskRequest, request: Request) -> dict[str, Any]:
    """Deep 模式：LLM grounded 总结；未配置/失败/证据不足各自**不报错也不 500**。

    分支顺序（Module/04 §3/§6；**证据优先**：弱证据上不调 LLM）：

    | 情况 | status | answer |
    |---|---|---|
    | ``answerable=false`` | ``insufficient_evidence`` | 短路包（TASK-087，不调 LLM） |
    | 未配置 ``ANSWER_*`` | ``degraded`` | 前置说明 ＋ 渲染包 |
    | 已配置但调用失败/超时 | ``degraded`` | 故障说明 ＋ 渲染包 |
    | 成功 | ``answered`` | LLM 答案（已回验引用） |

    为什么是 ``async def``（TASK-088）：LLM 调用是**秒级阻塞 I/O**，与 core 的 CPU 型检索不同；
    把两次外呼（检索 / LLM）都放进线程池，事件循环不因一次 ask 而卡住。
    """
    manager = get_engine_manager(request)
    with _audited(request, mode=audit.MODE_ASK, query=payload.question) as ctx:
        project_id = require_project_id(request, payload.projectId)
        ctx["projectId"] = project_id
        question = _require_query(payload.question, field="question", code="invalid_question")
        _require_index(manager, project_id)

        with _timed() as elapsed:
            ctx["elapsed"] = elapsed
            rescan = await run_in_threadpool(_rescan_before_query, manager, request, project_id)
            trace = await run_in_threadpool(
                manager.search, project_id, question, DEFAULT_MAX_TOKENS
            )
        pack = trace.pack
        # 两条路都如实记 ``degraded=True``（都不含 LLM 总结），但"为什么"不同：
        # 证据不足是 D-24，无 LLM 是 D-26。审计的 answerable 由 pack.answerable 出（TASK-084）。
        insufficient = not pack.answerable
        meta = pack_meta(
            pack,
            project_id=project_id,
            channels=trace.channels_used,
            degraded=True,
            reason=INSUFFICIENT_NOTICE if insufficient else DEGRADED_NOTICE,
            candidate_count=trace.candidate_count,
            checkpoint_id=payload.checkpointId,
        )
        meta["freshness"] = _with_rescan_signal(meta["freshness"], rescan)
        ctx["pack"] = pack
        # D-24 优先：证据不足时**不调 LLM**（省一次调用，也避免模型在弱证据上硬编）。
        # 审计如实记 degraded=true（本路径不含 LLM 总结）。
        if insufficient:
            ctx["degraded"] = True
            return _insufficient_package(pack, meta)

        provider = provider_for_app(request.app)
        if provider is None:
            # L5：未配置不报错（也不是 500）——降级包 + 告诉管理员该配什么。
            ctx["degraded"] = True
            return _degraded_response(
                pack, meta, notice=DEGRADED_NOTICE, reason=DEGRADED_NOTICE
            )

        try:
            outcome = await run_in_threadpool(
                answer_question,
                provider=provider,
                settings=get_settings(request),
                pack=pack,
                question=question,
            )
        except AnswerError as exc:
            # D-26 故障矩阵：超时/API 错误/密钥无效/形状不对 → 都是降级包，永不 500。
            # 注意：**不向调用方回显 provider 原始报错**（可能含 endpoint/内部细节），
            # 只记脱敏后的日志；用户侧看到的是同一句可操作说明。
            logger.warning(
                "ask 降级（LLM %s）：%s → %s",
                exc.kind,
                project_id,
                redact_text(f"{type(exc).__name__}: {exc}"),
            )
            ctx["degraded"] = True
            meta["degradedReason"] = LLM_FAILED_NOTICE
            return _degraded_response(
                pack, meta, notice=LLM_FAILED_NOTICE, reason=LLM_FAILED_NOTICE
            )

        ctx["degraded"] = False
        meta["degraded"] = False
        meta["degradedReason"] = None
        _write_llm_observations(ctx, provider, outcome)
        return {
            "status": "answered",
            "answer": outcome.answer,
            "evidenceSummary": evidence_summary(pack),
            "meta": meta,
        }


def _insufficient_package(pack: ContextPack, meta: dict[str, Any]) -> dict[str, Any]:
    """D-24 的结构化证据不足包（Module/04 §3）：有什么给什么 + 缺什么 + 怎么补。

    - ``bestEffortContext``：``render_markdown(pack)``——搜索确实命中了些东西，别丢；
    - ``missingEvidence``：可读文本列表（与 ``### Missing Evidence`` 同形），
      调用方不必再解析 ``meta.missingEvidence`` 的结构体；
    - ``nextQueries``：组装层确定性生成的自愈查询（Module/03 §5），
      Agent 拿到就能换个措辞再问，而不是自己瞎猜；
    - ``meta``：与 ``search`` 同一份（``pack_meta``，字段集冻结）。
    """
    return {
        "status": "insufficient_evidence",
        "bestEffortContext": render_markdown(pack),
        "missingEvidence": [
            f"[{item.code}]" + (f" ({item.symbol})" if item.symbol else "") + f" {item.message}"
            for item in pack.missing_evidence
        ],
        "nextQueries": list(pack.next_queries),
        "meta": meta,
    }


def _degraded_response(
    pack: Any, meta: dict[str, Any], *, notice: str, reason: str
) -> dict[str, Any]:
    """D-26 降级包（未配置与调用失败共用；Promise.all 式复用避免两处文案漂移）。"""
    meta["degraded"] = True
    meta["degradedReason"] = reason
    return {
        "status": "degraded",
        "answer": f"{notice}\n\n{render_markdown(pack)}",
        "evidenceSummary": evidence_summary(pack),
        "meta": meta,
    }


def _write_llm_observations(ctx: _AuditContext, provider: Any, outcome: Any) -> None:
    """把 §E 的三个观测值交回审计（**真实值**，不编造）。"""
    ctx["citationCoverage"] = outcome.citation_coverage
    ctx["llmLatencyMs"] = outcome.latency_ms
    ctx["answerTokens"] = outcome.answer_tokens
    ctx["answerModel"] = getattr(provider, "model", None)


# --------------------------------------------------------------------------- 查询审计（TASK-084）


class _AuditContext(dict[str, Any]):
    """一次请求的审计暂存（handler 把真实值写进来，退出时由 :func:`_audited` 落库）。"""


#: 当前请求的审计上下文（同步路径用它；async 路径见 :func:`_audited` 的跨线程交接）。
_ACTIVE: ContextVar[_AuditContext | None] = ContextVar("zace_query_audit_ctx", default=None)


@contextmanager
def _audited(request: Request, *, mode: str, query: str) -> Iterator[_AuditContext]:
    """包住整个 handler：**成功与失败都落一条审计**（旁路，绝不抛异常）。

    为什么用 contextmanager 而不是在 ``return`` 前写一行：

    - **异常路径也必须记**（TASK-084 §B）。FastAPI 的异常处理器在路由函数之外运行，
      在那里拿不到本次请求的 query/latency 上下文；在 handler 内部捕获才能记全。
    - ``_require_index`` 的 503/409/500 与参数校验的 400 都是**业务失败**，同样计入
      ``usage.failed``——与 TASK-062 对索引统计的口径一致（成功与失败都落）。

    落库失败（``db`` 为 ``None``，或 ``db.record_query`` 抛异常）由 ``audit`` 模块内部吞掉，
    只有 **未预期的异常**（代码缺陷）会重新抛出——那本来就会变成 500，行为不变。

    跨线程池的上下文交接（TASK-088）：``ask`` 是 async handler，而本服务的
    ``@app.middleware("http")`` 是 **BaseHTTPMiddleware**，它把每个请求丢进 AnyIO 线程池执行——
    ``contextvars`` 在**不同线程**里是分开的，于是 ``run_in_threadpool`` 里建的上下文不会回到外层。
    因此除 ``contextvars`` 外，还额外把 ``ctx`` 存到 ``request.state``（对象共享，与线程无关），
    退出时按**身份比较**取回。
    """
    ctx = _AuditContext()
    ctx["started"] = time.perf_counter()
    token = _ACTIVE.set(ctx)
    request.state.zace_audit_ctx = ctx
    try:
        yield ctx
    except ApiError as exc:
        _record_failure(
            request, ctx, mode=mode, query=query, reason=f"{exc.code}: {exc.message}"
        )
        raise
    except Exception as exc:  # noqa: BLE001 - 记完账再抛，最终仍是 500 internal_error
        _record_failure(
            request, ctx, mode=mode, query=query, reason=f"{type(exc).__name__}: {exc}"
        )
        raise
    else:
        pack = ctx.get("pack")
        if pack is None:  # pragma: no cover - 只有 handler 忘了写 ctx 才会走到
            return
        audit.record_query(
            _meta_db(request),
            project_id=_project_of(ctx),
            mode=mode,
            query=query,
            pack=pack,
            **_elapsed_kwargs(ctx),
            degraded=bool(ctx.get("degraded", False)),
            answerable=ctx.get("answerable"),
            confidence=ctx.get("confidence"),
            citation_coverage=ctx.get("citationCoverage"),
            llm_latency_ms=ctx.get("llmLatencyMs"),
            answer_tokens=ctx.get("answerTokens"),
            user_id=_user_id(request),
        )
    finally:
        # 同步 handler 在同线程执行，此时 ctx 已在上面落库完毕；async handler 的跨线程副本
        # 在这里取回（身份比较，避免误取别的请求的上下文）。
        shared = getattr(request.state, "zace_audit_ctx", None)
        if isinstance(shared, _AuditContext) and shared is not ctx:
            for key, value in shared.items():
                ctx.setdefault(key, value)
        request.state.zace_audit_ctx = None
        _ACTIVE.reset(token)


@contextmanager
def _timed() -> Iterator[dict[str, float]]:
    """测"懒重扫 + ``manager.search``"的毫秒耗时（写进返回的 dict 的 ``ms`` 键）。

    口径（TASK-064 §C-3，**取代** TASK-084 §B 较宽的说法）：只包检索/组装那一段，
    **不含**服务端渲染与响应装配；失败时同样会写入 ``ms``（在 ``finally`` 里），
    所以失败记录的 ``latencyMs`` 是真实的"跑到哪算哪"而不是写死的 0。

    注：``_rescan_before_query`` 在本地模式会先做一次增量懒重扫（TASK-034 §C），
    它属于"拿到结果之前"的必要工作，故计入（口径写在这里与执行记录，保证跨次可比）。
    """
    started = time.perf_counter()
    elapsed: dict[str, float] = {}
    try:
        yield elapsed
    finally:
        elapsed["ms"] = (time.perf_counter() - started) * 1000.0


def _elapsed_kwargs(ctx: _AuditContext) -> dict[str, Any]:
    """审计用的 ``latency_ms``（**成功与失败两个窗口彼此不同，都在执行记录里写明**）：

    - 成功：``ctx["elapsed"]``——只含"懒重扫 + 检索/组装"（TASK-064 §C-3 的口径）；
    - 失败（校验/索引/检索抛错的路径）：从 handler 进入算起的整段，因为"检索那一段"
      根本没跑完，用 0 会让失败记录的耗时恒为 0（"写死"正是本卡要杜绝的）。
    """
    elapsed = ctx.get("elapsed")
    if isinstance(elapsed, dict) and "ms" in elapsed:
        return {"latency_ms": float(elapsed["ms"])}
    started = float(ctx.get("started", 0.0))
    return {"latency_ms": max(0.0, (time.perf_counter() - started) * 1000.0)}


def _record_failure(
    request: Request,
    ctx: _AuditContext,
    *,
    mode: str,
    query: str,
    reason: str,
) -> None:
    """失败路径落库（``ctx`` 里可能已有 projectId/耗时，没有就用兜底值）。"""
    audit.record_query_error(
        _meta_db(request),
        project_id=_project_of(ctx),
        mode=mode,
        query=query,
        **_elapsed_kwargs(ctx),
        reason=reason,
        user_id=_user_id(request),
    )


def _meta_db(request: Request) -> MetaDB | None:
    """元数据库（本地模式未建库 → ``None``，审计静默跳过，检索照常）。"""
    db = getattr(request.app.state, "meta_db", None)
    return db if isinstance(db, MetaDB) else None


def _user_id(request: Request) -> str | None:
    """当前用户 id（本地模式为 ``None``——无账户体系，R34）。"""
    return getattr(getattr(request.state, "zace_user", None), "id", None)


def _project_of(ctx: _AuditContext) -> str:
    """审计归属的 projectId：解析出来就用它，否则用 ``""``（表示"没走到解析"）。

    不猜项目：审计宁可留空 projectId，也不把一次请求挂到别的项目上（会污染该项目的用量）。
    """
    value = ctx.get("projectId")
    return str(value) if value else ""


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
    "LLM_FAILED_NOTICE",
    "MAX_MAX_TOKENS",
    "MAX_QUERY_CHARS",
    "SearchRequest",
    "ask",
    "search",
]
