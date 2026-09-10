"""BM25 通道（TASK-010）：FTS5 词法召回 + CJK 双侧同分词。

设计依据：``docs/design/Module/02-检索策略.md`` §4.2-b（D-20 / D-45）：

- 配额 top 50；查询串必须经 :func:`zace_core.text.segment`（与索引侧同一分词器）；
- 多 token 采用 **OR 连接**（R11，2026-09-10 集成期裁定）：中文自然语言查询分词后
token 多，隐式 AND 会恒零命中；高精度需求由 ``Store.fts_search(operator="and")`` 显式选择；
- FTS 返回**原始 bm25 分（越小越相关，列权重见 `FTS_COLUMN_WEIGHTS`）并已按它升序**——
本模块把它转成 1-based 排名；
- generated 文件不在此排除（rerank 降权是 TASK-011 的事，D-02/Module/02 §4.2-b）。
"""

from __future__ import annotations

from zace_core.retrieval.fusion import CHANNEL_BM25, TIER_SEED, make_candidate
from zace_core.storage import Store
from zace_core.text import segment
from zace_core.types import Candidate

__all__ = ["REASON_BM25", "bm25_query_text", "recall_bm25"]

REASON_BM25 = "bm25"


def bm25_query_text(query: str) -> str:
    """BM25 侧查询归一化（L1 实现细节，不改分词器）：去反引号、``::`` 与 ``::`` 残留替换为空格。

    理由：jieba 会把 `` ` `` 与 ``:`` 切成独立 token，而正文里没有这些 token。OR 语义下
    噪声 token 虽不再让整条查询失配，却会**无差别扩大候选**（正文里的 ``:`` 到处都是），
    显式符号链查询（``TokenService::refresh``）尤其明显。其它通道与渲染一律用原文，
    本归一化只作用于 BM25 的 MATCH 串。
    """
    return query.replace("`", " ").replace("::", " ")


def recall_bm25(store: Store, query: str, *, limit: int = 50) -> list[Candidate]:
    """BM25 召回：``segment(bm25_query_text(query))`` → ``Store.fts_search`` → 排名候选（tier 1）。

    空查询/全空白分词结果 → 空列表（不抛异常）。FTS 原始分仅写进 ``reasons`` 供解释，
    不进 RRF（D-16：融合层只用排名，不用分数）。
    """
    segmented = segment(bm25_query_text(query))
    if not segmented.strip():
        return []
    hits = store.fts_search(segmented, limit=limit)
    return [
        make_candidate(
            chunk_id,
            channel=CHANNEL_BM25,
            rank=rank,
            tier=TIER_SEED,
            reason=f"{REASON_BM25} {raw_score:.4f}",
        )
        for rank, (chunk_id, raw_score) in enumerate(hits, start=1)
    ]
