# TASK-052：zace-client 的 npm 分发（供 Codex / Claude Code / pi 接入）

> 状态：review ｜ 阶段：Phase 2（M2c） ｜ 硬依赖：TASK-040R（client，review） ｜ soft 依赖：TASK-060（鉴权，未开卡）
> 建议分支：`feature/task-052_xwz0913`（从 TASK-040R 分支串联）
> 交付物所有权：
> - `npm/**`（`package.json` / `run.js` / `README.md`）
> - `server.json`（MCP registry 清单）
> - `.github/workflows/release.yml`（多平台构建 + 发布）
> - `client/tests/stdio.rs`（二进制级 stdio 验收；`client/**` 属 TASK-040R，本卡延续其所有权）
> - 本卡与 `docs/tasks/README.md`（状态行）
>
> 清单外文件不得改（不改 `core/**`、`service/**`、`docs/contracts/**`、`docs/design/**`）。

## 目标

让用户**只改配置**就能把 zace 接进 AI Agent：`npx zace-client --base-url <URL>` 即可作为 stdio MCP
server 被拉起。覆盖用户点名的三类客户端：**Codex CLI**（`~/.codex/config.toml`）、
**Claude Code**（`claude mcp add-json`）、**pi**（经 `pi-mcp-adapter` 读标准 `.mcp.json`）。

**验收口径（用户明确）**：只要 MCP 侧"请求成功"即可视为本卡成功——工具即便返回 `isError`
（如服务端未起、索引为空）也算协议与接入链路打通。

## 输入文档

1. `docs/tasks/TASK-040R-client骨架与同步代理.md`（本卡的前置：client 已可用）
2. `docs/plan/cloud-mcp-readiness.md` A1（鉴权缺口，影响配置项语义）
3. 参考实现：`/home/xuwenzheng/github/ACE/example/notace-tool-rs` 的 `npm/run.js`、
   `npm/package.json`、`server.json`、`.github/workflows/release.yml`（**只读**）

## 冻结接口（本卡不得变更）

- 消费：TASK-040R 的 CLI 契约（`--base-url` / `--token` / `--cache-root` 及对应环境变量）。
- 产出：**npm 包名 `zace-client`**、**二进制名 `zace-client`**、**五个资产名**
  （`zace-client_{Linux_x86_64,Linux_aarch64,Darwin_universal,Windows_x86_64,Windows_aarch64}`）
  —— `npm/run.js` 与 `release.yml` 必须同名（已用命令对账，见执行记录）。

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `npm/package.json` | 包元数据（`bin` → `run.js`；`os`/`cpu` 声明） |
| `npm/run.js` | 启动器：缓存目录定位 → Release 下载（重试 + 文件锁）→ 解压 → **本地回退** → inherit 拉起二进制 |
| `npm/README.md` | 四类客户端的可复制配置（Claude Code / Codex / pi / Cursor） |
| `server.json` | MCP registry 清单（stdio 传输 + 两个 runtime 参数） |
| `.github/workflows/release.yml` | tag 触发的五平台构建与发布 |
| `client/tests/stdio.rs` | 二进制级验收（stdout 纯净 / 错误分类 / 服务端不可达不崩） |

## 验收标准（DoD）

- [x] `cargo test --test stdio` 全绿（5 条：协议纯净、参数错误码、不可达转 `isError`、解析错误不终止、缺参走 stderr）
- [x] `node --check npm/run.js` 通过；`npm/package.json`、`server.json` 为合法 JSON
- [x] **资产名对账**：`release.yml` 的 `asset_name` 与 `run.js` 的 `assetName()` 逐一对应（命令见执行记录）
- [x] **端到端（经 npm）**：真实 `zace-service`（非本地模式）+ `node npm/run.js`
      → `initialize` / `tools/list` / `search_context` 返回带「文件:行号」的证据
- [x] 缓存目录名 == 服务端 `projectId`（证明身份链路一致）
- [x] 工作区基线三条全绿；本卡"执行记录"已回填；任务板状态改 `review`

## 明确不做

| 不做 | 理由 |
|---|---|
| 五个平台包（`npm/platforms/*` 子包） | 二进制放在 GitHub Release，包装器按需下载；子包是另一种分发形态，暂不需要 |
| 真正 `npm publish` / 打 tag / 发 Release | 需要用户账号凭据与仓库权限；本卡只交付可发布的产物 |
| `postinstall` 预下载 | 会让 `npm i` 变慢且离线失败；改为**首次运行时**下载（懒加载） |
| 服务端鉴权实现 | TASK-060/061（见就绪度报告 A1） |
| 客户端切片/检索逻辑 | D-02/D-34：切片与检索在服务端，客户端只做同步代理 |

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

### 2026-09-13 · 实施 AI · 分支 `feature/task-052_xwz0913`

**交付**：npm 分发（`npm/` + `server.json` + `release.yml`）+ 补齐 TASK-040R 缺失的**二进制级 stdio 测试**。

**为什么要补 `client/tests/stdio.rs`**：notace 有这一层而 TASK-040R 没有。协议在"有任何东西写到
stdout"那一刻就碎了，**单元测试抓不到**（它只测函数不测进程）。本卡补上后，五条断言覆盖：
帧纯净、参数错误码、服务端不可达转 `isError`、解析错误不终止循环、缺参诊断只走 stderr。

**验收命令与结果**

```console
$ cd client && cargo test --test stdio
running 5 tests
test stdout_carries_only_json_rpc_frames ... ok
test argument_errors_use_json_rpc_error_codes_without_touching_the_network ... ok
test unreachable_server_becomes_an_is_error_result_not_a_crash ... ok
test malformed_json_produces_a_parse_error_without_killing_the_loop ... ok
test missing_base_url_fails_loudly_on_stderr_with_clean_stdout ... ok
test result: ok. 5 passed; 0 failed

$ node --check npm/run.js && node -e "…JSON.parse…"
run.js 语法 OK / JSON 均合法

# 资产名对账（release.yml 与 run.js 必须逐一对应）
$ grep -o "zace-client_[A-Za-z0-9_]*\.\(tar\.gz\|zip\)" .github/workflows/release.yml | sort -u
zace-client_Darwin_universal.tar.gz
zace-client_Linux_aarch64.tar.gz
zace-client_Linux_x86_64.tar.gz
zace-client_Windows_aarch64.zip
zace-client_Windows_x86_64.zip
$ grep -o "zace-client_[A-Za-z0-9_]*\.\(tar\.gz\|zip\)" npm/run.js | sort -u
（同上五项，完全一致）
```

**端到端（经 npm 包装器，真实 service）**

```text
service ready
[1] initialize -> zace 2025-11-25
[2] tools/list -> ['search_context', 'ask_project']
[3] search_context -> isError = False (首次 6.6s，含索引)
    ## Relevant Context
    ### Code
    [E1] SessionStore.refresh_token — src/session.py:1-9
[4] 二次调用 0.04s（缓存命中 + checkpoint 复用）

stderr: [zace-client] 改用本地已构建的二进制：…/client/target/release/zace-client
=== 缓存目录 vs 服务端 projectId ===
a11af9dfebef5b3b                      # 客户端缓存目录
服务端 projectId = a11af9dfebef5b3b   # 一致
```

**首次运行的三级降级链（实测各段）**

1. 缓存命中 → 直接拉起（不上网）；
2. 缓存未命中 → 从 `releases/tags/v<version>` 下载资产（带文件锁防并发、指数退避重试）；
3. 下载失败（本机实测 **HTTP 404**，因为还没发布 Release）→ **回退到本地已构建的二进制**
   `client/target/{release,debug}/zace-client`；再失败则给出三条可操作的安装指引并以非 0 退出。

**契约影响**：无（未改任何契约文件；`server.json` 是新增的 MCP registry 清单，非 CF-* 契约）。

**与设计偏差**：无。落点 `npm/` 与既有 `client/`、`web/` 平级，属 monorepo 内的分发目录，
不违反 D-33（四物理单元指运行组件；npm 是打包层）。

**未决问题**

1. **发布与命名**：包名暂定 `zace-client`，`server.json` 的 `name` 暂定 `io.github.baoanaz/zace-client`
   —— 发布到公共 npm / MCP registry 前需确认命名与账号（**属发布动作，需用户执行**）。
2. **CI 属首次引入 GitHub Release 流程**：`release.yml` 未在本机验证（无 CI 环境），
   只能保证"资产名与包装器约定一致"；首次打 tag 时需实测一次。
3. **鉴权（A1）**：配置文档里 `--token` 标注为"服务端鉴权落地后必填"；当前服务端放行所有请求。
4. **平台覆盖**：仅五平台（Linux x64/arm64、macOS universal、Windows x64/arm64）；
   其它平台走"源码构建"路径（`run.js` 里给了指引）。
