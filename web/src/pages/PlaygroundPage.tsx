/**
 * Playground（Module/07 §2.2：**第一优先页面**）。
 *
 * 它是检索质量的人工入口：Fast 看 ContextPack（带行号与缺失说明），Deep 看降级包。
 * 两条纪律：
 * 1. 结果区**只渲染服务端返回的 markdown**（D-21/D-40），本页不拼装证据块；
 * 2. Deep 的 `degraded` 必须显著呈现——它不是 LLM 答案（D-26）。
 */

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  DEFAULT_MAX_TOKENS,
  MAX_MAX_TOKENS,
  MAX_QUERY_CHARS,
  ask,
  listProjects,
  search,
} from "../api/client";
import type { AskResponse, Project, SearchResponse } from "../api/types";
import { Markdown } from "../components/Markdown";
import {
  EvidenceTable,
  MetaPanel,
  STATUS_LABEL,
  formatTime,
  statusTone,
} from "../components/MetaPanel";
import { Badge, Card, CopyButton, ErrorBlock, LoadingBlock } from "../components/ui";

type Mode = "fast" | "deep";

interface HistoryEntry {
  id: string;
  mode: Mode;
  query: string;
  projectId: string;
  at: number;
}

const HISTORY_KEY = "zace.playground.history";

function readHistory(): HistoryEntry[] {
  try {
    const raw = window.sessionStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

export function PlaygroundPage() {
  const [params, setParams] = useSearchParams();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [projectId, setProjectId] = useState(params.get("project") ?? "");
  const [mode, setMode] = useState<Mode>("fast");
  const [query, setQuery] = useState("");
  const [maxTokens, setMaxTokens] = useState(DEFAULT_MAX_TOKENS);
  const [busy, setBusy] = useState(false);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [askResult, setAskResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [history, setHistory] = useState<HistoryEntry[]>(() => readHistory());

  useEffect(() => {
    void (async () => {
      try {
        const list = await listProjects();
        setProjects(list);
        if (!projectId && list.length > 0 && list[0]) setProjectId(list[0].projectId);
      } catch (err) {
        setError(err);
      }
    })();
    // 仅在挂载时拉一次项目列表；projectId 的后续变化由用户交互驱动。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed || !projectId) return;
    setBusy(true);
    setError(null);
    setSearchResult(null);
    setAskResult(null);
    const started = performance.now();
    try {
      if (mode === "fast") {
        setSearchResult(await search(projectId, trimmed, maxTokens));
      } else {
        setAskResult(await ask(projectId, trimmed));
      }
      const entry: HistoryEntry = {
        id: `${started}`,
        mode,
        query: trimmed,
        projectId,
        at: Date.now(),
      };
      const next = [entry, ...readHistory()].slice(0, 20);
      setHistory(next);
      window.sessionStorage.setItem(HISTORY_KEY, JSON.stringify(next));
    } catch (err) {
      setError(err);
    } finally {
      setElapsedMs(Math.round(performance.now() - started));
      setBusy(false);
    }
  }, [mode, maxTokens, projectId, query]);

  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      void submit();
    }
  }

  const project = projects?.find((item) => item.projectId === projectId) ?? null;
  const progress = project?.indexProgress;
  const notIndexed =
    progress !== undefined && progress !== null && progress.state !== "done" ? progress : null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">Playground</h1>
        <span className="text-xs text-slate-500">
          渲染的是服务端返回的 Markdown（D-21）；本页不重新拼装 ContextPack。
        </span>
      </div>

      <Card>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-slate-500" htmlFor="project">
              项目
            </label>
            <select
              id="project"
              value={projectId}
              onChange={(event) => {
                setProjectId(event.target.value);
                setParams(event.target.value ? { project: event.target.value } : {});
              }}
              className="rounded border border-slate-300 px-2 py-1 font-mono text-xs"
            >
              <option value="">请选择项目</option>
              {projects?.map((item) => (
                <option key={item.projectId} value={item.projectId}>
                  {item.displayName || item.projectId}
                </option>
              ))}
            </select>

            <div className="flex overflow-hidden rounded border border-slate-300 text-xs">
              {(["fast", "deep"] as Mode[]).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setMode(value)}
                  className={`px-3 py-1 ${
                    mode === value ? "bg-slate-900 text-white" : "bg-white hover:bg-slate-50"
                  }`}
                >
                  {value === "fast" ? "Fast（search）" : "Deep（ask）"}
                </button>
              ))}
            </div>

            {mode === "fast" && (
              <label className="flex items-center gap-1 text-xs text-slate-500">
                maxTokens
                <input
                  type="number"
                  min={1}
                  max={MAX_MAX_TOKENS}
                  value={maxTokens}
                  onChange={(event) => setMaxTokens(Number(event.target.value))}
                  className="w-24 rounded border border-slate-300 px-2 py-1 font-mono text-xs"
                />
              </label>
            )}
          </div>

          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            rows={3}
            maxLength={MAX_QUERY_CHARS}
            placeholder="例如：令牌过期后在哪里刷新？（Ctrl/Cmd + Enter 提交）"
            className="w-full resize-y rounded border border-slate-300 px-3 py-2 text-sm"
          />

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void submit()}
              disabled={busy || query.trim().length === 0 || !projectId}
              className="rounded bg-slate-900 px-4 py-1.5 text-sm text-white disabled:opacity-40"
            >
              {busy ? "检索中…" : mode === "fast" ? "检索" : "提问"}
            </button>
            {elapsedMs !== null && !busy && (
              <span className="text-xs text-slate-500">本次往返 {elapsedMs} ms（含网络与渲染）</span>
            )}
            {mode === "deep" && (
              <span className="text-xs text-amber-700">
                Deep 在 Phase 3 之前返回降级包（无 LLM 总结）。
              </span>
            )}
          </div>

          {notIndexed && (
            <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              该项目索引状态为 {notIndexed.state}
              {notIndexed.processedFiles !== undefined
                ? `（已处理 ${notIndexed.processedFiles} / 共 ${notIndexed.totalFiles} 文件，无百分比）`
                : ""}
              。检索可能返回 index_in_progress / index_failed。
            </p>
          )}

          {error !== null && <ErrorBlock error={error} />}
        </div>
      </Card>

      {busy && <LoadingBlock text="检索中…" />}

      {searchResult && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Card
            title="服务端渲染的 ContextPack"
            actions={<CopyButton text={searchResult.markdown} label="复制 Markdown" />}
          >
            <Markdown source={searchResult.markdown} />
          </Card>
          <div className="space-y-4">
            <Card title="meta">
              <MetaPanel meta={searchResult.meta} />
            </Card>
            <RawJson label="原始响应 JSON" value={searchResult} />
          </div>
        </div>
      )}

      {askResult && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Card
            title={
              <span className="flex flex-wrap items-center gap-2">
                Deep 结果
                <Badge tone={statusTone(askResult.status)}>{STATUS_LABEL[askResult.status]}</Badge>
              </span>
            }
            actions={<CopyButton text={askResult.answer} label="复制内容" />}
          >
            {askResult.status === "degraded" && (
              <p className="mb-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                status = degraded：这是检索与组装的结果，**不是** LLM 产生的答案（D-26）。
                可直接作为上下文使用。
              </p>
            )}
            <Markdown source={askResult.answer} />
            <h3 className="mt-4 mb-1 text-sm font-semibold">证据概览（evidenceSummary）</h3>
            <EvidenceTable items={askResult.evidenceSummary} />
          </Card>
          <div className="space-y-4">
            <Card title="meta">
              <MetaPanel meta={askResult.meta} />
            </Card>
            <RawJson label="原始响应 JSON" value={askResult} />
          </div>
        </div>
      )}

      {history.length > 0 && (
        <Card title="本次会话历史">
          <ul className="space-y-1 text-sm">
            {history.map((item) => (
              <li key={item.id} className="flex flex-wrap items-baseline gap-2">
                <span className="rounded bg-slate-100 px-1 text-xs">{item.mode}</span>
                <button
                  type="button"
                  className="text-left underline"
                  onClick={() => {
                    setMode(item.mode);
                    setQuery(item.query);
                    setProjectId(item.projectId);
                  }}
                >
                  {item.query}
                </button>
                <span className="text-xs text-slate-400">
                  {item.projectId} · {formatTime(Math.round(item.at / 1000))}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function RawJson({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <summary className="cursor-pointer text-sm font-semibold text-slate-700">{label}</summary>
      <pre className="mt-2 max-h-96 overflow-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-100">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}
