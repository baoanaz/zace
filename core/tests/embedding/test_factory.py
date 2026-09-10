"""factory.py 单元测试：配置解析、默认路径选择与可读错误（TASK-008 §D）。"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from zace_core.embedding.api import OpenAiCompatibleEmbeddingProvider
from zace_core.embedding.base import EmbeddingConfigError, LocalModelUnavailableError
from zace_core.embedding.factory import EmbeddingConfig, create_provider
from zace_core.embedding.local import LocalOnnxEmbeddingProvider
from zace_core.embedding.registry import DEFAULT_LOCAL_SLUG
from zace_core.interfaces import EmbeddingProvider

from .conftest import StubOnnxSession


def test_default_is_local_onnx_provider() -> None:
    provider = create_provider()
    assert isinstance(provider, LocalOnnxEmbeddingProvider)
    assert isinstance(provider, EmbeddingProvider)  # CF-09 协议兼容
    assert provider.profile.model_id == f"local:{DEFAULT_LOCAL_SLUG}"
    assert provider.profile.dim == 384
    assert provider.batch_size == 16  # 本地默认批大小（卡内 §A）


def test_local_model_selection_by_slug() -> None:
    provider = create_provider({"model": "bge-small-zh-v1.5"})
    assert provider.profile.model_id == "local:bge-small-zh-v1.5"
    assert provider.profile.dim == 512


def test_unknown_local_slug_lists_candidates() -> None:
    with pytest.raises(EmbeddingConfigError) as excinfo:
        create_provider({"model": "nope"})
    assert "arctic-embed-xs" in str(excinfo.value)


def test_local_overrides_are_applied(tokenizer, model_dir: Path) -> None:
    session = StubOnnxSession(dim=32)
    provider = create_provider(
        {
            "model": DEFAULT_LOCAL_SLUG,
            "dim": 32,
            "max_input_tokens": 64,
            "model_dir": str(model_dir),
        },
        tokenizer=tokenizer,
        session=session,
    )
    assert provider.profile.dim == 32
    assert provider.profile.max_input_tokens == 64
    assert len(provider.embed(["hello"])[0]) == 32


def test_api_mode_uses_registry_dim_and_batch_size() -> None:
    provider = create_provider(
        {"mode": "api", "model": "bge-m3", "base_url": "https://api.example.com"}
    )
    assert isinstance(provider, OpenAiCompatibleEmbeddingProvider)
    assert isinstance(provider, EmbeddingProvider)
    assert provider.profile.model_id == "api:bge-m3"
    assert provider.profile.dim == 1024
    assert provider.batch_size == 64  # API 默认批大小（卡内 §A）


def test_api_mode_requires_model_and_base_url() -> None:
    with pytest.raises(EmbeddingConfigError, match="model"):
        create_provider({"mode": "api", "base_url": "https://api.example.com"})
    with pytest.raises(EmbeddingConfigError, match="base_url"):
        create_provider({"mode": "api", "model": "bge-m3"})


def test_api_unknown_model_requires_explicit_dim() -> None:
    with pytest.raises(EmbeddingConfigError, match="dim"):
        create_provider(
            {"mode": "api", "model": "self-hosted-xyz", "base_url": "https://api.example.com"}
        )
    provider = create_provider(
        {
            "mode": "api",
            "model": "self-hosted-xyz",
            "base_url": "https://api.example.com",
            "dim": 768,
            "max_input_tokens": 1024,
        }
    )
    assert provider.profile.model_id == "api:self-hosted-xyz"
    assert provider.profile.dim == 768
    assert provider.profile.max_input_tokens == 1024


def test_api_accepts_injected_client() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": []}))
    )
    provider = create_provider(
        {"mode": "api", "model": "bge-m3", "base_url": "https://api.example.com"},
        client=client,
    )
    assert provider.embed([]) == []


def test_unknown_config_field_is_rejected() -> None:
    with pytest.raises(EmbeddingConfigError) as excinfo:
        create_provider({"model": DEFAULT_LOCAL_SLUG, "nope": 1})
    assert "nope" in str(excinfo.value)


def test_invalid_mode_is_rejected() -> None:
    with pytest.raises(EmbeddingConfigError, match="mode"):
        create_provider({"mode": "onnx"})


def test_invalid_batch_size_is_rejected() -> None:
    with pytest.raises(EmbeddingConfigError, match="batch_size"):
        EmbeddingConfig(batch_size=0)


def test_from_env_reads_embed_variables() -> None:
    config = EmbeddingConfig.from_env(
        {
            "EMBED_MODE": "api",
            "EMBED_MODEL": "bge-m3",
            "EMBED_BASE_URL": "https://api.example.com/v1",
            "EMBED_API_KEY": "sk-x",
            "EMBED_DIM": "1024",
            "EMBED_MAX_INPUT_TOKENS": "4096",
            "EMBED_BATCH_SIZE": "8",
            "EMBED_OFFLINE": "true",
        }
    )
    assert config.mode == "api"
    assert config.model == "bge-m3"
    assert config.base_url == "https://api.example.com/v1"
    assert config.api_key == "sk-x"
    assert config.dim == 1024
    assert config.max_input_tokens == 4096
    assert config.batch_size == 8
    assert config.offline is True


def test_from_env_defaults_to_local() -> None:
    config = EmbeddingConfig.from_env({})
    assert config.mode == "local"
    assert config.model is None
    assert config.offline is False


def test_from_env_rejects_non_integer_override() -> None:
    with pytest.raises(EmbeddingConfigError, match="EMBED_DIM"):
        EmbeddingConfig.from_env({"EMBED_DIM": "big"})


def test_preload_reports_missing_model_readably(tmp_path: Path) -> None:
    with pytest.raises(LocalModelUnavailableError, match="离线模式"):
        create_provider(
            {"offline": True, "cache_dir": str(tmp_path / "empty-cache"), "preload": True}
        )


def test_lazy_by_default_so_construction_never_downloads(tmp_path: Path) -> None:
    provider = create_provider(
        {"offline": True, "cache_dir": str(tmp_path / "empty-cache")}
    )
    assert isinstance(provider, LocalOnnxEmbeddingProvider)  # 构造不触发加载
    with pytest.raises(LocalModelUnavailableError):
        provider.embed(["hello"])
