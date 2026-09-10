"""TASK-010 BM25 通道（DoD：中文查询 segment 后命中；FTS 原始分方向）。"""

from __future__ import annotations

from zace_core.retrieval.bm25 import bm25_query_text, recall_bm25
from zace_core.retrieval.fusion import CHANNEL_BM25, TIER_SEED


def test_chinese_query_hits_after_segmentation(store, seed_file, sym) -> None:
    """中文一等场景（D-20/D-45）：查询侧与索引侧同一分词器。"""
    seed_file(
        store,
        path="src/auth/token_service.py",
        symbols=[sym("refresh", "TokenService.refresh", kind="method", start=45)],
        bodies={
            "TokenService.refresh": (
                "def refresh(self):\n"
                "    # token 过期 后 刷新 refresh_token\n"
                "    return self.store.rotate()\n"
            )
        },
    )
    seed_file(
        store,
        path="src/ui/refresh_panel.py",
        symbols=[sym("refreshPanel", "refreshPanel", start=3)],
        bodies={"refreshPanel": "def refreshPanel():\n    return 'ui only'\n"},
    )

    candidates = recall_bm25(store, "token 过期 刷新", limit=50)
    assert [c.chunk_id for c in candidates] == ["src/auth/token_service.py:TokenService.refresh:45"]
    assert candidates[0].tier == TIER_SEED
    assert candidates[0].channel_ranks == {CHANNEL_BM25: 1}
    assert any("bm25" in reason for reason in candidates[0].reasons)


def test_identifier_query_hits(store, seed_file, sym) -> None:
    seed_file(
        store,
        path="src/a.py",
        symbols=[sym("rotate", "TokenStore.rotate", start=210)],
        bodies={"TokenStore.rotate": "def rotate(self):\n    return refresh_token\n"},
    )
    candidates = recall_bm25(store, "TokenStore.rotate", limit=50)
    assert candidates and candidates[0].chunk_id == "src/a.py:TokenStore.rotate:210"


def test_ranks_follow_bm25_order(store, seed_file, sym) -> None:
    """FTS 原始分越小越相关 → 排名 1..N 按该顺序（方向不得反转）。"""
    seed_file(
        store,
        path="src/noise.py",
        symbols=[sym("noise", "noise", start=1)],
        bodies={"noise": "def noise():\n    return 'refresh_token once'\n"},
    )
    seed_file(
        store,
        path="src/hit.py",
        symbols=[sym("hit", "hit", start=1)],
        bodies={"hit": "def hit():\n    refresh_token refresh_token refresh_token\n"},
    )
    candidates = recall_bm25(store, "refresh_token", limit=50)
    assert [c.channel_ranks[CHANNEL_BM25] for c in candidates] == list(
        range(1, len(candidates) + 1)
    )
    assert candidates[0].chunk_id == "src/hit.py:hit:1"


def test_limit_respected(store, seed_file, sym) -> None:
    for index in range(5):
        seed_file(
            store,
            path=f"src/f{index}.py",
            symbols=[sym(f"f{index}", f"f{index}", start=1)],
            bodies={f"f{index}": "def f():\n    refresh_token\n"},
        )
    assert len(recall_bm25(store, "refresh_token", limit=2)) == 2


def test_empty_query_returns_empty(store) -> None:
    assert recall_bm25(store, "", limit=50) == []
    assert recall_bm25(store, "   ", limit=50) == []


def test_bm25_query_text_strips_explicit_noise() -> None:
    assert bm25_query_text("`refresh_token`") == " refresh_token "
    assert bm25_query_text("TokenService::refresh") == "TokenService refresh"


def test_backticked_symbol_query_still_hits(store, seed_file, sym) -> None:
    """反引号/``::`` 不得让整条查询失配（jieba 会把它们切成正文给不出的 token）。"""
    seed_file(
        store,
        path="src/auth/token_service.py",
        symbols=[sym("refresh", "TokenService.refresh", kind="method", start=45)],
        bodies={"TokenService.refresh": "def refresh(self):\n    return refreshToken\n"},
    )
    assert [c.chunk_id for c in recall_bm25(store, "`TokenService::refresh`", limit=50)] == [
        "src/auth/token_service.py:TokenService.refresh:45"
    ]


def test_generated_files_are_not_excluded_here(store, seed_file, sym) -> None:
    """Module/02 §4.2-b：generated 文件不排除（降权是 TASK-011 rerank 的事）。"""
    seed_file(
        store,
        path="src/proto_generated.py",
        symbols=[sym("gen", "gen", start=1)],
        bodies={"gen": "def gen():\n    refresh_token\n"},
    )
    candidates = recall_bm25(store, "refresh_token", limit=50)
    assert [c.chunk_id for c in candidates] == ["src/proto_generated.py:gen:1"]
