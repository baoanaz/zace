/**
 * 历史记录（TASK-071 → TASK-100 §需求2 合并为**一张表**）。
 *
 * 用户 2026-09-14 原话："索引记录 + 使用记录合并成一张表，用「类型」列区分：
 * 仓库初始化 / 检索；用户一眼看出，初始化花了多久、检索花了多久。"
 *
 * 为什么合并：用户一次请求可能包含几个仓库初始化 + 一个检索，分两个页签看
 * 需要来回切才能拼出"这次到底花了多久、慢了哪一步"。合并后按时间倒序排，
 * **同一时刻的初始化与检索天然相邻**，因果一眼可见。
 *
 * 表格列（用户要求 + 我的必需性判断）：
 *
 * | 列 | 来源 | 为什么必要 |
 * |---|---|---|
 * | 时间 | 都有 | 排序与"什么时候发生的" |
 * | 类型 | — | 区分仓库初始化 / 检索（用户的明确要求） |
 * | project / 查询 | 都有 | 是哪一次操作（初始化看项目，检索看问题） |
 * | trace id | `query_audit.request_id` | 报错时给管理员查日志（TASK-094 §C 的用途） |
 * | 结果 | 都有 | 成功/失败/证据不足——用户最关心的 |
 * | 耗时 | 都有 | 用户的明确要求 |
 * | 输入输出 | 都有 | **可点击弹窗**看真实数据（用户的明确要求） |
 * | 体量 | 初始化=chunks，检索=token | 用户说"Token 数或者 chunk 数量那种" |
 *
 * **弹窗的诚实边界**：`query_audit` **不存 LLM 的 answer 正文**（只存证据元数据），
 * 因此弹窗对"检索"展示的是**输入（query 全文）+ 检索到的证据清单**，
 * 并如实说明"答案正文未落库"——不拿证据清单冒充 LLM 输出（TASK-099 补 answer 后再展示）。
 *
 * 时间范围（用户 2026-09-14 追加要求：天为单位）：固定档位一键切换。
 * 注意**索引记录的后端端点不支持 days 过滤**（只按 limit 取最近 N 条），
 * 因此本页对索引做**前端按时间过滤**，并在页脚如实说明这一点。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  type IndexRun,
  type Project,
  type UsageRecord,
  type UsageSummary,
  getProjectIndexRuns,
  getUsageSummary,
  listProjects,
} from "../api/client";
import { CopyButton, EmptyState, ErrorBlock, LoadingBlock } from "../components/ui";
import { formatDuration, formatTime } from "./DashboardPage";

const ROW_LIMIT = 200;

/** 时间范围档位（天）。索引记录走前端过滤，检索走后端 `days` 参数。 */
const RANGE_OPTIONS: [number, string][] = [
  [1, "今天"],
  [7, "近 7 天"],
  [30, "近 30 天"],
  [90, "近 90 天"],
];

/** 单个项目历史读取失败：**保留下来显示**，不当作"没有数据"。 */
type RunReadFailure = { projectId: string; error: unknown };

/**
 * 统一后的表格行（初始化与检索共用一个形状）。
 *
 * `kind` 是用户要求的「类型」列；`input`/`output` 是弹窗要展示的原始数据。
 */
type ActivityRow =
  | {
      kind: "init";
      key: string;
      at: number;
      title: string;
      subtitle: string;
      state: "ok" | "failed";
      durationMs: number;
      volume: { label: string; value: string };
      traceId: string | null;
      input: { label: string; value: string }[];
      output: { label: string; value: string }[];
      note?: string;
    }
  | {
      kind: "search";
      key: string;
      at: number;
      title: string;
      subtitle: string;
      state: "ok" | "insufficient" | "failed" | "degraded";
      durationMs: number;
      volume: { label: string; value: string };
      traceId: string | null;
      input: { label: string; value: string }[];
      output: { label: string; value: string }[];
      note?: string;
    };

export function HistoryPage() {
  const [days, setDays] = useState(30);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [runs, setRuns] = useState<{ projectId: string; run: IndexRun }[] | null>(null);
  const [runFailures, setRunFailures] = useState<RunReadFailure[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [detail, setDetail] = useState<ActivityRow | null>(null);

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
      setRunFailures(perProject.flatMap((item) => (item.error === undefined ? [] : [item.error])));
      setRuns(
        perProject
          .flatMap((item) => item.items)
          .sort((left, right) => right.run.finishedAt - left.run.finishedAt)
          .slice(0, ROW_LIMIT),
      );
      setUsage(await getUsageSummary(days, ROW_LIMIT));
    } catch (err) {
      setError(err);
      setRuns(null);
      setRunFailures([]);
      setUsage(null);
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  const nameOf = useCallback(
    (projectId: string) =>
      projects?.find((item) => item.projectId === projectId)?.displayName || projectId,
    [projects],
  );

  /** 合并 + 按时间倒序 + 按窗口过滤（索引侧前端过滤，见文件头说明）。 */
  const rows = useMemo<ActivityRow[] | null>(() => {
    if (runs === null || usage === null) return null;
    const since = Math.floor(Date.now() / 1000) - days * 86400;

    const initRows: ActivityRow[] = runs
      .filter(({ run }) => run.finishedAt >= since)
      .map(({ projectId, run }) => ({
        kind: "init",
        key: `init-${projectId}-${run.runId}`,
        at: run.finishedAt,
        title: nameOf(projectId),
        subtitle: "仓库初始化",
        state: run.state === "done" ? "ok" : "failed",
        durationMs: run.durationMs,
        volume: { label: "chunks", value: String(run.chunks) },
        traceId: null,
        input: [
          { label: "项目", value: nameOf(projectId) },
          { label: "projectId", value: projectId },
        ],
        output: [
          { label: "解析文件", value: `${run.filesProcessed} / ${run.filesTotal}` },
          { label: "chunks", value: String(run.chunks) },
          { label: "解析问题", value: run.errors > 0 ? `${run.errors} 个` : "无" },
        ],
        ...(run.error ? { note: run.error } : {}),
      }));

    const searchRows: ActivityRow[] = usage.recent
      .filter((record) => record.createdAt >= since)
      .map((record) => ({
        kind: "search",
        key: `search-${record.queryId}`,
        at: record.createdAt,
        title: record.query,
        subtitle: "检索",
        state: searchState(record),
        durationMs: record.latencyMs,
        volume: { label: "token", value: String(record.usedTokens) },
        traceId: record.requestId,
        input: [{ label: "查询", value: record.query }],
        output: [
          { label: "证据条数", value: String(record.evidenceCount) },
          { label: "文档条数", value: String(record.docsCount) },
          { label: "模式", value: record.mode },
          ...(record.confidence ? [{ label: "confidence", value: record.confidence }] : []),
        ],
        // 诚实边界：answer 正文没有落库（TASK-099 补），不拿证据清单冒充它。
        note: "答案正文未落库：这里展示的是输入与检索到的证据概览。",
      }));

    return [...initRows, ...searchRows].sort((left, right) => right.at - left.at);
  }, [runs, usage, days, nameOf]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-lg font-semibold">历史记录</h1>
        <div className="flex overflow-hidden rounded border border-ink-line text-xs">
          {RANGE_OPTIONS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setDays(value)}
              className={`px-2.5 py-1 ${
                days === value
                  ? "bg-accent-seal text-white"
                  : "bg-paper-card text-ink-muted hover:bg-paper-base"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {error !== null && <ErrorBlock error={error} />}

      {runFailures.length > 0 && (
        <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <p className="text-sm font-medium text-amber-900">
            部分项目的初始化记录读取失败：
            {runFailures.map((item) => nameOf(item.projectId)).join("、")}
          </p>
          <p className="text-xs text-amber-800">
            下表<strong>只包含读取成功的项目</strong>，这些项目可能还有未显示的记录。
          </p>
          {runFailures.map((item) => (
            <ErrorBlock key={item.projectId} error={item.error} />
          ))}
        </div>
      )}

      {rows === null ? (
        <LoadingBlock />
      ) : rows.length === 0 ? (
        <div className="rounded-lg border border-ink-line bg-paper-card shadow-sm">
          <EmptyState
            title={`近 ${days} 天没有记录`}
            hint="在编辑器里接入 Agent 后向它提问，仓库初始化与检索都会记录在这里。"
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
                <th className="px-4 py-2 font-normal">类型</th>
                <th className="px-4 py-2 font-normal">项目 / 查询</th>
                <th className="px-4 py-2 font-normal">trace id</th>
                <th className="px-4 py-2 font-normal">结果</th>
                <th className="px-4 py-2 font-normal">耗时</th>
                <th className="px-4 py-2 font-normal">体量</th>
                <th className="px-4 py-2 font-normal">详情</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className="border-t border-ink-line/60">
                  <td className="px-4 py-2 text-xs text-ink-muted">{formatTime(row.at)}</td>
                  <td className="px-4 py-2 text-xs">
                    <KindBadge kind={row.kind} />
                  </td>
                  <td className="max-w-xs truncate px-4 py-2" title={row.title}>
                    {row.title}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {row.traceId ? (
                      <span className="inline-flex items-center gap-1">
                        <code className="font-mono text-ink-muted">{row.traceId}</code>
                        <CopyButton text={row.traceId} label="复制" />
                      </span>
                    ) : (
                      <span className="text-ink-muted" title="仓库初始化不产生 trace id">
                        —
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    <StateBadge state={row.state} />
                  </td>
                  <td className="px-4 py-2 text-xs">{formatDuration(row.durationMs)}</td>
                  <td className="px-4 py-2 text-xs text-ink-muted">
                    {row.volume.value} {row.volume.label}
                  </td>
                  <td className="px-4 py-2">
                    <button
                      type="button"
                      onClick={() => setDetail(row)}
                      className="rounded border border-ink-line px-2 py-0.5 text-xs text-ink-primary hover:bg-paper-base"
                    >
                      查看
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-ink-line/60 px-4 py-2 text-xs text-ink-muted">
            「仓库初始化」是首次调用 Tool 时索引整个仓库（耗时较长），之后只处理改动文件；
            「检索」是每次提问。初始化不产生 trace id（它属于客户端同步链路）。
          </p>
        </div>
      )}

      <DetailDialog row={detail} onClose={() => setDetail(null)} />
    </div>
  );
}

/** 类型徽标：仓库初始化 / 检索。 */
function KindBadge({ kind }: { kind: ActivityRow["kind"] }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 ${
        kind === "init" ? "bg-paper-base text-ink-primary" : "bg-blue-50 text-blue-800"
      }`}
    >
      {kind === "init" ? "仓库初始化" : "检索"}
    </span>
  );
}

/** 状态徽标：成功 / 失败 / 证据不足 / 降级。 */
function StateBadge({ state }: { state: ActivityRow["state"] }) {
  const map: Record<ActivityRow["state"], [string, string]> = {
    ok: ["成功", "bg-emerald-50 text-emerald-700"],
    failed: ["失败", "bg-rose-50 text-rose-700"],
    insufficient: ["证据不足", "bg-amber-50 text-amber-700"],
    degraded: ["降级", "bg-amber-50 text-amber-700"],
  };
  const [label, cls] = map[state];
  return <span className={`rounded px-1.5 py-0.5 ${cls}`}>{label}</span>;
}

/** 检索记录的状态归一（与首页/历史页原有口径一致，不重复造判断）。 */
function searchState(record: UsageRecord): "ok" | "insufficient" | "failed" | "degraded" {
  if (record.answerable === null) {
    return record.degraded ? "degraded" : "insufficient";
  }
  return record.answerable ? "ok" : "insufficient";
}

/**
 * 详情弹窗（用户 2026-09-14："按键的时候点击可以弹个小窗，看到用户的输入，
 * 以及 LLM 的输出"）。
 *
 * 用原生 `<dialog>`（与 `ConfirmDialog` 同一理由：焦点陷阱、Esc、aria-modal 都是浏览器给的）。
 * 内容分两栏：输入 / 输出——**没有 LLM answer 时如实说明**，不留空白也不编造。
 */
function DetailDialog({ row, onClose }: { row: ActivityRow | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) return;
    if (row !== null && !dialog.open) dialog.showModal();
    if (row === null && dialog.open) dialog.close();
  }, [row]);

  return (
    <dialog
      ref={ref}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      className="w-full max-w-2xl rounded-lg border border-ink-line bg-paper-card p-0 shadow-xl backdrop:bg-ink-primary/40"
    >
      {row !== null && (
        <div className="p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold text-ink-primary">
              <KindBadge kind={row.kind} /> {row.title}
            </h2>
            <span className="text-xs text-ink-muted">
              {formatTime(row.at)} · {formatDuration(row.durationMs)}
            </span>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <DetailSection title="输入" items={row.input} />
            <DetailSection title="输出" items={row.output} />
          </div>

          {row.note && (
            <p className="mt-3 rounded border border-ink-line bg-paper-base px-3 py-2 text-xs text-ink-muted">
              {row.note}
            </p>
          )}

          <div className="mt-4 flex justify-end gap-2">
            {row.traceId && <CopyButton text={row.traceId} label="复制 trace id" />}
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-ink-line px-3 py-1.5 text-sm text-ink-primary hover:bg-paper-base"
            >
              关闭
            </button>
          </div>
        </div>
      )}
    </dialog>
  );
}

function DetailSection({
  title,
  items,
}: {
  title: string;
  items: { label: string; value: string }[];
}) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-medium text-ink-muted">{title}</h3>
      <dl className="space-y-1">
        {items.map((item) => (
          <div key={item.label} className="border-b border-dashed border-ink-line/60 pb-1">
            <dt className="text-xs text-ink-muted">{item.label}</dt>
            <dd className="break-words text-sm text-ink-primary">{item.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
