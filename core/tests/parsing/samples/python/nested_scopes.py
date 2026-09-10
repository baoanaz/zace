"""TASK-002 语料：嵌套函数/嵌套类/lambda/推导式里的调用归属。"""

from __future__ import annotations


def outer(seed: int) -> int:
    def inner(value: int) -> int:
        return value + seed

    class Inner:
        def method(self) -> int:
            return inner(seed)

    items = [inner(i) for i in range(seed)]
    double = lambda x: inner(x)  # noqa: E731
    return sum(items) + double(seed) + Inner().method()


class Outer:
    """方法里的嵌套函数 fqn = Outer.method.nested。"""

    def method(self) -> int:
        def nested() -> int:
            return 1

        return nested()
