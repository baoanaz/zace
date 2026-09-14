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
 * **保存能力尚未实现**（TASK-099 后端卡）：现在没有任何配置写入端点，
 * LLM 配置只读环境变量。因此本页：
 * - 表单**结构按最终形态呈现**（模型名 / 接口地址 / API Key 三个字段 + 保存/清除），
 *   便于评审设计；但 `disabled` 并明确标注"保存待后端支持"——**不做假按钮**；
 * - 顶部如实显示当前生效值（只读），让用户知道"现在实际在用什么"。
 *
 * 安全口径（承 TASK-088，不放松）：
 * - **不显示 key 的任何部分**（含前缀/长度）——服务端连长度都不返回；
 * - 页面不把 Key 写进 localStorage/sessionStorage，提交后即从组件状态清除。
 */

import { useEffect, useState } from "react";

import { type DeploymentMeta, getMeta } from "../api/client";
import { Card, ErrorBlock, LoadingBlock } from "../components/ui";

/** 后端是否已支持保存用户级 LLM 配置（TASK-099 实施后置 true）。 */
const CAN_SAVE_USER_LLM = false;

export function SettingsPage() {
  const [meta, setMeta] = useState<DeploymentMeta | null>(null);
  const [error, setError] = useState<unknown>(null);

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

  if (error !== null) {
    return (
      <div className="space-y-5">
        <h1 className="text-lg font-semibold">设置</h1>
        <ErrorBlock error={error} />
      </div>
    );
  }
  if (meta === null) return <LoadingBlock text="正在读取配置…" />;

  const { llm } = meta.config;

  return (
    <div className="space-y-5">
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
            <span className="text-xs text-ink-muted">当前：{llm.model ?? "已配置"}</span>
          ) : (
            <span className="text-xs text-amber-700">未配置</span>
          )
        }
      >
        {!CAN_SAVE_USER_LLM && (
          <p
            data-testid="llm-save-notice"
            className="mb-3 rounded border border-ink-line bg-paper-base px-3 py-2 text-xs text-ink-muted"
          >
            自定义保存尚未开放（后端能力实施中）。下面展示的是<strong>当前生效值</strong>，
            修改请设服务端环境变量后重启。
          </p>
        )}

        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            // 保存能力未实现：不做假提交（不弹"已保存"、不发请求）。
          }}
        >
          <Field label="模型名" hint="例如 deepseek-chat / gpt-4o-mini">
            <input
              name="llmModel"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              disabled={!CAN_SAVE_USER_LLM}
              placeholder="deepseek/deepseek-v4.1-flash"
              className="w-full rounded border border-ink-line bg-paper-card px-3 py-2 font-mono text-sm text-ink-primary disabled:opacity-60"
            />
          </Field>

          <Field label="接口地址" hint="OpenAI 兼容的 /chat/completions 端点">
            <input
              name="llmBaseUrl"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              disabled={!CAN_SAVE_USER_LLM}
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
              disabled={!CAN_SAVE_USER_LLM}
              autoComplete="off"
              placeholder={llm.apiKeyConfigured ? "已配置（留空则不改）" : "sk-..."}
              className="w-full rounded border border-ink-line bg-paper-card px-3 py-2 font-mono text-sm text-ink-primary disabled:opacity-60"
            />
          </Field>

          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              disabled={!CAN_SAVE_USER_LLM}
              className="rounded bg-accent-seal px-4 py-1.5 text-sm font-medium text-white disabled:opacity-40"
            >
              保存
            </button>
            <button
              type="button"
              disabled={!CAN_SAVE_USER_LLM}
              onClick={() => {
                setApiKey("");
              }}
              className="rounded border border-ink-line px-4 py-1.5 text-sm text-ink-primary hover:bg-paper-base disabled:opacity-40"
            >
              清除
            </button>
          </div>
        </form>

        {!llm.configured && llm.missingEnv.length > 0 && (
          <p className="mt-3 text-xs text-amber-700">
            服务端缺少环境变量：{llm.missingEnv.join("、")}。未配置时 ask_project 返回检索结果而非总结。
          </p>
        )}
      </Card>
    </div>
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
