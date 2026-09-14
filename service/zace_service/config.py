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
  配置写错的人以为安全策略生效（诚实性优先于启动便利）；
- LLM 总结配置（``ANSWER_*``，TASK-088 / Module/04 §2）：**用户只需给 URL/KEY/MODEL 三个**，
  其余三项有内置默认值但同样允许环境变量覆盖。**未配置 = 未配置**（三个里的任一为空即视为
  未配置），``ask`` 走 D-26 降级包而不是启动报错（L5：开源产品冷启动体验）。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from zace_service import __version__

__all__ = [
    "ANSWER_API_KEY_ENV",
    "ANSWER_BASE_URL_ENV",
    "ANSWER_MAX_TOKENS_ENV",
    "ANSWER_MODEL_ENV",
    "ANSWER_TEMPERATURE_ENV",
    "ANSWER_TIMEOUT_S_ENV",
    "COOKIE_SECURE_ENV",
    "DATA_ROOT_ENV",
    "DEFAULT_ANSWER_MAX_TOKENS",
    "DEFAULT_ANSWER_TEMPERATURE",
    "DEFAULT_ANSWER_TIMEOUT_S",
    "DEFAULT_DATA_ROOT",
    "DEFAULT_HOST",
    "DEFAULT_LOCAL_RESCAN_INTERVAL_S",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_PORT",
    "LOCAL_MODE_ENV",
    "LOCAL_RESCAN_INTERVAL_ENV",
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
#: 数据根子目录名（core 的 ``projects/``；元数据库文件名见 ``metadb.META_DB_FILENAME``）。
PROJECTS_DIRNAME = "projects"
# ------------------------------------------------------------------ LLM 总结（TASK-088）
# 用户只需给三个必填项；下面三项是内置默认值（可覆盖），口径见 Module/04 §2 参数表。
#: LLM 的 OpenAI-compatible base URL（如 ``http://host:8080/v1``）。
ANSWER_BASE_URL_ENV = "ANSWER_BASE_URL"
#: LLM 的 API key（**绝不进日志/响应/仓库/设置页**）。
ANSWER_API_KEY_ENV = "ANSWER_API_KEY"
#: LLM 模型名（如 ``deepseek/deepseek-v4.1-flash``）。
ANSWER_MODEL_ENV = "ANSWER_MODEL"
#: 整体超时秒数（Module/04 §2：连接 10s / 整体 60s）。
ANSWER_TIMEOUT_S_ENV = "ANSWER_TIMEOUT_S"
#: 单次回答的 ``max_tokens``（Module/04 §2：3072）。
ANSWER_MAX_TOKENS_ENV = "ANSWER_MAX_TOKENS"
#: 采样温度（Module/04 §2：0.2——调查要事实不要创意）。
ANSWER_TEMPERATURE_ENV = "ANSWER_TEMPERATURE"
#: 三个必填项的默认值（未配置任一 → ``answer_configured`` 为 False，``ask`` 走降级包）。
DEFAULT_ANSWER_TIMEOUT_S = 60.0
DEFAULT_ANSWER_MAX_TOKENS = 3072
DEFAULT_ANSWER_TEMPERATURE = 0.2
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
    #: LLM 总结（TASK-088）：三个必填项＋三个可覆盖默认值。
    answer_base_url: str | None = None
    answer_api_key: str | None = None
    answer_model: str | None = None
    answer_timeout_s: float = DEFAULT_ANSWER_TIMEOUT_S
    answer_max_tokens: int = DEFAULT_ANSWER_MAX_TOKENS
    answer_temperature: float = DEFAULT_ANSWER_TEMPERATURE
    version: str = __version__

    @property
    def auth_required(self) -> bool:
        """是否要求凭据（= 非本地模式，Module/06 §2.2）；本地模式免鉴权（R34）。"""
        return not self.local_mode

    @property
    def answer_configured(self) -> bool:
        """LLM 是否已配置（三个必填项都非空；Module/04 §6）。

        **不是**“能连上”：未配置 → ``ask`` 走降级包并提示管理员去配；
        配了但打不通 → 另一条降级路径（§6 故障矩阵）。
        """
        return bool(self.answer_base_url and self.answer_model and self.answer_api_key)

    @property
    def answer_missing_env(self) -> tuple[str, ...]:
        """未配置时缺哪几个环境变量（只回**变量名**，不回值/不回长度）。"""
        missing: list[str] = []
        if not self.answer_base_url:
            missing.append(ANSWER_BASE_URL_ENV)
        if not self.answer_api_key:
            missing.append(ANSWER_API_KEY_ENV)
        if not self.answer_model:
            missing.append(ANSWER_MODEL_ENV)
        return tuple(missing)

    @property
    def meta_db_path(self) -> Path:
        """``zace-meta.db`` 的落点（与 core 的 ``projects/`` 同级，Module/06 §4-A）。"""
        return self.data_root / "zace-meta.db"

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
            answer_base_url=(source.get(ANSWER_BASE_URL_ENV) or "").strip() or None,
            answer_api_key=(source.get(ANSWER_API_KEY_ENV) or "").strip() or None,
            answer_model=(source.get(ANSWER_MODEL_ENV) or "").strip() or None,
            answer_timeout_s=_as_float(
                source.get(ANSWER_TIMEOUT_S_ENV),
                ANSWER_TIMEOUT_S_ENV,
                default=DEFAULT_ANSWER_TIMEOUT_S,
            ),
            answer_max_tokens=_as_int(
                source.get(ANSWER_MAX_TOKENS_ENV),
                ANSWER_MAX_TOKENS_ENV,
                default=DEFAULT_ANSWER_MAX_TOKENS,
            ),
            answer_temperature=_as_float(
                source.get(ANSWER_TEMPERATURE_ENV),
                ANSWER_TEMPERATURE_ENV,
                default=DEFAULT_ANSWER_TEMPERATURE,
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


def _as_int(raw: str | None, name: str, *, default: int) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"环境变量 {name} 必须是整数，收到 {raw!r}") from None
    if value < 1:
        raise ValueError(f"环境变量 {name} 必须 ≥ 1，收到 {raw!r}")
    return value
