"""TASK-002：兜底切分测试（800 行上限 / 不丢字符 / 确定性）。"""

from __future__ import annotations

from zace_core.parsing.fallback import (
    FALLBACK_MAX_CHARS,
    FALLBACK_MAX_LINES,
    FallbackBlock,
    split_fallback,
)


def joined(blocks: tuple[FallbackBlock, ...]) -> str:
    return "".join(block.content for block in blocks)


def test_empty_content() -> None:
    assert split_fallback("") == ()


def test_single_block_line_range() -> None:
    content = "a\nb\nc\n"
    blocks = split_fallback(content)
    assert len(blocks) == 1
    block = blocks[0]
    assert (block.index, block.start_line, block.end_line) == (1, 1, 3)
    assert block.content == content


def test_default_budget_constants() -> None:
    assert FALLBACK_MAX_LINES == 800
    assert FALLBACK_MAX_CHARS > FALLBACK_MAX_LINES  # 字符阀只针对单行巨型输入


def test_long_file_respects_line_budget_and_keeps_content() -> None:
    content = "".join(f"line {index}\n" for index in range(2000))
    blocks = split_fallback(content)
    assert len(blocks) >= 3  # 2000 行 / 800 上限
    assert joined(blocks) == content
    assert [block.index for block in blocks] == list(range(1, len(blocks) + 1))
    for block in blocks:
        assert block.end_line - block.start_line + 1 <= FALLBACK_MAX_LINES
    assert blocks[0].start_line == 1
    assert blocks[-1].end_line == 2000


def test_paragraph_boundary_preferred() -> None:
    paragraph_a = "".join(f"a{index}\n" for index in range(500))
    paragraph_b = "".join(f"b{index}\n" for index in range(500))
    paragraph_c = "".join(f"c{index}\n" for index in range(500))
    content = paragraph_a + "\n" + paragraph_b + "\n" + paragraph_c
    blocks = split_fallback(content)
    assert [block.content for block in blocks] == [
        paragraph_a + "\n",
        paragraph_b + "\n",
        paragraph_c,
    ]


def test_oversized_single_line_is_hard_sliced() -> None:
    content = "x" * (FALLBACK_MAX_CHARS * 2 + 10)
    blocks = split_fallback(content)
    assert len(blocks) == 3
    assert joined(blocks) == content
    assert all(len(block.content) <= FALLBACK_MAX_CHARS for block in blocks)
    assert all((block.start_line, block.end_line) == (1, 1) for block in blocks)


def test_custom_budget() -> None:
    content = "".join(f"{index}\n" for index in range(10))
    blocks = split_fallback(content, max_lines=2)
    assert len(blocks) == 5
    assert joined(blocks) == content
    for block in blocks:
        assert block.end_line - block.start_line + 1 <= 2


def test_deterministic() -> None:
    content = "".join(f"line {index}\n" for index in range(1000))
    assert split_fallback(content) == split_fallback(content)
