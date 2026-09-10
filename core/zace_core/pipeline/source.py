"""SourceProvider：流水线内部的源码读取契约（TASK-007 自定）。

边界：

- 流水线只依赖 ``read(path) -> bytes`` 与 ``list_files() -> Sequence[str]``；
  ``list_files`` 是 ``full_reparse``（遍历全部文件重跑增量）与 ``reembed``（枚举存量 chunk）
  的必需能力——任务卡只列了 ``read``，此处按卡内"遍历 SourceProvider 全部文件"的要求补齐，
  并在执行记录里作为 pipeline 内契约记录。
- CLI（TASK-013）提供 :class:`DirectorySource`（repo 目录）；Phase 2 service 提供 blobs 实现
  （按上传目录/DB 列举，本卡不实现，只保证协议够用）。
- 忽略规则（.zaceignore/.gitignore，D-28）归 TASK-013/Phase 2：它们可以传自己的 provider，
  或构造 :class:`DirectorySource` 后按需过滤 ``list_files()`` 结果。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = [
    "DEFAULT_SKIP_DIRS",
    "DirectorySource",
    "SourceProvider",
    "SourcePathError",
]


class SourcePathError(ValueError):
    """路径不是安全的仓库相对路径（绝对路径 / 越界 ``..`` / 反斜杠）。"""


@runtime_checkable
class SourceProvider(Protocol):
    """源码读取（pipeline 内部契约）。"""

    def read(self, path: str) -> bytes:
        """读取仓库相对路径 ``path`` 的原始字节；不存在时抛 ``FileNotFoundError``。"""
        ...

    def list_files(self) -> Sequence[str]:
        """列出全部可用文件（仓库相对路径，正斜杠，稳定排序）。"""
        ...


#: 目录扫描默认跳过的目录名（工程噪声；忽略规则细化归 TASK-013）。
DEFAULT_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".eggs",
        "dist",
        "build",
        "target",
        ".idea",
        ".vscode",
        ".zace",
    }
)


class DirectorySource:
    """``repo 目录`` 实现：``root`` 下的文件即源码，路径一律仓库相对、正斜杠。"""

    def __init__(
        self,
        root: str | Path,
        *,
        skip_dirs: frozenset[str] = DEFAULT_SKIP_DIRS,
    ) -> None:
        self._root = Path(root)
        self._skip_dirs = skip_dirs

    @property
    def root(self) -> Path:
        return self._root

    def read(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def list_files(self) -> tuple[str, ...]:
        root = self._root
        if not root.is_dir():
            return ()
        found: list[str] = []
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(root)
            if any(part in self._skip_dirs for part in relative.parts[:-1]):
                continue
            found.append(relative.as_posix())
        return tuple(sorted(found))

    def _resolve(self, path: str) -> Path:
        if not path or path.startswith("/") or "\\" in path:
            raise SourcePathError(f"非法仓库相对路径：{path!r}")
        parts = path.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise SourcePathError(f"非法仓库相对路径：{path!r}")
        return self._root.joinpath(*parts)
