# Agent 接入手册（API Key + `npx zace-client`）

> 状态：2026-09-14 编排者实测（本机 WSL2，逐条命令真实跑过）。
> 结论：**用户期望的接入形态已经可用**，无需改代码。
> 配套：`docs/handbook/云端embedding接入.md`（embedding 配置）、`docs/handbook/M2a-验收手册.md`（本地模式 demo）。

## 0. 一句话

网页/CLI 建用户 → 建 API Key → 把 `npx zace-client --base-url <URL> --token <KEY>` 填进编辑器 → 即可用真实问题检索。

## 1. 接入形态（编辑器配置）

```json
{
  "mcpServers": {
    "zace": {
      "command": "npx",
      "args": ["zace-client", "--base-url", "http://你的服务器地址", "--token", "<控制台里创建的 API Key>"]
    }
  }
}
```

`zace-client` 的参数（`npx -y zace-client --help` 实测输出）：

| 参数 | 说明 | env 等价 |
|---|---|---|
| `--base-url <URL>` | zace-service 地址（必填） | `ZACE_BASE_URL` |
| `--token <TOKEN>` | **API Key**（云端形态必填） | `ZACE_API_TOKEN` |
| `--cache-root <DIR>` | 本地缓存（默认 `~/.cache/zace`） | `ZACE_CLIENT_CACHE` |

## 2. 服务端准备（云端形态）

**关键**：默认是本地单用户模式（`ZACE_LOCAL_MODE` 默认 **true**），该模式下**完全不鉴权**、也没有账户概念。
要用 API Key，必须以**非本地模式**启动：

```bash
export ZACE_LOCAL_MODE=false          # 关键：开启鉴权
export ZACE_REGISTER_OPEN=true        # 可选：允许注册（否则只能 bootstrap 第一个用户）
uv run zace-service serve --host 0.0.0.0 --port 8787 --data-root <数据根>
```

启动后自查：

```console
$ curl -s http://127.0.0.1:8787/api/meta
{"version":"0.0.1","localMode":false,"authRequired":true,"registerOpen":true,
 "needsBootstrap":true,"userCount":null}
```

`authRequired=true` + `needsBootstrap=true` = 鉴权已开、还没有任何账户。

## 3. 建用户与 API Key（实测完整流程）

### 3.1 首个用户（bootstrap）

**全新部署必须走这一步**——`register` 默认关闭，否则没有任何途径产生第一个账户。

```console
$ curl -s -X POST http://127.0.0.1:8787/api/auth/bootstrap \
    -H 'Content-Type: application/json' \
    -d '{"name":"me","password":"correct-horse-battery"}' -c cookies.txt
{"userId":"6dea905f5f061860ccccc713cba8910f","name":"me","createdAt":1789307272}
```

- 字段是 **`name`**（不是 email）；长度 ≤64。
- 成功即自动登录（写 httpOnly session cookie 到 `cookies.txt`）。
- 已有用户时返回 403 `already_initialized`——**不会**创建第二个，也不会覆盖。

### 3.2 创建 API Key

```console
$ curl -s -X POST http://127.0.0.1:8787/api/auth/tokens \
    -H 'Content-Type: application/json' -b cookies.txt \
    -d '{"name":"client-key"}'
{"id":"46e8089b...","token":"zace_nayRNpV55hiNpb-L9MBw1PjOtQeJG6e-_7TpIrqnwrs",
 "prefix":"zace_nayRNp","name":"client-key"}
```

⚠️ **`token` 明文只在这里返回一次**。服务端只存 sha256 哈希（`hash_api_token`），
之后 `GET /api/auth/tokens` **不含明文**。丢了只能撤销重建。

### 3.3 用 Key 访问数据面

```console
$ curl -s http://127.0.0.1:8787/api/projects -H "Authorization: Bearer zace_nayRNp..."
[]

$ curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8787/api/projects     # 不带 key
401
```

**撤销后立即失效**（实测）：`DELETE /api/auth/tokens/{id}` → 204，之后同一 key 访问 → 401。

## 4. 端到端实测（`npx zace-client` + 真实 MCP 协议）

用 Python MCP SDK 的 `stdio_client` 拉起真实 `npx zace-client`：

```python
params = StdioServerParameters(
    command="npx",
    args=["-y", "zace-client", "--base-url", "http://127.0.0.1:8787", "--token", TOKEN],
)
# initialize → server=zace, protocol=2025-11-25
# tools/list → 2 个: search_context, ask_project
# tools/call search_context → isError=False
```

**真实返回**（带「文件:行号」证据，这就是接入成功的标志）：

```text
## Relevant Context
### Code
[E1] SessionStore.refresh_token — src/session.py:1-6
     reason: bm25 -0.9853 + bm25 rank 1 + vector 0.8691 + vector rank 1 + 相邻区间合并
     1 | """会话管理。"""
     4 | class SessionStore:
     5 |     def refresh_token(self, token: str) -> str:
     6 |         return token + "-refreshed"
### Meta
confidence: l...
```

**token 错误时的表现**（可读、不泄漏）：

```text
tools/call search_context → isError=True
无法在服务端定位项目（identityKey=769ff956...）：服务端返回 HTTP 401 Unauthorized：
{"error":{"code":"unauthorized","message":"缺少或无效的凭据：请在 Authorization: Bearer 头带上 API Key，或先登录"}}
```

## 5. 鉴权实现要点（为什么不用逐个路由加依赖）

服务端用**全局 HTTP 中间件**（`service/zace_service/app.py` 的 `_install_auth`）：

- **鉴权是全局不变量**：逐个路由挂 `Depends` 靠人工维护，漏一个就是越权面
  （TASK-051 A1 的 `auth: enabled` 自述就曾在骗人）；
- **免鉴权白名单**（`PUBLIC_PATHS`）：`/healthz`、`/api/meta`、`/api/auth/{login,register,bootstrap,logout}`；
  **其余全部要求凭据**；
- **凭据两种**：`Authorization: Bearer <API Key>`（客户端用）或 session cookie（浏览器用）；
- **本地模式完全放行**（`ZACE_LOCAL_MODE=true`，默认）：行为与 M2a 逐字一致（R34）；
- **401 不区分细节**（无效/已撤销/过期同一文案）——不给探测面。

客户端侧（Rust，`client/src/remote.rs`）：发 `Bearer`（若有 token），
错误文本**脱敏**（token 出现即替换为 `***`），响应体截断防止刷屏。

## 6. 排错表

| 现象 | 原因 | 处理 |
|---|---|---|
| 401 `unauthorized` | 没带 key / key 错 / key 已撤销 | 检查 `--token`；在控制台重建 key |
| 400 `project_id_required` | 非本地模式下检索必须显式给 `projectId` | 这是 R37 的设计（省略仅限本地模式）；client 会先 `resolve` 拿到 id |
| 403 `local_mode` | 在本地模式下调用 `/api/auth/bootstrap` 等 | 本地模式没有账户概念；要建用户必须 `ZACE_LOCAL_MODE=false` |
| 403 `already_initialized` | 已有用户还调 bootstrap | 改用登录；或开 `ZACE_REGISTER_OPEN=true` 注册 |
| `npx zace-client` 无输出 | 它是 **MCP stdio 服务**，等 stdin 上的 JSON-RPC | 正常。用编辑器或 MCP SDK 客户端连它 |
| client 报 401 但 token 是对的 | 服务端是本地模式（`authRequired=false`） | 确认服务端 `ZACE_LOCAL_MODE=false` |
| 连不上 127.0.0.1 | 本机 `http_proxy` 拦截 | `NO_PROXY=127.0.0.1,localhost` |

## 7. 尚未验证的部分（诚实声明）

| 项 | 状态 |
|---|---|
| 浏览器 UI 走完整流程（登录 → 建 key → 复制） | **未验证**（WebUI 在 TASK-070 推进中） |
| 编辑器（Cursor/Codex/Claude/pi）里真实接入 | **未验证**（本手册用 MCP SDK 模拟了协议层） |
| 多用户隔离（A 用户的 key 看不到 B 的项目） | **未实现**（TASK-061 租户双层，pending） |
| TLS / 域名 / 反向代理 | **未实现**（TASK-063 部署，pending） |
| 远端场景下的完整同步（大仓库首次上传） | 部分验证（client 的 resolve/upload 路径已通，大规模未压测） |

**当前可用的边界**：单用户、HTTP（非 HTTPS）、本机或内网。
公网部署前必须先做 TASK-061（租户隔离）与 TASK-063（TLS）。
