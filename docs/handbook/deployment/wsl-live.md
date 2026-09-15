# WSL 本地测试环境（与生产同构）

> **读者**：要在本地用**和生产一样的 URL 形态**验证真实 Agent 接入的人。
> **前提**：已按 [`../getting-started/README.md`](../getting-started/README.md) 装好依赖。
> **产出**：`http://localhost/zace-web/` + `http://localhost/zace-service/`（含 `/mcp`）。
>
> **为什么不用 `local` 模式**：`zace-service local --repo <目录>` 是免鉴权的单用户模式，
> 与生产的鉴权链路不同，验证不了接入配置能否平移到生产。

## 1. 与生产的一致性

| 项 | 生产（VPS） | 本地（WSL） |
|---|---|---|
| 前端路径 | `/zace-web/` | 同 |
| 后端路径 | `/zace-service` | 同 |
| 模式 | `serve`（完整鉴权） | 同 |
| 数据根 | `/root/.zace` | `~/.zace/live` |
| 静态托管 | nginx | nginx |
| 访问地址 | `https://<域名>/...` | `http://localhost/...` |

**关键约束**：数据根独立于代码——换代码、重建前端、重启服务都不影响已索引的数据与账户。

**启停策略**：**按需启停，不开机自启**。收到部署指令才 `start`，收到暂停指令就 `stop`。

## 2. 从零到跑起来（五步）

```bash
# ── ① 依赖 ─────────────────────────────────────────
sudo apt-get update && sudo apt-get install -y nginx
sudo systemctl disable nginx          # 关键：关闭开机自启

# ── ② 隐私资产（env 文件）──────────────────────────
tar xzf zace-secrets.tar.gz -C ~/
bash ~/zace-secrets/restore.sh wsl   # 交互式：填用户名/路径/key

# ── ③ nginx + systemd ──────────────────────────────
sudo cp ~/zace-secrets/nginx/zace-wsl.conf /etc/nginx/sites-available/zace-live
sudo ln -sf /etc/nginx/sites-available/zace-live /etc/nginx/sites-enabled/zace-live
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t

sudo cp ~/zace-secrets/systemd/zace-live.service /etc/systemd/system/
sudo systemctl daemon-reload

# ── ④ 前端构建 ─────────────────────────────────────
cd ~/2_github/AI/ACE/zace/web
ZACE_WEB_BASE=/zace-web/ VITE_ZACE_API_BASE=/zace-service npm run build

# ── ⑤ 启动 ─────────────────────────────────────────
sudo systemctl start zace-live nginx
curl -s http://localhost/zace-service/healthz     # {"status":"ok",...}
curl -sI http://localhost/zace-web/ | head -1     # 200
```

## 3. 固定 URL 与端口

```text
http://localhost/zace-web/         前端
http://localhost/zace-service/     后端（含 /mcp）
```

| 端口 | 用途 |
|---|---|
| 80 | nginx（对外唯一入口） |
| 8787 | zace-service（仅监听 `127.0.0.1`，由 nginx 转发） |

## 4. 环境变量文件

位置固定在 `~/.config/zace/live.env`，权限 `0600`。

**这是数据根的配置文件，不是临时变量**：所有服务都从它读配置，写一次就长期有效，
不要用 `export` 在终端里临时设（那样每次都要重设，且换终端就丢）。

```bash
mkdir -p ~/.config/zace
cat > ~/.config/zace/live.env <<'EOF'
ZACE_DATA_ROOT=/home/<USER>/.zace/live
ZACE_LOCAL_RESCAN_INTERVAL=0

EMBED_MODE=api
EMBED_MODEL=voyage-4-lite
EMBED_BASE_URL=https://api.voyageai.com
EMBED_DIM=1024
EMBED_CONCURRENCY=4
EMBED_BATCH_SIZE=500
EMBED_BATCH_TOKEN_BUDGET=300000
EMBED_MAX_INPUT_TOKENS=32000
EMBED_API_KEY=<Voyage key>

ANSWER_BASE_URL=http://<gateway>:8080/v1
ANSWER_MODEL=deepseek-flash
ANSWER_API_KEY=<gateway key>
ANSWER_TIMEOUT_S=120
ANSWER_MAX_TOKENS=16384

ANSWER_PROVIDER=DeepSeek
ANSWER_MAX_CONTEXT_TOKENS=1048576
EMBED_TPM=16000000
EMBED_RPM=2000

# TASK-110 §7.1：首个管理员按**名字**指定（默认值就是 xuwenzheng，显式写出便于换部署人）。
# 服务启动时把它提为 role='admin'；账户不存在时只记一行日志，不报错。
ZACE_ADMIN_NAME=xuwenzheng
EOF
chmod 600 ~/.config/zace/live.env
```

写入后自查（确认文件确实落盘）：

```bash
ls -l ~/.config/zace/live.env
grep -E '^(ZACE_DATA_ROOT|ANSWER_MODEL|ZACE_ADMIN_NAME)=' ~/.config/zace/live.env
```

> 隐私包里已带这份文件的模板与恢复脚本，见
> [`../privacy/资产清单.md`](../privacy/资产清单.md)。

## 5. nginx 站点配置

`/etc/nginx/sites-available/zace-live`（`<USER>` 换成实际用户名）：

```nginx
server {
    listen 80;
    server_name localhost;

    location /zace-web/ {
        alias /home/<USER>/2_github/AI/ACE/zace/web/dist/;
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
```

启用并移除默认站点：

```bash
sudo ln -sf /etc/nginx/sites-available/zace-live /etc/nginx/sites-enabled/zace-live
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
```

## 6. systemd 单元（按需启停，不自启）

`/etc/systemd/system/zace-live.service`：

```ini
[Unit]
Description=zace service (WSL live environment)
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/<USER>/2_github/AI/ACE/zace
EnvironmentFile=/home/<USER>/.config/zace/live.env
ExecStart=/home/<USER>/2_github/AI/ACE/zace/.venv/bin/zace-service serve --host 127.0.0.1 --port 8787
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo cp <上面的文件> /etc/systemd/system/zace-live.service
sudo systemctl daemon-reload
```

**不要执行 `systemctl enable`**——那会让它在 WSL 启动时自动运行。启用用 `start`，停止用 `stop`。

## 7. 启动与停止

```bash
# 启动
cd ~/2_github/AI/ACE/zace/web
ZACE_WEB_BASE=/zace-web/ VITE_ZACE_API_BASE=/zace-service npm run build   # 代码有更新才需要
sudo systemctl start zace-live
sudo systemctl start nginx

# 停止（数据保留在 ~/.zace/live，下次启动即恢复）
sudo systemctl stop zace-live
sudo systemctl stop nginx

# 看状态与日志
systemctl status zace-live
journalctl -u zace-live -n 50 --no-pager
```

## 8. 首次初始化与 API Key

仅首次部署需要（之后账户已存在，跳过）：

```bash
curl -s -X POST http://localhost/zace-service/api/auth/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{"name":"admin","password":"<密码>"}' -c /tmp/zace-cookie.txt
```

创建 Agent 用的 API Key（**明文只返回这一次**）：

```bash
curl -s -X POST http://localhost/zace-service/api/auth/tokens \
  -H 'Content-Type: application/json' -b /tmp/zace-cookie.txt \
  -d '{"name":"agent-key"}'
```

## 9. Agent 接入配置

```toml
[mcp_servers.zace]
command = "npx"
args = ["-y", "zace-client", "--base-url", "http://localhost/zace-service", "--token", "<API KEY>"]
startup_timeout_ms = 60000
```

`--base-url` 填**根地址**（`http://localhost/zace-service`），不带 `/mcp`，也不能只写 `http:`。

验证客户端可用：

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
| npx -y zace-client --base-url http://localhost/zace-service --token <API KEY> \
| head -3
```

预期 `tools/list` 返回 `search_context` 与 `ask_project`。
完整接入手册见 [`../getting-started/agent接入与API-Key.md`](../getting-started/agent接入与API-Key.md)。

## 10. 数据持久化边界

```text
~/.zace/live/                  ← 数据（换代码不动它）
├── zace-meta.db               ← 账户 / API Key / 审计 / 项目归属
└── projects/<projectId>/      ← 每个项目的索引

~/.config/zace/live.env        ← 配置（写一次长期有效）
/etc/systemd/system/zace-live.service   ← 启动定义
/etc/nginx/sites-available/zace-live    ← 路由定义
```

- 换代码（`git pull`）、重建前端、重启服务，数据都在；
- 客户端缓存按 endpoint 分片（`~/.cache/zace/<endpointHash>/<projectId>/`），
  换 `--base-url` 会自然作废旧缓存；
- core 的切片或嵌入指纹变化会触发索引重建（首次检索变慢），数据不丢。

## 相关文档

- 生产部署 → [`vps.md`](vps.md)
- 密钥与隐私包 → [`../privacy/资产清单.md`](../privacy/资产清单.md)
- 检索改动后的回归 → [`../benchmark/README.md`](../benchmark/README.md)
- 排障 → [`../operations/请求日志与trace-id报错手册.md`](../operations/请求日志与trace-id报错手册.md)
