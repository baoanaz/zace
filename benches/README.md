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

## 运行

```bash
uv run zace-core eval --golden benches/golden --repo <本地仓库路径> --report benches/results/<name>.md
uv run python benches/bakeoff/embed_compare.py --help   # TASK-015 交付
```
