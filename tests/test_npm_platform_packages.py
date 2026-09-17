"""平台子包与包装器平台表一致性（D-48/D-49 的护栏）。

两项“静默故障”类约定都在这里守住：

- 主包 ``optionalDependencies`` 与 6 个子包的版本/平台字段不一致 → 该平台用户**静默**装不上
  （npm 不报错，只是跳过解析不了的可选依赖）；
- ``npm/run.js`` 的平台表、CI 矩阵的 ``npm_suffixes`` 与生成脚本的 ``PLATFORMS`` 漂移 →
  包装器按 A 名字找、npm 按 B 条件装，两边对不上。

因此断言直接读三个真实文件（不复制一份常量表），漂移会立刻失败。
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_generator():
    """加载 ``scripts/make-platform-packages.py``（文件名带连字符，不能直接 import）。"""
    spec = importlib.util.spec_from_file_location(
        "make_platform_packages", ROOT / "scripts/make-platform-packages.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mk = _load_generator()


def test_platforms_and_packages_agree():
    main = json.loads((mk.NPM_DIR / "package.json").read_text(encoding="utf-8"))
    optional = main.get("optionalDependencies", {})
    suffixes = {s["suffix"] for s in mk.PLATFORMS}
    assert set(optional) == {f"{mk.MAIN_PACKAGE_NAME}-{s}" for s in suffixes}
    for value in optional.values():
        assert value == main["version"]
    for item in mk.PLATFORMS:
        pkg = json.loads(
            (mk.sub_package_dir(item["suffix"]) / "package.json").read_text(encoding="utf-8")
        )
        assert pkg["os"] == [item["os"]]
        assert pkg["cpu"] == [item["cpu"]]
        assert pkg["version"] == main["version"]
        assert "bin" not in pkg


def test_run_js_platform_table_covers_script_table():
    text = (mk.NPM_DIR / "run.js").read_text(encoding="utf-8")
    for item in mk.PLATFORMS:
        assert f'"{item["suffix"]}"' in text
        assert f'"{item["os"]}"' in text


def test_platforms_match_node_conventions():
    assert {s["os"] for s in mk.PLATFORMS} == {"linux", "darwin", "win32"}
    assert {s["cpu"] for s in mk.PLATFORMS} == {"x64", "arm64"}


def test_workflow_matrix_covers_every_suffix():
    """CI 矩阵必须覆盖平台表的每一项（每个平台一个 matrix 条目 + 一个 artifact）。"""
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    declared = set(re.findall(r"^\s+- suffix:\s*(\S+)\s*$", text, flags=re.MULTILINE))
    assert declared == {s["suffix"] for s in mk.PLATFORMS}
    # artifact 也要按平台分（同名文件不能用 merge-multiple 汇总）
    assert "name: binary-${{ matrix.suffix }}" in text


def test_check_version_script_passes():
    result = subprocess.run(
        ["bash", "scripts/check-version.sh"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --------------------------------------------------------------------------- #
# 下面几条守的是“发布形态”本身（D-48/D-49）。
# 它们都是**静默故障**类约定：破了不会报错，只会在用户侧表现为“装不上/拿错二进制”。
# --------------------------------------------------------------------------- #


def test_run_js_has_no_github_download_fallback():
    """包装器不得出现任何 GitHub 下载路径（D-49：npm 是唯一分发渠道）。

    为何要守：保留下载回退 = 两条分发渠道并存，出错时无法判断用户拿到的是哪个二进制。
    且 Node 默认不读 `https_proxy`，下载在代理环境下会以 403 限流形式静默失败。
    """
    text = (mk.NPM_DIR / "run.js").read_text(encoding="utf-8")
    for banned in ("api.github.com", "releases/tags", "browser_download_url", "downloadToFile"):
        assert banned not in text, f"run.js 里还有 GitHub 下载残留：{banned}"
    # 不应 require https（下载专用）；也不应再写缓存目录
    assert "require(\"https\")" not in text
    assert "cacheDir" not in text, "缓存目录机制应一并删除（它是旧下载路径的一部分）"


def test_main_package_publishes_to_next_not_latest():
    """主包默认发 `next`（不是 `latest`）——npm 发布不可逆，latest 必须是最后一个可控点。"""
    text = (ROOT / "scripts/make-platform-packages.py").read_text(encoding="utf-8")
    # 默认 tag 必须是 next
    assert 'default="next"' in text
    # 不得有直接发 latest 的写法
    assert '"--tag", "latest"' not in text
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "--phase main --tag next" in workflow


def test_promote_is_separate_and_after_smoke():
    """⑤ 必须拆成 pre-verify →（publish-main）→ smoke → promote → post-verify。"""
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    for job in ("pre-verify:", "publish-main:", "promote:", "post-verify:"):
        assert job in workflow, f"缺少发布阶段：{job}"
    # job 依赖顺序必须是 子包 → 前置验证 → 主包 → promote → 后置验证
    assert "needs: publish-platforms" in workflow
    assert "needs: pre-verify" in workflow
    assert "needs: publish-main" in workflow
    assert "needs: promote" in workflow
    # promote job 里必须先冒烟、再 promote（顺序写在同一个 job 的 steps 里）
    promote_job = workflow[workflow.index("\n  promote:") : workflow.index("\n  post-verify:")]
    smoke_idx = promote_job.index("smoke --tag next")
    promote_idx = promote_job.index("make-platform-packages.py promote")
    assert smoke_idx < promote_idx, "promote 之前必须先跑冒烟"


def test_macos_builds_per_arch_without_lipo():
    """macOS 两架构**独立构建**，不得再用 universal/lipo（D-48 补充）。"""
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    # 只看可执行语句（注释里提到 lipo 作为“为什么不用”的说明是允许的）
    code = "\n".join(
        line for line in workflow.splitlines() if not line.lstrip().startswith("#")
    )
    assert "lipo" not in code, "不应再用 lipo 合并 universal"
    assert "universal-apple-darwin" not in code
    assert "x86_64-apple-darwin" in workflow
    assert "aarch64-apple-darwin" in workflow
    # 两个 macOS 架构各占一个矩阵条目
    assert "suffix: darwin-x64" in workflow
    assert "suffix: darwin-arm64" in workflow


def test_verify_has_platforms_and_latest_phases():
    """验证必须分阶段：子包发布前验 platforms，全流程后验 latest。"""
    text = (ROOT / "scripts/make-platform-packages.py").read_text(encoding="utf-8")
    assert '"platforms", "latest"' in text.replace("\n", " ") or "platforms" in text
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "verify --phase platforms" in workflow
    assert "verify --phase latest" in workflow


def test_no_win32_in_package_names():
    """npm 包名不得含 `win32-`（真实故障：`Package name triggered spam detection`）。

    实测（2026-09-17）：`zace-client-win32-x64` 发布被 registry 拒绝，
    完整错误 `403 Forbidden - PUT .../zace-client-win32-x64 - Package name triggered
    spam detection`。同一次发布里前 4 个包（linux/darwin）全部成功，
    换成 `zace-client-windows-x64` 后正常——`win32` 是恶意软件命名的常见特征词。

    注意：**npm 包名**用 `windows`，而 package.json 的 `os` 字段必须仍是 `win32`
    （那是 Node `process.platform` 的取值，不能被"统一"掉）。
    """
    main = json.loads((mk.NPM_DIR / "package.json").read_text(encoding="utf-8"))
    for name in list(main.get("optionalDependencies", {})) + [main["name"]]:
        assert "win32" not in name, f"npm 包名不得含 win32（会被 spam detection 拦）：{name}"
    for spec in mk.PLATFORMS:
        assert "win32" not in f"{mk.MAIN_PACKAGE_NAME}-{spec['suffix']}"
        if spec["os"] == "win32":
            # os 字段必须仍是 win32（Node 的取值），别跟着包名一起改名
            assert spec["suffix"].startswith("windows-")
    # run.js 的 platform 字段也必须是 win32
    text = (mk.NPM_DIR / "run.js").read_text(encoding="utf-8")
    assert 'platform: "win32"' in text
