"""ContextPack 组装与渲染（TASK-012 / CF-03 / D-21）。

对外入口：
- ``assemble(store, query, candidates, ...)``：候选（已 rerank）+ flows + freshness
  → ContextPack；
- ``render_markdown(pack)`` / ``render_evidence_for_prompt(pack)``：双层合同共用 formatter；
- ``to_json(pack)``：CF-03 JSON（供 05-MCP / Phase 2 service 直接返回）；
- ``BudgetConfig`` / ``budget_for(mode)``：Fast 10K / Deep 12K 预算配置（D-23）；
- ``collect_index_signals(store, candidates)``：G4/stale 与 unresolved 信号收集。
"""

from __future__ import annotations

from zace_core.contextpack.assembly import (
    ADJACENT_GAP_LINES,
    DEEP_BUDGET,
    FAST_BUDGET,
    MODE_DEEP,
    MODE_FAST,
    BudgetConfig,
    IndexSignals,
    assemble,
    budget_for,
    collect_index_signals,
    estimate_tokens,
    numbered_lines,
    to_json,
)
from zace_core.contextpack.render import render_evidence_for_prompt, render_markdown

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
    "render_evidence_for_prompt",
    "render_markdown",
    "to_json",
]
