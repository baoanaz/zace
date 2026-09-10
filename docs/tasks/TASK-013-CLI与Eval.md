# TASK-013：core CLI + engine 装配 + golden runner

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-007、TASK-012 ｜ soft 依赖：无
> 建议分支：`feature/task-013_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/cli/`、`core/zace_core/engine.py`、`benches/run.py`、`core/tests/cli/`
## 目标

把索引、检索、组装装配成 `ContextEngine`（CF-07），并交付 `zace-core` CLI：
这是 M1 验收的**唯一人工入口**（Phase 2 的 service 将复用同一 engine）。

## 输入文档（按序读）

1. `core/zace_core/interfaces.py`（`ContextEngine` 冻结签名）
2. `docs/design/Module/06-服务化与部署.md` §1（core 纯库边界：CLI 是调试形态，不是产品面）
3. `docs/design/Module/05-MCP与同步.md` §3.4（D-29 project identity 规则，engine 在本卡实现基础版）
4. `benches/README.md`（golden 格式）

## 交付内容

### A. engine 装配（`engine.py`）

- 实现 `ContextEngine` 的过程化子集（`open/resolve_project/ingest/sync_status/search/delete_project`；`ask` 抛 NotImplemented 明确提示 Phase 3）。
- `resolve_project`：按 D-29 计算 identity_key（有 git remote → `sha256(remoteUrl + repo 相对路径)`；无 git → 绝对路径 hash），project_id = `sha256(identity_key)` 前 16 位十六进制；数据目录 = `data_root/projects/{project_id}/`。
- `search`：TASK-010 → 011 → 012 全链；`max_tokens` 透传预算。
- 索引同步语义：本卡为同步调用（service 层 Phase 2 负责异步 job 与进度）。

### B. CLI（`cli/`，argparse 即可，不要引入重型框架）

```text
zace-core ingest --repo <PATH> [--data <ROOT>] [--full]     # 全量/增量索引（--full 忽略增量）
zace-core search "<query>" --repo <PATH> [--data <ROOT>] [--max-tokens N] [--json]
zace-core status --repo <PATH> [--data <ROOT>]              # files/chunks/symbols/edges/freshness
zace-core eval --golden <DIR|FILE> --repo <PATH> --report <FILE>   # 跑 golden，写报告
```

- `--json` 输出 `ContextPack` JSON（走 CF-03 字段）；默认输出 Markdown 渲染。
- 退出码语义：0 成功；1 运行错误；2 参数错误。错误信息不得包含本机敏感绝对路径以外的内容（无 secret 场景）。

### C. golden runner（`benches/run.py`）

- 读取 `benches/golden/*.jsonl`（格式见 `benches/README.md`），逐条执行 `engine.search`，
  计算 **recall@5 / recall@10 / MRR**（命中判定：`expected` 中任一条的 `path` 出现且（若给 symbol）该 symbol 出现在候选/证据中）。
- 输出报告 Markdown（写入 `--report` 路径）：整体指标 + 分类指标（lang：中/英/混合；category）+ 逐条失败清单。

## 验收标准（DoD）

- [ ] `uv run pytest core/tests/cli -q` 全绿，必须覆盖：
  - E2E（fixture 小仓库）：`ingest` → `search` 返回含 `[E1]` 的 Markdown；`--json` 输出可被 CF-03 schema 校验；
  - 增量：二次 `ingest` 无重嵌入（计数 fake 或耗时断言）；
  - `status` 字段与 Store 实况一致；`--full` 触发全量重解析口径；
  - `eval` 对 3 条内置样例 gold 输出指标报告文件；
  - D-29 identity：同一 repo 路径两次 resolve → 同 project_id；`.git` 目录存在但无 remote → 路径 hash 分支。
- [ ] 手动验收（写入执行记录）：对本仓库 `zace/` 自身 `ingest` + 2 条中文查询 `search`，贴输出。
- [ ] **跨模块 E2E 断言（W3 起强制，见 contracts.md §3.3 R13）**：`ingest → search` 的端到端路径必须有一条测试，
      断言中文自然语言查询（≥5 token）能在**至少两个通道**命中目标符号且 `ContextPack.answerable is True`；
      不允许只测单层（本卡发现的 R11/R12 类缺陷只能由 E2E 暴露）。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/notace-tool-rs/src/main.rs`（CLI/二进制形态与 stdio 纪律，Phase 2 会细化）
- `source/codegraph/src/cli*`（子命令组织方式）

## 明确不做

- 不做 HTTP/service（Phase 2）；不做 ask/LLM（Phase 3）；不做 MCP（Phase 2 client）；
- 不做后台守护/常驻进程。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写：自举索引的真实耗时、chunks 数、两条查询结果摘要。）
