/**
 * 设置页（TASK-088 §F）。
 *
 * 守两件事（用户明确要求 + 安全硬线）：
 * 1. **展示生效中的 embedding 与 LLM 模型**（含超时/maxTokens/temperature 的只读展示）；
 * 2. **未配置时给可操作文案**（说清缺哪几个环境变量、以及 `ask_project` 会返回什么），
 *    不留空白——但**绝不显示 key 的任何部分**（页面只显示"已配置/未配置"）。
 */

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DeploymentMeta } from "../api/client";
import { SettingsPage } from "./SettingsPage";

function stubMeta(meta: Partial<DeploymentMeta> & { config: DeploymentMeta["config"] }) {
  const body: DeploymentMeta = {
    version: "0.0.1",
    localMode: true,
    authRequired: false,
    registerOpen: false,
    needsBootstrap: false,
    userCount: null,
    ...meta,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("设置页（TASK-088 §F）", () => {
  it("展示生效中的 LLM 与 embedding 配置", async () => {
    stubMeta({
      config: {
        embedding: {
          mode: "api",
          configured: true,
          missingEnv: [],
          model: "voyage-4-lite",
          provider: "voyage",
          baseUrl: "https://api.voyageai.com",
          dim: 1024,
          maxInputTokens: 32000,
        },
        llm: {
          configured: true,
          apiKeyConfigured: true,
          missingEnv: [],
          model: "deepseek/deepseek-v4.1-flash",
          baseUrl: "http://host:8080/v1",
          timeoutS: 60,
          maxTokens: 3072,
          temperature: 0.2,
        },
      },
    });

    render(<SettingsPage />);

    expect(await screen.findByText("deepseek/deepseek-v4.1-flash")).toBeInTheDocument();
    expect(screen.getByText("voyage-4-lite")).toBeInTheDocument();
    // key 只显示状态，不显示值（连前缀都没有）。
    expect(screen.getByText("已配置")).toBeInTheDocument();
    expect(screen.getByText("3072")).toBeInTheDocument();
    expect(screen.getByText("0.2")).toBeInTheDocument();
    expect(screen.getByText("60")).toBeInTheDocument();
  });

  it("未配置时明确说清缺哪些环境变量与 ask 的降级行为", async () => {
    stubMeta({
      config: {
        embedding: { mode: "local", configured: true, missingEnv: [] },
        llm: {
          configured: false,
          apiKeyConfigured: false,
          missingEnv: ["ANSWER_BASE_URL", "ANSWER_API_KEY", "ANSWER_MODEL"],
        },
      },
    });

    render(<SettingsPage />);

    const notice = await screen.findByTestId("llm-notice");
    expect(notice.textContent).toContain("未配置");
    expect(notice.textContent).toContain("返回检索结果");
    expect(screen.getByText("ANSWER_BASE_URL")).toBeInTheDocument();
    expect(screen.getByText("ANSWER_MODEL")).toBeInTheDocument();
    expect(screen.getAllByText("未配置").length).toBeGreaterThanOrEqual(1);
    // key 状态行也在（只显示状态，不显示任何值）。
    expect(screen.getByText("API Key")).toBeInTheDocument();
  });

  it("免鉴权端点上拿不到模型名时如实说明（不假装读到空值）", async () => {
    stubMeta({
      config: {
        embedding: { mode: "local", configured: true, missingEnv: [] },
        llm: { configured: true, apiKeyConfigured: true, missingEnv: [] },
      },
    });

    render(<SettingsPage />);

    expect(await screen.findByText(/只对已登录用户展示/)).toBeInTheDocument();
  });
});
