"""TASK-002 语料：__all__ 决定 is_exported；re-export 语义。"""

from __future__ import annotations

from .service import Service, helper

__all__ = ["Service", "helper"]

VERSION: str = "1.0"


def public_api() -> str:
    return helper("x")
