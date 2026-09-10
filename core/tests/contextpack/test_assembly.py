"""TASK-012 组装（DoD：预算/配额/去重三招/判定矩阵/缺口/性能）。"""

from __future__ import annotations

import time

import pytest
from zace_core.contextpack import (
    DEEP_BUDGET,
    FAST_BUDGET,
    BudgetConfig,
    IndexSignals,
    assemble,
    budget_for,
    collect_index_signals,
    estimate_tokens,
)
from zace_core.types import Flow, FlowNode, Freshness, SpecBlockDef


def _long(store, seed_file, sym, path: str, fqn: str, start: int, chars: int) -> None:
    seed_file(
        store,
        path=path,
        symbols=[sym(fqn, fqn, start=start, end=start)],
        bodies={fqn: "x" * chars},
    )


def _spec_block(path: str, heading: str, *, start: int = 10) -> SpecBlockDef:
    return SpecBlockDef(
        path=path,
        heading=heading,
        heading_path=f"架构 > {heading}",
        level=2,
        start_line=start,
        end_line=start + 5,
        content="设计说明" * 5,
        doctype="design",
    )


# --------------------------------------------------------------------------- 预算


def test_budget_truncates_and_counts_omitted(store, seed_file, sym, cand) -> None:
    for index in range(6):
        _long(store, seed_file, sym, f"src/f{index}.py", f"f{index}", 1, 400)
    candidates = [cand(f"src/f{i}.py", f"f{i}", 1, score=1.0 - i / 10) for i in range(6)]
    config = BudgetConfig(hard_cap=400, framework_overhead=0, single_file_ratio=1.0)

    pack = assemble(store, "q", candidates, config=config)
    assert pack.budget is not None
    assert pack.budget.truncated is True
    assert pack.budget.omitted_count >= 1
    assert pack.budget.used_tokens <= config.hard_cap
    assert len(pack.evidence) < len(candidates)


def test_framework_overhead_is_counted(store, seed_file, sym, cand) -> None:
    _long(store, seed_file, sym, "src/a.py", "f", 1, 40)
    config = BudgetConfig(hard_cap=1_000, framework_overhead=500, single_file_ratio=1.0)
    pack = assemble(store, "q", [cand("src/a.py", "f", 1, score=1.0)], config=config)
    assert pack.budget is not None
    item_tokens = sum(estimate_tokens(item.content) for item in pack.evidence)
    assert pack.budget.used_tokens == 500 + item_tokens


def test_flow_tokens_count_but_do_not_compete(store, seed_file, sym, cand) -> None:
    _long(store, seed_file, sym, "src/a.py", "f", 1, 40)
    flow = Flow(
        id="F1",
        nodes=(
            FlowNode(symbol="a", path="src/a.py", line=1),
            FlowNode(symbol="b", path="src/b.py", line=2),
        ),
    )
    config = BudgetConfig(hard_cap=10_000, framework_overhead=0, single_file_ratio=1.0)
    pack = assemble(store, "q", [cand("src/a.py", "f", 1, score=1.0)], flows=[flow], config=config)
    assert pack.budget is not None
    assert pack.budget.used_tokens > sum(estimate_tokens(i.content) for i in pack.evidence)
    assert pack.flows == [flow]


def test_budget_defaults_per_mode(store) -> None:
    assert FAST_BUDGET.hard_cap == 10_000
    assert DEEP_BUDGET.hard_cap == 12_000
    assert budget_for("deep").hard_cap == 12_000
    with pytest.raises(ValueError):
        budget_for("turbo")


def test_no_candidates_yields_empty_pack(store) -> None:
    pack = assemble(store, "token 刷新", [])
    assert pack.evidence == []
    assert pack.docs == []
    assert pack.answerable is False
    assert pack.confidence == "low"
    assert [item.code for item in pack.missing_evidence] == ["no_context_match"]
    assert "no_context_match" not in pack.next_queries


# --------------------------------------------------------------------------- 配额


def test_single_file_cap_25_percent_lets_other_files_fill(store, seed_file, sym, cand) -> None:
    seed_file(
        store,
        path="src/big.py",
        # 行距 >10 → 不触发相邻区间合并（本测试只验证单文件配额）
        symbols=[sym(f"big{i}", f"big{i}", start=i * 50 + 1) for i in range(3)],
        bodies={f"big{i}": "x" * 396 for i in range(3)},
    )
    _long(store, seed_file, sym, "src/other.py", "other", 1, 196)
    candidates = [
        cand("src/big.py", f"big{index}", index * 50 + 1, score=1.0 - index / 10)
        for index in range(3)
    ] + [cand("src/other.py", "other", 1, score=0.5)]
    config = BudgetConfig(hard_cap=1_000, framework_overhead=0)

    pack = assemble(store, "q", candidates, config=config)
    assert sum(1 for item in pack.evidence if item.path == "src/big.py") == 2
    assert any(item.path == "src/other.py" for item in pack.evidence)  # 其他文件补位
    assert pack.budget is not None and pack.budget.truncated is True


def test_tier3_quota_uses_30_percent_of_used_budget(store, seed_file, sym, cand) -> None:
    _long(store, seed_file, sym, "src/seed.py", "seed", 1, 396)     # 100 token，tier1
    _long(store, seed_file, sym, "src/g1.py", "g1", 1, 396)         # 100 token，tier3
    _long(store, seed_file, sym, "src/g2.py", "g2", 1, 76)          # 20 token，tier3
    candidates = [
        cand("src/seed.py", "seed", 1, score=1.0),
        cand("src/g1.py", "g1", 1, score=0.5, tier=3, channels={}, graph_depth=1),
        cand("src/g2.py", "g2", 1, score=0.4, tier=3, channels={}, graph_depth=1),
    ]
    config = BudgetConfig(hard_cap=10_000, framework_overhead=0, tier3_ratio=0.30)

    pack = assemble(store, "q", candidates, config=config)
    paths = [item.path for item in pack.evidence]
    assert "src/seed.py" in paths
    assert "src/g1.py" not in paths       # 100 > 30% × (100)
    assert "src/g2.py" in paths           # 20 ≤ 30% × (100 + 20)
    assert pack.budget is not None and pack.budget.omitted_count == 1


def test_spec_floor_keeps_a_doc_even_when_last(store, seed_file, sym, cand) -> None:
    for index in range(4):
        _long(store, seed_file, sym, f"src/f{index}.py", f"f{index}", 1, 396)
    seed_file(
        store,
        path="docs/auth.md",
        language="markdown",
        spec_blocks=[_spec_block("docs/auth.md", "Token Refresh")],
    )
    candidates = [
        cand(f"src/f{i}.py", f"f{i}", 1, score=1.0 - i / 10) for i in range(4)
    ] + [cand("docs/auth.md", "架构 > Token Refresh", 10, score=0.01, kind="spec")]
    config = BudgetConfig(hard_cap=1_200, framework_overhead=0, single_file_ratio=1.0)

    pack = assemble(store, "为什么这样设计", candidates, config=config)
    assert len(pack.docs) >= 1
    assert pack.docs[0].heading_path == "架构 > Token Refresh"


# --------------------------------------------------------------------------- 去重三招


def test_dedup_adjacent_interval_merge_overlap(store, seed_file, sym, cand) -> None:
    seed_file(
        store,
        path="src/a.py",
        symbols=[sym("one", "one", start=40, end=70), sym("two", "two", start=65, end=90)],
    )
    candidates = [
        cand("src/a.py", "one", 40, score=1.0, end=70),
        cand("src/a.py", "two", 65, score=0.9, end=90),
    ]
    config = BudgetConfig(hard_cap=10_000, framework_overhead=0, single_file_ratio=1.0)
    pack = assemble(store, "q", candidates, config=config)
    assert len(pack.evidence) == 1
    item = pack.evidence[0]
    assert item.lines == (40, 90)
    assert item.elided_lines == 0
    assert "相邻区间合并" in item.reason


def test_dedup_adjacent_interval_merge_counts_gap(store, seed_file, sym, cand) -> None:
    seed_file(
        store,
        path="src/a.py",
        symbols=[sym("one", "one", start=40, end=70), sym("two", "two", start=80, end=90)],
    )
    candidates = [
        cand("src/a.py", "one", 40, score=1.0, end=70),
        cand("src/a.py", "two", 80, score=0.9, end=90),
    ]
    config = BudgetConfig(hard_cap=10_000, framework_overhead=0, single_file_ratio=1.0)
    pack = assemble(store, "q", candidates, config=config)
    assert len(pack.evidence) == 1
    assert pack.evidence[0].lines == (40, 90)
    assert pack.evidence[0].elided_lines == 9  # 71..79


def test_dedup_far_apart_chunks_are_not_merged(store, seed_file, sym, cand) -> None:
    seed_file(
        store,
        path="src/a.py",
        symbols=[sym("one", "one", start=40, end=70), sym("two", "two", start=200, end=210)],
    )
    candidates = [
        cand("src/a.py", "one", 40, score=1.0, end=70),
        cand("src/a.py", "two", 200, score=0.9, end=210),
    ]
    config = BudgetConfig(hard_cap=10_000, framework_overhead=0, single_file_ratio=1.0)
    assert len(assemble(store, "q", candidates, config=config).evidence) == 2


def test_dedup_same_symbol_aggregation(store, seed_file, sym, cand) -> None:
    seed_file(
        store,
        path="src/a.py",
        symbols=[
            sym("run", "Foo.run", start=10, end=20),
            sym("run2", "Foo.run", start=200, end=210),
        ],
    )
    candidates = [
        cand("src/a.py", "Foo.run", 10, score=1.0, end=20),
        cand("src/a.py", "Foo.run", 200, score=0.9, end=210),
    ]
    config = BudgetConfig(hard_cap=10_000, framework_overhead=0, single_file_ratio=1.0)
    pack = assemble(store, "q", candidates, config=config)
    assert len(pack.evidence) == 1
    assert "同符号聚合×1" in pack.evidence[0].reason
    assert pack.budget is not None and pack.budget.omitted_count == 1


def test_dedup_skeleton_degradation_elides_lines(store, seed_file, sym, cand) -> None:
    body = "\n".join(f"line {index}" for index in range(400))
    seed_file(
        store,
        path="src/huge.py",
        symbols=[sym("huge", "huge", start=1, end=400)],
        bodies={"huge": body},
    )
    candidates = [cand("src/huge.py", "huge", 1, score=1.0, end=400)]
    config = BudgetConfig(hard_cap=1_000, framework_overhead=0, single_file_ratio=1.0)

    pack = assemble(store, "q", candidates, config=config)
    item = pack.evidence[0]
    assert item.elided_lines > 0
    assert item.lines == (1, 16)
    assert len(item.content.splitlines()) <= 20


def test_skeleton_degradation_not_triggered_when_budget_allows(store, seed_file, sym, cand) -> None:
    body = "\n".join(f"line {index}" for index in range(400))
    seed_file(
        store,
        path="src/huge.py",
        symbols=[sym("huge", "huge", start=1, end=400)],
        bodies={"huge": body},
    )
    candidates = [cand("src/huge.py", "huge", 1, score=1.0, end=400)]
    config = BudgetConfig(hard_cap=100_000, framework_overhead=0, single_file_ratio=1.0)
    item = assemble(store, "q", candidates, config=config).evidence[0]
    assert item.elided_lines == 0
    assert item.lines == (1, 400)


# --------------------------------------------------------------------------- 判定矩阵


def _pool(cand, *, explicit: int, consensus: int, plain: int, specs: int = 0):
    candidates = []
    for index in range(explicit):
        candidates.append(
            cand(f"src/e{index}.py", f"e{index}", 1, score=1.0,
                 channels={"exact": 1, "bm25": 1, "vector": 1})
        )
    for index in range(consensus):
        candidates.append(
            cand(f"src/c{index}.py", f"c{index}", 1, score=0.8, channels={"bm25": 1, "vector": 1})
        )
    for index in range(plain):
        candidates.append(
            cand(f"src/p{index}.py", f"p{index}", 1, score=0.5, channels={"bm25": 1})
        )
    for index in range(specs):
        candidates.append(
            cand(f"docs/s{index}.md", f"h{index}", 1, score=0.4, kind="spec",
                 channels={"bm25": 1})
        )
    return candidates


@pytest.mark.parametrize(
    "explicit,consensus,plain,specs,structural,graph_boundary,answerable,confidence",
    [
        (1, 3, 0, 0, False, False, True, "high"),      # explicit + ≥3 共识
        (1, 1, 0, 0, False, False, True, "low"),       # explicit 但共识不足 → 其余
        (1, 3, 0, 0, False, True, True, "low"),        # graph_boundary 阻断 high
        (0, 1, 1, 0, False, False, False, "medium"),   # 有共识无 explicit
        (0, 0, 2, 0, False, False, False, "low"),      # 仅单通道
        (0, 2, 0, 0, False, False, True, "medium"),    # 双通道共识 ≥2 → answerable
        (0, 0, 0, 0, True, False, True, "low"),        # 结构路由非空（接口预留）
    ],
)
def test_answerable_confidence_matrix(
    store, seed_file, sym, cand,
    explicit, consensus, plain, specs, structural, graph_boundary, answerable, confidence,
) -> None:
    for index in range(max(explicit, consensus, plain)):
        _long(store, seed_file, sym, f"src/x{index}.py", f"x{index}", 1, 40)
    candidates = _pool(cand, explicit=explicit, consensus=consensus, plain=plain, specs=specs)
    config = BudgetConfig(hard_cap=100_000, framework_overhead=0, single_file_ratio=1.0)
    pack = assemble(
        store, "q", candidates, config=config,
        structural_result=structural, graph_boundary=graph_boundary,
    )
    assert pack.answerable is answerable
    assert pack.confidence == confidence


def test_spec_only_hit_is_medium_confidence(store, seed_file, sym, cand) -> None:
    seed_file(
        store,
        path="docs/auth.md",
        language="markdown",
        spec_blocks=[_spec_block("docs/auth.md", "Token Refresh")],
    )
    candidates = [cand("docs/auth.md", "架构 > Token Refresh", 10, score=0.4, kind="spec")]
    pack = assemble(store, "q", candidates)
    assert pack.answerable is False
    assert pack.confidence == "medium"


# --------------------------------------------------------------------------- 缺失证据与 nextQueries


def test_missing_evidence_from_freshness_and_signals(store, seed_file, sym, cand) -> None:
    _long(store, seed_file, sym, "src/a.py", "f", 1, 40)
    freshness = Freshness(indexed_at=100, stale_files=("src/a.py",), indexing_files=("src/b.py",))
    pack = assemble(
        store,
        "q",
        [cand("src/a.py", "f", 1, score=1.0)],
        freshness=freshness,
        signals=IndexSignals(unresolved_count=3),
    )
    codes = [item.code for item in pack.missing_evidence]
    assert codes == ["index_stale", "indexing_pending", "unresolved_reference"]
    assert "缺" in pack.missing_evidence[0].message or "落后" in pack.missing_evidence[0].message


def test_missing_evidence_stale_doc_reference(store, seed_file, sym, cand) -> None:
    seed_file(
        store,
        path="src/auth/token_service.py",
        symbols=[sym("refresh", "TokenService.refresh", kind="method", start=45)],
    )
    seed_file(
        store,
        path="docs/auth.md",
        language="markdown",
        spec_blocks=[_spec_block("docs/auth.md", "Token Refresh")],
    )
    store.add_spec_refs(
        [
            (
                "docs/auth.md:架构 > Token Refresh:10",
                "src/auth/token_service.py:TokenService.refresh:45",
            )
        ]
    )
    store.apply_deletions(["src/auth/token_service.py"])

    spec = cand("docs/auth.md", "架构 > Token Refresh", 10, score=0.4, kind="spec")
    signals = collect_index_signals(store, [spec])
    assert signals.stale_doc_refs == {
        "docs/auth.md:架构 > Token Refresh:10": ("TokenService.refresh",)
    }
    pack = assemble(store, "q", [spec], signals=signals)
    codes = [item.code for item in pack.missing_evidence]
    assert "stale_doc_reference" in codes
    stale = next(item for item in pack.missing_evidence if item.code == "stale_doc_reference")
    assert stale.symbol == "TokenService.refresh"
    assert pack.docs[0].stale_refs == ("TokenService.refresh",)


def test_missing_evidence_retrieval_truncated(store, seed_file, sym, cand) -> None:
    for index in range(3):
        _long(store, seed_file, sym, f"src/f{index}.py", f"f{index}", 1, 400)
    candidates = [cand(f"src/f{i}.py", f"f{i}", 1, score=1.0 - i / 10) for i in range(3)]
    config = BudgetConfig(hard_cap=200, framework_overhead=0, single_file_ratio=1.0)
    pack = assemble(store, "q", candidates, config=config)
    assert "retrieval_truncated" in [item.code for item in pack.missing_evidence]


def test_next_queries_are_deterministic_and_bounded(store, seed_file, sym, cand) -> None:
    _long(store, seed_file, sym, "src/auth/token_service.py", "TokenService.refresh", 1, 40)
    candidates = [cand("src/auth/token_service.py", "TokenService.refresh", 1, score=1.0)]
    first = assemble(store, "q", candidates)
    second = assemble(store, "q", candidates)
    assert first.next_queries == second.next_queries
    assert 1 <= len(first.next_queries) <= 3
    assert "refresh 的调用方有哪些" in first.next_queries


def test_e_numbering_is_shared_between_evidence_and_docs(store, seed_file, sym, cand) -> None:
    seed_file(store, path="src/a.py", symbols=[sym("f", "f", start=1)])
    seed_file(
        store,
        path="docs/auth.md",
        language="markdown",
        spec_blocks=[_spec_block("docs/auth.md", "Token Refresh")],
    )
    candidates = [
        cand("src/a.py", "f", 1, score=1.0),
        cand("docs/auth.md", "架构 > Token Refresh", 10, score=0.5, kind="spec"),
    ]
    pack = assemble(store, "q", candidates)
    ids = [item.id for item in pack.evidence] + [item.id for item in pack.docs]
    assert ids == ["E1", "E2"]
    assert pack.docs[0].id == "E2"


def test_index_signals_without_store_inputs(store, seed_file, sym, cand) -> None:
    _long(store, seed_file, sym, "src/a.py", "f", 1, 40)
    signals = collect_index_signals(store, [cand("src/a.py", "f", 1, score=1.0)])
    assert signals.unresolved_count == 0
    assert dict(signals.stale_doc_refs) == {}


# --------------------------------------------------------------------------- 性能


def test_assembly_under_200ms_for_200_candidates(store, seed_file, sym, cand) -> None:
    for index in range(20):
        seed_file(
            store,
            path=f"src/mod{index}.py",
            symbols=[sym(f"f{index}_{j}", f"f{index}_{j}", start=j * 20 + 1)
                     for j in range(10)],
        )
    candidates = [
        cand(f"src/mod{index}.py", f"f{index}_{j}", j * 20 + 1, score=1.0 - (index * 10 + j) / 1000)
        for index in range(20)
        for j in range(10)
    ]
    assert len(candidates) == 200

    started = time.perf_counter()
    pack = assemble(store, "token 刷新", candidates, config=BudgetConfig(hard_cap=10_000))
    elapsed_ms = (time.perf_counter() - started) * 1000
    # 阈值 50ms 在多泳道并发跑测试时会误报（编排者实测 3 泳道并发失败 1 次，TASK-017）；
    # 放宽到 200ms 仍保留性能下限回归保护（断言不删）。
    assert elapsed_ms < 200, f"组装耗时 {elapsed_ms:.1f}ms ≥ 200ms"
    assert pack.evidence
