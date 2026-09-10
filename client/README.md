# zace-client（Phase 2）

Rust 单二进制（Module/05）：MCP 适配层（薄协议壳）+ Workspace 同步客户端（厚实本地代理）。

- 两个工具：`search_context` / `ask_project`（不暴露底层检索工具，D-12）
- 懒同步：每次 tool call 自动保证工作区新鲜（D-27），无常驻 watcher
- 忽略三层：`.zaceignore` > `.gitignore`（真实解析）> 内置默认（D-28）
- checkpoint / blob hash / 断点续传 / 分层超时矩阵（D-31/D-32）

Phase 0/1 期间本目录只放任务规划，不写代码；Rust 工程在 Phase 2 由 TASK-CLIENT-* 系列初始化。
