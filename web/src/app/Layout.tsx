/**
 * 应用外壳：**左侧边栏**主导航 + 当前账户 + 登出（TASK-071；TASK-098 §C 改版）。
 *
 * TASK-098 把顶栏横排导航改成**左侧固定侧边栏 + 右侧内容区**（参考 Voyage 控制台），
 * 配色换成老纸主题（paper / ink / accent token，见 `tailwind.config.js`）。
 *
 * 三条**不许变**的东西（本卡是纯视觉改版，不是功能重构）：
 * 1. `NAV` 的 `to` 路径——`to` 是路由契约，外部链接与文档都指向它；
 * 2. 账户名与登出按钮的行为（登出失败也要清本地状态）；
 * 3. 侧边栏与窄屏顶栏的**不透明**（内容滚动时不能透过导航文字）。
 *
 * TASK-100：新增「项目」页（用户 2026-09-14 要求放在控制台下面，与控制台同级）；
 * 删掉页脚版本说明文案（用户："用户不需要知道这些"）。
 *
 * TASK-110：新增「后台」入口，**只对管理员显示**（由 ``account.capabilities.isAdmin``
 * 决定，不在这里写 ``role === "admin"``）；「账户」项已移除——账户信息合并进控制台
 * （用户 2026-09-15 要求，/account 保留为跳转）。
 *
 * 窄屏（<768px）：侧边栏变成**抽屉**，由顶栏的汉堡按钮开关，点导航后自动关闭
 * （用户 2026-09-14 拍板；不引任何库）。
 */

import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { type Account, logout } from "../api/client";

/**
 * 大页面导航（用户 2026-09-13 指定的信息架构，2026-09-14 TASK-086 §1 定序）。
 *
 * 顺序即用户要求的展示顺序：控制台 → 项目 → 接入指南 → API Key → 历史记录 → 设置
 * （TASK-100 把「项目」插在控制台之后——它与控制台同级，都是"看数据"的页）。
 * **`to` 是路由契约**（外部链接与文档都指向它）。
 */
const NAV = [
  { to: "/", label: "控制台", end: true },
  { to: "/projects", label: "项目", end: false },
  { to: "/connect", label: "接入指南", end: false },
  { to: "/keys", label: "API Key", end: false },
  { to: "/history", label: "历史记录", end: false },
  { to: "/settings", label: "设置", end: false },
];

/**
 * 管理员专属导航（TASK-110）：只有 ``capabilities.isAdmin`` 为真时才出现在侧边栏。
 *
 * 为什么单独一条而不是把 ``NAV`` 写成带条件的数组：管理员条目在**末位且视觉上分开**
 * （它是运营工具，不是日常页面），把条件塞进同一个数组会让导航顺序变得难读。
 */
const ADMIN_NAV = { to: "/admin", label: "后台", end: false };

export function Layout({
  account,
  onSignedOut,
}: {
  account: Account | null;
  onSignedOut: () => void;
}) {
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // 抽屉状态只由交互驱动（汉堡按钮 / 遮罩 / 点导航关闭），不订阅路由变化。

  async function onLogout() {
    try {
      await logout();
    } catch {
      // 登出失败也要把本地状态清掉（否则界面会停在"已登录"而服务端其实已失效）。
    }
    onSignedOut();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen">
      {/*
       * 侧边栏：桌面常驻（md 起 translate-x-0），窄屏为抽屉。
       * `bg-paper-raised` 是**不透明**色（#f7ecd8）——内容滚动时不能透过导航文字。
       */}
      <aside
        id="zace-sidebar"
        data-testid="sidebar"
        className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-ink-line bg-paper-raised transition-transform duration-200 md:translate-x-0 ${
          drawerOpen ? "translate-x-0 shadow-xl" : "-translate-x-full"
        }`}
      >
        <div className="border-b border-ink-line px-5 py-5">
          <NavLink
            to="/"
            className="font-serif text-xl font-semibold tracking-tight text-ink-primary"
            onClick={() => setDrawerOpen(false)}
          >
            zace
          </NavLink>
          <p className="mt-0.5 text-xs text-ink-muted">Workspace Context Engine</p>
        </div>

        <nav aria-label="主导航" className="flex-1 space-y-1 px-3 py-4 text-sm">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setDrawerOpen(false)}
              className={({ isActive }) =>
                `block rounded px-3 py-2 ${
                  isActive
                    ? "bg-accent-seal font-medium text-white"
                    : "text-ink-muted hover:bg-paper-base hover:text-ink-primary"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
          {account?.capabilities?.isAdmin && (
            <NavLink
              to={ADMIN_NAV.to}
              end={ADMIN_NAV.end}
              onClick={() => setDrawerOpen(false)}
              className={({ isActive }) =>
                `mt-2 block rounded border-t border-dashed border-ink-line px-3 py-2 pt-3 ${
                  isActive
                    ? "bg-accent-seal font-medium text-white"
                    : "text-ink-muted hover:bg-paper-base hover:text-ink-primary"
                }`
              }
            >
              {ADMIN_NAV.label}
            </NavLink>
          )}
        </nav>

        <div className="border-t border-ink-line px-5 py-4 text-xs text-ink-muted">
          {account && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-ink-primary">{account.name}</span>
              {account.isLocal && <span>（本地）</span>}
              {/* TASK-110 §1.3/§1.4：身份徽章（拓荒者 #0027）。本地模式无身份体系，不显示。 */}
              {!account.isLocal && (
                <span
                  data-testid="sidebar-title"
                  className="rounded-full border border-ink-line bg-paper-base px-2 py-0.5 text-[11px] text-ink-muted"
                >
                  {account.earlyMemberNo === null
                    ? account.title
                    : `${account.title} #${String(account.earlyMemberNo).padStart(3, "0")}`}
                </span>
              )}            </div>
          )}
          {account && !account.isLocal && (
            <button
              type="button"
              onClick={() => void onLogout()}
              className="mt-2 rounded border border-ink-line bg-paper-card px-3 py-1 text-ink-primary hover:bg-paper-base"
            >
              登出
            </button>
          )}
        </div>
      </aside>

      {/*
       * 窄屏顶栏（<768px 才显示）：汉堡按钮 + 品牌字。
       * 同样保持不透明——它是窄屏下唯一的导航入口与滚动遮挡面。
       */}
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-ink-line bg-paper-raised px-4 py-3 md:hidden">
        <button
          type="button"
          /* 名称固定为“导航菜单”，开关状态由 aria-expanded 表达
             （不用“打开/关闭导航”两个名字，否则会与遮罩按钮重名）。 */
          aria-label="导航菜单"
          aria-expanded={drawerOpen}
          aria-controls="zace-sidebar"
          onClick={() => setDrawerOpen((open) => !open)}
          className="rounded border border-ink-line bg-paper-card px-2.5 py-1 text-ink-primary"
        >
          <span aria-hidden="true">☰</span>
        </button>
        <span className="font-serif text-base font-semibold text-ink-primary">zace</span>
      </header>

      {/* 抽屉遮罩：点它关抽屉。用 button 而不是 div，键盘也能关。 */}
      {drawerOpen && (
        <button
          type="button"
          aria-label="关闭导航抽屉"
          onClick={() => setDrawerOpen(false)}
          className="fixed inset-0 z-30 cursor-default bg-ink-primary/25 md:hidden"
        />
      )}

      {/* 内容区：桌面为侧边栏让出 15rem（w-60）宽度。 */}
      {/* TASK-100：宽度由**页面自己决定**（用户 2026-09-14）——只有历史记录这种宽表需要
          流式宽度；控制台/项目/接入指南/API Key/设置保持 64rem 的最大宽度更好读。
          因此壳层不再限制宽度，页面用 `WidePage`/`Page` 两个容器分别声明。 */}
      <div className="md:pl-60">
        <main className="px-4 py-6 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
