# TASK-037：索引范围策略落地（三层忽略规则 + 大小/二进制阈值）

> 状态：pending ｜ 阶段：Phase 2（M2b）｜ 硬依赖：TASK-036（它先给出规模实测数字，本卡用那些数字做前后对照）｜ soft 依赖：无
> 建议分支：`feature/task-037_<你的缩写><MMDD>`（从 TASK-036 分支串联）
> 交付物所有权：
> - `core/zace_core/pipeline/ignore.py`（新建：忽略规则引擎）
> - `core/zace_core/pipeline/source.py`（`DirectorySource` 与 `DEFAULT_SKIP_DIRS`）
> - `core/zace_core/pipeline/indexer.py`（**仅** §B 的阈值接入与 `skipped_files` 原因）
> - `core/tests/pipeline/**`（含 `test_ignore.py`）
> - `benches/results/robustness-scale.md`（**追加**"TASK-037 前后对照"章节，不改 TASK-036 的原始数字）
>
> 清单外文件不得改。

## 目标

让索引**只收该收的东西**。当前 `DirectorySource` 只按目录名跳过（`.git` / `node_modules` / `build` …），
实测后果（编排者在 hmi 仓库上量的）：

```text
linux-mtk-hmi：1667 个"可索引"文件中，绝大多数来自 cmake-build-release/**
                仓库 880 MB，含 301 个 >200KB 文件、最大 46 MB
systemservice：含 76 MB 单文件；cameraservice：含 lib/libcv.a（308 MB）
→ 这些都不该进索引：它们不是源码，却会吃掉索引时间、磁盘与检索噪声
```

**为什么归 core**（R42/R43）：D-28 把 `.gitignore` 真实解析放在 client（Rust `ignore` crate），
但 M2a 本地模式没有 client（R38），而本地模式的索引就在 core 里发生。
**契约是忽略"语义"，不是库**：将来 client 用 `ignore` crate 时，两侧行为必须一致。

## 输入文档（按序读，只读所需章节）

1. `docs/design/Module/05-MCP与同步.md` §3.1（**三层优先级 + 通用过滤的确切参数：128KB / 10% 不可打印**）
2. `docs/design/Module/01-切片存储.md` §6（"一 project 一 repo"与忽略相关的开放问题）
3. `docs/plan/contracts.md` §3.9（**R42/R43 是本卡的直接依据**）
4. `docs/tasks/TASK-036-多仓库规模自举与健壮性.md` 的报告（前后对照的基线数字）

## 冻结接口（本卡不得变更）

- **消费**：CF-01/CF-08（`IngestReport.skipped_files` 语义）、`SourceProvider` 协议。
- **产出**（TASK-041R 的 Rust client 需对齐同一语义）：
  - `zace_core.pipeline.ignore.IgnoreRules`：`from_root(root) -> IgnoreRules`、`is_ignored(path, *, is_dir) -> bool`、`reason_for(path) -> str | None`
  - `zace_core.pipeline.ignore.IndexScope`（阈值部分）：`should_read(path, size) -> tuple[bool, str | None]`

## §A 三层忽略（语义必须与 D-28 一致）

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1（最高） | `{repo}/.zaceignore` | 项目自定义，语法同 gitignore |
| 2 | `.gitignore`（仓库内各层目录的都要生效） | **真实解析**：注释、`!` 否定、目录尾 `/`、`**`、前导 `/` 锚定、`*`/`?`/`[]` 字符类 |
| 3（兜底） | 内置默认 | 现有 `DEFAULT_SKIP_DIRS` + 常见产物目录（**注意**：`build` 已在列表里，但 `cmake-build-release` 不在 → 需要模式化，不是穷举） |

- 否定规则（`!pattern`）必须能"救回"被上层忽略的文件（git 语义：后面的规则覆盖前面的）。
- **不读** `{repo}/.git/info/exclude` 与全局 `core.excludesFile`（V1 从简，写在报告里）。
- `.gitignore` 不存在时行为必须与现状一致（不报错）。
- 目录剪枝：被忽略的目录**不得**被遍历（性能关键——`cmake-build-release/` 下有几万个文件）。

## §B 通用过滤阈值（R43：与 Module/05 §3.1 同口径）

- `> 128 KB` 的文件 → 跳过，`skipped_files` 里带**原因**（例如 `"oversize:134217728"`）；
- 判定为二进制（**前 8 KB 中不可打印字符 > 10%**，避免读全量）→ 跳过，原因 `"binary"`；
- 阈值可配置（`Settings` 或环境变量），默认值即上述；
- **行为变更必须如实报告**：这些文件以前被索引，现在不索引了 → 报告里给出前后对照
  （文件数、chunk 数、耗时、磁盘），并且**不要**把 `skipped_files` 当错误（它本来就存在此字段）。

## §C 前后对照实测（本卡的核心证据）

在**同一批靶场**上重跑 TASK-036 §A 的命令，贴出对照表：

| 仓库 | 索引文件数 前→后 | chunks 前→后 | 耗时 前→后 | 索引体积 前→后 | skipped（按原因分组） |
|---|---|---|---|---|---|

至少覆盖：`linux-mtk-hmi`、`linux-mtk-mw-systemservice`、`Trellis`（或 TASK-036 报告里耗时最长的两个）。

**预期方向**（不作为 DoD 数字，只要如实报告）：hmi 的索引文件数大幅下降、耗时下降；
`cameraservice` 不再吞 308 MB 的 `lib/libcv.a`。

## §D 检索影响抽查（防止"少索引 = 检索变差"）

- 用**已存在**的 golden 子集（`benches/golden/linux-mtk-mw-cameraservice`，16 条）跑 `zace-core eval`，
  对照 TASK-014 基线数字；若指标下降，**如实报告并分析原因**（哪些用例的证据文件被忽略了？）。
- **纪律**：这是**回归检查**，不是调参；不得为了让数字好看而放宽忽略规则（R30）。
- 若 golden 用例的期望文件本身属于"应忽略"的类别（构建产物/二进制），**不要改用例**，
  在报告里标注"该用例期望与忽略策略冲突，需编排者裁定"。

## 验收标准（DoD）

- [ ] `core/tests/pipeline/test_ignore.py` 覆盖：三层优先级、`!` 否定、目录尾 `/`、`**`、
      前导 `/` 锚定、字符类、嵌套 `.gitignore`（子目录同名文件）、`.zaceignore` 覆盖 `.gitignore`、
      `.gitignore` 缺失时行为不变；**每条都要有一个真实形状的 fixture**（不要只测自制玩具样例）。
- [ ] 阈值：`>128KB`、二进制判定（用真实二进制 fixture，如 `.a` 或压缩包的一小段）、
      `skipped_files` 原因字符串、可配置性各一条。
- [ ] **性能**：被忽略目录不被遍历（测试用 `monkeypatch` 计数 `Path.rglob`/`stat` 调用，
      或构造大目录树断言耗时上界——二选一，说明理由）。
- [ ] §C 前后对照表 + §D 检索回归结果，写进报告。
- [ ] 自举实证（**必做**）：`uv run zace-core ingest --repo <hmi 仓库> --data /tmp/zace-037-hmi`
      完整输出贴进执行记录；再跑一条检索证明仍能命中真实源码。
- [ ] 基线三条全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、`uv run pytest`
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- 不实现 `.git/info/exclude` / 全局 excludes（V1 从简，报告里说明）。
- 不改 `zace-core ingest` 的 CLI 参数结构（如需 `--no-ignore` 之类的开关，先在报告里申请）。
- 不动 client / service 侧（Rust client 的对齐要求写在契约里，实现归 TASK-041R）。
- 不调检索质量参数（R30）；不为了让 eval 数字好看而放宽规则。
- 不做增量扫描的 mtime 快路径（那是 TASK-041R/062 的优化项）。

## 参考源码锚点（只读）

- `core/zace_core/pipeline/source.py`（`DEFAULT_SKIP_DIRS` / `DirectorySource.list_files`）
- `docs/design/Module/05-MCP与同步.md` §3.1（忽略规则的原始定义与参数）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写；**必须包含 §C 的前后对照表**。

## 执行记录

（实施 AI 在此填写。）
