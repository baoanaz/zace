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
 *
 * TASK-099 §C-5：后端已落地写入端点，因此：
 * - 原来那条"保存能力未就绪时如实标注"的断言改写为"保存真的发请求且**只发光字段**"——
 *   **不再有 `llm-save-notice`**（它描述的状态已经不成立，留着就是假话）；
 * - 新增"清除后回落服务端默认"与"`source=user` 时页面如实标注"（§C-4 的可见性）。
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

/**
 * 踢入 `/api/meta` 响应 + 一个记录写入请求的 fetch 桩（TASK-099 §C-5）。
 *
 * 返回的 `calls` 让断言能看清
 * “发了什么请求、请求体里有什么”——尤其是**key 只出现在 PUT 体里、不进任何其它字段**。
 *
 * TASK-113：`testResponse` 可指定 `/api/auth/llm-config/test` 的响应体（默认 ok=true），
 * 与 PUT/DELETE 分开处理——自检是独立端点。
 */
function stubMetaAndWrites(
  meta: Partial<DeploymentMeta> & { config: DeploymentMeta["config"] },
  refresh?: Partial<DeploymentMeta> & { config: DeploymentMeta["config"] },
  testResponse?: Record<string, unknown>,
) {
  const body: DeploymentMeta = {
    version: "0.0.1",
    localMode: true,
    authRequired: false,
    registerOpen: false,
    needsBootstrap: false,
    userCount: null,
    ...meta,
  };
  const calls: Array<{ url: string; method: string; body: unknown }> = [];
  let metaCalls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({
        url,
        method,
        body: init?.body === undefined ? undefined : JSON.parse(String(init.body)),
      });
      if (method === "GET") {
        metaCalls += 1;
        const payload = metaCalls > 1 && refresh ? { ...body, ...refresh } : body;
        return new Response(JSON.stringify(payload), { status: 200 });
      }
      if (method === "DELETE") return new Response(null, { status: 204 });
      // TASK-113：自检端点有独立的响应形状。
      if (url.includes("/llm-config/test")) {
        return new Response(
          JSON.stringify(
            testResponse ?? {
              ok: true,
              message: "连通（/v1/models 可访问，模型存在）",
              protocol: "responses",
              protocolLabel: "OpenAI Responses（/v1/responses）",
              endpoint: "https://my.llm/v1/responses",
              modelFound: true,
              supportedProtocols: ["openai", "responses"],
              protocolMismatch: false,
              checks: ["models"],
            },
          ),
          { status: 200 },
        );
      }
      return new Response(
        JSON.stringify({ model: "m", baseUrl: "u", apiKeyConfigured: true, updatedAt: 1, source: "user" }),
        { status: 200 },
      );
    }),
  );
  return calls;
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
          model: "deepseek-flash",
          baseUrl: "http://host:8080/v1",
        },
      },
    });

    render(<SettingsPage />);

    // 模型名与接口地址用当前生效值预填（便于用户看到"现在是什么"）。
    const model = await screen.findByLabelText(/模型名/);
    expect(model).toHaveValue("deepseek-flash");
    const baseUrl = screen.getByLabelText(/接口地址/);
    expect(baseUrl).toHaveValue("http://host:8080/v1");

    // Key 是 password 类型且**永不预填**（服务端不返回它，页面也无从得知）。
    const apiKey = screen.getByLabelText(/API Key/);
    expect(apiKey).toHaveAttribute("type", "password");
    expect(apiKey).toHaveValue("");
  });

  it("未配置时引导填写表单并说清 ask 的降级行为", async () => {
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

    // 未配置提示只讲用户下一步，不暴露部署环境变量实现细节。
    const notice = await screen.findByText(/尚未配置总结模型/);
    expect(notice.textContent).toContain("模型名、接口地址和 API Key");
    expect(notice.textContent).toContain("返回检索结果");
    // 标题旁的"未配置"状态。
    expect(screen.getAllByText("未配置").length).toBeGreaterThanOrEqual(1);
  });

  it("保存真的发请求（PUT），且请求体只含三个表单字段", async () => {
    const calls = stubMetaAndWrites({
      config: {
        embedding: { mode: "local", configured: true, missingEnv: [] },
        llm: { configured: true, apiKeyConfigured: true, missingEnv: [], model: "m", source: "server" },
      },
    });

    render(<SettingsPage />);

    // TASK-099 §C-5：保存能力已落地，**不再有**"尚未开放"的提示（那个状态已不成立）。
    await screen.findByLabelText(/模型名/);
    expect(screen.queryByTestId("llm-save-notice")).not.toBeInTheDocument();
    const save = screen.getByRole("button", { name: "保存" });
    expect(save).toBeEnabled();

    await userEvent.clear(screen.getByLabelText(/模型名/));
    await userEvent.type(screen.getByLabelText(/模型名/), "my-model");
    await userEvent.clear(screen.getByLabelText(/接口地址/));
    await userEvent.type(screen.getByLabelText(/接口地址/), "https://my.llm/v1");
    await userEvent.type(screen.getByLabelText(/API Key/), "sk-my-secret");
    await userEvent.click(save);

    await waitFor(() =>
      expect(calls.some((call) => call.method === "PUT")).toBe(true),
    );
    const put = calls.find((call) => call.method === "PUT")!;
    expect(put.url).toContain("/api/auth/llm-config");
    expect(put.body).toEqual({
      model: "my-model",
      baseUrl: "https://my.llm/v1",
      apiKey: "sk-my-secret",
      // TASK-113：协议随保存一起提交（下拉框当前值，未改则为当前生效值）。
      protocol: "openai",
    });
    // 保存后重新拉取生效值（否则顶部"当前"会停在旧值上）。
    await waitFor(() => expect(calls.filter((call) => call.method === "GET").length).toBeGreaterThan(1));
    // key 提交后从组件状态清除（安全口径：不在内存里多留）。
    expect((screen.getByLabelText(/API Key/) as HTMLInputElement).value).toBe("");
  });

  it("清除调用 DELETE，并在 source=user 时如实标注生效来源", async () => {
    const calls = stubMetaAndWrites(
      {
        config: {
          embedding: { mode: "local", configured: true, missingEnv: [] },
          llm: { configured: true, apiKeyConfigured: true, missingEnv: [], model: "mine", source: "user" },
        },
      },
      {
        config: {
          embedding: { mode: "local", configured: true, missingEnv: [] },
          llm: { configured: true, apiKeyConfigured: true, missingEnv: [], model: "srv", source: "server" },
        },
      },
    );

    render(<SettingsPage />);

    expect(await screen.findByTestId("llm-source-user")).toBeInTheDocument();
    expect(screen.getByText(/（你的配置）/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "清除" }));

    await waitFor(() => expect(calls.some((call) => call.method === "DELETE")).toBe(true));
    // 删除后"当前生效"应回落到服务端默认（服务端返回什么就显示什么，不自己编）。
    await waitFor(() => expect(screen.getByText(/（服务端默认）/)).toBeInTheDocument());
  });

  it("保存失败时给出可操作提示，且不回显 key", async () => {
    const seen: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        if ((init?.method ?? "GET") === "GET") {
          return new Response(
            JSON.stringify({
              version: "0.0.1",
              localMode: true,
              authRequired: false,
              registerOpen: false,
              needsBootstrap: false,
              userCount: null,
              config: {
                embedding: { mode: "local", configured: true, missingEnv: [] },
                llm: { configured: false, apiKeyConfigured: false, missingEnv: ["ANSWER_MODEL"], source: "server" },
              },
            }),
            { status: 200 },
          );
        }
        seen.push(String(init?.body));
        return new Response(
          JSON.stringify({ error: { code: "invalid_llm_config", message: "model 不能为空" } }),
          { status: 400 },
        );
      }),
    );

    render(<SettingsPage />);
    await userEvent.type(await screen.findByLabelText(/API Key/), "sk-should-not-leak");
    await userEvent.click(screen.getByRole("button", { name: "保存" }));

    const banner = await screen.findByTestId("llm-save-error");
    // 服务端的 message 会展示（它由服务端控制，不含 key）；但**页面上不得出现 key 本身**。
    expect(document.body.textContent).not.toContain("sk-should-not-leak");
    // key 确实只出现在 PUT 请求体里（那是它唯一该去的地方）。
    expect(seen.join(" ")).toContain("sk-should-not-leak");
    expect(banner.textContent).not.toContain("sk-should-not-leak");
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

/**
 * TASK-113（D-47）：协议选择 + 连接自检。
 *
 * 守三件事：
 * 1. **协议是显式选项**，且用当前生效值回填（而不是默默用 openai）；
 * 2. **测试连接真的发请求到自检端点**（且不写库：不带 PUT/DELETE）；
 * 3. **失败时要给出下一步**（建议协议 / 可用模型名），而不是只给一个红叉。
 */
describe("设置页：LLM 多协议与连接自检（TASK-113）", () => {
  const BASE_META = {
    embedding: { mode: "api", configured: true, missingEnv: [] },
    llm: {
      configured: true,
      apiKeyConfigured: true,
      missingEnv: [],
      model: "deepseek-v4-flash",
      baseUrl: "https://ai.cviauto.cn/ai/transit",
      protocol: "responses" as const,
      supportedProtocols: ["openai", "responses", "anthropic"],
    },
  };

  it("协议下拉框用当前生效值回填（用户能看出实际在用什么）", async () => {
    stubMetaAndWrites({ config: BASE_META });

    render(<SettingsPage />);

    const select = (await screen.findByLabelText(/协议/)) as HTMLSelectElement;
    expect(select.value).toBe("responses");
    // 三种协议都在选项里（用户可切换）。
    const values = Array.from(select.options).map((option) => option.value);
    expect(values).toEqual(["openai", "responses", "anthropic"]);
  });

  it("测试连接只调自检端点，且不触发保存（不写库）", async () => {
    const calls = stubMetaAndWrites({ config: BASE_META });

    render(<SettingsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "测试连接" }));

    await waitFor(() =>
      expect(calls.some((call) => call.url.includes("/llm-config/test"))).toBe(true),
    );
    const test = calls.find((call) => call.url.includes("/llm-config/test"))!;
    expect(test.method).toBe("POST");
    expect(test.body).toMatchObject({ model: "deepseek-v4-flash", protocol: "responses", deep: false });
    // 自检不得写库：本次没有任何 PUT/DELETE。
    expect(calls.some((call) => call.method === "PUT" || call.method === "DELETE")).toBe(false);
  });

  it("“发真实请求”按钮传 deep=true（区分两级的成本）", async () => {
    const calls = stubMetaAndWrites({ config: BASE_META });

    render(<SettingsPage />);
    await userEvent.click(
      await screen.findByRole("button", { name: "测试连接（发真实请求）" }),
    );

    await waitFor(() =>
      expect(calls.some((call) => call.url.includes("/llm-config/test"))).toBe(true),
    );
    const test = calls.find((call) => call.url.includes("/llm-config/test"))!;
    expect(test.body).toMatchObject({ deep: true });
  });

  it("成功时展示协议与端点（用户能核对到底打了哪个 URL）", async () => {
    stubMetaAndWrites({ config: BASE_META });

    render(<SettingsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "测试连接" }));

    const panel = await screen.findByTestId("llm-test-result");
    expect(panel.textContent).toContain("连通");
    expect(screen.getByTestId("llm-test-protocol").textContent).toContain("responses");
    expect(panel.textContent).toContain("/v1/responses");
  });

  it("协议不匹配时给出建议协议（实测根因：deepseek-v4-flash 不支持 openai）", async () => {
    stubMetaAndWrites(
      { config: BASE_META },
      undefined,
      {
        ok: false,
        message: "模型 deepseek-v4-flash 在上游只声明支持 responses，与你选的 openai 不匹配",
        protocol: "openai",
        endpoint: "https://ai.cviauto.cn/ai/transit/v1/chat/completions",
        modelFound: true,
        supportedProtocols: ["anthropic", "responses"],
        suggestedProtocol: "responses",
        protocolMismatch: true,
        checks: ["models"],
      },
    );

    render(<SettingsPage />);
    await userEvent.selectOptions(await screen.findByLabelText(/协议/), "openai");
    await userEvent.click(screen.getByRole("button", { name: "测试连接" }));

    const panel = await screen.findByTestId("llm-test-result");
    expect(panel.textContent).toContain("不匹配");
    expect(screen.getByTestId("llm-test-suggestion").textContent).toContain("responses");
    // 上游声明的协议也要展示（用户据此选对的）。
    expect(panel.textContent).toContain("responses");
  });

  it("模型名拼错时展示上游可用模型（帮用户改正）", async () => {
    stubMetaAndWrites(
      { config: BASE_META },
      undefined,
      {
        ok: false,
        message: "上游模型列表里没有 'deepseek-v4-falsh'（请核对模型名拼写）；该网关当前可用：deepseek-v4-flash",
        protocol: "responses",
        endpoint: "https://ai.cviauto.cn/ai/transit/v1/responses",
        modelFound: false,
        supportedProtocols: [],
        protocolMismatch: false,
        checks: ["models"],
      },
    );

    render(<SettingsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "测试连接" }));

    const panel = await screen.findByTestId("llm-test-result");
    expect(panel.textContent).toContain("deepseek-v4-flash");
    expect(panel.textContent).toContain("未在上游列表中");
  });

  it("改动表单后自检结果失效（不留旧绿灯）", async () => {
    stubMetaAndWrites({ config: BASE_META });

    render(<SettingsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "测试连接" }));
    expect(await screen.findByTestId("llm-test-result")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/模型名/), "x");

    expect(screen.queryByTestId("llm-test-result")).not.toBeInTheDocument();
  });

  it("保存时携带当前选中的协议", async () => {
    const calls = stubMetaAndWrites({ config: BASE_META });

    render(<SettingsPage />);
    await userEvent.selectOptions(await screen.findByLabelText(/协议/), "anthropic");
    await userEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(calls.some((call) => call.method === "PUT")).toBe(true));
    const put = calls.find((call) => call.method === "PUT")!;
    expect(put.body).toMatchObject({ protocol: "anthropic" });
  });
});
