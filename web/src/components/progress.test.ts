/**
 * `indexProgress` 五态渲染（D-30 的 UI 落点）。
 *
 * 这组用例守住三条口径：没有百分比、两个计数不同量纲、`done + error` 不是失败。
 */

import { describe, expect, it } from "vitest";

import type { IndexProgress } from "../api/types";
import { describeIndexProgress } from "./progress";

function make(partial: Partial<IndexProgress>): IndexProgress {
  return {
    state: "idle",
    startedAt: null,
    finishedAt: null,
    processedFiles: 0,
    totalFiles: 0,
    error: null,
    ...partial,
  };
}

describe("describeIndexProgress", () => {
  it("running 明确说明没有百分比", () => {
    const view = describeIndexProgress(
      make({ state: "running", processedFiles: 3, totalFiles: 1436 }),
    );
    expect(view.tone).toBe("running");
    expect(view.label).toBe("索引中");
    expect(view.detail).toContain("已处理 3 / 共 1436 文件");
    expect(view.detail).toContain("无百分比");
  });

  it("done 且无 error 是干净的完成态", () => {
    const view = describeIndexProgress(make({ state: "done", processedFiles: 10, totalFiles: 10 }));
    expect(view.tone).toBe("done");
    expect(view.error).toBeNull();
  });

  it("done 且有 error 是警告而不是失败（部分文件解析问题）", () => {
    const view = describeIndexProgress(
      make({ state: "done", processedFiles: 8, totalFiles: 10, error: "2 个文件解析失败" }),
    );
    expect(view.tone).toBe("warning");
    expect(view.label).toContain("部分文件有解析问题");
    expect(view.error).toBe("2 个文件解析失败");
  });

  it("failed 带出脱敏后的错误摘要", () => {
    const view = describeIndexProgress(make({ state: "failed", error: "ApiAuthError: 401" }));
    expect(view.tone).toBe("failed");
    expect(view.error).toContain("401");
  });

  it("idle 说明重启后需要重新 attach", () => {
    const view = describeIndexProgress(make({ state: "idle" }));
    expect(view.tone).toBe("idle");
    expect(view.label).toContain("重新 attach");
  });

  it("没有进度（未绑定本地目录）时给出口径说明", () => {
    const view = describeIndexProgress(null);
    expect(view.tone).toBe("idle");
    expect(view.detail).toContain("客户端上传");
  });
});
