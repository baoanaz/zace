# TASK-080：接入指南重做（两卡牌：npm 下载 + Agent 接入，含 --token）

> 状态：pending ｜ 阶段：Phase 4（M4）｜ 硬依赖：无 ｜ soft 依赖：TASK-082（token 占位符文案已定，勿等）
> 建议分支：`feature/task-080-connect-guide_<你的缩写><MMDD>`
> 交付物所有权：
> - `web/src/app/connect-info.ts`
> - `web/src/app/connect-info.test.ts`
> - `web/src/pages/ConnectPage.tsx`
> - `npm/README.md`（**仅**同步参数说明与示例；不要改 npm/run.js、package.json）
>
> 清单外文件不得改。**注意：本卡不改 `web/src/app/App.tsx` / `Layout.tsx`（那是 TASK-082 的领地）。**

## 目标

把接入指南改成用户指定的**两个卡牌**，让"下载客户端 → 配好 Agent"这条链路一站走通：

1. **卡牌一：下载 npm 包** —— 一条安装命令即可（使用者是工程师，不要写长篇前置说明）；
2. **卡牌二：选择 Agent 接入** —— Codex / Claude / pi 三按键，配置里**必须带 `--token`**。

用户原话（2026-09-13）：

> 接入指南里面没有显示 `--token` 的字段，一般是：
> ```
> [mcp_servers.zace]
> command = "npx"
> args = ["zace-client", "--base-url", "http://localhost:5174", "--token", "您的API Key"]
> startup_timeout_ms = 60000
> ```
> 并且要加一个 npm 下载 zace-client 的教程吧。最终接入指南应该是两个卡牌，一、下载 npm。二、选择 Agent 接入。

补充口径（用户在追问中确认）：

- 卡牌一**只给一条安装指令**，不写 Node 版本/前置检查等新手教程；
- 卡牌二的 URL 用占位符 `http://你的服务器地址`（**不要**预填 `window.location.origin` 的真实值，
  因为用户可能从本机打开管理面、但要让别的机器上的 Agent 连过去）；
- token 栏用占位符 `<您的 API Key>`（**不要**自动带入真实 Key，避免截图/录屏泄露）。

## 现状（实测，2026-09-13）

`web/src/app/connect-info.ts` 当前的 `stdioServer()`：

```ts
const args = [CLIENT_PACKAGE, "--base-url", ctx.baseUrl];
if (ctx.token) args.push("--token", ctx.token);   // ← token 为空就整段消失
```

问题：`ConnectPage` 的 token 输入框默认为空，于是**生成的配置里根本没有 `--token`**——
用户看不到这个字段，不知道有鉴权这回事。这正是用户报的问题。

`ConnectPage.tsx` 当前是三张卡（服务地址与 Key / 选择 Agent / HTTP API curl）。
用户要的是**两张卡**，且顺序是"先 npm，再 Agent"。

## 本卡必须做到的

### §A 卡牌一：下载 npm 包

- 标题体现"先装客户端"（如「1. 下载 zace-client」）；
- **一条命令**：`npm install -g zace-client` 或 `npx zace-client --help` 二选一，给出**可复制**片段；
  - 推荐以 `npx` 为主（无需全局安装）**但**用户明确说"加一个 npm 下载 zace-client 的教程"——
    因此卡牌一给**安装命令**（全局装），并在下方一行小字说明"也可以直接用 npx，无需安装"；
- 事实来源必须是 `npm/README.md` 与 `npm/package.json`（包名 `zace-client`，版本 0.0.1，已发布到 npm）；
  **不许凭印象写包名或命令**。

### §B 卡牌二：选择 Agent 接入

- 保留三按键：Codex / Claude / pi（`AGENT_TARGETS` 已有，顺序不变）；
- **每份配置都必须出现 `--token`**，值为占位符 `<您的 API Key>`（用户明确要求）；
- baseUrl 默认值为占位符 `http://你的服务器地址`；
- 页面提供一个输入框让用户填自己的真实地址与 Key（填了就替换占位符）——
  这是既有能力，保留；**默认态必须是占位符**，不是 `window.location.origin`；
- Codex 的 TOML 形态要与用户给的样例一致（`[mcp_servers.zace]` + `command`/`args`/`startup_timeout_ms`）。

### §C 删掉卡牌三（HTTP API curl）

用户说"就两个卡牌就可以"。curl 卡牌及其 `curlExample()` 一并从页面移除。
`curlExample` 若不再被任何地方引用，**连同其导出一起删除**（不要留死代码）；
若 `ConnectPage` 之外仍有引用，先 grep 确认再决定（`grep -rn curlExample web/src/`）。

### §D 同步 `npm/README.md`

`npm/README.md` 是接入片段的**事实来源之一**，必须与页面一致：

- 快速开始补上**安装**方式（不只 `npx`）；
- 参数表里 `--token` 的说明改为"服务端启用鉴权后**必填**"（TASK-060 已落地鉴权，旧文案说"尚未实现"是**过期的**）；
- 示例配置统一带 `--token <你的 API Key>`。

## 验收标准（DoD）

- [ ] `connect-info.test.ts` 更新并全绿，**必须覆盖**：
  - [ ] token 为空时，生成配置**仍包含 `--token`** 且值为占位符（这是本卡的核心回归点）；
  - [ ] token 有值时，占位符被真实值替换；
  - [ ] baseUrl 默认是占位符，不是页面 origin；
  - [ ] Codex TOML 形态含 `[mcp_servers.zace]`、`command = "npx"`、`startup_timeout_ms`；
  - [ ] 三按键产出的是**同一套 args**（仅包装方式不同）。
- [ ] 行为验收（贴真实输出）：`cd web && npm run lint && npm test && npm run build` 全绿。
- [ ] 人工核对：生成的 Codex 片段与用户给的样例**逐字对齐**（字段名、顺序、引号），在报告里贴对照。
- [ ] `curlExample` 若删除，确认 `grep -rn "curlExample" web/src/` 无残留引用。
- [ ] 基线三条命令全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest -o addopts="" -q`
- [ ] 任务卡"执行记录"已回填；任务板状态改为 `review`。

## 明确不做

- **不改** `--token` 的客户端参数名或语义（`client/src/main.rs` 的 clap 定义，属冻结接口）；
- **不自动带入真实 API Key**（用户明确选择占位符方案）；
- 不重做 `AGENT_TARGETS` 的三个 agent（Codex/Claude/pi 已定，多加或改顺序都算超范围）；
- 不碰 `web/src/app/App.tsx` / `Layout.tsx` / `DashboardPage.tsx` / `HistoryPage.tsx`（其它卡的领地）。

## 参考事实（核实过的，别猜）

| 事实 | 来源 |
|---|---|
| 包名 `zace-client`，版本 `0.0.1`，bin 是 `run.js` | `npm/package.json` |
| 实测 `npx -y zace-client --help` 可用（本机已缓存二进制） | 编排者 2026-09-13 实测 |
| 参数名：`--base-url` / `--token` / `--cache-root` | `client/src/main.rs` clap |
| token 由服务端以 `Authorization: Bearer` 校验 | `service/zace_service/auth.py::authenticate` |
| API Key 前缀 `zace_`，在 UI「API Key」页创建 | `service/zace_service/auth.py::TOKEN_PREFIX` |

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板：分支 / 验收命令与结果 / 契约影响 / 与设计偏差 / 未决问题。

## 执行记录

（实施 AI 在此填写。）
