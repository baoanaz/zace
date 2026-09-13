/** 项目详情（Module/07 §1「Project Detail」）：索引统计 + sync 状态 + 删除。 */

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError, deleteProject, getProject, rescanProject } from "../api/client";
import type { Project } from "../api/types";
import { describeIndexProgress } from "../components/progress";
import { Badge, Card, ErrorBlock, KeyValue, LoadingBlock } from "../components/ui";

export function ProjectDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setProject(await getProject(id));
    } catch (err) {
      setProject(null);
      setError(err);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onRescan() {
    setNotice(null);
    try {
      await rescanProject(id);
      setNotice("已触发重扫，进度见下方（索引期间无百分比）。");
    } catch (err) {
      if (err instanceof ApiError && err.code === "index_running") {
        setNotice("索引已在运行。");
      } else {
        setError(err);
      }
    }
    void load();
  }

  async function onDelete() {
    const confirmed = window.confirm(
      "确认删除该项目？\n\n全部源码镜像与索引将永久删除（blobs + index.db + vectors），不可恢复。",
    );
    if (!confirmed) return;
    try {
      await deleteProject(id);
      navigate("/");
    } catch (err) {
      setError(err);
    }
  }

  if (project === null && error === null) return <LoadingBlock />;
  if (error !== null) return <ErrorBlock error={error} />;
  if (project === null) return null;

  const view = describeIndexProgress(project.indexProgress);
  const sync = project.sync ?? {};

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">{project.displayName || project.projectId}</h1>
        <Badge tone={view.tone}>{view.label}</Badge>
        <Link className="text-sm underline" to={`/playground?project=${encodeURIComponent(project.projectId)}`}>
          去 Playground
        </Link>
      </div>

      {notice && <p className="rounded border border-slate-200 bg-white px-3 py-2 text-sm">{notice}</p>}

      <Card title="索引">
        {view.detail && <p className="mb-3 text-sm text-slate-700">{view.detail}</p>}
        {view.error && (
          <p className="mb-3 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-900">
            {view.error}
          </p>
        )}
        <KeyValue
          items={[
            ["indexProgress.state", project.indexProgress?.state ?? "—"],
            ["processedFiles", String(project.indexProgress?.processedFiles ?? "—")],
            [
              "totalFiles",
              `${project.indexProgress?.totalFiles ?? "—"}（含解析层会跳过的二进制/超限文件）`,
            ],
            [
              "startedAt / finishedAt",
              `${stamp(project.indexProgress?.startedAt)} / ${stamp(project.indexProgress?.finishedAt)}`,
            ],
          ]}
        />
        <p className="mt-2 text-xs text-slate-500">
          `processedFiles` 与 `totalFiles` 不是同一量纲，差值不代表"失败"；增量重扫无改动时为 0 属正常。
        </p>
      </Card>

      <Card title="账本（sync）">
        <KeyValue
          items={[
            ["filesIndexed", String(sync.filesIndexed ?? "—")],
            ["chunks", String(sync.chunks ?? "—")],
            ["symbols", String(sync.symbols ?? "—")],
            ["edges", String(sync.edges ?? "—")],
            ["lastIndexedAt", stamp(sync.lastIndexedAt ?? null)],
            ["branch / commit", `${sync.branch ?? "—"} / ${sync.commit ?? "—"}`],
            ["blobs", sync.blobs ? `${sync.blobs.count}（${formatBytes(sync.blobs.bytes)}）` : "—"],
            ["attachedRoot", project.attachedRoot ?? "—"],
            ["createdAt", stamp(project.createdAt ?? null)],
          ]}
        />
      </Card>

      <Card title="操作">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void onRescan()}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            手动重扫
          </button>
          <button
            type="button"
            onClick={() => void onDelete()}
            className="rounded border border-rose-300 px-3 py-1.5 text-sm text-rose-700 hover:bg-rose-50"
          >
            删除项目（永久）
          </button>
        </div>
      </Card>
    </div>
  );
}

function stamp(unixSeconds: number | null | undefined): string {
  if (!unixSeconds) return "—";
  return new Date(unixSeconds * 1000).toLocaleString();
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}
