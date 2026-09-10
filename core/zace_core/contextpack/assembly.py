"""ContextPack 组装（TASK-012 §A）：预算内、结构化、可引用、诚实标注缺口。

设计依据：``docs/design/Module/03-上下文组装.md`` 全篇（D-21 双层合同 / D-22 装填 / D-23 预算）：

```text
输入：候选（已 rerank） + flows + freshness + 索引信号
预算：hardCap（Fast 默认 10K，可配 8-12K；Deep 12K） − 框架开销 ≈500 token
装填：分数降序贪心；单文件 ≤25%；tier3 配额 ≤30%；spec 保底 ≥1
去重三招：相邻区间合并（行距 ≤10）/ 同符号聚合 / skeleton 降级（>300 行且超预算）
tier 不作为排序键（D-17）：只做配额与资格线
```

编号：evidence 与 docs **共用 E 编号空间**（占用顺序 = 装填顺序），flows 用 F（D-21）。

实现口径（本卡冻结，记录于任务卡"执行记录"）：

- **内容来源**：``store`` 提供切片正文；``EvidenceItem.content`` 是**带行号原文**
  （``45 | def refresh(...)``，CF-03 定义），渲染层直接输出；
- **spec 保底**在贪心前**预占**最高分 spec 候选（存在相关 spec 时），保证不被预算挤掉；
- **tier3 配额**按 §4.1 字面实现：``tier3_used + est > tier3_ratio × used`` 即跳过；
- **skeleton 降级**只在"超单文件上限或超硬预算"时触发（>300 行是前置条件）；
- **"命中行"**：RRF 只给 chunk 粒度 → 取**切片起始行**（符号定义行，即该切片锚点行）起
  ``context_lines`` 行，其余计入 ``elidedLines``；
- **token 估算** = ``ceil(chars/4)``（近似，不引入 tokenizer，Module/03 §2 要点 3）。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from zace_core.parsing.markdown import classify_doctype
from zace_core.storage import Store
from zace_core.types import (
    Budget,
    Candidate,
    ContextPack,
    EvidenceItem,
    Flow,
    Freshness,
    MissingEvidence,
)

__all__ = [
    "ADJACENT_GAP_LINES",
    "DEEP_BUDGET",
    "FAST_BUDGET",
    "MODE_DEEP",
    "MODE_FAST",
    "BudgetConfig",
    "IndexSignals",
    "assemble",
    "budget_for",
    "collect_index_signals",
    "estimate_tokens",
    "numbered_lines",
    "to_json",
]

MODE_FAST = "fast"
MODE_DEEP = "deep"

#: 相邻区间合并的行距阈值（Module/03 §3：同文件两 chunk 行距 ≤10 → 合并）。
ADJACENT_GAP_LINES = 10

_AGGREGATION_NOTE = "同符号聚合"
_MERGE_NOTE = "相邻区间合并"


def estimate_tokens(text: str) -> int:
    """chars/4 近似（Module/03 §2 要点 3：无 tokenizer 依赖，标注 approximate）。"""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def numbered_lines(content: str, start_line: int) -> str:
    """切片正文 → 带行号原文（``45 | def refresh(self):``）。"""
    lines = content.splitlines()
    return "\n".join(f"{start_line + offset} | {line}" for offset, line in enumerate(lines))


@dataclass(frozen=True, slots=True)
class BudgetConfig:
    """装填预算与配额（Module/03 §4.1/§4.2；D-23）。"""

    hard_cap: int = 10_000               # Fast 默认 10K（用户可 8-12K）
    framework_overhead: int = 500        # query/freshness/missing 等元数据
    single_file_ratio: float = 0.25      # A2：单文件 ≤25% hardCap
    tier3_ratio: float = 0.30            # A3：tier3 配额 ≤30%
    spec_floor: int = 1                  # 存在相关 spec 时至少装 1-2 块
    skeleton_line_threshold: int = 300   # 超过此行数且超预算 → skeleton 降级
    skeleton_context_lines: int = 15     # 降级保留的上下文行数（±15）


FAST_BUDGET = BudgetConfig()
#: Deep 12K 硬顶（Module/03 §4.2 裁决；Phase 3 接入，本卡只实现配置）。
DEEP_BUDGET = BudgetConfig(hard_cap=12_000)


def budget_for(mode: str) -> BudgetConfig:
    if mode == MODE_DEEP:
        return DEEP_BUDGET
    if mode != MODE_FAST:
        raise ValueError(f"mode 必须是 'fast' 或 'deep'，收到 {mode!r}")
    return FAST_BUDGET


@dataclass(frozen=True, slots=True)
class IndexSignals:
    """组装需要的索引侧信号（缺失即如实不报，不猜不造；A5）。"""

    stale_doc_refs: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    unresolved_count: int = 0


def collect_index_signals(store: Store, candidates: Sequence[Candidate]) -> IndexSignals:
    """从 Store 收集 Phase 1 可得的缺失证据信号（G4 stale + unresolved_refs）。"""
    stale: dict[str, tuple[str, ...]] = {}
    for candidate in candidates:
        if candidate.kind != "spec":
            continue
        refs = store.spec_refs_for_spec(candidate.chunk_id)
        names = tuple(_symbol_name_from_id(ref.symbol_id) for ref in refs if ref.stale)
        if names:
            stale[candidate.chunk_id] = names
    return IndexSignals(
        stale_doc_refs=stale,
        unresolved_count=len(store.unresolved_refs(status="failed")),
    )


def _symbol_name_from_id(symbol_id: str) -> str:
    """``{path}:{fqn}:{start_line}`` → ``fqn``（C++ 的 ``A::b`` 也能正确取回）。"""
    _head, sep, tail = symbol_id.partition(":")
    if not sep:
        return symbol_id
    fqn, _sep, _line = tail.rpartition(":")
    return fqn or symbol_id


# --------------------------------------------------------------------------- 装填


@dataclass(slots=True)
class _Slot:
    """已装填的一项（含行区间与 token 账，供合并/降级用）。"""

    candidate: Candidate
    item: EvidenceItem
    base_reason: str
    span: tuple[int, int]
    aggregated: int = 0

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.item.content)


def assemble(
    store: Store,
    query: str,
    candidates: Sequence[Candidate],
    *,
    flows: Sequence[Flow] = (),
    freshness: Freshness | None = None,
    mode: str = MODE_FAST,
    config: BudgetConfig | None = None,
    signals: IndexSignals | None = None,
    structural_result: bool = False,
    graph_boundary: bool = False,
) -> ContextPack:
    """候选（已 rerank）→ 预算内的 ContextPack（CF-03 字段）。"""
    active = config or budget_for(mode)
    single_file_cap = int(active.hard_cap * active.single_file_ratio)
    index_signals = signals if signals is not None else IndexSignals()
    fresh = freshness if freshness is not None else store.freshness()
    pool = sorted(candidates, key=lambda c: (-c.score, -c.rrf_score, c.chunk_id))

    used = active.framework_overhead
    omitted = 0
    capacity_cut = 0
    tier3_used = 0
    file_usage: dict[str, int] = {}
    symbol_slots: dict[str, _Slot] = {}
    slots: list[_Slot] = []

    def _place(candidate: Candidate, slot: _Slot, tokens: int) -> None:
        nonlocal used, tier3_used
        used += tokens
        key = candidate.path or ""
        file_usage[key] = file_usage.get(key, 0) + tokens
        if candidate.tier == 3:
            tier3_used += tokens
        slots.append(slot)
        if candidate.symbol_fqn:
            symbol_slots.setdefault(candidate.symbol_fqn, slot)

    # spec 保底：为最高分 spec 候选**预留预算**（存在相关 spec 时），贪心后再补入——
    # 保留"装填顺序 = score 降序"的语义（Module/03 §4.1 的 spec 保底配额）。
    reserved: _Slot | None = None
    if active.spec_floor > 0:
        for candidate in pool:
            if candidate.kind != "spec":
                continue
            slot = _build_slot(store, candidate, index_signals)
            if slot is None:
                continue
            reserved = slot
            break
    reserve_tokens = reserved.tokens if reserved is not None else 0
    hard_limit = max(active.hard_cap - reserve_tokens, active.framework_overhead)

    for candidate in pool:
        slot = _build_slot(store, candidate, index_signals)
        if slot is None:
            omitted += 1
            continue

        existing = symbol_slots.get(candidate.symbol_fqn) if candidate.symbol_fqn else None
        if existing is not None and existing is not slot:
            omitted += 1  # 同符号聚合：留最高分，其余计入 omittedCount 并在 reason 注明
            existing.aggregated += 1
            existing.item.reason = (
                f"{existing.base_reason} + {_AGGREGATION_NOTE}×{existing.aggregated}"
            )
            continue

        tokens = slot.tokens
        file_key = candidate.path or ""
        over_file_cap = file_usage.get(file_key, 0) + tokens > single_file_cap
        if over_file_cap or used + tokens > hard_limit:
            degraded = _degrade(candidate, slot, active, store)
            if degraded is not None:
                tokens = degraded.tokens

        if file_usage.get(file_key, 0) + tokens > single_file_cap:
            omitted += 1
            capacity_cut += 1
            continue
        if candidate.tier == 3 and tier3_used + tokens > active.tier3_ratio * used:
            omitted += 1
            capacity_cut += 1
            continue
        if used + tokens > hard_limit:
            omitted += 1
            capacity_cut += 1
            break

        merged = _try_merge(slots, slot, tokens)
        if merged is not None:
            delta = merged
            used += delta
            file_usage[file_key] = file_usage.get(file_key, 0) + delta
            continue
        _place(candidate, slot, tokens)

    if reserved is not None and reserved not in slots and used + reserved.tokens <= active.hard_cap:
        _place(reserved.candidate, reserved, reserved.tokens)

    truncated = capacity_cut > 0
    flow_tokens = sum(
        estimate_tokens(node.symbol) + estimate_tokens(node.path)
        for flow in flows
        for node in flow.nodes
    )

    evidence: list[EvidenceItem] = []
    docs: list[EvidenceItem] = []
    for index, slot in enumerate(slots, start=1):
        slot.item.id = f"E{index}"
        (docs if slot.item.type == "spec" else evidence).append(slot.item)

    pack = ContextPack(
        query=query,
        mode=mode,
        answerable=False,
        confidence="low",
        freshness=fresh,
        evidence=evidence,
        docs=docs,
        flows=list(flows),
        missing_evidence=[],
        next_queries=[],
        budget=Budget(
            used_tokens=used + flow_tokens,
            hard_cap=active.hard_cap,
            truncated=truncated,
            omitted_count=omitted,
        ),
    )
    pack.answerable, pack.confidence = _assess(
        pool, evidence, docs, structural_result=structural_result, graph_boundary=graph_boundary
    )
    pack.missing_evidence = _missing_evidence(
        pack,
        fresh,
        index_signals,
        omitted=omitted,
        truncated=truncated,
        evidence_count=len(evidence) + len(docs),
    )
    pack.next_queries = _next_queries(pool, evidence, docs)
    return pack


def _build_slot(store: Store, candidate: Candidate, signals: IndexSignals) -> _Slot | None:
    chunk = store.chunk_by_id(candidate.chunk_id)
    if chunk is None:
        return None
    is_spec = candidate.kind == "spec"
    reason = " + ".join(candidate.reasons) or "rrf"
    item = EvidenceItem(
        id="E0",  # 装填顺序确定后统一编号
        type="spec" if is_spec else ("test" if candidate.kind == "test" else "code"),
        path=chunk.file_path,
        content=numbered_lines(chunk.content, chunk.start_line),
        score=candidate.score,
        evidence_tier=candidate.tier,
        reason=reason,
        symbol=None if is_spec else chunk.symbol_fqn,
        heading_path=chunk.symbol_fqn if is_spec else None,
        doctype=classify_doctype(chunk.file_path) if is_spec else None,
        lines=(chunk.start_line, chunk.end_line),
        elided_lines=0,
        stale_refs=tuple(signals.stale_doc_refs.get(candidate.chunk_id, ())),
    )
    return _Slot(
        candidate=candidate,
        item=item,
        base_reason=reason,
        span=(chunk.start_line, chunk.end_line),
    )


def _degrade(
    candidate: Candidate,
    slot: _Slot,
    config: BudgetConfig,
    store: Store,
) -> _Slot | None:
    """单 chunk > ``skeleton_line_threshold`` 行且超预算 → 签名 + 起始行起 N 行。"""
    start, end = slot.span
    if end - start + 1 <= config.skeleton_line_threshold:
        return None
    chunk = store.chunk_by_id(candidate.chunk_id)
    if chunk is None:
        return None
    kept_end = min(start + config.skeleton_context_lines, end)
    head = chunk.content.splitlines()[: config.skeleton_context_lines + 1]
    body = numbered_lines("\n".join(head), start)
    signature = numbered_lines(chunk.signature, start) if chunk.signature else ""
    slot.item.content = f"{signature}\n{body}" if signature else body
    slot.item.lines = (start, kept_end)
    slot.item.elided_lines = max(0, end - kept_end)
    slot.span = (start, kept_end)
    return slot


def _try_merge(slots: list[_Slot], slot: _Slot, tokens: int) -> int | None:
    """相邻区间合并（去重第 1 招）：返回本次新增的 token 数，未合并返回 ``None``。"""
    start, end = slot.span
    for existing in slots:
        if existing.item.path != slot.item.path or existing.item.lines is None:
            continue
        if (existing.item.type == "spec") != (slot.item.type == "spec"):
            continue
        old_start, old_end = existing.item.lines
        gap = _gap_lines(old_start, old_end, start, end)
        if gap > ADJACENT_GAP_LINES:
            continue
        before = existing.tokens
        existing.item.lines = (min(old_start, start), max(old_end, end))
        existing.item.elided_lines += gap
        existing.item.content = f"{existing.item.content}\n{slot.item.content}"
        existing.span = (existing.item.lines[0], existing.item.lines[1])
        existing.item.reason = f"{existing.base_reason} + {_MERGE_NOTE}"
        return existing.tokens - before
    return None


def _gap_lines(old_start: int, old_end: int, start: int, end: int) -> int:
    """两个区间的未覆盖行数（重叠/相邻 → 0）。"""
    if start > old_end:
        return max(start - old_end - 1, 0)
    if old_start > end:
        return max(old_start - end - 1, 0)
    return 0


# --------------------------------------------------------------------------- 判定与缺口


def _is_explicit(candidate: Candidate) -> bool:
    return "exact" in candidate.channel_ranks or "explicit path" in candidate.reasons


def _consensus_count(candidates: Iterable[Candidate]) -> int:
    return sum(1 for candidate in candidates if len(candidate.channel_ranks) >= 2)


def _assess(
    pool: Sequence[Candidate],
    evidence: Sequence[EvidenceItem],
    docs: Sequence[EvidenceItem],
    *,
    structural_result: bool,
    graph_boundary: bool,
) -> tuple[bool, str]:
    """answerable / confidence 确定性判定（Module/03 §4.4，照抄实现）。"""
    explicit_hits = sum(1 for candidate in pool if _is_explicit(candidate))
    consensus = _consensus_count(pool)
    answerable = explicit_hits >= 1 or consensus >= 2 or structural_result

    spec_only = bool(docs) and not evidence
    if explicit_hits >= 1 and consensus >= 3 and not graph_boundary:
        confidence = "high"
    elif (consensus > 0 and explicit_hits == 0) or spec_only:
        confidence = "medium"
    else:
        confidence = "low"
    return answerable, confidence


def _missing_evidence(
    pack: ContextPack,
    freshness: Freshness,
    signals: IndexSignals,
    *,
    omitted: int,
    truncated: bool,
    evidence_count: int,
) -> list[MissingEvidence]:
    """Phase 1 可实现的缺失证据子集（Module/03 §5；graph_boundary/symbol_ambiguous 留接口）。"""
    missing: list[MissingEvidence] = []
    if freshness.stale_files:
        missing.append(
            MissingEvidence(
                code="index_stale",
                message=(
                    f"索引落后于工作区：{len(freshness.stale_files)} 个文件已变更但未重索引，"
                    "证据可能不是当前代码。"
                ),
            )
        )
    if freshness.indexing_files:
        missing.append(
            MissingEvidence(
                code="indexing_pending",
                message=(
                    f"{len(freshness.indexing_files)} 个文件仍在索引队列中，"
                    "这些文件暂时无法作为证据。"
                ),
            )
        )
    if signals.unresolved_count > 0:
        missing.append(
            MissingEvidence(
                code="unresolved_reference",
                message=(
                    f"{signals.unresolved_count} 个符号引用无法解析"
                    "（unresolved_refs status=failed），"
                    "涉及这些符号的调用关系可能缺失。"
                ),
            )
        )
    for item in pack.docs:
        if not item.stale_refs:
            continue
        names = ", ".join(item.stale_refs)
        missing.append(
            MissingEvidence(
                code="stale_doc_reference",
                message=(
                    f"文档 {item.path} 引用了已删除或改名的符号（{names}），该文档可能已过时；"
                    "需要以代码为准并更新文档。"
                ),
                symbol=item.stale_refs[0],
            )
        )
    if truncated:
        missing.append(
            MissingEvidence(
                code="retrieval_truncated",
                message=(
                    f"候选池被预算裁剪：省略 {omitted} 个候选，可能有相关但未展示的证据；"
                    "可提高预算或收窄查询。"
                ),
            )
        )
    if evidence_count == 0:
        missing.append(
            MissingEvidence(
                code="no_context_match",
                message="没有命中任何可用证据：查询词与索引内容无共识匹配，建议换用具体符号名或路径。",
            )
        )
    return missing


def _next_queries(
    pool: Sequence[Candidate],
    evidence: Sequence[EvidenceItem],
    docs: Sequence[EvidenceItem],
) -> list[str]:
    """确定性生成 2-3 条自愈查询（禁止 LLM；Module/03 §5）。"""
    queries: list[str] = []
    top = list(pool[:3])
    named = next((c for c in top if c.symbol_fqn and c.kind != "spec"), None)
    if named is not None:
        queries.append(f"{named.symbol_fqn.rsplit('.', 1)[-1]} 的调用方有哪些")
    pathed = next((c for c in top if c.path), None)
    if pathed is not None:
        queries.append(f"{pathed.path} 里还有哪些与查询相关的符号")
    spec = next(iter(docs), None)
    if spec is not None and spec.heading_path:
        queries.append(f"{spec.heading_path} 对应的实现代码在哪里")
    if not queries and evidence:
        queries.append(f"{evidence[0].path} 的实现细节")
    return queries[:3]


# --------------------------------------------------------------------------- 序列化


def to_json(pack: ContextPack) -> dict:
    """ContextPack → CF-03 JSON（键名与 ``docs/contracts/contextpack.schema.json`` 完全一致）。"""
    return {
        "query": pack.query,
        "mode": pack.mode,
        "answerable": pack.answerable,
        "confidence": pack.confidence,
        "freshness": _freshness_json(pack.freshness),
        "evidence": [_evidence_json(item) for item in pack.evidence],
        "docs": [_doc_json(item) for item in pack.docs],
        "flows": [_flow_json(flow) for flow in pack.flows],
        "missingEvidence": [
            {"code": item.code, "message": item.message, "symbol": item.symbol}
            for item in pack.missing_evidence
        ],
        "nextQueries": list(pack.next_queries),
        "budget": {
            "usedTokens": pack.budget.used_tokens if pack.budget else 0,
            "hardCap": pack.budget.hard_cap if pack.budget else 0,
            "truncated": pack.budget.truncated if pack.budget else False,
            "omittedCount": pack.budget.omitted_count if pack.budget else 0,
        },
    }


def _freshness_json(freshness: Freshness) -> dict:
    return {
        "indexedAt": freshness.indexed_at,
        "staleFiles": list(freshness.stale_files),
        "indexingFiles": list(freshness.indexing_files),
    }


def _evidence_json(item: EvidenceItem) -> dict:
    payload: dict = {
        "id": item.id,
        "type": item.type,
        "path": item.path,
        "content": item.content,
        "score": item.score,
        "evidenceTier": item.evidence_tier,
        "reason": item.reason,
        "elidedLines": item.elided_lines,
    }
    if item.symbol is not None:
        payload["symbol"] = item.symbol
    if item.lines is not None:
        payload["lines"] = [item.lines[0], item.lines[1]]
    return payload


def _doc_json(item: EvidenceItem) -> dict:
    payload: dict = {
        "id": item.id,
        "type": "spec",
        "path": item.path,
        "headingPath": item.heading_path or "",
        "doctype": item.doctype or classify_doctype(item.path),
        "content": item.content,
        "reason": item.reason,
    }
    if item.lines is not None:
        payload["lines"] = [item.lines[0], item.lines[1]]
    if item.stale_refs:
        payload["staleRefs"] = list(item.stale_refs)
    return payload


def _flow_json(flow: Flow) -> dict:
    return {
        "id": flow.id,
        "nodes": [
            {"symbol": node.symbol, "path": node.path, "line": node.line} for node in flow.nodes
        ],
        "truncated": flow.truncated,
    }
