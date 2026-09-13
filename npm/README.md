# zace-client

zace 的 MCP stdio 客户端：编辑器把它作为子进程拉起，它负责在本地扫描/增量上传代码，
把检索交给远端 `zace-service`（切片、索引、检索、渲染都在服务端）。

支持 **Claude Code / Codex / pi（经 pi-mcp-adapter）/ Cursor** 等所有支持 stdio 的 MCP 客户端。

## 快速开始

```bash
npx zace-client --base-url http://127.0.0.1:8787
```

`npx` 会按平台下载对应二进制并启动服务（stdio）。

## 客户端配置

三个 Agent 用的是同一套 stdio 配置，只是文件位置不同。

### Claude Code

```bash
claude mcp add-json zace --scope user '{
  "type": "stdio",
  "command": "npx",
  "args": ["zace-client", "--base-url", "http://127.0.0.1:8787"]
}'
```

### Codex CLI

`~/.codex/config.toml`：

```toml
[mcp_servers.zace]
command = "npx"
args = ["zace-client", "--base-url", "http://127.0.0.1:8787"]
startup_timeout_ms = 60000
```

### pi（通过 pi-mcp-adapter）

pi 本身不含 MCP，需先装适配器：`pi install npm:pi-mcp-adapter`。
然后写标准的 `.mcp.json`（项目级）或 `~/.config/mcp/mcp.json`（全局），适配器会自动读取：

```json
{
  "mcpServers": {
    "zace": {
      "command": "npx",
      "args": ["zace-client", "--base-url", "http://127.0.0.1:8787"]
    }
  }
}
```

### 其它（Cursor 等 JSON 配置）

```json
{
  "mcpServers": {
    "zace": {
      "command": "npx",
      "args": ["zace-client", "--base-url", "http://127.0.0.1:8787"]
    }
  }
}
```

## 配置项

| 参数 | 环境变量 | 必填 | 说明 |
|---|---|---|---|
| `--base-url` | `ZACE_BASE_URL` | 是 | `zace-service` 基础地址（须带 `http://` 或 `https://`） |
| `--token` | `ZACE_API_TOKEN` | 否 | 远端 API token（服务端鉴权落地后必填，见下） |
| `--cache-root` | `ZACE_CLIENT_CACHE` | 否 | 本地索引缓存根，默认 `~/.cache/zace` |

命令行参数优先于环境变量。

## 工具

| 工具 | 作用 |
|---|---|
| `search_context` | 检索与问题最相关的上下文（代码/调用链/文档证据包，带文件:行号） |
| `ask_project` | 项目级问题；当前返回检索结果 + 降级说明（LLM 总结属 Phase 3） |

## 已知限制

- **服务端鉴权尚未实现**（TASK-060/061）：`--token` 会被发送，但服务端当前放行所有请求；
  上云前必须完成鉴权。
- 首次索引大仓库时，第一个 tool call 会在上传期间等待（进度反馈属后续卡）。

## 从源码构建

```bash
git clone https://github.com/baoanaz/zace && cd zace/client
cargo build --release        # 产物：target/release/zace-client
```

`npm/run.js` 在下载不可用时会自动回退到 `client/target/{release,debug}/zace-client`。
