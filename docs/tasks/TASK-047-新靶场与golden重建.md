# TASK-047：新评测靶场建立与 golden 重建（hello-agents）+ M2a 冒烟脚本

> 状态：**review** ｜ 阶段：Phase 2（M2b / W6-lane C）｜ 硬依赖：无（core 可用即可）｜ soft 依赖：TASK-046（云端 embedding 让索引变快）
> 建议分支：`feature/task-047_<你的缩写><MMDD>`
> 交付物所有权：
> - `benches/golden/hello-agents/`（**新建目录**：本靶场用例）
> - `benches/README.md`（**仅**追加"靶场变更"章节；不改既有内容）
> - `benches/results/phase2-helloagents-baseline.md`（**新建**：基线报告）
> - `scripts/m2a-smoke.sh`（**新建**：一键冒烟）
> - `docs/handbook/M2a-验收手册.md`（**仅**追加"§10 一键冒烟脚本"一节，指向脚本；不改既有章节）
> - `docs/tasks/TASK-047-新靶场与golden重建.md`（本卡）、`docs/tasks/README.md`（本行）
>
> 清单外文件不得改（尤其 `core/**`、`docs/contracts/**`、`docs/design/**`）。

## 背景（为什么需要本卡）

**旧靶场全部不可得**：用户 2026-09-13 更换开发环境（家里 WSL2）。原三靶场
（`aibox-super-sdk` / `linux-mtk-mw-cameraservice` / `linux-mtk-hmi` 等）**在本机不存在**，
`benches/results/*` 的全部历史数字**无法复现**。而 TASK-037（索引范围）与后续 TASK-050（质量调优）
都需要靶场。

**用户拍板的新靶场**（`docs/plan/phase2-m2b-w6.md` U4）：

```text
/home/xuwenzheng/github/hello-agents     # datawhalechina/hello-agents（Python Agent 教程）
commit: 4f7682c（git remote: https://github.com/datawhalechina/hello-agents.git）
```

**为什么它是个好靶场**（编排者实测）：

| 特性 | 数字/事实 | 对 zace 的价值 |
|---|---|---|
| 规模适中 | 排除 `venv/` 后约 **976** 个可索引文件（227 `.md` + 749 `.py`） | 全量索引在一次会话内可完成 |
| **文档与代码一一对应** | `docs/chapterN/`（**中英双文档**）↔ `code/chapterN/`（实现） | **天然验证 spec 检索 + code/docs 平衡（R21）** |
| 真 `.gitignore` 样本 | 含 `venv/`、`__pycache__/`、`docs/_build/` 等规则；仓库里**真有** 10405 个 `.pyc` 与 5.0GB 的 `venv/` | **TASK-037 的活标本**：忽略规则落地前后可量化对照 |
| 有噪声文件 | **272 个 >128KB**（最大 7.1MB 的 png）、345 `.png`、58 个无扩展名文件 | TASK-037 的阈值（128KB / 二进制）可量化验证 |
| 多语言混合 | `Co-creation-projects/`（47 个独立小项目，含 `.vue` `.ts` `.json`） | 兜底切分路径与跨语言噪声的回归 |
| 中文为主 + 英文对照 | 每章中英双份 | D-20（CJK 一等场景）与中英一致性的真实回归 |

## 输入文档（按序读，只读所需章节）

1. `docs/plan/phase2-m2b-w6.md` §2.1/§2.5（本环境基线）/ §3.3（本卡定位）
2. `benches/README.md`（**用例编写指南**：`expected` 的 `path`/`symbol` 语义、负例口径、目录分层规则）
3. `docs/tasks/TASK-014-Golden集与基线.md`（历史口径与 DoD；**本次不重复它的靶场**，但沿用其纪律）
4. `docs/plan/contracts.md` §3.6（R29/R30：60 条 smoke 集的定位与"不据此调参"的纪律）
5. `docs/handbook/M2a-验收手册.md` §4.2（最小 MCP 客户端脚本——**冒烟脚本要复用它，不要重写**）

## 冻结接口（本卡不得变更）

- **消费**：`zace-core eval` 的 CLI 参数与 golden JSONL schema（见 `benches/README.md`）、
  `zace-service` 的 CLI（`local` / `mcp-config`）与 `/healthz`、`/api/projects/{id}` 的字段集（CF-05）。
- **产出**：`benches/golden/hello-agents/*.jsonl`（新用例）、`scripts/m2a-smoke.sh`（新脚本）。
- **不改**：`zace-core` / `zace-service` 的任何代码（本卡是**评测与脚本**卡，不是实现卡）。

## 交付内容

### §A 新靶场 golden（≥ 20 条，正例 + 负例）

**纪律（沿用 TASK-014，不可放松）**：

- 每条 `expected[].path` 必须是**用 `grep`/`read` 核验过的真答案**（不是"大概在这里"）；
- `symbol` 可选，但写了就必须真要收窄判定（写错会让用例失败，等于自欺）；
- 负例必须是**该仓库确实不存在的概念**（`grep -ril` 核验 0 命中）；
- **用例覆盖**（每条至少归一类，在 `category` 字段标明）：

| category | 说明 | 本靶场取材建议 |
|---|---|---|
| `spec` | 设计/教程文档中的概念 | 每章的中文文档（如"ReAct 范式"、"上下文工程"） |
| `symbol` | 具体符号定位 | `code/chapter4/ReAct.py`、`code/chapter8/03_WorkingMemory_Implementation.py` 等 |
| `behavior` | "怎么做/为什么" | 如"记忆工具如何做多轮检索"（对应第八章文档 + 实现） |
| `path` | 路径/文件定位 | `Co-creation-projects/<项目名>/` 定位某个小项目 |
| **中英对照** | 同一目标的中英两种问法 | 每章中英双文档是天然素材（验证 D-20） |

- **≥ 20 条**，其中**负例 ≥ 2 条**；正例要**跨章节分布**（不要全挤在 ch4/ch8）；
- `repo_hint` 统一填 `hello-agents`；`commit` 填你实际索引的 commit（`git rev-parse HEAD`）。

### §B 基线报告（`benches/results/phase2-helloagents-baseline.md`）

必须包含：

1. **被测对象**：路径、commit、**索引范围摘要**（列举文件数、实际解析数、chunks、skipped 与原因分布）；
2. **指标**：`recall@5` / `recall@10` / `MRR` / 负例通过情况，**分 category 与分语言拆开**；
3. **完整可复现命令**（含 embedding 配置：本波用云端，见 TASK-046 的手册）；
4. **本卡与历史的可比性声明**：旧靶场数字**不可比**（不同仓库），本报告是**新基线**；
5. **观察与未决**（如实记录，不要去"修"检索质量——那是 TASK-050，且需真实数据）。

**重要**：本报告的指标**不是优化目标**（R29/R30 仍然有效），只是新靶场的回归护栏基线。

### §C 旧靶场文件处置（**保留**，不删除）

- 旧 `benches/golden/{aibox-super-sdk,linux-mtk-mw-cameraservice}/` **原样保留**（历史可追溯）；
- 在 `benches/README.md` **追加**一节"靶场变更（2026-09-13）"，写清：
  哪些靶场不可得、为何换、新靶场是哪个、旧 golden 可否复用（**不可**：路径语义不同仓库）；
- **不要**改 `benches/README.md` 的既有内容（追加即可）。

### §D 一键冒烟脚本（`scripts/m2a-smoke.sh`）

**目标**：把"起服务 → 等索引 → 调 MCP → 断言命中"变成一条命令，**把本环境的坑固化进脚本**。

必须做到：

1. **key 注入**（F3：`.bashrc` 的非交互守卫让子进程拿不到 key）：
   脚本需能自己拿到 key（从 `~/.bashrc` 提取，或读 `.env`，或要求调用者 export——
   **选一种并在 `--help` 与文档里写清**）；找不到 key 时**明确报错并给出解决命令**，不要静默继续；
2. **`NO_PROXY=127.0.0.1,localhost`**（本机有 `http_proxy`，否则连不上本机服务）；
3. **端口/数据根/仓库路径可配**（默认值合理，且**不硬编码本机绝对路径**为唯一选项）；
4. **等索引**：轮询 `GET /api/projects/{id}` 直到 `state="done"`，**带上限**（如 30 分钟）并在超时时
   如实报当前进度（**不要伪造百分比**，D-30）；
5. **调一次 `search_context`**（复用 `docs/handbook/M2a-验收手册.md` §4.2 的最小客户端思路），
   **断言返回里有 `文件:行号`**（不能只看 exit code）；
6. **清理**（可选 `--keep`）：结束时停服务；**不动被索引的仓库**；
7. `set -euo pipefail`；失败时打印**可读的下一步**（不是裸堆栈）。

**验收**：脚本在实施 AI 本机**真跑过**，把完整输出贴进执行记录。

### §E 手册补充（追加一节）

在 `docs/handbook/M2a-验收手册.md` **追加** `## 10. 一键冒烟（可选）`：
指向 `scripts/m2a-smoke.sh`，写清用法、前置（key 怎么给）、失败时怎么排查。
**不要改**手册 0-9 节的既有内容。

## 验收标准（DoD）

- [ ] `benches/golden/hello-agents/` 存在，**≥ 20 条**（含负例 ≥ 2），每条 `expected` 经 grep 核验；
- [ ] `uv run zace-core eval --golden benches/golden/hello-agents --repo /home/xuwenzheng/github/hello-agents --data <数据根> --report benches/results/phase2-helloagents-baseline.md` 跑通，报告落盘；
- [ ] 报告中 **每个数字都能追溯到命令**；分 category 与分语言拆开；
- [ ] `benches/README.md` 追加了靶场变更章节（既有内容未动）；
- [ ] 旧 `benches/golden/{aibox-super-sdk,linux-mtk-mw-cameraservice}/` **仍在**（未被删除/修改）；
- [ ] `scripts/m2a-smoke.sh` 本机跑通，**断言了 `文件:行号`**（不是只看 exit code），输出贴进执行记录；
- [ ] 手册追加了 §10（既有 0-9 节未动）；
- [ ] 基线三条全绿：`uv run ruff check .`、`uv run python scripts/check_dependency_direction.py`、
      `uv run pytest -o addopts="" -q`（用 `-o addopts=""` 才能看到 passed 数字）；
- [ ] 任务卡"执行记录"已回填；任务板对应行状态改 `review`。

## 明确不做

- **不调检索质量参数**（R29/R30 冻结；R21/rerank/装填全归 TASK-050，且需要 TASK-023 的真实数据）；
- **不实现 `.gitignore` 解析**（那是 TASK-037 的领地——本卡的 §C 会给它提供**前后对照的数字**，
  但本卡自己不碰 `core/zace_core/pipeline/`）；
- **不删除任何既有 golden 文件或历史报告**；
- 不为了指标好看而挑用例子集或放宽负例口径（**这是本卡最容易犯的错**）；
- 不把靶场仓库（`hello-agents`）的任何文件纳入 zace 仓库（它是外部只读靶场）；
- 不在脚本里硬编码 key。

## 参考源码锚点（只读）

- `benches/README.md`（**用例编写指南**：schema、负例口径、目录分层——**先读这一节再出题**）
- `benches/run.py`（runner 实现：`--golden` 接受文件或目录、指标口径）
- `docs/handbook/M2a-验收手册.md` §4.2（最小 MCP 客户端：**复用，不要重写**）
- `core/zace_core/pipeline/source.py`（`DEFAULT_SKIP_DIRS`：理解当前**已经**跳过了什么，
  这决定你的"索引范围摘要"怎么读——`venv/` 已被跳过，但 272 个 >128KB 文件没有）
- `/home/xuwenzheng/github/hello-agents/`（靶场本体，**只读**：不要修改、不要在其中建文件）

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写，**必须包含**：

- 用例清单（id / category / lang / 期望目标一句话）；
- 基线指标表（分 category 与语言）；
- 索引范围实测（列举文件数 / 解析数 / chunks / skipped 分布）；
- 冒烟脚本的真实输出；
- 未决问题（尤其是**需要编排者裁定的**，例如某条用例期望与索引范围策略冲突）。

## 执行记录

### 2026-09-13 ｜ 分支 `feature/task-047_xwz0913` ｜ 状态：完成（待评审）

#### §A 新靶场 golden

- `benches/golden/hello-agents/helloagents.jsonl`：**31 条**（29 正例 + 2 负例），
  `repo_hint=hello-agents`，`commit=4f7682ceafe573d07cd8a7d0b89908500e83227d`。
- 分布：`symbol` 16 ｜ `spec` 12 ｜ `path` 1 ｜ `negative` 2；语言 `zh` 23 ｜ `en` 8。
- **跨章节覆盖 14 章**：ch1/2/3/4/7/8/9/10/11/12/13/14/15/16（未挤在 ch4/ch8）。
- 每条 `expected` 的核验脚本：
  ① 路径在磁盘存在；② 路径**在被索引的文件集内**（`DirectorySource` 口径，非 git 工作区）；
  ③ 若给了 `symbol`，该串确实出现在目标文件里。核验结果 **problems: 0**。
- 负例核验（对被索引的文件集，`grep -ril`，含未跟踪文件）：
  `reconcile`/`kubebuilder`/`CustomResourceDefinition` = 0；`Redlock`/`分布式锁`/`distributed lock` = 0。
- **未挑用例子集**：失败用例保留在集合里（R29/R30）。

#### §B 基线（`benches/results/phase2-helloagents-baseline.md`）

命令（完整可复现命令与 embedding 配置见报告的 §1）：

```bash
uv run zace-core eval --golden benches/golden/hello-agents \
  --repo /home/xuwenzheng/github/hello-agents --data /tmp/zace-ha \
  --report benches/results/phase2-helloagents-baseline.md
```

| 分组 | 用例数 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|
| **总体（正例）** | 29 | **0.655** | **0.690** | **0.460** |
| zh | 22 | 0.636 | 0.682 | 0.424 |
| en | 7 | 0.714 | 0.714 | 0.571 |
| symbol | 16 | 0.562 | 0.625 | 0.333 |
| spec | 12 | 0.750 | 0.750 | 0.625 |
| path | 1 | 1.000 | 1.000 | 0.500 |
| **负例** | 2 | — | — | **2/2 通过** |

向量通道降级用例数：**0**。

#### §C 旧靶场文件处置

`benches/golden/{aibox-super-sdk,linux-mtk-mw-cameraservice}/` **原样保留**（`git status` 无变更）。
`benches/README.md` **追加**「靶场变更（2026-09-13）」一节（+50 行，**0 删除**）。

#### §D 冒烟脚本（真实输出）

`scripts/m2a-smoke.sh` 在本机**真跑通过**（数据根 `/tmp/zace-smoke-clean`，`--max-retries 5`）：

```text
$ bash scripts/m2a-smoke.sh --repo /home/xuwenzheng/github/hello-agents \
      --data-root /tmp/zace-smoke-clean --port 8792 --query "记忆工具如何实现多轮检索？"
[1/5] key 已就绪（来源已解析，长度 51，不回显内容）
[2/5] 起服务：zace-service local --repo /home/xuwenzheng/github/hello-agents --data-root /tmp/zace-smoke-clean --port 8792
        projectId=e9ee9dd1d41a7d2c ｜ 服务日志：/tmp/zace-smoke-clean/zace-smoke-service.log
[3/5] 等索引完成（上限 1800s，每 5s 轮询一次；被 429 中断时最多重试 5 次）
        state=running，本次已解析 0/1862 个文件…
        （约 5 分钟后）
        索引完成：state=done，本次解析 1482/1862 个文件（无改动时 processed=0 属正常）
[4/5] 调 MCP tools/call search_context（断言返回里有「文件:行号」）
[zace] answerable=true · confidence=medium · evidence=22 · docs=4 · mode=fast · channels=bm25,vector · degraded=false

## Relevant Context
### Code
[E2] search_memory_demo — code/chapter8/01_MemoryTool_Basic_Operations.py:78-106
     reason: bm25 -14.9703 + bm25 rank 38 + vector 0.6394 + vector rank 6 + entry point / exported symbol +0.2
     78 | def search_memory_demo(memory_tool):
     79 |     """搜索记忆演示 - 实现语义理解的检索"""
     ...
[OK] 冒烟通过：MCP 返回包含「文件:行号」证据。          ← 退出码 0
[5/5] 已清理数据根：/tmp/zace-smoke-clean（--keep 可保留）
```

断言是 `grep -Eq '([A-Za-z0-9_./-]+\.[A-Za-z0-9]+):[0-9]+'`，**不是**只看 exit code。

#### §E 手册补充

`docs/handbook/M2a-验收手册.md` **追加** `## 10. 一键冒烟（可选）`（+80 行，**0 删除**；0-9 节未动）。

#### 索引范围实测

```text
files: added=1482 modified=0 deleted=0 parsed=1482
chunks: new=9971 reused=0 removed=0
vectors: upserted=9971 deleted=0
skipped: 380 个二进制/不可解码文件
elapsed: 364.1s
```

| 口径 | 数字 |
|---|---|
| 目录列举（`list_files()`） | 1862 |
| 实际解析 | 1482 |
| 跳过二进制 | 380（345 `.png` + 20 `.jpg` + 其余 `.db/.mp3/.pdf/.docx/.xlsx/.ogg/.ico`） |
| chunks / vectors | 9971 / 9971 |
| 解析语言分布 | python 749 ｜ markdown 227 ｜ fallback 506 |
| 解析错误 | 0（`files.parse_errors` 全为 `[]`） |

#### 验收标准（DoD）自查

- [x] `benches/golden/hello-agents/` 存在，31 条（含负例 2），每条 `expected` 经 grep 核验
- [x] `zace-core eval` 跑通，报告落盘 `benches/results/phase2-helloagents-baseline.md`
- [x] 报告中每个数字可追溯到命令；分 category 与语言拆开
- [x] `benches/README.md` 追加靶场变更节（既有内容未动）
- [x] 旧 golden 目录仍在（未被删除/修改）
- [x] `scripts/m2a-smoke.sh` 本机跑通，断言了 `文件:行号`（输出见上）
- [x] 手册追加 §10（0-9 节未动）
- [x] 基线三条全绿：`ruff` clean ｜ 依赖方向 通过 ｜ **668 passed, 2 skipped**（14.12s）
- [x] 本执行记录已回填；任务板对应行改 `review`

#### 与设计的偏差

无。未改 `core/**`、`service/**`、`docs/contracts/**`、`docs/design/**`；未碰 `hello-agents` 仓库。

#### 未决问题（需编排者裁定）

1. **基线产生于 TASK-046 之前**：索引时 `max_input_tokens` 走「未登记模型」分支 = **2048**（不是 bge-m3
   的 8192）。TASK-046 合入后若继续把本报告当长期护栏，**需裁定是否重跑**（长 chunk 的向量会变）。
   本卡不擅自重跑。
2. **F4 的实测补充（归属 TASK-046 §D）**：本机 TPM 限流约 **200K tokens/分钟**；且 `api.py` 一次 429
   即终结整次 ingest（实测复现 `chunks=9971 / vectors=0` 的静默降级形态）。本卡以 `EMBED_BATCH_SIZE=4`
   规避（未改 core），但**这正是泳道 B 要修的问题**——建议 B 的实现把「按 token 截断 + 按 token 分批 +
   429 有界重试」作为验收项。
3. **`symbol` 类指标偏低（0.562）**：失败模式是「文档挤掉代码」（`helloagents-0001/0002/0003/0017`），
   与 **R21 是同一现象在新靶场的再现**。按 R29/R30 **本卡不做任何调参**；证据留作 TASK-050 的素材。
4. **与 TASK-037 的接口**：本报告的「索引范围实测」是 TASK-037 的**前对照**（1862 列举 / 380 二进制跳过）；
   037 落地后 `list_files()` 预期降到 ~976，届时需更新本节数字。
5. **不要并发指向同一 `--data-root`**（实测会导致向量表 rebuild 清零）——已写进 `benches/README.md`
   与手册 §10 的提醒。
