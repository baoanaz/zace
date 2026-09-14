/** 通用展示组件：徽标 / 卡片 / 错误块 / 复制按钮（无请求，纯展示）。 */

import { useEffect, useRef, useState, type ReactNode } from "react";

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
 * 页面宽度容器（TASK-100）。
 *
 * 壳层（`Layout`）不再限定宽度，由页面自己选：
 * - `Page`（**默认**）：`max-w-5xl`（64rem）——控制台/项目/接入指南/API Key/设置；
 *   表单与信息卡在过宽的屏幕上会拉得很长、阅读困难。
 * - `WidePage`：`max-w-[120rem]`——**只有历史记录**这种列多的宽表需要。
 *
 * 为什么不用“按页面类型自动判断”：用户明确说“只有历史记录调宽即可”，
 * 自动判断会在新页面出现时默默给出错误宽度；显式声明让每个页面自己负责。
 */
export function Page({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-5xl space-y-5">{children}</div>;
}

export function WidePage({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-[120rem] space-y-5">{children}</div>;
}

/**
 * 滑动开关（TASK-099 前端收尾）：用户 2026-09-14 要求自动刷新用「滑动开关」而不是勾选框。
 *
 * 为什么自建而不是用原生 checkbox：用户明确要滑块观感；且原生 checkbox 无法在保持
 * 无障碍语义（role="switch"）的同时做出这个形态。这里用 `<button role="switch">`：
 * 键盘可聚焦、空格/回车可切换、`aria-checked` 让读屏器报出状态（比自造 div 正确）。
 *
 * 点击处理：`<button>` 自身可点；调用方用 `<label>` 包住它时，点 label 文字也会触发
 * 内部控件的 click（浏览器原生行为），因此**点文字与点滑块是同一条路径**，
 * 不需要额外的 `htmlFor`/`id` 配对。
 */
export function Switch({
  checked,
  onChange,
  label,
  disabled = false,
  testId,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
  testId?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      data-testid={testId}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-4 w-8 shrink-0 items-center rounded-full border transition-colors disabled:opacity-40 ${
        checked ? "border-accent-seal bg-accent-seal" : "border-ink-line bg-paper-base"
      }`}
    >
      <span
        aria-hidden="true"
        className={`absolute h-3 w-3 rounded-full bg-paper-card shadow-sm transition-transform ${
          checked ? "translate-x-4" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

/**
 * 二次确认弹窗（TASK-094 §D）：破坏性操作前必须让用户明确看过后果。
 *
 * 为什么用原生 `<dialog>` 而不是自造遮罩层：浏览器已经给了焦点陷阱、`Esc` 关闭与
 * `aria-modal` 语义，自造一套的常见后果是“键盘用户被卡在遮罩里”与“Esc 不生效”。
 *
 * 确认按钮用 `danger` token（TASK-100）：删除是破坏性操作，保留红色系；
 * 但用收敛的砖红（#9c3d2e）而不是高饱和正红——老纸主题下后者刺眼。
 *
 * 调用方负责挂载/卸载本组件（`open` 控制）；**取消按钮不发任何请求**——那是调用方必须
 * 自己保证的（本组件只回调 `onCancel`/`onConfirm`，不做业务判断）。
 */
export function ConfirmDialog({
  open,
  title,
  confirmLabel = "确认",
  cancelLabel = "取消",
  busy = false,
  onConfirm,
  onCancel,
  children,
}: {
  open: boolean;
  title: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      // Esc 关闭也要走 onCancel（否则调用方以为弹窗还开着，状态不同步）。
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
      className="max-w-lg rounded-lg border border-ink-line bg-paper-card p-0 shadow-xl backdrop:bg-ink-primary/40"
    >
      <div className="p-4">
        <h2 className="text-sm font-semibold text-ink-primary">{title}</h2>
        <div className="mt-2 space-y-2 text-sm text-ink-muted">{children}</div>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded border border-ink-line px-3 py-1.5 text-sm text-ink-primary hover:bg-paper-raised disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded bg-danger-base px-3 py-1.5 text-sm font-medium text-white hover:bg-danger-hover disabled:opacity-50"
          >
            {busy ? "处理中…" : confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
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
