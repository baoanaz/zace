"""中文 FTS：索引/查询双侧同一分词器（D-20 / D-45）+ bm25 语义。"""

from __future__ import annotations

from collections.abc import Callable

from zace_core.storage import Store
from zace_core.text import segment
from zace_core.types import ChunkDef, ParsedFile


def test_chinese_query_hits_only_after_segmentation(
    store: Store, make_parsed: Callable[..., ParsedFile], make_chunk: Callable[..., ChunkDef]
) -> None:
    chunk = make_chunk(
        fqn="refresh",
        content="def refresh():\n    # 刷新令牌的过期时间\n    return None\n",
        docstring="刷新令牌的过期逻辑",
    )
    store.apply_file_change(make_parsed(), [chunk], "file-hash-1")

    hits = store.fts_search(segment("刷新令牌"), 10)
    assert [chunk_id for chunk_id, _ in hits] == [chunk.id]
    # 不分词时 unicode61 把整串当一个 token → 不命中（证明是预分词生效，而非 tokenizer 巧合）。
    assert store.fts_search("刷新令牌", 10) == []


def test_chinese_query_matches_english_identifiers_in_content(
    store: Store, make_parsed: Callable[..., ParsedFile], make_chunk: Callable[..., ChunkDef]
) -> None:
    chunk = make_chunk(
        fqn="refresh_token",
        content="def refresh_token():\n    # 令牌刷新\n    pass\n",
    )
    unrelated = make_chunk(fqn="other", start=9, content="def other():\n    pass\n")
    store.apply_file_change(make_parsed(), [chunk, unrelated], "file-hash-1")
    hits = store.fts_search(segment("令牌 refresh_token"), 10)
    assert [chunk_id for chunk_id, _ in hits] == [chunk.id]


def test_bm25_orders_more_relevant_first(
    store: Store, make_parsed: Callable[..., ParsedFile], make_chunk: Callable[..., ChunkDef]
) -> None:
    strong = make_chunk(fqn="a", start=1, content="令牌 令牌 令牌 刷新\n")
    weak = make_chunk(fqn="b", start=5, content="令牌\n")
    store.apply_file_change(make_parsed(), [weak, strong], "file-hash-1")

    hits = store.fts_search(segment("令牌"), 10)
    assert [chunk_id for chunk_id, _ in hits] == [strong.id, weak.id]
    scores = [score for _, score in hits]
    assert all(score < 0 for score in scores)  # bm25 原始分（越小越相关）
    assert scores[0] < scores[1]


def test_limit_and_empty_query(
    store: Store, make_parsed: Callable[..., ParsedFile], make_chunk: Callable[..., ChunkDef]
) -> None:
    chunks = [
        make_chunk(fqn="a", start=1, content="alpha token\n"),
        make_chunk(fqn="b", start=5, content="alpha token again\n"),
    ]
    store.apply_file_change(make_parsed(), chunks, "file-hash-1")
    assert len(store.fts_search(segment("alpha token"), 1)) == 1
    assert store.fts_search("", 10) == []
    assert store.fts_search("   ", 10) == []


def test_update_removes_stale_fts_rows(
    store: Store, make_parsed: Callable[..., ParsedFile], make_chunk: Callable[..., ChunkDef]
) -> None:
    parsed = make_parsed()
    old = make_chunk(fqn="f", content="def f():\n    # 旧注释：缓存预热\n    pass\n")
    store.apply_file_change(parsed, [old], "file-hash-1")
    assert store.fts_search(segment("缓存预热"), 10) != []

    new = make_chunk(fqn="f", content="def f():\n    # 新注释：连接复用\n    pass\n")
    store.apply_file_change(parsed, [new], "file-hash-2")
    assert store.fts_search(segment("缓存预热"), 10) == []
    assert store.fts_search(segment("连接复用"), 10)[0][0] == new.id


def test_fts_syntax_characters_in_query_are_not_operators(
    store: Store, make_parsed: Callable[..., ParsedFile], make_chunk: Callable[..., ChunkDef]
) -> None:
    chunk = make_chunk(fqn="f", content="def f():\n    return a AND b\n")
    store.apply_file_change(make_parsed(), [chunk], "file-hash-1")
    # 引号包裹每个 token：AND/OR/NEAR 之类的字符不会被当成 FTS 语法。
    assert store.fts_search("a AND b", 10)[0][0] == chunk.id
    assert store.fts_search("NOT EXISTS", 10) == []
