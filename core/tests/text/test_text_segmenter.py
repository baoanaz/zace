"""jieba 预分词器行为（D-45：索引/查询同一函数）。"""

from __future__ import annotations

from zace_core.text import segment


def test_cjk_tokens_are_space_separated() -> None:
    result = segment("刷新令牌")
    assert result == "刷新 令牌"


def test_segmentation_is_idempotent_for_spaced_output() -> None:
    once = segment("刷新令牌的过期时间")
    assert segment(once) == once


def test_mixed_chinese_and_identifier() -> None:
    # jieba 默认按下划线切标识符（'refresh_token' → refresh/_/token）；
    # FTS unicode61 侧同样以下划线为分隔符，索引/查询两侧 token 空间一致。
    tokens = segment("refresh_token 过期后如何刷新").split()
    assert "refresh" in tokens and "token" in tokens
    assert "过期" in tokens
    assert "刷新" in tokens


def test_empty_inputs() -> None:
    assert segment("") == ""
    assert segment("   \n\t ") == ""


def test_no_blank_tokens() -> None:
    tokens = segment("def f():  # 刷新 令牌\n    return None\n").split()
    assert tokens and all(token.strip() for token in tokens)
