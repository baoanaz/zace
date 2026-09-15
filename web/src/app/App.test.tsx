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
          registerOpen: true,
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
    expect(screen.getByRole("button", { name: "没有账户？注册" })).toBeInTheDocument();
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
          // TASK-100 §需求9：控制台的「服务模型」卡读 config。
          config: {
            embedding: {
              mode: "api",
              configured: true,
              missingEnv: [],
              model: "voyage-4-lite",
              provider: "voyage",
              dim: 1024,
            },
            llm: { configured: true, apiKeyConfigured: true, missingEnv: [], model: "deepseek-flash" },
          },
        },
      },
      "/api/auth/me": { body: { ...ACCOUNT, isLocal: true, via: "local" } },
      "/api/account/overview": { body: OVERVIEW },
    });
    render(<App />);
    await screen.findByRole("heading", { name: "控制台" });
  }

  it("展示控制台的面板：账户资料 + 服务模型 + 工具调用（TASK-100 精简后）", async () => {
    await renderDashboard();
    // 页面标题是「控制台」，而面板名「账户资料」不受改名影响（TASK-086 §2）。
    expect(screen.getByRole("heading", { name: "账户资料" })).toBeInTheDocument();
    // TASK-100 §需求9：服务模型卡从设置页移来（LLM + embedding 的最小必要信息）。
    expect(screen.getByRole("heading", { name: "服务模型" })).toBeInTheDocument();

    // TASK-100 §需求3：用户定稿的 7 个数据（三行，虚线分隔）。
    expect(screen.getByRole("heading", { name: /工具调用/ })).toBeInTheDocument();
    // 行标签（左侧分类）。
    expect(screen.getByText("仓库初始化")).toBeInTheDocument();
    expect(screen.getByText("检索")).toBeInTheDocument();
    expect(screen.getByText("Tool 调用")).toBeInTheDocument();
    // 指标名（每行的右侧）。"次数"与"平均耗时"在初始化/检索两行都出现，故用 getAllByText。
    expect(screen.getAllByText("次数").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("平均耗时").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("最快 / 最慢")).toBeInTheDocument();
    expect(screen.getByText("成功")).toBeInTheDocument();
    expect(screen.getByText("失败")).toBeInTheDocument();

    // 用户要求：不要解释性文字（"首次调用时索引仓库"、"仅统计成功"等）。
    expect(screen.queryByText("首次调用时索引仓库")).not.toBeInTheDocument();
    expect(screen.queryByText("仅统计成功")).not.toBeInTheDocument();
    expect(screen.queryByText("每次提问算一次")).not.toBeInTheDocument();
  });

  it("TASK-100 §需求3：控制台不再出现内部概念（索引/检索）的统计面板", async () => {
    await renderDashboard();

    // 用户不知道"索引"与"使用"的区别，只关心 Tool 调用的成功/失败/耗时。
    expect(screen.queryByRole("heading", { name: /^索引（近/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^使用次数/ })).not.toBeInTheDocument();
    // "占用内存"、"索引总次数"、"P95 耗时" 等细节数字也不该在控制台上。
    expect(screen.queryByText("占用内存")).not.toBeInTheDocument();
    expect(screen.queryByText("索引总次数")).not.toBeInTheDocument();
    expect(screen.queryByText("P95 耗时")).not.toBeInTheDocument();
  });

  it("TASK-100 §需求4：项目表已移到独立项目页，控制台不再有项目面板", async () => {
    await renderDashboard();

    // TASK-086 §3 删掉的「最近索引」面板仍然不存在（那条约束继续有效）。
    expect(screen.queryByRole("heading", { name: /最近索引/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "查看全部历史" })).not.toBeInTheDocument();
    expect(screen.queryByText("336/338 文件 · ", { exact: false })).not.toBeInTheDocument();

    // TASK-100：项目面板**移出**控制台（→ `/projects`），不再是本页的一节。
    expect(screen.queryByRole("heading", { name: "项目" })).not.toBeInTheDocument();
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
