/**
 * 控制台首页（TASK-071；TASK-100 按用户 2026-09-14 要求精简）。
 *
 * 精简口径（用户原话："用户只是看数据，不需要知道这么多东西……保持高级感，专业"）：
 *
 * - **「索引」与「使用次数」合并成「工具调用」**：用户不知道索引/检索的内部概念，
 *   他只知道"我调了一次 Tool，成功还是失败，花了多久"。因此只留三个数字：
 *   成功、失败、平均耗时；
 * - **「项目」面板移出本页**（→ `/projects`）：项目是"管理"而非"看数据"，
 *   放同一页会让控制台变成大杂烩；
 * - **新增「服务模型」面板**：LLM 与 embedding 的最小必要信息
 *   （从设置页移来——它们是"当前生效值"，属于首屏该看的东西）；
 * - **删页脚版本说明**（`zace-web（Module 07 / D-40）…`）：用户不需要知道渲染链路。
 *
 * 保留「账户资料」：它是本页唯一的身份信息，用户需要确认"我是谁"。
 *
 * 面板口径（不许美化成好看的数字）：
 * - 未测量的一律显示 `—`（如 `citationCoverageAvg` 在 LLM 接入前恒为 null）；
 * - 索引耗时与检索耗时是**两个不同口径的平均值**（前者按索引 run，后者按查询），
 *   本页如实分开标注，不做无依据的加总。
 */

import { useCallback, useEffect, useState } from "react";

import { type AccountOverview, getAccountOverview } from "../api/client";
import { ErrorBlock, LoadingBlock, Page } from "../components/ui";
import { ServiceModels } from "../components/ServiceModels";

const WINDOW_DAYS = 30;

/**
 * 时间范围选择器（TASK-100，用户 2026-09-14："可选择范围时间，天为单位"）。
 *
 * 选项是**固定档位**而不是任意日期区间：用户要的是"看看最近怎么样"，
 * 固定档位一键切换即可；任意区间需要日期控件与后端区间查询（另开卡）。
 */
const RANGE_OPTIONS: [number, string][] = [
  [1, "今天"],
  [7, "近 7 天"],
  [30, "近 30 天"],
  [90, "近 90 天"],
];

function RangePicker({ days, onChange }: { days: number; onChange: (days: number) => void }) {
  return (
    <div className="flex overflow-hidden rounded border border-ink-line text-xs">
      {RANGE_OPTIONS.map(([value, label]) => (
        <button
          key={value}
          type="button"
          onClick={() => onChange(value)}
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
  );
}

export function DashboardPage() {
  const [data, setData] = useState<AccountOverview | null>(null);
  const [error, setError] = useState<unknown>(null);
  //: 时间窗口（天）。用户 2026-09-14 要求"可选择范围时间，天为单位"。
  const [days, setDays] = useState(WINDOW_DAYS);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await getAccountOverview(days));
    } catch (err) {
      setData(null);
      setError(err);
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error !== null) return <ErrorBlock error={error} />;
  if (data === null) return <LoadingBlock />;

  const { account: profile, index, usage } = data;

  return (
    <Page>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-lg font-semibold">控制台</h1>
        <RangePicker days={days} onChange={setDays} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="账户资料">
          <Row label="账户" value={profile.name} />
          <Row label="类型" value={profile.isLocal ? "本地单用户" : "云端账户"} />
          <Row label="创建时间" value={formatTime(profile.createdAt)} />
          <Row label="项目数" value={String(profile.projectCount)} />
        </Panel>

        <ServiceModels />
      </div>

      <Panel title={`工具调用（近 ${data.days} 天）`}>
        {/**
         * 用户 2026-09-14 定稿的 7 个数据（三行，虚线分隔，与「账户资料」同一种行样式）：
         *
         * | 行 | 数据 |
         * |---|---|
         * | 仓库初始化 | 次数 · 平均耗时 · 最快/最慢 |
         * | 检索 | 次数 · 平均耗时 |
         * | Tool 调用 | 成功 · 失败 |
         *
         * 用"仓库初始化"而不是"索引"：用户不知道索引/检索的内部概念，
         * 他只知道"我调了一次 Tool，成功还是失败，花了多久"。
         * 不加 hint 解释文字（用户："不要写解释了……这些字样，整体很乱"）。
         */}
        <StatRow
          label="仓库初始化"
          items={[
            ["次数", `${index.total} 次`],
            [
              "平均耗时",
              index.avgDurationMs === null ? "—" : formatDuration(index.avgDurationMs),
            ],
            [
              "最快 / 最慢",
              index.minDurationMs == null
                ? "—"
                : `${formatDuration(index.minDurationMs)} / ${formatDuration(index.maxDurationMs ?? 0)}`,
            ],
          ]}
        />
        <StatRow
          label="检索"
          items={[
            ["次数", `${usage.total} 次`],
            ["平均耗时", usage.avgLatencyMs === null ? "—" : `${usage.avgLatencyMs} ms`],
          ]}
        />
        <StatRow
          label="Tool 调用"
          items={[
            ["成功", String(usage.succeeded + index.succeeded), "ok"],
            ["失败", String(usage.failed + index.failed), "bad"],
          ]}
        />

        {usage.total === 0 && index.total === 0 && (
          <p className="mt-3 text-xs text-ink-muted">
            还没有调用记录——在 Agent 里问一句代码相关的问题，这里就会出现数据。
          </p>
        )}
      </Panel>
    </Page>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-ink-line bg-paper-card p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-ink-primary">{title}</h2>
      {children}
    </section>
  );
}

/**
 * 工具调用卡的一行：左侧分类名 + 右侧若干「指标 值」对，行间虚线分隔。
 *
 * 与「账户资料」的 `Row` 同一视觉语言（`border-dashed border-ink-line/70`）——
 * 用户 2026-09-14：“每行用虚线分开，类似账户资料里面那种虚线”。
 * 最后一行的虚线由调用方（`last:border-b-0`）控制：这里用 `space-y-0` + 末行去线。
 */
function StatRow({
  label,
  items,
}: {
  label: string;
  items: [string, string, ("ok" | "bad")?][];
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-8 gap-y-1 border-b border-dashed border-ink-line/70 py-2 last:border-b-0">
      <span className="w-20 shrink-0 text-xs text-ink-muted">{label}</span>
      {items.map(([key, value, tone]) => (
        <span key={key} className="flex items-baseline gap-2">
          <span className="text-xs text-ink-muted">{key}</span>
          <span
            className={`text-sm ${
              tone === "ok"
                ? "text-emerald-700"
                : tone === "bad"
                  ? "text-rose-700"
                  : "text-ink-primary"
            }`}
          >
            {value}
          </span>
        </span>
      ))}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-dashed border-ink-line/70 py-1.5">
      <span className="text-xs text-ink-muted">{label}</span>
      <span className="text-sm text-ink-primary">{value}</span>
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
