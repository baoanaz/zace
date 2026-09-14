/**
 * 首页仪表盘/控制台（TASK-071）：**只放账户资料与数据面板**（用户 2026-09-13 指定）。
 *
 * 面板口径（不许美化成好看的数字）：
 * - `avgDurationMs` **只统计成功的索引**——失败 run 的耗时是"失败得多快"；
 * - `processedFiles/totalFiles` 不同量纲，不做除法、**不显示百分比**；
 * - 未测量的一律显示 `—`（如 `citationCoverageAvg` 在 LLM 接入前恒为 null）。
 *
 * TASK-083：空态改由 `EmptyState` 渲染（每处都说明"怎样才会有数据"）；
 * `sumDisk` 不再把"后端未提供 `diskBytes`"伪装成"占用 0"。
 *
 * TASK-086：页面名从「账户」改为「控制台」；删掉「最近索引」记录面板（历史页的
 * 「索引记录」页签已覆盖该职能）。**「账户资料」是面板名，不是页面名，保持不变。**
 *
 * TASK-094：§A 项目表加「占用」列（未提供时显示 `—`）、§B4 顶部配额提示、§D 删除入口
 * （二次确认；**取消不发请求**；删除后重新拉取列表，不留残影）。
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  type Account,
  type AccountOverview,
  type QuotaStatusView,
  deleteProject,
  getAccountOverview,
} from "../api/client";
import { ConfirmDialog, EmptyState, ErrorBlock, LoadingBlock } from "../components/ui";

const WINDOW_DAYS = 30;

/** 待删除的项目（非 null 时弹二次确认；**不直接发请求**）。 */
type PendingDelete = { projectId: string; name: string };

export function DashboardPage({ account }: { account: Account | null }) {
  const [data, setData] = useState<AccountOverview | null>(null);
  const [error, setError] = useState<unknown>(null);
  //: 删除流程的独立状态：**不要**复用页面级 `error`，否则一次删除失败会把整个控制台换成错误页。
  const [pending, setPending] = useState<PendingDelete | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<unknown>(null);

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

  const confirmDelete = useCallback(async () => {
    if (pending === null) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteProject(pending.projectId);
      setPending(null);
      // 删除后**重新拉取**：不能只把该行从本地数组里滤掉——占用/统计都变了，
      // 本地删行会留下一份与后端不一致的旧数字（"残影"）。
      await load();
    } catch (err) {
      // 失败如实报错（404/网络错误都不静默）：保留弹窗，让用户看到原因再决定。
      setDeleteError(err);
    } finally {
      setDeleting(false);
    }
  }, [pending, load]);

  if (error !== null) return <ErrorBlock error={error} />;
  if (data === null) return <LoadingBlock />;

  const { account: profile, index, usage } = data;

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-semibold">控制台</h1>

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
          {data.storage !== undefined && <StorageBar storage={data.storage} />}
        </Panel>
      </div>

      {/*
       * TASK-086 §3：「最近索引」记录面板已删（用户："有专门的历史记录去看就行"）。
       * 「使用次数」因此从两列半边改为整宽——它原本靠一个 grid-cols-1 lg:grid-cols-2
       * 与已删面板并排；留着会被拉成半宽、右边真空。
       * 不删：「索引（近 N 天）」与「使用次数」两个统计面板（用户未要求）。
       */}
      <Panel title={`使用次数（近 ${data.days} 天）`}>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Metric label="查询总数" value={String(usage.total)} />
          <Metric label="有答案" value={String(usage.succeeded)} tone="ok" />
          <Metric label="证据不足" value={String(usage.insufficient)} tone={usage.insufficient > 0 ? "warn" : "muted"} />
          <Metric label="失败" value={String(usage.failed)} tone={usage.failed > 0 ? "bad" : "muted"} />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Metric
            label="平均耗时"
            value={usage.avgLatencyMs === null ? "—" : `${usage.avgLatencyMs} ms`}
          />
          <Metric
            label="P95 耗时"
            value={usage.p95LatencyMs === null ? "—" : `${usage.p95LatencyMs} ms`}
          />
        </div>
        <p className="mt-3 text-xs text-ink-muted">
          引用覆盖率：{usage.citationCoverageAvg === null ? "— 尚未测量（LLM 总结未接入）" : `${(usage.citationCoverageAvg * 100).toFixed(1)}%`}
        </p>
      </Panel>

      <Panel title="项目">
        {deleteError !== null && (
          <div className="mb-3">
            <ErrorBlock error={deleteError} />
          </div>
        )}
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
              <tr className="text-left text-xs text-ink-muted">
                <th className="border-b border-ink-line py-1">项目</th>
                <th className="border-b border-ink-line py-1">projectId</th>
                <th className="border-b border-ink-line py-1">文件</th>
                <th className="border-b border-ink-line py-1">chunks</th>
                <th className="border-b border-ink-line py-1">状态</th>
                <th className="border-b border-ink-line py-1" title="索引数据磁盘占用">
                  占用
                </th>
                <th className="border-b border-ink-line py-1">操作</th>
              </tr>
            </thead>
            <tbody>
              {data.projects.map((project) => (
                <tr key={project.projectId}>
                  <td className="border-b border-ink-line/60 py-1">
                    {project.displayName || project.projectId}
                  </td>
                  <td className="border-b border-ink-line/60 py-1 font-mono text-xs">
                    {project.projectId}
                  </td>
                  <td className="border-b border-ink-line/60 py-1">
                    {project.sync?.filesIndexed ?? "—"}
                  </td>
                  <td className="border-b border-ink-line/60 py-1">{project.sync?.chunks ?? "—"}</td>
                  <td className="border-b border-ink-line/60 py-1 text-xs">
                    {project.indexProgress?.state ?? "—"}
                  </td>
                  {/* 占用：后端未提供时 `—`（不把"未测量"伪装成 0 B）。 */}
                  <td
                    className="border-b border-ink-line/60 py-1"
                    data-testid={`disk-${project.projectId}`}
                  >
                    {project.diskBytes == null ? "—" : formatBytes(project.diskBytes)}
                  </td>
                  <td className="border-b border-ink-line/60 py-1">
                    <button
                      type="button"
                      onClick={() =>
                        setPending({
                          projectId: project.projectId,
                          name: project.displayName || project.projectId,
                        })
                      }
                      className="rounded border border-rose-200 px-2 py-0.5 text-xs text-rose-700 hover:bg-rose-50"
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="mt-2 text-xs text-ink-muted">
          「占用」是索引数据的磁盘占用（index.db + 向量 + 源码镜像），**不含源码仓库本身**；
          后端未提供时显示 —（不当作 0）。
        </p>
      </Panel>

      <ConfirmDialog
        open={pending !== null}
        title={`删除项目 ${pending?.name ?? ""}？`}
        confirmLabel="删除索引数据"
        busy={deleting}
        onConfirm={() => void confirmDelete()}
        onCancel={() => {
          // 取消**不发请求**（只关弹窗）；顺手清掉上一次的删除错误，避免下次点开时残留。
          setPending(null);
          setDeleteError(null);
        }}
      >
        <p>将删除该项目的**全部索引数据**（含向量与同步账本）。</p>
        <p>源码文件不受影响；下次 Agent 提问时会重新上传并索引。</p>
        <p className="text-xs text-ink-muted">
          projectId：<code className="font-mono">{pending?.projectId ?? ""}</code>
        </p>
      </ConfirmDialog>
    </div>
  );
}

/**
 * 存储配额条（TASK-094 §B4）：已用 / 上限 + 三态颜色。
 *
 * 口径：**不限时只显示已用**（不画进度条、不显示百分比）——“没有上限”不是“用了 0%”。
 * 这与后端 :class:`zace_service.quota.QuotaDimension` 的 `unlimited` 语义一一对应。
 */
function StorageBar({ storage }: { storage: QuotaStatusView }) {
  const { user } = storage;
  const tone =
    storage.status === "exceeded"
      ? { bar: "bg-rose-500", text: "text-rose-700", label: "已超出上限" }
      : storage.status === "warning"
        ? { bar: "bg-amber-500", text: "text-amber-700", label: "接近上限" }
        : { bar: "bg-emerald-500", text: "text-emerald-700", label: "正常" };

  return (
    <div className="mt-4 border-t border-ink-line/60 pt-3" data-testid="storage-quota">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-xs text-ink-muted">存储配额（索引数据）</span>
        <span className={`text-xs font-medium ${user.unlimited ? "text-ink-muted" : tone.text}`}>
          {user.unlimited
            ? `已用 ${formatBytes(user.usedBytes)} · 未设上限`
            : `已用 ${formatBytes(user.usedBytes)} / 上限 ${formatBytes(user.limitBytes)}`}
          {!user.unlimited && user.ratio !== null && `（${(user.ratio * 100).toFixed(0)}%）`}
        </span>
      </div>
      {!user.unlimited && (
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded bg-paper-raised">
          <div
            className={`h-full ${tone.bar}`}
            // 宽度封顶 100%：超限时进度条不能撑破容器（比例由文字如实给出）。
            style={{ width: `${Math.min(100, (user.ratio ?? 0) * 100).toFixed(1)}%` }}
          />
        </div>
      )}
      {storage.status !== "ok" && (
        <p className={`mt-2 text-xs ${tone.text}`}>
          {tone.label}：可在下方「项目」表按占用从大到小判断该删哪个；
          删除只影响索引数据，源码文件不受影响。
        </p>
      )}
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
      className={`rounded-lg border border-ink-line bg-paper-card p-4 shadow-sm ${className}`}
    >
      <h2 className="mb-3 text-sm font-semibold text-ink-primary">{title}</h2>
      {children}
    </section>
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
          : "text-ink-primary";
  return (
    <div>
      <div className="text-xs text-ink-muted">{label}</div>
      <div className={`text-xl font-semibold ${color}`}>{value}</div>
      {hint && <div className="text-xs text-ink-muted">{hint}</div>}
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
