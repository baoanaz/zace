/**
 * 首页仪表盘（TASK-071）：**只放账户资料与数据面板**（用户 2026-09-13 指定）。
 *
 * 面板口径（不许美化成好看的数字）：
 * - `avgDurationMs` **只统计成功的索引**——失败 run 的耗时是"失败得多快"；
 * - `processedFiles/totalFiles` 不同量纲，不做除法、**不显示百分比**；
 * - 未测量的一律显示 `—`（如 `citationCoverageAvg` 在 LLM 接入前恒为 null）。
 *
 * TASK-083：空态改由 `EmptyState` 渲染（每处都说明"怎样才会有数据"）；
 * `sumDisk` 不再把"后端未提供 `diskBytes`"伪装成"占用 0"。
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  type Account,
  type AccountOverview,
  getAccountOverview,
} from "../api/client";
import { EmptyState, ErrorBlock, LoadingBlock } from "../components/ui";

const WINDOW_DAYS = 30;

export function DashboardPage({ account }: { account: Account | null }) {
  const [data, setData] = useState<AccountOverview | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await getAccountOverview(WINDOW_DAYS));
    } catch (err) {
      setData(null);
      setError(err);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error !== null) return <ErrorBlock error={error} />;
  if (data === null) return <LoadingBlock />;

  const { account: profile, index, usage } = data;

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-semibold">账户</h1>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="账户资料" className="lg:col-span-1">
          <Row label="账户" value={profile.name} />
          <Row
            label="类型"
            value={profile.isLocal ? "本地单用户（无鉴权）" : "云端账户"}
          />
          <Row label="创建时间" value={formatTime(profile.createdAt)} />
          <Row label="项目数" value={String(profile.projectCount)} />
          <Row label="当前身份" value={account?.via ?? (profile.isLocal ? "local" : "—")} />
        </Panel>

        <Panel title={`索引（近 ${data.days} 天）`} className="lg:col-span-2">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Metric label="成功次数" value={String(index.succeeded)} tone="ok" />
            <Metric label="失败次数" value={String(index.failed)} tone={index.failed > 0 ? "bad" : "muted"} />
            <Metric
              label="平均耗时"
              value={index.avgDurationMs === null ? "—" : formatDuration(index.avgDurationMs)}
              hint="仅统计成功"
            />
            <Metric
              label="占用内存"
              value={formatBytes(index.diskBytes)}
              hint={index.diskBytes == null ? "后端未提供" : "索引数据磁盘占用"}
            />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Metric label="索引总次数" value={String(index.total)} />
            <Metric
              label="最快 / 最慢"
              value={
                index.minDurationMs == null
                  ? "—"
                  : `${formatDuration(index.minDurationMs)} / ${formatDuration(index.maxDurationMs ?? 0)}`
              }
            />
            <Metric
              label="最近一次"
              value={index.lastRunAt === null ? "—" : formatTime(index.lastRunAt)}
              hint={index.lastState ?? undefined}
            />
            <Metric label="项目" value={String(data.projects.length)} />
          </div>
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title={`使用次数（近 ${data.days} 天）`}>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Metric label="查询总数" value={String(usage.total)} />
            <Metric label="有答案" value={String(usage.succeeded)} tone="ok" />
            <Metric label="证据不足" value={String(usage.insufficient)} tone={usage.insufficient > 0 ? "warn" : "muted"} />
            <Metric label="失败" value={String(usage.failed)} tone={usage.failed > 0 ? "bad" : "muted"} />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <Metric
              label="平均耗时"
              value={usage.avgLatencyMs === null ? "—" : `${usage.avgLatencyMs} ms`}
            />
            <Metric
              label="P95 耗时"
              value={usage.p95LatencyMs === null ? "—" : `${usage.p95LatencyMs} ms`}
            />
          </div>
          <p className="mt-3 text-xs text-slate-500">
            引用覆盖率：{usage.citationCoverageAvg === null ? "— 尚未测量（LLM 总结未接入）" : `${(usage.citationCoverageAvg * 100).toFixed(1)}%`}
          </p>
        </Panel>

        <Panel title="最近索引记录">
          {index.recent.length === 0 ? (
            <EmptyState
              title="还没有索引记录"
              hint="在编辑器里接入 Agent 后让它同步一次（本地模式也可用客户端 attach 目录），这里就会列出最近的索引结果。"
              action={
                <Link className="text-xs underline" to="/connect">
                  去接入指南
                </Link>
              }
            />
          ) : (
            <ul className="space-y-2">
              {index.recent.slice(0, 6).map((run) => (
                <li key={run.runId} className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="flex items-center gap-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs ${
                        run.state === "done"
                          ? "bg-emerald-50 text-emerald-700"
                          : "bg-rose-50 text-rose-700"
                      }`}
                    >
                      {run.state === "done" ? "成功" : "失败"}
                    </span>
                    <span className="font-mono text-xs text-slate-500">{run.projectId}</span>
                  </span>
                  <span className="text-xs text-slate-500">
                    {formatDuration(run.durationMs)} · {run.filesProcessed}/{run.filesTotal} 文件 ·{" "}
                    {formatTime(run.finishedAt)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <Link className="mt-3 inline-block text-xs underline" to="/history">
            查看全部历史
          </Link>
        </Panel>
      </div>

      <Panel title="项目">
        {data.projects.length === 0 ? (
          <EmptyState
            title="还没有项目"
            hint="项目在你第一次同步时自动创建：接入 Agent 并让它上传/索引一个仓库，项目就会出现在这里。"
            action={
              <Link className="text-xs underline" to="/connect">
                去接入指南
              </Link>
            }
          />
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500">
                <th className="border-b border-slate-200 py-1">项目</th>
                <th className="border-b border-slate-200 py-1">projectId</th>
                <th className="border-b border-slate-200 py-1">文件</th>
                <th className="border-b border-slate-200 py-1">chunks</th>
                <th className="border-b border-slate-200 py-1">状态</th>
              </tr>
            </thead>
            <tbody>
              {data.projects.map((project) => (
                <tr key={project.projectId}>
                  <td className="border-b border-slate-100 py-1">
                    {project.displayName || project.projectId}
                  </td>
                  <td className="border-b border-slate-100 py-1 font-mono text-xs">
                    {project.projectId}
                  </td>
                  <td className="border-b border-slate-100 py-1">
                    {project.sync?.filesIndexed ?? "—"}
                  </td>
                  <td className="border-b border-slate-100 py-1">{project.sync?.chunks ?? "—"}</td>
                  <td className="border-b border-slate-100 py-1 text-xs">
                    {project.indexProgress?.state ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

function Panel({
  title,
  children,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white p-4 shadow-sm ${className}`}
    >
      <h2 className="mb-3 text-sm font-semibold text-slate-800">{title}</h2>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-dashed border-slate-100 py-1.5">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="text-sm text-slate-800">{value}</span>
    </div>
  );
}

function Metric({
  label,
  value,
  hint,
  tone = "muted",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "ok" | "bad" | "warn" | "muted";
}) {
  const color =
    tone === "ok"
      ? "text-emerald-700"
      : tone === "bad"
        ? "text-rose-700"
        : tone === "warn"
          ? "text-amber-700"
          : "text-slate-900";
  return (
    <div>
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-xl font-semibold ${color}`}>{value}</div>
      {hint && <div className="text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

export function formatTime(unixSeconds: number): string {
  if (!unixSeconds) return "—";
  return new Date(unixSeconds * 1000).toLocaleString();
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

/** 字节数格式化；`null`/`undefined`（后端未提供）显示 `—`，不退化成"0 B"。 */
export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GiB`;
}
