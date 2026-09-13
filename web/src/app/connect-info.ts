/**
 * 编辑器接入片段与"未就绪"清单。
 *
 * 编辑器片段与 `service/zace_service/cli_hint.py` 的产出**逐字对应**（同一份文案的两个出口：
 * CLI 就绪信息 / web 接入指南页）。改动这里的 JSON 形状时，同时改 cli_hint.py——
 * 否则用户会看到两个互相矛盾的配置片段。
 */

export const MCP_MOUNT_PATH = "/mcp";

/** stdio-only harness 的说明（与 `cli_hint._STDIO_NOTE` 同一事实：归 M2c 的 Rust client）。 */
export const STDIO_NOTE =
  "只支持 stdio 的 harness 需要一个 stdio 代理（在本地把 stdio 转发到本 URL）——" +
  "归 M2c 的 Rust client（TASK-040R），当前版本未提供。";

export function mcpUrl(origin: string): string {
  return `${origin}${MCP_MOUNT_PATH}`;
}

export function cursorSnippet(origin: string): string {
  return JSON.stringify({ mcpServers: { zace: { url: mcpUrl(origin) } } });
}

/** curl 示例：与 `docs/contracts/openapi.yaml` 的 `/api/query/search` 一致。 */
export function curlExample(origin: string, projectId: string): string {
  return [
    `curl -s -X POST ${origin}/api/query/search \\`,
    `  -H 'Content-Type: application/json' \\`,
    `  -d '{"projectId":"${projectId || "<projectId>"}","query":"令牌过期后在哪里刷新？"}'`,
  ].join("\n");
}

export interface NotReadyFeature {
  path: string;
  title: string;
  what: string;
  dependsOn: string[];
}

/**
 * 未就绪页清单（TASK-070 §F）。
 *
 * 纪律：**不许用假数据填充**——这些页面在后端落地前必须显式说明"还没有"，
 * 否则使用者会误以为鉴权/统计已经可用（那是最贵的一类误解）。
 */
export const NOT_READY_FEATURES: NotReadyFeature[] = [
  {
    path: "/login",
    title: "登录",
    what: "用账户登录，签发 httpOnly session cookie。",
    dependsOn: ["TASK-060"],
  },
  {
    path: "/register",
    title: "注册",
    what: "创建账户（默认关闭，由 ZACE_REGISTER_OPEN 控制）。",
    dependsOn: ["TASK-060"],
  },
  {
    path: "/setup",
    title: "初始化账户",
    what: "全新部署时创建第一个账户（users 表为空时才可用，用后自动关闭）。",
    dependsOn: ["TASK-060"],
  },
  {
    path: "/tokens",
    title: "API Key 管理",
    what: "创建/列出/撤销 API token（明文仅创建时显示一次）。",
    dependsOn: ["TASK-060"],
  },
  {
    path: "/usage",
    title: "用量与索引统计",
    what: "索引成功/失败次数、平均耗时；查询次数、confidence 分布、citationCoverage。",
    dependsOn: ["TASK-062", "TASK-064"],
  },
  {
    path: "/settings",
    title: "设置",
    what: "只读展示 ANSWER_* / EMBED_* 配置状态与注册开关。",
    dependsOn: ["TASK-060"],
  },
];

export function notReadyFor(path: string): NotReadyFeature | undefined {
  return NOT_READY_FEATURES.find((item) => item.path === path);
}
