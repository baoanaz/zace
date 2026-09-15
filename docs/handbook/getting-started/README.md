# 快速开始（本地把 zace 跑起来）

> **读者**：第一次接触本仓库，想在本地跑通 core 的人。
> **产出**：能对一个仓库建索引并检索。
>
> 要**部署服务**（有 WebUI / MCP 接入）→ 看完本页后去
> [`../deployment/wsl-live.md`](../deployment/wsl-live.md)。

## 1. 环境要求

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | **3.12+** | core 与 service |
| [uv](https://docs.astral.sh/uv/) | 最新 | 包管理与运行（不要用裸 pip） |
| Node.js | 20+ | 仅前端 `web/` 与 MCP 客户端 `client/` |
| Rust | 1.75+ | 仅从源码构建 `client/`（用 `npx` 则不需要） |

```bash
# 检查
python3 --version   # 需 >= 3.12
uv --version
node --version
```

WSL 上安装 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 2. 获取代码与依赖

```bash
git clone https://github.com/baoanaz/zace.git
cd zace
uv sync          # 装全部 workspace 依赖
```

## 3. 仓库结构（要知道的三个目录）

```text
zace/
├── core/        zace_core：索引、检索、组装（纯逻辑，不依赖网络框架）
├── service/     zace_service：FastAPI 服务（HTTP + MCP 端点）
├── client/      Rust MCP stdio 客户端（本地扫描 + 上传代理）
├── web/         React 控制台
├── benches/     golden 用例与基准脚本
└── docs/        本手册 + 设计 + 任务卡
```

依赖方向是单向的：`service → core`，`client` 独立。
（有静态检查保护：`uv run python scripts/check_dependency_direction.py`）

## 4. 配置（最少一步）

**没有 key 也能用**吗？——检索需要 embedding，Mock embedding 仅供测试。
要用真实模型，需要配一个 key：

```bash
cp .env.example .env
chmod 600 .env       # 含密钥必须 600
# 编辑 .env，填 EMBED_API_KEY
set -a; source .env; set +a
```

主路径是 **Voyage `voyage-4-lite`**；备选硅基流动 `bge-m3`（免费但 TPM 低）。
细节与坑见 [`cloud-embedding.md`](cloud-embedding.md)，
密钥管理见 [`../privacy/资产清单.md`](../privacy/资产清单.md)。

## 5. 建索引并检索

```bash
# 建索引（--data 指定数据根；换机器时它要跟着走）
uv run zace-core ingest --repo /path/to/some/repo --data ~/.zace/demo

# 检索
uv run zace-core search --data ~/.zace/demo "你的问题"
```

> **数据根是你的数据资产**：索引与项目元数据都在这里，换代码不影响。
> 未指定 `--data` 时用默认位置。

## 6. 跑测试

```bash
uv run pytest -o addopts="" -q      # 全仓
uv run ruff check .                 # 风格
uv run python scripts/check_dependency_direction.py   # 依赖方向
```

> 根 `pyproject.toml` 设了 `addopts = "-q"`，直接 `uv run pytest` **不打印**汇总行；
> 要看数字加 `-o addopts=""`。

## 7. 下一步

| 目标 | 去哪 |
|---|---|
| 起服务 + WebUI + MCP 接入 | [`../deployment/wsl-live.md`](../deployment/wsl-live.md) |
| 编辑器里接 MCP（`npx zace-client`） | [`agent接入与API-Key.md`](agent接入与API-Key.md) |
| 改检索代码后跑回归 | [`../benchmark/README.md`](../benchmark/README.md) |
| 查请求问题 | [`../operations/请求日志与trace-id报错手册.md`](../operations/请求日志与trace-id报错手册.md) |
| 理解设计与决策 | [`../../design/INDEX.md`](../../design/INDEX.md) |

## 8. 常见问题

| 现象 | 原因 |
|---|---|
| `uv sync` 慢或失败 | 首次要下载依赖；检查网络/代理 |
| 索引报 embedding 错误 | `EMBED_API_KEY` 未加载（需 `set -a; source .env; set +a`） |
| 连不上 `127.0.0.1` | WSL 设了 `http_proxy`：`export no_proxy='*'` |
| `pytest` 没打印通过数 | 加 `-o addopts=""`（见 §6） |
| 检索结果很差 | 先用 golden 基准确认不是环境问题 → [`../benchmark/README.md`](../benchmark/README.md) |
