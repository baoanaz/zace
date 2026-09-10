"""TASK-002 语料：装饰器（跟随函数进 chunk，start_line 含装饰器）。"""

from __future__ import annotations

from functools import wraps


def traced(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


@traced
def decorated() -> str:
    return "decorated"


@traced
class Decorated:
    """类装饰器同样计入 start_line。"""


class Container:
    @staticmethod
    def build() -> Decorated:
        return Decorated()

    @classmethod
    def create(cls) -> Container:
        return cls()

    @property
    def name(self) -> str:
        return "container"
