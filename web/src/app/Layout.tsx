/** 应用外壳：主导航 + 当前账户 + 登出（TASK-071）。 */

import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { type Account, logout } from "../api/client";

/** 大页面导航（用户 2026-09-13 指定的信息架构）。 */
const NAV = [
  { to: "/", label: "账户", end: true },
  { to: "/keys", label: "API Key", end: false },
  { to: "/history", label: "历史记录", end: false },
  { to: "/connect", label: "接入指南", end: false },
];

export function Layout({
  account,
  onSignedOut,
}: {
  account: Account | null;
  onSignedOut: () => void;
}) {
  const navigate = useNavigate();

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
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-3">
          <NavLink to="/" className="font-mono text-lg font-semibold text-slate-900">
            zace
          </NavLink>
          <nav className="flex flex-wrap gap-1 text-sm">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded px-2 py-1 ${
                    isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-xs text-slate-500">
            {account && (
              <span>
                {account.name}
                {account.isLocal && <span className="ml-1 text-slate-400">（本地）</span>}
              </span>
            )}
            {account && !account.isLocal && (
              <button
                type="button"
                onClick={() => void onLogout()}
                className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-50"
              >
                登出
              </button>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-slate-400">
        zace-web（Module 07 / D-40）：检索结果由服务端渲染，本页不重新拼装。
      </footer>
    </div>
  );
}
