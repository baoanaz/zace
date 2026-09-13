/**
 * 编辑器接入片段（TASK-071）。
 *
 * 事实来源（**不许凭印象写**）：
 * - 分发与配置片段：`npm/README.md` + `client/README.md`（TASK-052 已实测 `npx zace-client` 可用，
 *   包已发布到 npm，版本 0.0.1）；
 * - 参数名：`client/src/main.rs` 的 clap 定义（`--base-url` / `--token` / `--cache-root`）；
 * - 三个 agent 的配置文件位置与写法：`npm/README.md` 的"客户端配置"节。
 */

/** MCP stdio 客户端（编辑器把它拉起，由它扫描/上传本地代码）。 */
export const CLIENT_PACKAGE = "zace-client";

/** 本地索引缓存根（客户端默认）。 */
export const DEFAULT_CACHE_ROOT = "~/.cache/zace";

export type AgentId = "codex" | "claude" | "pi";

export interface AgentTarget {
  id: AgentId;
  label: string;
  /** 配置文件位置（写"哪个文件"，因为三者写法不同）。 */
  where: string;
  /** 补充说明（安装前置、注意事项）。 */
  note?: string;
}

/**
 * 三个按键（用户 2026-09-13 指定：只保留 Codex / Claude / pi）。
 *
 * 三个 agent 用的是**同一套 stdio 配置**，差别只在配置文件位置与包装方式——
 * 因此片段由同一函数生成，只有 `where` 与前置步骤不同。
 */
export const AGENT_TARGETS: AgentTarget[] = [
  {
    id: "codex",
    label: "Codex",
    where: "~/.codex/config.toml",
    note: "TOML 写法；startup_timeout_ms 给足首次拉取二进制的时间。",
  },
  {
    id: "claude",
    label: "Claude",
    where: "claude mcp add-json zace --scope user '<下面的 JSON>'",
    note: "用一条 CLI 命令写入用户级配置，比手改文件更不容易写坏。",
  },
  {
    id: "pi",
    label: "pi",
    where: ".mcp.json（命令行在 pi 里执行）",
    note: "pi 本身不含 MCP，需先装适配器：pi install npm:pi-mcp-adapter。",
  },
];

export interface SnippetContext {
  /** 服务地址（浏览器访问的 origin，或用户填的远端地址）。 */
  baseUrl: string;
  /** API Key（可留空：服务端未启用鉴权时省略）。 */
  token?: string;
}

/**
 * stdio 配置对象（Claude / pi / Cursor 等 JSON 形态通用）。
 *
 * `--token` **只在用户填了 Key 时才出现**：留空还写一个空 `--token ""` 会让客户端
 * 以为"配了鉴权但值是空的"，报错会误导。
 */
export interface StdioServer {
  command: string;
  args: string[];
}

export function stdioServer(ctx: SnippetContext): StdioServer {
  const args = [CLIENT_PACKAGE, "--base-url", ctx.baseUrl];
  if (ctx.token) args.push("--token", ctx.token);
  return { command: "npx", args };
}

export function stdioConfig(ctx: SnippetContext): { mcpServers: { zace: StdioServer } } {
  return { mcpServers: { zace: stdioServer(ctx) } };
}

/** Claude 的 CLI 写法（与 stdioConfig 同源，只是多了 type/stdio 包装）。 */
export function claudeCommand(ctx: SnippetContext): string {
  const server = stdioServer(ctx);
  const payload = { type: "stdio", command: server.command, args: server.args };
  return `claude mcp add-json zace --scope user '${JSON.stringify(payload)}'`;
}

/** Codex 的 TOML 写法（与 stdioConfig 同源）。 */
export function codexToml(ctx: SnippetContext): string {
  const args = [CLIENT_PACKAGE, "--base-url", ctx.baseUrl];
  if (ctx.token) args.push("--token", ctx.token);
  const quoted = args.map((item) => `"${item}"`).join(", ");
  return ["[mcp_servers.zace]", 'command = "npx"', `args = [${quoted}]`, "startup_timeout_ms = 60000"].join(
    "\n",
  );
}

/** 按目标产出"可直接粘贴"的文本。 */
export function snippetFor(target: AgentId, ctx: SnippetContext): string {
  if (target === "codex") return codexToml(ctx);
  if (target === "claude") return claudeCommand(ctx);
  return JSON.stringify(stdioConfig(ctx), null, 2);
}

/** curl 示例（与 CF-05 的 `/api/query/search` 一致）。 */
export function curlExample(baseUrl: string, projectId: string, token?: string): string {
  const auth = token ? ` \\\n  -H 'Authorization: Bearer ${token}'` : "";
  return [
    `curl -s -X POST ${baseUrl}/api/query/search \\`,
    `  -H 'Content-Type: application/json'${auth} \\`,
    `  -d '{"projectId":"${projectId || "<projectId>"}","query":"令牌过期后在哪里刷新？"}'`,
  ].join("\n");
}
