# TASK-082：删除 Playground 与项目管理页（含导航、路由、死链、测试清理）

> 状态：pending ｜ 阶段：Phase 4（M4）｜ 硬依赖：无 ｜ soft 依赖：TASK-083（空态组件）
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

（实施 AI 在此填写。）
