/**
 * 设置（TASK-088 §F；TASK-100 §需求9/10 精简为**只留 LLM**）。
 *
 * 用户 2026-09-14 原话："设置页面，其中 LLM 修改成自定义的配置方式，模型名、URL、Key。
 * 目的是给用户自定义 LLM 的选择。设置页面只保留 LLM 的配置，存储、部署形态等其他功能删除，精简。"
 *
 * 因此本页只做一件事：**让用户配自己的总结模型**。
 * - 存储配额 → 移到 `/projects`（那里有进度条与删除入口，是它的使用场景）；
 * - 部署形态（版本/本地模式/需要登录/开放注册）→ 删除（用户不需要知道这些）；
 * - 向量模型信息 → 移到控制台的「服务模型」卡（与 LLM 并排展示当前生效值）。
 *
 * **保存能力已实现**（TASK-099 §C 后端已落地）：`PUT /api/auth/llm-config` 写入用户配置，
 * `DELETE` 删除后回落服务端默认。本页：
 * - 顶部如实显示**当前实际生效**的那一份（`config.llm.source`：`user` = 你自己配的，
 *   `server` = 服务端环境变量）；
 * - 三个字段 + 保存/清除；保存后重新拉取 `/api/meta` 以刷新"当前值"；
 *
 * 安全口径（承 TASK-088，不放松）：
 * - **不显示 key 的任何部分**（含前缀/长度）——服务端连长度都不返回；
 * - 页面不把 Key 写进 localStorage/sessionStorage，提交后即从组件状态清除。
 */

import { useEffect, useState } from "react";

import {
  type DeploymentMeta,
  deleteUserLlmConfig,
  errorHint,
  getMeta,
  saveUserLlmConfig,
} from "../api/client";
import { Card, ErrorBlock, LoadingBlock, Page } from "../components/ui";

export function SettingsPage() {
  const [meta, setMeta] = useState<DeploymentMeta | null>(null);
  const [error, setError] = useState<unknown>(null);
  //: 保存/清除的反馈（成功文案或错误）；null = 还没有操作过。
  const [notice, setNotice] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  //: 表单状态。**不持久化**——Key 只活在内存里，提交后清除。
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const resolved = await getMeta();
        setMeta(resolved);
        // 用当前生效值预填"非敏感"字段（Key 永不预填——服务端不返回它）。
        setModel(resolved.config.llm.model ?? "");
        setBaseUrl(resolved.config.llm.baseUrl ?? "");
      } catch (err) {
        setError(err);
      }
    })();
  }, []);

  /** 重新拉取生效值（保存/清除后调用：否则顶部"当前"会停留在旧值上）。 */
  async function refresh() {
    const resolved = await getMeta();
    setMeta(resolved);
    setModel(resolved.config.llm.model ?? "");
    setBaseUrl(resolved.config.llm.baseUrl ?? "");
  }

  async function onSave() {
    setBusy(true);
    setNotice(null);
    setSaveError(null);
    try {
      await saveUserLlmConfig({ model, baseUrl, apiKey });
      // 提交后立即从组件状态清除 key（卡内安全口径：它不该在内存里多留一秒）。
      setApiKey("");
      await refresh();
      setNotice("已保存：之后 ask_project 会用你的配置");
    } catch (err) {
      setSaveError(err);
    } finally {
      setBusy(false);
    }
  }

  async function onClear() {
    setBusy(true);
    setNotice(null);
    setSaveError(null);
    try {
      await deleteUserLlmConfig();
      setApiKey("");
      await refresh();
      setNotice("已清除：之后 ask_project 回落服务端默认");
    } catch (err) {
      setSaveError(err);
    } finally {
      setBusy(false);
    }
  }

  if (error !== null) {
    return (
      <Page>
        <h1 className="text-lg font-semibold">设置</h1>
        <ErrorBlock error={error} />
      </Page>
    );
  }
  if (meta === null) return <LoadingBlock text="正在读取配置…" />;

  const { llm } = meta.config;
  const usingUser = llm.source === "user";

  return (
    <Page>
      <div>
        <h1 className="text-lg font-semibold">设置</h1>
        <p className="mt-1 text-sm text-ink-muted">
          为你的账户指定总结模型。留空则使用服务端的默认配置。
        </p>
      </div>

      <Card
        title="总结模型（LLM）"
        actions={
          llm.configured ? (
            <span className="text-xs text-ink-muted">
              当前：{llm.model ?? "已配置"}
              {usingUser ? "（你的配置）" : "（服务端默认）"}
            </span>
          ) : (
            <span className="text-xs text-amber-700">未配置</span>
          )
        }
      >
        {usingUser && (
          <p
            data-testid="llm-source-user"
            className="mb-3 rounded border border-ink-line bg-paper-base px-3 py-2 text-xs text-ink-muted"
          >
            当前生效的是<strong>你自己的配置</strong>；清除后会回落服务端默认。
          </p>
        )}

        {notice !== null && (
          <p
            data-testid="llm-notice"
            className="mb-3 rounded border border-ink-line bg-paper-base px-3 py-2 text-xs text-ink-primary"
          >
            {notice}
          </p>
        )}
        {saveError !== null && (
          <p
            data-testid="llm-save-error"
            className="mb-3 rounded border border-amber-700 px-3 py-2 text-xs text-amber-700"
          >
            {errorHint(saveError) ?? "保存失败，请稍后再试。"}
          </p>
        )}

        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            void onSave();
          }}
        >
          <Field label="模型名" hint="例如 deepseek-chat / gpt-4o-mini">
            <input
              name="llmModel"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder="deepseek-flash"
              className="w-full rounded border border-ink-line bg-paper-card px-3 py-2 font-mono text-sm text-ink-primary disabled:opacity-60"
            />
          </Field>

          <Field label="接口地址" hint="OpenAI 兼容的 /chat/completions 端点">
            <input
              name="llmBaseUrl"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="https://api.example.com/v1"
              className="w-full rounded border border-ink-line bg-paper-card px-3 py-2 font-mono text-sm text-ink-primary disabled:opacity-60"
            />
          </Field>

          <Field label="API Key" hint="只保存在服务端，不会回显">
            <input
              name="llmApiKey"
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              autoComplete="off"
              placeholder={llm.apiKeyConfigured ? "已配置（留空则不改）" : "sk-..."}
              className="w-full rounded border border-ink-line bg-paper-card px-3 py-2 font-mono text-sm text-ink-primary disabled:opacity-60"
            />
          </Field>

          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              disabled={busy}
              className="rounded bg-accent-seal px-4 py-1.5 text-sm font-medium text-white disabled:opacity-40"
            >
              保存
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                void onClear();
              }}
              className="rounded border border-ink-line px-4 py-1.5 text-sm text-ink-primary hover:bg-paper-base disabled:opacity-40"
            >
              清除
            </button>
          </div>
        </form>

        {!llm.configured && !usingUser && llm.missingEnv.length > 0 && (
          <p className="mt-3 text-xs text-amber-700">
            尚未配置总结模型。请在上方填写模型名、接口地址和 API Key；保存后
            ask_project 才会生成总结，未配置时只返回检索结果。
          </p>
        )}
      </Card>
    </Page>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-sm text-ink-primary">{label}</span>
        <span className="text-xs text-ink-muted">{hint}</span>
      </span>
      {children}
    </label>
  );
}
