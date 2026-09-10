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
| W1 | 4 | A `zace-lane-a` | TASK-001 | 已完成并合并 |
| W1 | | B `zace-lane-b` | TASK-002 → 003 → 004 | 已完成并合并 |
| W1 | | C `zace-lane-c` | TASK-005 → 009 | 已完成并合并 |
| W1 | | D `zace-lane-d` | TASK-008 | 已完成并合并 |
| W2 | 2 | A `zace-lane-a` | TASK-006 → 007 | **当前波次** |
| W2 | | E `zace-lane-e` | TASK-010 → 011 → 012 | **当前波次** |
| W3 | 1 | F `zace-lane-f` | TASK-013 → 014 → 015 | 等 W2 合并 |

并行安全的前提：各泳道的文件所有权互不重叠（见各任务卡"交付物"节），且都只在自己工作区里提交。

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

### W3-1 · 泳道 F（TASK-013 → 014 → 015 出口与评测）

```text
你是 zace 项目的实施工程师，本会话负责【泳道 F：CLI/eval → golden 集 → bake-off 校准】。
W2 的索引流水线（TASK-007）与检索组装（TASK-012）已由总览 AI 合并进 main。

【工作区】/home/xuwenzheng/2_github/AI/ACE/zace-lane-f
先执行 `git switch -c feature/task-013_xwzMMDD main` 确认能拿到最新主干；若目录或主干不对，先停下提醒我。

【开工】
1. 读：AGENTS.md、docs/plan/orchestration.md 的"泳道模式"节、docs/tasks/README.md、benches/README.md。
2. 按顺序完成 3 张任务卡（做完一张立刻做下一张）：
   docs/tasks/TASK-013-CLI与Eval.md
   docs/tasks/TASK-014-Golden集与基线.md
   docs/tasks/TASK-015-Bakeoff与校准.md
3. 工艺（每张卡重复一遍）：
   a) 开分支：第一张 `git switch -c feature/task-013_xwzMMDD main`；后续卡从上一张卡的分支创建。
   b) 只修改该卡"交付物（文件所有权）"清单里的文件；其他文件一律不动。
   c) 跑通该卡"验收标准"的全部命令 + 基线三条：uv run ruff check . / uv run python scripts/check_dependency_direction.py / uv run pytest。
   d) 回填该卡"执行记录"节；任务板对应行状态改 review。
   e) git add -A && git commit（"task-013: " / "task-014: " / "task-015: " 前缀）。
4. 输出报告（每张卡一段）：卡号 / 分支 / 验收命令与结果 / 契约影响 / 与设计偏差 / 未决问题。

【需要外部仓库时】TASK-014 需要 2-3 个真实仓库做 golden 集（建议 Python/C/C++ 各一个）。若本机没有，先报告缺什么、你打算 clone 哪些（列 URL 与 commit），等我确认后再继续；仓库放在 /tmp 之外会被清理的目录，不要 vendor 进仓库。
【联网提示】TASK-015 需要下载候选 embedding 模型；先在报告里说明下载清单与耗时。
【纪律】不 push、不切 main、不 force push；不改契约与设计文档；冲突先停下写进"未决问题"。
```

## 3. 收尾

- 每个泳道做完后，把它的完成报告整段贴回总览会话：我会核对验收输出、跑全仓集成检查、合并到 main、更新任务板，并给你下一波提示词。
- 全部 Phase 1 完成后我会做 M1 验收（对 zace 自身仓库索引 + 中文查询冒烟 + 增量验证 + golden 基线报告），然后规划 Phase 2 的卡片。
- 工作区清理（所有波次结束后）：`bash scripts/lane-worktrees.sh remove`。
