# TASK-009：向量存储（LanceDB）+ hash 复用对账

> 状态：pending ｜ 阶段：Phase 1 ｜ 硬依赖：无 ｜ soft 依赖：无
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

- [ ] `uv run pytest core/tests/vectors -q` 全绿（临时目录，dim=8 的随机向量即可），必须覆盖：
  - upsert → search 结果顺序正确（构造可判定的向量关系）；
  - 幂等：同一 chunk_id 再 upsert → 只有一条记录、向量被覆盖；
  - delete 后 search 不再返回；
  - `get_hashes` 命中/未命中；
  - `rebuild(dim=16)` 后旧数据不可见且可写入新维度；维度不匹配错误路径有测试；
  - 空库 search → `[]`。
- [ ] 规模冒烟（`@pytest.mark.slow`，不进 CI 默认集）：10k 行 dim=384 upsert + 10 次查询，记录耗时。
- [ ] 基线三条命令全绿。

## 参考源码锚点（只读）

- `source/ragcode/src/semantic/` + `source/ragcode/src/indexing/`（LanceDB 表管理与 generation 重建）
- `source/GitNexus/gitnexus/src`（向量层与 FTS 的协作方式）

## 明确不做

- 不做 embedding 计算（TASK-008）；不做跨项目共享向量；不做 ANN 索引参数调优（数据量上来后另立卡）。

## 完成报告（回填）

按 `docs/plan/orchestration.md` §3 模板填写。

## 执行记录

（实施 AI 在此填写。LanceDB 版本、表 API 的实际语义差异与最终口径必须记录。）
