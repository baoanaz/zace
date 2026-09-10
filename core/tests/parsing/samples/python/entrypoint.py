"""TASK-002 语料：__main__ 入口与模块级调用归属（owner = 文件 path）。"""

from __future__ import annotations


def main(argv: list[str]) -> int:
    return 0 if argv else 1


def _internal_helper() -> None:
    print("internal")


if __name__ == "__main__":
    raise SystemExit(main([]))
