# 发布与重启（zace-client npm 包 / 服务 / 前端）

> **读者**：要发一次新版本、或改完代码要让环境生效的人。
> **产出**：npm 上新的 `zace-client@<版本>`，以及跑着新代码的服务与前端。

## 0. 一条命令看懂全流程

```text
改版本号(四处一致) → 提交 → 推 main → 打 tag v<版本>
                                          ↓
            CI: 构建 6 平台 → 发 6 个子包 → 验证 → 发主包(next) → 冒烟 → promote latest
                                          ↓
                              VPS 部署（拉代码 + 重启服务）
```

> npm 发布细节（含手动流程与排障）→ [`npm.md`](npm.md)。

**唯一的硬约束**：发布 npm 时**先子包、后主包**。主包的 `optionalDependencies`
指向 6 个平台子包（`zace-client-<os>-<arch>`），子包没先上去，该平台用户就装不上。
CI 里由 `scripts/make-platform-packages.py publish` 保证这个顺序。

> **不再发 GitHub Release 二进制资产，也不再有任何下载回退**（D-48/D-49）。
> npm 平台子包是**唯一**的分发渠道。
>
> 为什么（实测踩到）：Node 默认**不读 `https_proxy`**（只认 `NODE_USE_ENV_PROXY=1`，v20+），
> 代理环境里启动器直连 GitHub 会命中共享出口 IP 的 403 rate limit——
> 同一时刻 `curl`（走代理）200、`node`（直连）403。
> 用户看到的是「MCP server failed to start: connection closed」，极难排查。
> 更深一层：保留下载回退 = 两条分发渠道并存，出错时无法判断用户拿到的是哪个二进制。
> 详见 [`npm.md`](npm.md) §5。

## 1. 发布 zace-client（npm）

**完整发布手册见 [`npm.md`](npm.md)**（六步流水线、脚本速查、排障、为什么删掉 GitHub 下载回退）。

速览：

```bash
# ① 改三处版本号 → 同步子包 → 校验
python3 scripts/make-platform-packages.py generate
bash scripts/check-version.sh v0.0.5
# ② 打 tag 触发 CI（构建 6 平台 → 发子包 → 验证 → 发主包 next → 冒烟 → promote latest）
git tag -a v0.0.5 -m "v0.0.5" && git push origin v0.0.5
```

要点：

- **npm 是唯一二进制分发渠道**（D-48/D-49）：6 个平台子包 `zace-client-<os>-<arch>`
  随包提供二进制，用户侧**没有下载步骤**；
- **先发子包、验证、再发主包（`--tag next`）、冒烟、最后 promote 到 `latest`** ——
  因为 npm 发布不可逆，latest 是最后一个可控点；
- 缺任一平台 = 该平台用户**静默**装不上（npm 不报错，只是跳过解析不了的可选依赖）；
- CI 需要仓库 secret `NPM_TOKEN`（Automation 类型）。

## 2. 重建前端

```bash
cd web
ZACE_WEB_BASE=/zace-web/ VITE_ZACE_API_BASE=/zace-service npm run build
# 产物：web/dist → nginx 的 /zace-web/ 站点根
```

两个变量必须与 nginx 公开路径一致：`ZACE_WEB_BASE` 决定产物资源 URL 与 Router `basename`，
`VITE_ZACE_API_BASE` 决定前端请求后端的前缀。

> 漏掉 `ZACE_WEB_BASE=/zace-web/` → 产物资源路径变成 `/assets/...` → nginx 回落默认站点 → **前端白屏**。

## 3. 重启服务

```bash
sudo systemctl restart zace-live      # WSL 同构环境
# sudo systemctl restart zace-service # VPS 生产

# 确认
systemctl status zace-live --no-pager | head -3
curl -s http://localhost/zace-service/healthz
curl -sI http://localhost/zace-web/ | head -1
```

**重启后前几秒可能 502**（进程在初始化）：等 3–5 秒再 curl。
`healthz` 返回 `{"status":"ok",...}` 即为就绪。

## 4. 顺序与坑

| 场景 | 顺序 |
|---|---|
| 只改了后端/前端代码 | 重建前端（若涉及）→ 重启服务 |
| 只发了 client | 打 tag → 等 5 平台资产 + 7 个 npm 包 → 服务**不用重启** |
| 改了 core 检索逻辑 | 跑 `benchmark/README.md` 的回归 → 重建前端 → 重启服务 |
| 改了工具 description | 改 `docs/contracts/mcp-tools.json` → **同步 `client/contract/`** → 发 client |
| 改了平台表（新增/删平台） | 改 `make-platform-packages.py` 的 `PLATFORMS` → `generate` → 同步 CI 矩阵 → `check-version.sh` |

| 现象 | 原因 |
|---|---|
| Release 只有 4 个平台资产 | cross（aarch64-musl）失败，多半是编译期资源跨出 crate 目录 |
| **某平台用户报「没有二进制」** | 该平台**子包没发或版本不一致**。这是**静默故障**（npm 跳过解析不了的可选依赖）；跑 `bash scripts/check-version.sh` 定位 |
| `npx zace-client` 403 rate limit | 旧版包装器在走 GitHub 下载路径。升到 ≥ `zace-client@0.0.5`（子包形态）即不再出现 |
| `npx` 仍是旧描述/旧行为 | 该版本没发，或 npx 缓存了旧二进制（清 `~/.cache/zace-client/<版本>/`） |
| npm 报 `cannot publish over` | 该版本号已发布过，换版本号 |

## 相关文档

- 密钥与隐私 → [`../privacy/资产清单.md`](../privacy/资产清单.md)
- 部署（VPS / WSL）→ [`../deployment/vps.md`](../deployment/vps.md)、[`../deployment/wsl-live.md`](../deployment/wsl-live.md)
- Agent 接入 → [`../getting-started/agent接入与API-Key.md`](../getting-started/agent接入与API-Key.md)
- 改动检索后回归 → [`../benchmark/README.md`](../benchmark/README.md)
