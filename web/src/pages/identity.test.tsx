/**
 * TASK-110 P4 验收：三种身份看到的页面确实不同。
 *
 * 卡内 §5 的 P4 清单（**逐条一个断言**）：
 *
 * | 验收项 | 用例 |
 * |---|---|
 * | 内测用户 Key 页显示 `🧭 拓荒者特权 · 可自定义 API Key` | ``describe("Key 页特权")`` 第一条 |
 * | 公测用户 Key 页**显式说明**自定义是拓荒者专属 | ``describe("Key 页特权")`` 第二条 |
 * | 头衔与编号在账户页可见（`拓荒者 #0027`） | ``describe("账户页")`` |
 * | 三种身份登录后页面确实不同 | ``describe("三身份对照")`` |
 *
 * 测试策略：把 ``fetch`` 桩成按路由返回不同身份（与 ``App.test.tsx`` 同一手法），
 * 然后**渲染真实页面组件**并断言可见文本。不断言实现细节（class 名），只断言
 * "用户能看到什么"——那才是"页面确实不同"的可观察证据。
 */

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Account } from "../api/client";
import { AccountPage } from "./AccountPage";
import { AdminPage } from "./AdminPage";
import { ApiKeysPage } from "./ApiKeysPage";

/** 一个账户模板（身份字段由用例覆盖；能力位必须与角色**一致**，它们本就是同源的）。 */
const PUBLIC_ACCOUNT: Account = {
  userId: "u1",
  name: "plain",
  createdAt: 1789300000,
  isLocal: false,
  via: "session",
  role: "public",
  title: "旅人",
  earlyMemberNo: null,
  capabilities: {
    canCustomKey: false,
    quotaBytes: 500 * 1024 * 1024,
    earlyMemberNo: null,
    isAdmin: false,
  },
};

const BETA_ACCOUNT: Account = {
  ...PUBLIC_ACCOUNT,
  name: "early",
  role: "beta",
  title: "拓荒者",
  earlyMemberNo: 27,
  capabilities: {
    canCustomKey: true,
    quotaBytes: 1024 * 1024 * 1024,
    earlyMemberNo: 27,
    isAdmin: false,
  },
};

const ADMIN_ACCOUNT: Account = {
  ...PUBLIC_ACCOUNT,
  name: "boss",
  role: "admin",
  title: "执炬者",
  capabilities: {
    canCustomKey: true,
    quotaBytes: 5 * 1024 * 1024 * 1024,
    earlyMemberNo: null,
    isAdmin: true,
  },
};

/** 按路由前缀桩 ``fetch``（返回体由调用方给）。 */
function stubRoutes(routes: Record<string, unknown>, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      for (const [key, body] of Object.entries(routes)) {
        if (url.includes(key)) {
          return new Response(JSON.stringify(body), { status });
        }
      }
      return new Response(JSON.stringify({ error: { code: "not_found", message: "no route" } }), {
        status: 404,
      });
    }),
  );
}

function renderInRouter(node: React.ReactNode) {
  return render(<MemoryRouter initialEntries={["/"]}>{node}</MemoryRouter>);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// --------------------------------------------------------------------------- Key 页特权

describe("Key 页特权展示（TASK-110 §1.7）", () => {
  it("内测用户的 Key 页显示 拓荒者特权 · 可自定义 API Key 与自定义输入框", async () => {
    stubRoutes({
      "/api/auth/me": BETA_ACCOUNT,
      "/api/auth/tokens": [],
    });
    renderInRouter(<ApiKeysPage />);

    const banner = await screen.findByTestId("privilege-banner");
    expect(banner.textContent).toContain("拓荒者特权");
    expect(banner.textContent).toContain("可自定义 API Key");
    expect(banner.textContent).toContain("#027");
    // 自定义输入框可用（placeholder 就是引导）。
    expect(screen.getByPlaceholderText("zace_my-project-2026")).toBeInTheDocument();
  });

  it("公测用户的 Key 页**显式说明**自定义是拓荒者专属，且不给输入框", async () => {
    stubRoutes({
      "/api/auth/me": PUBLIC_ACCOUNT,
      "/api/auth/tokens": [],
    });
    renderInRouter(<ApiKeysPage />);

    const banner = await screen.findByTestId("privilege-banner");
    expect(banner.textContent).toContain("拓荒者");
    expect(banner.textContent).toContain("专属");
    // 不是静默隐藏：面板仍在，只是说明了它属于谁。
    expect(screen.queryByPlaceholderText("zace_my-project-2026")).toBeNull();
  });

  it("管理员的 Key 页同样显示特权（管理员也享有自定义 Key）", async () => {
    stubRoutes({
      "/api/auth/me": ADMIN_ACCOUNT,
      "/api/auth/tokens": [],
    });
    renderInRouter(<ApiKeysPage />);

    const banner = await screen.findByTestId("privilege-banner");
    expect(banner.textContent).toContain("执炬者特权");
    expect(banner.textContent).toContain("可自定义 API Key");
  });
});

// --------------------------------------------------------------------------- 账户页

describe("账户页头衔与编号（TASK-110 §1.3/§1.4）", () => {
  it("内测用户看到 拓荒者 #027 与 1.00 GiB 额度", async () => {
    stubRoutes({
      "/api/auth/me": BETA_ACCOUNT,
      "/api/account/overview": {
        account: { name: "early", createdAt: 1789300000, isLocal: false, projectCount: 2 },
        index: { total: 0, succeeded: 0, failed: 0, avgDurationMs: null, recent: [] },
        usage: { total: 0, succeeded: 0, insufficient: 0, failed: 0, recent: [] },
        projects: [],
        days: 30,
        storage: {
          status: "ok",
          warnRatio: 0.8,
          projectId: "",
          user: { usedBytes: 1024, limitBytes: 1024 * 1024 * 1024, ratio: 0.000001, status: "ok", unlimited: false },
          project: { usedBytes: 0, limitBytes: 0, ratio: null, status: "ok", unlimited: true },
        },
      },
    });
    renderInRouter(<AccountPage />);

    expect(await screen.findByText("拓荒者 #027")).toBeInTheDocument();
    expect(screen.getByText("1.00 GiB")).toBeInTheDocument();
    expect(screen.getByText(/可用（拓荒者特权）/)).toBeInTheDocument();
  });

  it("无编号的内测用户只显示头衔（第 101 名起不再发号）", async () => {
    stubRoutes({
      "/api/auth/me": {
        ...BETA_ACCOUNT,
        earlyMemberNo: null,
        capabilities: { ...BETA_ACCOUNT.capabilities, earlyMemberNo: null },
      },
      "/api/account/overview": {
        account: { name: "early", createdAt: 1789300000, isLocal: false, projectCount: 0 },
        index: { total: 0, succeeded: 0, failed: 0, avgDurationMs: null, recent: [] },
        usage: { total: 0, succeeded: 0, insufficient: 0, failed: 0, recent: [] },
        projects: [],
        days: 30,
      },
    });
    renderInRouter(<AccountPage />);

    expect(await screen.findByTestId("title-badge")).toHaveTextContent("拓荒者");
    expect(screen.getByTestId("title-badge").textContent).not.toContain("#");
  });

  it("公测用户的账户页显示 旅人 与 不可用（拓荒者专属）", async () => {
    stubRoutes({
      "/api/auth/me": PUBLIC_ACCOUNT,
      "/api/account/overview": {
        account: { name: "plain", createdAt: 1789300000, isLocal: false, projectCount: 0 },
        index: { total: 0, succeeded: 0, failed: 0, avgDurationMs: null, recent: [] },
        usage: { total: 0, succeeded: 0, insufficient: 0, failed: 0, recent: [] },
        projects: [],
        days: 30,
      },
    });
    renderInRouter(<AccountPage />);

    expect(await screen.findByTestId("title-badge")).toHaveTextContent("旅人");
    expect(screen.getByText(/不可用（拓荒者专属）/)).toBeInTheDocument();
    expect(screen.getByText("500.0 MiB")).toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------- 后台页

describe("管理员后台页（TASK-110 §1.6）", () => {
  it("五个模块标签齐全", async () => {
    stubRoutes({
      "/api/admin/users": { users: [], limit: 100 },
    });
    renderInRouter(<AdminPage />);

    await waitFor(() => expect(screen.getByText("用户")).toBeInTheDocument());
    for (const label of ["用户", "邀请码", "项目", "调用统计", "系统状态"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("用户列表显示身份、编号、项目数与占用", async () => {
    stubRoutes({
      "/api/admin/users": {
        users: [
          {
            userId: "u2",
            name: "early",
            createdAt: 1789300000,
            isLocal: false,
            role: "beta",
            title: "拓荒者",
            earlyMemberNo: 27,
            quotaBytes: null,
            effectiveQuotaBytes: 1024 * 1024 * 1024,
            bannedAt: null,
            lastSeenAt: 1789400000,
            projectCount: 3,
            usedBytes: 1024 * 1024,
            usedText: "1.0 MiB",
            queryCount: 12,
          },
        ],
        limit: 100,
      },
    });
    renderInRouter(<AdminPage />);

    expect(await screen.findByText("early")).toBeInTheDocument();
    expect(screen.getByText("#027")).toBeInTheDocument();
    expect(screen.getByText("1.0 MiB")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    // 额度显示的是**实际生效**值（与上传被拒同源），不是角色默认值。
    expect(screen.getByText("1.00 GiB")).toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------- 三身份对照

describe("三身份对照（卡内 §3.6 的页面差异表）", () => {
  it("同一个 Key 页在三种身份下内容确实不同", async () => {
    const collect = async (account: Account) => {
      stubRoutes({ "/api/auth/me": account, "/api/auth/tokens": [] });
      const view = renderInRouter(<ApiKeysPage />);
      const banner = await screen.findByTestId("privilege-banner");
      const text = banner.textContent ?? "";
      view.unmount();
      vi.unstubAllGlobals();
      return text;
    };

    const asPublic = await collect(PUBLIC_ACCOUNT);
    const asBeta = await collect(BETA_ACCOUNT);
    const asAdmin = await collect(ADMIN_ACCOUNT);

    expect(new Set([asPublic, asBeta, asAdmin]).size).toBe(3);
    expect(asPublic).toContain("专属");
    expect(asBeta).toContain("拓荒者特权");
    expect(asAdmin).toContain("执炬者特权");
  });
});
