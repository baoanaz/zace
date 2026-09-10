"""service 测试公共夹具（TASK-030）。

纪律（`docs/tasks/README.md` 与各卡 DoD）：

- 一律用 ``tmp_path`` 下的临时 data_root，**不依赖本机绝对路径**；
- 不触网、不加载真实 embedding 模型（CI 离线；TASK-031 起注入确定性假 provider）；
- 应用实例都走 :func:`zace_service.app.create_app`（生产入口与测试入口同一个）。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from zace_service.app import create_app
from zace_service.config import Settings

#: 仓库根（``service/tests/conftest.py`` → parents[2]）。
REPO_ROOT = Path(__file__).resolve().parents[2]
#: CF-05 合同文件（路径集合的权威来源）。
OPENAPI_CONTRACT = REPO_ROOT / "docs" / "contracts" / "openapi.yaml"

_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})
_PATH_LINE_RE = re.compile(r"^  (/[^:]*):\s*$")
_METHOD_LINE_RE = re.compile(r"^    ([a-z]+):")


def test_settings(data_root: Path, **overrides: object) -> Settings:
    """测试用配置（临时 data_root；本地模式）。"""
    return Settings(data_root=data_root, local_mode=True, **overrides)  # type: ignore[arg-type]


def make_app(data_root: Path) -> FastAPI:
    """构造应用（测试内需要"全新 app + 额外测试路由"时用）。"""
    return create_app(test_settings(data_root))


def make_client(app: FastAPI) -> TestClient:
    """包一层 TestClient（``raise_server_exceptions=False``：500 信封由应用自己保证）。"""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """应用的配置对象（data_root 在 tmp_path 下）。"""
    return test_settings(tmp_path / "data")


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """临时 data_root 的应用实例（每个测试独立）。"""
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """同步 TestClient（lifespan 打开/关闭）。"""
    with make_client(app) as test_client:
        yield test_client


def _parse_contract_paths(text: str) -> dict[str, set[str]]:
    """从 CF-05 的 openapi.yaml 抽出 ``路径 → 方法集合``（不依赖 PyYAML：按缩进解析）。

    只取顶层 ``paths:`` 段下 2 空格缩进的路径键与 4 空格缩进的方法键——这足够表达
    CF-05 的冻结面（路径 + 方法），且不需要引入未声明的第三方依赖。
    """
    paths: dict[str, set[str]] = {}
    current: str | None = None
    in_paths = False
    for line in text.splitlines():
        if line.startswith("paths:"):
            in_paths = True
            continue
        if not in_paths:
            continue
        if line and not line.startswith(" "):  # 顶层键：paths 段结束
            break
        path_match = _PATH_LINE_RE.match(line)
        if path_match:
            current = path_match.group(1)
            paths[current] = set()
            continue
        method_match = _METHOD_LINE_RE.match(line)
        if method_match and current is not None and method_match.group(1) in _METHODS:
            paths[current].add(method_match.group(1))
    return paths


@pytest.fixture(scope="session")
def contract_paths() -> dict[str, set[str]]:
    """CF-05（``docs/contracts/openapi.yaml``）的路径与方法集合。"""
    assert OPENAPI_CONTRACT.is_file(), f"合同文件缺失：{OPENAPI_CONTRACT}"
    parsed = _parse_contract_paths(OPENAPI_CONTRACT.read_text(encoding="utf-8"))
    assert parsed, "合同解析结果为空：openapi.yaml 的 paths 段可能被改写"
    return parsed
