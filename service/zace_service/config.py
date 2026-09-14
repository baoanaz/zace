"""zace-service 配置（TASK-030 §交付物）。

设计依据：``docs/design/Module/06-服务化与部署.md`` §2.4（可观测：secret 全部环境变量注入）、
``docs/plan/contracts.md`` §3.8 R34（M2a 本地单用户模式：无鉴权、绑 127.0.0.1）。

口径（本卡冻结，后续卡只读不改）：

- 纯标准库实现（``os.environ`` + ``dataclasses``），**不引入 pydantic-settings**（依赖最小化）；
- ``data_root`` 与 core 的 ``ZACE_DATA_ROOT`` 同名同义（``~/.zace``，core 只管 ``projects/``）；
- ``local_mode`` 默认 ``True``：M2a 为本地单用户模式（R34），鉴权归 M2c（TASK-060/061）；
- ``local_rescan_interval_s``（TASK-034 §C）：本地模式下检索前的懒重扫间隔，默认 2.0 秒，
  **0 表示禁用**（测试与"只读演示"）；只影响本地模式（远端模式走客户端上传）；
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
    "COOKIE_SECURE_ENV",
    "DATA_ROOT_ENV",
    "DEFAULT_DATA_ROOT",
    "DEFAULT_HOST",
    "DEFAULT_LOCAL_RESCAN_INTERVAL_S",
    "DEFAULT_LOG_BACKUP_COUNT",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_LOG_MAX_BYTES",
    "DEFAULT_LOG_RETENTION_DAYS",
    "DEFAULT_PORT",
    "LOCAL_MODE_ENV",
    "LOCAL_RESCAN_INTERVAL_ENV",
    "LOG_BACKUP_COUNT_ENV",
    "LOG_DIRNAME",
    "LOG_MAX_BYTES_ENV",
    "LOG_RETENTION_DAYS_ENV",
    "PROJECTS_DIRNAME",
    "REGISTER_OPEN_ENV",
    "Settings",
]

#: 数据根环境变量（与 core 的 ``zace_core.engine.DATA_ROOT_ENV`` 同名同义）。
DATA_ROOT_ENV = "ZACE_DATA_ROOT"
#: 本地模式环境变量（R34：默认开启，M2c 才关）。
LOCAL_MODE_ENV = "ZACE_LOCAL_MODE"
#: 懒重扫间隔环境变量（TASK-034 §C；0 = 禁用）。
LOCAL_RESCAN_INTERVAL_ENV = "ZACE_LOCAL_RESCAN_INTERVAL"
#: 注册开关（TASK-060；默认关闭：自部署单人场景够用，Module/06 §2.2）。
REGISTER_OPEN_ENV = "ZACE_REGISTER_OPEN"
#: session cookie 的 Secure 属性（TASK-060；HTTPS 部署必须置 true）。
COOKIE_SECURE_ENV = "ZACE_COOKIE_SECURE"
#: 数据根子目录名（core 的 ``projects/``）与元数据库文件名（TASK-060）。
PROJECTS_DIRNAME = "projects"
#: 请求日志目录名（TASK-090 §A：落 ``{data_root}/logs/request.log``）。
LOG_DIRNAME = "logs"
#: 请求日志单文件上限（字节；超过即轮转，TASK-090 §A 窗口的"按 MB"维度）。
LOG_MAX_BYTES_ENV = "ZACE_LOG_MAX_BYTES"
#: 请求日志保留的轮转备份数（连同当前文件，窗口 = (备份数+1) × 单文件上限）。
LOG_BACKUP_COUNT_ENV = "ZACE_LOG_BACKUP_COUNT"
#: 请求日志保留天数（TASK-090 §A 窗口的"按天"维度；0 = 不按天清理，只按体积）。
LOG_RETENTION_DAYS_ENV = "ZACE_LOG_RETENTION_DAYS"
#: 默认：单文件 8 MiB × (9 备份 + 当前) ≈ 80 MiB 上界（单机 VPS 足够，且不会无限增长）。
DEFAULT_LOG_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 9
#: 默认保留 14 天（用户报错往往隔几天才反馈，太短查不到、太长无必要）。
DEFAULT_LOG_RETENTION_DAYS = 14
#: 默认懒重扫间隔（秒）：本地模式下检索前最多每 2s 扫一次（Module/05 §3.6 的 freshness 语义）。
DEFAULT_LOCAL_RESCAN_INTERVAL_S = 2.0
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
    local_rescan_interval_s: float = DEFAULT_LOCAL_RESCAN_INTERVAL_S
    #: 注册开关（TASK-060）：默认关闭；首个账户走 ``POST /api/auth/bootstrap``。
    register_open: bool = False
    #: session cookie 的 ``Secure``（TASK-060）：本地 http 调试为 False，上云必须 True。
    cookie_secure: bool = False
    #: 请求日志窗口（TASK-090 §A）：单文件上限 / 备份数 / 保留天数。
    log_max_bytes: int = DEFAULT_LOG_MAX_BYTES
    log_backup_count: int = DEFAULT_LOG_BACKUP_COUNT
    log_retention_days: int = DEFAULT_LOG_RETENTION_DAYS
    version: str = __version__

    @property
    def auth_required(self) -> bool:
        """是否要求凭据（= 非本地模式，Module/06 §2.2）；本地模式免鉴权（R34）。"""
        return not self.local_mode

    @property
    def meta_db_path(self) -> Path:
        """``zace-meta.db`` 的落点（与 core 的 ``projects/`` 同级，Module/06 §4-A）。"""
        return self.data_root / "zace-meta.db"

    @property
    def log_dir(self) -> Path:
        """请求日志目录（TASK-090 §A：``{data_root}/logs/``）。"""
        return self.data_root / LOG_DIRNAME

    @property
    def request_log_path(self) -> Path:
        """请求日志文件（TASK-090 §A：JSONL，轮转后为 ``request.log.1`` … ``.N``）。"""
        return self.log_dir / "request.log"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """从环境变量构造配置（缺省即本卡默认值）。"""
        source: Mapping[str, str] = os.environ if env is None else env
        raw_root = source.get(DATA_ROOT_ENV)
        return cls(
            data_root=Path(raw_root).expanduser() if raw_root else DEFAULT_DATA_ROOT,
            local_mode=_as_bool(source.get(LOCAL_MODE_ENV), LOCAL_MODE_ENV, default=True),
            local_rescan_interval_s=_as_float(
                source.get(LOCAL_RESCAN_INTERVAL_ENV),
                LOCAL_RESCAN_INTERVAL_ENV,
                default=DEFAULT_LOCAL_RESCAN_INTERVAL_S,
            ),
            register_open=_as_bool(source.get(REGISTER_OPEN_ENV), REGISTER_OPEN_ENV, default=False),
            cookie_secure=_as_bool(source.get(COOKIE_SECURE_ENV), COOKIE_SECURE_ENV, default=False),
            log_max_bytes=_as_int(
                source.get(LOG_MAX_BYTES_ENV), LOG_MAX_BYTES_ENV, default=DEFAULT_LOG_MAX_BYTES
            ),
            log_backup_count=_as_int(
                source.get(LOG_BACKUP_COUNT_ENV),
                LOG_BACKUP_COUNT_ENV,
                default=DEFAULT_LOG_BACKUP_COUNT,
            ),
            log_retention_days=_as_int(
                source.get(LOG_RETENTION_DAYS_ENV),
                LOG_RETENTION_DAYS_ENV,
                default=DEFAULT_LOG_RETENTION_DAYS,
            ),
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


def _as_int(raw: str | None, name: str, *, default: int) -> int:
    """解析非负整数（与 :func:`_as_float` 同纪律：非法值显式报错，不静默取默认）。"""
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"环境变量 {name} 必须是整数，收到 {raw!r}") from None
    if value < 0:
        raise ValueError(f"环境变量 {name} 不能为负（0 表示禁用），收到 {raw!r}")
    return value


def _as_float(raw: str | None, name: str, *, default: float) -> float:
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"环境变量 {name} 必须是数字，收到 {raw!r}") from None
    if value < 0:
        raise ValueError(f"环境变量 {name} 不能为负（0 表示禁用），收到 {raw!r}")
    return value
