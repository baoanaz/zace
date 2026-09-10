"""TASK-002 语料：动态特性如实进 unresolved（不猜）。"""

from __future__ import annotations

import importlib


class Client:
    def send(self, payload: str) -> str:
        handler = getattr(self, "handle_payload")  # noqa: B009  动态特性语料
        handler(payload)
        target = "handle_payload"
        getattr(self, target)(payload)
        self.registry[0](payload)
        (lambda: handler)(payload)
        module = importlib.import_module("json")
        other = importlib.import_module(name="os.path")
        __import__("sys")
        return module.__name__ + other.__name__


def call_by_string() -> None:
    "handler"()
