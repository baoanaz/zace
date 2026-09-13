/**
 * Playground：提交 → 渲染服务端 markdown + meta 面板；Deep 的降级状态必须显著。
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PlaygroundPage } from "./PlaygroundPage";

const MARKDOWN = [
  "## Relevant Context",
  "### Code",
  "[E1] SessionStore.refresh_token — src/session.py:1-9",
].join("\n");

const META = {
  projectId: "p1",
  query: "令牌过期",
  mode: "fast",
  checkpointId: null,
  answerable: true,
  confidence: "medium",
  channelsUsed: ["bm25", "vector"],
  degraded: false,
  degradedReason: null,
  candidateCount: 7,
  freshness: { indexedAt: 1789096917, staleFiles: [], indexingFiles: [] },
  budget: { usedTokens: 605, hardCap: 10000, truncated: false, omittedCount: 0 },
  evidenceCount: 1,
  docsCount: 1,
  flowsCount: 0,
  missingEvidence: [],
  pack: null,
};

function stubFetch(routes: Record<string, unknown>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push({ url, init });
    for (const [key, value] of Object.entries(routes)) {
      if (url.includes(key)) {
        return new Response(JSON.stringify(value), { status: 200 });
      }
    }
    return new Response(JSON.stringify({ error: { code: "not_found", message: "no route" } }), {
      status: 404,
    });
  });
  vi.stubGlobal("fetch", mock);
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("PlaygroundPage", () => {
  it("Fast 提交后渲染服务端 markdown 与 meta 面板", async () => {
    const fetchCalls = stubFetch({
      "/api/projects": [{ projectId: "p1", displayName: "demo", indexProgress: { state: "done" } }],
      "/api/query/search": { markdown: MARKDOWN, meta: META },
    });
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <PlaygroundPage />
      </MemoryRouter>,
    );

    const textarea = await screen.findByPlaceholderText(/令牌过期后在哪里刷新/);
    await user.type(textarea, "令牌过期");
    await user.click(screen.getByRole("button", { name: "检索" }));

    // 文本会出现两次：一处是服务端 Markdown 的渲染结果，一处是调试用的原始 JSON 面板。
    const hits = await screen.findAllByText(/SessionStore.refresh_token/);
    expect(hits.length).toBeGreaterThanOrEqual(1);
    expect(document.querySelector(".zace-markdown")?.textContent).toContain(
      "SessionStore.refresh_token",
    );
    // meta 面板字段如实展示（不推导）
    expect(screen.getByText("bm25, vector")).toBeInTheDocument();
    expect(screen.getByText("605")).toBeInTheDocument();

    const body = JSON.parse(String(fetchCalls.at(-1)?.init?.body ?? "{}"));
    expect(body).toMatchObject({ projectId: "p1", query: "令牌过期" });
  });

  it("Deep 的 degraded 状态显著展示，不包装成答案", async () => {
    stubFetch({
      "/api/projects": [{ projectId: "p1", displayName: "demo", indexProgress: { state: "done" } }],
      "/api/query/ask": {
        status: "degraded",
        answer: `${MARKDOWN}\n\n（降级说明）`,
        evidenceSummary: [
          { id: "E1", type: "code", path: "src/session.py", lines: [1, 9], tier: 1, score: 0.9 },
        ],
        meta: { ...META, mode: "fast", degraded: true, degradedReason: "Deep 模式尚未接入" },
      },
    });
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <PlaygroundPage />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole("button", { name: "Deep（ask）" }));
    await user.type(await screen.findByPlaceholderText(/令牌过期后在哪里刷新/), "令牌过期");
    await user.click(screen.getByRole("button", { name: "提问" }));

    expect(await screen.findByText(/degraded（降级包，不是 LLM 答案）/)).toBeInTheDocument();
    expect(screen.getByText(/不是\*\*LLM 产生的答案|\*\*不是\*\* LLM 产生的答案/)).toBeInTheDocument();
    expect(screen.getByText("E1")).toBeInTheDocument();
  });

  it("空索引错误展示 code 与下一步指引", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/api/projects")) {
          return new Response(
            JSON.stringify([
              { projectId: "p1", displayName: "demo", indexProgress: { state: "running" } },
            ]),
            { status: 200 },
          );
        }
        return new Response(
          JSON.stringify({
            error: { code: "index_in_progress", message: "索引尚未就绪：从未同步过" },
          }),
          { status: 409 },
        );
      }),
    );
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <PlaygroundPage />
      </MemoryRouter>,
    );

    await user.type(await screen.findByPlaceholderText(/令牌过期后在哪里刷新/), "q");
    await user.click(screen.getByRole("button", { name: "检索" }));

    await waitFor(() => {
      expect(screen.getByText("index_in_progress")).toBeInTheDocument();
    });
    expect(screen.getByText(/等索引完成/)).toBeInTheDocument();
  });
});
