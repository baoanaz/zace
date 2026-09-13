/**
 * 首屏门禁与仪表盘口径（TASK-071）。
 *
 * 守两件事：
 * 1. **首屏是登录页**（用户明确要求），且"全新部署无账户"时显示初始化而不是登录；
 * 2. 统计面板**不美化数字**：失败次数不参与平均耗时、未测量显示 —。
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

function stubFetch(routes: Record<string, { status?: number; body: unknown }>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      calls.push({ url, init });
      for (const [key, value] of Object.entries(routes)) {
        if (url.includes(key)) {
          return new Response(JSON.stringify(value.body), { status: value.status ?? 200 });
        }
      }
      return new Response(JSON.stringify({ error: { code: "not_found", message: "no route" } }), {
        status: 404,
      });
    }),
  );
  return calls;
}

const ACCOUNT = {
  userId: "u1",
  name: "owner",
  createdAt: 1789300000,
  isLocal: false,
  via: "session",
};

const OVERVIEW = {
  account: { name: "owner", createdAt: 1789300000, isLocal: false, projectCount: 1 },
  index: {
    total: 10,
    succeeded: 9,
    failed: 1,
    avgDurationMs: 61_000,
    minDurationMs: 800,
    maxDurationMs: 230_900,
    lastRunAt: 1789305566,
    lastState: "done",
    diskBytes: 12_582_912,
    recent: [
      {
        runId: 3,
        projectId: "p1",
        state: "done",
        startedAt: 1789305500,
        finishedAt: 1789305566,
        durationMs: 66_000,
        filesTotal: 338,
        filesProcessed: 336,
        chunks: 9389,
        errors: 3,
        error: "broken.c: syntax error",
      },
    ],
  },
  usage: {
    projectId: null,
    days: 30,
    total: 20,
    succeeded: 15,
    insufficient: 4,
    failed: 1,
    avgLatencyMs: 137,
    p95LatencyMs: 420,
    confidenceDistribution: { medium: 15, low: 4 },
    citationCoverageAvg: null,
    topQueries: [],
    recent: [],
  },
  projects: [
    {
      projectId: "p1",
      displayName: "demo",
      sync: { filesIndexed: 338, chunks: 9389 },
      indexProgress: { state: "done" },
    },
  ],
  days: 30,
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("首屏门禁", () => {
  it("云端 + 有账户 + 未登录 → 显示登录页（首屏是登录，不是仪表盘）", async () => {
    stubFetch({
      "/api/meta": {
        body: {
          version: "0.0.1",
          localMode: false,
          authRequired: true,
          registerOpen: false,
          needsBootstrap: false,
          userCount: 1,
        },
      },
      "/api/auth/me": {
        status: 401,
        body: { error: { code: "unauthorized", message: "缺少或无效的凭据" } },
      },
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "登录" })).toBeInTheDocument();
    // 注册关闭时如实说明（不自作主张显示注册入口）
    expect(screen.getByText(/注册已关闭/)).toBeInTheDocument();
  });

  it("云端 + 无账户 → 显示初始化账户（否则用户没有账户可登）", async () => {
    stubFetch({
      "/api/meta": {
        body: {
          version: "0.0.1",
          localMode: false,
          authRequired: true,
          registerOpen: false,
          needsBootstrap: true,
          userCount: 0,
        },
      },
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "初始化账户" })).toBeInTheDocument();
    expect(screen.getByText(/首次部署/)).toBeInTheDocument();
  });

  it("本地模式 → 不需要登录，直接进入控制台", async () => {
    stubFetch({
      "/api/meta": {
        body: {
          version: "0.0.1",
          localMode: true,
          authRequired: false,
          registerOpen: false,
          needsBootstrap: false,
          userCount: null,
        },
      },
      "/api/auth/me": { body: { ...ACCOUNT, isLocal: true, via: "local" } },
      "/api/account/overview": { body: OVERVIEW },
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "控制台" })).toBeInTheDocument();
    // 本地模式没有登出按钮（没有账户可登出）
    expect(screen.queryByRole("button", { name: "登出" })).not.toBeInTheDocument();
  });
});

describe("仪表盘统计口径", () => {
  async function renderDashboard() {
    stubFetch({
      "/api/meta": {
        body: {
          version: "0.0.1",
          localMode: true,
          authRequired: false,
          registerOpen: false,
          needsBootstrap: false,
          userCount: null,
        },
      },
      "/api/auth/me": { body: { ...ACCOUNT, isLocal: true, via: "local" } },
      "/api/account/overview": { body: OVERVIEW },
    });
    render(<App />);
    await screen.findByRole("heading", { name: "控制台" });
  }

  it("展示控制台的面板：账户资料 + 索引统计 + 使用次数 + 项目", async () => {
    await renderDashboard();
    // 页面标题是「控制台」，而面板名「账户资料」不受改名影响（TASK-086 §2）。
    expect(screen.getByRole("heading", { name: "账户资料" })).toBeInTheDocument();
    expect(screen.getByText("成功次数")).toBeInTheDocument();
    expect(screen.getByText("失败次数")).toBeInTheDocument();
    // "平均耗时"在索引与用量两个面板都出现，因此按数量与数值断言（索引 avg = 61.0 s）
    expect(screen.getAllByText("平均耗时")).toHaveLength(2);
    expect(screen.getByText("占用内存")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument(); // succeeded
    expect(screen.getByText("1m 1s")).toBeInTheDocument(); // avg = 61000ms
    expect(screen.getByText("12.0 MiB")).toBeInTheDocument(); // disk
    expect(screen.getByText(/仅统计成功/)).toBeInTheDocument();
  });

  it("未测量的引用覆盖率显示“尚未测量”而不是 0", async () => {
    await renderDashboard();
    expect(screen.getByText(/尚未测量/)).toBeInTheDocument();
  });

  it("不再有索引记录面板，但项目面板保留（TASK-086 §3）", async () => {
    await renderDashboard();

    // 删掉的那块：它的标题、「查看全部历史」链接与那条运行记录都不该再现。
    // （历史页的「索引记录」页签是**另一个**文案，不受影响，由 HistoryPage 的测试覆盖。）
    expect(screen.queryByRole("heading", { name: /最近索引/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "查看全部历史" })).not.toBeInTheDocument();
    expect(screen.queryByText("336/338 文件 · ", { exact: false })).not.toBeInTheDocument();

    // 用户明确要求保留「项目」面板（那条记录在此表里仍然可见）。
    expect(screen.getByRole("heading", { name: "项目" })).toBeInTheDocument();
    expect(screen.getByText("demo")).toBeInTheDocument();

    // 未接 LLM 的引用覆盖率仍如实显示"尚未测量"。
    expect(screen.getByText(/尚未测量/)).toBeInTheDocument();
  });
});

describe("登录交互", () => {
  it("登录失败展示服务端文案与下一步", async () => {
    stubFetch({
      "/api/meta": {
        body: {
          version: "0.0.1",
          localMode: false,
          authRequired: true,
          registerOpen: false,
          needsBootstrap: false,
          userCount: 1,
        },
      },
      "/api/auth/me": {
        status: 401,
        body: { error: { code: "unauthorized", message: "缺少或无效的凭据" } },
      },
      "/api/auth/login": {
        status: 401,
        body: { error: { code: "unauthorized", message: "账户名或密码不正确" } },
      },
    });
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole("heading", { name: "登录" });

    await user.type(screen.getByLabelText("账户"), "owner");
    await user.type(screen.getByLabelText("密码"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(screen.getByText("账户名或密码不正确")).toBeInTheDocument();
    });
    expect(screen.getByText("unauthorized")).toBeInTheDocument();
  });
});
