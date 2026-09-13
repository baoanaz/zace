# 多 AI 协作规矩（工作区隔离）

> 状态：2026-09-13 编排者制定（用户拍板"强制一卡一工作区"）。
> 本文件是 `AGENTS.md` 与 `docs/plan/orchestration.md` 的**补充细则**，只讲"怎么并排干活不打架"。
> 起因：实测发生两次提交错位，导致一个会话被迫重做工作（见 `feature/task-071` 的提交信息）。

## 0. 一句话

**一个 AI 会话 = 一个独占工作区（git worktree）= 一个分支。主工作区只用于集成，不许在里面写代码。**

## 1. 为什么（根因，不是猜测）

多个会话共用同一个工作目录时，`git commit` 提交到哪个分支**取决于"谁最后切换了 HEAD"**。
实测后果：

| 事故 | 现象 |
|---|---|
| 提交错位 | 会话 A 的提交出现在会话 B 的分支上，A 的分支看起来"提交丢了" |
| 分支回退 | `main` 被别的会话 `git switch` 走，**main 的头指针跟着一起走了** |
| 被迫重做 | 会话 B 的未提交工作被 A 的 `git add -A` 卷进 A 的提交；B 只能重新实现一遍（`6049d59` 的提交信息记录了这件事） |
| 冲突解不完 | 双方都在主工作区改同一批文件（如 `docs/tasks/README.md`） |

**注意**：这不是"分支策略"问题——各自开分支早就做了。**缺的是"各自开工作区"**。

## 2. 工作区划分（硬性）

| 目录 | 用途 | 谁可以用 |
|---|---|---|
| `/home/xuwenzheng/github/ACE/zace` | **集成专用**：合并、评审、推送、跑全仓基线 | **只能编排者**（且必须 `guard` 通过） |
| `/home/xuwenzheng/github/ACE/zace-lane-<x>` | 实现专用：一个会话独占到该卡完成 | 认领了该 lane 的会话 |

**禁止**：在会话里 `cd` 到主工作区改代码；禁止在别人的 lane 里写文件。

## 3. 操作规程

### 3.1 开工（每个实现会话）

```bash
cd /home/xuwenzheng/github/ACE/zace

# 1) 看哪个 lane 空闲
bash scripts/lane-worktrees.sh status

# 2) 认领（会写 .lane-owner，防止两个会话抢同一个 lane）
bash scripts/lane-worktrees.sh claim <lane> TASK-xxx

# 3) 切到自己的工作区，从最新 main 开分支
cd /home/xuwenzheng/github/ACE/zace-lane-<lane>
git fetch origin -q
git switch -c feature/task-xxx_<缩写><MMDD> main

# 4) 只在这里工作、提交
```

### 3.2 收工（每个实现会话）

```bash
# 1) 基线三条必须绿
uv run ruff check . && uv run python scripts/check_dependency_direction.py && uv run pytest -o addopts="" -q
#    注意：本仓 addopts=-q 会吞掉汇总行，必须加 -o addopts="" 才能看到 passed 数字

# 2) 回填任务卡"执行记录" + 任务板状态改 review
# 3) 提交
git add -A && git commit -m "task-xxx: ..."    # 英文祈使句 + 任务号
# 4) 不 push（推送由编排者统一做，避免多人 push 竞争）
# 5) 释放认领
cd /home/xuwenzheng/github/ACE/zace && bash scripts/lane-worktrees.sh release <lane>
```

### 3.3 集成（编排者）

```bash
cd /home/xuwenzheng/github/ACE/zace
bash scripts/lane-worktrees.sh guard          # 必须 ✅（在 main 且干净）
git merge --no-ff feature/task-xxx_<...>      # 逐卡合并
uv run ruff check . && uv run python scripts/check_dependency_direction.py && uv run pytest -o addopts="" -q
git push origin main                          # 推送由编排者统一做
```

### 3.4 清理

```bash
bash scripts/lane-worktrees.sh remove <lane>   # 有安全闸：脏/未合并/仍被认领一律拒绝
```

## 4. 共享文件的冲突热点（**唯一真正会撞的地方**）

各卡的**代码**文件所有权不重叠（这是任务卡设计保证的），但以下文件**人人都会改**：

| 文件 | 谁改 | 冲突避免方式 |
|---|---|---|
| `docs/tasks/README.md`（任务板） | 每张卡完工都改状态行 | 只改**自己那一行**；编排者合并时解决 |
| `docs/plan/contracts.md`（决策登记） | 需要新裁定时 | 只在卡内"申请"，由编排者写入 |
| `gitignore` / `.env.example` / 根 `pyproject.toml` | 少见 | 改前在卡内申请 |

**规则**：改这些文件时**只做最小改动**（一行/一段），不要顺手重排格式——重排会让别人的 diff 全部冲突。

## 5. 编排者的自查清单

每次进入主工作区前：

```bash
bash scripts/lane-worktrees.sh status   # 看清谁在用哪个 lane
bash scripts/lane-worktrees.sh guard    # 主工作区必须在 main 且干净
```

**发现主工作区被别的会话占用**（分支不是 main 或有未提交改动）：

- **不要**强行 `git switch`（会抛弃对方的未提交改动）；
- 若对方改动**必须保留**：`git stash push -u -m "<说明>"` 存起来后再切，并在派活提示词里告知对方去哪个 lane 继续；
- 若判断对方已收工：按其分支名建立对应 lane 继续，而不是在主工作区里接着干。

## 6. 已有事故的处置记录

| 时间 | 事故 | 处置 |
|---|---|---|
| 2026-09-13 | TASK-049 提交落到 `feature/task-070` 分支 | 用 `git commit-tree` 底层操作只把对应文件写回 main，**不切换分支**（避免动到并发会话的工作区） |
| 2026-09-13 | `feature/task-071` 的未提交工作被卷进 TASK-049 提交 | 该会话自行重做（`6049d59`）；编排者此后不再用 `git add -A` 在共享工作区提交 |
| 2026-09-13 | 主工作区被 WebUI 会话切到 `docs/repo-structure`，`main` 头指针随之偏移 | 把 WebUI 的未提交改动 `git stash push -u` 存档（可恢复），再切回 main |
