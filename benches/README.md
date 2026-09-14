# benches — golden set 与基准回归

> 用途：把"检索质量"变成可回归的数字（Module/02 §7-1）。Phase 1 的 M1 验收与 TASK-015 的校准都依赖本目录。

## 目录约定

| 路径 | 归属任务 | 内容 |
|---|---|---|
| `golden/*.jsonl` | TASK-014（样例骨架见 `golden/sample.jsonl`） | 查询用例集 |
| `run.py` | TASK-013 | golden runner：逐条执行 `engine.search`，产出 recall/MRR 报告 |
| `results/` | 各任务 | 报告产物（Markdown）：`phase1-baseline.md`、`phase1-bakeoff.md` 等 |
| `bakeoff/` | TASK-015 | embedding 对比与 rerank 校准脚本 |

## 用例格式（JSONL，一行一条）

```json
{"id": "zace-0001", "repo_hint": "zace", "commit": "self",
 "query": "chunk_id 是怎么构成的？", "lang": "zh",
 "category": "symbol",
 "expected": [{"path": "core/zace_core/types.py", "symbol": "ChunkDef"}],
 "notes": "dogfood：切片存储契约"}
```

| 字段 | 说明 |
|---|---|
| `id` | 全局唯一，`<repo>-<4 位序号>` |
| `repo_hint` | 期望仓库的提示名（如 `zace` / `flask` / `redis` / `fmt`）；runner 用 `--repo` 指向本地 checkout |
| `commit` | 期望的仓库版本（`self` 表示本仓库当前工作区；外部仓库填完整/短 hash） |
| `query` | 中/英/混合自然语言（可含反引号符号） |
| `lang` | `zh` / `en` / `mixed` |
| `category` | `symbol`（符号定位）/ `path`（文件定位）/ `behavior`（行为问题）/ `spec`（文档设计问题）/ `negative`（仓库不存在 → 期望无强证据） |
| `expected` | 命中集合：任一条的 `path` 出现在 top-k 候选（且若给 `symbol`，该符号出现在候选/证据中）即命中；`negative` 用空数组 |
| `notes` | 可选，出题人备注 |

## 指标定义

- **recall@k** = 命中用例数 / 总用例数（k=5、10）；**MRR** = 首个命中排名的倒数均值。
- 命中判定在 runner 中实现（TASK-013）；评估分列：整体 + 按 `lang` + 按 `category`。
- `negative` 用例单独统计：top5 无强相关证据且 `missingEvidence` 非空视为通过。

## 外部仓库准备（不 vendor 源码）

```bash
# 示例：按用例中记录的 commit 检出，runner 的 --repo 指向这里
git clone https://github.com/psf/requests /tmp/repos/requests && git -C /tmp/repos/requests checkout <commit>
```

外部仓库的选取与 commit 记录在 `golden/*.jsonl` 与报告里；同一用例集在不同机器上应能复现同一口径。

### 已指定的评测仓库（TASK-014 必须覆盖）

| repo_hint | 本地路径 | commit | 规模/特点 |
|---|---|---|---|
| `zace` | 本仓（`--repo .`） | `self` | dogfood；注意其 golden 文件自身会被索引（负例口径见下） |
| `aibox-super-sdk` | `/home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk` | `debf8a322aff7d2d21939bc6d09b4cfa985671ea` | 451 个可索引文件（266 py + 152 md）；**文档密度极高**（memory 能力 146 个 md / 83 个 py），是 spec 检索的主靶场 |
| （自选 1 个） | 使用者本机可得为准 | 记录实际 commit | 建议 C++（fmt）或 C（redis），补齐语言维度 |

- 种子用例：`benches/golden/aibox-seed.jsonl`（8 条，编排者已验证可落地）；TASK-014 在此基础上扩充并在报告中记录实际 commit。
- 该仓库的 `.venv/` 已在 `DEFAULT_SKIP_DIRS` 中，无需手工排除；索引前确认 checkout 到上述 commit。

#### 负例口径（R17）

- **外部仓库**：负例取该仓库中确实不存在的概念（种子文件已给一例；出题时用 `grep -ril` 核验 0 命中）。
- **zace 自身（dogfood）**：`benches/golden/*.jsonl` 就在被索引仓库内，查询原文会被 BM25/Vector 命中自身 → 负例须
  要么改用仓库中不存在的符号，要么在 eval 时用 `--exclude` 类参数（若有）排除 `benches/`；TASK-014 定口径并在报告写明。

## 运行

```bash
# 全量（目录级，需要该仓库已索引；索引优先级见下文“索引可复用”）
uv run zace-core eval --golden benches/golden --repo <本地仓库路径> --report benches/results/<name>.md

# 单仓库 + 复用预建索引（推荐：跑一次索引，之后每次改动几秒出分）
uv run zace-core eval --repo <任意 checkout> --data <共享索引根> --project-id <projectId> \
  --golden benches/golden/<repo_hint> --report benches/results/<name>.md

uv run python benches/bakeoff/embed_compare.py --help   # TASK-015 交付
```

> 单次 32 题 eval 实测约 10–15 秒（287 文件仓库 / 3416 切片）；开销几乎全在检索，
> 不在索引——所以“复用索引”是跑分提速的关键。

### 当前靶场与快速回归（cockpit-agents-py）

```bash
# 靶场（只读外部靶场：不在其中建文件、不修改它）
#   /home/xuwenzheng/4_AIBOX/gitlab/minicpm/cockpit-agents-py @ febac6d
# 索引根：~/.zace/cloud-demo（projectId 可从 `zace-core status` 读出）
uv run zace-core eval --repo /home/xuwenzheng/4_AIBOX/gitlab/minicpm/cockpit-agents-py \
  --data ~/.zace/cloud-demo --project-id <projectId> \
  --golden benches/golden/cockpit-agents-py --report benches/results/<name>.md
```

| 靶场 | golden | 状态 |
|---|---|---|
| `cockpit-agents-py` @ `febac6d` | `benches/golden/cockpit-agents-py/cockpit.jsonl`（32 条，含 2 负例） | **主靶场**（车载 Agent Server：Runtime/LangGraph/HMI/SDK/MCP/上下文预算/日志） |
| `zace`（本仓） | `benches/golden/zace/zace.jsonl`（20 条） | dogfood 回放；`benches/golden/**` 已由 `.zaceignore` 排除（见"出题规则"第 4 条） |
| `hello-agents` | `benches/golden/hello-agents/helloagents.jsonl`（31 条） | 2026-09-13 靶场，需另行检出 |
| `aibox-super-sdk` / `linux-mtk-mw-cameraservice` | 对应目录 | **旧机器靶场，本机不可得**，仅历史留存 |

## 用例编写指南（TASK-014 追加）

### 目录结构：按仓库分层

runner 的 `--golden` 接受**文件或目录**，目录模式会 `rglob` 收集全部 `*.jsonl`；而一次 eval 只针对一个
`--repo`。因此用例按仓库分层，一次目录调用 = 一个仓库的完整用例集：

```text
benches/golden/
├── zace/                         # dogfood（--repo .）
│   ├── sample.jsonl              # 格式样例骨架（TASK-013 遗留，4 条，随 TASK-014 移入本目录，内容未改）
│   └── zace.jsonl                # TASK-014 新增 20 条
├── aibox-super-sdk/
│   ├── aibox-seed.jsonl          # 编排者种子 8 条（随 TASK-014 移入本目录，内容未改）
│   └── aibox.jsonl               # TASK-014 新增 12 条
└── linux-mtk-mw-cameraservice/   # 自选 C++ 仓库
    └── cameraservice.jsonl       # TASK-014 新增 16 条
```

`benches/golden`（根）仍可整体跑通（id 全局唯一，跨仓库用例会对着单个仓库索引跑出必然失败，
只用于 runner 冒烟/回归，不用于指标口径）。**出题时不要把用例堆回根目录**，否则无法按仓库取指标。

### 命令模板

```bash
# 每个仓库一次（目录级）
uv run zace-core eval --golden benches/golden/zace --repo . --data <data-root> --report benches/results/<name>.md
# C++ 自选仓库
uv run zace-core eval --golden benches/golden/linux-mtk-mw-cameraservice \
  --repo /home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice --data /tmp/zace-cam \
  --report benches/results/<name>.md
```

### 两段口径（TASK-014 冻结）

| 段 | 排名来源 | 覆盖什么 |
|---|---|---|
| ① 索引层 | `SearchTrace.candidates`（recall→expand→rerank 后的候选池序） | 召回/融合/rerank 的质量，**不受 TASK-017/019 的装填影响** |
| ② 端到端 | `ContextPack` 的 E 编号装填序（`zace-core eval` 默认） | agent 实际读到的顺序（含装填、行序渲染、spec 保底） |

两段对比可定位增益来自哪一层。① 没有 CLI 开关，需用 `Engine.search_with_trace` 写十行脚本
（见 `results/phase1-baseline.md` §7 附录；建议编排者后续在 runner 上加 `--stage index|e2e`）。

### 出题规则

1. **期望必须是 grep 核验过的真答案**：`expected[].path` 用仓库相对路径精确匹配，`symbol` 可选但会额外收窄判定。
2. **符号期望按“证据级”写**：runner 的符号判定是单向的（证据符号需等于期望符号，或以 `.symbol` / `::symbol` 结尾，或在正文中按词边界出现）。
   期望写类名 `Indexer` 时，只有“符号就是 `Indexer`”的证据块才算命中，`Indexer.ingest` 的证据块会被判失败——想要类+成员都算命中，就把两条 `expected` 都写上。
3. **负例核验口径 = 被索引的文件集，不是 git 工作区**：`DirectorySource` 不使用 `.gitignore`，
   未跟踪文件（`CLAUDE.md`、`.claude/`、`egg-info/`、构建目录里的文本文件）同样入库。
   因此 `grep -ril <概念> <repo>` 必须覆盖未跟踪文件与构建目录（`.venv` 等除外）。
4. **zace dogfood 的回音已消除（TASK-101 §H）**：`benches/golden/**` 存的就是查询原文，此前会被索引，
   查询命中自己（实测 `zace-0110`/`zace-0117` 的 top-3 出现 `benches/golden/zace/zace.jsonl`）。
   现在由仓库根的 **`.zaceignore`** 排除 `benches/golden/` 与 `benches/results/` ——
   排除放在**项目层**而不是 `DEFAULT_SKIP_DIRS`：只有 zace 自己存在这个自引用，不该改 core 对所有仓库的行为。
   **注意**：老索引里已固化的回音不会被自动清掉，需要重建一次（`ingest --full`）。
5. **语言/类别配额**（Module/02 §7-1 的 golden set 要求）：中文 ≥15、英文 ≥10、中英混合 ≥15；
   类型须覆盖 `symbol` / `path` / `behavior` / `spec` / `negative`；至少 1 条 `negative` 在外部仓库上。
6. **索引可复用 —— 用 `--project-id` 直接挂预建索引**（TASK-101 §E/§F）：

   ```bash
   # ① 第一次（只有第一次需要真索引，分钟级 + embedding 花费）
   uv run zace-core ingest --repo /path/to/repo --data ~/.zace/bench
   #    输出 ``project: <projectId>`` —— 记下它

   # ② 以后任意次数（换 checkout、换 worktree、换分支都可以）
   uv run zace-core eval --repo /tmp/any-checkout --data ~/.zace/bench \
     --project-id <上面的 projectId> \
     --golden benches/golden/<repo> --report benches/results/<name>.md
   ```

   **为什么需要 `--project-id`**：数据目录名就是 D-29 身份算出的 `projectId`
   （`{data}/projects/{projectId}/`），而身份只由 **git remote + 仓库内的相对路径** 决定。因此
   换 checkout 路径、在无 `.git` 的副本、或又开一个 worktree 时都会解析到**另一个** projectId，
   进而去找一个不存在的索引。`--project-id` 就是把这个映射显式接管过来（实测：同 commit 的
   worktree 与裸副本都能直接复用同一份索引，跑分与原地一致）。

   **正确说法是“同一 remote + 同一相对路径的 worktree 共用同一个 project 目录，lane 之间会互相覆盖”；
   不是“路径变了也能复用”。** 后者是错的——这正是本卡实测修正的一条。

   **纪律**：
   - `--project-id` 跳过身份计算与 `project.json` 核验，**不**会静默重建索引；索引缺失或向量维度
     不符时**如实报错**（`DimensionMismatchError`）；
   - 报告里仍必须写清“索引来自哪个 commit / 哪个工作区”（见上一条）；
   - `--project-id` 只用于 benchmark/调试；**不要**在生产服务路径上使用它。
   - 共享索引根建议固定一个目录（如 `~/.zace/bench`）长期复用，不要每个 lane 各建一份。

### 跨主机复现（新 WSL / 另一台机器 / 换机克隆）

> **先读这条（合规，第 0 条）**：`index.db` 里存的是**切片正文原文**（`chunks.content`），
> 因此 bundle ≈ 被索引仓库的源码副本。**分发前先确认接收方有权接触该仓库源码**：
> 公司内部仓库（如 `cockpit-agents-py`）的 bundle **不得**进入公开仓库或公网主机
> （用例文件 `benches/golden/**` 可以，它只有问题与文件路径、没有正文）。
>
> **更省的做法（优先考虑）**：如果接收方本来就能 checkout 靶场，那它缺的只是 **embedding 能力**——
> 只共享 key、让它在本地索引一次即可（cockpit 规模约 2 分钟），**完全不扩散正文**，
> 也不需要传 17M。bundle 适用于"接收方拿不到靶场代码"或"要绝对复现同一份索引"的场景。

目标：**拉下代码就能跑分**，不重新索引。这靠两件东西：

| 件 | 解决什么 | 体积（cockpit 实测） |
|---|---|---|
| 索引（`index.db` + `vectors/`） | 不重新索引（省分钟级 + embedding 花费） | 17M |
| 查询向量侧车（`query-vectors.json`） | 目标机**没有 key / 没有本地模型**也能跑向量通道 | 0.7M / 32 条 |

**能力边界（实测，别记错）**：

| 场景 | `eval` | `search`（随便问） |
|---|---|---|
| 有 key | ✅ 正常，侧车只省往返 | ✅ 正常 |
| **无 key + 有侧车** | ✅ `--replay`，**仅限侧车里预热过的 query**（32 条 golden 正好是预热的） | ✅ 自动切离线；未预热的 query 如实降级并打印提示 |
| 无 key + 无侧车 | ❌ 向量通道全降级 | ❌ 同上 |

侧车是**缓存不是嵌入后端**：它不能给任意新 query 造向量。要"随便问"必须有 key（或本地模型，
但换模型 = 改指纹，指标不可比）。

> 只带索引是**不够**的：向量通道在**查询时**才调 `embed_query()`（CF-09），目标机没 key 就会
> 静默降级成 BM25+Exact，指标与出题机器不是同一口径。侧车把"查询 → 向量"也固化了。
> `blobs/` 与 `sync-state.json` 不进包——`eval`/`search` 不读它们（只用于增量同步）。

```bash
# ① 出题机器（有 key）：预热并打包（一次）
uv run zace-core eval --repo <靶场> --data <索引根> --project-id <id> \
  --golden benches/golden/<repo_hint> --report /tmp/prep.md \
  --vector-cache benches/golden/query-vectors.json          # 预热侧车
bash scripts/bench-bundle.sh pack <projectId> <靶场> /tmp/<repo>-bundle.tar.gz <索引根>

# ② 任意主机：解包 → 跑分（无需 key、可断网）
bash scripts/bench-bundle.sh unpack /tmp/<repo>-bundle.tar.gz ~/.zace/bench
uv run zace-core eval --repo <任意 checkout> --project-id <projectId> --data ~/.zace/bench \
  --golden benches/golden/<repo_hint> --report benches/results/<name>.md \
  --vector-cache <侧车> --replay                            # --replay = 不碰任何 embedding 后端
```

**实测口径（TASK-101，cockpit 32 题）**：预热机联网跑 vs 另一主机离线回放，
`recall@5 0.767 / recall@10 0.867 / MRR 0.505 / 负例 2/2` **完全一致**。

三条纪律（都经过反例验证）：

1. **未命中必须可见**：`--replay` 下查询不在侧车里 → 该用例走"向量通道降级"并计入报告
   （实测 1 条未命中 → 报告 `向量通道降级用例数：1`）。**不会**静默换成 BM25 冒充命中；
2. **指纹必须对得上**：侧车、索引、当前配置三者的 `embedding_model`/`dim` 不一致 → **直接拒绝**
   （实测报 `向量侧车文件与索引的 embedding 不一致`）。拿别的模型的向量算 cosine，指标会莫名变差
   且无从察觉，比直接失败危险得多；
3. **指纹以索引为准**：`--replay` 时从索引的 `index_config` 读 `(model, dim)`，**不**读环境变量——
   目标机的 `EmbeddingConfig.from_env()` 会回落到默认本地模型（实测 dim=384 vs 索引 1024），
   整轮跑分直接失败。

## 靶场变更（2026-09-13）

### 为什么换靶场

用户 2026-09-13 更换开发环境（家用 WSL2）。**旧靶场在本机全部不可得**，`benches/results/*` 的历史数字
无法在本机复现（数字来自旧机器的工作区，路径与 commit 都已不在）：

| 旧靶场 | 原路径（旧机器） | 本机状态 |
|---|---|---|
| `aibox-super-sdk` | `/home/xuwenzheng/4_AIBOX/gitlab/minicpm/aibox-super-sdk` | **不存在** |
| `linux-mtk-mw-cameraservice` | `/home/xuwenzheng/0_project/main/linux-mtk-mw-cameraservice` | **不存在** |
| `linux-mtk-hmi` | 同上系列 | **不存在** |

**旧 golden 文件原样保留**（`benches/golden/{aibox-super-sdk,linux-mtk-mw-cameraservice}/`，历史可追溯），
但**不可复用于新靶场**：`expected[].path` 是**仓库相对路径**，语义绑定到各自的仓库；
对另一个仓库跑只会得到必然失败。旧报告同理——它们是历史记录，不是当前基线。

### 新主靶场

```text
/home/xuwenzheng/github/hello-agents        # datawhalechina/hello-agents（Python Agent 教程）
commit: 4f7682ceafe573d07cd8a7d0b89908500e83227d
remote: https://github.com/datawhalechina/hello-agents.git
```

> 该仓库是**只读外部靶场**：不在其中建文件、不修改它、不把它的任何文件纳入 zace 仓库；
> 索引数据根放 `/tmp` 或 `~/.cache`。

选它的理由（编排者实测，见 `docs/plan/phase2-m2b-w6.md` §3.1）：**文档与代码一一对应**
（`docs/chapterN/` 中英双份 ↔ `code/chapterN/` 实现），天然覆盖 spec 检索、中英对照（D-20）
与 code/docs 平衡（R21）；`Co-creation-projects/` 提供多语言小项目；同时它含大量大文件与二进制
（272 个 >128KB、345 个 `.png`），是索引范围策略（TASK-037）的活标本。

**用例目录**：`benches/golden/hello-agents/helloagents.jsonl`（31 条，含 2 条负例）。
`repo_hint` 统一为 `hello-agents`，`commit` 为上面索引时的 `HEAD`。

### 只看某一层（召回层 vs 端到端）

两段口径（§“两段口径”）的对比靠 `Engine.search_with_trace` 的候选池序：

```python
from zace_core.engine import Engine
trace = Engine.open("~/.zace/bench").search_with_trace("<projectId>", query, 10_000)
trace.pack      # ② 端到端：agent 实际读到的顺序
trace.candidates  # ① 索引层：recall → expand → rerank 后的候选池序（不受装填闸门影响）
```

定位“答案没进包”时先看这两个：候选池里**有**、包里**没有** → 是装填/配额问题（`docs_ratio`、
`score_ratio`），不是召回问题。

### 出题纪律（沿用 TASK-014，不放松）

- 每条 `expected[].path` 都用 `grep` 核验过**存在**，且**在被索引的文件集内**（`DirectorySource` 的
  口径，不是 git 工作区——见上文"出题规则"第 3 条）；
- 负例用该仓库**确实不存在**的概念核验 `0` 命中；核验必须覆盖**被索引的文件集**而非 git 工作区；
- 不为了指标好看而挑用例子集或放宽负例口径（R29/R30：本报告的指标是**回归护栏**，不是优化目标）。

### 相关报告

| 报告 | 内容 |
|---|---|
| `results/phase2-helloagents-baseline.md` | 新靶场基线（recall/MRR，分 category 与语言；含索引范围实测） |
| `results/phase1-baseline.md` 等旧报告 | 旧机器/旧靶场的历史记录，**与本靶场不可比** |
