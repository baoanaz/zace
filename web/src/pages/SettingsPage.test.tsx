/**
 * 设置页（TASK-088 §F；TASK-100 §需求9/10 精简为**只留 LLM 配置**）。
 *
 * 守三件事（用户明确要求 + 安全硬线）：
 * 1. **LLM 三个字段可编辑**（模型名 / 接口地址 / API Key）——这是用户要的"自定义 LLM"；
 * 2. **绝不显示 key 的任何部分**（页面只显示"已配置/未配置"，Key 输入框也永不预填）；
 * 3. **未配置时给可操作文案**（说清缺哪几个环境变量、以及 `ask_project` 返回什么）。
 *
 * TASK-100 的同步说明（**没有删掉任何安全断言**）：
 *
 * | 原断言 | 现断言 | 说明 |
 * |---|---|---|
 * | 展示 embedding 的模型/维度/厂商 | 移到控制台的 `ServiceModels` 测试 | embedding 信息按用户要求移出设置页 |
 * | 展示 timeout/maxTokens/temperature | **删除**（连同字段一起，页面不再展示调优细节） | 用户："精简展示"；安全类断言保留 |
 * | `llm-notice` 文案 | 保留为 `llm-save-notice` + 未配置提示 | 仍是"未配置时给可操作文案" |
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

describe("设置页（TASK-088 §F / TASK-100 §需求9）", () => {
  it("LLM 的三个字段以可编辑表单呈现（用户自定义入口）", async () => {
    stubMeta({
      config: {
        embedding: { mode: "api", configured: true, missingEnv: [], model: "voyage-4-lite" },
        llm: {
          configured: true,
          apiKeyConfigured: true,
          missingEnv: [],
          model: "deepseek/deepseek-v4.1-flash",
          baseUrl: "http://host:8080/v1",
        },
      },
    });

    render(<SettingsPage />);

    // 模型名与接口地址用当前生效值预填（便于用户看到"现在是什么"）。
    const model = await screen.findByLabelText(/模型名/);
    expect(model).toHaveValue("deepseek/deepseek-v4.1-flash");
    const baseUrl = screen.getByLabelText(/接口地址/);
    expect(baseUrl).toHaveValue("http://host:8080/v1");

    // Key 是 password 类型且**永不预填**（服务端不返回它，页面也无从得知）。
    const apiKey = screen.getByLabelText(/API Key/);
    expect(apiKey).toHaveAttribute("type", "password");
    expect(apiKey).toHaveValue("");
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

    // 未配置提示仍在（"缺什么 + 会怎样"）。
    const notice = await screen.findByText(/缺少环境变量/);
    expect(notice.textContent).toContain("ANSWER_BASE_URL");
    expect(notice.textContent).toContain("ANSWER_MODEL");
    expect(notice.textContent).toContain("返回检索结果");
    // 标题旁的"未配置"状态。
    expect(screen.getAllByText("未配置").length).toBeGreaterThanOrEqual(1);
  });

  it("保存能力未就绪时如实标注（不做假按钮）", async () => {
    stubMeta({
      config: {
        embedding: { mode: "local", configured: true, missingEnv: [] },
        llm: { configured: true, apiKeyConfigured: true, missingEnv: [], model: "m" },
      },
    });

    render(<SettingsPage />);

    // 后端能力（TASK-099）尚未实施：页面必须说明，而不是给一个点了没反应的按钮。
    expect(await screen.findByTestId("llm-save-notice")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
  });

  it("TASK-100 §需求10：设置页不再展示存储配额与部署形态", async () => {
    stubMeta({
      config: {
        embedding: { mode: "local", configured: true, missingEnv: [] },
        llm: { configured: true, apiKeyConfigured: true, missingEnv: [], model: "m" },
        storage: { perProjectBytes: 524288000, perUserBytes: 2147483648, warnRatio: 0.8, enabled: true },
      },
    });

    render(<SettingsPage />);

    // 存储配额 → 移到 `/projects`；部署形态 → 删除（用户："其他功能删除，精简"）。
    await screen.findByLabelText(/模型名/);
    expect(screen.queryByText("存储配额（只读）")).not.toBeInTheDocument();
    expect(screen.queryByText("部署形态")).not.toBeInTheDocument();
    // 向量模型信息也移出（→ 控制台的「服务模型」卡）。
    expect(screen.queryByText(/检索向量模型/)).not.toBeInTheDocument();
  });
});
