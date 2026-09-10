"""zace-service 配置（TASK-030 §交付物）。

设计依据：``docs/design/Module/06-服务化与部署.md`` §2.4（可观测：secret 全部环境变量注入）、
``docs/plan/contracts.md`` §3.8 R34（M2a 本地单用户模式：无鉴权、绑 127.0.0.1）。

口径（本卡冻结，后续卡只读不改）：

- 纯标准库实现（``os.environ`` + ``dataclasses``），**不引入 pydantic-settings**（依赖最小化）；
- ``data_root`` 与 core 的 ``ZACE_DATA_ROOT`` 同名同义（``~/.zace``，core 只管 ``projects/``）；
- ``local_mode`` 默认 ``True``：M2a 为本地单用户模式（R34），鉴权归 M2c（TASK-060/061）；
- 非法布尔值**显式报错**而不是静默取默认——``local_mode`` 决定是否要求鉴权，静默取真会让
  配置写错的人以为安全策略生效（诚实性优先于启动便利）。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from zace_service import __version__

__all__ = [
    "DATA_ROOT_ENV",
    "DEFAULT_DATA_ROOT",
    "DEFAULT_HOST",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_PORT",
    "LOCAL_MODE_ENV",
    "Settings",
]

#: 数据根环境变量（与 core 的 ``zace_core.engine.DATA_ROOT_ENV`` 同名同义）。
DATA_ROOT_ENV = "ZACE_DATA_ROOT"
#: 本地模式环境变量（R34：默认开启，M2c 才关）。
LOCAL_MODE_ENV = "ZACE_LOCAL_MODE"
#: 默认数据根（core 的 ``DEFAULT_DATA_ROOT`` 同值；service 只读 settings，不重复定义语义）。
DEFAULT_DATA_ROOT = Path.home() / ".zace"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_LOG_LEVEL = "info"

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True, slots=True)
class Settings:
    """服务运行配置（不可变；测试用 ``dataclasses.replace`` 派生变体）。"""

    data_root: Path = DEFAULT_DATA_ROOT
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    log_level: str = DEFAULT_LOG_LEVEL
    local_mode: bool = True
    version: str = __version__

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """从环境变量构造配置（缺省即本卡默认值）。"""
        source: Mapping[str, str] = os.environ if env is None else env
        raw_root = source.get(DATA_ROOT_ENV)
        return cls(
            data_root=Path(raw_root).expanduser() if raw_root else DEFAULT_DATA_ROOT,
            local_mode=_as_bool(source.get(LOCAL_MODE_ENV), LOCAL_MODE_ENV, default=True),
        )


def _as_bool(raw: str | None, name: str, *, default: bool) -> bool:
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    raise ValueError(f"环境变量 {name} 必须是布尔值（{sorted(_TRUTHY | _FALSY)}），收到 {raw!r}")
