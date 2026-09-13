/**
 * 应用外壳导航（TASK-086 §1）。
 *
 * 守两件事（本卡真正会退化、且用户直接看得见的地方）：
 * 1. **导航顺序 = 控制台 → 接入指南 → API Key → 历史记录**（用户 2026-09-14 要求）；
 * 2. **`to` 是路由契约**——顺序变了，路径一个都不能变（外部链接与文档都指向它们）。
 *
 * 另外顺手钉住 §4 的一个易破点：header 必须保持 `bg-white` 实心，
 * 否则加了全局背景纹理后内容滚动会透过导航文字。
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Layout } from "./Layout";

function renderLayout(initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Layout account={null} onSignedOut={() => {}} />
    </MemoryRouter>,
  );
}

/** 只取主导航里的链接（排除 header 左侧的 "zace" 品牌链接）。 */
function navLinks() {
  return screen.getByRole("navigation").querySelectorAll("a");
}

/** 取某个导航项的高亮 class；找不到就抛出（而不是断言非空）。 */
function navLinkClass(label: string): string {
  const link = [...navLinks()].find((item) => item.textContent === label);
  if (!link) throw new Error(`主导航里没有「${label}」`);
  return link.className;
}

describe("主导航（TASK-086 §1）", () => {
  it("顺序为 控制台 → 接入指南 → API Key → 历史记录", () => {
    renderLayout();

    expect([...navLinks()].map((link) => link.textContent)).toEqual([
      "控制台",
      "接入指南",
      "API Key",
      "历史记录",
    ]);
  });

  it("顺序变了但路由路径一个都没变", () => {
    renderLayout();

    expect([...navLinks()].map((link) => link.getAttribute("href"))).toEqual([
      "/",
      "/connect",
      "/keys",
      "/history",
    ]);
  });

  it("控制台仍指向 / 且 end 生效：/connect 时它不高亮", () => {
    renderLayout("/connect");

    // 若 "/" 丢了 `end`，它会在每个子路径上都保持高亮。
    expect(navLinkClass("控制台")).not.toContain("bg-slate-900");
    expect(navLinkClass("接入指南")).toContain("bg-slate-900");
  });

  it("header 保持 bg-white 实心（TASK-086 §4：不能透过导航文字）", () => {
    renderLayout();

    expect(screen.getByRole("banner").className).toContain("bg-white");
  });
});
