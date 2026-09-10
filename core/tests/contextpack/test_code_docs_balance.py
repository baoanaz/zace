"""TASK-021（R21）：装填层 Code/Docs 平衡（code_floor + docs_ratio）的回归测试。

背景（TASK-014 基线实测）：文档密集仓库里，中文行为/路径题的 top-3 常被设计文档占满，
代码证据被完全挤出（`aibox-0004`/`0007`/`0009`/`0012`/`0017` 等）。机制是"文档在 BM25 与
Vector 双通道都强命中 + 文档切片数量放大"，且装填层当时只有 `single_file_ratio`（按文件限），
没有按证据类型的总量约束。

本文件覆盖任务卡 DoD 的四项：
1. `code_floor` 生效：文档吃满预算、贪心循环提前 break 时，仍至少装 N 块代码证据；
2. `docs_ratio` 上限生效：超出的 spec 候选计入 `omittedCount`、`truncated=True`，
   并在 `missingEvidence.retrieval_truncated` 里如实说明；
3. 无代码候选时不伤害纯文档包（spec 保底 + 份额上限不生效）；
4. `chunk_id` 去重（TASK-019 回归不破）与预算不变量。
"""

from __future__ import annotations

from dataclasses import replace

from zace_core.contextpack import BudgetConfig, assemble, estimate_tokens
from zace_core.types import SpecBlockDef

SPEC_PATH = "docs/design.md"


def _spec_block(path: str, heading_path: str, *, start: int, end: int, chars: int) -> SpecBlockDef:
    """构造指定行区间与正文长度的 spec 块（正文 = ``chars`` 个字符，单行）。"""
    return SpecBlockDef(
        path=path,
        heading=heading_path.rsplit(" > ", 1)[-1],
        heading_path=heading_path,
        level=2,
        start_line=start,
        end_line=end,
        content="设计" * (chars // 2),
        doctype="design",
    )


def _seed_specs(store, seed_file, count: int, *, chars: int) -> list[tuple[str, int]]:
    """一个文件里落下 ``count`` 个互不相邻的 spec 块（返回 (heading_path, start) 清单）。

    注意：同一路径多次 ``seed_file`` 会**整文件替换**切片，必须一次性给出全部块。
    """
    blocks = [
        _spec_block(SPEC_PATH, f"架构 > 节{index}", start=10 + index * 20, end=14 + index * 20,
                    chars=chars)
        for index in range(count)
    ]
    seed_file(store, path=SPEC_PATH, language="markdown", spec_blocks=blocks)
    return [(block.heading_path, block.start_line) for block in blocks]


def _code(store, seed_file, sym, path: str, fqn: str, chars: int) -> None:
    seed_file(store, path=path, symbols=[sym(fqn, fqn, start=1, end=1)], bodies={fqn: "x" * chars})


def _docs_tokens(pack) -> int:
    return sum(estimate_tokens(item.content) for item in pack.docs)


def _placed(pack):
    return sorted([*pack.evidence, *pack.docs], key=lambda item: int(item.id[1:]))


def test_code_floor_places_code_when_greedy_breaks_on_oversized_candidate(
    store, seed_file, sym, cand
):
    """代码保底：贪心在“单块过大”的代码候选上 break → 保底补入仍装 ≥code_floor 块较小代码证据。"""
    anchors = _seed_specs(store, seed_file, 3, chars=800)  # 约 201 token/块
    _code(store, seed_file, sym, "src/big.py", "big", 1_600)  # 约 401 token，装不下
    for index in range(2):
        _code(store, seed_file, sym, f"src/s{index}.py", f"s{index}", 300)  # 约 76 token

    candidates = [
        cand(SPEC_PATH, heading, start, score=1.0 - index / 10, kind="spec")
        for index, (heading, start) in enumerate(anchors)
    ]
    candidates.append(cand("src/big.py", "big", 1, score=0.6))
    candidates += [cand(f"src/s{i}.py", f"s{i}", 1, score=0.5 - i / 10) for i in range(2)]
    # docs_ratio=1.0：本用例只验**代码保底**这条腿（份额上限另有用例），
    # 让文档 + 超大代码块把贪心逼到 break，靠保底补入小代码块。
    config = BudgetConfig(
        hard_cap=1_000,
        framework_overhead=0,
        single_file_ratio=1.0,
        docs_ratio=1.0,
        spec_floor=0,
        code_floor=2,
    )

    pack = assemble(store, "q", candidates, config=config)

    assert [item.path for item in pack.evidence] == ["src/s0.py", "src/s1.py"]
    assert pack.budget.truncated is True  # 超大代码块确实被预算挡下
    assert pack.budget.used_tokens <= config.hard_cap

    # 对照：同一候选集把 code_floor 关掉 → 贪心 break 后没有任何代码证据
    off = assemble(store, "q", candidates, config=replace(config, code_floor=0))
    assert off.evidence == []


def test_docs_ratio_caps_spec_share_of_used_budget(store, seed_file, sym, cand):
    """spec 份额上限：超额 spec 计入 omittedCount 并置 truncated，缺口在 missingEvidence 里说明。"""
    anchors = _seed_specs(store, seed_file, 6, chars=500)  # 约 126 token/块
    for index in range(2):
        _code(store, seed_file, sym, f"src/c{index}.py", f"c{index}", 300)

    candidates = [
        cand(SPEC_PATH, heading, start, score=1.0 - index / 10, kind="spec")
        for index, (heading, start) in enumerate(anchors)
    ] + [cand(f"src/c{i}.py", f"c{i}", 1, score=0.4 - i / 10) for i in range(2)]
    config = BudgetConfig(
        hard_cap=1_000,
        framework_overhead=0,
        single_file_ratio=1.0,
        docs_ratio=0.25,
        spec_floor=1,
        code_floor=2,
    )

    pack = assemble(store, "q", candidates, config=config)
    content_budget = config.hard_cap - config.framework_overhead

    assert pack.docs  # 保底 spec 仍在
    assert _docs_tokens(pack) <= config.docs_ratio * content_budget
    assert pack.budget.truncated is True
    assert pack.budget.omitted_count >= 4  # 超份额的 spec 逐条计入，不静默丢弃
    codes = [item.code for item in pack.missing_evidence]
    assert "retrieval_truncated" in codes
    message = next(m.message for m in pack.missing_evidence if m.code == "retrieval_truncated")
    assert "spec 份额上限" in message


def test_spec_floor_wins_over_docs_ratio(store, seed_file, sym, cand):
    """保底优先：保底 spec 自身就超出份额上限时仍装填（否则文档密集查询会一块 spec 都不剩）。"""
    _seed_specs(store, seed_file, 1, chars=500)
    _code(store, seed_file, sym, "src/c.py", "c", 300)
    candidates = [
        cand(SPEC_PATH, "架构 > 节0", 10, score=1.0, kind="spec"),
        cand("src/c.py", "c", 1, score=0.9),
    ]
    config = BudgetConfig(
        hard_cap=1_000, framework_overhead=0, single_file_ratio=1.0, docs_ratio=0.05
    )

    pack = assemble(store, "q", candidates, config=config)

    assert len(pack.docs) == 1
    assert pack.docs[0].path == SPEC_PATH
    assert len(pack.evidence) == 1  # 有代码候选 → docs_ratio 生效，但保底不被它否掉


def test_pure_doc_pack_is_not_hurt_when_pool_has_no_code(store, seed_file, cand):
    """例外条款：池里没有代码候选时 docs_ratio 不生效（纯文档问题不被本卡伤害）。"""
    anchors = _seed_specs(store, seed_file, 6, chars=500)
    candidates = [
        cand(SPEC_PATH, heading, start, score=1.0 - index / 10, kind="spec")
        for index, (heading, start) in enumerate(anchors)
    ]
    config = BudgetConfig(
        hard_cap=1_000,
        framework_overhead=0,
        single_file_ratio=1.0,
        docs_ratio=0.10,  # 若误生效：只能装 1 块 spec
        spec_floor=1,
    )

    pack = assemble(store, "q", candidates, config=config)

    assert len(pack.docs) == 6
    content_budget = config.hard_cap - config.framework_overhead
    assert _docs_tokens(pack) > config.docs_ratio * content_budget
    assert pack.budget.truncated is False
    assert pack.budget.omitted_count == 0


def test_code_floor_does_not_duplicate_chunk_id_or_break_budget(store, seed_file, sym, cand):
    """去重与预算不变量（TASK-019 回归）：保底补入不得重复装同一 chunk_id、E 编号连续。"""
    anchors = _seed_specs(store, seed_file, 3, chars=500)
    for index in range(3):
        _code(store, seed_file, sym, f"src/c{index}.py", f"c{index}", 300)

    candidates = [
        cand(SPEC_PATH, heading, start, score=1.0 - index / 10, kind="spec")
        for index, (heading, start) in enumerate(anchors)
    ] + [cand(f"src/c{i}.py", f"c{i}", 1, score=0.7 - i / 10) for i in range(3)]
    config = BudgetConfig(
        hard_cap=1_000, framework_overhead=0, single_file_ratio=1.0, code_floor=2, docs_ratio=0.5
    )

    pack = assemble(store, "q", candidates, config=config)
    placed = _placed(pack)

    assert len({item.id for item in placed}) == len(placed)  # E 编号唯一
    assert [item.id for item in placed] == [f"E{i}" for i in range(1, len(placed) + 1)]
    spans = {(item.path, item.lines, item.content) for item in placed}
    assert len(spans) == len(placed)  # 无重复块
    assert len(pack.evidence) >= config.code_floor
    assert pack.budget.used_tokens == config.framework_overhead + sum(
        estimate_tokens(item.content) for item in placed
    )
    assert pack.budget.used_tokens <= config.hard_cap
