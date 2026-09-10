"""``zace-service`` 命令行入口（TASK-030 §交付物；console script 见 ``service/pyproject.toml``）。

风格与 core CLI（``zace_core/cli/app.py``）一致：argparse + ``main() -> int``。

```text
zace-service [--host H] [--port N] [--data-root PATH] [--log-level LEVEL] [--reload]
```

- 参数缺省值来自 :class:`~zace_service.config.Settings`（即 ``ZACE_DATA_ROOT`` /
  ``ZACE_LOCAL_MODE`` 等环境变量），命令行显式给出时优先；
- ``--reload`` 是开发便利开关：uvicorn 的 reload 需要 import string，此时子进程从
  **环境变量**重建配置（``ZACE_DATA_ROOT`` 由本函数写入），因此 ``--log-level`` 只作用于
  uvicorn 自身日志，服务自身 JSON 日志沿用默认 ``info``；
- uvicorn 自带 access log 关闭（``access_log=False``）：访问日志由 middleware 以 JSON 输出，
  避免 stderr 上出现两套格式、也避免 uvicorn 记录带 query string 的 URL。
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import uvicorn

from zace_service.app import create_app
from zace_service.config import DATA_ROOT_ENV, Settings

__all__ = ["build_parser", "main"]

PROG = "zace-service"
LOG_LEVELS = ("critical", "error", "warning", "info", "debug", "trace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="zace 服务化外壳（M2a 本地单用户模式：无鉴权、绑 127.0.0.1）",
    )
    parser.add_argument("--host", default=None, help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认 8787）")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help=f"数据根目录（默认 ${DATA_ROOT_ENV} 或 ~/.zace）",
    )
    parser.add_argument(
        "--log-level", default=None, choices=LOG_LEVELS, help="日志级别（默认 info）"
    )
    parser.add_argument("--reload", action="store_true", help="代码变更自动重启（开发用）")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """启动 uvicorn（前台阻塞）。"""
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    base = Settings.from_env()
    settings = replace(
        base,
        host=args.host or base.host,
        port=args.port or base.port,
        data_root=args.data_root or base.data_root,
        log_level=args.log_level or base.log_level,
    )
    if args.reload:
        os.environ[DATA_ROOT_ENV] = str(settings.data_root)
        uvicorn.run(
            "zace_service.app:create_app",
            factory=True,
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level,
            access_log=False,
            reload=True,
        )
        return 0
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        access_log=False,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - 手工入口
    raise SystemExit(main())
