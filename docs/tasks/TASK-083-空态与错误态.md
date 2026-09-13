# TASK-083：空态 / 加载态 / 错误态统一（让"0 条数据"不再像坏了）

> 状态：pending ｜ 阶段：Phase 4（M4）｜ **硬依赖：TASK-082（必须先合并）** ｜ soft 依赖：无
> 建议分支：`feature/task-083-empty-states_<你的缩写><MMDD>`（**从 TASK-082 的分支串联创建**）
> 交付物所有权：
> - `web/src/components/ui.tsx`（新增 `EmptyState`，可选调整 `ErrorBlock`/`LoadingBlock`）
> - `web/src/pages/HistoryPage.tsx`（替换空态/错误态）
> - `web/src/pages/DashboardPage.tsx`（替换空态/错误态）
> - `web/src/pages/ApiKeysPage.tsx`（空态，若有）
> - `web/src/components/ui.test.tsx`（**新建**；若你判断需要单测）
>
> 清单外文件不得改。

## ⚠️ 硬依赖 TASK-082（编排者裁定：本卡不能与它并行）

TASK-082 会**删除** `ProjectsPage.tsx` / `ProjectDetailPage.tsx` / `PlaygroundPage.*`，
并清理 `HistoryPage.tsx`、`DashboardPage.tsx` 里的死链。

本卡要改的正是 `HistoryPage.tsx` 与 `DashboardPage.tsx` 的**空态文案**——
两卡同改两个文件**必然冲突**。因此：

- **必须先合并 TASK-082，本卡再从它的分支串联创建**；
- 串联后这两页已经删掉死链，你的空态文案里**不要再引用** `/projects` 或 `/playground`
  （那两个路由已不存在）——空态要引导用户去**接入指南**（`/connect`）或在编辑器里用 Agent 提问。

## 目标

用户诉求（2026-09-13 确认）：

> 先给 UI 加空态/错误提示

背景：后端统计缺口（TASK-084/085）修复前，历史记录页与仪表盘的很多数字是 `0` 或 `—`。
现状的问题是**"0 条"与"坏了"看起来一样**，用户无法判断是自己还没用、还是后端没记上。

本卡交付：**能让用户一眼分辨三种状态**——

| 状态 | 用户应该看到 |
|---|---|
| 还没产生数据 | "还没有…"，并**说明怎样才会产生**（可操作的一句话） |
| 正在加载 | 加载指示（现有 `LoadingBlock`） |
| 请求失败 | 错误信息 + 原因 + 可操作提示（现有 `ErrorBlock`，检查是否够用） |

## 现状（实测）

- `web/src/components/ui.tsx` 已有 `LoadingBlock`、`ErrorBlock`、`Card`、`Badge`、`KeyValue`、`CopyButton`；
- `HistoryPage.tsx:115-118` 与 `229-231` 有手写的空态文案（且含死链，TASK-082 会改）；
- `DashboardPage.tsx:122`、`156-158` 有手写的空态文案；
- 空态样式不统一（有的是 `<p className="text-sm text-slate-500">`，有的带链接）。

## 本卡必须做到的

### §A 新增 `EmptyState` 组件（`ui.tsx`）

- 接受 `title`、可选 `hint`（可操作说明，如"在编辑器里接入 Agent 后同步一次就会产生记录"）、
  可选 `action`（ReactNode，如按钮）；
- 与现有组件风格一致（Tailwind、slate 色系、`text-sm`）；
- **不引入新的依赖**。

### §B 替换各处手写空态

- HistoryPage 的索引记录空态、查询记录空态；
- DashboardPage 的最近索引记录空态、项目列表空态；
- ApiKeysPage 的 Key 列表空态（若无则跳过）。

**文案要求**：每处空态都要说明"怎样才会有数据"。例如：

- 索引记录空态 → "还没有索引记录。在编辑器里接入 Agent 并让它同步一次即可产生。"
- 查询记录空态 → "还没有查询记录。接入 Agent 后向它提问就会记录在这里。"
- API Key 空态 → "还没有 API Key。点右上角创建后，配置到 Agent 里即可。"

**不得**写"暂无数据"这类无信息量的文案。

### §C 错误态检查

- 确认 `ErrorBlock` 能在后端返回 CF-05 错误信封时给出**可读原因**（而不是 `[object Object]`）；
- 若 `ErrorBlock` 对网络错误（服务不可达）的提示不够可操作，补一句"确认服务是否已启动"。
- **不要**吞掉错误（不许 catch 后显示空态——那会让"后端坏了"看起来像"还没数据"）。

## 验收标准（DoD）

- [ ] `cd web && npm run lint && npm test && npm run build` 全绿。
- [ ] 新增 `ui.test.tsx`（若写了）：至少覆盖 `EmptyState` 渲染 title/hint/action 三个分支。
- [ ] 行为验收（贴真实输出）：在**空数据**的云端服务上打开页面，确认：
  - [ ] 每处空态都有"怎样才会产生数据"的说明；
  - [ ] 把后端停掉后刷新，页面显示的是**错误**而不是空态（这条必须实测，是本卡的核心价值）。
- [ ] 反例验收：**Grep 确认**没有 `catch {}` 式静默吞错导致空态（列出检查过的位置）。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest -o addopts="" -q`
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- 不做图表化（那是 TASK-072 的范围，需另开卡）；
- 不做 i18n；
- 不改后端任何文件；
- 不改 `ConnectPage.tsx` / `connect-info.ts`（TASK-080 的领地）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：改了哪些空态位置、错误态实测截图或输出、
以及是否与 TASK-082 串行（哪种安排）。

## 执行记录

（实施 AI 在此填写。）
