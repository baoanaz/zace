/**
 * 端到端测试：**真实 service + 真实页面**（TASK-070 §DoD 的第 3 条）。
 *
 * 默认跳过——它需要一个已索引的 zace-service。启用方式：
 *
 * ```bash
 * # 终端 A
 * export NO_PROXY=127.0.0.1,localhost
 * uv run zace-service local --repo <仓库> --data-root /tmp/zace-web-check/data --port 8787
 * # 终端 B（等索引完成）
 * cd web && ZACE_E2E=1 ZACE_E2E_BASE=http://127.0.0.1:8787 npx vitest run src/pages/e2e.test.tsx
 * ```
 *
 * 为什么值得单独一个文件：单元测试用的是 mock，只能证明"我按我以为的契约解析了"。
 * 这个文件证明的是"服务端实际返回的形状被页面正确渲染了"——契约对齐的唯一硬证据。
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { PlaygroundPage } from "./PlaygroundPage";

const enabled = process.env["ZACE_E2E"] === "1";
const base = process.env["ZACE_E2E_BASE"] ?? "http://127.0.0.1:8787";
const projectId = process.env["ZACE_E2E_PROJECT"] ?? "";
const query = process.env["ZACE_E2E_QUERY"] ?? "令牌过期后在哪里刷新？";

describe.skipIf(!enabled)("端到端（真实 service）", () => {
  it("真实检索结果能在 Playground 页面渲染出带行号的证据块", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={[`/playground?project=${projectId}`]}>
        <PlaygroundPage />
      </MemoryRouter>,
    );

    // 项目下拉框里应出现真实项目（projectId 或 displayName）。
    const select = await screen.findByRole("combobox", {}, { timeout: 10_000 });
    expect(select).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText(/令牌过期后在哪里刷新/);
    await user.type(textarea, query);
    await user.click(screen.getByRole("button", { name: "检索" }));

    // 文本会出现两次：服务端 Markdown 的渲染结果 + 调试用的原始 JSON 面板。
    await screen.findAllByText(/Relevant Context/, {}, { timeout: 30_000 });
    const markdown = document.querySelector(".zace-markdown")?.textContent ?? "";
    expect(markdown).toContain("Relevant Context");

    // 证据块必须带「文件:行号」——这是 ContextPack 的硬要求（手册 §4.1）。
    expect(markdown).toMatch(/\[E\d+\]/);
    expect(markdown).toMatch(/\.(py|md|rs|c|cpp|h):\d+(-\d+)?/);
  }, 60_000);

  it("真实服务可达（healthz 与 projects 的形状与类型声明一致）", async () => {
    const health = (await (await fetch(`${base}/healthz`)).json()) as Record<string, unknown>;
    expect(health["status"]).toBe("ok");
    expect(typeof health["localMode"]).toBe("boolean");
    expect(Array.isArray(health["projects"])).toBe(true);

    const projects = (await (await fetch(`${base}/api/projects`)).json()) as unknown[];
    expect(Array.isArray(projects)).toBe(true);
  }, 30_000);
});
