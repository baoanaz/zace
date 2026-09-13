/** 项目总览（Module/07 §1「Project List」）：状态即数据，不做推算（§2.3）。 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  ApiError,
  attachProject,
  deleteProject,
  getHealth,
  listProjects,
  rescanProject,
  type ApiError as ApiErrorType,
} from "../api/client";
import type { Health, Project } from "../api/types";
import { describeIndexProgress } from "../components/progress";
import { Badge, Card, ErrorBlock, KeyValue, LoadingBlock } from "../components/ui";

export function ProjectsPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      // healthz 与 projects 都调：healthz 给出 localMode/版本/内存态进度，projects 给出账本统计。
      const [h, p] = await Promise.all([getHealth(), listProjects()]);
      setHealth(h);
      setProjects(p);
    } catch (err) {
      setHealth(null);
      setProjects(null);
      setError(err);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onRescan(projectId: string) {
    setNotice(null);
    try {
      await rescanProject(projectId);
      setNotice(`已触发重扫：${projectId}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "index_running") {
        setNotice("该项目的索引已在运行，无需重复触发。");
      } else {
        setError(err);
      }
    }
    void load();
  }

  async function onDelete(projectId: string, name: string) {
    const confirmed = window.confirm(
      `确认删除项目「${name}」？\n\n` +
        "全部源码镜像与索引将永久删除（blobs + index.db + vectors），不可恢复。无软删除期。",
    );
    if (!confirmed) return;
    try {
      await deleteProject(projectId);
      setNotice(`已删除：${projectId}`);
    } catch (err) {
      setError(err);
    }
    void load();
  }

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-semibold">项目</h1>

      {error !== null && <ErrorBlock error={error} />}
      {notice && (
        <p className="rounded border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
          {notice}
        </p>
      )}

      {health && <ServiceCard health={health} onReload={() => void load()} />}
      {health?.localMode && <AttachCard onDone={() => void load()} />}

      {projects === null && error === null && <LoadingBlock />}
      {projects !== null && projects.length === 0 && (
        <Card title="还没有项目">
          <p className="text-sm text-slate-700">
            本地模式下用下方的「绑定本地目录」表单，或命令行：
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-100">
            uv run zace-service local --repo /绝对路径/你的仓库
          </pre>
          <p className="mt-2 text-xs text-slate-500">
            远端形态（客户端上传）请见 <Link className="underline" to="/connect">接入指南</Link>。
          </p>
        </Card>
      )}

      {projects?.map((project) => (
        <ProjectCard
          key={project.projectId}
          project={project}
          onRescan={() => void onRescan(project.projectId)}
          onDelete={() => void onDelete(project.projectId, project.displayName || project.projectId)}
        />
      ))}
    </div>
  );
}

function ServiceCard({ health, onReload }: { health: Health; onReload: () => void }) {
  return (
    <Card
      title="服务"
      actions={
        <button
          type="button"
          onClick={onReload}
          className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
        >
          刷新
        </button>
      }
    >
      <KeyValue
        items={[
          ["版本", health.version],
          ["模式", health.localMode ? "本地单用户（无鉴权，R34）" : "远端（需鉴权）"],
          ["auth", health.auth],
          ["dataRoot", <code className="font-mono text-xs">{health.dataRoot}</code>],
          [
            "core",
            health.core.importable ? (
              <Badge tone="done">importable</Badge>
            ) : (
              <Badge tone="failed">不可导入</Badge>
            ),
          ],
        ]}
      />
    </Card>
  );
}

function AttachCard({ onDone }: { onDone: () => void }) {
  const [root, setRoot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiErrorType | unknown>(null);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await attachProject(root.trim());
      setRoot("");
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="绑定本地目录（本地模式）">
      <form onSubmit={onSubmit} className="space-y-2">
        <div className="flex flex-wrap gap-2">
          <input
            value={root}
            onChange={(event) => setRoot(event.target.value)}
            placeholder="/绝对路径/你的仓库"
            className="min-w-[20rem] flex-1 rounded border border-slate-300 px-3 py-1.5 font-mono text-sm"
          />
          <button
            type="submit"
            disabled={busy || root.trim().length === 0}
            className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          >
            {busy ? "绑定中…" : "绑定并后台索引"}
          </button>
        </div>
        <p className="text-xs text-slate-500">
          立即返回，不等索引完成（D-31）；索引进度在项目卡片上如实显示。
        </p>
        {error !== null && <ErrorBlock error={error} />}
      </form>
    </Card>
  );
}

function ProjectCard({
  project,
  onRescan,
  onDelete,
}: {
  project: Project;
  onRescan: () => void;
  onDelete: () => void;
}) {
  const view = describeIndexProgress(project.indexProgress);
  const sync = project.sync ?? {};

  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-2">
          {project.displayName || project.projectId}
          <Badge tone={view.tone}>{view.label}</Badge>
        </span>
      }
      actions={
        <div className="flex gap-2">
          <Link
            to={`/playground?project=${encodeURIComponent(project.projectId)}`}
            className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
          >
            去 Playground
          </Link>
          <button
            type="button"
            onClick={onRescan}
            className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
          >
            重扫
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded border border-rose-300 px-2 py-1 text-xs text-rose-700 hover:bg-rose-50"
          >
            删除
          </button>
        </div>
      }
    >
      <div className="space-y-2">
        <p className="font-mono text-xs text-slate-500">{project.projectId}</p>
        {view.detail && <p className="text-sm text-slate-700">{view.detail}</p>}
        {view.error && (
          <p className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-900">
            {view.error}
          </p>
        )}
        <KeyValue
          items={[
            ["files", String(sync.filesIndexed ?? "—")],
            ["chunks", String(sync.chunks ?? "—")],
            ["symbols", String(sync.symbols ?? "—")],
            ["edges", String(sync.edges ?? "—")],
            ["attachedRoot", project.attachedRoot ?? "—"],
            ["lastIndexedAt", sync.lastIndexedAt ? formatStamp(sync.lastIndexedAt) : "—"],
          ]}
        />
        <Link className="text-xs underline" to={`/projects/${encodeURIComponent(project.projectId)}`}>
          详情
        </Link>
      </div>
    </Card>
  );
}

function formatStamp(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleString();
}
