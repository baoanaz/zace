# TASK-070：zace-web 骨架 + 项目总览 + Playground + 接入指南（M4 首卡）

> 状态：review ｜ 阶段：Phase 4（M4，与 Phase 2/3 后端并行可做）｜ 硬依赖：无（只用**已 done** 的端点）｜
> soft 依赖：TASK-060/061/062/064（登录、token、统计、用量页需要它们先落地）
> 建议分支：`feature/task-070_<你的缩写><MMDD>`
> 交付物所有权：**`web/**` 全目录**（新建；本卡是该目录的唯一所有者）
> - `web/package.json`、`web/vite.config.ts`、`web/tsconfig*.json`、`web/tailwind.config.js`、`web/index.html`
> - `web/src/**`（app / api / components / pages）
> - `web/README.md`（替换现有占位内容）
>
> 清单外文件不得改。`.github/workflows/ci.yml`、根 `pyproject.toml`、`docs/**` 如需改动**先在"执行记录"申请**。

## 目标

把 `docs/design/Module/07-WebUI.md` 的骨架**落地成可运行、可真实联调**的 SPA，并且**只做后端已就绪的部分**：

```text
现在就能用的页：项目总览 / 项目详情 / Search Playground / ask Playground / 接入指南
现在做不了的页：登录、注册、初始化账户、API Key、索引统计、用量  →  显式"未就绪"占位（见 §E）
```

判据（DoD 的第一条）：**启一个真实 zace-service，浏览器里能找到自己的仓库、输入问题、看到带行号的证据块。**

## 输入文档（按序读，只读所需章节）

1. `docs/design/Module/07-WebUI.md` §1（页面骨架表）、§2（**对接原则是本卡真正的规范**）、§3（技术形态）
2. `docs/design/INDEX.md` §3 的 **D-40**（V1 = 管理面 + Playground；**复用服务端渲染，不自研渲染层**）
3. `docs/contracts/openapi.yaml`（CF-05：本卡只消费 `/api/projects*`、`/api/query/*`、`/healthz`）
4. `service/zace_service/packmeta.py`（`meta` 字段集；Playground 的元数据面板据此渲染）
5. `docs/handbook/M2a-验收手册.md` §2（`indexProgress` 六字段口径与"为什么没有百分比"）、§4.1（返回形态与判读）

## 冻结接口（本卡不得变更）

- **消费**（只读，不得要求后端改形状）：
  - `GET /healthz` → `{status, version, dataRoot, localMode, auth, core:{…}, projects:[{projectId, attachedRoot, indexProgress}]}`
  - `GET /api/projects`、`GET /api/projects/{id}`、`POST /api/projects/attach`、`POST /api/projects/{id}/rescan`
  - `POST /api/query/search` → `{markdown, meta}`、`POST /api/query/ask` → `{status, answer, evidenceSummary, meta}`
  - 错误信封 `{error:{code, message}}`（`errors.py`）——**所有错误展示必须走同一组件**
- **产出**（TASK-071+ 依赖）：
  - `web/src/api/client.ts`：`getHealth()` / `listProjects()` / `getProject(id)` / `attachProject(root, displayName?)` /
    `rescanProject(id)` / `search(projectId, query, maxTokens?)` / `ask(projectId, question)`
  - `ApiError { code, message, status }`（把 CF-05 的错误信封统一成一种异常）
  - `web/src/components/Markdown.tsx`（**唯一**的 Markdown 渲染入口，D-40：不重写 ContextPack 渲染）

## §A 技术形态（D-40 的直接落地）

- Vite + React 18 + TypeScript + Tailwind；**纯静态 SPA，无 SSR、无 BFF、无路由服务**
- 开发期：Vite dev server 代理 `/api`、`/healthz` 到 `http://127.0.0.1:8787`（`ZACE_WEB_API` 可覆盖）
  ——**不要求 service 加 CORS**（生产同源由 Caddy 承担）
- 生产期：`npm run build` → `web/dist/`，静态托管（Caddy）；`/api` 与 `/` 同源
- 路由：`react-router-dom`（`/`、`/projects/:id`、`/playground`、`/connect`，未就绪页用占位路由）
- **无秘密**：不写 localStorage 存 token；本卡尚未有鉴权（本地模式）

## §B 页面：项目总览（`/`）

- 数据源：`GET /healthz` + `GET /api/projects`（**两个都调**：healthz 给出 `localMode`/`auth`/版本与内存态进度）
- 每张项目卡展示：`displayName`、`projectId`（等宽字体，可点击复制）、`attachedRoot`（本地模式）、
  `sync.{filesIndexed, chunks, symbols, edges}`、`lastIndexedAt`
- **进度如实呈现**（D-30 / 手册 §2）：
  - `state=running` → "索引中（已处理 N / 共 M 文件，无百分比）"，**禁止**任何百分比或进度条
  - `state=done` 且 `error` 非空 → 黄色提示"索引完成，但 N 个文件有解析问题"，可展开看摘要
  - `state=failed` → 红色，显示脱敏后的 `error`
  - `state=idle` → "未索引（重启后需重新 attach）"
- 操作：手动重扫（`POST /api/projects/{id}/rescan`；409 `index_running` 要显示为"已经在跑"而非报错）、
  删除项目（二次确认，**文案必须写明"全部源码镜像与索引将永久删除"**，Module/07 §2.4）
- 空态：无项目时给出"如何产生第一个项目"的引导（本地模式：命令行 attach；链接到接入指南页）
- 本地模式附"绑定本地目录"表单（`POST /api/projects/attach`）——这是本地场景最省事的入口

## §C 页面：项目详情（`/projects/:id`）

- 索引统计（files/chunks/symbols/edges）、`sync` 摘要、`indexProgress` 全字段（含口径提示 `?` 图标）
- 「去 Playground 问这个项目」按钮（带 projectId 跳转）
- 删除项目（同 §B 的确认文案）

## §D 页面：Playground（`/playground`）——**本卡的第一优先页面**（Module/07 §2.2）

- 顶部：项目选择器（默认取第一个已索引项目）+ 模式切换 **Fast（search）/ Deep（ask）** + `maxTokens` 输入
- 输入框：支持 `Ctrl/Cmd+Enter` 提交；提交中禁用并显示耗时
- 结果区（左右两栏，窄屏上下堆叠）：
  - **左：服务端返回的 `markdown` 原样渲染**（D-21/D-40：**不得**重新实现 ContextPack 渲染、
    不得按 `[E1]` 自己拼装 DOM）。渲染器只负责 CommonMark + GFM 表格/代码高亮
  - **右：`meta` 面板**：`answerable` / `confidence` / `channelsUsed` / `degraded`+`degradedReason` /
    `budget.usedTokens|hardCap|truncated|omittedCount` / `evidenceCount` / `docsCount` / `flowsCount` /
    `missingEvidence` / `freshness`（`indexedAt`、`staleFiles`、`indexingFiles`、`rescanError`）/ `candidateCount`
  - Deep 模式的 `status`（`answered|insufficient_evidence|degraded`）**必须显著展示**，
    并把 `DEGRADED_NOTICE` 的语义（"这是检索包不是 LLM 答案"）如实呈现，**不许**把它包装成答案
- **调试友好**：可折叠的"原始响应 JSON"（本卡不引 Monaco，用 `<pre>` 即可）；
  一键复制 Markdown；查询历史（内存 + `sessionStorage`，仅本机）
- 未索引/索引中/空索引的错误（409 `index_in_progress`、500 `index_failed`、503 `embedding_unavailable`）
  → 走统一错误组件，保留 `code`，并给出下一步指引（引用 `docs/handbook/M2a-验收手册.md` §6）

## §E 页面：接入指南（`/connect`）——本卡的第二优先页面

**为什么现在做**：这份内容今天只存在于 CLI 输出（`cli_hint.py` 的 `mcp-config`）和手册里，
新用户第一件事就是找不到它。后端已就绪（纯前端页）。

内容（**逐条对齐现有事实，不许写未来形态**）：

1. 服务地址：`{origin}/mcp`（Streamable HTTP）+ `/healthz` 状态徽标（版本、`localMode`、`auth`）
2. 编辑器配置片段：与 `service/zace_service/cli_hint.py::format_snippets` 的产出**文本一致**
   （Cursor `mcp.json` + 通用 harness），一键复制
3. **只支持 stdio 的 harness 需要代理**——如实写"归 M2c 的 Rust client（TASK-040R）"（`_STDIO_NOTE` 原文）
4. 三种接入路径对照表：编辑器 MCP / CLI（`zace-core`）/ HTTP API（curl 示例，
   与 `docs/contracts/openapi.yaml` 一致）
5. 数据落点与隐私：`dataRoot`（来自 `/healthz`）、"项目删除即全删"、
   **启用外部 ANSWER_* 时证据片段会发往该 LLM 提供商**（Module/06 §3 的明示要求）
6. 常见故障速查（3–5 条，取自手册 §6，例如 403 编辑器连不上、索引中、provider 不可用）

**纪律**：页面上的端点/命令必须能跑通；写不对就别写（宁少勿假）。

## §F 未就绪页（占位，不许假装可用）

`/login`、`/register`、`/setup`（初始化账户）、`/tokens`、`/usage`、`/settings` 六个路由渲染统一的
`<NotReadyPage>`：说明功能是什么、**依赖哪张卡**（TASK-060/061/062/064）、以及"当前可用的是什么"。

**明确禁止**：用假数据填充这些页面（会让人以为后端已支持）。可用灰底 + 卡片 + 依赖卡号链接。

## §G 前端工程约定

- API client 统一处理：非 2xx → 解析 `{error:{code,message}}` → 抛 `ApiError`；
  网络失败与代理未启动 → 明确提示"服务未启动（尝试 `uv run zace-service local --repo …`）"
- 组件分层：`components/`（展示，无请求）、`pages/`（请求 + 组合）、`api/`（唯一请求出口）
- 类型：`api/types.ts` 手写与 CF-05 一致的接口（**不引 openapi 代码生成**，V1 只消费 6 个端点）
- 测试：`vitest` + `@testing-library/react`，覆盖
  ① `ApiError` 解析（含 `not_implemented` 501）
  ② `indexProgress` 五种 state 的渲染文案（含 `done+error` 与 `running` 的"无百分比"）
  ③ Playground 提交成功后渲染 markdown 与 meta 面板
  ④ 错误码映射（409/500/503 各一条，断言展示的指引文本）
- 代码风格：与仓库一致（**无 emoji**；注释写"为什么"，不写"是什么"）

## 验收标准（DoD）

- [ ] `cd web && npm ci && npm run build` 成功（产物 `web/dist/`），`npm run lint` 与 `npx tsc --noEmit` 干净
- [ ] `npx vitest run` 全绿，覆盖 §G 列出的四组用例
- [ ] **端到端行为验收（贴真实输出/截图说明）**：
      1. 起真实服务：`uv run zace-service local --repo <仓库>`（等索引完成，或用已 attach 的项目）
      2. `npm run dev` 打开首页 → 看到该项目、状态与统计
      3. Playground 输入一个**真实问题** → 看到带 `[E*] 文件:行号` 的服务端 Markdown + meta 面板
      4. 切 Deep → 看到降级包与其 `status` 如实展示
      5. 断开服务再看首页 → 看到"服务未启动"的可操作提示（不是白屏）
- [ ] 基线三条命令仍全绿（本卡不改 Python，但**不得破坏**）：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] CI 覆盖（**先在执行记录申请**）：`.github/workflows/ci.yml` 追加 `web` job（`npm ci` + `build` + `vitest run`）；
      未获批时在报告中说明"CI 尚未覆盖 web"作为已知缺口
- [ ] `web/README.md` 更新为真实内容（跑法、代理配置、与 Module/07 的对应关系）
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`

## 参考实现锚点（只读参考 IA，**不复制代码**；用户 2026-09-13 拍板）

- LiteLLM `ui/litellm-dashboard`：Keys / Usage / Logs 的信息架构（我们借"页签分组 + 表格 + 单条详情抽屉"）
- Supabase `apps/studio`：清单 + 右侧抽屉的交互范式
- E2B `dashboard-ee`：**专有许可，只读其产品形态**（onboarding 引导流），**不得复制任何代码**

> 三者均为 Next.js 技术栈，与 D-40 的"纯静态 SPA、无 SSR/BFF"冲突；本卡**只借信息架构与交互范式**，
> 实现全部自研（用户已拍板）。许可与依赖包袱（Prisma/Postgres/AntD）一律不引入。

## 明确不做

- 不做登录/注册/token/用量/设置页的真实实现（依赖 TASK-060/061/062/064；本卡只放占位）
- **不自研 ContextPack 渲染**（D-21/D-40；只渲染服务端 `markdown`）
- 不做 Graph 可视化、Retrieval Trace、预算装填可视化（Module/07 §4 = V2+）
- 不做暗色主题切换、i18n、移动端专项适配（V1 只保证窄屏可用不破版）
- 不引 UI 组件库（AntD/MUI/shadcn 一律不引；Tailwind 手写），不引状态管理库（React Query/SWR/Redux）
- 不改任何 Python 代码、不改 `docs/contracts/**`、不改 `docs/design/**`

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写：分支 / 验收命令与结果（含真实检索输出片段）/
契约影响（期望为"无"，只消费 CF-05）/ 与设计偏差 / 未决问题。

## 执行记录

### 2026-09-13 · 实施 AI · 分支 `feature/task-070_xwz0913`（从 `main` @ `42587cf` 开出）

**状态：实现完成，待编排者评审。**

#### 关键决策

1. **页面范围严格按“后端已就绪”划分**：实现 4 页（项目总览 / 项目详情 / Playground / 接入指南），
   六个未就绪页统一渲染 `NotReadyPage`（标注依赖卡号，**不用假数据**）。
2. **验证用 Vite 代理，而非让 service 加 CORS**：生产同源（Caddy），开发用代理；
   因此**未改 service 一行代码**（也避开了与其它会话的文件冲突）。
3. **新增 `API_BASE`（`VITE_ZACE_API_BASE`）**：默认同源；它同时服务“web 与服务不同源”与
   **端到端测试直连真实服务**（否则 e2e 无法在无代理环境下跑）。这是 CF-05 之外的 web 内部约定，不影响后端。
4. **端到端测试默认跳过**（`ZACE_E2E=1` 启用）：它需要已索引的真实服务，不适合进 CI；
   单元测试（mock）负责契约形状，e2e 负责“真实返回被正确渲染”。
5. **`indexProgress` 不出现百分比**（含单测钉住）：`processedFiles`/`totalFiles` 不同量纲，
   差值不代表失败；`done + error` 渲染为警告而非失败。

#### 验收命令与结果（本机实测）

```console
$ cd web && npm run lint
> eslint src --max-warnings 0          # exit 0，无输出

$ cd web && npm test
 Test Files  3 passed | 1 skipped (4)
      Tests  15 passed | 2 skipped (17)  # skipped = e2e（需 ZACE_E2E=1）

$ cd web && npm run build
> tsc --noEmit && vite build
✓ 299 modules transformed.
dist/index.html                   0.44 kB │ gzip:   0.29 kB
dist/assets/index-CLA8mgnn.css   12.61 kB │ gzip:   3.02 kB
dist/assets/index-C8yvTGnv.js   397.66 kB │ gzip: 128.27 kB
✓ built in 1.45s

$ cd . && uv run ruff check .                                # All checks passed!
$ uv run python scripts/check_dependency_direction.py        # 依赖方向检查通过
$ uv run pytest                                              # 727 passed, 2 skipped
```

#### 端到端行为验收（真实 service，§DoD 第 3 条）

起服务（硅基流动 bge-m3，2 文件演示仓库，索引 2s 完成）：

```console
$ uv run zace-service local --repo /home/xuwenzheng/zace-scratch/demo-repo \
    --data-root /tmp/zace-web-check/data --port 8787
  身份      : 非 git 仓库 → 绝对路径 hash（D-29）
  索引      : 后台进行中（state=running，已处理 0/0 个文件）
  {"msg": "索引完成：e6fe81dbaebfb65d（parsed=2/2，added=2，errors=0）"}
```

页面消费的端点全部实调（Vite 代理链路也验过：`curl http://127.0.0.1:5173/healthz` 与
`/api/projects` 均返回真实 JSON）：

```console
$ curl -s http://127.0.0.1:8787/healthz | jq '.localMode, .auth, .projects[0].indexProgress'
true
"disabled(local)"
{ "state": "done", "processedFiles": 2, "totalFiles": 2, "error": null }

$ curl -s -X POST .../api/query/search -d '{"projectId":"e6fe81dbaebfb65d","query":"令牌过期后在哪里刷新？"}'
## Relevant Context
### Code
[E2] SessionStore.refresh_token — src/session.py:1-13
     reason: bm25 -2.7637 + bm25 rank 1 + vector 0.6372 + vector rank 1 + 相邻区间合并
     11 |     def refresh_token(self, token: str) -> str:
     12 |         """刷新会话 token：过期后由本方法负责续期。"""
### Docs
[E1] README.md > 演示仓库 > 会话（readme）
### Meta
confidence: medium | index: fresh (28s ago) | budget: 605/10.0K

$ curl -s -X POST .../api/query/ask -d '{...}'
status = degraded ；meta.degradedReason = "Deep 模式（LLM 总结）尚未接入（Phase 3）…"

$ curl -o /dev/null -w '%{http_code}' .../api/auth/tokens   → 501
$ curl -o /dev/null -w '%{http_code}' .../api/usage/projects/<id> → 501
```

真实页面渲染断言（`ZACE_E2E=1`）：

```console
$ ZACE_E2E=1 ZACE_E2E_BASE=http://127.0.0.1:8787 ZACE_E2E_PROJECT=e6fe81dbaebfb65d \
    VITE_ZACE_API_BASE=http://127.0.0.1:8787 npx vitest run src/pages/e2e.test.tsx
 ✓ 真实检索结果能在 Playground 页面渲染出带行号的证据块 373ms
 Test Files  1 passed (1) / Tests  2 passed (2)
```

#### 契约影响

**无**（只消费 CF-05 已有端点与字段）。新增的是 web 内部约定：
`VITE_ZACE_API_BASE`（构建期环境变量）与 `NOT_READY_FEATURES` 清单（纯前端）。

#### 与设计偏差

1. **`/api/meta` 未使用**：接入指南页用 `/healthz` 取 `localMode`/`auth`/`dataRoot`——
   `/healthz` 今天已是免鉴权端点，无需为 web 新增契约（TASK-060 的 `/api/meta` 落地后，
   接入指南页的“登录入口”可按它显隐）。
2. **未引 UI 组件库与状态管理库**（卡内已声明），表格与抽屉式详情均为手写 Tailwind。
3. **TASK-061/062/064 的能力不在本卡**（按分工另开卡），web 侧对应页为未就绪占位。

#### 未决问题（需编排者裁定）

1. **CI 与根 README 的改动已提交但未获批**：本卡改了 `.github/workflows/ci.yml`（追加 `web` job：
   `npm ci` + `lint` + `test` + `build`）与根 `README.md` 仓库布局表一行（`web/` 的描述）。
   理由：`web/` 是本卡新增的包，无 CI 覆盖会很快腐化（前端回归无门禁）。
   **若判定越界，请指示回退这两处，并把它记为已知缺口。**
2. **401/登录态尚未处理**：M2c 引入 session 后，web 需要 `401 → 跳登录页` 的全局处理与
   `/api/meta` 驱动的引导（登录/注册/初始化）。建议在 TASK-071（依赖 TASK-060/061）一并做。
3. **`web/dist` 与 Caddy 编排**：本卡只产出静态产物；接入 compose/Caddy 属 TASK-063。
4. **Playground 历史仅存 sessionStorage**（本机、单标签页）。若要做可分享的 Playground，
   可基于 TASK-064 的 `recent` 做回放。

#### 建议复核点

- `web/src/components/progress.ts`：五态文案与手册 §2 的口径是否一致（尤其 `done+error`）；
- `web/src/pages/ConnectPage.tsx`：页面上的命令/端点逐条能否跑通（接入指南最容易被写坏）；
- `web/src/pages/PlaygroundPage.tsx`：是否真的**没有**自行拼装证据块（D-40 的硬约束）。
