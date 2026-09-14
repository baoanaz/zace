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
    // 两种记录都在同一张表里（这是用户要求的核心：不用切页签）。
    // TASK-100（用户 2026-09-14）：「类型」列改为显示**实际工具名**。
    expect(within(table).getByText("仓库初始化")).toBeInTheDocument();
    expect(within(table).getByText("search_context")).toBeInTheDocument();
    // 项目与查询分列。
    expect(within(table).getByText("项目")).toBeInTheDocument();
    expect(within(table).getByText("查询")).toBeInTheDocument();
    // 两行都属于 demo 项目，因此项目名出现两次（这正是分列后的正确表现）。
    expect(within(table).getAllByText("demo").length).toBe(2);
    expect(within(table).getByText("令牌在哪里刷新")).toBeInTheDocument();
    // 体量：初始化看 chunks，检索看 token。
    expect(within(table).getByText("4210 chunks")).toBeInTheDocument();
    expect(within(table).getByText("576 token")).toBeInTheDocument();
  });

  it("仓库初始化那行的「查询」列为 —（它不是提问，没有输入文本）", async () => {
    stubAll();
    renderPage(<HistoryPage />);

    const table = await screen.findByRole("table");
    const initRow = within(table)
      .getAllByRole("row")
      .find((row) => row.textContent?.includes("仓库初始化"))!;
    const cells = within(initRow).getAllByRole("cell");
    // 列序：时间 0 / 类型 1 / 项目 2 / 查询 3 / trace id 4 / 结果 5 / 耗时 6 / 体量 7 / 查看 8
    expect(cells[2]).toHaveTextContent("demo");
    expect(cells[3]).toHaveTextContent("—");
  });

  it("按时间倒序：较新的记录排在前面", async () => {
    // 初始化在 1789305566（与检索同一秒）——改早一点，让顺序确定。
    stubAll([record], [{ ...RUN, finishedAt: 1789305000 }]);
    renderPage(<HistoryPage />);

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1); // 去掉表头
    expect(rows.length).toBe(2);
    // 第一行必须是较新的那条（检索，1789305566 > 1789305000）。
    expect(within(rows[0]!).getByText("search_context")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("仓库初始化")).toBeInTheDocument();
  });

  it("「查看」按钮弹出两个可滚动代码块（Tool 输入 / 输出）", async () => {
    stubAll();
    renderPage(<HistoryPage />);

    const table = await screen.findByRole("table");
    const searchRow = within(table)
      .getAllByRole("row")
      .find((row) => row.textContent?.includes("令牌在哪里刷新"))!;

    await userEvent.click(within(searchRow).getByRole("button", { name: "查看" }));

    const dialog = await screen.findByRole("dialog");
    // 用户 2026-09-14 定稿：**上下两个块**——Tool 输入 / Tool 输出（不再单列 LLM 答案）。
    expect(within(dialog).getByText("Tool 输入")).toBeInTheDocument();
    expect(within(dialog).getByText("Tool 输出")).toBeInTheDocument();
    expect(within(dialog).queryByText("LLM 答案")).not.toBeInTheDocument();
    // 代码块是 <pre>（可滚动容器）。
    const pres = dialog.querySelectorAll("pre");
    expect(pres.length).toBe(2);
    expect(pres[0]?.textContent).toContain("令牌在哪里刷新");
    expect(pres[0]?.className).toContain("overflow-auto");
    // 底层元信息（用户："其他底层有证据数量啊，文档条数这种信息"）。
    expect(within(dialog).getByText("证据条数")).toBeInTheDocument();
    expect(within(dialog).getByText("文档条数")).toBeInTheDocument();
    // 诚实边界：测试夹具的 answerText 为 null，弹窗要如实说明这条是 search（不调 LLM），
    // 而不是拿证据清单冒充 LLM 输出。
    expect(within(dialog).getByText(/search_context 不调用 LLM|未调用 LLM|调用了 LLM 但失败/)).toBeInTheDocument();
  });

  it("弹窗标题不重复输入内容（用户：太长了）", async () => {
    stubAll();
    renderPage(<HistoryPage />);

    const table = await screen.findByRole("table");
    const searchRow = within(table)
      .getAllByRole("row")
      .find((row) => row.textContent?.includes("令牌在哪里刷新"))!;
    await userEvent.click(within(searchRow).getByRole("button", { name: "查看" }));

    const dialog = await screen.findByRole("dialog");
    const heading = within(dialog).getByRole("heading");
    // 标题只写工具名 + 项目名，**不含**查询全文。
    expect(heading.textContent).toContain("search_context");
    expect(heading.textContent).toContain("demo");
    expect(heading.textContent).not.toContain("令牌在哪里刷新");
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

describe("§需求4 刷新（TASK-100 用户 2026-09-14 定稿）", () => {
  it("页头排版：标题 + 刷新按钮 + 数据更新于（同一个左侧分组）", async () => {
    stubAll();
    renderPage(<HistoryPage />);

    await screen.findByRole("table");
    expect(screen.getByRole("button", { name: "刷新" })).toBeInTheDocument();
    // 首次加载成功后显示时间戳（用户要求短格式「数据更新于：HH:MM:SS」）。
    expect(await screen.findByText(/数据更新于：/)).toBeInTheDocument();
  });

  it("自动刷新常开且**不提供开关**（用户定稿：不让用户管这个概念）", async () => {
    stubAll();
    renderPage(<HistoryPage />);

    await screen.findByRole("table");
    // 页面上不应再有 switch 控件或「自动刷新」字样。
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByText("自动刷新")).not.toBeInTheDocument();
  });

  it("刷新按钮点击后重新请求（手动刷新仍可用）", async () => {
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
    const before = calls.filter((url) => url.includes("usage/summary")).length;

    await userEvent.click(screen.getByRole("button", { name: "刷新" }));

    await waitFor(() => {
      const after = calls.filter((url) => url.includes("usage/summary")).length;
      expect(after).toBeGreaterThan(before);
    });
  });

  /**
   * **用户报的\"低概率全白\"的回归用例**（2026-09-14）：
   * 切时间档位时旧表格必须留在屏幕上，不能被 LoadingBlock 换掉。
   *
   * 根因是首屏 effect 一律走非静默路径 → `runs`/`usage` 被置空 → `rows` 为 null →
   * 渲染 LoadingBlock。修复后 `load` 按\"屏幕上是否已有数据\"决定静默与否。
   */
  it("切时间档位时不白屏：表格在整个切换过程中都留在 DOM 里", async () => {
    stubAll();
    renderPage(<HistoryPage />);

    const table = await screen.findByRole("table");
    expect(table).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "近 7 天" }));

    // 切换过程中**任何时刻**都不应出现加载态（表格必须一直在）。
    // 用 waitFor 循环观察：若中途被 LoadingBlock 替换，这里会抓到。
    let sawLoading = false;
    const observer = setInterval(() => {
      if (screen.queryByText("加载中…") !== null) sawLoading = true;
    }, 1);
    await waitFor(() => {
      expect(screen.getByRole("table")).toBeInTheDocument();
    });
    clearInterval(observer);
    expect(sawLoading).toBe(false);
    expect(screen.queryByText("加载中…")).not.toBeInTheDocument();
  });

  it("刷新失败时不清空已有数据（只显示错误横幅）", async () => {
    let failNext = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("usage/summary") && failNext) {
          throw new TypeError("Failed to fetch");
        }
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

    failNext = true;
    await userEvent.click(screen.getByRole("button", { name: "刷新" }));

    await waitFor(() => {
      expect(screen.getByText(/连不上 zace-service/)).toBeInTheDocument();
    });
    // 表格仍在（清空会让"网络抖一下"看起来像"记录全没了"）。
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});
