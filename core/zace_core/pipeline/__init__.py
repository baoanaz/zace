"""pipeline：索引流水线（TASK-007）。

子模块分工：

- ``indexer``：``Indexer``（ChangeSet → 增量失效 → 向量对账）+ ``IngestReport``；
- ``source``：``SourceProvider`` 协议与目录实现（全量重解析 / 存量向量重建的输入）；
- ``ignore``：三层忽略规则（``.zaceignore`` > ``.gitignore`` > 内置）与大小/二进制阈值
  （TASK-037 / D-28 / R42-R43）。
"""

from zace_core.pipeline.ignore import (
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_SKIP_DIR_PATTERNS,
    DEFAULT_SKIP_DIRS,
    IgnoreRules,
    IndexScope,
)
from zace_core.pipeline.indexer import (
    CPP_EXTENSIONS,
    H_EXTENSION,
    LANGUAGES_KEY,
    Indexer,
    IngestReport,
)
from zace_core.pipeline.source import (
    DirectorySource,
    SourcePathError,
    SourceProvider,
)

__all__ = [
    "CPP_EXTENSIONS",
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_SKIP_DIRS",
    "DEFAULT_SKIP_DIR_PATTERNS",
    "DirectorySource",
    "H_EXTENSION",
    "IgnoreRules",
    "IndexScope",
    "Indexer",
    "IngestReport",
    "LANGUAGES_KEY",
    "SourcePathError",
    "SourceProvider",
]
