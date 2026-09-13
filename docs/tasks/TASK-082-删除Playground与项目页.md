# TASK-082：删除 Playground 与项目管理页（含导航、路由、死链、测试清理）

> 状态：review（2026-09-23 lane-c 实施完成，待编排者评审）｜ 阶段：Phase 4（M4）｜ 硬依赖：无 ｜ soft 依赖：TASK-083（空态组件）
> 建议分支：`feature/task-082-remove-pages_<你的缩写><MMDD>`
> 交付物所有权：
> - `web/src/app/App.tsx`（删路由与 import）
> - `web/src/app/Layout.tsx`（删导航项）
> - `web/src/pages/PlaygroundPage.tsx`、`web/src/pages/PlaygroundPage.test.tsx`（**删除**）
> - `web/src/pages/ProjectsPage.tsx`、`web/src/pages/ProjectDetailPage.tsx`（**删除**）
> - `web/src/pages/e2e.test.tsx`（删 Playground 相关用例，保留 healthz 可达性用例）
> - `web/src/pages/DashboardPage.tsx`（**仅**去掉指向 `/projects/*` 的链接与死链文案）
> - `web/src/pages/HistoryPage.tsx`（**仅**去掉指向 `/projects/*`、`/playground` 的链接与死链文案）
> - `web/src/api/client.ts`（**仅**删除因此不再被引用的导出函数）
>
> 清单外文件不得改。**特别提醒：不要改 `web/src/app/connect-info.ts` / `ConnectPage.tsx`（TASK-080 的领地）、
> 不要改 `web/src/components/ui.tsx`（TASK-083 的领地）。**

## 目标

用户原话（2026-09-13）：

> 3、Playground 删除，没用
> 4、项目 删除，没用

补充口径（用户在追问中确认）：

- **只删导航和页面**，仪表盘保留项目列表（否则看不到 Agent 索引了哪些库）；
- 删除后**同步清理相关测试**（不留假绿、不 skip）。

## ⚠️ 本卡的关键约束（编排者已预检）

### §A 两个删除必须在同一张卡

`App.tsx` 与 `Layout.tsx` 同时被 Playground 与项目页引用。拆成两张卡会让两个会话改同两个文件，
**必然冲突**。因此合并为本卡。

### §B 死链必须一起清理（否则用户点到就是 404）

删除路由后，以下位置的 `<Link>` 会指向不存在的路由（React Router 会落到 `*` 兜底 → 跳回首页，
看起来很诡异）。**必须逐处改掉文案**（去掉链接，改为纯文字或指向仍在的页面）：

| 文件 | 行（约） | 现状 | 改法 |
|---|---|---|---|
| `DashboardPage.tsx` | 157 | `还没有项目。去 <Link to="/projects">项目管理</Link> 绑定本地目录，或在编辑器里接入后让客户端同步。` | 去掉链接，改为说明"在编辑器里接入后让客户端同步" |
| `DashboardPage.tsx` | 175 | 项目表格里项目名是 `<Link to={`/projects/${id}`}>` | 改为纯文本（保留 `projectId` 列，信息不丢） |
| `DashboardPage.tsx` | 173 | 项目表格整体保留 | **保留**（用户明确要保留项目列表） |
| `HistoryPage.tsx` | 118 | `还没有索引记录。在 <Link to="/projects">项目管理</Link> 绑定本地目录…` | 去掉链接 |
| `HistoryPage.tsx` | 146 | 索引行里项目名是 `<Link to={`/projects/${projectId}`}>` | 改为纯文本 |
| `HistoryPage.tsx` | 231 | `去 <Link to="/playground">Playground</Link> 提问后…` | 去掉链接，改为"在编辑器里用 Agent 提问后" |

**要求**：改完后 `grep -rn 'to="/projects\|to="/playground\|/projects/\${' web/src/` **必须无结果**。

### §C 后端端点不要删

`/api/projects`、`/api/projects/{id}`、`/api/projects/{id}/rescan`、`/api/projects/attach` 是
**客户端与本地模式在用的真实接口**，删页面不等于删接口。本卡**只动 `web/`**，不碰 `service/`。

### §D `client.ts` 的导出函数

删除页面后，以下函数可能不再被引用，请 **grep 确认后再删**（有引用就留着）：

- `deleteProject`、`getProject`、`rescanProject`、`attachProject`（来自 ProjectDetailPage）
- `askProject` / `searchContext`（来自 PlaygroundPage）

**注意**：若 `searchContext`/`askProject` 只被 Playground 使用，删除后 `web/src/api/client.ts` 的
相关类型（`SearchResponse`/`AskResponse`）也可能成为死代码。**只删确定无引用的**，
并在报告里列出删了哪些、依据是什么（贴 grep 输出）。

### §E 测试清理

- `web/src/pages/PlaygroundPage.test.tsx` → **整个文件删除**；
- `web/src/pages/e2e.test.tsx` → 删掉"Playground 渲染带行号证据"用例，
  **保留**"真实服务可达（healthz 与 projects 的形状与类型声明一致）"用例
  （它验证类型声明与后端一致，价值独立于 Playground）。
  若该文件删到只剩一个用例，把文件名/描述改得贴合它现在测的东西（可选，别过度）。

## 验收标准（DoD）

- [ ] `cd web && npm run lint && npm test && npm run build` 全绿（**测试数会减少，这是预期的**，
      在报告里给出改动前后的 passed 数，说明减少的用例属于被删页面）。
- [ ] 死链检查：`grep -rn 'to="/projects\|to="/playground' web/src/` → **无输出**。
- [ ] 路由检查：`App.tsx` 里不再有 `playground`、`projects`、`projects/:id` 三条路由。
- [ ] 导航检查：`Layout.tsx` 的 NAV 只剩「账户 / API Key / 历史记录 / 接入指南」四项。
- [ ] 仪表盘仍显示项目列表（用户明确要求保留）。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest -o addopts="" -q`
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- 不删后端 `/api/projects*` 端点；
- 不删 `web/src/api/types.ts` 里与项目相关的类型（仍被 Dashboard/History/Connect 使用）；
- 不改 `ConnectPage.tsx` 对 `listProjects()` 的使用（TASK-080 负责）；
- 不为被删页面写"重定向占位"（用户要的是删除，不是保留入口）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：改动前后测试数对比、删除的函数清单及 grep 依据。

## 执行记录

### TASK-082 完成报告（2026-09-23，lane-c）

- **分支**：`feature/task-082-remove-pages_xwz0923`（从 `main @ d1a87ba` 创建，工位 `zace-lane-c`）
- **状态**：review（本地提交，**未 push**）

#### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `cd web && npm run lint` | clean（`eslint src --max-warnings 0`，无输出） |
| `cd web && npm test` | **26 passed \| 3 skipped (29)**（改动前：29 passed \| 4 skipped (33)） |
| `cd web && npm run build` | 通过（`tsc --noEmit` + `vite build`，44 modules，dist/assets/index-B3WOCTwb.js 240.11 kB） |
| `grep -rn 'to="/projects\|to="/playground' web/src/` | **无输出**（exit 1） |
| `grep -rn '/playground\|path: "projects\|ProjectsPage\|PlaygroundPage\|ProjectDetailPage' web/src/` | **无输出**（exit 1） |
| `uv run ruff check .` | All checks passed! |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过（core 纯库 / service 不上探） |
| `uv run pytest -o addopts="" -q` | **746 passed, 2 skipped**（与 main 基线一致，本卡只动 `web/`） |

#### 改动前后测试数对比（DoD 要求）

| | 测试文件 | passed | skipped | 合计 |
|---|---|---|---|---|
| 改动前 | 5 passed \| 2 skipped (7) | 29 | 4 | 33 |
| 改动后 | 4 passed \| 2 skipped (6) | 26 | 3 | 29 |

**减少的用例归属**（全部属于被删页面，无一处是"跳过/删断言"式假绿）：

- `PlaygroundPage.test.tsx` 整个文件删除 → **-3 passed**（提交后渲染 markdown+meta 面板、Deep 降级显著、证据块带行号）；
- `e2e.test.tsx` 删除 "真实检索结果能在 Playground 页面渲染出带行号的证据块" 用例 → **-1 skipped**（该用例原本默认 skip，因为要真实服务）；
- 保留：`e2e.test.tsx` 的 "真实服务可达（healthz 与 projects 的形状与类型声明一致）"（1 skipped），文件名与注释已改得贴合它现在测的东西（第 22-27 行）。

#### 6 处死链逐处改法（卡内 §B）

| 文件 | 原状 | 改后 |
|---|---|---|
| `DashboardPage.tsx:157` | `去 <Link to="/projects">项目管理</Link> 绑定本地目录` | "在编辑器里接入后让客户端同步一次即可出现（本地模式可用客户端 attach 本地目录）。" |
| `DashboardPage.tsx:175` | 项目名 `<Link to={\`/projects/${id}\`}>` | 纯文本 `{project.displayName \|\| project.projectId}`（`projectId` 列仍在，信息不丢） |
| `DashboardPage.tsx:173` | 项目表格 | **保留**（用户明确要求仪表盘保留项目列表） |
| `HistoryPage.tsx:118` | `在 <Link to="/projects">项目管理</Link> 绑定本地目录` | "让客户端同步一次（或在编辑器里接入后同步）即可产生。" |
| `HistoryPage.tsx:146` | 索引行项目名 `<Link to={\`/projects/${projectId}\`}>` | 纯文本 `{nameOf(projectId)}` |
| `HistoryPage.tsx:231` | `去 <Link to="/playground">Playground</Link> 提问后` | "从编辑器里问一次即可产生。" |

`HistoryPage.tsx` 因此不再使用 `Link`，已删掉 `import { Link } from "react-router-dom"`。

#### 其它改动

- `App.tsx`：删 `playground` / `projects` / `projects/:id` 三条路由与三个页面 import（旧路径跳转 `setup/register/tokens/usage/settings/login/*` 全部保留）。
- `Layout.tsx`：`NAV` 由 6 项变 4 项 —— 账户 / API Key / 历史记录 / 接入指南。
- 删除文件：`PlaygroundPage.tsx`、`PlaygroundPage.test.tsx`、`ProjectsPage.tsx`、`ProjectDetailPage.tsx`（`git rm`）。
- `console.e2e.test.tsx:101`：导航断言同步为 4 项（原断言含"项目"与"Playground"，不删会变红）。该文件在卡内交付物清单外，但属于"删导航/路由"(§A) 的直接后果。
- `web/README.md`：同步页面表（删 `/projects`、`/playground` 两行 + 目录树里"Markdown 是唯一渲染入口"的失效描述），并加一段 TASK-082 说明。

#### 删除的 `client.ts` 导出函数清单及 grep 依据（卡内 §D）

grep 命令：`cd web/src && grep -rn '<FN>' .`（已先 `git rm` 四个页面文件，故只剩 client.ts 自身声明）

| 函数 | 唯一引用者 | grep 结果 | 处置 |
|---|---|---|---|
| `getProject` | `ProjectDetailPage.tsx`（:6, :21） | 删除页面后仅剩声明 | **删** |
| `attachProject` | `ProjectsPage.tsx`（:8, :158） | 同上 | **删** |
| `rescanProject` | `ProjectsPage.tsx`、`ProjectDetailPage.tsx` | 同上 | **删** |
| `deleteProject` | `ProjectsPage.tsx`、`ProjectDetailPage.tsx` | 同上 | **删** |
| `ask` | `PlaygroundPage.tsx`（:17, :93） | 同上 | **删** |
| `search` | `PlaygroundPage.tsx`（:91）**+ `client.test.ts:53`**（复用为 501 占位错误路径的 fixture） | **仍有引用** | **保留**（并按 §D"有引用就留着"） |

连带清理：`SearchResponse` 仍被保留的 `search` 使用 → 保留；`AskResponse` 不再被 `client.ts` 使用 → 从 `client.ts` 的 `import type` 中移除，**但** `AskResponse` 本身以及 `export type { AskResponse }` 的重导出保留，因为 `components/MetaPanel.tsx` 仍引用它（§"不删与项目相关类型"的同理）。

#### 契约影响

无。未改 `docs/contracts/**`、`core/zace_core/{types,interfaces,hashing}.py`；`docs/design/**` 未改（Playground 与 `/projects` 页属 Module/07 设计内容，删除与设计文档不一致之处见"未决问题"）。后端端点全部保留，`service/` 未动。

#### 与设计的偏差

1. **Module/07 §2.2 的"Playground 是第一优先页面"被用户指令推翻**（用户 2026-09-13："Playground 删除，没用"；"项目 删除，没用"）。实现按用户口径执行；设计文档与 `INDEX.md` §3 **D-40**（"V1 = 管理面 + Playground"）未改（本卡禁止改设计文档），**需要编排者按 L3 流程更新**。
2. 项目管理能力（attach / rescan / delete 的 web 入口）不再可达，但对应后端端点仍在（§C 要求）。

#### 未决问题

1. **设计文档漂移（需 L3 裁决）**：`docs/design/Module/07-WebUI.md` 把 Playground 定为"第一优先页面"，`docs/design/INDEX.md` §3 D-40 也写 "V1 = 管理面 + Playground"。实现已按用户指令删除页面。建议编排者更新 Module/07 与 D-40，并在 `INDEX.md` §4 记录漂移。
2. **`components/Markdown.tsx` 与 `components/MetaPanel.tsx` 成为死代码**：删掉 `PlaygroundPage` 后，全仓 grep 显示二者**再无引用**（`grep -rn 'MetaPanel' web/src/` 只剩其自身定义；`grep -rn 'components/Markdown' web/src/` 无结果）。它们不在本卡交付物清单内，且其去留取决于第 1 条的裁决（若判定 web 不再渲染 ContextPack，则二者与 `api/types.ts` 的 `SearchResponse`/`AskResponse`/`PackMeta` 可一并清理；若将来恢复检索调试页则应保留）。**本次保留，未删**。
3. **`client.ts` 的 `search()` 目前只被测试使用**：`PlaygroundPage` 删除后它没有产品调用方，仅 `client.test.ts:53` 借用它验证 501 错误路径。按 §D 留在原处（避免为一个 fixture 删契约入口），但请编排者决定是否改由 `getHealth()` 承担该断言。
4. **`web/HANDOFF.md`（TASK-070 交接文档，不在本卡所有权内）仍是旧口径**：第 8 行说 UI 链路含 Playground、第 70 行把"TASK-074 Playground 可分享 / 历史回放"列为 P2。需编排者裁决 TASK-074 是否作废以及 HANDOFF 是否更新。

#### 建议复核点

1. `DashboardPage.tsx` 项目表格（第 154-195 行）：确认"保留项目列表"且项目名已为纯文本、`projectId` 列仍在；
2. `App.tsx` 是否只少了三条路由（旧路径跳转表未被误伤）；
3. `web/src/api/client.ts` 删除的 6 个函数：对照本报告 grep 表确认没有"有引用却删掉"；
4. `npm test` 的 26 passed 是否与"-3 passed/-1 skipped 均属被删页面"的解释吻合。
