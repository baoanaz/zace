"""OpenAI-compatible embedding API 实现（TASK-008 §C，可选路径）。

隐私语义：与 local.py 相反，**文本会发往第三方服务**（API 提供方）。本模块不写日志、
不落盘，异常信息统一走 ``_redact`` 脱敏，保证 API key 不出现在日志/异常/``repr`` 里。
设置页的隐私告知文案由 Phase 4 负责（本卡只在 docstring 中注明语义）。

协议：``POST {base_url}/v1/embeddings``，请求体 ``{"model": ..., "input": [...]}``，
响应 ``{"data": [{"index": i, "embedding": [...]}]}``（index 用于恢复输入顺序）。
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import httpx
import numpy as np

from zace_core.embedding.base import (
    ApiAuthError,
    ApiNetworkError,
    ApiRateLimitError,
    ApiResponseError,
    EmbeddingConfigError,
    EmbeddingDimMismatchError,
    Side,
    iter_batches,
    l2_normalize,
    with_prefix,
)
from zace_core.embedding.registry import ApiModelSpec
from zace_core.interfaces import EmbeddingProfile

#: API 批大小（卡内 §A）。
DEFAULT_BATCH_SIZE = 64

#: 超时：连接 10s / 整体 60s（卡内 §C）。
DEFAULT_TIMEOUT_CONNECT = 10.0
DEFAULT_TIMEOUT_TOTAL = 60.0

#: 失败重试上限（卡内 §C：≤2 次，指数退避）。
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_BASE = 0.5

#: Retry-After 上限，避免服务端给出超长等待把索引 job 挂死。
MAX_RETRY_AFTER = 30.0

_AUTH_STATUS = frozenset({401, 403})
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}")


def build_default_client(
    *,
    timeout_total: float = DEFAULT_TIMEOUT_TOTAL,
    timeout_connect: float = DEFAULT_TIMEOUT_CONNECT,
) -> httpx.Client:
    """构造默认 HTTP 客户端（连接 10s / 整体 60s）。"""
    return httpx.Client(timeout=httpx.Timeout(timeout_total, connect=timeout_connect))


def embeddings_endpoint(base_url: str) -> str:
    """拼 embedding endpoint；``base_url`` 已带 ``/v1`` 时不重复拼接。"""
    base = base_url.strip().rstrip("/")
    if not base:
        raise EmbeddingConfigError("base_url 不能为空（如 https://api.openai.com）")
    return f"{base}/embeddings" if base.endswith("/v1") else f"{base}/v1/embeddings"


class OpenAiCompatibleEmbeddingProvider:
    """OpenAI-compatible API provider（可选实现；API key 全程脱敏）。

    失败语义（供上层决定是否降级，TASK-010）：
    ``ApiAuthError`` / ``ApiRateLimitError`` / ``ApiNetworkError`` / ``ApiResponseError``
    / ``EmbeddingDimMismatchError``，均为 ``EmbeddingError`` 子类。
    """

    def __init__(
        self,
        spec: ApiModelSpec,
        *,
        base_url: str,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        sleep: Callable[[float], None] = time.sleep,
        timeout_total: float = DEFAULT_TIMEOUT_TOTAL,
        timeout_connect: float = DEFAULT_TIMEOUT_CONNECT,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        if batch_size < 1:
            raise EmbeddingConfigError(f"batch_size 必须 ≥ 1，收到 {batch_size}")
        if max_retries < 0:
            raise EmbeddingConfigError(f"max_retries 不能为负，收到 {max_retries}")
        self._spec = spec
        self._endpoint = embeddings_endpoint(base_url)
        self._api_key = api_key or None
        self._owns_client = client is None
        self._client = client or build_default_client(
            timeout_total=timeout_total, timeout_connect=timeout_connect
        )
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._extra_headers = dict(extra_headers or {})

    # -- 只读状态 ---------------------------------------------------------

    @property
    def spec(self) -> ApiModelSpec:
        return self._spec

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def profile(self) -> EmbeddingProfile:
        """CF-09 指纹：变更即触发 D-07 二级失效（写 ``index_config``）。"""
        return EmbeddingProfile(
            model_id=self._spec.model_id,
            dim=self._spec.dim,
            max_input_tokens=self._spec.max_input_tokens,
        )

    @property
    def batch_size(self) -> int:
        return self._batch_size

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(model_id={self._spec.model_id!r}, "
            f"endpoint={self._endpoint!r}, api_key={'***' if self._api_key else None})"
        )

    def close(self) -> None:
        """关闭自建客户端；注入的客户端由调用方负责（避免替别人关连接池）。"""
        if self._owns_client:
            self._client.close()

    # -- 推理 -------------------------------------------------------------

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """CF-09 契约方法：按索引侧（passage）语义嵌入。"""
        return self.embed_side(texts, "passage")

    def embed_query(self, texts: Sequence[str]) -> list[list[float]]:
        """检索侧（query）语义嵌入；未配置前缀的模型与 ``embed`` 等价。"""
        return self.embed_side(texts, "query")

    def embed_side(self, texts: Sequence[str], side: Side) -> list[list[float]]:
        if side not in ("passage", "query"):  # pragma: no cover - 防御性分支
            raise EmbeddingConfigError(f"side 必须是 'passage' / 'query'，收到 {side!r}")
        items = list(texts)
        if not items:
            return []
        prefix = self._spec.query_prefix if side == "query" else self._spec.passage_prefix
        vectors: list[list[float]] = []
        for batch in iter_batches(items, self._batch_size):
            vectors.extend(self._embed_batch([with_prefix(text, prefix) for text in batch]))
        return vectors

    def _embed_batch(self, batch: Sequence[str]) -> list[list[float]]:
        body = self._post({"model": self._spec.name, "input": list(batch)})
        data = body.get("data")
        if not isinstance(data, list) or len(data) != len(batch):
            got = len(data) if isinstance(data, list) else "非列表"
            raise ApiResponseError(
                f"embedding 响应行数 {got} 与请求 {len(batch)} 不一致（endpoint={self._endpoint}）"
            )
        rows: list[tuple[int, Any]] = []
        for position, row in enumerate(data):
            if not isinstance(row, dict) or "embedding" not in row:
                raise ApiResponseError(
                    "embedding 响应缺少 embedding 字段"
                    f"（第 {position} 行，endpoint={self._endpoint}）"
                )
            index = row.get("index", position)
            if not isinstance(index, int) or index < 0 or index >= len(batch):
                raise ApiResponseError(
                    f"embedding 响应 index={index!r} 非法（第 {position} 行，"
                    f"请求 {len(batch)} 条，endpoint={self._endpoint}）"
                )
            rows.append((index, row["embedding"]))
        rows.sort(key=lambda item: item[0])

        vectors: list[list[float]] = []
        for _, raw in rows:
            vector = _as_float_list(raw, endpoint=self._endpoint)
            if len(vector) != self._spec.dim:
                raise EmbeddingDimMismatchError(
                    f"{self._spec.model_id} 返回维度 {len(vector)} 与注册表 dim={self._spec.dim} "
                    f"不一致（endpoint={self._endpoint}）；请修正注册表或显式覆盖 dim"
                    f"（dim 变更会改变 index_config 指纹，触发 D-07 二级失效）"
                )
            vectors.append(vector)
        # 卡内 §A：与本地实现一致，统一返回单位向量（向量库按余弦检索）。
        return l2_normalize(np.asarray(vectors, dtype=np.float32)).tolist()

    # -- HTTP -------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        headers.update(self._extra_headers)
        return headers

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        attempts = self._max_retries + 1
        last_network_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self._client.post(self._endpoint, json=payload, headers=self._headers())
            except httpx.HTTPError as exc:
                last_network_error = exc
                if attempt + 1 < attempts:
                    self._sleep_before_retry(attempt, response=None)
                    continue
                raise ApiNetworkError(
                    self._redact(
                        f"embedding 请求网络失败（{type(exc).__name__}，endpoint={self._endpoint}，"
                        f"尝试 {attempt + 1}/{attempts}）：{exc!r}"
                    )
                ) from exc

            if response.status_code == 200:
                return self._decode(response)
            if response.status_code in _AUTH_STATUS:
                raise ApiAuthError(
                    self._redact(
                        "embedding 鉴权失败"
                        f"（HTTP {response.status_code}，endpoint={self._endpoint}）；"
                        "请检查 EMBED_API_KEY 是否有效（key 不进入日志/异常文本）"
                    )
                )
            if self._is_retryable(response.status_code) and attempt + 1 < attempts:
                self._sleep_before_retry(attempt, response=response)
                continue
            raise self._status_error(response, attempts, last_network_error)
        raise ApiNetworkError(  # pragma: no cover - 循环必然在内部 raise/return
            f"embedding 请求未完成（endpoint={self._endpoint}）"
        )

    @staticmethod
    def _is_retryable(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    def _status_error(
        self, response: httpx.Response, attempts: int, last_network_error: Exception | None
    ) -> Exception:
        snippet = self._redact(response.text[:200].replace("\n", " "))
        detail = f"响应体片段：{snippet}"
        if response.status_code == 429:
            return ApiRateLimitError(
                f"embedding 被限流（HTTP 429，endpoint={self._endpoint}，已尝试 {attempts} 次）；"
                f"{detail}"
            )
        if response.status_code >= 500:
            return ApiResponseError(
                f"embedding 服务端错误（HTTP {response.status_code}，endpoint={self._endpoint}，"
                f"已尝试 {attempts} 次）；{detail}"
            )
        extra = f"（上次网络错误：{last_network_error!r}）" if last_network_error else ""
        return ApiResponseError(
            f"embedding 请求被拒绝（HTTP {response.status_code}，endpoint={self._endpoint}）；"
            f"{detail}{extra}"
        )

    def _sleep_before_retry(self, attempt: int, *, response: httpx.Response | None) -> None:
        delay = self._backoff_base * (2**attempt)
        if response is not None:
            retry_after = _parse_retry_after(response)
            if retry_after is not None:
                delay = max(delay, retry_after)
        self._sleep(delay)

    def _decode(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise ApiResponseError(
                self._redact(
                    f"embedding 响应不是合法 JSON（endpoint={self._endpoint}）：{exc!r}；"
                    f"响应体片段：{response.text[:200]!r}"
                )
            ) from exc
        if not isinstance(body, dict):
            raise ApiResponseError(
                f"embedding 响应结构非法（期望 JSON 对象，endpoint={self._endpoint}）"
            )
        error = body.get("error")
        if error is not None:
            raise ApiResponseError(
                self._redact(
                    f"embedding 响应包含 error 字段（endpoint={self._endpoint}）：{error!r}"
                )
            )
        return body

    def _redact(self, text: str) -> str:
        """异常/日志文本脱敏：key 本体与 ``Bearer <token>`` 形态都不外泄。"""
        if self._api_key:
            text = text.replace(self._api_key, "***")
        return _BEARER_PATTERN.sub(r"\1***", text)


def _as_float_list(raw: Any, *, endpoint: str) -> list[float]:
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ApiResponseError(f"embedding 向量非法（endpoint={endpoint}）：{type(raw).__name__}")
    try:
        return [float(value) for value in raw]
    except (TypeError, ValueError) as exc:
        raise ApiResponseError(f"embedding 向量含非数值元素（{endpoint}）：{exc!r}") from exc


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    if value <= 0:
        return None
    return min(value, MAX_RETRY_AFTER)
