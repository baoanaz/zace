"""CJK 预分词器：FTS5 unicode61 的中文修正（D-20 / D-45）。

背景（Module/02 §4.2-b）：unicode61 tokenizer 对连续中文不分词（整段成为一个 token），
中文查询直接失效。裁定方案：索引侧写入 FTS 前先分词、空格连接；查询侧用同一函数
预处理后再交给 ``Store.fts_search``。分词器与存储解耦（本模块不依赖 SQLite）。

实现约束：
- jieba 惰性初始化（首次调用才建词典），import 本模块无副作用、无日志噪音；
- 精确模式（默认 lcut），不做大小写/全半角归一化——归一化归 FTS unicode61。
"""

from __future__ import annotations

import logging
from types import ModuleType

__all__ = ["segment"]

_jieba: ModuleType | None = None


def _load_jieba() -> ModuleType:
    global _jieba
    if _jieba is None:
        import jieba

        jieba.setLogLevel(logging.ERROR)  # 遮蔽 "Building prefix dict ..." 等日志
        _jieba = jieba
    return _jieba


def segment(text: str) -> str:
    """jieba 精确模式分词并以空格连接；索引侧与查询侧必须调用本函数（D-45）。

    - 空白输入返回 ``""``（调用方按空查询处理）；
    - 输出 token 间恒为单空格，token 内不含空白；
    - 对未登录词/英文标识符 jieba 原样保留，FTS unicode61 再按自身规则切分。
    """
    if not text or not text.strip():
        return ""
    jieba = _load_jieba()
    return " ".join(token for token in jieba.cut(text) if token.strip())
