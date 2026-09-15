/**
 * 管理员后台（TASK-110 §3.6 / §1.6）：五个模块，一个页面 + 标签切换。
 *
 * 为什么一个页面而不是五个路由：这五个模块是**同一个运营动作**的不同切片
 * （排查一个人 → 看他的项目 → 看他的调用），来回跳路由会让\"我刚刚看的是谁\"断掉。
 * 标签切换保留上下文，且与卡内\"后台五模块\"的表述一一对应。
 *
 * 两条纪律：
 *
 * 1. **入口由后端决定**：本页只在 ``account.capabilities.isAdmin`` 为真时可达
 *    （路由层与侧边栏都看它），前端不自己写 ``role === \"admin\"``；
 * 2. **不重算后端已算好的数**：占用用 ``usedText``、额度用 ``effectiveQuotaBytes``——
 *    自己换算单位会与账户页在舍入上漂移。
 */

import { useCallback, useEffect, useState } from "react";

import {
  type AdminProject,
  type AdminStats,
  type AdminUser,
  type Invite,
  createAdminInvite,
  getAdminStats,
  getAdminSystem,
  listAdminInvites,
  listAdminProjects,
  listAdminUsers,
  patchAdminUser,
  revokeAdminInvite,
} from "../api/client";
import { EmptyState, ErrorBlock, LoadingBlock, Page } from "../components/ui";
import { formatBytes } from "./AccountPage";
import { formatTime } from "./DashboardPage";

type Tab = "users" | "invites" | "projects" | "stats" | "system";

const TABS: [Tab, string][] = [
  ["users", "用户"],
  ["invites", "邀请码"],
  ["projects", "项目"],
  ["stats", "调用统计"],
  ["system", "系统状态"],
];

const ROLE_OPTIONS: [string, string][] = [
  ["public", "公测（旅人）"],
  ["beta", "内测（拓荒者）"],
  ["admin", "管理员（执炬者）"],
];

export function AdminPage() {
  const [tab, setTab] = useState<Tab>("users");
  return (
    <Page>
      <div>
        <h1 className="text-lg font-semibold">管理后台</h1>
        <p className="mt-1 text-sm text-ink-muted">运营与排查工具（仅管理员可见）。</p>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-ink-line pb-2 text-sm">
        {TABS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setTab(value)}
            className={`rounded px-3 py-1.5 ${
              tab === value
                ? "bg-accent-seal text-white"
                : "text-ink-muted hover:bg-paper-base hover:text-ink-primary"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "users" && <UsersTab />}
      {tab === "invites" && <InvitesTab />}
      {tab === "projects" && <ProjectsTab />}
      {tab === "stats" && <StatsTab />}
      {tab === "system" && <SystemTab />}
    </Page>
  );
}

// --------------------------------------------------------------------------- 用户

function UsersTab() {
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setUsers((await listAdminUsers()).users);
    } catch (err) {
      setUsers(null);
      setError(err);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function patch(userId: string, body: Parameters<typeof patchAdminUser>[1]) {
    setBusy(true);
    setError(null);
    try {
      await patchAdminUser(userId, body);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (error !== null) return <ErrorBlock error={error} />;
  if (users === null) return <LoadingBlock />;

  return (
    <section className="rounded-lg border border-ink-line bg-paper-card shadow-sm">
      {users.length === 0 ? (
        <EmptyState title="还没有用户" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-muted">
                <Th>账户</Th>
                <Th>身份</Th>
                <Th>项目</Th>
                <Th>索引占用</Th>
                <Th>额度</Th>
                <Th>检索次数</Th>
                <Th>最后活跃</Th>
                <Th>操作</Th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.userId} className="border-t border-ink-line/60">
                  <td className="px-4 py-2">
                    <span className="text-ink-primary">{user.name}</span>
                    {user.bannedAt !== null && (
                      <span className="ml-2 rounded bg-rose-100 px-1.5 py-0.5 text-xs text-rose-700">
                        已封禁
                      </span>
                    )}
                    <div className="text-xs text-ink-muted">
                      注册于 {formatTime(user.createdAt)}
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    <select
                      value={user.role}
                      disabled={busy}
                      onChange={(event) => void patch(user.userId, { role: event.target.value })}
                      className="rounded border border-ink-line bg-paper-card px-2 py-1 text-xs"
                    >
                      {ROLE_OPTIONS.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                    {user.earlyMemberNo !== null && (
                      <div className="mt-1 font-mono text-xs text-ink-muted">
                        #{String(user.earlyMemberNo).padStart(3, "0")}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs">{user.projectCount}</td>
                  <td className="px-4 py-2 text-xs">{user.usedText}</td>
                  <td className="px-4 py-2 text-xs">
                    {formatBytes(user.effectiveQuotaBytes)}
                    {user.quotaBytes !== null && (
                      <div className="text-[11px] text-ink-muted">（人工指定）</div>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs">{user.queryCount}</td>
                  <td className="px-4 py-2 text-xs text-ink-muted">
                    {user.lastSeenAt === null ? "—" : formatTime(user.lastSeenAt)}
                  </td>
                  <td className="px-4 py-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void patch(user.userId, { banned: user.bannedAt === null })}
                      className={`rounded border px-2 py-1 text-xs ${
                        user.bannedAt === null
                          ? "border-rose-300 text-rose-700 hover:bg-rose-50"
                          : "border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                      }`}
                    >
                      {user.bannedAt === null ? "封禁" : "恢复"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------- 邀请码

function InvitesTab() {
  const [invites, setInvites] = useState<Invite[] | null>(null);
  const [kinds, setKinds] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [kind, setKind] = useState("C");
  const [maxUses, setMaxUses] = useState(1);
  const [expiresInDays, setExpiresInDays] = useState<string>("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const body = await listAdminInvites();
      setInvites(body.invites);
      setKinds(body.kinds);
    } catch (err) {
      setInvites(null);
      setError(err);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createAdminInvite({
        kind,
        maxUses,
        expiresInDays: expiresInDays.trim() === "" ? null : Number(expiresInDays),
        code: code.trim().toUpperCase(),
      });
      setCode("");
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function onRevoke(target: string) {
    if (!window.confirm(`确认失效邀请码 ${target}？`)) return;
    try {
      await revokeAdminInvite(target);
      await load();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <div className="space-y-4">
      {error !== null && <ErrorBlock error={error} />}

      <form
        onSubmit={onCreate}
        className="flex flex-wrap items-end gap-3 rounded-lg border border-ink-line bg-paper-card p-4 shadow-sm"
      >
        <label className="text-sm">
          <span className="mb-1 block text-xs text-ink-muted">类型</span>
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value)}
            className="rounded border border-ink-line bg-paper-card px-3 py-1.5 text-sm"
          >
            <option value="A">A · 管理员</option>
            <option value="B">B · 内测（拓荒者）</option>
            <option value="C">C · 公测（旅人）</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-ink-muted">可用次数</span>
          <input
            type="number"
            min={1}
            max={10000}
            value={maxUses}
            onChange={(event) => setMaxUses(Number(event.target.value))}
            className="w-24 rounded border border-ink-line bg-paper-card px-3 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-ink-muted">有效期（天，空 = 永久）</span>
          <input
            type="number"
            min={1}
            max={3650}
            value={expiresInDays}
            onChange={(event) => setExpiresInDays(event.target.value)}
            placeholder="永久"
            className="w-32 rounded border border-ink-line bg-paper-card px-3 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-ink-muted">指定码面（空 = 随机）</span>
          <input
            value={code}
            onChange={(event) => setCode(event.target.value.toUpperCase())}
            maxLength={6}
            placeholder="如 B7K2M9"
            className="w-32 rounded border border-ink-line bg-paper-card px-3 py-1.5 font-mono text-sm tracking-widest"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-accent-seal px-4 py-1.5 text-sm text-white disabled:opacity-40"
        >
          {busy ? "创建中…" : "创建邀请码"}
        </button>
      </form>

      <section className="rounded-lg border border-ink-line bg-paper-card shadow-sm">
        {invites === null ? (
          <LoadingBlock />
        ) : invites.length === 0 ? (
          <EmptyState title="还没有邀请码" hint="用上方表单创建第一张。" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs text-ink-muted">
                  <Th>码</Th>
                  <Th>类型</Th>
                  <Th>使用</Th>
                  <Th>有效期</Th>
                  <Th>使用记录</Th>
                  <Th>状态</Th>
                  <Th>操作</Th>
                </tr>
              </thead>
              <tbody>
                {invites.map((invite) => (
                  <tr key={invite.code} className="border-t border-ink-line/60">
                    <td className="px-4 py-2 font-mono text-xs tracking-widest">
                      {invite.code}
                    </td>
                    <td className="px-4 py-2 text-xs">
                      {invite.kind} · {kinds[invite.kind] ?? "—"}
                    </td>
                    <td className="px-4 py-2 text-xs">
                      {invite.usedCount} / {invite.maxUses}
                    </td>
                    <td className="px-4 py-2 text-xs text-ink-muted">
                      {invite.expiresAt === null ? "永久" : formatTime(invite.expiresAt)}
                    </td>
                    <td className="px-4 py-2 text-xs text-ink-muted">
                      {(invite.uses ?? []).length === 0
                        ? "—"
                        : (invite.uses ?? [])
                            .map(
                              (use) =>
                                `${use.userName ?? use.userId.slice(0, 6)} @ ${formatTime(use.usedAt)}`,
                            )
                            .join("；")}
                    </td>
                    <td className="px-4 py-2 text-xs">
                      {invite.revokedAt !== null ? (
                        <span className="text-rose-700">已失效</span>
                      ) : (
                        <span className="text-emerald-700">有效</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {invite.revokedAt === null && (
                        <button
                          type="button"
                          onClick={() => void onRevoke(invite.code)}
                          className="rounded border border-rose-300 px-2 py-1 text-xs text-rose-700 hover:bg-rose-50"
                        >
                          失效
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

// --------------------------------------------------------------------------- 项目

function ProjectsTab() {
  const [projects, setProjects] = useState<AdminProject[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    void (async () => {
      try {
        setProjects((await listAdminProjects()).projects);
      } catch (err) {
        setError(err);
      }
    })();
  }, []);

  if (error !== null) return <ErrorBlock error={error} />;
  if (projects === null) return <LoadingBlock />;

  return (
    <section className="rounded-lg border border-ink-line bg-paper-card shadow-sm">
      {projects.length === 0 ? (
        <EmptyState title="还没有项目" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-muted">
                <Th>项目</Th>
                <Th>归属</Th>
                <Th>占用</Th>
                <Th>索引历史</Th>
                <Th>最近状态</Th>
                <Th>失败原因 / 跳过</Th>
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => (
                <tr key={project.projectId} className="border-t border-ink-line/60">
                  <td className="px-4 py-2">
                    <span className="text-ink-primary">
                      {project.displayName || project.projectId}
                    </span>
                    <div className="font-mono text-[11px] text-ink-muted">
                      {project.projectId}
                    </div>
                    {project.attachedRoot && (
                      <div className="font-mono text-[11px] text-ink-muted">
                        {project.attachedRoot}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2 font-mono text-[11px] text-ink-muted">
                    {project.ownerId ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-xs">{formatBytes(project.diskBytes)}</td>
                  <td className="px-4 py-2 text-xs">
                    共 {project.history.total} · 成功 {project.history.succeeded} · 失败{" "}
                    {project.history.failed}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {project.history.lastState ?? "—"}
                    <div className="text-[11px] text-ink-muted">
                      {project.history.lastRunAt === null
                        ? "—"
                        : formatTime(project.history.lastRunAt)}
                    </div>
                  </td>
                  <td className="max-w-xs px-4 py-2 text-xs">
                    {project.lastError ? (
                      <span className="break-all text-rose-700">{project.lastError}</span>
                    ) : (
                      <span className="text-ink-muted">—</span>
                    )}
                    {project.lastSkipped !== null && project.lastSkipped > 0 && (
                      <div className="text-[11px] text-ink-muted">
                        上次跳过 {project.lastSkipped} 个文件
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------- 统计

function StatsTab() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    void (async () => {
      try {
        setStats(await getAdminStats());
      } catch (err) {
        setError(err);
      }
    })();
  }, []);

  if (error !== null) return <ErrorBlock error={error} />;
  if (stats === null) return <LoadingBlock />;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Panel title={`检索 / 提问（近 ${stats.days} 天）`}>
        <Row label="总调用" value={`${stats.search.total} 次`} />
        <Row label="有答案" value={String(stats.search.succeeded)} />
        <Row label="证据不足" value={String(stats.search.insufficient)} />
        <Row label="降级失败" value={String(stats.search.failed)} />
        <Row
          label="错误率"
          value={stats.errorRate === null ? "—" : `${(stats.errorRate * 100).toFixed(1)}%`}
        />
        <Row label="Token 用量" value={String(stats.tokens)} />
        <Row
          label="平均耗时"
          value={stats.search.avgLatencyMs === null ? "—" : `${stats.search.avgLatencyMs} ms`}
        />
        <Row
          label="P95 耗时"
          value={stats.search.p95LatencyMs === null ? "—" : `${stats.search.p95LatencyMs} ms`}
        />
      </Panel>

      <Panel title="索引（全库）">
        <Row label="项目数" value={String(stats.projectCount)} />
        <Row label="总次数" value={String(stats.index.total)} />
        <Row label="成功" value={String(stats.index.succeeded)} />
        <Row label="失败" value={String(stats.index.failed)} />
        <Row
          label="平均耗时"
          value={stats.index.avgDurationMs === null ? "—" : `${stats.index.avgDurationMs} ms`}
        />
      </Panel>
    </div>
  );
}

// --------------------------------------------------------------------------- 系统

function SystemTab() {
  const [health, setHealth] = useState<Awaited<ReturnType<typeof getAdminSystem>> | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    void (async () => {
      try {
        setHealth(await getAdminSystem());
      } catch (err) {
        setError(err);
      }
    })();
  }, []);

  if (error !== null) return <ErrorBlock error={error} />;
  if (health === null) return <LoadingBlock />;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Panel title="服务">
        <Row label="状态" value={health.status} />
        <Row label="版本" value={health.version} />
        <Row label="部署形态" value={health.localMode ? "本地单用户" : "云端"} />
        <Row label="鉴权" value={health.auth} />
        <Row label="数据根" value={<span className="font-mono text-xs">{health.dataRoot}</span>} />
      </Panel>
      <Panel title="Embedding / LLM">
        <Row label="core 可导入" value={health.core.importable ? "是" : "否"} />
        {health.core.ok !== undefined && (
          <Row label="provider 探测" value={health.core.ok ? "正常" : "异常"} />
        )}
        {health.core.modelId && <Row label="模型" value={health.core.modelId} />}
        {health.core.dim !== undefined && <Row label="维度" value={String(health.core.dim)} />}
        {health.core.reason && (
          <Row
            label="原因"
            value={<span className="break-all text-rose-700">{health.core.reason}</span>}
          />
        )}
      </Panel>
    </div>
  );
}

// --------------------------------------------------------------------------- 小组件

function Th({ children }: { children: React.ReactNode }) {
  return <th className="px-4 py-2 font-normal">{children}</th>;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-ink-line bg-paper-card p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-ink-primary">{title}</h2>
      <dl className="divide-y divide-dashed divide-ink-line/70 text-sm">{children}</dl>
    </section>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="text-ink-primary">{value}</dd>
    </div>
  );
}