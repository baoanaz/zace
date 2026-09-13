# TASK-040R：zace-client（Rust MCP stdio 客户端 + 本地同步代理）

> 状态：review ｜ 阶段：Phase 2（M2c，MCP 最终形态） ｜ 硬依赖：TASK-033（同步 API，done）/ TASK-051（就绪度预研，review） ｜ soft 依赖：TASK-060（鉴权，未开卡）
> 建议分支：`feature/task-040r_xwz0913`
> 交付物所有权：
> - `client/**`（Rust 工程；`client/README.md` 可改）
> - `docs/tasks/TASK-040R-client骨架与同步代理.md`（本卡）
> - `docs/tasks/README.md`（状态行）
>
> 清单外文件不得改（**不改 `core/**`、`service/**`、`docs/contracts/**`、`docs/design/**`**）。

## 目标

交付 MCP 的**最终形态**（R38 / D-39 / `Background/01-notace-tool-rs.md`）：编辑器以 stdio 拉起本地
`zace-client`，client 负责扫描 / 三层忽略 / CF-02 哈希 / 增量上传 / checkpoint，**检索与渲染仍在服务端**
（D-21）。本地 MCP（service 直出 Streamable HTTP，TASK-040）只作短期验证。

**被谁消费**：Claude Code / Codex / Cursor 等支持 stdio 的 harness（TASK-040 的 HTTP 形态无法覆盖它们）。

## 输入文档（按序读）

1. `docs/plan/cloud-mcp-readiness.md`（**本卡的直接前置**：A1 鉴权 / A2 身份 / A3 归一化 / A5 新鲜度 / A10 现成资产）
2. `docs/design/Background/01-notace-tool-rs.md`（参考实现的完整报告）
3. `docs/design/Module/05-MCP与同步.md` §2-§5
4. `docs/contracts/mcp-tools.json`（CF-06）、`docs/contracts/openapi.yaml`（CF-05）
5. 参考源码：`/home/xuwenzheng/github/ACE/example/notace-tool-rs`（**只读**）

## 冻结接口（本卡不得变更）

- **消费**：CF-02（`blob_hash` = `sha256(path‖0x00‖content)`）、CF-05（REST 端点与字段名）、
  CF-06（两个工具名/参数名/上限）、D-29（`identityKey` / `projectId` 算法）。
- **产出**：无新契约（本卡不碰契约文件）。若后续需要新增配置或字段，走 L2 流程。

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `client/Cargo.toml`、`client/Cargo.lock` | Rust 工程（binary crate；锁文件入库保证可复现构建） |
| `client/src/lib.rs`、`main.rs` | 装配与 CLI（`--base-url` / `--token` / `--cache-root`，全部支持环境变量） |
| `client/src/identity.rs` | D-29 身份（**与 core 逐字节一致**；含跨语言常量测试） |
| `client/src/blobref.rs` | CF-02 `blob_hash`（含 `0x00` 分隔符）+ 二进制判定 + 控制字符清洗 |
| `client/src/ignore.rs` | D-28 三层忽略（`ignore` crate + 内置目录名/模式） |
| `client/src/index.rs` | 本地缓存（`~/.cache/zace/<projectId>/`）+ 已验证缓存命中 + 对账 |
| `client/src/remote.rs` | CF-05 客户端（resolve / batch-upload / deletions / checkpoint / query） |
| `client/src/tools.rs` | CF-06 两个工具 + 懒同步编排（身份→resolve→扫描→上传→checkpoint→检索） |
| `client/src/protocol.rs` | MCP stdio（JSON-RPC 2.0；stdout 纯净；错误三分类） |
| `client/examples/identity.rs` | 身份手工核对入口（跨语言对照） |

## 验收标准（DoD）

- [x] `cargo test` 全绿（**33 passed**）；`cargo clippy --all-targets` 无告警；`cargo fmt` 已跑
- [x] **跨语言一致性**：Rust 与 Python（`zace_core.identity`）对同一仓库算出**同一** `identityKey` / `projectId`
      （实测：`782e76df…` / `56689f49a838cb78`）
- [x] **端到端**：真实 `zace-service`（`ZACE_LOCAL_MODE=false`）+ 真实 stdio 会话
      （initialize → tools/list → search_context → ask_project）返回带「文件:行号」的证据
- [x] **懒同步**（D-27）：追加一个函数后再次调用，新函数立刻可检索（无需手动同步）
- [x] 错误面：相对路径/反斜杠 → JSON-RPC `-32602`；未知工具 → `-32602`；服务端故障 → `isError: true`
- [x] 基线三条仍绿（本卡不改 Python 侧）：`uv run ruff check .` / 依赖方向 / `uv run pytest`
- [x] 本卡"执行记录"已回填；任务板状态改 `review`

## 明确不做（留给后续卡）

| 不做 | 理由 |
|---|---|
| 鉴权（Bearer token 的**服务端**实现） | TASK-060/061；client 侧已支持 `--token` 并在错误文本里脱敏 |
| checkpoint 自愈的 **stale-blob** 分支 | 需要服务端返回 stale 列表的语义（CF-05 目前不返回）；另开卡 |
| 首同步进度反馈（D-31 的 120s 转后台） | 当前上传在 tool call 内同步完成；大仓库体验优化属后续卡（TASK-062） |
| `npx zace` npm 分发 / gzip / 并发上传 | 优化项，不阻断可用性 |
| 修改 core/service 任何文件 | 本卡是纯新增（`client/`）；服务端缺口（A1 鉴权）另行开卡 |

## 参考源码锚点（只读）

`/home/xuwenzheng/github/ACE/example/notace-tool-rs`（本机已具备）：
`src/blobref.rs`（blob/hash）、`src/index.rs`（缓存/verified hit）、`src/finnian.rs`（同步编排/自愈/超时）、
`src/protocol.rs`（stdio/协议版本/错误映射）。**只学架构与纪律，不复制实现**（Demo.md §1）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

### 2026-09-13 · 实施 AI · 分支 `feature/task-040r_xwz0913`（从 TASK-051 分支串联）

**与参考实现（notace）的四处关键差异**（zace 的 CF-02/CF-05 已冻结，不能照搬）：

| 主题 | notace | zace-client | 依据 |
|---|---|---|---|
| blob 哈希 | `sha256(path‖content)` **无分隔符** | `sha256(path‖0x00‖content)` | CF-02 / D-43；有专门测试证明两者不同 |
| 切片 | 超 400 行按行切成 `path#chunk1of3` | **文件级一文件一 blob**，不切块 | D-02：切片是服务端 AST 符号级职责 |
| 项目定位 | 只传 blob 名单，服务端自己认 | **先 `POST /api/projects/resolve`**（D-29） | 就绪度报告 §2 A2（**这是云端 MCP 的正解**） |
| 上传载体 | 明文 `content` 字段 | **base64 `contentB64`** | CF-05（JSON 二进制安全编码） |
| blob 名 | 无分隔符 hash | CF-02 hash | 服务端账本按 CF-02 校验 |
| 检索 | `POST /agents/codebase-retrieval`（带 blob 名单） | `POST /api/query/search`（`projectId` + 可选 `checkpointId`） | CF-05 |

**有意改进（`Background/01` §7 的建议）**：

1. **缓存不放工作区**：`~/.cache/zace/<projectId>/index.json`（notace 放项目内 `.not-ace-tool/`），
   不污染仓库、不与 `.gitignore` 纠缠；
2. **`ignore` crate 做真实 `.gitignore` 解析**（含否定规则），而不是硬编码目录名列表；
3. **内置目录用模式**（`cmake-build-*` / `build-*` / `out` …）而非穷举；
4. **跳过原因结构化**（`oversize:<size>` / `binary` / `unreadable`），为 R43 的"如实报告"留接口。

**验收命令与结果**

```console
$ cd client && cargo test
test result: ok. 33 passed; 0 failed               # 单元测试（含跨语言常量表）
$ cargo clippy --all-targets
Finished `dev` profile（无告警）
$ cargo fmt --check                                  # 已格式化
```

端到端（真实 service + 真实 stdio 会话）：

```text
=== healthz ===
{"status":"ok","localMode":false,"auth":"enabled",...}

[1] initialize -> {'name': 'zace', 'version': '0.0.1'} protocol= 2025-11-25
[2] tools/list -> ['search_context', 'ask_project']
[3] search_context -> isError = False
[E2] SessionStore.refresh_token — src/session.py:1-13
     reason: bm25 -2.7887 + bm25 rank 1 + vector 0.8712 + vector rank 3 + 相邻区间合并
[4] ask_project -> isError = False
[zace] status=degraded
[5] 相对路径 → JSON-RPC error = -32602 project_root 必须是绝对路径
stderr: (空)                                        # stdout 协议纯净
projectId= 56689f49a838cb78 name= demo-repo         # 服务端项目
cache/56689f49a838cb78/index.json                   # 客户端缓存目录 = 同一 projectId
```

**跨语言身份一致性**（云端正确性的关键，就绪度报告 §2 A2'的必补测试）：

```text
Python(core) identityKey = 782e76dfd0f59c077672539d46074ea59ddd0ddb9b9c5019b291e6381dfebe4c
Rust(client) identityKey = 782e76dfd0f59c077672539d46074ea59ddd0ddb9b9c5019b291e6381dfebe4c
Python(core) projectId   = 56689f49a838cb78
Rust(client) projectId   = 56689f49a838cb78
```

**懒同步实测（D-27）**：稳态查询 3.15s（进程冷启动为主）→ 向 `src/session.py` 追加
`revoke_token()` 后再次调用 **0.20s**，命中 `[E1] SessionStore.revoke_token — src/session.py:1-18`，
服务端 chunks 7 / symbols 4——增量上传 + 重建 checkpoint 生效。

**契约影响**：无（本卡纯新增 `client/`，未改任何契约文件与 Python 代码）。

**与设计偏差**：一处**已记录的语义分歧**（不留隐患，写清在 `client/src/ignore.rs` 的模块文档里）：
`ignore` crate 默认豁免被 git 跟踪的文件，而 core 的 Python 实现按纯规则匹配。该分歧只影响
"被 `.gitignore` 命中但已被 git 跟踪"的文件（编排者在 TASK-037 实测约 1.9%）。R42 要求的是
`ignore` crate 语义，故**客户端行为合规**；两侧完全一致需专项对照测试卡。

**未决问题（附建议）**

1. **服务端鉴权（A1）是 TASK-040R 上线的硬前置**：client 已支持 `--token`，但服务端现在
   **无鉴权**（带无效 token 也放行，见就绪度报告 A1）→ 建议把 TASK-060 提为硬依赖。
2. **A3（D-29 协议形式归一化）未做**：`git@` 与 `https://` 仍是两个 project → 属 L3，待拍板；
   本卡已在 `identity.rs` 用测试锁住当前行为，归一化时改一处即可。
3. **stale-blob 自愈分支未做**（现状：服务端不返回 stale 列表）→ 另开卡，或作为 checkpoint
   语义澄清（就绪度报告 A8）的一部分。
4. **缓存目录约定**：`~/.cache/zace/<projectId>/`（新增的本地路径约定，非契约）——若未来
   `zace-meta.db`（Module 06 §2.4）落地，需一并考虑迁移。
