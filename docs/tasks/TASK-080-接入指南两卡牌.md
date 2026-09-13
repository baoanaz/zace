# TASK-080：接入指南重做（两卡牌：npm 下载 + Agent 接入，含 --token）

> 状态：review ｜ 阶段：Phase 4（M4）｜ 硬依赖：无 ｜ soft 依赖：TASK-082（token 占位符文案已定，勿等）
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

### 2026-09-13 · 实施 AI · 分支 `feature/task-080-connect_xwz0923`（从 `main` @ `d1a87ba` 开出，泳道 lane-a）

**状态：实现完成，待编排者评审（任务板已改 review）。**

#### 关键决策

1. **占位符回落放在 `connect-info.ts`，不在页面**：`stdioServer()` 对空串/纯空白一律回落为
   `http://你的服务器地址` / `<您的 API Key>`，`ConnectPage` 只做受控输入与透传。
   这样"`--token` 永远出现"是一条被单测钉住的不变量，页面重组不会悄悄破坏它。
2. **`--token` 无条件写入**（本卡核心）：旧实现在 token 为空时整段省略 `--token`，
   用户因此不知道存在鉴权。现在缺省值是占位符——语义是"我还没填"，不是"没有这个参数"。
3. **不再预填 `window.location.origin`**，也**不再调用 `listProjects()`**（它只服务已删除的
   curl 卡牌；去掉后页面少一次请求，未登录时的静默降级也一并消失）。
4. **卡牌一只保留一条安装命令 + 一行 npx 小字**（用户口径：使用者是工程师，不要长篇前置说明）；
   命令 `npm install -g zace-client` 的包名取自 `npm/package.json` 的 `name`。
5. **`curlExample()` 连同导出删除**：`grep -rn curlExample web/src/` 已无残留（见下）。

#### 验收命令与结果（本机实测）

```console
$ cd web && npm run lint
> eslint src --max-warnings 0            # exit 0，无输出

$ cd web && npm test
 Test Files  5 passed | 2 skipped (7)
      Tests  30 passed | 4 skipped (34)   # skipped = e2e（需 ZACE_E2E=1）

$ cd web && npm run build
> tsc --noEmit && vite build
✓ 302 modules transformed.  ✓ built in 1.71s

$ grep -rn "curlExample" web/src/        # exit 1（无匹配 = 无残留引用）

$ uv run ruff check .                    # All checks passed!
$ uv run python scripts/check_dependency_direction.py
依赖方向检查通过（core 纯库 / service 不上探）。
$ uv run pytest -o addopts="" -q
746 passed, 2 skipped, 4 warnings in 17.97s
```

> 环境备注（不影响结论）：本 worktree 的 `web/node_modules` 与 `.venv` 是新建 worktree 时缺失的，
> 已分别用 `npm ci`（锁文件一致）与 `uv sync --all-packages --all-extras` 恢复；
> `.lane-owner` 为 lane 认领文件，不入提交。

#### 新增单测覆盖（`connect-info.test.ts`，8 项）

| DoD 要求 | 用例 |
|---|---|
| token 为空仍含 `--token` 且为占位符 | 「没填 Key 时仍然写出 --token（值为占位符）」——同时断言**三按键的产出都含 `--token`** |
| token 有值 → 替换占位符 | 「填了地址与 Key 时占位符被真实值替换」 |
| baseUrl 默认是占位符而非 origin | 「没填地址时用占位符，而不是页面 origin」（含纯空白用例） |
| Codex TOML 形态 | 「三按键同一套 args」+「Codex TOML 与用户给的样例逐字对齐」 |
| 三按键同一套 args | 「三按键产出的是同一套 args，只有包装方式不同」 |
| 卡牌一安装命令 | 「安装命令用的是 npm 上的真实包名」 |

#### 人工核对：与用户样例逐字对照

用户给的样例（2026-09-13）：

```toml
[mcp_servers.zace]
command = "npx"
args = ["zace-client", "--base-url", "http://localhost:5174", "--token", "您的API Key"]
startup_timeout_ms = 60000
```

页面在**填了地址与 Key** 时的实际产出（同一 `codexToml()` 输出，字段名/顺序/引号一致）：

```toml
[mcp_servers.zace]
command = "npx"
args = ["zace-client", "--base-url", "http://localhost:5174", "--token", "您的API Key"]
startup_timeout_ms = 60000
```

页面在**什么都不填**（默认态）时的实际产出（占位符口径）：

```toml
[mcp_servers.zace]
command = "npx"
args = ["zace-client", "--base-url", "http://你的服务器地址", "--token", "<您的 API Key>"]
startup_timeout_ms = 60000
```

```console
$ npm install -g zace-client                                            # 卡牌一
$ claude mcp add-json zace --scope user '{"type":"stdio","command":"npx","args":["zace-client","--base-url","http://你的服务器地址","--token","<您的 API Key>"]}'
```

#### 契约影响

无（L1）。只消费既有事实：`client/src/main.rs` 的 clap 参数名、`npm/package.json` 的包名、
`service/zace_service/auth.py` 的 `Bearer` 语义与 `zace_` 前缀；未改任何契约文件、未改客户端参数。

#### 与设计偏差

1. **删除了卡牌三（curl 卡牌）**，同时删除 `curlExample()` 导出——卡内 §C 明确要求。
   `ConnectPage` 因此不再需要 `listProjects()`，连带去掉该请求（未改 `api/client.ts`）。
2. **`ConnectPage` token 输入框文案**改为「留空则用占位符 `<您的 API Key>`」，
   并在说明里指向本页「API Key」创建入口；`authRequired` 只用于一行条件提示
   （本地模式说明 token 可忽略），不再是「留空就不写 `--token`」的理由。
3. **`npm/README.md` 的「已知限制」第 1 条**由「服务端鉴权尚未实现」改写为实际语义
   （仅 `ZACE_LOCAL_MODE=false` 生效，本地模式完全放行）——按 §D 要求同步事实来源。

#### 未决问题（交编排者裁定）

1. **占位符 `<您的 API Key>` 直接粘进配置会带着尖括号**：用户按 §B 明确要求用该占位符
   （不自动带入真实 Key 以防截图泄露），因此保持原样。若后续要降低"忘替换"的错误率，
   建议另开卡（候选：页面上加一句"记得替换尖括号内容"，或由 `--token` 缺省采用环境变量
   `ZACE_API_TOKEN`）——均超出本卡范围，未实现。
2. **`ConnectPage` 目前没有 UI 级单测**（本卡 DoD 只要求 `connect-info.test.ts`）。
   卡片二的两卡牌结构、按钮切换、输入实时更新未被自动化覆盖；真浏览器验证同样缺席
   （与 TASK-070 未决问题 4 同源）。若要门禁，建议随 TASK-082/083 的页面改动一并补。
3. **`npm/README.md` 与页面片段的一致性无自动化校验**（`npm/README.md` 里用
   `http://127.0.0.1:8787`、页面用占位符，属刻意的示例 vs 模板差异）。
   如果希望"文档与页面永不漂移"，需要把片段抽成单一来源，属独立任务。

#### 建议复核点

- `web/src/app/connect-info.ts` 的 `orPlaceholder()` + `stdioServer()`："`--token` 永远出现"的不变量；
- `codexToml()` 的字段顺序是否仍与用户样例一致（最容易被顺手改坏）；
- `npm/README.md` 的参数表/示例是否与页面口径一致（尤其 `--token` 必填条件的措辞）；
- `ConnectPage` 是否确实不再引用 `window.location.origin` 与 `listProjects()`。
