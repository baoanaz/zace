/**
 * 接入指南（TASK-070 §E）。
 *
 * 为什么这个页面重要：这份内容此前只存在于 CLI 的 `mcp-config` 输出与验收手册里，
 * 新用户第一件事就是找不到它。**页面上写下的每条命令/端点都必须能跑通**（宁少勿假）。
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getHealth, listProjects } from "../api/client";
import type { Health, Project } from "../api/types";
import { STDIO_NOTE, curlExample, cursorSnippet, mcpUrl } from "../app/connect-info";
import { Card, CopyButton, ErrorBlock, KeyValue, LoadingBlock } from "../components/ui";

export function ConnectPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<unknown>(null);

  const origin = window.location.origin;

  useEffect(() => {
    void (async () => {
      try {
        const [h, p] = await Promise.all([getHealth(), listProjects()]);
        setHealth(h);
        setProjects(p);
      } catch (err) {
        setError(err);
      }
    })();
  }, []);

  const sampleProjectId = projects[0]?.projectId ?? "";
  const cursor = cursorSnippet(origin);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-lg font-semibold">接入指南</h1>
        <span className="text-xs text-slate-500">
          页面上的地址取自当前访问的 origin：{origin}（与
          <code className="mx-1 rounded bg-slate-100 px-1">ZACE_WEB_API</code>代理目标无关）
        </span>
      </div>

      {error !== null && <ErrorBlock error={error} />}
      {health === null && error === null && <LoadingBlock />}

      {health && (
        <Card title="服务状态">
          <KeyValue
            items={[
              ["版本", health.version],
              ["模式", health.localMode ? "本地单用户（无鉴权）" : "远端（需鉴权）"],
              ["auth", health.auth],
              ["dataRoot", <code className="font-mono text-xs">{health.dataRoot}</code>],
              ["已绑定项目", String(health.projects.length)],
            ]}
          />
        </Card>
      )}

      <Card
        title="1. 编辑器（Cursor 等，Streamable HTTP）"
        actions={<CopyButton text={cursor} label="复制配置" />}
      >
        <p className="mb-2 text-sm text-slate-700">
          MCP 端点：<code className="rounded bg-slate-100 px-1 font-mono text-xs">{mcpUrl(origin)}</code>
        </p>
        <pre className="overflow-x-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-100">
          {cursor}
        </pre>
        <p className="mt-2 text-xs text-slate-500">
          与 <code className="rounded bg-slate-100 px-1">uv run zace-service mcp-config</code>{" "}
          输出的片段一致（同一份文案的两个出口）。
        </p>
        <p className="mt-2 rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
          {STDIO_NOTE}
        </p>
      </Card>

      <Card title="2. 命令行（zace-core）">
        <pre className="overflow-x-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-100">
          {[
            "# 索引一个仓库（数据根建议显式指定）",
            "uv run zace-core ingest --repo /绝对路径/你的仓库 --data ~/.zace",
            "",
            "# 中文/符号混合查询",
            'uv run zace-core search "令牌过期后在哪里刷新？" --repo /绝对路径/你的仓库',
            "",
            "# 起服务并绑定本地仓库（浏览器打开本页所在地址）",
            "uv run zace-service local --repo /绝对路径/你的仓库 --port 8787",
          ].join("\n")}
        </pre>
      </Card>

      <Card
        title="3. HTTP API（curl）"
        actions={<CopyButton text={curlExample(origin, sampleProjectId)} label="复制示例" />}
      >
        <pre className="overflow-x-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-100">
          {curlExample(origin, sampleProjectId)}
        </pre>
        <p className="mt-2 text-xs text-slate-500">
          端点与字段以 <code className="rounded bg-slate-100 px-1">docs/contracts/openapi.yaml</code>（CF-05）为准；
          本地模式无需凭据，远端模式需要 Bearer token（尚未实现，见
          <Link className="mx-1 underline" to="/tokens">API Key 管理</Link>）。
        </p>
      </Card>

      <Card title="4. 数据落点与隐私">
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li>
            数据根：<code className="rounded bg-slate-100 px-1 font-mono text-xs">{health?.dataRoot ?? "—"}</code>
            （每项目一个目录：blobs/ + index.db + vectors/）。
          </li>
          <li>删除项目 = 删除该目录，无软删除期；索引可从源码重算。</li>
          <li>
            embedding 默认走配置的 provider（当前默认路径为云端 API）——**源码会发往该 provider**；
            切换本地 ONNX 可避免源码出网（EMBED_MODE=local，当前暂缓）。
          </li>
          <li>
            启用外部 ANSWER_* 时，**证据片段会发往该 LLM 提供商**（Module/06 §3 的明示要求）。
          </li>
        </ul>
      </Card>

      <Card title="5. 常见问题">
        <ul className="space-y-2 text-sm text-slate-700">
          <li>
            <strong>索引还没跑完就查询</strong>：返回 409 <code>index_in_progress</code> 或 500{" "}
            <code>index_failed</code>——索引期间没有百分比（core 无回调），进度见
            <Link className="mx-1 underline" to="/">项目页</Link>。
          </li>
          <li>
            <strong>编辑器连不上/403</strong>：确认服务在跑、端口一致；MCP 端点有 Origin 白名单
            （挡浏览器跨站请求）与主机头校验。
          </li>
          <li>
            <strong>provider 不可用</strong>：返回 503 <code>embedding_unavailable</code> /
            <code>embedding_unreachable</code>，检查 EMBED_MODE / EMBED_MODEL / EMBED_BASE_URL / EMBED_API_KEY。
          </li>
          <li>
            <strong>projectId 对不上</strong>：带 git remote 的仓库走 D-29 身份（换机器同 projectId）；
            非 git 目录退化为绝对路径 hash，换路径就会变。
          </li>
        </ul>
      </Card>

      <Card title="6. 尚未就绪（不在本版本范围）">
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
          <li>登录 / 注册 / 初始化账户 / API Key 管理：TASK-060</li>
          <li>索引统计与查询用量页面：TASK-062 / TASK-064</li>
          <li>stdio-only harness 的本地代理：M2c 的 Rust client（TASK-040R）</li>
        </ul>
      </Card>
    </div>
  );
}
