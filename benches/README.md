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
