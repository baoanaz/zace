# benches — golden set 与基准回归

> 用途：把"检索质量"变成可回归的数字（Module/02 §7-1）。Phase 1 的 M1 验收与 TASK-015 的校准都依赖本目录。

## 新会话从这里开始（30 秒导航）

本目录混了**两类**东西：① 检索质量回归（golden 用例）② 索引耗时/吞吐基准。
先对号入座，不要通读：

| 我要… | 入口 |
|---|---|
| 跑检索质量回归（eval） | 本文件「靶场」「运行」两节 + `benches/run.py --list-targets` |
| **复用三靶场持久索引**跑基准（**不要重新索引**） | `targets-benchmark.md` §持久索引 + `results/raw/ingest-vps/INDEXES.json` |
| 看索引耗时/内存/带宽/TPM 的结论与留档 | `results/README.md`（报告索引）→ `results/index-cost-model-vps.md` |
| 改维度 / chunk 切分前，先看冻结配置与基线 | **`results/baseline-v1.md`** |
| 改计量脚本 / 查指标口径定义 | `embed-bench/README.md` |
| 找某个数字的原始证据 | `results/README.md` §4 `raw/` 证据索引 |

> **设备绑定纪律**：`results/` 里的每个数字只对产它的设备成立（VPS 生产 `vps-la-2c2g` vs 公司 WSL `company-wsl`），
> 引用时必须带设备标识与日期；跨设备直接比大小是错的。

## 目录约定

| 路径 | 内容 |
|---|---|
| `targets.json` | **靶场清单**：把「用例集 + 预建索引」绑成靶场名（golden / commit / projectId / 指纹 / 产物获取方式）。只放元信息，**不放索引** |
| `golden/<repo>/*.jsonl` | 查询用例集（问题 + 期望文件/符号；**不含正文**） |
| `run.py` | 统一入口：`--target <靶场名>` 展开 `--golden`/`--project-id`，其余参数原样转给 `zace-core eval` |
| `test_targets.py` | 清单与入口的单元测试（不在根 `pyproject.toml` 的 `testpaths` 里，跑法见"运行"） |
| `results/*.md` | 报告产物：当前口径的原始报告 + 整理过的基线/选型报告 |
| `results/README.md` | **报告与原始证据索引**（哪份是当前口径、哪份是历史留档、数字出处在哪） |
| `targets-benchmark.md` | **耗时基准靶场登记**：`benchmark/{leveldb,HelloAgents,langchain}` 三档规模与持久索引 |
| `embed-bench/` | 索引耗时/吞吐计量脚本（含指标口径定义与内存纪律），见其 `README.md` |
| `bakeoff/` | embedding 选型脚本（TASK-015A；一次性方法学工具，不是用例集） |

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

## 靶场（用例集 + 本地索引）

**默认流程：公共仓库 + 本地建一次索引 + 索引落持久目录**，之后只跑 `eval`。
索引是可重建的派生物，**不进任何分发通道**——产品侧不负责索引传递，公开服务器也不该收到别人的源码副本。

```bash
uv run python benches/run.py --list-targets     # 清单：角色 / 用例 / commit / 索引来源
```

| 角色 | 靶场 | 用例 | commit | 索引 |
|---|---|---|---|---|
| **primary（主靶场）** | `hello-agents`（`datawhalechina/hello-agents`） | 31（含 2 负例） | `4f7682ceafe5` | clone 到该 commit，`zace-core ingest` 一次 |
| dogfood | `zace`（本仓） | 24（`zace.jsonl` 20 + `sample.jsonl` 4） | `self` | 本仓自举，405 文件 ≈ 34s；projectId 已记在清单，任意 checkout 可复用 |
| internal（**不进默认流程**） | `cockpit-agents-py` | 32（含 2 负例，答案经读码核实） | `febac6d2273bb` | 索引含公司内部源码，只能内网获得（`scripts/bench-bundle.sh`）；公开机器不参与 |

主靶场建索引（**只做一次**）：

```bash
git clone https://github.com/datawhalechina/hello-agents /path/to/hello-agents
git -C /path/to/hello-agents checkout 4f7682ceafe573d07cd8a7d0b89908500e83227d
uv run zace-core ingest --repo /path/to/hello-agents --data ~/.zace/bench   # 打印 project: <id>（可记进清单）
```

- 外部靶场是**只读**的：不在其中建文件、不修改它、不把它的源码纳入本仓；索引数据根放持久目录（`~/.zace/bench`）。
- `expected[].path` 是**仓库相对路径**，绑定各自的仓库与 commit；换靶场或换 commit 都要重新核对期望，不能复用。
- 教程仓（hello-agents）文档多、代码少，覆盖 spec 检索与中英对照；想要更强的代码检索区分度，可照同一套出题
  规则再加一个**公共工程仓**当第二主靶场（如 `openai-agents-python` / `langgraph`）。
- 旧靶场 `aibox-super-sdk` / `linux-mtk-mw-cameraservice`（及其用例与报告）已于 2026-09-14 下线：
  靶场在旧机器上不可得，且用例里的 `expected[].path` 暴露公司内部仓库结构。历史见 git。

#### 负例口径（R17）

- **外部仓库**：负例取该仓库中确实不存在的概念（种子文件已给一例；出题时用 `grep -ril` 核验 0 命中）。
- **zace 自身（dogfood）**：`benches/golden/*.jsonl` 就在被索引仓库内，查询原文会被 BM25/Vector 命中自身 → 负例须
  要么改用仓库中不存在的符号，要么在 eval 时用 `--exclude` 类参数（若有）排除 `benches/`；TASK-014 定口径并在报告写明。

## 运行

### 一键跑分（推荐：靶场名 + 数据根）

```bash
# 主靶场（hello-agents）：先按上节建一次索引，之后每次跑分只读索引
uv run python benches/run.py --target hello-agents --repo /path/to/hello-agents \
  --data ~/.zace/bench --report benches/results/<name>.md

# zace（dogfood）：索引建一次，之后**任意 checkout** 都能复用（projectId 已记在清单里）
uv run python benches/run.py --target zace --data ~/.zace/bench \
  --report benches/results/<name>.md

# 没有 key 的机器：带预热好的查询向量侧车 + --replay（指标与联网跑逐位一致）
uv run python benches/run.py --target zace --data ~/.zace/bench \
  --report benches/results/<name>.md \
  --vector-cache ~/.zace/bench/query-vectors-zace.json --replay

# 内部靶场（不进默认流程）：索引 + 侧车从内网来，本机无需 key、无需靶场代码
uv run python benches/run.py --target cockpit-agents-py --data ~/.zace/bench \
  --report benches/results/<name>.md --vector-cache <侧车> --replay
```

> **索引根必须放持久目录（约定 `~/.zace/bench`），别放 `/tmp`。**
> `--data` 下的索引是**长期资产**（zace 自举实测 57M / 5297 切片）：放 `/tmp` 会在重启后消失，
> 下次跑分又得重新索引 + 重新嵌入（还要花 key 的额度）。`/tmp` 只适合"临时试一下"。
>
> **固定用例 + 固定索引 = 观察 core 改动的干净口径**：题目与期望答案不动、索引不动，只改 core，
> 两次 `eval` 的差值就是改动的净效果。索引本身只在 core 的切片/嵌入指纹变化时才需要重建
> （指纹不符时 `eval` 会直接报错，不会拿旧索引冒充同一口径）。

`--target` 只做一件事：按 `benches/targets.json` 注入 `--golden` 与 `--project-id`，并把出处
（commit / projectId / 索引来源）打到 stderr——报告要能回答"这份数字来自哪份索引"。命中判定与
指标口径仍在 `zace-core eval`，这里**没有**第二套实现。

### 直接调 CLI（等价的裸写法）

```bash
# 单仓库 + 复用预建索引
uv run zace-core eval --repo <任意 checkout> --data <共享索引根> --project-id <projectId> \
  --golden benches/golden/<repo_hint> --report benches/results/<name>.md

uv run python benches/bakeoff/embed_compare.py --help   # TASK-015A 交付
```

> 单次 32 题 eval 实测约 10–15 秒（287 文件仓库 / 3416 切片）；开销几乎全在检索，
> 不在索引——所以"复用索引"是跑分提速的关键。

### 跑 benches 自己的测试

`benches/` 不在根 `pyproject.toml` 的 `testpaths` 里（CI 不覆盖），要显式给路径：

```bash
uv run pytest -o addopts="" -q benches/test_targets.py benches/bakeoff/test_embed_compare.py
```

## 用例编写指南（TASK-014 追加）

### 目录结构：按仓库分层

runner 的 `--golden` 接受**文件或目录**，目录模式会 `rglob` 收集全部 `*.jsonl`；而一次 eval 只针对一个
`--repo`。因此用例按仓库分层，一次目录调用 = 一个仓库的完整用例集：

```text
benches/golden/
├── cockpit-agents-py/            # 主靶场（内部仓库，只放用例）
│   └── cockpit.jsonl             # 32 条（含 2 负例）
├── zace/                         # dogfood（--repo .）
│   ├── sample.jsonl              # 格式样例骨架（TASK-013 遗留，4 条）
│   └── zace.jsonl                # TASK-014 新增 20 条
└── hello-agents/                 # 公开靶场（datawhalechina/hello-agents）
    └── helloagents.jsonl         # 31 条（含 2 负例）
```

**出题时不要把用例堆回根目录**：一次 eval 只对一个仓库取指标，混在一起会跑出必然失败。
需要跨靶场冒烟时直接用 `benches/run.py --target <名字>` 逐个跑。

### 命令模板

```bash
# 推荐走 --target（见"运行"）；下面是等价的裸 CLI 写法
uv run zace-core eval --golden benches/golden/zace --repo . --data <data-root> \
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

> **这一节只适用于"接收方拿不到靶场代码"的场景（内部靶场），不是默认流程。**
> 默认流程是公共靶场 + 本地建索引（见上节）；`bundle` 会分发靶场正文，属于例外手段。

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

## 靶场变更（2026-09-13 换靶场；2026-09-14 清理旧靶场）

### 为什么换靶场，以及旧靶场为什么被删掉

用户 2026-09-13 更换开发环境（家用 WSL2）。**旧靶场在新机器上全部不可得**，`benches/results/*` 的历史数字
无法复现（数字来自旧机器的工作区，路径与 commit 都已不在）：

| 旧靶场 | 原路径（旧机器） | 现状 |
|---|---|---|
| `aibox-super-sdk` | `<内部靶场>/aibox-super-sdk` | **已下线**：靶场不可得，且用例 `expected[].path` 暴露公司内部仓库结构 → 用例与旧报告于 2026-09-14 删除（历史见 git） |
| `linux-mtk-mw-cameraservice` | `<内部靶场>/linux-mtk-mw-cameraservice` | 同上 |
| `linux-mtk-hmi` | 同上系列 | 从未出题 |

删掉而不是留档的理由：`expected[].path` 是**仓库相对路径**，语义绑定各自的仓库，换靶场不可复用；
而它们躺在公开仓库里就等于把内部仓库的目录结构对外发布。旧报告同理——是历史记录，不是当前基线。

### 当前靶场

| 靶场 | 用例 | 检查点 |
|---|---|---|
| `cockpit-agents-py` @ `febac6d` | 32 条（含 2 负例） | **主靶场**：车载 Agent Server（Runtime/LangGraph/HMI/SDK/MCP/上下文预算/日志）；内部仓库，索引只走内网 |
| `hello-agents` @ `4f7682c` | 31 条（含 2 负例） | 公开教程仓（`datawhalechina/hello-agents`）；文档与代码一一对应，覆盖 spec 检索与中英对照（D-20） |

两个外部靶场都是**只读**的：不在其中建文件、不修改它、不把它的源码纳入 zace 仓库；
checkout 路径由运行时给（`--repo` 或 `targets.json` 的提示），**不硬编码在本仓文档里**；
索引数据根放 `~/.zace/...` 或 `/tmp`。

选 hello-agents 的理由（编排者实测，见 `docs/plan/phase2-m2b-w6.md` §3.1）：**文档与代码一一对应**
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
| `results/raw-helloagents-baseline.md` | **主靶场**（hello-agents @ `4f7682c`，31 题）基线：recall@5 0.586 / recall@10 0.655 / MRR 0.388 / 负例 1/2（2026-09-14，voyage-4-lite / 1024 维） |
| `results/raw-cockpit-baseline.md` / `raw-cockpit-t101-final.md` | 内部靶场（cockpit 32 题）的原始 eval 报告：修复前 / TASK-101 修复后 |
| `results/raw-zace-t101-final.md` | zace dogfood（20 题）TASK-101 修复后的原始报告 |
| `results/phase2-helloagents-baseline.md` | hello-agents 靶场基线（recall/MRR，分 category 与语言；含索引范围实测） |
| `results/index-cost-model-company-wsl.md` | **索引耗时模型 + 设备绑定基准**（`company-wsl`）：`耗时 ≈ chunk 数 × 21 ms`；瓶颈是下载向量响应体而非 TPM；含三靶场基准与并发安全边界 |
| `targets-benchmark.md` | **耗时基准靶场登记**：`benchmark/{leveldb,HelloAgents,langchain}`（三档规模，2026-09-15 起） |
| `results/phase1-baseline.md` / `phase2-bakeoff.md` / `index-performance-w6.md` / `robustness-scale.md` | 整理过的历史结论：Phase 1 基线、embedding 选型（D-44 依据）、索引性能、规模与健壮性。旧机器产出，**与当前靶场不可比**，仅作决策依据留档 |
| 旧靶场的 `raw-*` 报告 | 已于 2026-09-14 删除（历史见 git） |
