#!/usr/bin/env bash
# pack-secrets.sh — 收集仓库外的隐私资产，打成可搬运的 tar.gz。
#
# 用途：换机器（WSL / VPS）时，把不能进 git 的东西一次性带过去。
#      配套恢复脚本在包内 restore.sh；说明书见
#      docs/handbook/privacy/资产清单.md。
#
# 用法：
#   bash scripts/pack-secrets.sh [-o 输出路径] [-y]
#
#   -o  输出文件（默认 ~/zace-secrets.tar.gz）
#   -y  跳过确认
#
# 安全：本脚本只读不写仓库外文件；输出的包权限 0600。
#      **绝不**把包放进 git 工作区。
set -euo pipefail

OUT="${HOME}/zace-secrets.tar.gz"
ASSUME_YES=0

while getopts ":o:yh" opt; do
  case "$opt" in
    o) OUT="$OPTARG" ;;
    y) ASSUME_YES=1 ;;
    h) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知选项：-$OPTARG（用 -h 看用法）" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PKG="$WORK/zace-secrets"
mkdir -p "$PKG"/{env,npm,systemd,nginx}

say()  { printf '  %s\n' "$*"; }
warn() { printf '  \033[33m! %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }

# copy_secret <源> <目标相对路径>
# 复制文件并强制 0600；源缺失时给出提示但不中断（部分资产可能本机没有）。
copy_secret() {
  local src="$1" dst="$PKG/$2"
  if [ ! -f "$src" ]; then
    warn "缺失：$src（跳过）"
    return 0
  fi
  install -m 600 "$src" "$dst"
  ok "$2  ←  $src"
}

echo "== 收集隐私资产 =="

copy_secret "$REPO_ROOT/.env"                    env/project.env
copy_secret "${HOME}/.config/zace/live.env"      env/live.env
copy_secret "${HOME}/.config/zace/benchmark.env" env/benchmark.env
copy_secret "${HOME}/.npmrc"                     npm/npmrc

# env 里的本机绝对路径要占位化，否则换机器会把数据写到不存在的目录。
placeholderize_env() {
  local f="$1" me="$(id -un)"
  [ -f "$f" ] || return 0
  sed -i -e "s|/home/${me}|<HOME>|g" "$f"
}

# systemd / nginx：包内放**规范模板**（带占位符，无密钥）。
# 若系统上存在现行文件，则一并提示与本机实际值的差异，但**不用它覆盖模板**
# （本机文件含硬编码路径/用户名，拷到新机器就失效）。
write_template() {
  local rel="$1"
  cat > "$PKG/$rel"
  ok "$rel（规范模板）"
}

write_template systemd/zace-live.service <<'EOF'
[Unit]
Description=zace service (WSL live environment)
After=network.target

[Service]
Type=simple
WorkingDirectory=<REPO>
EnvironmentFile=<HOME>/.config/zace/live.env
ExecStart=<REPO>/.venv/bin/zace-service serve --host 127.0.0.1 --port 8787
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

write_template systemd/zace-service.service <<'EOF'
[Unit]
Description=zace service
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/zace
EnvironmentFile=/etc/zace/zace.env
ExecStart=/opt/zace/.venv/bin/zace-service serve --host 127.0.0.1 --port 8787
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

write_template nginx/zace-wsl.conf <<'EOF'
server {
    listen 80;
    server_name localhost;

    location /zace-web/ {
        alias <REPO>/web/dist/;
        try_files $uri $uri/ /zace-web/index.html;
    }

    location /zace-service/ {
        proxy_pass http://127.0.0.1:8787/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_read_timeout 300s;
    }
}
EOF

write_template nginx/zace-vps.conf <<'EOF'
server {
    listen 80;
    server_name <DOMAIN>;

    location /zace-web/ {
        alias /opt/zace/web/dist/;
        try_files $uri $uri/ /zace-web/index.html;
    }

    location /zace-service/ {
        proxy_pass http://127.0.0.1:8787/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_read_timeout 300s;
    }
}
EOF

# 提示本机与模板的差异（供人工核对，不影响包内容）
for pair in "systemd/zace-live.service:/etc/systemd/system/zace-live.service" \
            "nginx/zace-wsl.conf:/etc/nginx/sites-available/zace-live"; do
  src="${pair##*:}"
  [ -f "$src" ] && say "本机已存在 $src（包内仍用模板；如需保留本机特化值，请手动改包内文件）"
done

# env 占位化（在 copy_secret 之后）
for f in "$PKG"/env/*.env; do placeholderize_env "$f"; done

# ---------- 打码检查：确保没把不该进包的东西塞进来 ----------
echo
echo "== 检查包内不含意外的大文件/明显非密钥文件 =="
if find "$PKG" -type f -size +64k | grep -q .; then
  warn "包内有 >64k 的文件，请确认："
  find "$PKG" -type f -size +64k -exec ls -lh {} \;
fi

# 模板文件不应含本机用户名/真实 home 路径（防手误拷入硬编码值）
if grep -rln "$(id -un)" "$PKG" 2>/dev/null | grep -v '/env/\|/npm/' | grep -q .; then
  warn "模板中出现了本机用户名，请检查："
  grep -rn "$(id -un)" "$PKG" 2>/dev/null | grep -v '/env/\|/npm/' || true
fi

# ---------- 写入 README 与 MANIFEST ----------
cat > "$PKG/README.md" <<'EOF'
# zace 隐私包

**这是敏感文件，不要提交到任何 git 仓库、不要上传到任何网盘/聊天。**

## 用法

```bash
tar xzf zace-secrets.tar.gz -C ~/
bash ~/zace-secrets/restore.sh wsl     # 或 vps
```

恢复完成后，按 `docs/handbook/deployment/` 里的对应篇章继续。
完整清单与本机路径对照见仓库内 `docs/handbook/privacy/资产清单.md`。
EOF

{
  echo "# 包内文件清单"
  echo
  echo "生成时间：$(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "生成主机：$(hostname)"
  echo
  echo "| 包内路径 | 本机来源 | 恢复目标 | 权限 |"
  echo "|---|---|---|---|"
  echo "| env/project.env | zace/.env | <repo>/.env | 600 |"
  echo "| env/live.env | ~/.config/zace/live.env | ~/.config/zace/live.env | 600 |"
  echo "| env/benchmark.env | ~/.config/zace/benchmark.env | ~/.config/zace/benchmark.env | 600 |"
  echo "| npm/npmrc | ~/.npmrc | ~/.npmrc | 600 |"
  echo "| systemd/*.service | /etc/systemd/system/ | 同左 | 644 |"
  echo "| nginx/*.conf | /etc/nginx/sites-available/ | 同左 | 644 |"
  echo
  echo "## 轮转提醒"
  echo
  echo "若这些 key 曾以明文经过不可信通道，去各自控制台重新签发。"
  echo "轮转 embedding key **不需要重建索引**。详见资产清单 §8。"
} > "$PKG/MANIFEST.md"

# ---------- restore.sh ----------
cat > "$PKG/restore.sh" <<'RESTORE_EOF'
#!/usr/bin/env bash
# restore.sh — 把隐私包内容恢复到当前机器。
#
# 用法：bash restore.sh [wsl|vps]
#
# 交互式：会问你用户名（替换模板里的 <USER>）、仓库路径、域名。
# 幂等：重复执行会覆盖同名文件（先备份为 *.bak）。
set -euo pipefail

MODE="${1:-}"
if [ "$MODE" != "wsl" ] && [ "$MODE" != "vps" ]; then
  echo "用法：bash restore.sh [wsl|vps]" >&2
  echo "  wsl = 本地接入验证环境（~/.zace/live）" >&2
  echo "  vps = 生产环境（/root/.zace）" >&2
  exit 2
fi

PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_NAME="$(id -un)"
REPO_DEFAULT="$HOME/2_github/AI/ACE/zace"

read -rp "用户名 [$USER_NAME]: " u; USER_NAME="${u:-$USER_NAME}"
read -rp "仓库路径 [$REPO_DEFAULT]: " r; REPO_PATH="${r:-$REPO_DEFAULT}"
if [ "$MODE" = "vps" ]; then
  read -rp "公网域名（如 zace.example.com，无则回车跳过 nginx 域名替换）: " DOMAIN
else
  DOMAIN="localhost"
fi
read -rp "数据根 [$( [ "$MODE" = vps ] && echo /root/.zace || echo "$HOME/.zace/live" )]: " d

ok() { printf '  \033[32m✓\033[0m %s\n' "$*"; }

# backup_then_install <源> <目标> [mode] — 目标存在则先备份
backup_then_install() {
  local src="$1" dst="$2" mode="${3:-600}"
  [ -f "$src" ] || { echo "  跳过（包内没有）：$src"; return 0; }
  mkdir -p "$(dirname "$dst")"
  [ -f "$dst" ] && cp -p "$dst" "$dst.bak.$(date +%s)" && echo "  已备份原文件 → $dst.bak.*"
  install -m "$mode" "$src" "$dst"
  ok "$dst"
}

sed_subst() {  # 替换模板占位符
  local f="$1"
  sed -i "s|<USER>|$USER_NAME|g; s|<HOME>|$HOME|g; s|<REPO>|$REPO_PATH|g; s|<DOMAIN>|$DOMAIN|g; s|<DATA_ROOT>|$DATA_ROOT|g" "$f"
}

echo "== 恢复 env =="
DATA_ROOT="${d:-$( [ "$MODE" = vps ] && echo /root/.zace || echo "$HOME/.zace/live" )}"
export DATA_ROOT
for f in "$PKG"/env/*.env; do
  [ -f "$f" ] || continue
  sed_subst "$f"
done

backup_then_install "$PKG/env/project.env" "$REPO_PATH/.env" 600
backup_then_install "$PKG/env/live.env" "$HOME/.config/zace/live.env" 600
backup_then_install "$PKG/env/benchmark.env" "$HOME/.config/zace/benchmark.env" 600
chmod 700 "$HOME/.config/zace" 2>/dev/null || true

echo "== 恢复 npm token =="
backup_then_install "$PKG/npm/npmrc" "$HOME/.npmrc" 600

echo "== 恢复部署配置（需 sudo）=="
if [ "$MODE" = "wsl" ]; then
  SVC="$PKG/systemd/zace-live.service"; NGX="$PKG/nginx/zace-wsl.conf"; NGX_DST=zace-live
else
  SVC="$PKG/systemd/zace-service.service"; NGX="$PKG/nginx/zace-vps.conf"; NGX_DST=zace
fi
if [ -f "$SVC" ]; then
  sed_subst "$SVC"
  sudo install -m 644 "$SVC" "/etc/systemd/system/$(basename "$SVC")"
  ok "/etc/systemd/system/$(basename "$SVC")"
fi
if [ -f "$NGX" ]; then
  sed_subst "$NGX"
  sudo install -m 644 "$NGX" "/etc/nginx/sites-available/$NGX_DST"
  sudo ln -sf "/etc/nginx/sites-available/$NGX_DST" "/etc/nginx/sites-enabled/$NGX_DST"
  ok "/etc/nginx/sites-available/$NGX_DST"
fi
sudo systemctl daemon-reload 2>/dev/null || true

echo
echo "== 下一步 =="
if [ "$MODE" = "wsl" ]; then
  cat <<'NEXT'
  1) 构建前端：
     cd <repo>/web && ZACE_WEB_BASE=/zace-web/ VITE_ZACE_API_BASE=/zace-service npm run build
  2) 启动（按需，不要 enable）：
     sudo systemctl start zace-live nginx
  3) 验证：
     curl -s http://localhost/zace-service/healthz
     curl -sI http://localhost/zace-web/ | head -1
  详见 docs/handbook/deployment/wsl-live.md
NEXT
else
  cat <<'NEXT'
  1) 构建前端：
     cd <repo>/web && ZACE_WEB_BASE=/zace-web/ VITE_ZACE_API_BASE=/zace-service npm run build
  2) 启用并启动：
     sudo systemctl enable --now zace-service nginx
  3) 验证：
     curl -s https://<域名>/zace-service/healthz
  详见 docs/handbook/deployment/vps.md
NEXT
fi
echo
echo "提醒：确认 .env 权限为 600；不要把隐私包提交进 git。"
RESTORE_EOF
chmod +x "$PKG/restore.sh"

# ---------- 打包 ----------
echo
echo "== 打包 =="
rm -f "$OUT"
tar czf "$OUT" -C "$WORK" zace-secrets
chmod 600 "$OUT"

echo
ok "已生成：$OUT"
ls -lh "$OUT"
echo
echo "包内文件："
tar tzf "$OUT" | sed 's/^/  /'
echo
cat <<'TIP'
下一步：
  1) 把包拷到目标机器（scp / U 盘，**不要**走公开网盘或聊天）
  2) tar xzf zace-secrets.tar.gz -C ~/ && bash ~/zace-secrets/restore.sh wsl|vps
  3) 删掉中转副本：shred -u <包>  或  rm -P <包>

安全自查：
  - 包权限应为 600
  - 包不要放在 git 工作区内
  - 若曾经过不可信通道，去控制台轮转 key（见资产清单 §8）
TIP
