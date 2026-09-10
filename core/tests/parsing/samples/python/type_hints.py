"""TASK-002 语料：泛型基类 / Protocol / 模块级带注解 assignment。"""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar

T = TypeVar("T")

Registry: dict[str, int] = {}


class Store(Generic[T]):  # noqa: UP046  经典 Generic[T]：验证 subscript 下钻
    """泛型基类：extends 目标是 Generic（下钻 subscript）。"""

    def get(self) -> T | None:
        raise NotImplementedError


class Handler(Protocol):
    def handle(self, payload: str) -> None: ...


class SpecializedStore(Store[str]):
    def get(self) -> str | None:
        return None
