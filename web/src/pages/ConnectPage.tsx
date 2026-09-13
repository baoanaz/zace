/**
 * 接入指南（TASK-071）：**三个按键**（Codex / Claude / pi）+ 一份可直接复制的配置。
 *
 * 设计口径（用户 2026-09-13 指定）：
 * - 页面只回答"把这段配置粘到 agent 里"，其余背景信息一律删掉；
 * - 服务地址与 API Key 由用户填（默认取当前 origin 与刚创建的 Key），片段随输入实时更新；
 * - **只写今天真能跑的写法**：分发链路（npm 上的 `zace-client`）已实测可用；
 *   未就绪的能力（如服务端启用鉴权后的 token 流程）如实标注，不编造。
 */

import { useEffect, useMemo, useState } from "react";

import { getMeta, listProjects, type Project } from "../api/client";
import {
  AGENT_TARGETS,
  DEFAULT_CACHE_ROOT,
  type AgentId,
  curlExample,
  snippetFor,
} from "../app/connect-info";
import { Card, CopyButton } from "../components/ui";

export function ConnectPage() {
  const [target, setTarget] = useState<AgentId>("codex");
  const [baseUrl, setBaseUrl] = useState("");
  const [token, setToken] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [authRequired, setAuthRequired] = useState<boolean | null>(null);

  useEffect(() => {
    setBaseUrl(window.location.origin);
    void (async () => {
      try {
        // 项目列表用于 curl 示例；未登录时可能 401，这里静默降级（示例里用占位 projectId）。
        setProjects(await listProjects());
      } catch {
        setProjects([]);
      }
      try {
        setAuthRequired((await getMeta()).authRequired);
      } catch {
        setAuthRequired(null);
      }
    })();
  }, []);

  const ctx = useMemo(() => ({ baseUrl, token: token.trim() || undefined }), [baseUrl, token]);
  const snippet = useMemo(() => snippetFor(target, ctx), [target, ctx]);
  const active = AGENT_TARGETS.find((item) => item.id === target) ?? AGENT_TARGETS[0]!;
  const sampleProjectId = projects[0]?.projectId ?? "";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold">接入指南</h1>
        <p className="mt-1 text-sm text-slate-600">
          选一个 agent，复制配置，粘到它的 MCP 配置文件里即可。
        </p>
      </div>

      <Card title="1. 服务地址与 API Key">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-xs text-slate-500">服务地址</span>
            <input
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="https://zace.example.com"
              className="w-full rounded border border-slate-300 px-3 py-1.5 font-mono text-sm"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs text-slate-500">
              API Key（可留空；下一个里程碑起必填）
            </span>
            <input
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="zace_..."
              className="w-full rounded border border-slate-300 px-3 py-1.5 font-mono text-sm"
            />
          </label>
        </div>
        {authRequired === false ? (
          <p className="mt-2 text-xs text-slate-500">
            当前服务是本地单用户模式（无鉴权），API Key 可留空——留空时片段里不会出现
            <code className="mx-1 rounded bg-slate-100 px-1">--token</code>。
          </p>
        ) : null}
      </Card>

      <Card title="2. 选择 Agent">
        <div className="mb-3 flex flex-wrap gap-2">
          {AGENT_TARGETS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTarget(item.id)}
              className={`rounded border px-4 py-2 text-sm ${
                target === item.id
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-300 bg-white hover:bg-slate-50"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-slate-500">
            写入位置：<code className="rounded bg-slate-100 px-1">{active.where}</code>
          </span>
          <CopyButton text={snippet} label="复制配置" />
        </div>
        <pre className="overflow-x-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-100">
          {snippet}
        </pre>
        {active.note && <p className="mt-2 text-xs text-slate-500">{active.note}</p>}
        <p className="mt-2 text-xs text-slate-500">
          {active.label} 通过 <code className="rounded bg-slate-100 px-1">npx zace-client</code>{" "}
          拉起本地客户端：它在本地扫描并上传代码，检索与渲染在服务端完成。
          本地索引缓存默认在 <code className="rounded bg-slate-100 px-1">{DEFAULT_CACHE_ROOT}</code>。
        </p>
      </Card>

      <Card title="3. HTTP API（curl）" actions={<CopyButton text={curlExample(baseUrl, sampleProjectId, token.trim() || undefined)} />}>
        <pre className="overflow-x-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-100">
          {curlExample(baseUrl, sampleProjectId, token.trim() || undefined)}
        </pre>
        <p className="mt-2 text-xs text-slate-500">
          端点与字段以 <code className="rounded bg-slate-100 px-1">docs/contracts/openapi.yaml</code>
          （CF-05）为准。
        </p>
      </Card>
    </div>
  );
}
