#!/usr/bin/env bash
# zace-client 的唯一发布入口（D-48/D-49）。
#
# 用法：
#     bash scripts/release-client.sh 0.0.7
#
# 为什么要有这个脚本（而不是把流程写进文档）：
#   文档只能防遗忘，脚本才能真正保证每次做法一致。此前"手工零散执行发布命令"
#   已经造成过一次真实事故（见 §故障对照表的 win32 spam detection 一例）。
#   故：**Agent 拿到"发布 zace-client x.y.z"时的标准动作就是跑这一条命令**，
#   不要再手工拼 `npm publish` / `git tag` / `check-version.sh` 等步骤。
#
# 它做什么（本节即权威定义，handbook 只复述）：
#   ① 前置检查：在 main、工作区干净、tag 不存在、版本号比已发布的新
#   ② 改版本号（client/Cargo.toml + npm/package.json + server.json）
#   ③ 同步平台子包（generate）+ check-version.sh + make-platform-packages.py check
#   ④ 跑测试（ruff + 依赖方向 + pytest）
#   ⑤ commit → push main → 打 tag v<version> → push tag
#   ⑥ 等 CI：gh 可用且已登录 → `gh run watch --compact --exit-status`；
#      否则只报告"CI 已触发"并退出（不阻塞、不轮询）
#   ⑦ CI 成功后复核 `npm view zace-client version` 与 dist-tag，确认 latest == 本次版本
#
# **它不做什么**（刻意的边界）：
#   - 不构建二进制、不发布任何 npm 包 —— 六平台 build / publish / verify / promote
#     全部由 GitHub Actions 负责（本地不可能编 macOS，也不该让本地产物进 npm）；
#   - 不使用 `--force`、不移动或重打已有 tag、不覆盖已发布的版本号；
#   - 不读取、不打印 NPM_TOKEN（发布凭据只存在于 GitHub Actions secret 里）。
#
# 失败时怎么办：**放弃当前版本号，修复后递增新版本重跑**。
# npm 的版本号不可撤回，已 push 的 tag 也不移动 —— 这是本仓库的硬约定。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROG="release-client"
NPM_PACKAGE="zace-client"
VARIANTS=(linux-x64 linux-arm64 darwin-x64 darwin-arm64 windows-x64 windows-arm64)

die() { echo "✗ $*" >&2; exit 1; }
step() { echo; echo "=== $*"; }
ok() { echo "✓ $*"; }

# ---------------------------------------------------------------- ① 前置检查

usage() {
  cat <<EOF
用法：bash scripts/release-client.sh <version> [--no-wait]

  <version>   要发布的版本号，如 0.0.7（不带 v 前缀）
  --no-wait   不等 CI（打完 tag 即返回）

例：bash scripts/release-client.sh 0.0.7
EOF
}

VERSION=""
WAIT=1
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --no-wait) WAIT=0 ;;
    -*) die "未知参数：$arg（见 --help）" ;;
    *) [ -z "$VERSION" ] || die "只接受一个版本号参数" ; VERSION="$arg" ;;
  esac
done

[ -n "$VERSION" ] || { usage; exit 2; }
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "版本号必须是 x.y.z 形式：$VERSION"

step "① 前置检查"

current_branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$current_branch" = "main" ] || die "必须在 main 上发布（当前：$current_branch）"

if [ -n "$(git status --porcelain)" ]; then
  echo "工作区有未提交改动：" >&2
  git status --short >&2
  die "先提交或清理工作区（本脚本要自己提交版本号改动，不能混入其它改动）"
fi
ok "在 main 且工作区干净"

git fetch --tags --quiet origin 2>/dev/null || true
if git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null; then
  die "tag v$VERSION 已存在 —— 禁止移动/重写已有 tag。请递增新版本号"
fi
if git ls-remote --exit-code --tags origin "v$VERSION" >/dev/null 2>&1; then
  die "远端已存在 tag v$VERSION —— 同上，请递增新版本号"
fi
ok "tag v$VERSION 本地与远端都不存在"

# 版本必须比已发布的新（否则 npm 会拒绝，属于"已经在 registry 上"）
published="$(npm view "$NPM_PACKAGE" version 2>/dev/null || echo "")"
if [ -n "$published" ]; then
  if [ "$published" = "$VERSION" ]; then
    die "$NPM_PACKAGE@$VERSION 已发布过 —— npm 版本不可撤回，请递增新版本号"
  fi
  newest="$(printf '%s\n%s\n' "$published" "$VERSION" | sort -V | tail -1)"
  [ "$newest" = "$VERSION" ] || die "版本号 $VERSION 低于已发布的 $published（npm 不允许回退版本）"
  ok "当前已发布最新版：$published → 本次发布 $VERSION"
else
  echo "（查不到 $NPM_PACKAGE 的已发布版本，跳过新版本比较）"
fi

# 顺带把"某个平台子包是否已占用该版本"查出来，避免发到一半才发现
taken=()
for v in "${VARIANTS[@]}"; do
  if npm view "${NPM_PACKAGE}-${v}@${VERSION}" version >/dev/null 2>&1; then
    taken+=("${NPM_PACKAGE}-${v}")
  fi
done
if [ "${#taken[@]}" -gt 0 ]; then
  echo "以下平台子包已存在 ${VERSION}（publish 会自动跳过它们，通常无害）：" >&2
  printf '  - %s\n' "${taken[@]}" >&2
fi

# ---------------------------------------------------------------- ② 改版本号

step "② 改版本号 → $VERSION"

python3 - "$VERSION" <<'PY'
import json, pathlib, re, sys
version = sys.argv[1]
root = pathlib.Path(".")

cargo = root / "client/Cargo.toml"
text = cargo.read_text(encoding="utf-8")
# 只替换 [package] 段的 version（文件里还有依赖的 version = "..."）
new, count = re.subn(
    r'(?m)^(version\s*=\s*)"[^"]*"', rf'\g<1>"{version}"', text, count=1
)
assert count == 1, "client/Cargo.toml 里没找到 [package] 的 version 行"
cargo.write_text(new, encoding="utf-8")
print(f"  client/Cargo.toml → {version}")

for name in ("npm/package.json", "server.json"):
    path = root / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = version
    if "packages" in payload:  # server.json 的 packages[0].version 也要改
        payload["packages"][0]["version"] = version
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {name} → {version}")
PY

python3 scripts/make-platform-packages.py generate >/dev/null
ok "平台子包 package.json 与 optionalDependencies 已同步"

# ---------------------------------------------------------------- ③ 一致性校验

step "③ 一致性校验"
bash scripts/check-version.sh "v$VERSION"
python3 scripts/make-platform-packages.py check --allow-missing-binaries
ok "版本号与平台表一致（二进制由 CI 构建并 stage，本地不检查产物）"

# ---------------------------------------------------------------- ④ 测试

step "④ 测试"
uv run ruff check . >/dev/null && ok "ruff"
uv run python scripts/check_dependency_direction.py >/dev/null && ok "依赖方向"
uv run pytest -o addopts="" -q 2>&1 | tail -3

# ---------------------------------------------------------------- ⑤ 提交并打 tag

step "⑤ 提交 / push main / 打 tag"

git add client/Cargo.toml client/Cargo.lock npm/package.json server.json \
        npm/platforms scripts .github docs/handbook/release/npm.md tests 2>/dev/null || true
# Cargo.lock 在版本变化后需要刷新（client 自身版本进 lock）
( cd client && cargo update --workspace --offline >/dev/null 2>&1 ) || true
git add client/Cargo.lock 2>/dev/null || true

if git diff --cached --quiet; then
  echo "（版本号已是 $VERSION，无需提交）"
else
  git commit -q -m "release: $NPM_PACKAGE v$VERSION"
  ok "已提交 $(git rev-parse --short HEAD)"
fi

git push origin main
ok "已 push main"

git tag -a "v$VERSION" -m "$NPM_PACKAGE v$VERSION"
git push origin "v$VERSION"
ok "已 push tag v$VERSION —— CI release 流水线已触发"

# ---------------------------------------------------------------- ⑥ 等 CI

step "⑥ 等待 CI"

run_url=""
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  # 等到 gh 能看到本次 tag 的 release run（刚 push 完有几秒延迟）
  for _ in 1 2 3 4 5 6; do
    run_id="$(gh run list --workflow=release.yml --branch "v$VERSION" --limit 1 \
                --json databaseId --jq '.[0].databaseId' 2>/dev/null || true)"
    [ -n "$run_id" ] && break
    sleep 5
  done
  if [ -n "$run_id" ]; then
    echo "workflow run: $run_id"
    run_url="https://github.com/$(git remote get-url origin | sed -E 's#.*[:/]([^/]+/[^/.]+)(\.git)?$#\1#')/actions/runs/$run_id"
    if [ "$WAIT" -eq 1 ]; then
      gh run watch "$run_id" --compact --exit-status || {
        echo >&2
        echo "✗ CI 未通过（run: $run_url）" >&2
        echo "  处置：**不移动 tag、不覆盖版本号**；修复后递增新版本重跑本脚本。" >&2
        exit 1
      }
      ok "CI 通过"
    else
      echo "（--no-wait：不等 CI。run: $run_url）"
    fi
  else
    echo "gh 未能定位到本次 run（可能需要稍等）。手动查看："
    echo "  gh run list --workflow=release.yml --limit 3"
  fi
else
  echo "gh 不可用或未登录 —— 不阻塞。CI 已触发，请稍后自行查看："
  echo "  https://github.com/baoanaz/zace/actions"
fi

# ---------------------------------------------------------------- ⑦ 复核 npm

step "⑦ 复核 npm"

if [ -z "$run_url" ] || [ "$WAIT" -eq 0 ]; then
  echo "（CI 结果未知，跳过复核。CI 成功后请确认：）"
  echo "  npm view $NPM_PACKAGE version"
  echo "  npm view $NPM_PACKAGE dist-tags"
else
  # registry 的读端缓存传播可能长达数分钟（实测一次发布里 6 个子包在 4 分钟内陆续可读），
  # 故给到约 6 分钟；这只是"等自己刚发的包变可见"，不是在轮询别人的状态。
  latest=""
  for attempt in $(seq 1 24); do
    latest="$(npm view "$NPM_PACKAGE" version 2>/dev/null || echo "")"
    [ "$latest" = "$VERSION" ] && break
    sleep 15
  done
  echo "  npm view $NPM_PACKAGE version  → ${latest:-（查询失败）}"
  npm view "$NPM_PACKAGE" dist-tags 2>/dev/null || true
  [ "$latest" = "$VERSION" ] || die "latest 未指向 $VERSION（registry 同步较慢？稍后重查）"
  missing=()
  for v in "${VARIANTS[@]}"; do
    npm view "${NPM_PACKAGE}-${v}@${VERSION}" version >/dev/null 2>&1 || missing+=("${NPM_PACKAGE}-${v}")
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    printf '✗ 以下平台子包查不到 %s：\n' "$VERSION" >&2
    printf '  - %s\n' "${missing[@]}" >&2
    die "平台子包不齐（该平台用户会静默装不上）"
  fi
  ok "6 个平台子包 + 主包均已在 registry 上，latest == $VERSION"
  echo
  echo "🎉 发布完成：$NPM_PACKAGE@$VERSION"
fi
