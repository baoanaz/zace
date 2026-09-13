/** 应用外壳：导航 + 未就绪页的入口（Module/07 §1 的页面表）。 */

import { NavLink, Outlet } from "react-router-dom";

import { NOT_READY_FEATURES } from "../app/connect-info";

const NAV = [
  { to: "/", label: "项目" },
  { to: "/playground", label: "Playground" },
  { to: "/connect", label: "接入指南" },
];

export function Layout() {
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
                end={item.to === "/"}
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
          <div className="ml-auto flex flex-wrap gap-1 text-xs text-slate-500">
            {NOT_READY_FEATURES.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                title={`未就绪：依赖 ${item.dependsOn.join(" / ")}`}
                className="rounded border border-dashed border-slate-300 px-2 py-0.5 hover:bg-slate-50"
              >
                {item.title}
              </NavLink>
            ))}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-slate-400">
        zace-web（Module 07 / D-40）：管理面与 Playground。检索结果由服务端渲染，本页不重新拼装。
      </footer>
    </div>
  );
}
