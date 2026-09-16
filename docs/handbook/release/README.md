# 发布与重启（zace-client npm 包 / 服务 / 前端）

> **读者**：要发一次新版本、或改完代码要让环境生效的人。
> **产出**：npm 上新的 `zace-client@<版本>`，以及跑着新代码的服务与前端。

## 0. 一条命令看懂全流程

```text
改版本号(三处一致) → 提交 → 推到 main → 打 tag v<版本> → Release 构建 5 平台二进制
                                                              ↓
                          本地服务重启（生效新代码）      npm publish（在资产就绪之后）
```

**唯一的硬约束**：`npm publish` 必须在 Release 资产**全部就绪之后**。
`npx zace-client` 的运行方式是「按版本号去 GitHub Release 下载对应平台的二进制」
（`npm/run.js` → `releases/tags/v<version>`），资产没齐就发布 = 用户 404。

## 1. 发布 zace-client

### 1.1 版本号（四处，必须一致）

| 文件 | 字段 |
|---|---|
| `client/Cargo.toml` | `version` |
| `npm/package.json` | `version` |
| `server.json` | `version` 与 `packages[0].version` |

```bash
bash scripts/check-version.sh v0.0.4     # 校验四处一致 + 与待发布 tag 一致
```

**为什么要这个脚本**：三者不一致时，npm 包装器会去 GitHub 找一个不存在的 tag，
表现为「包装器启动失败」，根因却在版本号——这是最费时间排查的一类故障。

### 1.2 发版

```bash
git commit && git push origin main
git tag -a v0.0.4 -m "<一句话说明>"       # tag 必须指向**已包含改动**的提交
git push origin v0.0.4                     # 触发 .github/workflows/release.yml
```

构建 **5 个平台资产**：Linux x86_64/aarch64(musl)、macOS universal、Windows x86_64/aarch64。
实测约 3 分钟（与缓存冷热相关）。**成功标志**：Release 页有 **5 个平台资产 + `SHA256SUMS`**。

```bash
# 确认平台资产齐（应为 5）
curl -s https://api.github.com/repos/baoanaz/zace/releases/tags/v0.0.4 \
  | grep -c '"name": "zace-client_'
```

### 1.3 npm publish

```bash
cd npm && npm publish        # 需要已登录且有该包发布权
npm view zace-client version # 确认 latest 已更新
```

### 1.4 tag 打错了要重发（版本从未发布到 npm 时）

```bash
git push origin :refs/tags/v0.0.4     # 删远程 tag
git tag -d v0.0.4                     # 删本地 tag
git tag -a v0.0.4 -m "..."            # 重新指向修复提交
git push origin v0.0.4                # 重新触发构建
```

> 仅当该版本**尚未 `npm publish`** 时可用（npm 不允许重复发布同一版本号）。
> 已发布过就换新版本号，别改写历史。

### 1.5 client 代码改动的两个构建约束（实测踩过）

**① 编译期资源不能跨出 crate 目录。**
`aarch64-unknown-linux-musl` 走 `cross`（Docker），而 **cross 只把 crate 根目录挂进容器**——
容器内 `/project/..` 是容器的 `/`（`bin/boot/dev/...`），仓库上层的 `docs/` 完全不可见。
所以 `include_str!("../../docs/...")` 在这一个平台必然编译失败（其余 5 个平台正常，极易漏看）。

- 需要编译期嵌入仓库文件时，在 crate 内保留一份副本（如 `client/contract/`），
  并加测试与权威文件逐字节比对（`contract_copy_matches_repo_copy`）；
- **验证方式**：本地 `cargo build` 看不出来，必须看 Release 是否 5 个平台资产齐全。

**② 描述类文本改动也要发版才生效。**
MCP 的 `tools/list` 在 stdio 面由 **client** 声明（`protocol.rs` → `tools::definitions()`），
service 那份 description 到不了 AI 眼前。改了工具描述（含 CF-06 契约）**必须发 client 新版本**，
否则编辑器里看到的仍是旧文案。

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
| 只发了 client | 打 tag → 等 5 平台资产 → `npm publish`（**服务不用重启**） |
| 改了 core 检索逻辑 | 跑 `benchmark/README.md` 的回归 → 重建前端 → 重启服务 |
| 改了工具 description | 改 `docs/contracts/mcp-tools.json` → **同步 `client/contract/`** → 发 client |

| 现象 | 原因 |
|---|---|
| Release 只有 4 个平台资产 | cross（aarch64-musl）失败，多半是编译期资源跨出 crate 目录 |
| `npx zace-client` 403 rate limit | GitHub API 限流，重试即可（非发布缺陷） |
| `npx` 仍是旧描述/旧行为 | 该版本没发，或 npx 缓存了旧二进制（清 `~/.cache/zace-client/<版本>/`） |
| npm 报 `cannot publish over` | 该版本号已发布过，换版本号 |

## 相关文档

- 密钥与隐私 → [`../privacy/资产清单.md`](../privacy/资产清单.md)
- 部署（VPS / WSL）→ [`../deployment/vps.md`](../deployment/vps.md)、[`../deployment/wsl-live.md`](../deployment/wsl-live.md)
- Agent 接入 → [`../getting-started/agent接入与API-Key.md`](../getting-started/agent接入与API-Key.md)
- 改动检索后回归 → [`../benchmark/README.md`](../benchmark/README.md)
