"""TASK-002 语料：模块级符号 + 类/继承 + 模块级调用归属。"""

from __future__ import annotations

import os  # noqa: F401

MODULE_CONSTANT: int = 42
PLAIN_NAME = "unannotated assignment is not a symbol"

os.getcwd()


def top_level(value: int) -> int:
    """带注解的模块级函数。"""
    return helper(value) + MODULE_CONSTANT


async def fetch(url: str) -> str:
    """async 函数也是 function_definition。"""
    return await load(url)  # noqa: F821  故意未定义：跨文件调用交 TASK-006


def helper(value: int) -> int:
    return value * 2


class BaseService:
    """基类。"""


class Service(BaseService):
    """继承 BaseService；方法 kind=method。"""

    def run(self, key: str) -> str:
        return self.transform(key)

    def transform(self, key: str) -> str:
        return key.upper()
