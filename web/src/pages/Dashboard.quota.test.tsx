/**
 * TASK-094 前端验收：§A 项目占用列 / §B4 配额条 / §C 历史页 trace id / §D 删除入口。
 *
 * 四条纪律对应四组用例：
 *
 * 1. **§D 取消不发请求**（`test_..._cancel_...`）：断言 `fetch` 里**没有** DELETE——这是
 *    最容易写错的一条（把删除直接挂在按钮上就会漏掉确认）。
 * 2. **§D 确认才删 + 删完刷新**：断言 DELETE 被调、且之后重新拉了列表（项目消失）。
 * 3. **§D 失败如实报错**：404 不静默吞掉，且**不把整页换成错误页**（项目表仍在）。
 * 4. **§A/§C 口径诚实**：后端未给 `diskBytes` → `—`；旧记录没有 `requestId` → `—`。
 *
 * 渲染一律经 `MemoryRouter`：两个页面在空态/提示里用了 `<Link>`（跳到接入指南），
 * 没有 Router 上下文会直接抛错——那是测试环境缺件，不是产品缺陷。
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DashboardPage } from "./DashboardPage";
import { HistoryPage } from "./HistoryPage";

/** 渲染页面（带 Router：页面在空态与提示里用了 `<Link>`）。 */
function renderPage(node: React.ReactElement) {
  return render(<MemoryRouter>{node}</MemoryRouter>);
}

const ACCOUNT = { userId: "u1", name: "owner", createdAt: 1789300000, isLocal: true, via: "local" };

/** 一个带 `diskBytes` 的项目（§A 的新字段）。 */
const PROJECT = {
  projectId: "p1",
  displayName: "demo",
  attachedRoot: "/repo/demo",
  indexProgress: { state: "done" },
  sync: { filesIndexed: 287, chunks: 3416 },
  diskBytes: 30_408_704, // 29.0 MiB
};

type Route = { status?: number; body?: unknown };
type Call = { url: string; method: string };

/** 极简 fetch 桩：按 URL 片段匹配；未匹配 → 404。记录方法以便断言"没有发 DELETE"。 */
function stubFetch(routes: Record<string, Route>) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push({ url, method });
      for (const [key, value] of Object.entries(routes)) {
        if (url.includes(key)) {
          if (method === "DELETE" && value.status === 204) {
            return new Response(null, { status: 204 });
          }
          return new Response(JSON.stringify(value.body ?? null), { status: value.status ?? 200 });
        }
      }
      return new Response(JSON.stringify({ error: { code: "not_found", message: "no route" } }), {
        status: 404,
      });
    }),
  );
  return calls;
}

function overview(overrides: Record<string, unknown> = {}) {
  return {
    account: { name: "owner", createdAt: 1789300000, isLocal: true, projectCount: 1 },
    index: {
      total: 1,
      succeeded: 1,
      failed: 0,
      avgDurationMs: 1000,
      minDurationMs: 800,
      maxDurationMs: 1200,
      lastRunAt: 1789305566,
      lastState: "done",
      diskBytes: 30_408_704,
      recent: [],
    },
    usage: {
      projectId: null,
      days: 30,
      total: 1,
      succeeded: 1,
      insufficient: 0,
      failed: 0,
      avgLatencyMs: 12,
      p95LatencyMs: 12,
      confidenceDistribution: {},
      citationCoverageAvg: null,
      topQueries: [],
      recent: [],
    },
    projects: [PROJECT],
    days: 30,
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// --------------------------------------------------------------------------- §A 占用列

describe("§A 项目占用可见", () => {
  it("项目表格显示每项目占用（复用 formatBytes 的 MiB 口径）", async () => {
    stubFetch({ "/api/account/overview": { body: overview() } });

    renderPage(<DashboardPage account={ACCOUNT} />);

    const cell = await screen.findByTestId("disk-p1");
    expect(cell).toHaveTextContent("29.0 MiB");
    expect(screen.getByRole("columnheader", { name: "占用" })).toBeInTheDocument();
  });

  it("后端未提供 diskBytes 时显示 —（不把未测量伪装成 0 B）", async () => {
    stubFetch({
      "/api/account/overview": {
        body: overview({ projects: [{ ...PROJECT, diskBytes: null }] }),
      },
    });

    renderPage(<DashboardPage account={ACCOUNT} />);

    const cell = await screen.findByTestId("disk-p1");
    expect(cell).toHaveTextContent("—");
    expect(cell).not.toHaveTextContent("0 B");
  });

  it("diskBytes 未提供时也不显示 0 B（旧版服务的兼容路径）", async () => {
    const withoutDisk = { ...PROJECT };
    delete (withoutDisk as { diskBytes?: number }).diskBytes;
    stubFetch({ "/api/account/overview": { body: overview({ projects: [withoutDisk] }) } });

    renderPage(<DashboardPage account={ACCOUNT} />);

    expect(await screen.findByTestId("disk-p1")).toHaveTextContent("—");
  });
});

// --------------------------------------------------------------------------- §B4 配额条

describe("§B4 存储配额展示", () => {
  it("有上限时显示已用/上限与百分比", async () => {
    stubFetch({
      "/api/account/overview": {
        body: overview({
          storage: {
            status: "warning",
            warnRatio: 0.8,
            projectId: "p1",
            user: {
              usedBytes: 1_610_612_736,
              limitBytes: 2_147_483_648,
              ratio: 0.75,
              status: "warning",
              unlimited: false,
            },
            project: { usedBytes: 0, limitBytes: 524_288_000, ratio: 0, status: "ok", unlimited: false },
          },
        }),
      },
    });

    renderPage(<DashboardPage account={ACCOUNT} />);

    const quota = await screen.findByTestId("storage-quota");
    expect(quota).toHaveTextContent("1.50 GiB");
    expect(quota).toHaveTextContent("2.00 GiB");
    expect(quota).toHaveTextContent("75%");
  });

  it("不限（limitBytes=0）时只显示已用，不显示百分比与上限字样", async () => {
    stubFetch({
      "/api/account/overview": {
        body: overview({
          storage: {
            status: "ok",
            warnRatio: 0.8,
            projectId: "p1",
            user: {
              usedBytes: 29 * 1024 * 1024,
              limitBytes: 0,
              ratio: null,
              status: "ok",
              unlimited: true,
            },
            project: { usedBytes: 0, limitBytes: 0, ratio: null, status: "ok", unlimited: true },
          },
        }),
      },
    });

    renderPage(<DashboardPage account={ACCOUNT} />);

    const quota = await screen.findByTestId("storage-quota");
    expect(quota).toHaveTextContent("未设上限");
    expect(quota).not.toHaveTextContent("上限 0 B");
  });

  it("后端未提供 storage 时不渲染配额条（旧版服务）", async () => {
    stubFetch({ "/api/account/overview": { body: overview() } });

    renderPage(<DashboardPage account={ACCOUNT} />);

    await screen.findByTestId("disk-p1");
    expect(screen.queryByTestId("storage-quota")).not.toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------- §D 删除入口

describe("§D 项目删除入口", () => {
  it("点击删除弹出二次确认，文案说清后果，且此刻还没有发 DELETE", async () => {
    const calls = stubFetch({ "/api/account/overview": { body: overview() } });
    const user = userEvent.setup();

    renderPage(<DashboardPage account={ACCOUNT} />);
    await screen.findByTestId("disk-p1");

    await user.click(screen.getByRole("button", { name: "删除" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/删除项目 demo/)).toBeInTheDocument();
    expect(within(dialog).getByText(/全部索引数据/)).toBeInTheDocument();
    expect(within(dialog).getByText(/源码文件不受影响/)).toBeInTheDocument();
    // 关键：确认之前绝不能已经删了。
    expect(calls.filter((call) => call.method === "DELETE")).toHaveLength(0);
  });

  it("取消 → 不发请求（断言无 DELETE）", async () => {
    const calls = stubFetch({ "/api/account/overview": { body: overview() } });
    const user = userEvent.setup();

    renderPage(<DashboardPage account={ACCOUNT} />);
    await screen.findByTestId("disk-p1");

    await user.click(screen.getByRole("button", { name: "删除" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "取消" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(calls.filter((call) => call.method === "DELETE")).toHaveLength(0);
    expect(calls.filter((call) => call.method === "GET")).toHaveLength(1); // 只拉过一次概览
    // 项目行仍在（没有本地删行）。
    expect(screen.getByTestId("disk-p1")).toBeInTheDocument();
  });

  it("确认 → 调 DELETE /api/projects/{id}，并刷新列表使该项目消失", async () => {
    const calls = stubFetch({
      "/api/account/overview": { body: overview() },
      "/api/projects/p1": { status: 204 },
    });
    const user = userEvent.setup();

    // 模拟后端状态：一旦收到 DELETE，后续概览就返回空列表（“真的删掉了”）。
    const empty = overview({ projects: [], account: { ...overview().account, projectCount: 0 } });
    let deleted = false;
    let overviewCalls = 0;
    const original = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/account/overview")) {
        overviewCalls += 1;
        if (deleted) {
          return new Response(JSON.stringify(empty), { status: 200 });
        }
      }
      if (method === "DELETE") {
        deleted = true;
      }
      return original(input as RequestInfo, init);
    }) as typeof fetch;

    renderPage(<DashboardPage account={ACCOUNT} />);
    await screen.findByTestId("disk-p1");
    const before = overviewCalls;

    await user.click(screen.getByRole("button", { name: "删除" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "删除索引数据" }));

    await waitFor(() => {
      expect(screen.getByText(/还没有项目/)).toBeInTheDocument();
    });
    const deletes = calls.filter((call) => call.method === "DELETE");
    expect(deletes).toHaveLength(1);
    expect(deletes[0]?.url).toContain("/api/projects/p1");
    // 删除后**重新拉取**（不是本地滤掉）：概览请求次数确实增加了。
    expect(overviewCalls).toBeGreaterThan(before);
  });

  it("删除失败（404）→ 如实报错，不静默吞掉，且页面其余部分仍可用", async () => {
    stubFetch({
      "/api/account/overview": { body: overview() },
      "/api/projects/p1": {
        status: 404,
        body: { error: { code: "project_not_found", message: "项目不存在：p1" } },
      },
    });
    const user = userEvent.setup();

    renderPage(<DashboardPage account={ACCOUNT} />);
    await screen.findByTestId("disk-p1");

    await user.click(screen.getByRole("button", { name: "删除" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "删除索引数据" }));

    await waitFor(() => {
      expect(screen.getByText("项目不存在：p1")).toBeInTheDocument();
    });
    expect(screen.getByText("project_not_found")).toBeInTheDocument();
    // 不是整页错误：项目表仍在，用户可以重试或取消。
    expect(screen.getByTestId("disk-p1")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("权限/网络类错误也如实展示（不静默）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/api/account/overview")) {
          return new Response(JSON.stringify(overview()), { status: 200 });
        }
        if ((init?.method ?? "GET").toUpperCase() === "DELETE") {
          throw new TypeError("Failed to fetch");
        }
        return new Response("null", { status: 200 });
      }),
    );
    const user = userEvent.setup();

    renderPage(<DashboardPage account={ACCOUNT} />);
    await screen.findByTestId("disk-p1");
    await user.click(screen.getByRole("button", { name: "删除" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "删除索引数据" }));

    await waitFor(() => {
      expect(screen.getByText(/连不上 zace-service/)).toBeInTheDocument();
    });
  });
});

// --------------------------------------------------------------------------- §C trace id

describe("§C 历史页 trace id", () => {
  const record = {
    queryId: 1,
    projectId: "p1",
    mode: "fast",
    query: "令牌在哪里刷新",
    answerable: true,
    confidence: "high",
    degraded: false,
    latencyMs: 137,
    evidenceCount: 3,
    docsCount: 1,
    usedTokens: 576,
    citationCoverage: null,
    requestId: "trace-094-abcdef",
    createdAt: 1789305566,
  };

  function usage(records: unknown[]) {
    return {
      projectId: null,
      days: 30,
      total: records.length,
      succeeded: records.length,
      insufficient: 0,
      failed: 0,
      avgLatencyMs: 137,
      p95LatencyMs: 137,
      confidenceDistribution: {},
      citationCoverageAvg: null,
      topQueries: [],
      recent: records,
    };
  }

  async function openUsageTab() {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/api/projects")) {
          return new Response(JSON.stringify([PROJECT]), { status: 200 });
        }
        if (url.includes("/index-runs")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response(JSON.stringify(usage([record])), { status: 200 });
      }),
    );
    renderPage(<HistoryPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "使用记录" }));
    return user;
  }

  it("每条记录显示 trace id，可复制（CopyButton）", async () => {
    await openUsageTab();

    const table = await screen.findByRole("table");
    expect(within(table).getByText("trace id")).toBeInTheDocument();
    expect(within(table).getByText("trace-094-abcdef")).toBeInTheDocument();
    expect(within(table).getByRole("button", { name: "复制" })).toBeInTheDocument();
    // 说明文案要能指导用户"下一步做什么"。
    expect(screen.getByText(/报给管理员/)).toBeInTheDocument();
  });

  it("旧记录没有 requestId → 显示 —，不编造一个 id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/api/projects")) {
          return new Response(JSON.stringify([PROJECT]), { status: 200 });
        }
        if (url.includes("/index-runs")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        return new Response(JSON.stringify(usage([{ ...record, requestId: null }])), {
          status: 200,
        });
      }),
    );
    const user = userEvent.setup();
    renderPage(<HistoryPage />);
    await user.click(await screen.findByRole("button", { name: "使用记录" }));

    const table = await screen.findByRole("table");
    expect(within(table).queryByText(/trace-094/)).not.toBeInTheDocument();
    expect(within(table).queryByRole("button", { name: "复制" })).not.toBeInTheDocument();
    expect(within(table).getByText("—")).toBeInTheDocument();
  });
});
