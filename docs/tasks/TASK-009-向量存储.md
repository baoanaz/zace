# TASK-009：向量存储（LanceDB）+ hash 复用对账

> 状态：done ｜ 阶段：Phase 1 ｜ 硬依赖：无 ｜ soft 依赖：无
> 建议分支：`feature/task-009_<你的缩写><MMDD>`
> 交付物所有权：`core/zace_core/vectors/`、`core/tests/vectors/`

## 目标

交付 per-project 向量存储：`chunk_vectors(chunk_id, content_hash, vector)` 的建表/写入/删除/ANN 检索，
以及基于 content_hash 的向量复用对账（D-43：换模型整表重建，换代码只嵌变更 chunk）。

## 输入文档（按序读）

1. `docs/design/Module/01-切片存储.md` §3.1（向量方案对比）、§3.3（vectors/ 目录 + 表设计）、§4.1（增量复用）
2. `core/zace_core/types.py`（`VectorRow` / `VectorHit`）
3. `core/zace_core/interfaces.py`（`EmbeddingProfile`：dim 来自此处）
4. `docs/design/Background/03-ragcode.md`（LanceDB 生产使用与 generation 机制——zace 用 table replace 简化，见 Module/01 §3.3 权衡）

## 交付内容

- `open(project_dir, dim)` / `close()`：`vectors/` 目录下的 LanceDB 库；表不存在则建（固定维度）。
- 写：`upsert(rows: Sequence[VectorRow])`（按 chunk_id 幂等覆盖）；`delete(chunk_ids)`。
- 读：`search(vector: Sequence[float], top_k) -> list[VectorHit]`（余弦，得分越高越相关，返回按分降序）；
  空表/无查询 → 空列表。
- 对账：`get_hashes(chunk_ids) -> dict[str, str]`（TASK-007 判断哪些 chunk 可复用向量）。
- 重建：`rebuild(dim)`（embedding 模型/维度变更时调用）——整表重建的原子替换语义，重建期间旧表可读或明确失败（记录口径）。
- 维度不匹配时报错文案必须给出"触发 D-07 二级失效"的明确指引。

## 交付物（文件所有权）

| 路径 | 内容 |
|---|---|
| `core/zace_core/vectors/__init__.py` | 导出 |
| `core/zace_core/vectors/store.py` | LanceDB 封装实现 |
| `core/tests/vectors/` | 测试 |

## 验收标准（DoD）

- [x] `uv run pytest core/tests/vectors -q` 全绿（临时目录，dim=8 的随机向量即可），必须覆盖：
  - upsert → search 结果顺序正确（构造可判定的向量关系）；
  - 幂等：同一 chunk_id 再 upsert → 只有一条记录、向量被覆盖；
  - delete 后 search 不再返回；
  - `get_hashes` 命中/未命中；
  - `rebuild(dim=16)` 后旧数据不可见且可写入新维度；维度不匹配错误路径有测试；
  - 空库 search → `[]`。
- [x] 规模冒烟（`@pytest.mark.slow`，不进 CI 默认集）：10k 行 dim=384 upsert + 10 次查询，记录耗时。
- [x] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/ragcode/src/semantic/` + `source/ragcode/src/indexing/`（LanceDB 表管理与 generation 重建）
- `source/GitNexus/gitnexus/src`（向量层与 FTS 的协作方式）

## 明确不做

- 不做 embedding 计算（TASK-008）；不做跨项目共享向量；不做 ANN 索引参数调优（数据量上来后另立卡）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

### 2026-09-10 / feature/task-009_xwz0910（泳道 C，本地分支交付，基于 feature/task-005_xwz0910）

**完成报告**

- 分支：`feature/task-009_xwz0910`
- 验收：
  - `uv run pytest core/tests/vectors -q` → 全绿（11 passed, 1 skipped；skipped = 规模冒烟，默认不进基线）；
  - 规模冒烟：`ZACE_RUN_SLOW=1 uv run pytest core/tests/vectors -q -m slow -s` → passed，
    实测 upsert 10k×dim384 = 0.66s，10 次查询 = 0.17s（17 ms/query）；
  - 基线三条：`uv run ruff check .` → All checks passed；
    `uv run python scripts/check_dependency_direction.py` → 通过；`uv run pytest` → 34 passed, 1 skipped。
- 关键产物：`core/zace_core/vectors/store.py`（`VectorStore` / `VectorStoreError` /
  `DimensionMismatchError`）、`core/zace_core/vectors/__init__.py`、
  `core/tests/vectors/{conftest.py,test_store.py}`。
- 契约影响：无。`VectorRow` / `VectorHit` 按冻结定义使用；未动 `types.py` / `interfaces.py` /
  `core/pyproject.toml`（无新增依赖）。
- 与设计偏差：无。`rebuild` 的“原子替换 + 旧表可读或明确失败”按“可用 API 的最简语义”落为：单次
  `create_table(mode="overwrite")` + 句柄立即切换（详下口径表）。
- 未决问题：无。
- 建议复核点：① `rebuild` 口径（OSS 无 `rename_table`，单进程句柄语义）是否接受；② `get_hashes`
  用空查询 + where 而非 `to_lance()`（后者需未预装的 pylance，未自行加依赖）是否接受；
  ③ `search` 返回相似度（`1 - _distance`）而非距离，与 `VectorHit.score` 语义一致。

**LanceDB 版本与 API 语义差异（本卡要求记录）**

- 版本：`lancedb 0.38.0` / `pyarrow 25.0.1`（来自 `core/pyproject.toml` 预置依赖，未自行添加任何依赖）。
- 建表：`create_table(name, schema=..., mode="create"|"overwrite")`；本版本无 `create_empty_table`，
  用 `schema=` 建空表（验证可用）。
- 幂等写：`merge_insert("chunk_id").when_matched_update_all().when_not_matched_insert_all()`；
  同 chunk_id 重复 upsert 后行数不变、向量/hash 被覆盖（测试覆盖）。批量 1024/次。
- 检索：`search(vec, vector_column_name="vector").distance_type("cosine").limit(k).to_list()`；
  结果带 `_distance`（余弦距离，越小越相关），对外 score = `1 - _distance`（降序）。
- 空表检索：原生返回 `[]`（仍保留 `count_rows()==0` 短路）。
- 维度不匹配：底层报错文案为 `Invalid input, query dim(N) doesn't match the column vector vector dim(M)`；
  本层先预检，并将底层同类错误翻译为 `DimensionMismatchError`，文案含“触发 D-07 二级失效”+
  `rebuild(dim)` 与重新嵌入指引（测试断言 `D-07` 字样）。
- 重建：**LanceDB OSS 不支持 `rename_table`**（实测 `NotImplementedError: not supported`），因此不用
  “临时表 + 改名”方案；改用单次 `create_table(mode="overwrite")`（实测：新 schema/新维度、数据为空）。
  口径：重建后旧数据对新句柄不可见（本实例立即切换句柄）；Lance 版本语义下已打开的旧句柄仍可读旧快照；
  跨进程并发不在本层保护范围（per-project 单写者，Module/01 §4.3）。
- 过滤读：`to_lance()` 需要未预装的 `pylance`（`ImportError`）→ 未使用，改为
  `search(None).where("chunk_id IN (...)").select([...]).to_list()`（零新依赖）。
- `db.table_names()` 已废弃（DeprecationWarning）→ 改用 `db.list_tables()`（分页响应对象，已做分页收尾）。
- 表结构：单表 `chunk_vectors`，列 `chunk_id / content_hash / vector(fixed_size_list<float32, dim>)`；
  `vectors/` 目录位于 `project_dir` 下（Module/01 §3.3）。
- slow 标记：`core/tests/vectors/conftest.py` 注册 `slow` 并默认 skip；`ZACE_RUN_SLOW=1` 启用（不引入
  pytest 配置改动，不占用公共文件）。
