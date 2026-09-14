# TASK-098 视觉证据（WebUI 复古博物画风格 + 侧边栏布局）

本目录是 TASK-098 的**截图与可复现脚本**。截图由**真浏览器**（Playwright + Chromium）产出，
不是文字描述或 jsdom 模拟。

## 截图对照

| 文件 | 说明 |
|---|---|
| `before-login-desktop.png` / `after-login-desktop.png` | 登录页（1440×900）改版前后 |
| `before-login-narrow.png` / `after-login-narrow.png` | 登录页（390×780）改版前后；改版后装饰区收起 |
| `before-dashboard-desktop.png` / `after-dashboard-desktop.png` | 控制台（顶栏 → 侧边栏） |
| `before-history-desktop.png` / `after-history-desktop.png` | 历史记录页 |
| `before-keys-desktop.png` / `after-keys-desktop.png` | API Key 页 |
| `before-dashboard-narrow.png` / `after-dashboard-narrow.png` | 窄屏控制台（汉堡按钮顶栏） |
| `after-drawer-narrow.png` | 窄屏**抽屉打开态**（改版前无此形态，故无对应 before 图） |
| `after-login-register-desktop.png` | 注册模式（验证三模式未回归） |
| `after-login-bootstrap-desktop.png` | 初始化账户模式 |
| `after-dashboard-signedin-desktop.png` | 云端已登录（侧边栏底部账户名 + 登出） |

改版前的窄屏没有抽屉，`before-dashboard-narrow.png` 即当时的窄屏全貌
（曾另存一张 `before-drawer-narrow.png`，与它逐字节相同，已删除避免冗余）。

## 复现方式

```bash
# 1) 构建前端
cd web && npm run build

# 2) 起一个 mock（静态托管 dist + 假 API；仅截图用，不属于产品代码）
python3 docs/evidence/task-098/mock_server.py 8120 cloud   "$PWD/web/dist" &
python3 docs/evidence/task-098/mock_server.py 8121 local   "$PWD/web/dist" &
python3 docs/evidence/task-098/mock_server.py 8122 register "$PWD/web/dist" &
python3 docs/evidence/task-098/mock_server.py 8123 bootstrap "$PWD/web/dist" &
python3 docs/evidence/task-098/mock_server.py 8124 cloudauth "$PWD/web/dist" &

# 3) 截图 / 核验（脚本内已写死本机 chromium-1243 路径）
python3 docs/evidence/task-098/shoot.py   8120 cloud   ./shots after
python3 docs/evidence/task-098/shoot.py   8121 local   ./shots after
python3 docs/evidence/task-098/verify.py    # 29 项功能零回归核验（导航顺序/路径/抽屉/登录页）
python3 docs/evidence/task-098/modes.py     # 登录页三模式核验
python3 docs/evidence/task-098/logout.py    # 登出回归

# 4) 对比度自检（WCAG 相对亮度）
python3 docs/evidence/task-098/contrast.py
```

## 对比度自检结果（`contrast.py` 实测）

| 配对 | 对比度 | AA 正文 (4.5:1) |
|---|---|---|
| `ink.primary` #2a2419 on `paper.base` #f3e4c7 | **12.26:1** | PASS |
| `ink.primary` on `paper.raised` #f7ecd8 | 13.15:1 | PASS |
| `ink.primary` on `paper.card` #ffffff | 15.39:1 | PASS |
| `ink.muted` #6b5d48 on `paper.base` | **5.09:1** | PASS |
| `ink.muted` on `paper.raised` | 5.46:1 | PASS |
| `ink.muted` on `paper.card` | 6.39:1 | PASS |
| 白字 on `accent.seal` #8c3a2b（active 导航 / 主按钮） | **7.62:1** | PASS |
| `accent.seal` on `paper.base` | 6.07:1 | PASS |
| （对照）旧 `slate-500` #64748b on `paper.base` | 3.79:1 | **FAIL ← 因此必须迁移** |
| （对照）旧 `slate-400` #94a3b8 on `paper.base` | 2.04:1 | **FAIL ← 因此必须迁移** |

> 注意：把老纸底换成底色后，页面里原有的 `slate-500` / `slate-400` 文字在米黄底上
> **不满足 AA**（3.79 / 2.04）。所以本次对这些 className 的迁移不是"顺手美化"，
> 而是本卡"对比度自检"验收项的**必要条件**。

## 纹理参数实测

对 `after-login-desktop.png` 的纸面区域做像素采样：

- 底色 `paper.base` = `#f3e4c7` = (243, 228, 199)
- 实测纸面范围 (236, 220, 191) ~ (242, 227, 198)
- 亮度极差 ≈ 4.8 / 224 ≈ **2%** —— 纹理确实"极淡"，不构成噪点、不影响可读性。
