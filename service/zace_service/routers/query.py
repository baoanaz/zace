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
- **空索引 → 409 ``index_in_progress``**（D-30 例外条款）：返回 200 空包会让 agent 误判
  "仓库里没有相关代码"，宁可让它带着"先同步"的提示重试；
- ``ask`` **绝不 500**：Phase 2 没有 LLM，``Engine.ask()`` 抛 ``NotImplementedError``，
  本实现不调用它，而是返回带 ``status="degraded"`` 的检索包（诚实降级，D-26）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from zace_core.contextpack import render_markdown

from zace_service.deps import get_engine_manager, require_project_id
from zace_service.errors import ApiError
from zace_service.packmeta import evidence_summary, pack_meta
from zace_service.runtime import EngineManager

router = APIRouter(tags=["query"])

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

    trace = manager.search(project_id, query, payload.maxTokens)
    meta = pack_meta(
        trace.pack,
        project_id=project_id,
        channels=trace.channels_used,
        degraded=trace.degraded,
        reason=trace.degraded_reason,
        candidate_count=trace.candidate_count,
        checkpoint_id=payload.checkpointId,
        include_pack=payload.includePack,
    )
    return {"markdown": render_markdown(trace.pack), "meta": meta}


@router.post("/api/query/ask")
def ask(payload: AskRequest, request: Request) -> dict[str, Any]:
    """Deep 模式：Phase 2 固定返回**降级包**（200 + ``status="degraded"``），绝不 500。"""
    manager = get_engine_manager(request)
    project_id = require_project_id(request, payload.projectId)
    question = _require_query(payload.question, field="question", code="invalid_question")
    _require_index(manager, project_id)

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
    return {
        "status": "degraded",
        "answer": f"{DEGRADED_NOTICE}\n\n{render_markdown(pack)}",
        "evidenceSummary": evidence_summary(pack),
        "meta": meta,
    }


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
    """空索引 → 409（D-30 的例外条款）：不返回 200 空包，而是给可执行的提示。"""
    chunks = manager.sync_status(project_id)["chunks"]
    if chunks == 0:
        raise ApiError(
            "index_in_progress",
            "该项目尚未索引（chunks=0）：请先同步（client 会在 tool call 时自动上传，"
            "或调用 POST /api/sync/batch-upload），索引完成后再查询。",
            409,
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
