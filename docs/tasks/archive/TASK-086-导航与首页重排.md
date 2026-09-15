# TASK-086：导航与首页重排 + 全局背景纹理

> 状态：review ｜ 阶段：Phase 4（M4）｜ 硬依赖：无（TASK-082/083 已合并）｜ soft 依赖：无
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

- [x] `cd web && npm run lint && npm test && npm run build` 全绿。
- [x] `Layout.test.tsx`（若写了）断言导航顺序为
      `["控制台", "接入指南", "API Key", "历史记录"]`，且 `to` 值未变。
- [x] 行为验收（贴真实输出或截图路径）：
  - [x] 导航顺序符合 §1；
  - [x] 页面标题显示「控制台」；
  - [x] 控制台**无**「最近索引记录」面板，**有**「项目」面板；
  - [x] 背景为浅蓝灰 + 网格（截图）。
- [x] `grep -rn "最近索引记录" web/src/` → 无结果（除历史页自身的「索引记录」页签，那是不同文案）。
- [x] 路由回归：`/`、`/connect`、`/keys`、`/history` 四条路径仍可达（`App.tsx` 不改）。
- [x] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、
      `uv run pytest -o addopts="" -q`
- [x] 任务卡"执行记录"已回填；任务板状态改为 `review`。

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

**2026-09-14 ｜ 分支 `feature/task-086-nav-home-bg_xwz0913`（泳道 lane-h）**

### 开工前的一个偏差（已自解，记录备查）

lane-h 工作区的 HEAD 停在 `460dc28`（detached），是本波之前的 `create` 遗留。
它是 `85ff1aa` 的**祖先**——即本卡需要的文件（`TASK-086-*.md`、`web/src/pages/DashboardPage.tsx`、
`HistoryPage.tsx`、`ApiKeysPage.tsx`）在该提交上**尚不存在**（web 控制台来自 task-070/080~085，未进这个 worktree）。
处置：按 `docs/plan/multi-ai-worktrees.md` §3.1 从 `main`（= `85ff1aa`）开分支，与本卡第 3 步指令一致，无副作用。

### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `cd web && npm run lint` | clean（`eslint src --max-warnings 0`，无输出） |
| `cd web && npm test` | **38 passed \| 3 skipped**（8 files；3 个 skipped 是 `ZACE_E2E=1` 才跑的真实服务用例） |
| `cd web && npm run build` | ✅ `tsc --noEmit` + `vite build`，44 modules，`dist/assets/index-*.css` 14.07 kB |
| `uv run ruff check .` | All checks passed! |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过（core 纯库 / service 不上探） |
| `uv run pytest -o addopts="" -q` | **804 passed, 2 skipped** in 27.52s |
| `grep -rn "最近索引记录" web/src/` | **无结果** ✅ |

### 四条要求逐条

**§1 导航顺序**（`Layout.tsx`）：数组字面量顺序改为 `控制台(/) → 接入指南(/connect) → API Key(/keys) → 历史记录(/history)`；
`to` 与 `end` 一个都没动（`App.tsx` 零改动）。新增 `Layout.test.tsx` 断言顺序 + `href` 数组 + `/connect` 下 `/` 不高亮（`end` 生效）。

**§2 页面标题**：`DashboardPage.tsx` 的 `<h1>` 「账户」→「控制台」。
`grep -rn "账户" web/src/` 逐个判读结果：**改 1 处**（页面 `<h1>`）+ 导航 label 1 处；
**不改**：`账户资料`（面板名）、`<Row label="账户">`（资料字段名）、`云端账户`/`行单用户`（值文案）、
`account.name`、`账户名已被占用`（错误文案）、`LoginPage` 的 `账户` 输入框 label、
`App.test.tsx` / `console.e2e.test.tsx` 里作为**测试描述/输入框定位**出现的「账户」（非面向用户文案）。

**§3 删面板**：删掉 `<Panel title="最近索引记录">` 整块（含其内的 `查看全部历史` 链接与运行记录列表）。
**保留**「项目」面板、「索引（近 N 天）」、「使用次数」两个统计面板。

**§4 全局背景**（`index.css` + `tailwind.config.js`）：CSS 渐变实现，无图片/new dependency。
底色 `#eef2f7`（浅蓝灰），网格线 `rgba(100,116,139,0.16)`（低对比），间距 `24px`：

```css
body {
  background-color: theme("colors.grid.base"); /* #eef2f7 */
  background-image:
    linear-gradient(to right,  theme("colors.grid.line") 1px, transparent 1px),
    linear-gradient(to bottom, theme("colors.grid.line") 1px, transparent 1px);
  background-size: 24px 24px;
}
```

定义在 `body` 上（**全局**：登录页/加载态也在这个底上），因此不必改 `App.tsx` 的加载分支；
header 保持 `bg-white` 实心（新增的 `Layout.test.tsx` 钉住这条）。
构建产物核对：
`body{...;background-color:#eef2f7;background-image:linear-gradient(to right,rgba(100,116,139,.16) 1px,transparent 1px),linear-gradient(to bottom,rgba(100,116,139,.16) 1px,transparent 1px);background-size:24px 24px}`

### 行为验收（真实浏览器，非 mock 断言）

用一次性 mock API（`/tmp`，未进仓库）+ `vite` dev server + Windows Chrome headless 截了图。实测：

- 导航顺序 `控制台 | 接入指南 | API Key | 历史记录`，高亮随路径移动；
- `/` 标题「控制台」、`/connect`「接入指南」、`/keys`「API Key」、`/history`「历史记录」——**四条路径均可达**，
  `--dump-dom` 确认各页 `aria-current="page"` 落在对应链接上；
- 控制台**无**「最近索引记录」面板，**有**「项目」面板（表格里能看到 mock 的两条项目）；
- 背景为浅蓝灰 + 可辨网格，白色卡片保持原有 `bg-white` + 边框。

### 删除面板后清理掉的死代码

**零**。grep 依据（删面板后逐项确认仍被其他面板使用）：

| 符号 | 原用途 | 现用途 |
|---|---|---|
| `EmptyState` | 面板空态 | 「项目」面板空态（`DashboardPage.tsx:132`） |
| `Link` | 面板内两个链接 | 「项目」面板空态的 `去接入指南`（:136） |
| `index.recent` | 面板列表 | Dashboard 已无引用（`UsageSummary.recent` 是另一个字段，仅在 HistoryPage） |
| `formatDuration` / `formatTime` / `formatBytes` | 共享格式化 | 索引面板仍在用 |

`index.recent` 是 `AccountOverview.index: IndexStats` 的字段（后端 `/api/account/overview` 真实返回），
不属本卡所有（`api/client.ts`），若删声明会与后端形状脱节——**保留**，不留死代码。

### 伴生修改（说明理由，非顺手改）

卡内 DoD 要求断言新标题/新 nav 顺序，两类失败用例必须跟着改，否则 `npm test` 不可能绿：

1. `web/src/app/App.test.tsx`：4 处 `heading{name:"账户"}` → `控制台`；
   原「索引记录里 done 显示为成功」用例所测的 UI 已删，**重写为**「不再有索引记录面板，但项目面板保留」（否则该用例会被静默删除——那是掩盖而非覆盖）。
2. `web/src/pages/console.e2e.test.tsx`（`skipIf` 门控）：标题断言与 nav 断言按新事实更新，nav 改为**顺序**断言。

### 一处刻意的布局调整（与卡内「约 122 行起」描述略有偏差）

「最近索引记录」面板不是独立一块，它与「使用次数」共处一个 `grid-cols-1 lg:grid-cols-2`。
只删面板会留下**半宽的「使用次数」+ 右半边真空**。因此同时**去掉这层 grid 包裹**，让「使用次数」恢复整宽。
面板本身的内容与口径零改动。

### 契约影响 / 偏差 / 未决

- **契约影响**：无（未碰 `docs/contracts/**`、`zace_core/types.py`、`interfaces.py`；路由表未动）。
- **与设计偏差**：无。删面板是用户直接指令（历史页「索引记录」页签已覆盖该职能）。
- **未决问题**：无。
- **建议复核点**：① §4 网格在更深底色下的观感（现为 `rgba(100,116,139,.16)` @24px，参考图未在磁盘找到，凭卡内描述取参考值）；
  ② 「使用次数」整宽是否合意；③ `App.test.tsx` 那两处**重写**用例的语义是否被认可。

