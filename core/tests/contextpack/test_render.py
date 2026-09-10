"""TASK-012 Markdown 渲染（DoD：完整 pack 的渲染快照 + 行号/⚠/Meta 齐全）。"""

from __future__ import annotations

from pathlib import Path

from zace_core.contextpack import (
    BudgetConfig,
    IndexSignals,
    assemble,
    render_evidence_for_prompt,
    render_markdown,
)
from zace_core.types import Flow, FlowNode, Freshness, SpecBlockDef

NOW = 1_760_000_300


def _spec_block() -> SpecBlockDef:
    return SpecBlockDef(
        path="docs/design/auth.md",
        heading="Token Refresh",
        heading_path="认证 > Token Refresh",
        level=2,
        start_line=30,
        end_line=32,
        content="刷新流程说明\n\n使用 refresh_token",
        doctype="design",
    )


def _build_pack(store, seed_file, sym, cand):
    seed_file(
        store,
        path="src/auth/token_service.py",
        symbols=[sym("refresh", "TokenService.refresh", kind="method", start=45, end=46)],
        bodies={"TokenService.refresh": "def refresh(self):\n    return self.store.rotate()"},
    )
    seed_file(
        store,
        path="src/store.py",
        symbols=[sym("rotate", "TokenStore.rotate", kind="method", start=210, end=212)],
        bodies={"TokenStore.rotate": "def rotate(self):\n    return 'rotated'\n"},
    )
    seed_file(
        store,
        path="src/mw.py",
        symbols=[sym("verify", "AuthMiddleware.verify", kind="method", start=88, end=89)],
        bodies={"AuthMiddleware.verify": "def verify(self, request):\n    return refresh()"},
    )
    seed_file(store, path="docs/design/auth.md", language="markdown", spec_blocks=[_spec_block()])
    store.add_spec_refs(
        [
            (
                "docs/design/auth.md:认证 > Token Refresh:30",
                "src/auth/token_service.py:TokenService.refresh:45",
            )
        ]
    )
    store.apply_deletions(["src/legacy.py"])

    candidates = [
        cand(
            "src/auth/token_service.py",
            "TokenService.refresh",
            45,
            score=3.5,
            tier=0,
            channels={"exact": 1, "bm25": 1, "vector": 1},
            reasons=["explicit symbol TokenService.refresh", "3-channel consensus +0.5"],
            end=46,
        ),
        cand(
            "src/store.py",
            "TokenStore.rotate",
            210,
            score=2.0,
            channels={"bm25": 2, "vector": 2},
            reasons=["bm25 -1.2", "vector 0.81"],
            end=212,
        ),
        cand(
            "src/mw.py",
            "AuthMiddleware.verify",
            88,
            score=1.8,
            channels={"bm25": 3, "vector": 3},
            reasons=["bm25 -1.0", "vector 0.77"],
            end=89,
        ),
        cand(
            "docs/design/auth.md",
            "认证 > Token Refresh",
            30,
            score=1.2,
            kind="spec",
            channels={"bm25": 1},
            reasons=["bm25 -2.1", "high-value doctype +0.8"],
        ),
    ]
    flow = Flow(
        id="F1",
        nodes=(
            FlowNode(symbol="AuthMiddleware.verify", path="src/mw.py", line=88),
            FlowNode(symbol="TokenService.refresh", path="src/auth/token_service.py", line=45),
        ),
        truncated=False,
    )
    freshness = Freshness(indexed_at=NOW - 300, stale_files=("src/old.py",))
    config = BudgetConfig(hard_cap=10_000, framework_overhead=500)
    signals = IndexSignals(
        stale_doc_refs={"docs/design/auth.md:认证 > Token Refresh:30": ("LegacyToken.rotate",)},
        unresolved_count=2,
    )
    return assemble(
        store,
        "token 过期后在哪里刷新？",
        candidates,
        flows=[flow],
        freshness=freshness,
        config=config,
        signals=signals,
    )


def test_render_section_order_and_details(store, seed_file, sym, cand) -> None:
    pack = _build_pack(store, seed_file, sym, cand)
    text = render_markdown(pack, now=NOW)

    order = [
        "## Relevant Context",
        "### Code",
        "### Flow",
        "### Docs",
        "### Missing Evidence",
        "### Meta",
    ]
    positions = [text.index(section) for section in order]
    assert positions == sorted(positions)

    assert "[E1] TokenService.refresh — src/auth/token_service.py:45-46" in text
    assert "45 | def refresh(self):" in text          # 行号（agent 可对齐 Edit）
    assert "46 |     return self.store.rotate()" in text
    assert "[F1] AuthMiddleware.verify → TokenService.refresh" in text
    assert "[E4] docs/design/auth.md > 认证 > Token Refresh（design）" in text
    assert "⚠ 引用了已删除符号 LegacyToken.rotate，文档可能过时" in text
    assert "- [index_stale] " in text
    assert "- [stale_doc_reference] (LegacyToken.rotate) " in text
    assert "confidence: high | index: stale (1 files) | budget: " in text


def test_render_meta_budget_and_index_fresh(store, seed_file, sym, cand) -> None:
    seed_file(store, path="src/a.py", symbols=[sym("f", "f", start=1)])
    pack = assemble(
        store,
        "q",
        [cand("src/a.py", "f", 1, score=1.0)],
        freshness=Freshness(indexed_at=NOW - 300),
    )
    text = render_markdown(pack, now=NOW)
    assert "index: fresh (5 min ago)" in text
    assert "budget: 504/10.0K" in text   # <1000 用原值，≥1000 用 K（Module/03 §6 例）
    assert "confidence: low" in text


def test_render_evidence_for_prompt_has_no_meta_or_flow(store, seed_file, sym, cand) -> None:
    pack = _build_pack(store, seed_file, sym, cand)
    prompt_section = render_evidence_for_prompt(pack)
    assert "### Code" in prompt_section
    assert "### Docs" in prompt_section
    assert "### Meta" not in prompt_section
    assert "### Flow" not in prompt_section
    assert "### Missing Evidence" not in prompt_section
    assert "[E1]" in prompt_section and "[E4]" in prompt_section


def test_render_empty_pack_keeps_missing_and_meta(store) -> None:
    pack = assemble(store, "nothing", [])
    text = render_markdown(pack)
    assert "## Relevant Context" in text
    assert "### Missing Evidence" in text
    assert "- [no_context_match] " in text
    assert "### Meta" in text
    assert "### Code" not in text


SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "rich_pack.md"


def test_render_markdown_snapshot(store, seed_file, sym, cand) -> None:
    """完整 pack 的 Markdown 与固定快照一致（行号、⚠、Meta 齐全）。"""
    pack = _build_pack(store, seed_file, sym, cand)
    expected = SNAPSHOT_PATH.read_text(encoding="utf-8").rstrip("\n")
    assert render_markdown(pack, now=NOW) == expected
