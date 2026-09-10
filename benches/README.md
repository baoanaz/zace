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
uv run zace-core eval --golden benches/golden --repo <本地仓库路径> --report benches/results/<name>.md
uv run python benches/bakeoff/embed_compare.py --help   # TASK-015 交付
```

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
4. **zace dogfood 的 R17 免责**：`benches/golden/**` 自身在仓库内且会被索引，任何负例的查询原文都能被
   自身命中（实测：`Category=negative` 的样例题因 `test_cli_eval.py` 的 fixture + `golden/zace/sample.jsonl`
   命中 top-2 而 `answerable=true`）。dogfood 负例只能以“该 query 在 core/ 与 docs/ 中无对应实现”为前提，
   并在报告里注明本次运行的索引是否包含 golden 文件。
5. **语言/类别配额**（Module/02 §7-1 的 golden set 要求）：中文 ≥15、英文 ≥10、中英混合 ≥15；
   类型须覆盖 `symbol` / `path` / `behavior` / `spec` / `negative`；至少 1 条 `negative` 在外部仓库上。
6. **索引可复用，但必须记录索引状态**：`--data` 指向已有 data root 可省去 7-20 分钟重建；
   报告里必须写清“索引来自哪个 commit / 哪个工作区”（`identity_key` 只由 git remote + 相对路径决定，
   **同一 remote 的不同 worktree 共用同一个 project 目录**，lane 之间会互相覆盖，不能凭目录名判断内容）。
