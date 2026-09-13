/**
 * 接入指南：三个按键 + 片段与真实客户端参数一致（TASK-071）。
 *
 * 这组用例守的是"页面上写的能跑通"：片段里的命令/参数名必须与 npm 包的真实 CLI 一致
 * （`--base-url` / `--token`；包名 `zace-client`）。
 */

import { describe, expect, it } from "vitest";

import {
  AGENT_TARGETS,
  CLIENT_PACKAGE,
  claudeCommand,
  codexToml,
  curlExample,
  snippetFor,
  stdioConfig,
  stdioServer,
} from "./connect-info";

const CTX = { baseUrl: "https://zace.example.com", token: "zace_abc123" };

describe("接入片段", () => {
  it("恰好三个 agent：Codex / Claude / pi", () => {
    expect(AGENT_TARGETS.map((item) => item.label)).toEqual(["Codex", "Claude", "pi"]);
  });

  it("stdio 片段用 npx 拉起真实包名与参数", () => {
    const server = stdioServer(CTX);
    expect(server.command).toBe("npx");
    expect(server.args).toEqual([
      CLIENT_PACKAGE,
      "--base-url",
      "https://zace.example.com",
      "--token",
      "zace_abc123",
    ]);
    expect(CLIENT_PACKAGE).toBe("zace-client");
  });

  it("没有 Key 时不写空的 --token（留给服务端未启用鉴权的场景）", () => {
    const server = stdioServer({ baseUrl: "http://127.0.0.1:8787" });
    expect(server.args).toEqual(["zace-client", "--base-url", "http://127.0.0.1:8787"]);
    expect(server.args.join(" ")).not.toContain("--token");
  });

  it("Codex 用 TOML 写法且带 startup_timeout_ms", () => {
    const toml = codexToml(CTX);
    expect(toml).toContain("[mcp_servers.zace]");
    expect(toml).toContain('command = "npx"');
    expect(toml).toContain('"zace-client"');
    expect(toml).toContain("startup_timeout_ms = 60000");
  });

  it("Claude 用 add-json 一条命令，且内含同一份 command/args", () => {
    const command = claudeCommand(CTX);
    expect(command.startsWith("claude mcp add-json zace --scope user '")).toBe(true);
    const payload = JSON.parse(command.slice(command.indexOf("{"), command.lastIndexOf("}") + 1));
    expect(payload.type).toBe("stdio");
    expect(payload.command).toBe("npx");
    expect(payload.args).toEqual(stdioServer(CTX).args);
  });

  it("pi 产出标准 .mcp.json 结构", () => {
    const parsed = JSON.parse(snippetFor("pi", CTX));
    expect(parsed.mcpServers.zace.command).toBe("npx");
    expect(stdioConfig(CTX).mcpServers.zace.args).toEqual(parsed.mcpServers.zace.args);
  });

  it("curl 示例带 Bearer 且指向 search 端点", () => {
    const example = curlExample("https://zace.example.com", "p1", "zace_abc");
    expect(example).toContain("https://zace.example.com/api/query/search");
    expect(example).toContain("Authorization: Bearer zace_abc");
    expect(example).toContain('"projectId":"p1"');
  });
});
