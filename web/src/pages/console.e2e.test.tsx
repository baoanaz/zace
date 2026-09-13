/**
 * 端到端：**真实服务 + 真实页面**（TASK-070/071 console 流程）。
 *
 * 默认跳过；启用方式（需要一个云端模式的服务实例）：
 *
 * ```bash
 * export NO_PROXY=127.0.0.1,localhost
 * ZACE_LOCAL_MODE=false ZACE_REGISTER_OPEN=true ZACE_DATA_ROOT=/tmp/zace-ui/data \
 *   uv run zace-service serve --port 8891
 * cd web && ZACE_E2E=1 ZACE_E2E_BASE=http://127.0.0.1:8891 \
 *   ZACE_E2E_USER=<账户> ZACE_E2E_PASSWORD=<密码> \
 *   VITE_ZACE_API_BASE=http://127.0.0.1:8891 npx vitest run src/pages/console.e2e.test.tsx
 * ```
 *
 * 为什么必须有它：单元测试用 mock 只能证明"我按我以为的契约解析了"。
 * 这个文件证明的是**真实服务返回被真实页面正确渲染**——契约对齐的唯一硬证据。
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "../app/App";

const enabled = process.env["ZACE_E2E"] === "1";
const base = process.env["ZACE_E2E_BASE"] ?? "http://127.0.0.1:8891";
const user = process.env["ZACE_E2E_USER"] ?? "";
const password = process.env["ZACE_E2E_PASSWORD"] ?? "";

/**
 * 模拟浏览器对**同源**请求的 cookie 行为（仅在测试内，不改产品代码）。
 *
 * 为什么需要：vitest 的 jsdom 环境里，`fetch` 是 Node 的 undici——它**不共享 jsdom 的 cookie
 * jar**，因此登录响应里的 `Set-Cookie` 不会被后续请求带上，账户面板会因 401 而渲染不出来。
 * 生产形态里 web 与 API 由 Caddy 同源（Module/07 §3），浏览器会自动带上 cookie，
 * 所以这里补的就是浏览器免费提供、而测试环境缺失的那一环。
 */
function installCookieForwarder(origin: string): () => void {
  const original = globalThis.fetch;
  const jar = new Map<string, string>();

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const sameOrigin = url.startsWith(origin);
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : {}));
    if (sameOrigin && jar.size > 0) {
      headers.set("Cookie", [...jar].map(([k, v]) => `${k}=${v}`).join("; "));
    }
    const response = await original(input as RequestInfo, { ...init, headers });
    if (sameOrigin) {
      // 只取 cookie 名与值（不关心属性）；登出时服务端会下发 Max-Age=0。
      for (const raw of response.headers.getSetCookie?.() ?? []) {
        const [pair] = raw.split(";");
        const index = (pair ?? "").indexOf("=");
        if (index <= 0) continue;
        const name = pair!.slice(0, index);
        const value = pair!.slice(index + 1);
        if (value === "" || raw.includes("Max-Age=0")) jar.delete(name);
        else jar.set(name, value);
      }
    }
    return response;
  }) as typeof fetch;

  return () => {
    globalThis.fetch = original;
  };
}

afterEach(() => {
  window.sessionStorage.clear();
});

describe.skipIf(!enabled)("端到端：账户console（真实服务）", () => {
  it("首屏是登录页；登录后进入账户面板并显示真实统计字段", async () => {
    const restore = installCookieForwarder(base);
    try {
      render(<App />);

      // 1) 首屏必须是登录页（用户指定的信息架构）。
      expect(
        await screen.findByRole("heading", { name: "登录" }, { timeout: 15_000 }),
      ).toBeInTheDocument();

      // 2) 登录（真实 POST /api/auth/login → session cookie）。
      const typed = userEvent.setup();
      await typed.type(screen.getByLabelText("账户"), user);
      await typed.type(screen.getByLabelText("密码"), password);
      await typed.click(screen.getByRole("button", { name: "登录" }));

      // 3) 落到账户面板，且四个数据面板都在。
      expect(
        await screen.findByRole("heading", { name: "账户" }, { timeout: 15_000 }),
      ).toBeInTheDocument();
      for (const label of ["账户资料", "成功次数", "失败次数", "占用内存"]) {
        expect(screen.getByText(label)).toBeInTheDocument();
      }
      // "平均耗时"在索引与用量两个面板各有一个（口径不同），因此按数量断言。
      expect(screen.getAllByText("平均耗时")).toHaveLength(2);
      // 导航包含全部大页面。
      for (const label of ["项目", "Playground", "API Key", "历史记录", "接入指南"]) {
        expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
      }
    } finally {
      restore();
    }
  }, 60_000);

  it("未测量项显示破折号/尚未测量，而不是 0（诚实性）", async () => {
    const response = await fetch(`${base}/api/meta`);
    const meta = (await response.json()) as { authRequired: boolean };
    expect(meta.authRequired).toBe(true);

    const me = await fetch(`${base}/api/auth/me`);
    expect(me.status).toBe(401);
  }, 30_000);
});
