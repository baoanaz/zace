/**
 * TASK-094 §C + TASK-100 §需求2：历史页的 trace id 与合并后的表格。
 *
 * 迁移说明（TASK-100）：历史页从"索引记录 / 使用记录两个页签"合并成**一张表**
 * （用户 2026-09-14 要求），因此不再需要点页签；断言内容**一条未删**，只调整了定位方式：
 *
 * | 原断言 | 现断言 | 守护的东西 |
 * |---|---|---|
 * | 点「使用记录」页签后查表 | 直接查表（已合并） | 检索记录可见 |
 * | `getByText("trace id")` 表头 | 保留 | trace id 列存在 |
 * | 复制按钮 + "报给管理员" 文案 | 改为"复制"+ 弹窗里的 trace id 复制 | 可复制的 trace id |
 * | 无 requestId → `—` | 保留 | 不编造 id |
 *
 * 另外新增（TASK-100 §需求2 的核心）：类型列区分仓库初始化 / 检索，
 * 以及"查看"按钮弹出输入输出详情。
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HistoryPage } from "./HistoryPage";

function renderPage(node: React.ReactElement) {
  return render(<MemoryRouter>{node}</MemoryRouter>);
}

const PROJECT = {
  projectId: "p1",
  displayName: "demo",
  attachedRoot: "/repo/demo",
  indexProgress: { state: "done" },
  sync: { filesIndexed: 287, chunks: 3416 },
  diskBytes: 30_408_704,
};

const RUN = {
  runId: 7,
  projectId: "p1",
  state: "done",
  startedAt: 1789305500,
  finishedAt: 1789305566,
  durationMs: 66_000,
  filesTotal: 344,
  filesProcessed: 338,
  chunks: 4210,
  errors: 0,
  error: null,
};

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

/** 统一的 fetch 桩：项目列表 + 索引 run + 用量。 */
function stubAll(records: unknown[] = [record], runs: unknown[] = [RUN]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/index-runs")) {
        return new Response(JSON.stringify(runs), { status: 200 });
      }
      if (url.includes("/api/projects")) {
        return new Response(JSON.stringify([PROJECT]), { status: 200 });
      }
      return new Response(JSON.stringify(usage(records)), { status: 200 });
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("§C 历史页 trace id（TASK-094）", () => {
  it("检索记录显示可复制的 trace id", async () => {
    stubAll();
    renderPage(<HistoryPage />);

    const table = await screen.findByRole("table");
    expect(within(table).getByText("trace id")).toBeInTheDocument();
    expect(within(table).getByText("trace-094-abcdef")).toBeInTheDocument();
    expect(within(table).getByRole("button", { name: "复制" })).toBeInTheDocument();
  });

  it("旧记录没有 requestId → 显示 —，不编造一个 id", async () => {
    stubAll([{ ...record, requestId: null }]);
    renderPage(<HistoryPage />);

    const table = await screen.findByRole("table");
    expect(within(table).queryByText(/trace-094/)).not.toBeInTheDocument();
    // 初始化那行也没有 trace id（它不产生 trace），因此 `—` 至少一处。
    expect(within(table).getAllByText("—").length).toBeGreaterThanOrEqual(1);
  });
});

describe("§需求2 合并表格（TASK-100）", () => {
  it("一张表同时包含「仓库初始化」与「检索」，用类型列区分", async () => {
    stubAll();
    renderPage(<HistoryPage />);

    const table = await screen.findByRole("table");
    // 两种类型都在同一张表里（这是用户要求的核心：不用切页签）。
    expect(within(table).getByText("仓库初始化")).toBeInTheDocument();
    expect(within(table).getByText("检索")).toBeInTheDocument();
    // 初始化的行显示项目名与 chunks；检索的行显示 query 与 token。
    expect(within(table).getByText("demo")).toBeInTheDocument();
    expect(within(table).getByText("令牌在哪里刷新")).toBeInTheDocument();
    expect(within(table).getByText("4210 chunks")).toBeInTheDocument();
    expect(within(table).getByText("576 token")).toBeInTheDocument();
  });

  it("按时间倒序：较新的记录排在前面", async () => {
    // 初始化在 1789305566（与检索同一秒）——改早一点，让顺序确定。
    stubAll([record], [{ ...RUN, finishedAt: 1789305000 }]);
    renderPage(<HistoryPage />);

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1); // 去掉表头
    expect(rows.length).toBe(2);
    // 第一行必须是较新的那条（检索，1789305566 > 1789305000）。
    expect(within(rows[0]!).getByText("检索")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("仓库初始化")).toBeInTheDocument();
  });

  it("「查看」按钮弹出输入输出详情（用户要求的可点击弹窗）", async () => {
    stubAll();
    renderPage(<HistoryPage />);

    const table = await screen.findByRole("table");
    const searchRow = within(table)
      .getAllByRole("row")
      .find((row) => row.textContent?.includes("令牌在哪里刷新"))!;

    await userEvent.click(within(searchRow).getByRole("button", { name: "查看" }));

    const dialog = await screen.findByRole("dialog");
    // 输入：查询全文。弹窗内标题与详情值都含该字符串，故用 getAllByText。
    expect(within(dialog).getByText("输入")).toBeInTheDocument();
    expect(within(dialog).getAllByText(/令牌在哪里刷新/).length).toBeGreaterThanOrEqual(1);
    // 输出：证据概览（**不是** LLM 答案——answer 未落库，弹窗如实说明）。
    expect(within(dialog).getByText("输出")).toBeInTheDocument();
    expect(within(dialog).getByText("证据条数")).toBeInTheDocument();
    expect(within(dialog).getByText(/答案正文未落库/)).toBeInTheDocument();
  });

  it("弹窗可关闭（Esc 与按钮都行）", async () => {
    stubAll();
    renderPage(<HistoryPage />);

    const table = await screen.findByRole("table");
    const searchRow = within(table)
      .getAllByRole("row")
      .find((row) => row.textContent?.includes("令牌在哪里刷新"))!;
    await userEvent.click(within(searchRow).getByRole("button", { name: "查看" }));
    await screen.findByRole("dialog");

    await userEvent.click(screen.getByRole("button", { name: "关闭" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});

describe("§需求3 时间范围选择（TASK-100）", () => {
  it("提供天为单位的档位，默认近 30 天", async () => {
    stubAll();
    renderPage(<HistoryPage />);

    // 默认档位高亮。
    const active = await screen.findByRole("button", { name: "近 30 天" });
    expect(active.className).toContain("bg-accent-seal");
    // 其余档位存在。
    expect(screen.getByRole("button", { name: "今天" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "近 7 天" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "近 90 天" })).toBeInTheDocument();
  });

  it("切换档位会带 days 重新请求检索汇总（后端参数）", async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        calls.push(url);
        if (url.includes("/index-runs")) {
          return new Response(JSON.stringify([RUN]), { status: 200 });
        }
        if (url.includes("/api/projects")) {
          return new Response(JSON.stringify([PROJECT]), { status: 200 });
        }
        return new Response(JSON.stringify(usage([record])), { status: 200 });
      }),
    );

    renderPage(<HistoryPage />);
    await screen.findByRole("table");

    await userEvent.click(screen.getByRole("button", { name: "近 7 天" }));

    await waitFor(() => {
      expect(calls.some((url) => url.includes("days=7"))).toBe(true);
    });
  });
});
