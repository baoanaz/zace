# zace-web

zace 的**管理面与 Playground**（Module 07 / D-40）。静态 SPA，直连 `zace-service` 的 REST API；
**不做**检索与渲染——ContextPack → Markdown 由服务端完成，web 只做分节包装与元数据展示。

```text
浏览器 ── 静态 SPA（本目录产物）── REST /api ──► zace-service ──► zace-core
```

## 现在有什么（本版本）

| 页面 | 路径 | 数据来源 |
|---|---|---|
| 项目总览 | `/` | `GET /healthz` + `GET /api/projects`；绑定本地目录、重扫、删除 |
| 项目详情 | `/projects/:id` | `GET /api/projects/{id}`；索引统计、sync 账本、重扫、删除 |
| Playground | `/playground` | `POST /api/query/search`（Fast）与 `POST /api/query/ask`（Deep 降级包） |
| 接入指南 | `/connect` | 编辑器 MCP 片段、CLI 与 curl 示例、数据落点与隐私、常见问题 |

**未就绪页面**（`/login`、`/register`、`/setup`、`/tokens`、`/usage`、`/settings`）渲染统一的
"尚未就绪"说明并标注依赖卡号——**刻意不用假数据填充**，否则会让人以为后端已经支持。

后端依赖（见 `docs/tasks/`）：登录/注册/初始化账户与 API Key → TASK-060；索引成功/失败次数与
平均耗时 → TASK-062；查询用量与 citationCoverage → TASK-064；租户隔离 → TASK-061。

## 开发

```bash
# 1) 起一个有数据的服务（终端 A）
export NO_PROXY=127.0.0.1,localhost
uv run zace-service local --repo /绝对路径/你的仓库 --data-root /tmp/zace-web --port 8787

# 2) 前端（终端 B）
cd web
npm ci
npm run dev            # http://127.0.0.1:5173
```

Vite 把 `/api` 与 `/healthz` 代理到 `ZACE_WEB_API`（默认 `http://127.0.0.1:8787`）：

```bash
ZACE_WEB_API=http://127.0.0.1:8899 npm run dev
```

**为什么不用 CORS**：生产形态是 Caddy 同源托管（`/` 静态、`/api` 反代 service），
开发期用 Vite 代理即可，因此 service 无需增加 CORS 中间件。

## 命令

| 命令 | 作用 |
|---|---|
| `npm run dev` | 开发服务器（含代理） |
| `npm run build` | 类型检查 + 产物到 `dist/`（静态托管） |
| `npm run lint` | ESLint（`--max-warnings 0`） |
| `npm test` | vitest（单元测试默认全跑，端到端测试默认跳过） |

## 端到端测试（真实服务）

单元测试用的是 mock，只能证明"按我以为的契约解析了"。要证明"服务端实际返回被正确渲染"，
用真实服务跑：

```bash
ZACE_E2E=1 ZACE_E2E_BASE=http://127.0.0.1:8787 ZACE_E2E_PROJECT=<projectId> \
  VITE_ZACE_API_BASE=http://127.0.0.1:8787 npx vitest run src/pages/e2e.test.tsx
```

它断言真实检索结果里出现 `[E*]` 证据块与「文件:行号」——ContextPack 的硬要求。

## 与设计文档的对应

- `docs/design/Module/07-WebUI.md`：页面骨架与对接原则（§2 的四条纪律是本目录的规范）
- `docs/design/INDEX.md` §3 **D-40**：V1 = 管理面 + Playground，**复用服务端渲染不自研**
- `docs/contracts/openapi.yaml`（CF-05）：唯一消费的接口契约
- `docs/tasks/TASK-070-web骨架与Playground.md`：本目录的任务卡与验收标准

## 目录

```text
src/
  api/         唯一请求出口（client.ts）+ CF-05 类型（types.ts）
  app/         路由与布局、接入指南文案、未就绪页清单
  components/  展示组件（Markdown 是唯一的渲染入口）、indexProgress 口径
  pages/       请求 + 组合
```

约定：`components/` 不发请求；所有错误经 `ApiError` 统一展示；`indexProgress` 渲染**不出现百分比**
（core 无进度回调，宁可信息少不可信息假）。
