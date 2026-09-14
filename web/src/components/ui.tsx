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
    <section className="rounded-lg border border-ink-line bg-paper-card shadow-sm">
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-ink-line/70 px-4 py-3">
          <h2 className="text-sm font-semibold text-ink-primary">{title}</h2>
          {actions}
        </header>
      )}
      <div className="px-4 py-3">{children}</div>
    </section>
  );
}

/** 把任意抛出物转成可读文本：**永不出 `[object Object]`**（TASK-083 要求）。 */
function describeError(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  if (typeof error === "object" && error !== null && "message" in error) {
    const message = (error as { message: unknown }).message;
    if (typeof message === "string" && message.length > 0) return message;
  }
  // null/undefined 与无法序列化的值不能直接落进兜底文案（`String(null)` 会渲染成 "null"）。
  if (error !== null && error !== undefined) {
    try {
      const json = JSON.stringify(error);
      if (json && json !== "{}" && json !== "null") return json;
    } catch {
      // 循环引用等无法序列化的情况：落到下面的兜底文案。
    }
  }
  return "请求失败（错误对象没有可读的 message）";
}

/** 错误块：服务端 message + `code` + 由 `code` 推出的下一步指引（不各页各写文案）。 */
export function ErrorBlock({ error }: { error: unknown }) {
  const message = describeError(error);
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
      {hint && hint !== message && <p className="mt-1 text-rose-700">{hint}</p>}
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
      className="rounded border border-ink-line bg-paper-card px-2 py-1 text-xs text-ink-primary hover:bg-paper-base"
    >
      {copied ? "已复制" : label}
    </button>
  );
}

export function KeyValue({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
      {items.map(([key, value]) => (
        <div key={key} className="flex items-baseline justify-between gap-3 border-b border-dashed border-ink-line/70 pb-1">
          <dt className="text-xs text-ink-muted">{key}</dt>
          <dd className="text-sm text-ink-primary">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function LoadingBlock({ text = "加载中…" }: { text?: string }) {
  return <p className="py-6 text-center text-sm text-ink-muted">{text}</p>;
}

/**
 * 空态块（TASK-083）：**只用于"请求成功但没有数据"**。
 *
 * 为什么要有这个组件："0 条"与"后端坏了"在旧版看起来一样——用户分不清
 * 是"自己还没用"还是"服务没记上"。因此本组件把两件事钉死：
 *
 * 1. **`hint` 必须说明"怎样才会有数据"**（可操作的一句话），不许写"暂无数据"；
 * 2. **错误一律走 `ErrorBlock`**——请求失败时禁止渲染本组件，否则"后端坏了"会被
 *    伪装成"还没数据"。调用方必须先判错误、再判空数组（各页先渲染 `ErrorBlock`，
 *    确认无错误后才轮到 `EmptyState`）。
 */
export function EmptyState({
  title,
  hint,
  action,
}: {
  title: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="px-4 py-6 text-center">
      <p className="text-sm font-medium text-ink-primary">{title}</p>
      {hint && <p className="mx-auto mt-1 max-w-prose text-sm text-ink-muted">{hint}</p>}
      {action && <div className="mt-3 flex justify-center">{action}</div>}
    </div>
  );
}
