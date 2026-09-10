# 分发手册：波次、泳道与可复制提示词

> 面向用户：照着做即可，不需要懂 git 或开发细节。评审、测试与合并由总览 AI（编排者）负责。
> 面向实施 AI：每段提示词是自包含的，照其中步骤执行即可。

## 0. 你要做的三件事

1. **建工作区**（只需一次）：在任意终端执行
   ```bash
   bash /home/xuwenzheng/2_github/AI/ACE/zace/scripts/lane-worktrees.sh create
   ```
   它会在 `/home/xuwenzheng/2_github/AI/ACE/` 下建出 `zace-lane-a` … `zace-lane-f` 六个独立工作区（互不干扰，可同时开工）。
2. **开会话**：每一波按下方表格开对应数量的 AI 会话，**会话的工作目录必须是对应的工作区**（如泳道 A 用 `zace-lane-a`），然后把该泳道的提示词整段粘贴进去。
3. **收报告**：AI 做完会输出“完成报告”。把这些报告复制粘贴回总览会话（我），我评审+跑集成测试+合并，然后给你下一波的提示词。

> 若某个 AI 中途提问题、卡住或报错：把它的原话复制给我，我判断后给你处理方式。

### 已知事项（2026-09-10）

- **远程推送已修好**：origin 已从 HTTPS 换为 **SSH**（`git@github.com:baoanaz/zace.git`），本机 `~/.ssh/id_rsa` 已验证可认证（身份 baoanaz），`git push` 不再需要任何凭据输入。若以后新建仓库要推送，同样用 SSH URL 即可。
- **工作区里的“main”是本地 main**：不要自行 `git pull`。各泳道从本地 main 开分支，远端同步由编排者（总览 AI）在合并后统一推送；开工前按提示词里的核验命令确认 main 包含上一波提交即可。

## 1. 波次表（谁和谁可以同时做）

| 波次 | 同时开几个会话 | 泳道（工作区） | 任务卡（按序做） | 状态 |
|---|---|---|---|---|
| W1 / W2 | — | A/B/C/D/E | TASK-001..012 | 已完成 |
| W3a | 3 | B / C / F | TASK-016 / TASK-017 / TASK-013 | 已完成 |
| W3c | 2 | A / C | TASK-018 / TASK-019 | 已完成 |
| W3d | 2 | B / F | TASK-020（零成本版）/ TASK-014（基线） | 已完成 |
| W4a | 1 | A `zace-lane-a` | TASK-021 → TASK-022（质量修复） | 已完成 |
| W5a | 1 | A `zace-lane-a` | TASK-030 → 031 → 032 → 033（Phase 2 M2a-1：service 外壳） | 已完成 |
| W5b | 1 | A `zace-lane-a` | TASK-035 → 034（进行中）→ 040 → 045 | 进行中 |
| **W5c** | **3** | **A / B / C** | A：续做 TASK-034 → 040 → 045（demo 收口）；B：TASK-015A（模型选型）；C：TASK-036 → 037（规模自举 + 索引范围） | **当前波次（整夜并行）** |

## 2. 提示词（整段复制）

### W1-1 · 泳道 A（TASK-001 存储层）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 A：索引存储线】。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-a
启动会话时应把工作目录设为该路径。若当前工作目录不是它，先停下来提醒我，不要改任何文件。

【开工】
1. 读：AGENTS.md、docs/plan/orchestration.md 的"泳道模式"节、docs/tasks/README.md。
2. 完成 1 张任务卡：docs/tasks/TASK-001-存储层.md（严格按卡内"输入文档 → 冻结接口 → 交付物 → 验收标准"执行）。
3. 工艺：
   a) git switch -c feature/task-001_xwzMMDD main      ← 把 MMDD 换成今天的月日
   b) 只修改任务卡"交付物（文件所有权）"清单里的文件；其他文件一律不动
      （特别是 docs/design/**、docs/contracts/**、../source/**、别人的模块目录）。
   c) 跑通任务卡"验收标准"里的全部命令，外加基线三条：
      uv run ruff check .
      uv run python scripts/check_dependency_direction.py
      uv run pytest
   d) 回填任务卡"执行记录"节，并把 docs/tasks/README.md 里 TASK-001 那行状态改成 review。
   e) git add -A && git commit（提交信息以 "task-001: " 开头）。
4. 做完直接输出报告，不要等我确认。

【报告格式】
- 卡号 / 分支：
- 验收命令与结果：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切到 main、不 force push；不改契约与设计文档；遇到与设计/契约冲突就停下，写进"未决问题"并在报告里说明。依赖已在 core/pyproject.toml 预置，缺依赖不要自行添加，先在报告里说明。
```

### W1-2 · 泳道 B（TASK-002 → 003 → 004 解析线）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 B：解析线（Python → C → C++）】。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-b
启动会话时应把工作目录设为该路径。若当前工作目录不是它，先停下来提醒我，不要改任何文件。

【开工】
1. 读：AGENTS.md、docs/plan/orchestration.md 的"泳道模式"节、docs/tasks/README.md。
2. 按顺序完成 3 张任务卡（做完一张立刻做下一张，不要等我确认）：
   docs/tasks/TASK-002-Parser基座与Python.md
   docs/tasks/TASK-003-C抽取器.md
   docs/tasks/TASK-004-Cpp抽取器.md
3. 工艺（每张卡重复一遍）：
   a) 开分支：第一张卡 `git switch -c feature/task-002_xwzMMDD main`；
      后续卡从上一张卡的分支创建，例如 `git switch -c feature/task-003_xwzMMDD feature/task-002_xwzMMDD`。
   b) 只修改该卡"交付物（文件所有权）"清单里的文件；其他文件一律不动
      （特别是 docs/design/**、docs/contracts/**、../source/**、registry.py / base.py / __init__.py）。
   c) 跑通该卡"验收标准"里的全部命令，外加基线三条：
      uv run ruff check .
      uv run python scripts/check_dependency_direction.py
      uv run pytest
   d) 回填该卡"执行记录"节，并把 docs/tasks/README.md 里对应那行状态改成 review。
   e) git add -A && git commit（提交信息以 "task-002: " / "task-003: " / "task-004: " 开头）。
4. 全部做完后输出报告（每张卡一段）。

【报告格式】（每张卡一段）
- 卡号 / 分支：
- 验收命令与结果：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切到 main、不 force push；不改契约与设计文档；遇到与设计/契约冲突就停下，写进"未决问题"并在报告里说明。依赖已在 core/pyproject.toml 预置，缺依赖不要自行添加，先在报告里说明。
```

### W1-3 · 泳道 C（TASK-005 → 009 文档与向量线）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 C：Markdown 文档线 + 向量存储线】。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-c
启动会话时应把工作目录设为该路径。若当前工作目录不是它，先停下来提醒我，不要改任何文件。

【开工】
1. 读：AGENTS.md、docs/plan/orchestration.md 的"泳道模式"节、docs/tasks/README.md。
2. 按顺序完成 2 张任务卡（做完一张立刻做下一张，不要等我确认）：
   docs/tasks/TASK-005-Markdown-SpecBlock.md
   docs/tasks/TASK-009-向量存储.md
3. 工艺（每张卡重复一遍）：
   a) 开分支：第一张卡 `git switch -c feature/task-005_xwzMMDD main`；
      第二张卡从上一张卡的分支创建：`git switch -c feature/task-009_xwzMMDD feature/task-005_xwzMMDD`。
   b) 只修改该卡"交付物（文件所有权）"清单里的文件；其他文件一律不动
      （特别是 docs/design/**、docs/contracts/**、../source/**、别人模块与 registry.py / base.py / __init__.py）。
   c) 跑通该卡"验收标准"里的全部命令，外加基线三条：
      uv run ruff check .
      uv run python scripts/check_dependency_direction.py
      uv run pytest
   d) 回填该卡"执行记录"节，并把 docs/tasks/README.md 里对应那行状态改成 review。
   e) git add -A && git commit（提交信息以 "task-005: " / "task-009: " 开头）。
4. 全部做完后输出报告（每张卡一段）。

【报告格式】（每张卡一段）
- 卡号 / 分支：
- 验收命令与结果：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切到 main、不 force push；不改契约与设计文档；遇到与设计/契约冲突就停下，写进"未决问题"并在报告里说明。依赖已在 core/pyproject.toml 预置，缺依赖不要自行添加，先在报告里说明。
```

### W1-4 · 泳道 D（TASK-008 Embedding 双实现）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 D：Embedding Provider 双实现】。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-d
启动会话时应把工作目录设为该路径。若当前工作目录不是它，先停下来提醒我，不要改任何文件。

【开工】
1. 读：AGENTS.md、docs/plan/orchestration.md 的"泳道模式"节、docs/tasks/README.md。
2. 完成 1 张任务卡：docs/tasks/TASK-008-Embedding双实现.md（严格按卡内"输入文档 → 冻结接口 → 交付物 → 验收标准"执行）。
3. 工艺：
   a) git switch -c feature/task-008_xwzMMDD main      ← 把 MMDD 换成今天的月日
   b) 只修改任务卡"交付物（文件所有权）"清单里的文件；其他文件一律不动
      （特别是 docs/design/**、docs/contracts/**、../source/**）。
   c) 跑通任务卡"验收标准"里的全部命令（CI 测试不得依赖网络），外加基线三条：
      uv run ruff check .
      uv run python scripts/check_dependency_direction.py
      uv run pytest
   d) 回填任务卡"执行记录"节，并把 docs/tasks/README.md 里 TASK-008 那行状态改成 review。
   e) git add -A && git commit（提交信息以 "task-008: " 开头）。
4. 做完直接输出报告。

【报告格式】
- 卡号 / 分支：
- 验收命令与结果：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切到 main、不 force push；不改契约与设计文档；遇到与设计/契约冲突就停下，写进"未决问题"并在报告里说明。
【联网提示】需要下载 ONNX 模型或新依赖时，先在报告里说明你下载了什么、放在哪、耗时多少；不要在仓库里提交模型文件。
```

### W2-1 · 泳道 A 继续（TASK-006 → 007）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 A 续：Chunk 模型与索引流水线】。
上一波（TASK-001）已由总览 AI 合并进本地 main，本波从本地 main 开始。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-a
（会话工作目录设为此路径；若 CWD 不是它，先停下提醒我，不要改任何文件。）

【开工前核验】本地 main 已含 W1 全部产出（TASK-001/002-004/005/008/009）。执行：
  git log --oneline -1 main     # 应看到 “Close W1 lanes: record drift rulings...”
  ls core/zace_core/storage core/zace_core/embedding core/zace_core/vectors core/zace_core/parsing
两个都不对就先停下报告，不要自行 git pull（远端比本地旧）。
开分支：git switch -c feature/task-006_xwzMMDD main

【开工】
1. 读：AGENTS.md、docs/plan/orchestration.md 的“泳道模式”一节、docs/tasks/README.md、
   以及 docs/plan/contracts.md §3.2（R1-R10 实现口径——本波两张卡都直接受影响）。
2. 按顺序完成 2 张任务卡（做完一张立刻做下一张）：
   docs/tasks/TASK-006-Chunk模型与解析.md
   docs/tasks/TASK-007-索引流水线.md
   TASK-007 需要 embedding/向量真实实现，此时已在 main 上，直接使用，不要用桩。
3. 工艺（每张卡重复一遍）：
   a) 开分支：第一张 `git switch -c feature/task-006_xwzMMDD main`；
      第二张从第一张创建：`git switch -c feature/task-007_xwzMMDD feature/task-006_xwzMMDD`。
   b) 只修改该卡“交付物（文件所有权）”清单里的文件；其他文件一律不动。
   c) 跑通该卡“验收标准”的全部命令 + 基线三条：
      uv run ruff check . / uv run python scripts/check_dependency_direction.py / uv run pytest
   d) 回填该卡“执行记录”节，并把 docs/tasks/README.md 对应行状态改为 review。
   e) git add -A && git commit（“task-006: ” / “task-007: ” 前缀）。
4. 输出报告（每张卡一段）。

【报告格式】（每张卡一段）
- 卡号 / 分支：
- 验收命令与结果：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切 main、不 force push；不改契约与设计文档；冲突先停下写进“未决问题”。
```

### W2-2 · 泳道 E（TASK-010 → 011 → 012 检索线）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 E：检索线（通道融合 → 图扩展/rerank → ContextPack）】。
W1 的存储（TASK-001）、向量（TASK-009）、embedding（TASK-008）已由总览 AI 合并进本地 main。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-e
（会话工作目录设为此路径；若 CWD 不是它，先停下提醒我，不要改任何文件。）

【开工前核验】本地 main 已含 W1 全部产出。执行：
  git log --oneline -1 main     # 应看到 “Close W1 lanes: record drift rulings...”
  ls core/zace_core/storage core/zace_core/embedding core/zace_core/vectors
两个都不对就先停下报告，不要自行 git pull（远端比本地旧）。
开分支：git switch -c feature/task-010_xwzMMDD main

【开工】
1. 读：AGENTS.md、docs/plan/orchestration.md 的“泳道模式”一节、docs/tasks/README.md、
   以及 docs/plan/contracts.md §3.2（R1-R10 实现口径，尤其 R2 的 embed_query）。
2. 按顺序完成 3 张任务卡（做完一张立刻做下一张）：
   docs/tasks/TASK-010-检索通道与RRF.md
   docs/tasks/TASK-011-图扩展与Rerank.md
   docs/tasks/TASK-012-ContextPack组装.md
3. 工艺（每张卡重复一遍）：
   a) 开分支：第一张 `git switch -c feature/task-010_xwzMMDD main`；后续卡从上一张卡的分支创建。
   b) 只修改该卡“交付物（文件所有权）”清单里的文件（注意：011 不得改 retrieval/__init__.py；012 可在 core/pyproject.toml 的 dev extra 加 jsonschema）。
   c) 跑通该卡“验收标准”的全部命令 + 基线三条：
      uv run ruff check . / uv run python scripts/check_dependency_direction.py / uv run pytest
   d) 回填该卡“执行记录”节，并把 docs/tasks/README.md 对应行状态改为 review。
   e) git add -A && git commit（“task-010: ” / “task-011: ” / “task-012: ” 前缀）。
4. 输出报告（每张卡一段）。

【报告格式】（每张卡一段）
- 卡号 / 分支：
- 验收命令与结果：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切 main、不 force push；不改契约与设计文档；冲突先停下写进“未决问题”。
```

### W3a-1 · 泳道 B（TASK-016 BM25 多词召回修复）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 B：BM25 多词召回语义修复 + 跨模块 E2E 回归】。
背景：编排者的端到端实测发现中文自然语言查询在 BM25 通道恒零命中（FTS5 隐式 AND），
导致 answerable 恒为 False——这是一个已定位、已给出修复方向的真实缺陷。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-b
（会话工作目录设为此路径；若 CWD 不是它，先停下提醒我，不要改任何文件。）

【开工前核验】
  git log --oneline -1          # 应为 “Merge W2 lanes and add two quality-fix cards found by E2E”
  git switch -c feature/task-016_xwzMMDD main

【开工】
1. 读：AGENTS.md、docs/plan/orchestration.md 的"泳道模式"一节、docs/tasks/README.md、
   docs/tasks/TASK-016-BM25多词召回修复.md（含完整背景、修复要求 A/B/C/D 与验收标准）、
   docs/plan/contracts.md §3.3（R11-R13 裁定）。
2. 完成 TASK-016 一张卡。特别注意：
   - 卡内已给出 codegraph 的参考实现位置（source/codegraph/src/db/queries.ts:1505-1513，只读），
     修复方向（OR 连接 + 列权重）已定，不要自行发明其他方案；若你判断方案有问题，先停下写进"未决问题"。
   - 本卡**必须交付** core/tests/integration/ 的跨模块 E2E 测试（卡内 §D 列了 5 条必须断言）；
     embedding 用卡内要求的确定性假 provider（CI 不联网）。
   - 你会同步修改 core/tests/storage/ 下少量依赖旧 AND 语义的断言——这是卡内明确授权的，
     每处改动要在执行记录说明；不得弱化"中文不分词不命中"等关键覆盖。
3. 工艺：
   a) 只修改卡内"交付物所有权"清单里的文件；其他文件一律不动（尤其 core/zace_core/contextpack/，那是 TASK-017 的范围）。
   b) 跑通卡内"验收标准"全部命令 + 基线三条：
      uv run ruff check . / uv run python scripts/check_dependency_direction.py / uv run pytest
   c) 回填"执行记录"（必须含修复前后对比数据：BM25 命中数 0→N、answerable False→True）。
   d) 任务板 docs/tasks/README.md 里 TASK-016 那行状态改为 review。
   e) git add -A && git commit（提交信息以 "task-016: " 开头）。
4. 输出报告。

【报告格式】
- 卡号 / 分支：
- 验收命令与结果：
- 修复前后对比（BM25 命中数 / answerable / confidence）：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切 main、不 force push；不改契约与设计文档；冲突先停下写进"未决问题"。
```

### W3a-2 · 泳道 C（TASK-017 证据块行序修复）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 C：ContextPack 证据块行号单调性修复】。
背景：编排者的端到端实测发现渲染出的证据块行号回跳（9→6→14→1），会误导 agent 对齐编辑。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-c
（会话工作目录设为此路径；若 CWD 不是它，先停下提醒我，不要改任何文件。）

【开工前核验】
  git log --oneline -1          # 应为 “Merge W2 lanes and add two quality-fix cards found by E2E”
  git switch -c feature/task-017_xwzMMDD main

【开工】
1. 读：AGENTS.md、docs/plan/orchestration.md 的"泳道模式"一节、docs/tasks/README.md、
   docs/tasks/TASK-017-证据块行序修复.md（含根因分析、修复要求、DoD）、
   docs/plan/contracts.md §3.3（R12）。
2. 完成 TASK-017 一张卡。要点：
   - 只改 合并区间的存储与渲染顺序 与 elidedLines 语义；阈值/配额/保底/E 编号顺序等行为保持不变。
   - 卡内"DoD"第一条是修一处 flaky 性能断言（test_assembly.py 的 elapsed_ms < 50），
     并发跑测试时会误报——放宽阈值或标 slow，不要删断言。
3. 工艺：
   a) 只修改卡内"交付物所有权"清单里的文件（core/zace_core/contextpack/、core/tests/contextpack/）；
      其他一律不动（尤其 core/zace_core/storage/、core/zace_core/retrieval/，那是 TASK-016 的范围）。
   b) 跑通卡内"验收标准"全部命令 + 基线三条：
      uv run ruff check . / uv run python scripts/check_dependency_direction.py / uv run pytest
   c) 回填"执行记录"，贴一段修复后的渲染样例（证明行号单调、省略标注正确）。
   d) 任务板对应行状态改 review。
   e) git add -A && git commit（"task-017: " 前缀）。
4. 输出报告（格式同上：卡号 / 分支 / 验收命令与结果 / 契约影响 / 与设计偏差 / 未决问题）。

【纪律】不 push、不切 main、不 force push；不改契约与设计文档；冲突先停下写进"未决问题"。
```

### W3a-3 · 泳道 F（TASK-013 CLI + eval runner）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 F：core CLI + engine 装配 + golden runner】。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-f
（会话工作目录设为此路径；若 CWD 不是它，先停下提醒我，不要改任何文件。）

【开工前核验】
  git log --oneline -1          # 应为 “Merge W2 lanes and add two quality-fix cards found by E2E”
  ls core/zace_core/pipeline core/zace_core/retrieval core/zace_core/contextpack
  git switch -c feature/task-013_xwzMMDD main

【开工】
1. 读：AGENTS.md、docs/plan/orchestration.md 的"泳道模式"一节、docs/tasks/README.md、
   docs/tasks/TASK-013-CLI与Eval.md、benches/README.md、docs/plan/contracts.md §3.2/§3.3。
2. 完成 TASK-013 一张卡（**本波只做这一张**，不要提前做 014/015——它们必须等 BM25/行序修复合并后才跑，
   否则黄金集指标会系统性失真）。
3. 已知事项（避免踩坑）：
   - 本波并行泳道 B 正在修 BM25（core/zace_core/storage/store.py + retrieval/bm25.py），
     泳道 C 正在修 contextpack 行序。**你的 eval runner 要按接口调用，不要依赖这两处的当前行为**；
     若你发现测试受它们影响，先记录不要修改它们的文件。
   - `core/tests/contextpack/test_assembly.py` 有一处并发下会误报的 50ms 性能断言（泳道 C 正在修），
     若你跑全仓测试时它偶发失败，不必处理。
4. 工艺：
   a) 只修改卡内"交付物所有权"清单里的文件（core/zace_core/cli/、core/zace_core/engine.py、benches/run.py、core/tests/cli/）；
      `core/pyproject.toml` 的 console script 入口已预置（zace-core = "zace_core.cli:main"），无需改。
   b) 跑通卡内"验收标准"全部命令（含新增的跨模块 E2E 断言）+ 基线三条。
   c) 回填"执行记录"：贴对 zace 仓库自身 ingest 的真实耗时/chunks 数与 2 条中文查询输出摘要。
   d) 任务板对应行状态改 review。
   e) git add -A && git commit（"task-013: " 前缀）。
5. 输出报告（格式：卡号 / 分支 / 验收命令与结果 / 契约影响 / 与设计偏差 / 未决问题）。

【纪律】不 push、不切 main、不 force push；不改契约与设计文档；冲突先停下写进"未决问题"。
```

### W3c-1 · 泳道 A（TASK-018 兜底行号修复，阻断项）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 A：兜底切分行号修复 + chunk id 唯一性 + 单文件失败隔离】。
背景：TASK-013 的自举实测发现，在真实 zace 仓库上执行 `zace-core ingest --repo .` 会直接崩溃
（sqlite3.IntegrityError: UNIQUE constraint failed: chunks.id）。根因已由编排者定位并写在任务卡里。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-a
（会话工作目录设为此路径；若 CWD 不是它，先停下提醒我，不要改任何文件。）

【开工前核验】
  git log --oneline -1          # 应为 “Merge branch 'feature/task-013_xwz0910'” 之后的最新 main
  git switch -c feature/task-018_xwzMMDD main

【开工】
1. 读：AGENTS.md、docs/plan/orchestration.md 的"泳道模式"一节、docs/tasks/README.md、
   docs/tasks/TASK-018-兜底行号与ID唯一性修复.md（含完整根因分析、修复要求 A/B/C、DoD）、
   docs/plan/contracts.md §3.4（R14）。
2. 完成 TASK-018 一张卡。要点：
   - §A 根因：parsing/fallback.py 的 _split 在分隔符分支递归时丢失基准偏移（顶层 offset=0 掩盖了它）。
     卡内给了最小复现，先跑一遍确认，再修。
   - §B 防御：chunking/splitter.py 出口检测重复 id → 抛带明细的 ValueError，**禁止静默去重/丢弃**。
   - §C 隔离：pipeline/indexer.py 让单文件失败不中断整次 ingest，如实写进 report.errors。
   - **核心验收**：`uv run zace-core ingest --repo . --data /tmp/zace-u1-check` 在 zace 仓库本体
     （不剔除 uv.lock/.git）上跑通，把输出贴进执行记录。这是阻断解除的唯一凭证。
3. 工艺：
   a) 只修改卡内"交付物所有权"清单里的文件；其他一律不动（尤其 core/zace_core/contextpack/，那是 TASK-019 的范围）。
   b) 跑通卡内"验收标准"全部命令 + 基线三条：
      uv run ruff check . / uv run python scripts/check_dependency_direction.py / uv run pytest
   c) 回填"执行记录"（含 ingest 成功输出与最小复现回归测试）。
   d) 任务板 docs/tasks/README.md 里 TASK-018 那行状态改为 review。
   e) git add -A && git commit（提交信息以 "task-018: " 开头）。
4. 输出报告。

【报告格式】
- 卡号 / 分支：
- 验收命令与结果（含 zace 仓库本体 ingest 输出）：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切 main、不 force push；不改契约与设计文档；冲突先停下写进"未决问题"。
```

### W3c-2 · 泳道 C（TASK-019 spec 保底重复装填）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 C：spec 保底块重复装填修复 + 预算不变量测试】。
背景：TASK-013 在真实仓库自举时发现同一 spec 块被装填两次（占两个 E 编号、吃掉约 1.4K token）。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-c
（会话工作目录设为此路径；若 CWD 不是它，先停下提醒我，不要改任何文件。）

【开工前核验】
  git log --oneline -1          # 应为最新 main（含 TASK-016/017/013 的合并）
  git switch -c feature/task-019_xwzMMDD main

【开工】
1. 读：AGENTS.md、docs/plan/orchestration.md 的"泳道模式"一节、docs/tasks/README.md、
   docs/tasks/TASK-019-spec保底重复装填修复.md（含根因代码定位、修复要求、DoD）、
   docs/plan/contracts.md §3.4（R15）。
2. 完成 TASK-019 一张卡。要点：
   - 根因：assembly.py 里 `reserved not in slots` 用 _Slot 对象身份比较（无 __eq__）恒为 True；
     贪心循环会先装填同一候选，随后保底分支又装一次。
   - 修复方向：按 chunk_id 去重；保底语义（预留预算 + 至少 1-2 块 spec）与 E 编号=装填顺序均不得变。
   - 卡内 DoD 有 4 条测试要求（去重/预算不变量/保底仍在/回归），其中"保底仍在"是防你修过头。
3. 工艺：
   a) 只修改卡内"交付物所有权"清单里的文件（core/zace_core/contextpack/、core/tests/contextpack/）；
      其他一律不动（尤其 parsing/、chunking/、pipeline/，那是 TASK-018 的范围）。
   b) 跑通卡内"验收标准"全部命令 + 基线三条：
      uv run ruff check . / uv run python scripts/check_dependency_direction.py / uv run pytest
   c) 回填"执行记录"：贴该查询修复前后的 E 编号清单对比。
   d) 任务板对应行状态改 review。
   e) git add -A && git commit（"task-019: " 前缀）。
4. 输出报告（格式：卡号 / 分支 / 验收命令与结果 / 契约影响 / 与设计偏差 / 未决问题）。

【纪律】不 push、不切 main、不 force push；不改契约与设计文档；冲突先停下写进"未决问题"。
```

### W5a · 泳道 A（Phase 2 M2a-1：service 外壳，四张卡串联）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 A：Phase 2 M2a-1 —— zace-service 骨架 + core 接入 + 查询/同步 API】。
背景：core 引擎（Phase 1）已完成并在真实仓库上验证；现在要做"服务化外壳"，让编辑器里的 MCP 客户端能连上来。
本波四张卡串联（同一泳道、有依赖），做完一张立刻做下一张，不要等我确认。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-a
（会话工作目录设为此路径；若 CWD 不是它，先停下提醒我，不要改任何文件。）

【开工前核验】
  git log --oneline -1     # 应为 "Add M2a service cards and extend ingest contract with source provider"
  git switch -c feature/task-030_xwzMMDD main   ← MMDD 换成今天月日

【开工】按顺序完成 4 张任务卡：
  docs/tasks/TASK-030-service骨架.md
  docs/tasks/TASK-031-core接入.md
  docs/tasks/TASK-032-查询API.md
  docs/tasks/TASK-033-同步API.md
  每张卡开头都有"交付物所有权"清单，只改清单内文件。
  第二张起从上一张的分支串联：
    git switch -c feature/task-031_xwzMMDD feature/task-030_xwzMMDD   （以此类推）

【必读（每张卡开工前）】
  docs/tasks/README.md
  docs/plan/orchestration.md 的"泳道模式"一节
  docs/plan/contracts.md §3.8（R33-R37：本波四张卡的直接口径）
  docs/contracts/openapi.yaml（CF-05 是冻结合同：路径与错误信封不得改）
  各卡的"输入文档"节（只读所需章节）

【本波特别提醒】
1. TASK-031 有一处 **core 侧改动**：`core/zace_core/engine.py` 的 `Engine.ingest` 要支持
   `source=...` 参数（契约 CF-07 已由编排者在 main 上更新好，你只实现 core 侧那一处）。
   卡内 §A 写了"为什么"——**不传 source 会在配置指纹失效时静默清空索引**，
   必须写一条回归测试同时断言"错误行为（清空）"与"正确行为（重建）"。
2. TASK-030 的 CF-05 路径集合一致性测试是本波的地基（路径不得增删改名）。
3. TASK-032 的 `meta` 字段集是给下一波 Rust client（TASK-040）的输入契约，写出后不要随意改。
4. TASK-032 的 ask 端点在 Phase 2 一定走降级包（LLM 属 Phase 3）——**不得 500**。
5. service 是薄壳（D-34）：不要往 service 里塞检索/组装逻辑，一律调 core。
6. 不要在 service 引入新的第三方依赖；缺依赖先在报告里说明。
7. 不要基于测试集调检索质量参数（R29/R30 冻结中）。

【工艺】（每张卡重复）
  a) 只修改该卡"交付物所有权"清单里的文件；
  b) 跑通该卡"验收标准"全部命令 + 基线三条：
     uv run ruff check . / uv run python scripts/check_dependency_direction.py / uv run pytest
     （注意：本波会新增 service/tests/，跑全仓 pytest 也要绿）
  c) 回填该卡"执行记录"（含卡内要求的实测输出）；
  d) 任务板 docs/tasks/README.md 对应行状态改为 review；
  e) git add -A && git commit（"task-030: " / "task-031: " / …前缀）。

【报告格式】（每张卡一段）
- 卡号 / 分支：
- 验收命令与结果：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切 main、不 force push；不改 docs/contracts/**、docs/design/**、
core/zace_core/{types,interfaces,hashing}.py；遇到契约/设计冲突先停下写进"未决问题"。
```

### W5b · 泳道 A（Phase 2 M2a-2：本地模式 + MCP 端点，**demo 收口波**）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 A：Phase 2 M2a-2 —— 错误映射 → 本地单用户模式 → service 侧 MCP 端点】。
背景：service 的骨架/查询/同步 API 已完成并合并。本波三张卡做完，用户就能在编辑器里用真实问题验证系统（M2 验收）。
三张卡串联（同泳道、有依赖），做完一张立刻做下一张，不要等我确认。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-a
（会话工作目录设为此路径；若 CWD 不是它，先停下提醒我，不要改任何文件。）

【开工前核验】
  git log --oneline -1     # 应为 "Merge branch 'feature/task-033_xwz0910'"
  git switch -c feature/task-035_xwzMMDD main   ← MMDD 换成今天月日

【开工】按顺序完成 3 张任务卡：
  docs/tasks/TASK-035-provider健康与错误映射.md
  docs/tasks/TASK-034-本地单用户模式.md
  docs/tasks/TASK-040-service侧MCP端点.md
  第二张起从上一张的分支串联（git switch -c feature/task-034_xwzMMDD feature/task-035_xwzMMDD，以此类推）。

【必读】
  docs/tasks/README.md、docs/plan/orchestration.md 的"泳道模式"一节、
  docs/contracts/mcp-tools.json（CF-06：工具 schema 是冻结合同）、
  docs/plan/contracts.md §3.8（R33-R38；**R38 是本波 MCP 形态的裁定依据**，务必读）、
  各卡"输入文档"节。

【本波特别提醒（每一条都是踩过的坑或硬纪律）】
1. TASK-040 的卡里有"已验证的实现要点"5 条——那是我实测 mcp==2.2.0 得到的结论，
   **照做，别重新摸索**：导入路径是 mcp.server.mcpserver.MCPServer（不是 fastmcp，会直接 ImportError）；
   挂载必须传 streamable_http_path="/"（否则路径叠加成 /mcp/mcp 全 404）；session manager 的 lifespan 必须跑。
2. TASK-040 的 Origin 防护**默认已生效**（恶意 Origin 返回 403）——**不要为了"跑通"把它关掉**。
3. 本波会新增第三方依赖 mcp>=2.2（只加在 service/pyproject.toml）。这是本波唯一允许的新依赖。
4. TASK-034 的进度语义要诚实：索引期间 processed_files 允许为 0，**不许伪造百分比**（D-30）。
5. TASK-034 的懒重扫失败**不得**让检索失败——记日志 + 如实报告，照常返回既有索引结果。
6. TASK-040 必须复用 TASK-032 的 packmeta 与 render_markdown，不要另写一份 meta 或渲染。
7. 不要基于当前 60 条测试集调检索质量参数（R29/R30 冻结中）。
8. core 引擎调用是阻塞的——MCP 工具必须写成 async + 线程池执行，不要在事件循环里直接跑。

【工艺】（每张卡重复）
  a) 只修改该卡"交付物所有权"清单里的文件；
  b) 跑通该卡"验收标准"全部命令 + 基线三条：
     uv run ruff check . / uv run python scripts/check_dependency_direction.py / uv run pytest
  c) 回填该卡"执行记录"（含卡内要求的实测输出）；
  d) 任务板对应行状态改为 review；
  e) git add -A && git commit（"task-035: " / "task-034: " / "task-040: " 前缀）。

【报告格式】（每张卡一段）
- 卡号 / 分支：
- 验收命令与结果：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切 main、不 force push；不改 docs/contracts/**、docs/design/**、
core/zace_core/{types,interfaces,hashing}.py；冲突先停下写进"未决问题"。
```

### W5c-1 · 泳道 A（续做：TASK-034 → 040 → 045，**demo 收口**）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 A 续做：完成本地单用户模式 → service 侧 MCP 端点 → 验收手册】。
上一轮已经写完 TASK-034 的代码（未提交），本会话从当前工作区接着做完。做完就能在编辑器里用真实问题验证系统。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-a
（会话工作目录设为此路径；若 CWD 不是它，先停下提醒我，不要改任何文件。）

【开工前先看清现状】
  git log --oneline -1            # 应为 "task-035: map engine/dependency errors to 503/507 ..."
  git branch --show-current       # 应为 feature/task-034_xwz0910
  git status --short              # 会看到 TASK-034 的未提交改动（这是上一轮的成果，别丢）
  uv run pytest 2>&1 | tail -3    # 应为 629 passed, 2 skipped
先读 docs/tasks/TASK-034-本地单用户模式.md 的"验收标准"，逐条对照现状，把没做的补齐。

【开工顺序】三张卡串联：
  1) TASK-034（续做）：docs/tasks/TASK-034-本地单用户模式.md
     - 剩余：卡内标"必做"的真实仓库自举 + 执行记录回填 + 任务板改 review + 提交
     - 已知偏差要登记：service/tests/test_skeleton.py 的 CF-05 路径白名单（新增 attach/rescan 路径）；
       service/tests/test_error_mapping.py 的改动也要在执行记录里说明原因
     - 提交一个 task-034 的 commit（把上一轮的改动一并提交）
  2) TASK-040（新）：docs/tasks/TASK-040-service侧MCP端点.md
  3) TASK-045（新）：docs/tasks/TASK-045-M2a验收手册.md
  第二、三张卡从上一张的分支串联。

【本波特别提醒】
1. TASK-040 卡里有"已验证的实现要点"5 条——那是我实测 mcp==2.2.0 得到的结论，**照做**：
   导入是 mcp.server.mcpserver.MCPServer（fastmcp 在 2.x 已移除，导入即 ImportError）；
   挂载必须传 streamable_http_path="/"（否则路径叠加成 /mcp/mcp，全 404）；
   session manager 的 lifespan 必须跑（否则 initialize 建不了会话）。
2. TASK-040 的 Origin 防护默认已生效（恶意 Origin 返 403）——**不要为了"跑通"关掉它**。
3. 本波唯一允许的新依赖是 service/pyproject.toml 里的 mcp>=2.2。
4. MCP 工具必须 async + 线程池执行（core 调用是阻塞的），不要在事件循环里直接跑。
5. TASK-040 必须复用 TASK-032 的 packmeta 与 render_markdown，不要另写一份。
6. 不要基于当前 60 条测试集调检索质量参数（R29/R30 冻结）。
7. TASK-045 的手册里每一条命令与输出都必须是**你真跑过的**，不要凭想象写。

【工艺】（每张卡重复）
  a) 只修改该卡"交付物所有权"清单里的文件；
  b) 跑通该卡"验收标准"全部命令 + 基线三条：
     uv run ruff check . / uv run python scripts/check_dependency_direction.py / uv run pytest
  c) 回填该卡"执行记录"；任务板对应行状态改为 review；
  d) git add -A && git commit（"task-034: " / "task-040: " / "task-045: " 前缀）。

【报告格式】（每张卡一段）
- 卡号 / 分支：
- 验收命令与结果：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切 main、不 force push；不改 docs/contracts/**、docs/design/**、
core/zace_core/{types,interfaces,hashing}.py；冲突先停下写进"未决问题"。
```

### W5c-2 · 泳道 B（TASK-015A：embedding 模型选型，长任务）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 B：embedding bake-off（模型选型）】。
这是长任务：模型下载 + 多个模型各自独立建索引 + 评测，预计数小时，**不要为了快而抽掉候选模型或缩小靶场**，
但要把每一步的中间结果落盘，便于断点续跑。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-b
（会话工作目录设为此路径；若 CWD 不是它，先停下提醒我，不要改任何文件。）

【开工前核验】
  git log --oneline -1     # 应为 "Merge branch 'feature/task-035_xwz0910'"
  git switch -c feature/task-015a_xwzMMDD main   ← MMDD 换成今天月日

【开工】完成 docs/tasks/TASK-015-Bakeoff与校准.md（**只做 A 部分**）。

【本波最重要的纪律】
1. 这是"**选型**"卡，不是"调优"卡：**不得**修改 rerank 权重、FTS 列权重、前缀匹配开关、
   RecallLimits、docs_ratio、CONSENSUS_SCORE_RATIO 中的任何一个（R30 冻结；卡内也写明了）。
   唯一变量是 embedding provider。报告里要贴 git diff 证明这一点。
2. TASK-023 的真实调用数据还没有，所以**不许**基于当前 60 条 smoke 集去调任何参数（R29/R30）。
   本卡允许用 smoke 集比较"模型之间"的差异——那是模型选型，不是参数调优。
3. 每个模型的索引要用**独立数据根**，中间结果落 JSON，支持断点续跑（重跑一次几小时不可接受）。
4. 时间与体积同样重要：报告必须给出索引耗时与向量库体积的真实数字（VPS 选型与分发体积要用）。
5. 首次下载模型会联网（HuggingFace）。记录：下载了什么、多大、放在哪、耗时多少；
   **不要**把模型文件提交进仓库。
6. 若某模型在本机跑不动（体积/内存/耗时不可接受），如实记录并继续下一个，不要卡死。

【可复用的现成资源（不要重建）】
- golden 用例：benches/golden/{zace,aibox-super-sdk,linux-mtk-mw-cameraservice}/*.jsonl（60 条）
- 评测命令：uv run zace-core eval --repo <路径> --data <数据根> --golden <用例目录> --report <输出.md>
- 已有索引（默认 e5-small）：/tmp/zace-aibox、/tmp/zace-verify-main、/tmp/zace-cam
  （这些是"基线模型"的现成结果，可直接读它们的 eval 报告，但**换模型的索引必须重建**）
- 模型缓存目录：/tmp/zace-embedding-cache

【工艺】
  a) 只修改卡内"交付物所有权"清单里的文件；
  b) 跑通卡内"验收标准"全部命令 + 基线三条：
     uv run ruff check . / uv run python scripts/check_dependency_direction.py / uv run pytest
  c) 回填"执行记录"（含模型对比表）；任务板对应行状态改为 review；
  d) git add -A && git commit（"task-015a: " 前缀）。

【报告格式】
- 卡号 / 分支：
- 候选模型与数据根：
- 对比表（每个模型：recall@5/@10、MRR、索引耗时、查询延迟、向量库体积）：
- 推荐默认模型与理由（含不选更大模型的原因）：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切 main、不 force push；不改 docs/contracts/**、docs/design/**、
core/zace_core/{types,interfaces,hashing}.py；不改任何排序/装填参数；冲突先停下写进"未决问题"。
```

### W5c-3 · 泳道 C（TASK-036 → 037：规模自举与索引范围，长任务）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 C：多仓库规模自举与健壮性 → 索引范围策略】。
这是长任务：要在本机多个真实仓库（最大 4400+ 文件 / 880 MB / 含 308MB 二进制）上跑全量索引并修 bug。
上一次同类自举发现了阻断 M1 的崩溃（chunk id 冲突），这次靶场规模大一个数量级，请认真对待。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-c
（会话工作目录设为此路径；若 CWD 不是它，先停下提醒我，不要改任何文件。）

【开工前核验】
  git log --oneline -1     # 应为 "Merge branch 'feature/task-035_xwz0910'"
  git switch -c feature/task-036_xwzMMDD main   ← MMDD 换成今天月日

【开工】按顺序完成 2 张任务卡（做完一张立刻做下一张）：
  docs/tasks/TASK-036-多仓库规模自举与健壮性.md
  docs/tasks/TASK-037-索引范围策略.md（从 task-036 分支串联）

【本波最重要的纪律】
1. **时间预算**：单仓库 ingest 用 timeout 限制 90 分钟，超时就记"超时 + 已处理进度"继续下一个。
   按卡内表格从小到大跑。**先在全部靶场跑完 §A 拿到事实，再回头修 §B 的 bug。**
2. 所有靶场仓库都是**只读**参考：只读源码，不改它们、不在它们里面建文件（数据根放 /tmp）。
3. TASK-036 只做"测量 + 修崩溃"：**不要顺手改忽略规则/大小阈值**（那是 TASK-037），
   发现这类问题就在报告里给证据 + 交接。
4. TASK-037 会改索引范围（以前被索引的文件以后不索引）——**这必须如实前后对照报告**，
   并且要抽查检索是否变差（卡内 §D）；不许为了让 eval 数字好看而放宽规则（R30 冻结）。
5. 报告要贴**完整输出**（耗时、chunks、errors、skipped），不要只写"通过"。
6. 若发现"该不该索引"这类需要产品判断的问题，写进报告让编排者裁定，不要自己拍。

【可复用资源】
- 已索引：/tmp/zace-aibox、/tmp/zace-verify-main、/tmp/zace-cam
- golden 用例：benches/golden/{zace,aibox-super-sdk,linux-mtk-mw-cameraservice}（cameraservice 16 条用于 §D 回归）
- ingest 命令：uv run zace-core ingest --repo <路径> --data /tmp/zace-scale-<n>
- 检索命令：uv run zace-core search "<查询>" --repo <路径> --data <数据根>

【工艺】（每张卡重复）
  a) 只修改该卡"交付物所有权"清单里的文件；
  b) 跑通该卡"验收标准"全部命令 + 基线三条：
     uv run ruff check . / uv run python scripts/check_dependency_direction.py / uv run pytest
  c) 回填该卡"执行记录"；任务板对应行状态改为 review；
  d) git add -A && git commit（"task-036: " / "task-037: " 前缀）。

【报告格式】（每张卡一段）
- 卡号 / 分支：
- 六靶场汇总表（文件数 / chunks / 耗时 / errors / skipped）：
- 修复清单（每条：现象 / 复现 / 根因 / 修复 / 回归测试）：
- 契约影响（无 / 说明）：
- 与设计偏差（无 / 说明）：
- 未决问题（无 / 说明）：

【纪律】不 push、不切 main、不 force push；不改 docs/contracts/**、docs/design/**、
core/zace_core/{types,interfaces,hashing}.py；冲突先停下写进"未决问题"。
```

## 3. 收尾

- 每个泳道做完后，把它的完成报告整段贴回总览会话：我会核对验收输出、跑全仓集成检查、合并到 main、更新任务板，并给你下一波提示词。
- Phase 1 已完成 M1 验收（基线报告 benches/results/phase1-baseline.md）；Phase 2 的卡片已按 docs/plan/phase2-roadmap.md 逐波开出。
- 工作区清理（所有波次结束后）：`bash scripts/lane-worktrees.sh remove`。
