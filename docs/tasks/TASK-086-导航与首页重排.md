# TASK-086：导航与首页重排 + 全局背景纹理

> 状态：pending ｜ 阶段：Phase 4（M4）｜ 硬依赖：无（TASK-082/083 已合并）｜ soft 依赖：无
> 建议分支：`feature/task-086-nav-home-bg_<你的缩写><MMDD>`
> 交付物所有权：
> - `web/src/app/Layout.tsx`（导航顺序、背景容器）
> - `web/src/pages/DashboardPage.tsx`（标题改名、删「最近索引记录」面板）
> - `web/src/index.css`（全局背景纹理）
> - `web/tailwind.config.js`（如需新增背景色 token）
> - `web/src/app/Layout.test.tsx`（**新建**，可选但推荐）
>
> 清单外文件不得改。**特别提醒：不要改 `HistoryPage.tsx`（其上「索引记录」页签已覆盖此职能）、
> 不要改 `ConnectPage.tsx` / `connect-info.ts`（TASK-080 的成果，本卡只是把它移到导航第二位）。**

## 目标

用户 2026-09-14 提出 4 条 UI 调整，一次做完：

| # | 用户原话 | 要做的事 |
|---|---|---|
| 1 | 「接入指南移动到账户右边，作为第二个页面」 | 导航顺序：控制台 → **接入指南** → API Key → 历史记录 |
| 2 | 「账户这个页面，改名成控制台」 | 导航 label 与页面 `<h1>` 都改为「控制台」 |
| 3 | 「控制台，删除最近索引记录吧有专门的历史记录去看就行，项目保留吧」 | 删 Dashboard 的「最近索引记录」面板；**保留**「项目」面板 |
| 4 | 「整体的背景能不能不要全白的，稍微来点背景吧」 | 加浅蓝灰底 + 淡网格纹理（参考图见下） |

## §1 导航顺序（Layout.tsx）

当前 `NAV`：

```ts
const NAV = [
  { to: "/", label: "账户", end: true },
  { to: "/keys", label: "API Key", end: false },
  { to: "/history", label: "历史记录", end: false },
  { to: "/connect", label: "接入指南", end: false },
];
```

改为（顺序即用户要求）：

```ts
const NAV = [
  { to: "/", label: "控制台", end: true },
  { to: "/connect", label: "接入指南", end: false },
  { to: "/keys", label: "API Key", end: false },
  { to: "/history", label: "历史记录", end: false },
];
```

**注意**：路由路径 `/` 与 `/connect` **不变**（只改顺序与 label），否则会破坏既有链接与测试。

## §2 「账户」→「控制台」（DashboardPage.tsx）

- 页面 `<h1>`「账户」→「控制台」；
- **保留**「账户资料」面板的标题不变（那是面板名，不是页面名——用户说的是页面改名）；
- **检查是否有其它面向用户的「账户」字样**：`grep -rn "账户" web/src/` 逐个判读，
  导航 label、页面标题要改；`账户名已被占用` 这类**错误文案不要动**（语义不同）。

## §3 删除「最近索引记录」面板（DashboardPage.tsx）

- 删除 `<Panel title="最近索引记录">` 整块（约 122 行起）；**「项目」面板保留**（用户明确要求）；
- 该面板删除后，`index.recent` 若**不再被任何地方使用**，把不再需要的解构/类型引用一并清理
  （先 grep 确认，别留死代码）；
- `查看全部历史` 链接随面板一起删除（它在那个面板内）；历史页本身仍从导航可达。
- **不要**动「索引（近 N 天）」面板（那是成功/失败/平均耗时统计，用户没要求删）。

## §4 全局背景（index.css / Layout.tsx）

参考图特征（用户给的截图，`/mnt/c/.../f3ada18ba0601abb89160a94bbff62fb.png`）：

- **底色**：浅蓝灰（约 `#eef2f7` / `slate-100` 偏蓝），不是纯白；
- **纹理**：细网格线（约 24px 间距），线色比底色略深一点点（低对比、不抢内容）；
- 白色卡片浮在网格上，卡片自身的白底与边框**保持现状**（有对比才有层次）。

实现要求：

- 网格用 **CSS 渐变**（`background-image: linear-gradient(...)` 两条 + `background-size`）实现，
  **不引入图片、不引入新依赖**；
- 背景定义在 `index.css` 的 `body`（或 `Layout` 的容器类）上，**深色/移动端不破版**；
- 网格线必须**足够淡**：如果在小屏或高 DPI 下噪点明显，降低不透明度；
- header 的 `bg-white` 保留（顶部栏应实心，否则内容滚动时会透过文字）。

## 验收标准（DoD）

- [ ] `cd web && npm run lint && npm test && npm run build` 全绿。
- [ ] `Layout.test.tsx`（若写了）断言导航顺序为
      `["控制台", "接入指南", "API Key", "历史记录"]`，且 `to` 值未变。
- [ ] 行为验收（贴真实输出或截图路径）：
  - [ ] 导航顺序符合 §1；
  - [ ] 页面标题显示「控制台」；
  - [ ] 控制台**无**「最近索引记录」面板，**有**「项目」面板；
  - [ ] 背景为浅蓝灰 + 网格（截图）。
- [ ] `grep -rn "最近索引记录" web/src/` → 无结果（除历史页自身的「索引记录」页签，那是不同文案）。
- [ ] 路由回归：`/`、`/connect`、`/keys`、`/history` 四条路径仍可达（`App.tsx` 不改）。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、
      `uv run pytest -o addopts="" -q`
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- 不删「项目」面板（用户明确要求保留）；
- 不改「索引（近 N 天）」与「使用次数」两个统计面板；
- 不改路由路径（只改顺序与 label）；
- 不做深色模式（另开卡）；
- 不引入 UI 组件库、不引入图标包、不引入图片资源。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：导航顺序、背景实现方式（贴 CSS 片段）、
以及删除面板后清理掉的死代码清单。

## 执行记录

（实施 AI 在此填写。）
