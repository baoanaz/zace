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
 *
 * TASK-100 §需求6（用户 2026-09-14）：删掉页面上的解释性文案——用户是工程师，
 * 页面只留"做什么"与可粘贴的片段。
 */

import { useMemo, useState } from "react";

import {
  AGENT_TARGETS,
  BASE_URL_PLACEHOLDER,
  INSTALL_COMMAND,
  type AgentId,
  snippetFor,
  TOKEN_PLACEHOLDER,
} from "../app/connect-info";
import { Card, CopyButton, Page } from "../components/ui";

export function ConnectPage() {
  const [target, setTarget] = useState<AgentId>("codex");
  const [baseUrl, setBaseUrl] = useState("");
  const [token, setToken] = useState("");
  // 空串交给 `connect-info` 回落成占位符（页面不做第二套判断）。
  const ctx = useMemo(() => ({ baseUrl, token }), [baseUrl, token]);
  const snippet = useMemo(() => snippetFor(target, ctx), [target, ctx]);
  const active = AGENT_TARGETS.find((item) => item.id === target) ?? AGENT_TARGETS[0]!;

  return (
    <Page>
      <div>
        <h1 className="text-lg font-semibold">接入指南</h1>
        <p className="mt-1 text-sm text-ink-muted">两步：装客户端，然后把配置粘进你的 Agent。</p>
      </div>

      <Card title="1. 下载 zace-client" actions={<CopyButton text={INSTALL_COMMAND} />}>
        <pre className="overflow-x-auto rounded bg-ink-primary p-3 font-mono text-xs text-paper-base">
          {INSTALL_COMMAND}
        </pre>
      </Card>

      <Card title="2. 配置 Agent 接入">
        <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-xs text-ink-muted">
              服务地址（留空则用占位符 {BASE_URL_PLACEHOLDER}）
            </span>
            <input
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder={BASE_URL_PLACEHOLDER}
              className="w-full rounded border border-ink-line bg-paper-card px-3 py-1.5 font-mono text-sm text-ink-primary"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs text-ink-muted">
              API Key（留空则用占位符 {TOKEN_PLACEHOLDER}）
            </span>
            <input
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="zace_..."
              className="w-full rounded border border-ink-line bg-paper-card px-3 py-1.5 font-mono text-sm text-ink-primary"
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
                  ? "border-accent-seal bg-accent-seal text-white"
                  : "border-ink-line bg-paper-card text-ink-primary hover:bg-paper-base"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-ink-muted">
            写入位置：<code className="rounded bg-paper-base px-1 text-ink-primary">{active.where}</code>
          </span>
          <CopyButton text={snippet} label="复制配置" />
        </div>
        <pre className="overflow-x-auto rounded bg-ink-primary p-3 font-mono text-xs text-paper-base">
          {snippet}
        </pre>
      </Card>
    </Page>
  );
}
