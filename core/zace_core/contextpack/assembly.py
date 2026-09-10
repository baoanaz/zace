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
- **spec 保底**在贪心前**预占**最高分 spec 候选（存在相关 spec 时），保证不被预算挤掉；保底分支与
  贪心循环、合并路径共用 `placed_ids`（**按 chunk_id** 判重，R15，不再靠 `_Slot` 值比较）；预留块若
  已被贪心循环装填，预留预算立即**归还**（后续候选恢复完整 `hardCap`）；
- **tier3 配额**按 §4.1 字面实现：``tier3_used + est > tier3_ratio × used`` 即跳过；
- **skeleton 降级**只在"超单文件上限或超硬预算"时触发（>300 行是前置条件）；
- **"命中行"**：RRF 只给 chunk 粒度 → 取**切片起始行**（符号定义行，即该切片锚点行）起
  ``context_lines`` 行，其余计入 ``elidedLines``；
- **token 估算** = ``ceil(chars/4)``（近似，不引入 tokenizer，Module/03 §2 要点 3）；
- **片段化存储（TASK-017 / R12）**：``_Slot`` 按 ``(start, end, 原文)`` 片段列表存正文，
  合并按行号**有序插入**并去重重叠行；出口按片段行号升序编号拼接，省略区间**就地标注**
  （``... （省略 N 行）``）；``elidedLines`` = 声明区间行数 − Σ片段行数（真实省略行数）。
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
    "elision_note",
    "estimate_tokens",
    "has_elision_note",
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


#: 省略区间标注（证据块正文与渲染层共用同一措辞；Module/03 §6）。
_ELISION_TEMPLATE = "... （省略 {count} 行）"
_ELISION_PREFIX = "... （省略"


def elision_note(count: int) -> str:
    """省略标注文本（``... （省略 9 行）``）。"""
    return _ELISION_TEMPLATE.format(count=count)


def has_elision_note(content: str) -> bool:
    """正文里是否已**就地**标注了省略区间（合并区间的间隙 / 降级尾部）。"""
    return any(line.strip().startswith(_ELISION_PREFIX) for line in content.splitlines())


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
class _Segment:
    """证据块内的一个连续行区间：``text`` 为该区间的**原始**正文（渲染时加行号）。

    真实 chunk 的 ``content`` 行数与 ``[start_line, end_line]`` 等长；测试夹具允许二者不等
    （符号声明区间与正文长度不一致），此时按行号裁剪原文可能取到空文本（不渲染，只记行账）。
    """

    start: int
    end: int
    text: str

    @property
    def line_count(self) -> int:
        """该区间覆盖的行数（按行号算，elidedLines 的账）。"""
        return self.end - self.start + 1


@dataclass(slots=True)
class _Slot:
    """已装填的一项（片段列表 + 声明末行 + token 账，供合并/降级用）。"""

    candidate: Candidate
    item: EvidenceItem
    base_reason: str
    segments: list[_Segment]
    #: 声明覆盖的末行（≥ 末个片段 end）：skeleton 降级只保留前 N 行时，尾部省略记在这里。
    elision_upper: int
    prelude: str = ""  # skeleton 降级的签名（带行号），置于首个片段之前
    aggregated: int = 0

    @property
    def span(self) -> tuple[int, int]:
        """片段包围盒（首片段 start, 末片段 end）。"""
        return self.segments[0].start, self.segments[-1].end

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

    #: 已装填 chunk_id（R15）：同一 chunk 只装一次——保底分支、贪心循环与合并路径共用。
    #: 修复前保底分支用 `reserved not in slots` 做 `_Slot` **值**比较：预留候选由贪心循环装下后，
    #: 只要该 slot 被 `_try_merge`/`_degrade` 就地改动，值就不再相等，保底分支会把同一 chunk
    #: 的原始 span 再装一次（真实复现：E1(173-232) 合并块 + E30(175-197) 预留块）。
    placed_ids: set[str] = set()

    def _place(candidate: Candidate, slot: _Slot, tokens: int) -> None:
        nonlocal used, tier3_used
        used += tokens
        key = candidate.path or ""
        file_usage[key] = file_usage.get(key, 0) + tokens
        if candidate.tier == 3:
            tier3_used += tokens
        slots.append(slot)
        placed_ids.add(candidate.chunk_id)
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
    reserved_id = reserved.candidate.chunk_id if reserved is not None else None

    def _hard_limit() -> int:
        """预留期间收窄的硬顶；预留块被装填后即归还预留预算（R15，不再挤压其它候选）。"""
        pending = reserved_id is not None and reserved_id not in placed_ids
        return max(active.hard_cap - (reserve_tokens if pending else 0), active.framework_overhead)

    for candidate in pool:
        if candidate.chunk_id in placed_ids:
            omitted += 1  # 同一 chunk 只装一次（与 _place / 保底分支共用同一判重集合）
            continue
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
        hard_limit = _hard_limit()
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
            placed_ids.add(candidate.chunk_id)  # 已并入既有块：同一 chunk 不再单独装填
            continue
        _place(candidate, slot, tokens)

    # 保底补入：仅在预留块**尚未**被装填时执行（按 chunk_id 判重，R15）。
    if (
        reserved is not None
        and reserved.candidate.chunk_id not in placed_ids
        and used + reserved.tokens <= active.hard_cap
    ):
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
        content="",  # 由 _sync 按片段列表统一生成（TASK-017）
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
    slot = _Slot(
        candidate=candidate,
        item=item,
        base_reason=reason,
        segments=[_Segment(chunk.start_line, chunk.end_line, chunk.content)],
        elision_upper=chunk.end_line,
    )
    _sync(slot)
    return slot


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
    slot.prelude = numbered_lines(chunk.signature, start) if chunk.signature else ""
    slot.segments = [_Segment(start, kept_end, "\n".join(head))]
    _sync(slot)
    return slot


def _try_merge(slots: list[_Slot], slot: _Slot, tokens: int) -> int | None:
    """相邻区间合并（去重第 1 招）：返回本次新增的 token 数，未合并返回 ``None``。

    合并后片段按行号升序排列（不再是“分数顺序拼接”），重叠行去重、相邻区间归并。
    """
    for existing in slots:
        if existing.item.path != slot.item.path or existing.item.lines is None:
            continue
        if (existing.item.type == "spec") != (slot.item.type == "spec"):
            continue
        if _segments_distance(existing.segments, slot.segments) > ADJACENT_GAP_LINES:
            continue
        before = existing.tokens
        _merge_segments(existing, slot.segments)
        existing.item.reason = f"{existing.base_reason} + {_MERGE_NOTE}"
        return existing.tokens - before
    return None


def _merge_segments(slot: _Slot, incoming: Sequence[_Segment]) -> None:
    """把 ``incoming`` 片段按行序并入 ``slot``（重叠行去重，相邻区间归并）。"""
    for segment in incoming:
        slot.segments.extend(_uncovered_pieces(segment, slot.segments))
    slot.segments.sort(key=lambda segment: segment.start)
    slot.segments = _coalesce(slot.segments)
    _sync(slot)


def _uncovered_pieces(segment: _Segment, existing: Sequence[_Segment]) -> list[_Segment]:
    """``segment`` 中未被 ``existing`` 覆盖的子区间（原文按行号裁剪，可能为空文本）。"""
    pieces = [(segment.start, segment.end)]
    for other in existing:
        remaining: list[tuple[int, int]] = []
        for start, end in pieces:
            if other.end < start or other.start > end:
                remaining.append((start, end))
                continue
            if other.start > start:
                remaining.append((start, other.start - 1))
            if other.end < end:
                remaining.append((other.end + 1, end))
        pieces = remaining
    return [_Segment(start, end, _slice_text(segment, start, end)) for start, end in pieces]


def _slice_text(segment: _Segment, start: int, end: int) -> str:
    """取 ``segment`` 原文中 ``[start, end]`` 行的子串（行号超出原文时返回已可用部分）。"""
    lines = segment.text.splitlines()
    low = max(start - segment.start, 0)
    return "\n".join(lines[low : end - segment.start + 1])


def _coalesce(segments: Sequence[_Segment]) -> list[_Segment]:
    """相邻（行距 0）片段归并为一个片段；区间合并语义不变（连续区间不拆块）。"""
    merged: list[_Segment] = []
    for segment in segments:
        if merged and segment.start <= merged[-1].end + 1:
            previous = merged[-1]
            text = "\n".join(part for part in (previous.text, segment.text) if part)
            merged[-1] = _Segment(previous.start, max(previous.end, segment.end), text)
            continue
        merged.append(segment)
    return merged


def _segments_distance(left: Sequence[_Segment], right: Sequence[_Segment]) -> int:
    """两组片段间的最小未覆盖行数（重叠/相邻 → 0）——合并阈值按最近片段算。"""
    return min(_gap_lines(a.start, a.end, b.start, b.end) for a in left for b in right)


def _sync(slot: _Slot) -> None:
    """片段列表 → ``item.content`` / ``item.lines`` / ``item.elided_lines``（唯一出口）。"""
    segments = slot.segments
    first, last = segments[0].start, segments[-1].end
    slot.elision_upper = max(slot.elision_upper, last)
    covered = sum(segment.line_count for segment in segments)
    slot.item.lines = (first, last)
    slot.item.elided_lines = max(slot.elision_upper - first + 1 - covered, 0)
    slot.item.content = _render_content(slot)


def _render_content(slot: _Slot) -> str:
    """按片段行号升序拼接带行号正文，省略区间**就地**标注（间隙与尾部）。"""
    parts: list[str] = []
    if slot.prelude:
        parts.append(slot.prelude)
    previous: _Segment | None = None
    for segment in slot.segments:
        if previous is not None:
            gap = segment.start - previous.end - 1
            if gap > 0:
                parts.append(elision_note(gap))
        if segment.text:
            parts.append(numbered_lines(segment.text, segment.start))
        previous = segment
    tail = slot.elision_upper - slot.segments[-1].end
    if tail > 0:
        parts.append(elision_note(tail))
    return "\n".join(parts)


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
