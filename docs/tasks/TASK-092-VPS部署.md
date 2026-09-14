# TASK-092：VPS 部署（docker compose 单栈 + 公网发布）

> 状态：pending ｜ 阶段：Phase 5（M5，上线）｜ 硬依赖：TASK-089（MCP 越权口）、TASK-090（日志）
> 建议分支：`feature/task-092-deploy_<你的缩写><MMDD>`
> 交付物所有权：
> - `deploy/`（**新建**：`docker-compose.yml`、`Caddyfile`、`.env.example`、`README.md`）
> - `service/Dockerfile`、`web/Dockerfile`（**新建**）
> - `docs/handbook/部署.md`（**新建**）
> - `.github/workflows/`（如需镜像构建流水线）
>
> 清单外文件不得改（尤其 `core/**`、`service/zace_service/**` 的实现代码）。
> **注意：本机没有 docker**（编排者核实 `docker --version` 不存在）——本卡的验收必须包含
> "在目标 VPS 上真实跑起来"，本地无法完整验证的部分要如实说明。

## 背景（用户 2026-09-14 明确要求）

> 等全部稳定后，补上 VPS 部署。就可以基于 VPS 的 IP 公网发布了。

设计依据：`docs/design/Module/06-服务化与部署.md` §4-A（已定稿）：

```yaml
services:
  caddy:        # 443 自动 TLS → service:8000(/api)、web:3000(/)
  zace-service: # volume: ~/.zace（projects/ + zace-meta.db）
  zace-web:     # 静态 SPA
```

- 规格：**2C4G 起步**，4C8G 舒适；磁盘 <500MB/百万行代码；
- **不上 k8s**（V1 上限是单 compose）。

## 前置阻断（**开工前必须确认已合并**）

| 前置 | 为什么 |
|---|---|
| **TASK-089**（MCP 面归属校验） | 当前云端 MCP 面**仍是越权面**（B 可检索 A 的代码）——公网发布前**必须**修好 |
| **TASK-090**（请求日志与 trace 查询） | 发布后有人报错，你才能按 `X-Request-Id` 查到日志 |
| TASK-061（REST 归属） | 已合并 ✅ |

**若这两张卡未合并，本卡不得开工**（否则等于把越权面发布到公网）。

## §A 镜像

- **`service/Dockerfile`**：Python 3.12 + `uv`；装 `core` + `service`（**不含** web/client）；
  - 注意：**本地 ONNX embedding 会拉大镜像**（onnxruntime + 模型）；V1 用云端 embedding
    （`EMBED_MODE=api`），镜像里可考虑不装 onnxruntime（**你评估，报告说明**）；
  - 启动命令：`zace-service serve --host 0.0.0.0 --port 8000`；
  - **健康检查**：用 `/healthz`（已存在）。
- **`web/Dockerfile`**：多阶段（node build → 静态产物）；**产物交给 Caddy**，
  所以 web 容器可以是"只提供静态文件"的极小镜像（**或**直接把 `web/dist` 打进 Caddy 镜像——
  你评估哪个更简单，报告说明）。
- **`.dockerignore`**：必须排除 `.venv`、`node_modules`、`client/target`、`benches/results`、
  **`.env`（密钥绝不进镜像）**。

## §B compose

- 三个服务：`caddy` / `zace-service` / `zace-web`（或静态产物直接给 caddy）；
- **数据卷**：`zace-service` 的 `~/.zace`（`projects/` + `zace-meta.db`）**必须持久化**；
- **Caddy**：443 自动 TLS；`/api/*` 与 `/mcp` → service；`/` → web；
  - 证书需要域名。**若用户暂时只有 IP、没有域名**：Caddy 自动 TLS 不可用（Let's Encrypt 要求域名）。
    **这种情况必须给出可行方案**（如：先用自签证书 / 或 Caddy 的 `tls internal` / 或纯 HTTP + 后续补域名），
    并在报告里写清"基于 IP 发布"的实际限制与安全后果（**明文的 API key 会暴露**）。
- **环境变量**：通过 compose 的 `env_file` 注入（`.env` 不进仓库）；
  必填项在 `deploy/.env.example` 里逐条说明（`ZACE_DATA_ROOT`、`ANSWER_*`、`EMBED_*`、
  `ZACE_REGISTER_OPEN`、`ZACE_COOKIE_SECURE` 等）。
- **`ZACE_COOKIE_SECURE=true`**：上云必须开（TASK-060 的配置项，默认 false 是给本地 http 调试的）。

## §C 上线检查清单（写成 `docs/handbook/部署.md`）

手册要"用户照着做就能起来"，至少含：

1. **服务器准备**：规格建议、装 docker/compose、开 80/443 端口；
2. **配置**：`.env` 逐项说明（哪些必填、怎么生成 key）；
3. **首次启动**：`POST /api/auth/bootstrap` 建首个账户（或把 `register` 打开建完再关）；
4. **域名与 TLS**：域名解析 → Caddy 自动证书；**没有域名时的替代方案与风险**；
5. **验证**：`/healthz`、`/api/meta`、UI 可达、**真实 `npx zace-client` 用公网地址接入并提问**；
6. **备份**：数据卷怎么备份（`zace-meta.db` + `projects/`）；
7. **升级**：重建镜像、数据兼容性；
8. **常见故障**：证书失败、端口占用、`needsBootstrap` 卡住、embedding key 缺失。

## 验收标准（DoD）

- [ ] **本机验证**（docker 不可用时如实说明）：
  - [ ] `docker compose config` 语法校验通过（若本机能装 docker），或
  - [ ] 至少完成 compose 文件与 Caddyfile 的**静态自检**（YAML 语法 + 变量引用完整性脚本）；
  - [ ] **如实报告本机验证到了哪一步**（不要声称跑过没跑过的）。
- [ ] **VPS 验证**（**核心凭证，必须在真实服务器上做**）：
  - [ ] `docker compose up -d` 三个服务健康；
  - [ ] 公网 `https://<域名>/healthz` 返回 `status: ok`；
  - [ ] 公网 UI 可打开并能初始化账户；
  - [ ] **真实 `npx zace-client --base-url https://<域名>` 接入并提问成功**（贴输出）；
  - [ ] 数据卷持久化：重启容器后索引与账户仍在（贴验证）。
- [ ] **安全项**（逐条勾选，缺一不可）：
  - [ ] `ZACE_REGISTER_OPEN=false`（建完账户就关）；
  - [ ] `ZACE_COOKIE_SECURE=true`；
  - [ ] 镜像里**不含** `.env`（`docker history` 或 `docker run ls` 验证）；
  - [ ] 公网下 `/mcp` 未授权访问被拒（**这正是 TASK-089 的验收**）；
  - [ ] `/healthz` 不泄露 projectId 列表（TASK-089 顺带项）；
  - [ ] 日志里搜不到任何 key 明文。
- [ ] `docs/handbook/部署.md` 完整（含"没有域名怎么办"）。
- [ ] 基线三条命令全绿（本机）。
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- 不上 k8s/helm（V1 上限是单 compose）；
- 不做 CI/CD 自动部署（V1 手动 `compose up` 即可）；
- 不做多机集群/负载均衡；
- 不做数据库外部化（SQLite 单机足够，Module/06 §4-A 口径）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：本机与 VPS 各自验证到哪一步的**诚实分层报告**、
"无域名"场景的实际处置、安全项逐条勾选结果。

## 执行记录

### 2026-09-14 · VPS 原生部署阶段记录（非 DoD 完成）

- **分支/提交基线**：按用户明确授权直接在 VPS `main @ ce2b42d` 操作。
- **实际部署**：因本机已有 nginx 占用 80/443，且 VPS 仅 2 vCPU / 1.9GB RAM，本阶段采用
  systemd (`zace-service`) + 既有 nginx + 静态 SPA，而非卡内设计的 Docker Compose + Caddy。
- **公开路径**：Web 为 `https://154.12.34.214/zace-web/`；service base URL 为
  `https://154.12.34.214/zace-service`。未保留旧 `/zace/`、`/zace-api/` 路径。
- **代码改动**：Vite `base` 读取 `ZACE_WEB_BASE`，React Router `basename` 使用
  `import.meta.env.BASE_URL`；生产构建同时设置
  `ZACE_WEB_BASE=/zace-web/` 与 `VITE_ZACE_API_BASE=/zace-service`。
- **真实验证**：`npm run lint`、`npm run typecheck`、生产 `npm run build`、`nginx -t` 通过；
  公网 Web 入口、hash 静态资源、SPA 深层路由、`/healthz`、`/api/meta` 均返回 200；nginx 与
  zace-service 均为 active + enabled。
- **已知基线失败**：`npm test -- src/app/App.test.tsx` 为 4 passed / 3 failed，失败与改动前交接
  一致，报错为 Node/jsdom `AbortSignal` 实例不匹配。
- **未决/未完成**：卡内 `deploy/`、Dockerfiles、部署手册及 compose/Caddy 验收尚未交付；
  `npx zace-client` 鉴权 E2E、MCP stdio、服务重启后的账户/索引持久化仍待验证。因此本卡继续
  保持 `pending`，不得据此声明 TASK-092 DoD 完成。
