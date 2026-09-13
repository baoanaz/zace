/**
 * 接入指南（TASK-080）：**两张卡牌**——先装客户端，再配 Agent。
 *
 * 设计口径（用户 2026-09-13 指定）：
 * - 卡牌一：一条 `npm install -g zace-client`；使用者是工程师，不写 Node 版本等新手前置；
 * - 卡牌二：Codex / Claude / pi 三按键，配置**必定带 `--token`**（缺省为占位符
 *   `<您的 API Key>`）；地址缺省为 `http://你的服务器地址`，**不预填页面 origin**——
 *   用户可能从本机打开管理面、却要让别的机器上的 Agent 连过去；
 * - 不自动带入真实 Key（避免截图/录屏泄露）；用户填了就实时替换占位符；
 * - 事实来源：`npm/README.md` / `npm/package.json` / `client/src/main.rs` 的 clap 定义。
 */

import { useEffect, useMemo, useState } from "react";

import { getMeta } from "../api/client";
import {
  AGENT_TARGETS,
  BASE_URL_PLACEHOLDER,
  DEFAULT_CACHE_ROOT,
  INSTALL_COMMAND,
  type AgentId,
  snippetFor,
  TOKEN_PLACEHOLDER,
} from "../app/connect-info";
import { Card, CopyButton } from "../components/ui";

export function ConnectPage() {
  const [target, setTarget] = useState<AgentId>("codex");
  const [baseUrl, setBaseUrl] = useState("");
  const [token, setToken] = useState("");
  const [authRequired, setAuthRequired] = useState<boolean | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setAuthRequired((await getMeta()).authRequired);
      } catch {
        setAuthRequired(null);
      }
    })();
  }, []);

  // 空串交给 `connect-info` 回落成占位符（页面不做第二套判断）。
  const ctx = useMemo(() => ({ baseUrl, token }), [baseUrl, token]);
  const snippet = useMemo(() => snippetFor(target, ctx), [target, ctx]);
  const active = AGENT_TARGETS.find((item) => item.id === target) ?? AGENT_TARGETS[0]!;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold">接入指南</h1>
        <p className="mt-1 text-sm text-slate-600">两步：装客户端，然后把配置粘进你的 Agent。</p>
      </div>

      <Card title="1. 下载 zace-client" actions={<CopyButton text={INSTALL_COMMAND} />}>
        <pre className="overflow-x-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-100">
          {INSTALL_COMMAND}
        </pre>
        <p className="mt-2 text-xs text-slate-500">
          也可以不安装：下面的片段用 <code className="rounded bg-slate-100 px-1">npx</code>{" "}
          拉起，<code className="rounded bg-slate-100 px-1">npx</code> 会按需下载，
          <code className="mx-1 rounded bg-slate-100 px-1">{INSTALL_COMMAND}</code> 只是让首次启动快一些。
        </p>
      </Card>

      <Card title="2. 配置 Agent 接入">
        <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-xs text-slate-500">
              服务地址（留空则用占位符 {BASE_URL_PLACEHOLDER}）
            </span>
            <input
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder={BASE_URL_PLACEHOLDER}
              className="w-full rounded border border-slate-300 px-3 py-1.5 font-mono text-sm"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs text-slate-500">
              API Key（留空则用占位符 {TOKEN_PLACEHOLDER}）
            </span>
            <input
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="zace_..."
              className="w-full rounded border border-slate-300 px-3 py-1.5 font-mono text-sm"
            />
          </label>
        </div>

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
          <code className="rounded bg-slate-100 px-1">--token</code> 的取值是你在本页「API Key」
          里创建的 Key（<code className="rounded bg-slate-100 px-1">zace_</code> 开头，明文只显示一次）。
          {authRequired === false
            ? "当前服务是本地单用户模式（无鉴权），本地连过去时可忽略该参数。"
            : "服务端启用鉴权后必填。"}
        </p>
        <p className="mt-2 text-xs text-slate-500">
          {active.label} 通过 <code className="rounded bg-slate-100 px-1">npx zace-client</code>{" "}
          拉起本地客户端：它在本地扫描并上传代码，检索与渲染在服务端完成。
          本地索引缓存默认在 <code className="rounded bg-slate-100 px-1">{DEFAULT_CACHE_ROOT}</code>。
        </p>
      </Card>
    </div>
  );
}
