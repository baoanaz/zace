/**
 * 历史记录（TASK-071）：两个页签——**索引记录**与**使用记录**。
 *
 * 口径（与首页一致，不重复造数）：
 * - 索引记录来自 `index_runs`（成功与失败都落库；`running` 不落库）；
 * - 使用记录来自 `query_audit`（**不含源码内容**，只存 evidence 元数据与耗时）；
 * - 时间窗口默认 30 天；空数据一律显示"没有记录"，不填假行。
 *
 * TASK-083：空态改由 `EmptyState` 渲染；并且**不再吞掉单项目读失败**——旧实现
 * 用 `catch { return [] }` 把"某个项目读历史失败"渲染成"还没有索引记录"，
 * 让后端故障看起来像"还没用"。现在失败的项目会与成功数据一起如实列出。
 *
 * TASK-094 §C：使用记录表加「trace id」列（可复制）。用户报错后拿它去查服务端日志
 * （TASK-090 的 `/api/request-log/{requestId}`），从而把"历史页看到的这一次查询"
 * 与"服务端那一次请求的完整链路"关联起来。旧记录（升级前写下的）没有该值 → 显示 `—`。
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  type IndexRun,
  type Project,
  type UsageSummary,
  getProjectIndexRuns,
  getUsageSummary,
  listProjects,
} from "../api/client";
import { CopyButton, EmptyState, ErrorBlock, LoadingBlock } from "../components/ui";
import { formatDuration, formatTime } from "./DashboardPage";

type Tab = "index" | "usage";

const WINDOW_DAYS = 30;
const ROW_LIMIT = 100;

/** 单个项目历史读取失败：**保留下来显示**，不当作"没有数据"。 */
type RunReadFailure = { projectId: string; error: unknown };

export function HistoryPage() {
  const [tab, setTab] = useState<Tab>("index");
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [runs, setRuns] = useState<{ projectId: string; run: IndexRun }[] | null>(null);
  const [runFailures, setRunFailures] = useState<RunReadFailure[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    setRunFailures([]);
    try {
      const listed = await listProjects();
      setProjects(listed);
      // 逐项目取历史再合并：跨项目端点只回聚合，而"什么时候索引了哪个项目"需要明细。
      // 单项目读失败不静默吞掉——降级为"保留其余数据 + 明确列出失败的项目"。
      const perProject = await Promise.all(
        listed.map(async (project) => {
          try {
            const items = await getProjectIndexRuns(project.projectId, ROW_LIMIT);
            return { items: items.map((run) => ({ projectId: project.projectId, run })) };
          } catch (err) {
            return { items: [], error: { projectId: project.projectId, error: err } };
          }
        }),
      );
      setRunFailures(
        perProject.flatMap((item) => (item.error === undefined ? [] : [item.error])),
      );
      setRuns(
        perProject
          .flatMap((item) => item.items)
          .sort((left, right) => right.run.finishedAt - left.run.finishedAt)
          .slice(0, ROW_LIMIT),
      );
      setUsage(await getUsageSummary(WINDOW_DAYS, ROW_LIMIT));
    } catch (err) {
      setError(err);
      setRuns(null);
      setRunFailures([]);
      setUsage(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-lg font-semibold">历史记录</h1>
        <span className="text-xs text-ink-muted">
          使用记录窗口：近 {usage?.days ?? WINDOW_DAYS} 天
        </span>
      </div>

      {error !== null && <ErrorBlock error={error} />}

      <div className="flex overflow-hidden rounded border border-ink-line text-sm">
        {(
          [
            ["index", "索引记录"],
            ["usage", "使用记录"],
          ] as [Tab, string][]
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setTab(value)}
            className={`px-4 py-1.5 ${
              tab === value ? "bg-accent-seal text-white" : "bg-paper-card hover:bg-paper-base"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "index" && (
        <IndexHistory runs={runs} projects={projects} failures={runFailures} />
      )}
      {tab === "usage" && <UsageHistory usage={usage} />}
    </div>
  );
}

function IndexHistory({
  runs,
  projects,
  failures,
}: {
  runs: { projectId: string; run: IndexRun }[] | null;
  projects: Project[] | null;
  failures: RunReadFailure[];
}) {
  const nameOf = (projectId: string) =>
    projects?.find((item) => item.projectId === projectId)?.displayName || projectId;

  if (runs === null) return <LoadingBlock />;

  if (runs.length === 0) {
    return (
      <div className="rounded-lg border border-ink-line bg-paper-card shadow-sm">
        {failures.length > 0 ? (
          <div className="space-y-2 p-4">
            <p className="text-sm font-medium text-rose-800">
              索引记录读取失败：{failures.map((item) => nameOf(item.projectId)).join("、")}
            </p>
            <p className="text-sm text-ink-muted">
              这**不代表还没有数据**——请先解决上面的错误，再判断是否有记录。
            </p>
            {failures.map((item) => (
              <ErrorBlock key={item.projectId} error={item.error} />
            ))}
          </div>
        ) : (
          <EmptyState
            title="还没有索引记录"
            hint="在编辑器里接入 Agent 后让它同步一次（本地模式也可用客户端 attach 目录），这里就会出现每次索引的结果。"
            action={
              <Link className="text-xs underline" to="/connect">
                去接入指南
              </Link>
            }
          />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {failures.length > 0 && (
        <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <p className="text-sm font-medium text-amber-900">
            部分项目的索引记录读取失败：
            {failures.map((item) => nameOf(item.projectId)).join("、")}
          </p>
          <p className="text-xs text-amber-800">
            下表**只包含读取成功的项目**，这些项目可能还有未显示的记录。
          </p>
          {failures.map((item) => (
            <ErrorBlock key={item.projectId} error={item.error} />
          ))}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-ink-line bg-paper-card shadow-sm">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs text-ink-muted">
              <th className="px-4 py-2 font-normal">结束时间</th>
              <th className="px-4 py-2 font-normal">项目</th>
              <th className="px-4 py-2 font-normal">结果</th>
              <th className="px-4 py-2 font-normal">耗时</th>
              <th className="px-4 py-2 font-normal">文件（解析/总数）</th>
              <th className="px-4 py-2 font-normal">chunks</th>
              <th className="px-4 py-2 font-normal">解析问题</th>
            </tr>
          </thead>
          <tbody>
            {runs.map(({ projectId, run }) => (
              <tr key={`${projectId}-${run.runId}`} className="border-t border-ink-line/60">
                <td className="px-4 py-2 text-xs text-ink-muted">{formatTime(run.finishedAt)}</td>
                <td className="px-4 py-2">{nameOf(projectId)}</td>
                <td className="px-4 py-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs ${
                      run.state === "done"
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-rose-50 text-rose-700"
                    }`}
                  >
                    {run.state === "done" ? "成功" : "失败"}
                  </span>
                  {run.error && (
                    <span
                      title={run.error}
                      className="ml-2 cursor-help text-xs text-amber-700 underline decoration-dotted"
                    >
                      有解析问题
                    </span>
                  )}
                </td>
                <td className="px-4 py-2">{formatDuration(run.durationMs)}</td>
                <td className="px-4 py-2">
                  {run.filesProcessed} / {run.filesTotal}
                </td>
                <td className="px-4 py-2">{run.chunks}</td>
                <td className="px-4 py-2 text-xs text-ink-muted">{run.errors || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="border-t border-ink-line/60 px-4 py-2 text-xs text-ink-muted">
          "文件（解析/总数）"两列不是同一量纲（总数含二进制/超限文件），**不换算百分比**；
          失败记录没有有意义的耗时，因此不参与平均耗时的计算。
        </p>
      </div>
    </div>
  );
}

function UsageHistory({ usage }: { usage: UsageSummary | null }) {
  if (usage === null) return <LoadingBlock />;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 rounded-lg border border-ink-line bg-paper-card p-4 text-sm shadow-sm sm:grid-cols-4">
        <Stat label="查询次数" value={String(usage.total)} />
        <Stat label="有答案" value={String(usage.succeeded)} />
        <Stat label="证据不足" value={String(usage.insufficient)} />
        <Stat label="失败" value={String(usage.failed)} />
        <Stat
          label="平均耗时"
          value={usage.avgLatencyMs === null ? "—" : `${usage.avgLatencyMs} ms`}
        />
        <Stat
          label="P95 耗时"
          value={usage.p95LatencyMs === null ? "—" : `${usage.p95LatencyMs} ms`}
        />
        <Stat
          label="引用覆盖率"
          value={
            usage.citationCoverageAvg === null
              ? "—"
              : `${(usage.citationCoverageAvg * 100).toFixed(1)}%`
          }
        />
        <Stat label="用量 token" value={String(sumTokens(usage))} />
      </div>

      {Object.keys(usage.confidenceDistribution).length > 0 && (
        <div className="rounded-lg border border-ink-line bg-paper-card p-4 text-sm shadow-sm">
          <h2 className="mb-2 text-sm font-semibold text-ink-primary">confidence 分布</h2>
          <div className="flex flex-wrap gap-3">
            {Object.entries(usage.confidenceDistribution).map(([key, count]) => (
              <span key={key} className="rounded bg-paper-base px-2 py-1 text-xs text-ink-primary">
                {key}: {count}
              </span>
            ))}
          </div>
        </div>
      )}

      {usage.recent.length === 0 ? (
        <div className="rounded-lg border border-ink-line bg-paper-card shadow-sm">
          <EmptyState
            title="这段时间还没有查询记录"
            hint="在编辑器里接入 Agent 后向它提问，每次查询都会记录在这里（默认看近 30 天）。"
            action={
              <Link className="text-xs underline" to="/connect">
                去接入指南
              </Link>
            }
          />
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-ink-line bg-paper-card shadow-sm">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-muted">
                <th className="px-4 py-2 font-normal">时间</th>
                <th className="px-4 py-2 font-normal">trace id</th>
                <th className="px-4 py-2 font-normal">模式</th>
                <th className="px-4 py-2 font-normal">查询</th>
                <th className="px-4 py-2 font-normal">结果</th>
                <th className="px-4 py-2 font-normal">耗时</th>
                <th className="px-4 py-2 font-normal">证据</th>
                <th className="px-4 py-2 font-normal">token</th>
              </tr>
            </thead>
            <tbody>
              {usage.recent.map((record) => (
                <tr key={record.queryId} className="border-t border-ink-line/60">
                  <td className="px-4 py-2 text-xs text-ink-muted">
                    {formatTime(record.createdAt)}
                  </td>
                  {/* trace id：可复制；旧记录（后端升级前写的）没有它 → —。 */}
                  <td className="px-4 py-2 text-xs">
                    {record.requestId ? (
                      <span className="inline-flex items-center gap-1">
                        <code className="font-mono text-ink-muted">{record.requestId}</code>
                        <CopyButton text={record.requestId} label="复制" />
                      </span>
                    ) : (
                      <span className="text-ink-muted" title="该记录落库时尚未记录 trace id">
                        —
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs">{record.mode}</td>
                  <td className="px-4 py-2">{record.query}</td>
                  <td className="px-4 py-2 text-xs">
                    {record.answerable === null
                      ? record.degraded
                        ? "降级"
                        : "—"
                      : record.answerable
                        ? "有答案"
                        : "证据不足"}
                    {record.confidence && (
                      <span className="ml-1 text-ink-muted">({record.confidence})</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs">{record.latencyMs} ms</td>
                  <td className="px-4 py-2 text-xs">
                    {record.evidenceCount} / {record.docsCount}
                  </td>
                  <td className="px-4 py-2 text-xs">{record.usedTokens}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-ink-line/60 px-4 py-2 text-xs text-ink-muted">
            审计只保存证据的元数据（id/路径/行号/分层/分数），**不含源码内容**。
            「trace id」是这次查询的请求标识：出现问题时**把这个 id 报给管理员**，
            可在服务端按它回溯完整日志（含错误堆栈）。
          </p>
        </div>
      )}
    </div>
  );
}

function sumTokens(usage: UsageSummary): number {
  return usage.recent.reduce((total, record) => total + record.usedTokens, 0);
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-ink-muted">{label}</div>
      <div className="text-lg font-semibold text-ink-primary">{value}</div>
    </div>
  );
}
