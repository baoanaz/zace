#!/usr/bin/env python3
"""golden runner 独立入口（TASK-013 §C）。

与 ``zace-core eval`` 是**同一份实现**（``zace_core.cli.eval``），本文件只做参数透传，
避免诞生第二套命中判定口径（``benches/README.md`` 的"同一用例集在不同机器上复现同一口径"）。

```bash
uv run python benches/run.py --golden benches/golden --repo . --report benches/results/phase1.md
# 等价于
uv run zace-core eval --golden benches/golden --repo . --report benches/results/phase1.md
```
"""

from __future__ import annotations

import sys
from pathlib import Path

#: 仓库根（本文件的上一级）。
ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    """把 ``benches/run.py`` 的参数原样转给 ``zace-core eval``。"""
    core = ROOT / "core"
    if core.is_dir() and str(core) not in sys.path:
        # 未安装 zace-core 的裸 venv 里也能直接跑（安装环境下这行是空操作）。
        sys.path.insert(0, str(core))
    from zace_core.cli.app import main as cli_main

    return cli_main(["eval", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(main())
