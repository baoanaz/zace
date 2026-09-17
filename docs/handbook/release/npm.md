# npm 发布手册（zace-client 平台子包）

> **读者**：要把 `zace-client` 发布到 npm 的人（维护者）。
> **产出**：`zace-client@<版本>` 在 npm 上可 `npx` 直接运行，6 个平台都有二进制。
>
> 设计依据：`docs/design/INDEX.md` 的 **D-48**（二进制走 npm 平台子包）与
> **D-49**（今后所有预编译二进制一律按此形态分发）。
> 重建前端 / 重启服务见 [`README.md`](README.md)；本文件只管 **npm**。

## 0. 发一个版本：只有一条命令

```bash
bash scripts/release-client.sh x.y.z
```

**这是唯一入口**，Agent 收到"发布 zace-client x.y.z"时应直接跑它，
不要手工拼 `git tag` / `npm publish` / `check-version.sh` 等零散步骤
（手工零散执行正是下文 §6 那次真实故障的背景）。

它做的事（含每一步的前置校验）：

```text
① 前置检查  在 main、工作区干净、tag 不存在、版本高于已发布
② 改版本号  client/Cargo.toml + npm/package.json + server.json
③ 同步校验  generate 子包 → check-version.sh → 平台包元数据 check
④ 测试      ruff + 依赖方向 + pytest
⑤ 交付      commit → push main → 打并 push tag v<version>
⑥ 等 CI     gh 可用 → `gh run watch --compact --exit-status`
            不可用 → 只报告"CI 已触发"，不阻塞
⑦ 复核      npm view zace-client version / dist-tags，确认 latest == 本次版本
            且 6 个平台子包都在 registry 上
```

**边界（它刻意不做的事）**：不构建二进制、不发布任何 npm 包 ——
六平台 build / publish / verify / promote 全部由 GitHub Actions 负责
（本地编不了 macOS，也不该让本地产物进 npm）。

**失败处置**：npm 版本号不可撤回、已 push 的 tag 不移动 ——
**放弃当前版本号，修复后递增新版本重跑**（§6 有 0.0.5 一例）。

## 0.1 一句话理解形态

```text
zace-client                       ← 启动器（run.js）+ 6 个平台子包作 optionalDependencies
├── zace-client-linux-x64         ← 各含本平台的裸二进制
├── zace-client-linux-arm64
├── zace-client-darwin-x64        ┐ 两个架构**各自独立构建**（不用 lipo/universal）
├── zace-client-darwin-arm64      ┘
├── zace-client-windows-x64
└── zace-client-windows-arm64
```

npm 按子包自己的 `os`/`cpu` 字段**只装本平台那一个**。用户侧**没有下载步骤**：
`npx --yes --prefer-online zace-client@latest …` 直接可用，不需要任何额外配置。

**npm 是唯一的二进制分发渠道**。没有 GitHub Release 二进制资产，
包装器里也没有任何下载回退 —— 见 §5「为什么删掉回退」。

## 1. 用户端配置（给用户看的形态）

```toml
[mcp_servers.zace]
command = "npx"
args = [
  "--yes",
  "--prefer-online",
  "zace-client@latest",
  "--base-url",
  "https://你的服务地址",
  "--token",
  "用户自己的 token"
]
startup_timeout_ms = 60000
```

- `--yes`：非交互（MCP 子进程没有 TTY，缺它可能卡在确认提示）；
- `--prefer-online`：跳过本地 npx 缓存，总是查 registry 解出新版本
  （否则旧缓存会让用户“升级了但行为没变”）；
- `@latest`：显式走 latest 标签（`next` 是发布中间态，用户不该看到）。

> 也可以 `npm i -g zace-client@latest` 后直接用 `zace-client` 命令。

## 2. 发布流水线（六步，每步都有硬门）

```text
① Build 6 平台（每架构独立）
        ↓
② publish-platforms      发 6 个平台子包
        ↓
③ pre-verify             6 个子包都能在 registry 查到该版本   ← 缺一个就停，不发主包
        ↓
④ publish-main           发主包，tag = next（此时 latest 不动）
        ↓
⑤ promote                先冒烟（真实 npx 装+启动）→ 再把 latest 切过去
        ↓
⑥ post-verify            latest 已指向该版本
```

**为什么主包先发 `next` 而不是直接 `latest`**：npm 发布**不可逆**（同版本不能重发）。
直接发 latest 意味着一旦子包有问题，所有 `@latest` 用户**立刻**拿到坏包。
先发 next，latest 仍指向旧的好版本 —— 留出验证与补救窗口。

**为什么 macOS 不用 universal（lipo）**：子包机制下 x64/arm64 本就是两个包，
合并只会让每个用户多下另一个架构的代码（体积翻倍），
并让产物校验、签名、按架构排查都变复杂。

### 2.1 触发方式（脚本内部等价于这几步）

`release-client.sh` 最终就是「push main + push tag」，tag 触发
`.github/workflows/release.yml`，六步全自动。若需手工复现（例如脚本本身有问题时）：

```bash
python3 scripts/make-platform-packages.py generate
bash scripts/check-version.sh v0.0.5      # 须通过
git commit -am "release: zace-client v0.0.5"
git push origin main
git tag -a v0.0.5 -m "zace-client v0.0.5"
git push origin v0.0.5                    # ← 触发构建与发布
```

**需要仓库 secret `NPM_TOKEN`**（Settings → Secrets → Actions）：
npm 上 Access Tokens 的 **Automation** 类型（绕过 2FA，CI 必需）。
没有它 `publish` 步骤会 401。**本地永不读取该 token。**

### 2.2 逐平台手工发布（仅当 CI 不可用时；不推荐，仅作兜底）

本机只能编出**本机平台**的产物。要发全 6 平台必须用 CI，或逐平台在对应机器上构建。

```bash
# ── ① 构建（在能编该平台的机器上；产物名必须是 zace-client[.exe]）──
# Linux x64（**必须 musl 静态**，否则旧发行版报 GLIBC_2.xx not found）
cd client && cargo build --release --target x86_64-unknown-linux-musl
# Linux arm64：cross build --release --target aarch64-unknown-linux-musl
# macOS：在 macOS 上分别编
#   cargo build --release --target x86_64-apple-darwin
#   cargo build --release --target aarch64-apple-darwin
# Windows：cargo build --release --target {x86_64,aarch64}-pc-windows-msvc

# ── ② 暂存进子包目录（会校验静态链接/平台族/架构）──
python3 scripts/make-platform-packages.py stage \
    --suffix linux-x64 --binary client/target/x86_64-unknown-linux-musl/release/zace-client

# ……其余 5 个平台同理（各自机器上 stage 后，把 npm/platforms/ 目录一起发布）

# ── ③ 发布前硬门 ──
python3 scripts/make-platform-packages.py check      # 6 个子包都真有二进制 + 平台字段一致
bash scripts/check-version.sh                        # 版本四处一致 + 子包一致

# ── ④ 发子包 → ⑤ 验证 → ⑥ 发主包(next) → ⑦ 冒烟 → ⑧ promote ──
python3 scripts/make-platform-packages.py publish --phase platforms
python3 scripts/make-platform-packages.py verify  --phase platforms
python3 scripts/make-platform-packages.py publish --phase main --tag next
python3 scripts/make-platform-packages.py smoke   --tag next
python3 scripts/make-platform-packages.py promote
python3 scripts/make-platform-packages.py verify  --phase latest
```

登录：`npm login`（或 `NODE_AUTH_TOKEN=npm_xxx` 环境变量）。

> **发布中途失败可恢复**：`publish` 会跳过已存在于 registry 的包
> （npm 不允许重发同版本，失败重跑不应卡死）。修好后从失败那一步继续即可。
> 但 **`publish-main` 一旦成功就不能重跑** —— 换 patch 版本号重来。

## 3. 脚本速查

| 命令 | 作用 |
|---|---|
| `generate` | 生成/同步 6 个子包的 `package.json` + 主包 `optionalDependencies`（幂等） |
| `stage --suffix S --binary P` | 把某平台二进制放进对应子包（**校验静态链接 / 平台族 / 架构**） |
| `check` | **发布前硬门**：6 个子包都真有非空二进制、版本与平台字段一致 |
| `publish --phase platforms` | 发 6 个平台子包 |
| `publish --phase main --tag next` | 发主包到 `next` 标签 |
| `smoke --tag next` | **真实 npx 安装 + 启动**冒烟（空目录里跑 `--help`） |
| `promote` | 把 `latest` 切到当前版本（幂等，可重试） |
| `verify --phase platforms\|latest` | 查 registry：子包齐 / 7 包齐 + latest 指向（带重试） |

`bash scripts/check-version.sh` 额外校验：`client/Cargo.toml` / `npm/package.json` /
`server.json` / 6 个子包版本全部一致，平台表与 `run.js`、CI 矩阵一致。
CI 的 `python` job 也会跑它（漂移在 PR 阶段就被拦下）。

### 3.1 版本号在哪里（改版本时必须同时改）

| 文件 | 字段 | 谁改 |
|---|---|---|
| `client/Cargo.toml` | `version` | 手动 |
| `npm/package.json` | `version` | 手动 |
| `server.json` | `version` + `packages[0].version` | 手动 |
| `npm/platforms/*/package.json` | `version` | **`generate` 自动同步** |
| `npm/package.json` | `optionalDependencies` | **`generate` 自动同步** |

```bash
# 改完前三处后：
python3 scripts/make-platform-packages.py generate
bash scripts/check-version.sh v0.0.5
```

## 4. 排障

> 本表是**故障对照表**：正常发布路径只有 `bash scripts/release-client.sh x.y.z` 一条，
> 下面的条目只在出问题时才需要读。§6 是历史事故复盘，**不参与正常流程**。

| 现象 | 原因 / 处置 |
|---|---|
| `check` 报「缺二进制」 | 该平台没 stage。**不要绕过** —— 缺一个平台就是该平台用户静默装不上 |
| `stage` 报「动态链接」 | 编的是 gnu 目标；用 `--target x86_64-unknown-linux-musl` |
| `stage` 报「产物格式是 elf 但需要 macho」 | 二进制定位错了，或平台表写错 |
| 用户报「找不到本平台的二进制」 | 该平台子包没发/版本不一致。`npm view zace-client-<os>-<arch> version` 确认；`check-version.sh` 定位 |
| 用户 `npx` 行为没变 | npx 缓存了旧包。配置里加 `--prefer-online`（§1 已是标准形态） |
| `npm publish` 报 `cannot publish over` | 该版本号已发布过（**不可逆**）。换 patch 版本号 |
| `npm publish` 报 `403 … Package name triggered spam detection` | **包名**被 npm 防刷规则拦（不是速率）。实测：`zace-client-win32-x64` 必然被拒，改名 `zace-client-windows-x64` 即通过 —— `win32` 是恶意软件命名的常见特征词。**注意**：npm 包名用 `windows`，而 package.json 的 `os` 字段必须仍是 `win32`（Node `process.platform` 的取值） |
| CI `publish` 401 | 缺 `NPM_TOKEN` secret，或 token 不是 Automation 类型 |
| `latest` 没指到新版本 | `promote` 步骤失败：手动 `npm dist-tag add zace-client@<v> latest` |
| 想回退 latest 到旧版本 | `npm dist-tag add zace-client@<旧版本> latest`（**不要**用 `npm unpublish`） |

## 5. 为什么删掉 GitHub 下载回退

早期形态是「启动器按版本号去 GitHub Release 下载二进制」。两个真实故障（2026-09-16 实测）：

1. **Node 默认不读 `https_proxy`**（只认 `NODE_USE_ENV_PROXY=1`，v20+），
   代理环境里启动器直连 GitHub → 命中共享出口 IP 的 API 限流：
   同一时刻 `curl`（走代理）200、`node`（直连）403 `rate limit exceeded`。
   用户看到的是 `MCP server failed to start: connection closed`，排查代价极高。
2. **版本对齐是人为纪律**：`npm publish` 必须等 Release 资产全绿，慢一步就是 404。

更深一层的理由（**这才是删回退的真正原因**）：保留任何“自动下载”路径都等于
**两条分发渠道并存** —— 出错时无法判断用户拿到的是哪个二进制
（npm 的？还是 GitHub 上的旧货？），排查会往错误方向跑。

故现在：子包找不到就**显式失败**，并打印平台信息与可操作指引
（`npm view <子包> version` 是第一步）。“第一次只发 Linux”这类过渡也不允许 ——
缺失平台是**静默**故障，用户侧没有任何提示。

## 6. 历史事故复盘（不参与正常流程，仅供排查参考）

### 0.0.5：首次发布卡在 Windows 包，最终放弃该版本

**现象**：build 六平台全绿、stage/guard 通过、前 4 个包（linux×2 + darwin×2）发布成功，
从第 5 个起失败；流水线按设计停在 `pre-verify`，**主包未发布、latest 仍指旧版本**
（这就是"六步流水线"要保住的东西）。

**第 5 个包的完整错误**（包名是 `zace-client-win32-x64`）：

```text
403 Forbidden - PUT https://registry.npmjs.org/zace-client-win32-x64
Package name triggered spam detection; if you believe this is in error,
please contact support at https://npmjs.com/support
```

**根因是包名，不是发布速率**：错误信息明确指向包名，且同一次发布里前 4 个包成功。
`win32` 是恶意软件命名的常见特征词，被 npm 防刷规则命中。

> 曾被误判为"9 秒连发 4 个新包触发限流"。该假设已被上述证据否决，
> **未落地任何节流代码** —— 如果以后遇到真正的速率限制，错误串会是
> `429`/`rate limit`，而不是 `spam detection`。以错误串为准。

**修法**（0.0.6）：子包名 `zace-client-win32-*` → `zace-client-windows-*`；
**`os` 字段保持 `win32`**（Node `process.platform` 取值，改了会装错平台）；
加了守卫 `test_no_win32_in_package_names` 防回归。

**版本处置**：0.0.5 的 tag 与已发布的 4 个子包**保持不动**（npm 版本不可撤回），
升到 0.0.6 重新完整发布；0.0.5 从未发主包，用户无感知。
这就是"失败不移动 tag、递增新版本"这条约定的来源。

### 结论（沉淀成规则）

1. 发布是**七步不可逆流程**，必须由 `release-client.sh` 一条命令走完，
   避免手工零散执行造成状态半成品（0.0.5 就是半成品：4 个子包已占版本号）；
2. 失败时**放弃版本号**，不要试图修补已有 tag/版本；
3. npm 报错先看**完整错误串**，不要凭"时间间隔"猜原因。

## 7. 与其它发布步骤的关系

| 改动类型 | 要不要发 npm |
|---|---|
| `client/` 的任何改动（含工具 description） | **要**。MCP 的 `tools/list` 由 client 声明，service 那份到不了 AI 眼前 |
| 只改 core 检索 / service / 前端 | 不要（但 service 需重启，前端需重建） |
| 改 `docs/contracts/mcp-tools.json` | 要（**且需同步 `client/contract/`**） |

CLI 版本一致性：`client/Cargo.toml` 与 npm 包版本必须相同（`check-version.sh` 守住）。

## 相关文档

- 重建前端 / 重启服务 → [`README.md`](README.md)
- 部署（VPS / WSL）→ [`../deployment/vps.md`](../deployment/vps.md)、[`../deployment/wsl-live.md`](../deployment/wsl-live.md)
- 用户接入手册 → [`../getting-started/agent接入与API-Key.md`](../getting-started/agent接入与API-Key.md)
- npm 包自身说明 → [`../../../npm/README.md`](../../../npm/README.md)
