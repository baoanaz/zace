/** 通用展示组件：徽标 / 卡片 / 错误块 / 复制按钮（无请求，纯展示）。 */

import { useState, type ReactNode } from "react";

import { errorHint } from "../api/client";
import type { ProgressTone } from "./progress";
import { TONE_CLASS } from "./progress";

export function Badge({
  children,
  tone = "idle",
  title,
}: {
  children: ReactNode;
  tone?: ProgressTone;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${TONE_CLASS[tone]}`}
    >
      {children}
    </span>
  );
}

export function Card({
  title,
  actions,
  children,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
          {actions}
        </header>
      )}
      <div className="px-4 py-3">{children}</div>
    </section>
  );
}

/** 错误块：服务端 message + `code` + 由 `code` 推出的下一步指引（不各页各写文案）。 */
export function ErrorBlock({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  const code =
    typeof error === "object" && error !== null && "code" in error
      ? String((error as { code: unknown }).code)
      : null;
  const hint = errorHint(error);

  return (
    <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="font-medium">{message}</span>
        {code && <code className="rounded bg-rose-100 px-1 text-xs">{code}</code>}
      </div>
      {hint && <p className="mt-1 text-rose-700">{hint}</p>}
    </div>
  );
}

export function CopyButton({ text, label = "复制" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // 剪贴板不可用（非安全上下文/权限）：如实提示，不静默失败。
      setCopied(false);
    }
  }

  return (
    <button
      type="button"
      onClick={onCopy}
      className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
    >
      {copied ? "已复制" : label}
    </button>
  );
}

export function KeyValue({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
      {items.map(([key, value]) => (
        <div key={key} className="flex items-baseline justify-between gap-3 border-b border-dashed border-slate-100 pb-1">
          <dt className="text-xs text-slate-500">{key}</dt>
          <dd className="text-sm text-slate-800">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function LoadingBlock({ text = "加载中…" }: { text?: string }) {
  return <p className="py-6 text-center text-sm text-slate-500">{text}</p>;
}
