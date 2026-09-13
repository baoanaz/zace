/**
 * `IndexProgress` 的如实渲染（D-30 / Module 07 §2.3）。
 *
 * 三条不许妥协的规则（口径来自 `docs/handbook/M2a-验收手册.md` §2）：
 * 1. **没有百分比**：core 的 ingest 无回调，中间态拿不到真实完成度——宁可信息少，不可信息假；
 * 2. `totalFiles` 与 `processedFiles` **不是同一量纲**（前者含二进制/构建产物，后者只数真正解析的文件），
 *    所以只并排显示，不做除法；
 * 3. `state="done"` 且 `error` 非空 = "索引完成，但这些文件有解析问题"，**不是失败**。
 */

import type { IndexProgress } from "../api/types";

export type ProgressTone = "idle" | "running" | "done" | "warning" | "failed";

export interface ProgressView {
  tone: ProgressTone;
  label: string;
  detail: string | null;
  error: string | null;
}

/** 把 `indexProgress` 归一成可渲染的视图（纯函数，便于单测）。 */
export function describeIndexProgress(
  progress: IndexProgress | null | undefined,
): ProgressView {
  if (!progress) {
    return {
      tone: "idle",
      label: "未索引",
      detail: "服务未绑定本地目录，或该项目走客户端上传（索引状态见 sync）。",
      error: null,
    };
  }

  const counts = `已处理 ${progress.processedFiles} / 共 ${progress.totalFiles} 文件`;
  const noPercent = "无百分比：core 索引过程没有进度回调，这里不伪造进度条";

  switch (progress.state) {
    case "running":
      return { tone: "running", label: "索引中", detail: `${counts}（${noPercent}）`, error: null };
    case "done":
      if (progress.error) {
        return {
          tone: "warning",
          label: "索引完成（部分文件有解析问题）",
          detail: counts,
          error: progress.error,
        };
      }
      return { tone: "done", label: "索引完成", detail: counts, error: null };
    case "failed":
      return {
        tone: "failed",
        label: "索引失败",
        detail: counts,
        error: progress.error ?? "未提供错误详情",
      };
    case "idle":
    default:
      return {
        tone: "idle",
        label: "未索引（重启后需重新 attach）",
        detail: counts,
        error: null,
      };
  }
}

export const TONE_CLASS: Record<ProgressTone, string> = {
  idle: "bg-slate-100 text-slate-600 border-slate-200",
  running: "bg-blue-50 text-blue-700 border-blue-200",
  done: "bg-emerald-50 text-emerald-700 border-emerald-200",
  warning: "bg-amber-50 text-amber-800 border-amber-200",
  failed: "bg-rose-50 text-rose-700 border-rose-200",
};
