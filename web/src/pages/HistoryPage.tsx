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
/** 自动刷新间隔（毫秒）：用户 2026-09-14 要求"全局自动 10 秒刷新一次"。 */
const AUTO_REFRESH_MS = 10_000;

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
/**
 * 统一后的表格行（初始化与检索共用一个形状）。
 *
 * 弹窗内容分三层（TASK-100 用户 2026-09-14 定稿）：
 * 1. `input` → 「Tool 输入」代码块；
 * 2. `answer` → 「LLM 答案」代码块（仅检索有；未调 LLM 时为 `null`）；
 * 3. `metrics` → 底层元信息行（证据条数 / 文档条数 / 模式 / 体量）。
 */
type ActivityRow = {
  kind: "init" | "search";
  key: string;
  at: number;
  /** 项目名（两种类型都有——检索也属于某个项目）。 */
  project: string;
  /** 查询文本；仓库初始化没有它（`null` → 表格里显示 `—`）。 */
  query: string | null;
  state: "ok" | "insufficient" | "failed" | "degraded";
  durationMs: number;
  volume: { label: string; value: string };
  traceId: string | null;
  /** Tool 输入（代码块内容）。 */
  input: { label: string; value: string }[];
  /** LLM 答案正文；`null` = 未调 LLM（证据不足短路）或调用失败。 */
  answer: string | null;
  /** 非答案的输出信息（初始化看文件数/chunks，检索看证据/模式）。 */
  output: { label: string; value: string }[];
  /** 底层元信息（与 `output` 同源，展示位置不同：这里是页脚小字行）。 */
  metrics: { label: string; value: string }[];
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
  //: 最近一次成功刷新的时间（页头显示「数据更新于 HH:MM:SS」——用户 2026-09-14 要求简短）。
  const [refreshedAt, setRefreshedAt] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  /**
   * `rows` 的镜像 ref（TASK-099 前端收尾）：`load` 里需要知道"屏幕上此刻是否已有数据"，
   * 但 `rows` 是 `useMemo` 的产物、在 `load` 定义之后才算出。用 ref 把最近一次的值带过去，
   * 避免把 `rows` 加进 `load` 的依赖（那会让每次数据变化都重建 `load` → 重挂定时器）。
   */
  const rowsRef = useRef<ActivityRow[] | null>(null);

  /**
   * 拉取数据。
   *
   * `silent`（TASK-099 前端收尾，用户 2026-09-14 要求"不要白屏、要无感刷新"）：
   * - `silent=false`：`rows===null` 时显示 `LoadingBlock`，这是**首次进入**的正常首屏；
   * - `silent=true`（刷新按钮 / 自动刷新 / 切时间档位）：**不动任何正在展示的数据**，
   *   也不把 `rows` 置空，因此表格原样待着，新数据到了直接替换（React 只重渲染变化的行，不闪）。
   *
   * 为什么不用"先置空再填"：那正是白屏的来源——`rows` 一为 `null` 就渲染 `LoadingBlock`，
   * 整块表格消失。刷新是**更新**已有视图，不是重新进入页面。
   */
  const load = useCallback(
    async (options: { silent?: boolean } = {}) => {
      // **智能默认**（用户 2026-09-14 报的"低概率全白"的根因）：
      // 已经渲染过表格（`rows !== null`）时，任何刷新都不应再白屏。
      // 调用方不传 `silent` 时按"屏幕上是否已有数据"决定，而不是一律非静默——
      // 后者会让"切时间档位"这样的小动作把整张表拆掉重建。
      const silent = options.silent ?? rowsRef.current !== null;
      setError(null);
      if (!silent) setRunFailures([]);
      setLoading(true);
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
      setRefreshedAt(Date.now());
    } catch (err) {
      // 刷新失败**不清空已有数据**：把上一次成功的结果留在屏幕上（清空会让"网络抖一下"
      // 看起来像"记录全没了"），只显示错误横幅。
      setError(err);
    } finally {
      setLoading(false);
    }
    },
    [days],
  );

  useEffect(() => {
    void load();
  }, [load]);

  //: 自动刷新常开（用户 2026-09-14 定稿：不要开关，"后台存在新的请求就默认刷新一次"）。
  //:
  //: 两条纪律：① `load` 随 `days` 变化，因此切时间档位后定时器自动用新的窗口；
  //: ② 清理函数必须 clearInterval，否则每次挂载都叠一个定时器（请求数会指数增长）。
  useEffect(() => {
    const timer = window.setInterval(() => {
      // 自动刷新一律静默：用户可能正在看表格或读弹窗，不能让他眼前的东西消失。
      void load({ silent: true });
    }, AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
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
        kind: "init" as const,
        key: `init-${projectId}-${run.runId}`,
        at: run.finishedAt,
        project: nameOf(projectId),
        query: null,
        state: run.state === "done" ? ("ok" as const) : ("failed" as const),
        durationMs: run.durationMs,
        volume: { label: "chunks", value: String(run.chunks) },
        traceId: null,
        input: [
          { label: "项目", value: nameOf(projectId) },
          { label: "projectId", value: projectId },
        ],
        answer: null,
        output: [
          { label: "解析文件", value: `${run.filesProcessed} / ${run.filesTotal}` },
          { label: "chunks", value: String(run.chunks) },
          { label: "解析问题", value: run.errors > 0 ? `${run.errors} 个` : "无" },
        ],
        metrics: [
          { label: "解析文件", value: `${run.filesProcessed} / ${run.filesTotal}` },
          { label: "chunks", value: String(run.chunks) },
        ],
        ...(run.error ? { note: run.error } : {}),
      }));

    const searchRows: ActivityRow[] = usage.recent
      .filter((record) => record.createdAt >= since)
      .map((record) => ({
        kind: "search" as const,
        key: `search-${record.queryId}`,
        at: record.createdAt,
        project: nameOf(record.projectId),
        query: record.query,
        state: searchState(record),
        durationMs: record.latencyMs,
        volume: { label: "token", value: String(record.usedTokens) },
        traceId: record.requestId,
        input: [{ label: "查询", value: record.query }],
        // TASK-099 §A：answer 正文已落库；为 null 时用 answerStatus 说清是
        // “没调 LLM”（证据不足短路）还是“调了但失败”。
        answer: record.answerText,
        output: [
          { label: "证据条数", value: String(record.evidenceCount) },
          { label: "文档条数", value: String(record.docsCount) },
          { label: "模式", value: record.mode },
          ...(record.confidence ? [{ label: "confidence", value: record.confidence }] : []),
        ],
        metrics: [
          { label: "证据条数", value: String(record.evidenceCount) },
          { label: "文档条数", value: String(record.docsCount) },
          { label: "模式", value: record.mode },
          ...(record.confidence ? [{ label: "confidence", value: record.confidence }] : []),
          ...(record.answerStatus ? [{ label: "答案状态", value: record.answerStatus }] : []),
        ],
        note: record.answerText
          ? undefined
          : record.answerStatus === "insufficient_evidence"
            ? "证据不足（answerable=false）：按 D-24 短路，未调用 LLM。"
            : record.answerStatus === "degraded"
              ? "调用了 LLM 但失败（超时/不可达/形状不对）：本条没有答案正文。"
              : undefined,
      }));

    return [...initRows, ...searchRows].sort((left, right) => right.at - left.at);
  }, [runs, usage, days, nameOf]);

  // 把最新的 rows 写进 ref（供 load 判断"是否已有数据"）。
  rowsRef.current = rows;

  return (
    <div className="space-y-5">
      {/**
       * 页头排版（用户 2026-09-14）：`历史记录  刷新  数据更新于：HH:MM:SS`
       * ——刷新按钮**紧跟标题**（左侧），时间戳与时间范围靠右。
       *
       * 自动刷新**常开且不提供开关**（用户定稿）：它本来就是"后台有新请求就自动刷一次"，
       * 让用户管一个开关只会多一个要理解的概念；需要立即看最新的就点「刷新」。
       * 仍保留手动刷新：它有明确反馈价值（点下去能看到数据真的变了）。
       */}
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-lg font-semibold">历史记录</h1>
          <button
            type="button"
            onClick={() => void load({ silent: true })}
            disabled={loading}
            className="rounded border border-ink-line px-2.5 py-1 text-xs text-ink-primary hover:bg-paper-base disabled:opacity-50"
          >
            {loading ? "刷新中…" : "刷新"}
          </button>
          {/* 数据更新时间（用户：显示「数据更新于 HH:MM:SS」）。 */}
          {refreshedAt !== null && (
            <span className="text-xs text-ink-muted">
              数据更新于：{new Date(refreshedAt).toLocaleTimeString()}
            </span>
          )}
        </div>

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
                <th className="whitespace-nowrap px-3 py-2 font-normal">时间</th>
                <th className="whitespace-nowrap px-3 py-2 font-normal">类型</th>
                <th className="whitespace-nowrap px-3 py-2 font-normal">项目</th>
                <th className="px-3 py-2 font-normal">查询</th>
                <th className="whitespace-nowrap px-3 py-2 font-normal">trace id</th>
                <th className="whitespace-nowrap px-3 py-2 font-normal">结果</th>
                <th className="whitespace-nowrap px-3 py-2 font-normal">耗时</th>
                <th className="whitespace-nowrap px-3 py-2 font-normal">体量</th>
                <th className="whitespace-nowrap px-3 py-2 font-normal">详情</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className="border-t border-ink-line/60">
                  {/* 时间：**两行紧凑显示**（日期 + 时间）而不是一长串 — 用户反馈列太挤。 */}
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-ink-muted">
                    {formatShortDate(row.at)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs">
                    <KindBadge kind={row.kind} />
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">{row.project}</td>
                  {/* 查询列：完整宽度（占据剩余空间），单行截断。 */}
                  <td className="w-full max-w-0 px-3 py-2">
                    {row.query ? (
                      <span className="block truncate" title={row.query}>
                        {row.query}
                      </span>
                    ) : (
                      <span className="text-ink-muted">—</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs">
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
                  <td className="whitespace-nowrap px-3 py-2 text-xs">
                    <StateBadge state={row.state} />
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs">
                    {formatDuration(row.durationMs)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-ink-muted">
                    {row.volume.value} {row.volume.label}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">
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

/**
 * 时间列的紧凑格式：`9/14 19:38`（而不是 `9/14/2026, 7:38:03 PM`）。
 *
 * 为什么换格式（用户 2026-09-14 反馈"列太挤"）：完整 `toLocaleString()` 会输出
 * 二十多个字符，把时间列撑到最宽、又自动折成两行。历史记录看的是"最近发生了什么"，
 * 年份通常不必要；完整时间在「查看」弹窗里（那里用 `formatTime` 给全）。
 */
function formatShortDate(unixSeconds: number): string {
  if (!unixSeconds) return "—";
  const date = new Date(unixSeconds * 1000);
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${month}/${day} ${hh}:${mm}`;
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
 * 详情弹窗（用户 2026-09-14 两次反馈后的最终形态）：
 *
 * - **两个可滚动代码块**（`<pre>` + `overflow-auto` + `max-h`）分别包住 Tool 输入与输出；
 *   长 query 不再撑爆弹窗，也不用截断（内部出滚动条）；
 * - **标题不再写完整输入**（用户：“标题就不要写输入内容了，太长了”）：
 *   只写类型 + 时间 + 耗时，输入本身在代码块里；
 * - **元信息放在底层**（证据条数/文档条数/模式等）——用户：“其他底层有证据数量啊，
 *   文档条数这种信息”。
 *
 * 用原生 `<dialog>`（与 `ConfirmDialog` 同一理由：焦点陷阱、Esc、aria-modal 都是浏览器给的）。
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
      className="w-[min(90vw,52rem)] rounded-lg border border-ink-line bg-paper-card p-0 shadow-xl backdrop:bg-ink-primary/40"
    >
      {row !== null && (
        <div className="p-4">
          {/* 标题：只写"是什么·什么时候·多久"，不重复输入内容。 */}
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="flex items-baseline gap-2 text-sm font-semibold text-ink-primary">
              <KindBadge kind={row.kind} />
              <span>{row.project}</span>
            </h2>
            <span className="text-xs text-ink-muted">
              {formatTime(row.at)} · {formatDuration(row.durationMs)}
            </span>
          </div>

          <div className="mt-3 space-y-3">
            <CodeBlock label="Tool 输入" text={inputText(row)} />
            {/* LLM 答案：有正文就展示（可滚动）；没有就说清是哪种没有。 */}
            <CodeBlock label="LLM 答案" text={answerText(row)} />
            <CodeBlock label="Tool 输出" text={outputText(row)} />
          </div>

          {/** 底层元信息：证据条数 / 文档条数 / 模式 / confidence / 体量。 */}
          <MetaRow row={row} />

          {row.note && <p className="mt-2 text-xs text-ink-muted">{row.note}</p>}

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

/**
 * 可滚动代码块（用户：“两个代码块，可以下拉滑动条的那种”）。
 *
 * `max-h-[16rem]`（小屏）/`max-h-[22rem]`（大屏）+ `overflow-auto`：内容短时自然高度，
 * 长时内部出滚动条（**不出现横向撑破弹窗**：`whitespace-pre-wrap` 让长行自动折行）。
 */
function CodeBlock({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <div className="mb-1 text-xs text-ink-muted">{label}</div>
      <pre className="max-h-64 overflow-auto rounded border border-ink-line bg-paper-base p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-ink-primary">
        {text}
      </pre>
    </div>
  );
}

/** Tool 输入的纯文本形态（供代码块展示）。 */
function inputText(row: ActivityRow): string {
  return row.input.map((item) => `${item.label}：${item.value}`).join("\n");
}

/** Tool 输出的纯文本形态（供代码块展示）。 */
function outputText(row: ActivityRow): string {
  return row.output.map((item) => `${item.label}：${item.value}`).join("\n");
}

/**
 * LLM 答案的纯文本形态。
 *
 * `answer` 为 `null` 时**不编造**：按 `note` 的同一判断回一句说明，
 * 让用户一眼看出"这次没答案是因为证据不足"还是"调了但失败"。
 */
function answerText(row: ActivityRow): string {
  if (row.answer) return row.answer;
  if (row.kind === "init") return "（仓库初始化不调用 LLM）";
  if (row.note) return `（${row.note}）`;
  return "（本条没有答案正文）";
}

/** 底层元信息行：一行小字，不受代码块滚动影响。 */
function MetaRow({ row }: { row: ActivityRow }) {
  return (
    <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 border-t border-ink-line/60 pt-2">
      {row.metrics.map((item, index) => (
        <div key={`${item.label}-${index}`} className="flex items-baseline gap-1.5">
          <dt className="text-xs text-ink-muted">{item.label}</dt>
          <dd className="text-xs text-ink-primary">{item.value}</dd>
        </div>
      ))}
      <div className="flex items-baseline gap-1.5">
        <dt className="text-xs text-ink-muted">{row.volume.label}</dt>
        <dd className="text-xs text-ink-primary">{row.volume.value}</dd>
      </div>
    </dl>
  );
}
