# TASK-098：WebUI 视觉改版（复古博物画风格 + 侧边栏布局）

> 状态：review ｜ 阶段：Phase 4（M4）｜ 硬依赖：无 ｜ soft 依赖：TASK-094（同改 Dashboard/History 两页，建议串行）
> 建议分支：`feature/task-098-retro-theme_<你的缩写><MMDD>`
> 交付物所有权：
> - `web/src/index.css`（全局主题：底色 / 纹理 / 字体）
> - `web/tailwind.config.js`（颜色 token 扩展）
> - `web/src/app/Layout.tsx`（**布局重构**：顶栏 → 侧边栏）
> - `web/src/app/Layout.test.tsx`（**必须同步更新**，见 §E）
> - `web/src/pages/LoginPage.tsx`（登录页改版）
> - `web/src/components/ui.tsx`（Card / Badge / EmptyState 等的配色微调）
>
> 清单外文件不得改（尤其 `web/src/api/**`、`web/src/pages/{Dashboard,History,ApiKeys,Connect,Settings}Page.tsx` 的**逻辑**——
> 只允许因布局变化而必需的 className 调整，**不得改行为**）。

## 背景（用户 2026-09-14 提供三张参考图）

用户要求把 WebUI 改成**复古博物画 / 老纸风格**（参考 **Claude Fable 5** 的视觉语言）。

**三张参考图的本地路径**（实施 AI 可直接读图理解风格）：

```
/mnt/d/Wechat/xwechat_files/wxid_gs0k4bk0lxz322_5db1/temp/RWTemp/2026-09/f1ce0c6a259e191012ae32d51b949415/a1651c654aaba7ed656d93e045dbbac5.png   ← Claude Fable 5（老纸 + 博物插画 + 衬线字）
/mnt/d/Wechat/xwechat_files/wxid_gs0k4bk0lxz322_5db1/temp/RWTemp/2026-09/f1ce0c6a259e191012ae32d51b949415/835856744e6c1a468535905c47a23d5e.png   ← Voyage 登录页（左装饰 + 右白卡片）
/mnt/d/Wechat/xwechat_files/wxid_gs0k4bk0lxz322_5db1/temp/RWTemp/2026-09/f1ce0c6a259e191012ae32d51b949415/a84a80416190ac62de1ddb6bc030fd5b.png   ← Voyage 控制台（左侧边栏 + 右侧内容）
```

> **注**：这三张图在 Windows 微信临时目录（`/mnt/d/...`）。若路径已失效（临时文件会被清理），
> 按下方描述与用户原话理解即可——**不要因为看不到图而停工**，存在偏差就在报告里说明。

| 参考 | 特征 | 来源 |
|---|---|---|
| **Claude Fable 5 宣传图** | 米黄老纸底 + **衬线字体** + 标本插画 + 深墨色文字 | `a1651c65...png` |
| **Voyage 登录页** | 左大空白 + 细线几何图案 + **右侧白色浮卡片** | `835856744...png` |
| **Voyage 控制台** | **左侧导航栏** + 右侧内容区 | `a84a8041...png` |

**用户原话**：

> UI 呈现风格改一下，登入页面这样，背景是一个随机的色卡，采用 #f3e4c7 这种偏黄色的牛皮纸风格吧？
> 类似古老旧画这样，如果你能制作纹理或者别的那就更好。右边是白色的登入卡片。
>
> 然后内部的化，排版改成左边这样的选择，也就是我们的工作台、API key、接入指南这些。
> 右边就是具体内容展现，颜色风格也可以按照古老旧画，这种风格来。

## 目标

1. **视觉主题**：米黄老纸底 + 衬线字体 + 深墨色文字（复古博物画气质）；
2. **登录页**：左装饰 + 右白卡片（参考 Voyage 布局）；
3. **主应用**：顶栏导航 → **左侧边栏导航** + 右侧内容区。

## §A 设计 token（先定，再改页面）

### §A-1 颜色（`tailwind.config.js` 扩展，**不要写死在组件里**）

| token | 值 | 用途 |
|---|---|---|
| `paper.base` | `#f3e4c7` | 主背景（用户指定） |
| `paper.raised` | `#f7ecd8` | 次级背景（侧边栏 / hover） |
| `paper.card` | `#ffffff` | 卡片（保持纯白，与老纸底形成层次） |
| `ink.primary` | `#2a2419` | 主文字（深墨，非纯黑——纯黑在米黄底上太硬） |
| `ink.muted` | `#6b5d48` | 次级文字 |
| `ink.line` | `#d9c9a8` | 边框线 |
| `accent.seal` | `#8c3a2b` | 强调色（朱砂印泥色，用于 active 态 / 按钮） |

**要求**：
- **全部走 token**，组件里不出现裸色值（现有 `grid.base` / `grid.line` 的做法可参考）；
- 保留 `grid` 这个既有 token 名或合理迁移（**改它要同步改 `index.css` 与 `Layout.test.tsx`**）。

### §A-2 字体

| 用途 | 建议 |
|---|---|
| **标题 / 品牌字** | 衬线：`ui-serif, Georgia, "Songti SC", "SimSun", serif` |
| 正文 | 保留现有 sans（中文可读性优先） |
| 代码 | 保留现有 mono |

> **不要引入 Web Font 依赖**（不下载字体文件）——用系统字体栈，离线可用。
> 复古感主要靠**颜色 + 衬线标题 + 间距**营造，而不是靠字体文件。

### §A-3 背景纹理（**用户拍板：斑驳旧纸感**）

用户说“如果你能制作纹理或者别的那就更好”，并选定**斑驳旧纸感**：

```
底色 #f3e4c7 + 几十处极淡径向渐变叠加
无规律感，像旧纸的褪色痕迹；纯 CSS 实现，无图片资源
```

**实现要求**：

- 用**多处 `radial-gradient` 叠加**（建议 8-16 处，尺寸/位置错开），不是单一渐变；
- 每个斑点的透明度**极低**（建议 `rgba(0,0,0,0.015)` 量级），叠加后仍不能影响文字可读；
- **斑点尺寸要大**（如 300-800px），避免看起来像噪点；
- `background-attachment: fixed`（滚动时纹理不跟着跑，更像“一张纸”）；
- **参数集中到一个 CSS 变量/注释块**，便于后续调参。

**可选增强（你判断，报告说明）**：在斑点之上再叠一层**极淡的斜线**做纸张纤维感
（`repeating-linear-gradient`，透明度 <0.02）。若效果不好就只用斑点。

> **注意**：斑驳纹理在**低端显示器/高 DPI 屏**上可能表现不同，注意不要出现色带
> （banding）——用足够大的渐变尺寸可以避免。

## §B 登录页改版

**布局**（参考 Voyage 登录页）：

```
┌────────────────────────────────┬──────────────────┐
│                                │                  │
│   装饰区（老纸底 + 纹理）        │  ┌────────────┐  │
│                                │  │  zace      │  │  ← 白卡片
│   · 品牌字（衬线、大字）         │  │  登录/注册  │  │
│   · 细线几何图案（可选）         │  │  [表单]    │  │
│   · 一句 tagline               │  └────────────┘  │
│                                │                  │
└────────────────────────────────┴──────────────────┘
```

**要求**：
- 保持**全部现有功能**：三种模式（login / register / bootstrap）由 `GET /api/meta` 决定，
  三个表单字段、错误展示、忙态禁用、注册开关提示——**一个都不能丢**；
- 品牌区用衬线字体；tagline 可用现有的 "Workspace Context Engine"；
- 卡片保持 `bg-white` 纯白（用户明确"右边是白色的登入卡片"）；
- **窄屏**（<768px）时装饰区收起或简化（不能挤压表单）。

## §C 主应用布局改版（顶栏 → 侧边栏）

**现状**：`Layout.tsx` 是**顶栏**（header 内横排导航）。

**目标**（参考 Voyage 控制台）：

```
┌──────────────┬──────────────────────────────────┐
│  zace        │  页面标题                          │
│              │                                  │
│  工作台       │  ┌────────────────────────────┐  │
│  接入指南     │  │  内容区（各页面）           │  │
│  API Key     │  │                            │  │
│  历史记录     │  └────────────────────────────┘  │
│  设置         │                                  │
│              │                                  │
│  ────────    │                                  │
│  账户名       │                                  │
│  [登出]       │                                  │
└──────────────┴──────────────────────────────────┘
   侧边栏 (固定宽度)      右侧内容区
```

**要求**：
- **导航项与顺序不变**（控制台 → 接入指南 → API Key → 历史记录 → 设置）——
  这是 TASK-086 定的契约，`to` 路径是外部链接指向的目标，**不得改**；
- 账户名与登出移到侧边栏底部；
- active 态用 `accent.seal`（朱砂色）而非当前的 `bg-slate-900`；
- **窄屏响应**（**用户拍板：固定 + 抽屉**）：
  - 桌面（≥768px）：侧边栏**固定展开**（建议宽 200px）；
  - 窄屏（<768px）：折叠为一个**汉堡按钮**，点击展开抽屉（overlay 或推入式）；
  - 抽屉需支持**点击导航后自动关闭**；
  - 不要引入抽屉库（自己写轻量实现即可，约 20-30 行 state + className）；
  - 退而求其次：若抽屉实现成本超预期，可先做“窄屏变顶部横条”，
    但**必须在报告里说明并列为未决问题**。
- 页脚说明文案保留。

## §D 各页面卡片配色微调

`components/ui.tsx` 的 `Card` / `Badge` / `EmptyState` 等把 `slate-*` 换成新 token。
**只改配色与边框，不改结构与行为**。

## §E 测试同步（**必读，这里最容易出错**）

现有测试**硬绑定了样式类名**，改版必然打破它们：

```tsx
// web/src/app/Layout.test.tsx:68-75（现状）
expect(navLinkClass("控制台")).not.toContain("bg-slate-900");
expect(navLinkClass("接入指南")).toContain("bg-slate-900");
expect(screen.getByRole("banner").className).toContain("bg-white");
```

**要求**：

1. `Layout.test.tsx` 的样式断言**必须同步更新**（改用新 token 的类名）；
2. **不得删除这些断言**——它们守护的是"active 态可辨识"与"header 不透明"
   （TASK-086 §4 的真实教训）。**改成断言新类名即可**；
3. 若布局从顶栏改侧边栏导致 `getByRole("banner")` 失效，
   **改用合适的 role 或结构断言**（如实说明改动原因）；
4. 其余测试（`App.test.tsx` / `ui.test.tsx` / `e2e.test.tsx` / `console.e2e.test.tsx`）
   凡是因改版失败的，**同步修正且不得削弱覆盖**；
5. **严禁**为了让测试通过而删断言或改产品代码的行为。

## 验收标准（DoD）

- [ ] `cd web && npm run lint && npm test && npm run build` 全绿；
- [ ] **功能零回归**（这是本卡最高优先级）：
  - [ ] 登录 / 注册 / 初始化三种模式仍正常；
  - [ ] 五个导航项仍在且顺序不变，`to` 路径未改；
  - [ ] 登出仍正常；
  - [ ] 各页面（控制台 / 接入指南 / API Key / 历史 / 设置）内容正常渲染；
- [ ] **视觉证据**（本卡是视觉任务，**必须提供**）：
  - [ ] 登录页截图（含桌面宽度与窄屏各一张）；
  - [ ] 主应用截图（侧边栏 + 内容区，至少两个不同页面）；
  - [ ] 说明背景纹理的实现方式与参数；
  - > 本机已装 Playwright chromium（`~/.cache/ms-playwright/chromium-1243`），
    > **可写真浏览器截图**（`npm run build` 后用 `vite preview` + Playwright 访问）。
    > 若确实跑不通，用 jsdom 无法产出截图——**那就在报告里如实说明"未能提供截图"**，
    > 不要用文字描述冒充视觉验证。
- [ ] **对比度自检**：正文文字与老纸底的对比度不低于 WCAG AA（4.5:1）；
      贴出你用工具或人工计算的值；
- [ ] 基线三条命令全绿：`uv run ruff check .`、
      `uv run python scripts/check_dependency_direction.py`、`uv run pytest -o addopts="" -q`
      （后三条是因为改 `web/` 不应影响 Python 侧，顺带确认没误改）；
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- **不改** 任何 API 调用、路由 `to` 路径、页面业务逻辑；
- **不引入** 新的 npm 依赖（不装 UI 库、不下载字体文件）；
- **不做** 深色模式（本轮只做老纸风格）；
- **不做** 动画/过渡特效（除非极轻量）；
- **不改** `web/src/api/**`、`web/src/app/App.tsx` 的路由表；
- **不改** 服务端渲染的 Markdown 样式契约（检索结果的 `render_markdown` 输出不受影响）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板。**必须包含**：

- §A 设计 token 全表（颜色 + 字体 + 纹理参数）；
- **截图对照**（改版前 vs 改版后，登录页 + 主应用各一组）；
- §E 测试同步清单（改了哪些断言、为什么，**证明没有削弱覆盖**）；
- 对比度自检结果。

## 执行记录

### 2026-09-14 ｜ 泳道 J ｜ 分支 `feature/task-098-retro-theme_xwz0914`

**基线**：从 `main` 的 `cf2d4a4` 起（该提交即本卡的纹理/窄屏决策钉版；开工时本分支停在
`e90ac11`，已用 `git merge --ff-only main` 快进到 `cf2d4a4`，无自有提交、无冲突）。

**交付物（均已改）**：

| 文件 | 改动 |
|---|---|
| `web/tailwind.config.js` | 新增 `paper` / `ink` / `accent` token；新增 `fontFamily.serif` 衬线栈 |
| `web/src/index.css` | 老纸底 + 斑驳纹理（14 处 radial-gradient + 1 层纤维斜线）；标题用衬线；移除旧 `grid` 纹理 |
| `web/src/app/Layout.tsx` | 顶栏 → 侧边栏；窄屏汉堡抽屉 |
| `web/src/app/Layout.test.tsx` | **同步**样式断言到新 token，并新增 2 条（见 §E） |
| `web/src/pages/LoginPage.tsx` | 左装饰区（老纸+衬线品牌字+细线几何图案）+ 右纯白浮卡片 |
| `web/src/components/ui.tsx` | `Card` / `CopyButton` / `KeyValue` / `LoadingBlock` / `EmptyState` 配色迁移 |
| `web/index.html` | `<body>` 去掉 `bg-slate-50 text-slate-900`（底色/纹理由 `index.css` 提供） |
| `web/src/components/progress.ts` | `TONE_CLASS.idle` 迁移到 token |
| `web/src/components/{Markdown,MetaPanel}.tsx` | 配色迁移（代码块底色改 `ink.primary`） |
| `web/src/pages/{Dashboard,History,ApiKeys,Connect,Settings}Page.tsx` | **仅 className**：`slate-*`/`bg-white` → 新 token |
| `docs/evidence/task-098/` | 截图对照 + 可复现脚本 + 对比度计算脚本（新增） |

**§A 设计 token 全表**

颜色（`tailwind.config.js`，组件内无裸色值）：

| token | 值 | 用途 |
|---|---|---|
| `paper.base` | `#f3e4c7` | 主背景（用户指定） |
| `paper.raised` | `#f7ecd8` | 侧边栏 / 窄屏顶栏 / hover |
| `paper.card` | `#ffffff` | 卡片（保持纯白） |
| `ink.primary` | `#2a2419` | 主文字（深墨，非纯黑） |
| `ink.muted` | `#6b5d48` | 次级文字 |
| `ink.line` | `#d9c9a8` | 边框线 |
| `accent.seal` | `#8c3a2b` | 朱砂：active 导航 / 主按钮 |

字体：`fontFamily.serif = ui-serif, Georgia, Cambria, "Songti SC", "SimSun", "Noto Serif CJK SC", serif`
（系统栈，**零字体文件依赖**），只作用于 `h1/h2/h3` 与品牌字；正文保留原 sans，代码保留 mono。

纹理参数（`index.css` 顶部集中注释块，变量 `--zace-stain: 92 70 38` / `--zace-bleach: 255 250 236`）：

- **14 处 radial-gradient**（8 处暗斑 alpha 0.013-0.026 + 6 处泛白 alpha 0.018-0.030），
  圆半径 300-820px、坐标互相错开；
- 叠 1 层纤维斜线 `repeating-linear-gradient(118deg, … 1px, transparent 120px)`，alpha 0.012
  （间距刻意取大以避开高 DPI 摩尔纹/色带）；
- `background-attachment: fixed`；
- 实测纸面亮度极差 ≈ 2%（见证据目录 README），不构成噪点。

**选择理由**：用户拍板“斑驳旧纸感”，故用**多处径向渐变**而非细密斜线（斜线偏“亚麻布”，
与老纸气质不符）；斜线只作为**极淡辅助层**保留纤维感（§A-3 的“可选增强”），
因 alpha 0.012 且间距 120px，实测无可见摩尔纹。

**§E 测试同步清单（无一条被删除）**

| 原断言 | 现断言 | 守护的东西（未变） |
|---|---|---|
| `navLinkClass("控制台")` `.not.toContain("bg-slate-900")` | `.not.toContain("bg-accent-seal")` | 非 active 项不高亮（`end` 生效） |
| `navLinkClass("接入指南")` `.toContain("bg-slate-900")` | `.toContain("bg-accent-seal")` | active 态可辨识 |
| `getByRole("banner").className` 含 `bg-white` | `getByTestId("sidebar").className` 含 `bg-paper-raised` | 导航底色**不透明** |

- 第 3 条换元素的原因（§E-3 允许并要求如实说明）：侧边栏是 `<aside>`，隐式 role 为
  `complementary` 而非 `banner`（`banner` 只对应不在 section 内的 `<header>`）。改版后仍存在
  `<header>`，但它只是**窄屏顶栏**（`md:hidden`），不再是承载导航的常驻面——继续用 `banner`
  会**测错对象**。因此改为断言真正承载导航的侧边栏。
- **覆盖面不缩小（反而扩大）**：`Layout.test.tsx` 由 4 条增至 **6 条**——新增
  ①“窄屏顶栏也不透明”（另一个滚动遮挡面，同一 §4 教训）；
  ②“账户名与登出仍在侧边栏底部”（§C 要求，原先无断言）。
- `navLinks()` 改用 `getByRole("navigation", { name: "主导航" })`：语义未变，测试不依赖布局细节。
- `App.test.tsx` / `ui.test.tsx` / `SettingsPage.test.tsx` / `client.test.ts` / `progress.test.ts`
  **未改动即通过**（43 passed）——说明改版没有改变任何可观察行为。

**验收命令与结果**

```
cd web && npm run lint    → 通过（eslint 无输出）
npm test                  → 7 passed | 2 skipped (9 files)，43 passed | 3 skipped (46 tests)
npm run build             → ✓ built in 3.70s（dist/assets/index-*.css 19.31 kB / *.js 247.97 kB）
uv run ruff check .                        → All checks passed!
uv run python scripts/check_dependency_direction.py → 依赖方向检查通过
uv run pytest -o addopts="" -q             → 878 passed, 2 skipped（与 dispatch.md 记录的基线一致）
```

**真浏览器核验（Playwright chromium，29 项全 PASS，脚本见 `docs/evidence/task-098/verify.py`）**

- 导航项顺序 `控制台→接入指南→API Key→历史记录→设置` 与 `to` 路径 `/ /connect /keys /history /settings` 全部不变；
- 逐项点击后 URL 与 active 底色（`bg-accent-seal`）均正确；
- 窄屏抽屉：初始关闭 → 汉堡打开 → **点导航后自动关闭** → 点遮罩关闭；
- 登录页三模式（login / register / bootstrap，`modes.py`）+ 登录失败错误块 + 登出回登录页（`logout.py`）。

**对比度自检（WCAG，`contrast.py` 实测）**

- 正文 `ink.primary` on `paper.base` = **12.26:1**；次级文字 `ink.muted` on `paper.base` = **5.09:1**；
- active 导航/主按钮（白字 on `accent.seal`）= **7.62:1**；
- 均 ≥ AA 4.5:1。
- **顺带发现并修复的真实问题**：老纸底替换原浅蓝灰后，页面里原有的 `slate-500`(3.79:1) 与
  `slate-400`(2.04:1) 文字**不再满足 AA**。故对这些 className 的迁移是本卡“对比度自检”
  验收项的**必要条件**，不是顺手美化。

**与设计的偏差 / 需要编排者留意**

1. **清单外文件改动（已尽量克制）**：本卡清单外实际改了 3 处，均属“配色统一”必需，理由如下，
   若编排者认为越界可要求回退：
   - `web/index.html`：`<body>` 的 `bg-slate-50 text-slate-900` 必须去掉，否则会**盖住** `index.css`
     的纸底纹理（`bg-slate-50` 直接覆盖 `background-color`）；
   - `web/src/components/{progress.ts,Markdown.tsx,MetaPanel.tsx}`：同 §D“卡片配色微调”性质，
     且含上面 `slate-500/400` 的 AA 违规项；不迁移则对比度验收不通过；
   - `web/src/pages/{ApiKeys,Connect,Settings}Page.tsx`：卡片内**直接**写着 `border-slate-200 bg-white`
     等类名（不经 `ui.tsx` 的 `Card`），不迁则视觉不统一、且 `slate-500/400` 文字违反 AA。
     **五个页面的逻辑一行未改**（可通过 `git diff` 核对：无新增/删除状态、副作用、事件处理）。
2. **`colors.grid` 被移除**：任务卡 §A-1 提到“保留 `grid` 或合理迁移”。我选择**移除**并换为 `paper`
   ——网格是“工程感”，与老纸气质冲突；且仓库内除 `index.css` 外**无任何引用**（已全仓 grep 确认
   只有 `docs/tasks/TASK-086-*.md` 的设计说明里提及）。若需保留兼容名请告知。
3. **`accent.sealsoft` 已删除**：初版加了 hover 变浅色，但**白字在 `#a8543f` 上只有 5.2:1、
   且与 `seal` 区分度低**，收益不抵多一个 token 的维护成本，故删掉，hover 不做色变。

**未决问题**

1. **与 TASK-094 的冲突面**：094 也改 `DashboardPage.tsx` / `HistoryPage.tsx`。本卡在这两个文件里
   只动 className（及其中的颜色 token），**未触碰任何逻辑**。若 094 已改同一区域，合并时
   大概率是纯文本冲突（配色行 vs 逻辑行），按 §0 由编排者裁决——本卡**未顺手改任何 094 的功能**。
2. **窄屏抽屉的键盘可达性**：当前 `Esc` 不能关抽屉（只有汉堡/遮罩/点导航三种关法）。
   卡内说“不要做复杂交互”，故未加；如需可后续补一个 `keydown` 监听。
3. **构建产物中的 `text-paper-base` 仅用于深色代码块**：`bg-ink-primary` + `text-paper-base`
   的代码块**未做对比度断言**（`#f3e4c7` on `#2a2419` = 12.26:1，实际同样满足 AA）。

