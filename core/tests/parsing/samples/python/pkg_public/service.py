"""TASK-002 语料：包内子模块（与 __init__.py 组成包结构）。"""

from __future__ import annotations


def helper(text: str) -> str:
    return text.strip()


class Service:
    def run(self) -> str:
        return helper("x")
