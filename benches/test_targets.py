"""``benches/targets.py`` 的单元测试（靶场清单解析与命令拼装）。

纪律：**不联网、不建索引、不读真实数据根**——只测纯逻辑（清单校验、参数拼装、错误信息）。
真实数字来自 ``benches/results/*.md``。

运行（``benches/`` 不在根 ``pyproject.toml`` 的 ``testpaths`` 里，需显式给路径）：

```bash
uv run pytest -o addopts="" -q benches/test_targets.py
```
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "benches") not in sys.path:
    sys.path.insert(0, str(ROOT / "benches"))

import targets as tt  # noqa: E402


def _manifest(tmp_path: Path, targets: dict) -> Path:
    path = tmp_path / "targets.json"
    path.write_text(json.dumps({"schema": tt.SCHEMA, "targets": targets}), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 清单读取与校验
# ---------------------------------------------------------------------------


def test_repo_manifest_lists_the_three_kept_targets() -> None:
    targets = tt.load_targets()
    assert list(targets) == ["zace", "hello-agents", "cockpit-agents-py"]
    for target in targets.values():
        assert target.golden.is_dir(), f"{target.name} 的 golden 目录不存在"
        assert list(target.golden.glob("*.jsonl")), f"{target.name} 的 golden 没有用例"


def test_recorded_indexes_carry_a_project_id_and_fingerprint() -> None:
    targets = tt.load_targets()
    assert targets["cockpit-agents-py"].project_id == "8e69da62f37e5783"
    assert targets["zace"].project_id == "adfdd1a626db62b7"
    # 记了 projectId 的靶场必须同时记指纹：否则拿别的模型的向量算 cosine 无从察觉
    for name in ("cockpit-agents-py", "zace"):
        assert targets[name].embedding == {"model": "api:voyage-4-lite", "dim": 1024}
    # 还没建索引的靶场不得凭空的 projectId 绕过身份核验
    assert targets["hello-agents"].project_id is None


def test_unknown_target_lists_available_names(tmp_path: Path) -> None:
    with pytest.raises(tt.TargetError) as excinfo:
        tt.resolve_target("cockpit", path=tt.TARGETS_PATH)
    message = str(excinfo.value)
    assert "未知靶场：cockpit" in message
    assert "cockpit-agents-py" in message


def test_bad_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "targets.json"
    path.write_text(json.dumps({"schema": 999, "targets": {}}), encoding="utf-8")
    with pytest.raises(tt.TargetError) as excinfo:
        tt.load_targets(path)
    assert "schema" in str(excinfo.value)


def test_missing_required_field_is_rejected(tmp_path: Path) -> None:
    path = _manifest(tmp_path, {"zace": {"golden": "benches/golden/zace", "commit": "self"}})
    with pytest.raises(tt.TargetError) as excinfo:
        tt.load_targets(path)
    assert "repo_hint" in str(excinfo.value)


def test_missing_manifest_is_reported(tmp_path: Path) -> None:
    with pytest.raises(tt.TargetError) as excinfo:
        tt.load_targets(tmp_path / "nope.json")
    assert "找不到靶场清单" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 命令拼装
# ---------------------------------------------------------------------------


def test_build_eval_args_binds_project_id_and_data() -> None:
    target = tt.resolve_target("cockpit-agents-py")
    argv = tt.build_eval_args(
        target,
        data="/tmp/bench",
        report="/tmp/r.md",
        vector_cache="/tmp/qvec.json",
        replay=True,
    )
    assert argv == [
        "--golden", str(target.golden),
        "--project-id", "8e69da62f37e5783",
        "--data", "/tmp/bench",
        "--report", "/tmp/r.md",
        "--vector-cache", "/tmp/qvec.json",
        "--replay",
    ]


def test_build_eval_args_keeps_extra_flags_passthrough() -> None:
    target = tt.resolve_target("hello-agents")
    argv = tt.build_eval_args(
        target, data="/tmp/bench", report="/tmp/r.md", repo="/path/to/repo",
        extra=["--max-tokens", "8000"],
    )
    assert argv[-2:] == ["--max-tokens", "8000"]
    assert "--project-id" not in argv  # 没绑索引 → 由 D-29 身份计算


def test_recorded_project_id_lets_any_checkout_reuse_the_index() -> None:
    """记了 projectId 的靶场不需要 --repo：换 checkout/换 worktree 都能挂同一份索引。"""
    target = tt.resolve_target("zace")
    argv = tt.build_eval_args(target, data="/tmp/bench", report="/tmp/r.md")
    assert "--repo" not in argv
    assert argv[argv.index("--project-id") + 1] == "adfdd1a626db62b7"


def test_target_without_index_binding_needs_repo() -> None:
    target = tt.resolve_target("hello-agents")
    with pytest.raises(tt.TargetError) as excinfo:
        tt.build_eval_args(target, data="/tmp/bench", report="/tmp/r.md")
    assert "--repo" in str(excinfo.value)


def test_replay_without_sidecar_is_rejected() -> None:
    target = tt.resolve_target("cockpit-agents-py")
    with pytest.raises(tt.TargetError) as excinfo:
        tt.build_eval_args(target, data="/tmp/bench", report="/tmp/r.md", replay=True)
    assert "--vector-cache" in str(excinfo.value)


def test_target_arg_is_extracted_in_both_forms() -> None:
    assert tt.split_target_arg(["--target", "zace", "--data", "x"]) == ("zace", ["--data", "x"])
    assert tt.split_target_arg(["--target=zace", "--replay"]) == ("zace", ["--replay"])
    assert tt.split_target_arg(["--golden", "g"]) == (None, ["--golden", "g"])
    with pytest.raises(tt.TargetError):
        tt.split_target_arg(["--target"])


def test_describe_targets_mentions_every_target() -> None:
    text = tt.describe_targets(tt.load_targets())
    for name in ("zace", "hello-agents", "cockpit-agents-py"):
        assert name in text
    assert "8e69da62f37e5783" in text
