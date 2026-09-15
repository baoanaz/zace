# TASK-083：空态 / 加载态 / 错误态统一（让"0 条数据"不再像坏了）

> 状态：review ｜ 阶段：Phase 4（M4）｜ **硬依赖：TASK-082（已合并，本卡从 main 创建）** ｜ soft 依赖：无
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

### 2026-09-13 ｜ 分支 `feature/task-083-empty-states_xwz0913`（lane-f，从 `main` = 83b221a 创建）

**串行安排**：本卡与 TASK-082 **已串行**——082 已合并进 `main`（`589f018`，见任务板第 106 行），
故本卡直接从 `main` 创建分支，不需要再从 082 的分支串联。

**改了哪些空态位置（5 处，全部换成 `EmptyState`，每处都写“怎样才会有数据”）**：

| # | 文件 : 位置 | 文案（title / hint） |
|---|---|---|
| 1 | `HistoryPage.tsx` 索引记录页签 | “还没有索引记录” / “在编辑器里接入 Agent 后让它同步一次（本地模式也可用客户端 attach 目录），这里就会出现每次索引的结果。” + `Link → /connect` |
| 2 | `HistoryPage.tsx` 使用记录页签 | “这段时间还没有查询记录” / “在编辑器里接入 Agent 后向它提问，每次查询都会记录在这里（默认看近 30 天）。” + `Link → /connect` |
| 3 | `DashboardPage.tsx` 最近索引记录面板 | “还没有索引记录” / 同上 + `Link → /connect` |
| 4 | `DashboardPage.tsx` 项目面板 | “还没有项目” / “项目在你第一次同步时自动创建：接入 Agent 并让它上传/索引一个仓库，项目就会出现在这里。” + `Link → /connect` |
| 5 | `ApiKeysPage.tsx` Key 列表 | “还没有 API Key” / “用上方表单创建一把，再把完整 Key 配置到编辑器 / CLI 客户端里；只有创建那一刻能看到完整值。” |

引导一律指向 `/connect`（接入指南）；**未引用** `/projects` 或 `/playground`（已随 TASK-082 删除）。

**新增组件**：`ui.tsx` 的 `EmptyState({title, hint?, action?})`（Tailwind / slate / `text-sm`，与现有组件一致；无新依赖）。

**额外修复（都是“把后端故障伪装成空数据”的反例，属本卡 §C 范围）**：

1. `HistoryPage` 逐项目读取——旧代码 `catch { return [] }` 会把“某个项目读历史失败”渲染成
   “还没有索引记录”。现改为：记录失败项目，**在空数据时显示错误而不是空态**，在有数据时
   显示“部分项目的索引记录读取失败：<项目名>”警告条并声明下表只含读取成功的项目。
2. `DashboardPage.sumDisk`——旧实现 `index.diskBytes ?? 0` + `formatBytes(0) → “—”`，
   把“后端未提供 diskBytes”与“占用 0”推得同一个“—”且提示写着“索引数据磁盘占用”，有误导。
   现直接传 `index.diskBytes`，未提供时 hint 显示“后端未提供”；`formatBytes` 入参放宽为可空。
3. `ErrorBlock` 的 `String(error)` 兜底——对 `null` 会渲染成字面量 `null`，对无 `message` 的
   对象会渲染成 `[object Object]`（卡内 §C 明令禁止）。新增 `describeError()`：Error → message、
   字符串直通、有 message 的对象取 message、其余 JSON 序列化、最后兜底文案；并避免
   `hint === message` 时重复输出两遍。

**验收命令与结果**：

```
$ cd web && npm run lint   → 无输出（eslint src --max-warnings 0 通过）
$ cd web && npm test       → Test Files 5 passed | 2 skipped (7)；Tests 34 passed | 3 skipped (37)
                             （新增 src/components/ui.test.tsx：7 passed）
$ cd web && npm run build  → tsc --noEmit 通过；vite build ✓ built in 938ms
$ uv run ruff check .                                  → All checks passed!
$ uv run python scripts/check_dependency_direction.py  → 依赖方向检查通过
$ uv run pytest -o addopts="" -q                       → 782 passed, 2 skipped, 1 warning in 21.85s
```

**行为验收（真实 HTTP，非 mock）**：

| 场景 | 搭法 | 实际看到 |
|---|---|---|
| 后端停掉（反例，核心 DoD） | 页面请求指向未监听端口 | 三页都显示 `ErrorBlock`（`连不上 zace-service。请先启动服务…` + `network_error`）；**均未**出现空态 |
| 后端在、数据为空（正例） | `zace-service local --repo /tmp/zace-empty-repo`（真实服务，1 项目、0 查询） | `/api/usage/summary` → 200 且 `total=0`；页面显示“这段时间还没有查询记录”+ hint + “去接入指南”；无错误块 |
| 单项目读取失败（部分降级） | 本地桩服务：`/api/projects` 200、`/api/projects/*/index-runs` 500 | 显示“索引记录读取失败：坏掉的项目”+“**不代表还没有数据**”+ `internal_error`；**未**出现“还没有索引记录” |

反例实测的关键输出（后端停掉时，三页均为）：

```
HISTORY_HAS_ERROR: true      HISTORY_HAS_EMPTY_STATE: false
DASH_HAS_ERROR:    true      DASH_HAS_EMPTY_STATE:    false
KEYS_HAS_ERROR:    true      KEYS_HAS_EMPTY_STATE:    false
```

**反例验收｜grep 检查过的“静默吞错”位置清单**（`grep -rn "catch" web/src --include=*.tsx --include=*.ts`，逐条判读）：

| 位置 | 是否导致“错误显示成空态” | 结论 |
|---|---|---|
| `HistoryPage.tsx:57` | **是（本次已修）** | 原 `catch { return [] }` → 现记录失败并显示错误（见上） |
| `DashboardPage.tsx:33`、`ApiKeysPage.tsx:32/50/65`、`LoginPage.tsx:47/71` | 否 | `catch (err) { setError(err) }` → 页面渲染 `ErrorBlock` |
| `ConnectPage.tsx:37` | 否 | 仅取 `authRequired` 展示开关，失败置 `null` → 显示占位符；页面不渲染任何数据空态 |
| `Layout.tsx:27` | 否 | 登出失败仍清本地态并跳登录（注释已说明），不涉及空态 |
| `App.tsx:55/66` | 否 | 首屏门禁：401 → 匿名态由设计；其余错误落到匿名态后登录页会给出可操作提示 |
| `api/client.ts:134` | 否 | `fetch` 网络失败 → `ApiError("network_error", SERVICE_DOWN_MESSAGE)`，**恰恰是错误态的来源** |
| `api/client.ts:155` | 否 | `safeJson` 非 JSON 响应 → `null`；若 HTTP 非 2xx 随后抛 `ApiError(http_*)` |
| `ui.tsx:63` | 否 | `CopyButton` 剪贴板不可用：有状态提示，非数据空态 |
| `ui.tsx:98` | 否 | 新增 `describeError` 的 `JSON.stringify` 兜底（循环引用），随后返回可读文案 |

另：`grep -rn "暂无数据\|暂无" web/src` 仅命中 `ui.tsx` 的组件注释里“不许写暂无数据”一句，无实际文案。

**契约影响**：无（未触 `docs/contracts/**`、`core/zace_core/{types,interfaces}.py`；纯前端展示层）。

**与设计偏差**：无。

**与 DoD 字面的偏差（如实记录）**：DoD 写“在**空数据**的云端服务上打开页面”。本次空数据正例用的是
`zace-service local`（本地单用户模式）真实服务（`/api/usage/summary`、`/api/account/overview` 均 200 且为空），
未跑“云端账户 + session 登录”那条链路——本卡关心的“0 条 vs 坏了”两种形态已分别用真实 HTTP
证伪/证实，但云端鉴权形态未覆盖，建议编排者补一次。

**未决问题**：

1. **真实浏览器截图未取到**（DoD 原文写“截图或输出”，本卡交付的是输出）。本机无浏览器且
   无 sudo：Playwright Chromium 可下载，但缺 `libnss3`/`libnspr4`/`libasound.so.2`，
   `sudo` 需密码 → 无法启动真实浏览器。改用“**无 mock 的真实 fetch**”harness（jsdom 里打真实
   HTTP）覆盖了三个场景，证据强度接近但**不等于**真实浏览器渲染；建议编排者在有浏览器的机器上
   补一次视觉确认。
2. 本卡只改了本卡所有权内的文件。**同类问题仍在卡外文件中**（未改，供后续卡参考）：
   `Layout.tsx:27` 的静默登出、`App.tsx:66` 的兜底匿名态、`ConnectPage.tsx:37` 的 `null` 占位。
3. `DashboardPage` 项目表里 `project.sync?.filesIndexed ?? "—"` 一类“未测量显示 —”的口径未动
   （属 TASK-072 图表化范围，本卡明确不做）。

