"""结构化 JSON 日志（TASK-030 §交付物；Module/06 §2.4 可观测 + §3 secret 纪律）。

纪律（卡内冻结）：

- 一律 JSON 单行写 **stderr**（stdout 留给将来的协议/管道用途，日志不得污染）；
- 字段：``ts`` / ``level`` / ``logger`` / ``msg`` / ``requestId`` + 调用方 ``extra``；
- **脱敏**：``Authorization`` / ``Cookie`` / token / 请求体不进日志。落地方式有两条：
  ① 访问日志只记录 method / path / status / 耗时（**不碰 headers、不碰 body**）；
  ② 所有经 :class:`JsonFormatter` 输出的文本再过一遍 :func:`redact_text`，
     即使调用方手滑把 header 拼进 message，secret 也不会落盘。

``requestId`` 用 :mod:`contextvars` 传递（middleware 每请求设置一次），
因此线程池里的同步 handler 打日志也能带上同一个 id（``anyio.to_thread`` 会复制上下文）。
"""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime

__all__ = [
    "JSON_LOG_HANDLER_NAME",
    "REDACTED",
    "bind_request_id",
    "configure_logging",
    "current_request_id",
    "get_logger",
    "redact_text",
    "register_secret",
    "reset_request_id",
]

#: JSON handler 的固定名字（``configure_logging`` 幂等：重复调用只改 level，不叠 handler）。
JSON_LOG_HANDLER_NAME = "zace-json-stderr"
#: 脱敏占位符。
REDACTED = "***"

_request_id: ContextVar[str | None] = ContextVar("zace_request_id", default=None)
_secrets: set[str] = set()

_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
#: ``Authorization: xxx`` / ``cookie=xxx`` / ``"token": "xxx"`` 形态的键值对。
_KEYED_SECRET_RE = re.compile(
    r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key|api[_-]?key"
    r"|access[_-]?token|token|secret|password|passwd|credential)\b(\"?\s*[:=]\s*)(\"?)([^\s,;\"']+)"
)

#: ``LogRecord`` 的标准属性（作为 ``extra`` 过滤依据；新增属性靠 ``__dict__`` 差集识别）。
_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime"}


def redact_text(text: str) -> str:
    """脱敏一段文本（Bearer token、key: value 形态的凭据、显式登记的 secret）。"""
    if not text:
        return text
    scrubbed = _BEARER_RE.sub(f"Bearer {REDACTED}", text)
    scrubbed = _KEYED_SECRET_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}{REDACTED}", scrubbed
    )
    for secret in _secrets:
        if secret and secret in scrubbed:
            scrubbed = scrubbed.replace(secret, REDACTED)
    return scrubbed


def register_secret(value: str) -> None:
    """登记一个需要脱敏的明文（如运行期生成的一次性 token）；空值忽略。"""
    if value:
        _secrets.add(value)


def bind_request_id(request_id: str) -> Token[str | None]:
    """绑定当前上下文的 requestId（返回值交给 :func:`reset_request_id` 还原）。"""
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def current_request_id() -> str | None:
    return _request_id.get()


def get_logger(name: str = "zace_service") -> logging.Logger:
    """取 logger（配置由 :func:`configure_logging` 统一负责）。"""
    return logging.getLogger(name)


class RedactingFilter(logging.Filter):
    """把 ``record.msg`` / args / ``extra`` 里的凭据抹掉（第二道防线，见模块 docstring）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        for key, value in list(record.__dict__.items()):
            if key in _STANDARD_ATTRS or key.startswith("_"):
                continue
            if isinstance(value, str):
                record.__dict__[key] = redact_text(value)
        return True


class JsonFormatter(logging.Formatter):
    """``LogRecord`` → 单行 JSON（字段见模块 docstring）。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
        }
        request_id = current_request_id()
        if request_id:
            payload["requestId"] = request_id
        for key, value in sorted(record.__dict__.items()):
            if key in _STANDARD_ATTRS or key.startswith("_"):
                continue
            payload[key] = redact_text(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "info") -> logging.Logger:
    """装上 JSON handler（幂等：只加一次，重复调用即改 level）。返回根 logger。"""
    root = logging.getLogger()
    handler = next(
        (item for item in root.handlers if getattr(item, "name", "") == JSON_LOG_HANDLER_NAME),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
        handler.name = JSON_LOG_HANDLER_NAME
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    # 过滤器挂在 **handler** 上：handler 会收到所有子 logger 传播上来的记录，因此
    # caplog / 第三方 handler / 未来的文件 handler 拿到的都已是脱敏文本。
    # （logger 级 filter 只对直接写在该 logger 上的记录生效，覆盖不到子 logger，故不作为主防线。）
    if not any(isinstance(item, RedactingFilter) for item in handler.filters):
        handler.addFilter(RedactingFilter())
    if not any(isinstance(item, RedactingFilter) for item in root.filters):
        root.addFilter(RedactingFilter())
    handler.setLevel(_resolve_level(level))
    root.setLevel(_resolve_level(level))
    return root


def _resolve_level(level: str) -> int:
    resolved = logging.getLevelName(level.strip().upper())
    return resolved if isinstance(resolved, int) else logging.INFO
