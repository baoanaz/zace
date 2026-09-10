# TASK-013：core CLI + engine 装配 + golden runner

> 状态：review ｜ 阶段：Phase 1 ｜ 硬依赖：TASK-007、TASK-012 ｜ soft 依赖：无
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

### TASK-013 完成报告（2026-09-10，泳道 F）

- 分支：`feature/task-013_xwz0910`（本地提交，未 push）
- 交付物：`core/zace_core/engine.py`、`core/zace_core/cli/{__init__,app,eval}.py`、
  `benches/run.py`、`core/tests/cli/`（31 用例）
- 认领时未单独提交 `in_progress` 状态：泳道模式单卡单分支，无并发认领风险；本提交一次性把
  卡片与任务板置 `review`。

#### 验收命令与结果

| 命令 | 结果 |
|---|---|
| `uv run pytest core/tests/cli -q` | **31 passed** |
| `uv run ruff check .` | clean |
| `uv run python scripts/check_dependency_direction.py` | 依赖方向检查通过 |
| `uv run pytest`（全仓基线） | **458 passed, 2 skipped**（无失败；`contextpack` 的 50ms 并发断言本次未误报） |

DoD 逐条对应（`core/tests/cli/`）：

- E2E fixture 仓库：`test_e2e_markdown_reports_numbered_evidence`（`ingest → search` 输出含 `[E1]` 的
  Markdown）、`test_e2e_json_validates_against_cf03_schema`（`--json` 过 CF-03 合同校验）；
- 增量：`test_second_ingest_is_incremental_and_reembeds_nothing`（计数 fake 断言零嵌入调用）、
  `test_modified_file_reembeds_only_changed_chunk`（改一个 docstring → 恰好 1 个 chunk 重嵌）；
- `--full` / status：`test_full_flag_triggers_full_reparse`（`invalidation=full_reparse` + 全量重解析）、
  `test_ingest_populates_index_and_status_matches_store`（`status --json` 与 `Store.counts()/freshness()` 逐字段相等）；
- eval：`test_eval_writes_metric_report`（3 条内置样例 → 报告文件 + 指标）；
- D-29 identity：`test_same_repo_path_resolves_to_same_project`、
  `test_git_remote_identity_is_shared_across_checkout_paths`、
  `test_git_dir_without_remote_falls_back_to_path_hash`；
- **跨模块 E2E（R13）**：`test_cross_module_e2e_target_hit_by_two_channels_and_answerable`——
  中文 NL 查询（jieba 分词后 13 token）→ 目标符号 `TokenService.refresh_token` 带
  `{'inferred': 2, 'vector': 5}` 两通道 + `ContextPack.answerable is True`；
  真实 Store + VectorStore + Indexer + retrieval + contextpack，embedding 用确定性假 provider。

#### 自举（对本仓库自身 ingest + 2 条中文查询）

1. **真实工作区 `zace-core ingest --repo .` 当前失败**（非本卡代码问题，见未决问题 U1）：
   `sqlite3.IntegrityError: UNIQUE constraint failed: chunks.id`（触发文件 `uv.lock`）。
2. 因此自举测量在**同内容副本**上完成（`tar` 复制工作区到 `/tmp/zace-self-ingest`，剔除 `.git` 与
   `uv.lock`；无 `.git` → 走 D-29 的"无 remote → 路径 hash"分支，顺带验证该分支）：

```
project: 6df6db722a2871c2 (created)      files: added=206 modified=0 deleted=0 parsed=206
chunks: new=2239 reused=0 removed=0      vectors: upserted=2239 deleted=0
graph: edges_retargeted=1289 unresolved_resolved=20 spec_refs=1819 ambiguous=202
elapsed: 366.1s          # 真实本地 ONNX（multilingual-e5-small, 384d）首次全量
```

3. 增量复跑同一命令：`elapsed: 0.1s`，`added/modified/deleted=0`、`chunks: new=0`、
   `vectors: upserted=0`（真仓库上确认增量口径）。
4. `zace-core status`：`files 206 / chunks 2239 / symbols 1397 / edges 6660 / pending_jobs 0`，
   `freshness` 为真实时间戳。
5. 两条中文查询（默认 Markdown 输出，`--data ~/.zace-test`）：

| # | 查询 | 命中 | 摘要 |
|---|---|---|---|
| 1 | `chunk_id 是怎么构成的？` | `[E1] chunk_id — core/zace_core/chunking/splitter.py:72-174` | reason 含 `inferred symbol chunk_id + inferred rank 1 + vector 0.9048`；`confidence: medium`；`budget: 10.0K/10.0K`（truncated） |
| 2 | `BM25 多词召回为什么会恒零命中中文查询` | `[E8] bm25_query_text — core/zace_core/retrieval/bm25.py` | reason **只有 `vector ... rank 10`**——R11 现象在自举中复现（长中文查询 BM25 零命中，仅向量通道）；`confidence: low`；`9.1K/10.0K` |

6. `zace-core eval --golden benches/golden`（现有 4 条样例，TASK-014 会扩充）：
   `recall@5 0.667 / recall@10 1.000 / MRR 0.542`（en 1.000、zh 0.500@5）；负例 `zace-0004` 通过 0/1
   （原因见 U3）。报告样例留在 `/tmp/zace-phase1-smoke.md`（`benches/results/` 属 TASK-014）。

#### 契约影响

**无契约变更（L1）**：未改 `docs/contracts/**`、`types.py`、`interfaces.py`、`hashing.py`。
`ContextEngine` 冻结面（`open/resolve_project/ingest/sync_status/search/ask/delete_project`）按 CF-07
原样实现，并有一条 `isinstance(engine, ContextEngine)` 的显式自证测试。

#### 与设计偏差（均为卡内允许的"实现级扩展"，逐条记录）

1. **engine 新增扩展入口**：`resolve_repo` / `ingest_repo` / `search_with_trace` / `project_dir` /
   `read_manifest` / `write_manifest` / 模块级 `plan_scan`。冻结接口只给 `resolve_project(identity_key)`
   （D-29 的 identity 计算按卡内要求放在 engine 侧，CLI 用 `resolve_repo` 组合二者）；
   `search_with_trace` 返回的 `SearchTrace` 额外带 `channels_used/degraded/candidates`——
   CF-03 的 `ContextPack` 没有 degraded 字段、组装后通道命中信息也被合并掉，E2E 断言需要一个
   不改契约的观察面。
2. **落盘状态两个文件**（都不属 CF-01）：`{project_dir}/project.json`（identity_key/display_name，
   兼作 `created` 标记）与 `{project_dir}/scan_manifest.json`（CLI 侧增量对账状态——Phase 2 client
   的 scan 状态本地版；`Store` 无"列出文件 hash"的公开读 API，且 Phase 2 的 ChangeSet 本就由调用方算）。
3. **CLI 面加了一个 `status --json`**（卡内 `--json` 只写了 search）：DoD 要求"status 字段与 Store
   实况一致"，机器可读输出便于逐字段断言；字段名 = `SyncStatus`（CF-08）的 dataclass 字段。
4. **`ingest` 同步执行但保留 job id 返回**（卡内"本卡为同步调用"）：job id 为 `job-sync-<12hex>`，
   语义是"已完成的 job"；异步/进度上报留给 Phase 2 service。
5. **R13 的 `core/tests/integration/` 未创建**：该目录归 TASK-016 交付，本波 TASK-016 与本卡并行
   且尚未合并。E2E 断言放在本卡所有权内的 `core/tests/cli/test_cli_search.py`；TASK-016 合并后由
   编排者决定是否搬迁/去重。
6. **未实现 D-28 忽略规则**（`.zaceignore`/`.gitignore`）：`pipeline/source.py` 的 docstring 把忽略
   规则记为"TASK-013/Phase 2"，但卡内 §B 的 CLI 面没有它，故未自行实现（依赖 `DirectorySource`
   内置跳过目录 + 卡外参数不变）。需要的钩子已就位：`plan_scan` 只消费 `source.list_files()` 的结果。

#### 未决问题（交编排者裁决）

**U1（阻断 M1 §6-1，建议新开卡修 TASK-002）**：兜底切分嵌套时分片偏移量丢失 → 行号错乱 + chunk id 冲突。

- 根因：`core/zace_core/parsing/fallback.py::_split(text, offset, ...)` 在 `_group(parts, ...)` 时
  **没有把 `offset` 加到** `_split_keep` 返回的相对偏移上（`_group` 记录的是相对 `text` 的偏移）；
  触发条件是"某个按 `\n\n` 切出的片段仍超限 → 递归再切"。
- 最小复现：`split_fallback("1\n…\n6\n\n7\n…\n12\n", max_lines=5)` → 第 3 块 `start_line=1`（应为 8）。
- 现场（`uv.lock`，1518 行）：11 个兜底块，第 9/10/11 块 start 为 `[1, 208, 1440]`（应为 ~1311/…）。
- 后果一：`core/zace_core/chunking/splitter.py::_fallback_chunks` 不做 id 去重（同文件非兜底路径的
  `add()` 有去重），出现两个 `uv.lock:(module):1` → `Store.apply_file_change` INSERT 抛
  `UNIQUE constraint failed: chunks.id` → `zace-core ingest --repo .` 直接失败（M1 §6-1 无法通过，
  影响任意含大文件/超长行文件的仓库）。
- 后果二（即使 id 不去重冲突）：行号错乱会让证据行号与实际内容错位，与 R12 同类，误导 agent 对齐编辑。
- 归属：TASK-002（`parsing/fallback.py`）+ TASK-006（`_fallback_chunks` 去重护栏）。**本卡未修改这两处文件**。

**U2（TASK-012 组装缺陷，建议开卡或并入 TASK-017 同批修复）**：spec 保底预留块被重复装填。

- 现象：`ContextPack` 里同一个 spec chunk 出现两次——一次是贪心装填（可能已被"相邻区间合并"扩成
  大块），一次是保底预留块（原始 span），两者 `path`/`headingPath` 相同、E 编号不同。
- 根因：`contextpack/assembly.py` 末尾 `if reserved is not None and reserved not in slots …: _place(...)`
  比较的是 **`_Slot` 对象**，而同候选在贪心循环里已由 `_build_slot` 生成过另一个 `_Slot` 对象。
- 真实仓库复现（`--data ~/.zace-test`，5 条查询中 2 条命中）：查询
  `BM25 多词召回为什么会恒零命中中文查询` → `docs/design/Background/06-core-engine-proposal.md`
  的 `2. 检索策略（核心） > 2.1 四路并行召回` 同时为 `E1`（173-232，含合并）与 `E28`（175-197，预留块），
  该次 pack 预算已是 `10.0K/10.0K`（truncated），重复块直接吃掉约 1.4K token 预算。
- 现有测试只覆盖"spec 会被挤出预算"的分支（`test_spec_floor_keeps_a_doc_even_when_last`），
  未覆盖"预留候选本来就能装下"的分支——这是单层测试无法暴露的 E2E 类缺陷。**本卡未修改 `contextpack/`**。

**U3（TASK-014 出题口径）**：`benches/golden/*.jsonl` 自身在被索引的仓库里，负例查询会被"查询字符串本身"
命中。自举中 `zace-0004`（PaymentGateway 负例）因 `benches/golden/sample.jsonl` 与
`core/tests/cli/test_cli_eval.py` 含该查询原文而拿到 BM25+Vector 双通道证据 → `answerable=True`。
建议 TASK-014 出题时把 golden 集排除出索引（依赖 D-28）或改用"仓库内确实不存在的符号"做负例。

**U4（非阻塞观察）**：`IngestReport.ambiguous_refs` 在零变更的增量 ingest 里仍报 200（它统计的是仓库
现存多义引用状态，不是本次增量），字段名容易被读成 delta；归 TASK-007 口径澄清。

#### 建议复核点

1. `engine.py` 的 `_assess` 相关假设：`answerable` 用的是 `consensus >= 2`（**候选**数 ≥2 带 ≥2 通道），
   所以"单个双通道候选"不等于 answerable——E2E 查询因此带两个标识符（注释已写明）；
2. `plan_scan` 的增量语义（未变化文件不进 ChangeSet → 不重解析、不重嵌）与 `--full` 的全量重解析分野；
3. `core/tests/cli/` 的 E2E 是否满足 R13 的意图，以及是否与 TASK-016 的 `core/tests/integration/` 合并；
4. `benches/run.py` 只做参数透传（命中判定/指标只有一份实现，在 `zace_core/cli/eval.py`）；
5. 提交前请确认 U1 的修复卡优先级（它挡着 M1 §6-1 的自举检查）。

