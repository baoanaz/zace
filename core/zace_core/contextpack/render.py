"""ContextPack 渲染（TASK-012 §B）：对外 Markdown（Module/03 §6，D-21 双层合同）。

节顺序固定：``## Relevant Context`` → Code / Flow / Docs / Missing Evidence / Meta。
引用格式 ``[E*]`` / ``[F*]`` 与合同一致（04 citation 的锚点）；代码带行号（agent 可直接对齐
Edit）；stale 文档带 ``⚠`` 行；budget/confidence/index 状态入 ``Meta``。

``render_evidence_for_prompt`` 是同一 formatter 的子函数（只有 Code/Docs 分节），
供 Module/04 的 prompt 组装在 Phase 3 直接复用——两处绝不各写一套渲染逻辑。

省略标注（``... （省略 N 行）``）由组装层**就地**写在 ``item.content`` 里（TASK-017 / R12：
标注位置与行号区间一致）；本层只对外部构造、未就地标注的 pack 兜底追加。
"""

from __future__ import annotations

import time

from zace_core.contextpack.assembly import elision_note, has_elision_note
from zace_core.types import ContextPack, EvidenceItem, Freshness

__all__ = ["render_evidence_for_prompt", "render_markdown"]


def render_markdown(pack: ContextPack, *, now: int | None = None) -> str:
    """完整 ContextPack → Markdown（Fast 模式 MCP 直接返回的形态）。"""
    sections: list[str] = ["## Relevant Context"]
    sections.extend(_code_section(pack))
    sections.extend(_flow_section(pack))
    sections.extend(_docs_section(pack))
    sections.extend(_missing_section(pack))
    sections.append(_meta_section(pack, now=now))
    return "\n".join(sections)


def render_evidence_for_prompt(pack: ContextPack) -> str:
    """04 prompt 的 evidence 分节（复用同一 formatter，Phase 3 直接用）。"""
    sections: list[str] = []
    sections.extend(_code_section(pack, heading="### Code"))
    sections.extend(_docs_section(pack))
    return "\n".join(sections).strip()


# --------------------------------------------------------------------------- 分节


def _code_section(pack: ContextPack, *, heading: str = "### Code") -> list[str]:
    if not pack.evidence:
        return []
    lines = [heading]
    for item in pack.evidence:
        lines.extend(_evidence_lines(item))
    return lines


def _docs_section(pack: ContextPack) -> list[str]:
    if not pack.docs:
        return []
    lines = ["### Docs"]
    for item in pack.docs:
        lines.extend(_evidence_lines(item, is_doc=True))
    return lines


def _flow_section(pack: ContextPack) -> list[str]:
    if not pack.flows:
        return []
    lines = ["### Flow"]
    for flow in pack.flows:
        chain = " → ".join(node.symbol for node in flow.nodes)
        suffix = "（已截断）" if flow.truncated else ""
        lines.append(f"[{flow.id}] {chain}{suffix}")
    return lines


def _missing_section(pack: ContextPack) -> list[str]:
    if not pack.missing_evidence:
        return []
    lines = ["### Missing Evidence"]
    for item in pack.missing_evidence:
        symbol = f" ({item.symbol})" if item.symbol else ""
        lines.append(f"- [{item.code}]{symbol} {item.message}")
    return lines


def _evidence_lines(item: EvidenceItem, *, is_doc: bool = False) -> list[str]:
    if is_doc:
        doctype = f"（{item.doctype}）" if item.doctype else ""
        heading = f" > {item.heading_path}" if item.heading_path else ""
        header = f"[{item.id}] {item.path}{heading}{doctype}"
    else:
        target = item.symbol or item.path
        span = ""
        if item.lines is not None:
            span = f":{item.lines[0]}-{item.lines[1]}"
        header = f"[{item.id}] {target} — {item.path}{span}"
    lines = [header, f"     reason: {item.reason}"]
    lines.extend(f"     {line}" for line in item.content.splitlines())
    if item.elided_lines > 0 and not has_elision_note(item.content):
        lines.append(f"     {elision_note(item.elided_lines)}")
    if item.stale_refs:
        lines.append(f"     ⚠ 引用了已删除符号 {', '.join(item.stale_refs)}，文档可能过时")
    return lines


def _meta_section(pack: ContextPack, *, now: int | None) -> str:
    budget = pack.budget
    used = budget.used_tokens if budget else 0
    cap = budget.hard_cap if budget else 0
    confidence = pack.confidence
    return (
        f"### Meta\n"
        f"confidence: {confidence} | index: {_index_status(pack.freshness, now)} | "
        f"budget: {_thousands(used)}/{_thousands(cap)}"
    )


def _index_status(freshness: Freshness, now: int | None) -> str:
    if freshness.indexing_files:
        return f"indexing ({len(freshness.indexing_files)} files)"
    if freshness.stale_files:
        return f"stale ({len(freshness.stale_files)} files)"
    if freshness.indexed_at is None:
        return "unknown"
    reference = int(time.time()) if now is None else now
    age = max(reference - freshness.indexed_at, 0)
    return f"fresh ({_age(age)} ago)"


def _age(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h"


def _thousands(tokens: int) -> str:
    if tokens < 1000:
        return str(tokens)
    return f"{tokens / 1000:.1f}K"
