"""pipeline：索引流水线（TASK-007）。

子模块分工：

- ``indexer``：``Indexer``（ChangeSet → 增量失效 → 向量对账）+ ``IngestReport``；
- ``source``：``SourceProvider`` 协议与目录实现（全量重解析 / 存量向量重建的输入）。
"""

from zace_core.pipeline.indexer import (
    CPP_EXTENSIONS,
    H_EXTENSION,
    LANGUAGES_KEY,
    Indexer,
    IngestReport,
)
from zace_core.pipeline.source import (
    DEFAULT_SKIP_DIRS,
    DirectorySource,
    SourcePathError,
    SourceProvider,
)

__all__ = [
    "CPP_EXTENSIONS",
    "DEFAULT_SKIP_DIRS",
    "H_EXTENSION",
    "LANGUAGES_KEY",
    "DirectorySource",
    "Indexer",
    "IngestReport",
    "SourcePathError",
    "SourceProvider",
]
