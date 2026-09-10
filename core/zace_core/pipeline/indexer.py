"""索引流水线：``ChangeSet`` → 增量失效 → 向量对账（TASK-007）。

设计依据：``docs/design/Module/01-切片存储.md`` §4.1（双层增量）、§4.2（配置指纹与分层失效）、
§4.3（时序）；实现期口径：``docs/plan/contracts.md`` §3.2 R1（``.h`` 仓库级抬升）、
R4（``FileDelta`` 三集合）、R8（imports 边缘）、R10（向量相似度/rebuild 语义）。

职责与边界：

- **唯一索引入口**：``Indexer.ingest(changes)`` 是 CLI（TASK-013）与 Phase 2 service 上传共用的
  同步索引路径；job 表/进度上报/并发 worker 池都不在本卡（Phase 2 / Module/01 §4.3）。
- **消费而非重写**：解析走 ``parsing.registry``，切块走 TASK-006 ``split_file``/``embedding_text``，
  二阶段解析与 spec 引用走 TASK-006 ``resolve_pending``/``retry_failed``/``resolve_edges``/
  ``link_spec_references``，入库走 TASK-001 ``Store``，向量走 TASK-009 ``VectorStore``；
  索引侧 embedding 一律 ``embed()``（passage），不得用 ``embed_query()``（R2）。
- **语言识别（R1）**：本卡是唯一知道"仓库文件集"的地方。若仓库已见任意 C++ 扩展名文件
  （本次变更集 ∪ 已索引语言 ∪ 全量扫描清单），``.h`` 按 ``cpp`` 解析；registry 不改。
  V1 已知限制（R1）：先索引 ``.h`` 后出现 ``.cpp`` 时，旧 ``.h`` 要等它下次变更才重解析。
- **三档执行**（``check_fingerprint`` 驱动，D-07）：
  ``none`` → 常规增量（只嵌 ``FileDelta.new``）；``reembed`` → 重建向量表并重嵌**存量** chunk
  （不写 SQLite）；``full_reparse`` → 遍历 provider 全部文件重跑增量 + 重建向量表。
- **向量清理**：``FileDelta.removed_chunk_ids`` 直接删；整文件删除用 Indexer 进程内记录过的
  chunk id 清理（见 ``orphan_files`` 与执行记录"未决问题"：``Store`` 目前没有"按文件列 chunk id"
  或"``apply_deletions`` 返回被删 id"的原语，跨进程删除会留孤儿向量——检索侧会跳过、下一次全量
  重建清理）。
- 单项目串行：不做并发（跨项目并行属 service 层职责）。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from zace_core.chunking import (
    IndexFingerprint,
    Invalidation,
    check_fingerprint,
    embedding_text,
    link_spec_references,
    resolve_edges,
    resolve_pending,
    retry_failed,
    split_file,
    stored_fingerprint,
    write_fingerprint,
)
from zace_core.hashing import file_content_hash
from zace_core.interfaces import EmbeddingProvider
from zace_core.parsing.registry import EXTENSION_LANGUAGE, detect_language, get_parser
from zace_core.pipeline.source import SourceProvider
from zace_core.storage import Store
from zace_core.types import ChangeSet, ChunkDef, ParsedFile, VectorRow
from zace_core.vectors import VectorStore

__all__ = ["CPP_EXTENSIONS", "H_EXTENSION", "LANGUAGES_KEY", "Indexer", "IngestReport"]

#: ``index_config`` 中记录"仓库已见语言集合"的键（R1 抬升的持久化依据）。
LANGUAGES_KEY = "indexed_languages"
#: C/C++ 歧义扩展名（R1 抬升目标）。
H_EXTENSION = ".h"
#: C++ 扩展名集合：取自 registry（含任务卡 R1 清单的全部项，外加注册表里的 ``.c++``/``.h++``）。
CPP_EXTENSIONS = frozenset(
    extension for extension, language in EXTENSION_LANGUAGE.items() if language == "cpp"
)


@dataclass(frozen=True, slots=True)
class IngestReport:
    """一次 ``ingest`` 的结果（TASK-013 日志 / Phase 2 进度上报的字段来源）。

    前 8 个字段是任务卡规定的口径；其余为流水线自证与观测所需（本卡执行记录同步记录）。
    """

    added: int = 0                # 本次按 added 处理并写入的文件数
    modified: int = 0             # 本次按 modified 处理并写入的文件数
    deleted: int = 0              # 本次删除的文件数
    chunks_new: int = 0           # 新写入且 hash 变化、需要嵌入的 chunk 数
    chunks_reused: int = 0        # content_hash 未变、向量可复用的 chunk 数
    chunks_removed: int = 0       # 行被移除（需要删向量）的 chunk 数
    unresolved_resolved: int = 0  # 本次落边的 unresolved 引用条数
    errors: tuple[str, ...] = ()  # 解析/读取失败（不中断整体 ingest）
    invalidation: Invalidation = Invalidation.NONE  # 本次执行的失效层级（D-07）
    files_parsed: int = 0         # 实际解析（含兜底切分）的文件数
    vectors_upserted: int = 0     # 写入/覆盖的向量行数
    vectors_deleted: int = 0      # 删除的向量行数
    edges_retargeted: int = 0     # 裸名边 fqn 化成功行数
    spec_refs: int = 0            # 新写入的 spec_references 行数
    ambiguous_refs: int = 0       # 多义引用条数（全连 / 裸名边未定）
    skipped_files: tuple[str, ...] = ()     # 二进制/不可解码而跳过的文件
    orphan_files: tuple[str, ...] = ()      # 删除时无法枚举 chunk id（向量可能残留）的文件
    languages: tuple[str, ...] = ()         # 本次处理后仓库已见语言集合（R1 抬升输入）


@dataclass
class _Accumulator:
    """报告累加器（``IngestReport`` 保持 frozen，便于下游安全传递）。"""

    added: int = 0
    modified: int = 0
    deleted: int = 0
    chunks_new: int = 0
    chunks_reused: int = 0
    chunks_removed: int = 0
    unresolved_resolved: int = 0
    invalidation: Invalidation = Invalidation.NONE
    files_parsed: int = 0
    vectors_upserted: int = 0
    vectors_deleted: int = 0
    edges_retargeted: int = 0
    spec_refs: int = 0
    ambiguous_refs: int = 0
    errors: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    orphan_files: list[str] = field(default_factory=list)
    languages: tuple[str, ...] = ()

    def report(self) -> IngestReport:
        return IngestReport(
            added=self.added,
            modified=self.modified,
            deleted=self.deleted,
            chunks_new=self.chunks_new,
            chunks_reused=self.chunks_reused,
            chunks_removed=self.chunks_removed,
            unresolved_resolved=self.unresolved_resolved,
            errors=tuple(self.errors),
            invalidation=self.invalidation,
            files_parsed=self.files_parsed,
            vectors_upserted=self.vectors_upserted,
            vectors_deleted=self.vectors_deleted,
            edges_retargeted=self.edges_retargeted,
            spec_refs=self.spec_refs,
            ambiguous_refs=self.ambiguous_refs,
            skipped_files=tuple(self.skipped_files),
            orphan_files=tuple(self.orphan_files),
            languages=self.languages,
        )


@dataclass(frozen=True, slots=True)
class _Input:
    """一个待索引文件（``kind`` 只影响报告计数）。"""

    path: str
    data: bytes
    kind: str  # "added" / "modified"


@dataclass(frozen=True, slots=True)
class _Indexed:
    """单文件索引结果（供后续二阶段解析与向量阶段复用）。"""

    parsed: ParsedFile
    chunks: tuple[ChunkDef, ...]
    new_ids: tuple[str, ...]
    removed_ids: tuple[str, ...]


class Indexer:
    """把变更集变成索引更新的同步流水线（per-project 单写者）。"""

    def __init__(
        self,
        store: Store,
        embedding: EmbeddingProvider,
        vectors: VectorStore,
        source: SourceProvider,
    ) -> None:
        self._store = store
        self._embedding = embedding
        self._vectors = vectors
        self._source = source
        self._languages = _load_languages(store)
        #: path → 本进程写入过的 chunk id（整文件删除时清向量；见模块 docstring 的边界说明）
        self._known_chunks: dict[str, tuple[str, ...]] = {}

    # ------------------------------------------------------------------ 对外

    @property
    def languages(self) -> tuple[str, ...]:
        """仓库已见语言集合（R1 抬升输入）。"""
        return tuple(sorted(self._languages))

    def fingerprint(self) -> IndexFingerprint:
        return IndexFingerprint.build(self._embedding.profile)

    def ingest(self, changes: ChangeSet) -> IngestReport:
        """按配置指纹决定执行档位并完成一次索引（唯一入口）。"""
        invalidation = check_fingerprint(self._store, self.fingerprint())
        if invalidation is Invalidation.FULL_REPARSE:
            return self.full_reparse(changes)
        if invalidation is Invalidation.REEMBED:
            return self.reembed(changes)
        return self._run(changes, Invalidation.NONE)

    def full_reparse(self, changes: ChangeSet | None = None) -> IngestReport:
        """指纹一级失效：遍历 provider 全部文件重跑增量 + 重建向量表。"""
        return self._run(changes or ChangeSet(), Invalidation.FULL_REPARSE)

    def reembed(self, changes: ChangeSet | None = None) -> IngestReport:
        """指纹二级失效：只重建向量（SQLite 索引原样）。"""
        return self._run(changes or ChangeSet(), Invalidation.REEMBED)

    # ------------------------------------------------------------------ 主流程

    def _run(self, changes: ChangeSet, invalidation: Invalidation) -> IngestReport:
        acc = _Accumulator(invalidation=invalidation)
        rebuild_vectors = invalidation is not Invalidation.NONE
        deleted = set(changes.deleted)

        if deleted:
            self._delete_files(sorted(deleted), acc)

        inputs = self._collect_inputs(changes, invalidation, deleted, acc)
        repo_languages = self._languages | {
            language
            for language in (detect_language(item.path) for item in inputs)
            if language is not None
        }
        repo_is_cpp = "cpp" in repo_languages

        indexed: list[_Indexed] = []
        for item in inputs:
            result = self._index_file(item, repo_is_cpp, acc)
            if result is not None:
                indexed.append(result)

        parsed_files = [result.parsed for result in indexed]
        written: dict[str, ChunkDef] = {}
        for result in indexed:
            for chunk in result.chunks:
                written.setdefault(chunk.id, chunk)
            acc.chunks_reused += len(result.chunks) - len(result.new_ids)

        if rebuild_vectors:
            self._rebuild_vectors(acc, written, {result.parsed.path for result in indexed})
        else:
            self._embed_new(acc, indexed)
            removed_ids = [
                chunk_id for result in indexed for chunk_id in result.removed_ids
            ]
            if removed_ids:
                acc.vectors_deleted += self._vectors.delete(removed_ids)

        self._resolve(acc, parsed_files)
        self._languages = repo_languages | {
            result.parsed.language for result in indexed if result.parsed.language
        }
        self._store.set_config(LANGUAGES_KEY, json.dumps(sorted(self._languages)))
        acc.languages = tuple(sorted(self._languages))
        if rebuild_vectors or stored_fingerprint(self._store) is None:
            write_fingerprint(self._store, self.fingerprint())
        return acc.report()

    # ------------------------------------------------------------------ 输入

    def _collect_inputs(
        self, changes: ChangeSet, invalidation: Invalidation, deleted: set[str], acc: _Accumulator
    ) -> list[_Input]:
        """待处理文件清单：全量模式先铺 provider 清单，再叠加变更集（同路径以变更集为准）。"""
        items: dict[str, _Input] = {}
        if invalidation is Invalidation.FULL_REPARSE:
            for path in self._source.list_files():
                if path in deleted:
                    continue
                try:
                    data = self._source.read(path)
                except OSError as exc:  # 扫描期读失败不中断整体 ingest
                    acc.errors.append(f"{path}: {type(exc).__name__}: {exc}")
                    continue
                items[path] = _Input(path=path, data=data, kind="modified")
        for blob in changes.added:
            items[blob.path] = _Input(path=blob.path, data=blob.content, kind="added")
        for blob in changes.modified:
            items[blob.path] = _Input(path=blob.path, data=blob.content, kind="modified")
        return [items[path] for path in sorted(items)]

    def _index_file(self, item: _Input, repo_is_cpp: bool, acc: _Accumulator) -> _Indexed | None:
        text = _decode(item.data)
        if text is None:
            acc.skipped_files.append(item.path)
            return None
        language = _language_for(item.path, repo_is_cpp)
        parsed = self._parse(item.path, text, language, acc)
        chunks = tuple(split_file(parsed, text))
        delta = self._store.apply_file_change(parsed, chunks, file_content_hash(item.data))
        if item.kind == "added":
            acc.added += 1
        else:
            acc.modified += 1
        acc.files_parsed += 1
        acc.chunks_new += len(delta.new_chunk_ids)
        acc.chunks_removed += len(delta.removed_chunk_ids)
        self._known_chunks[item.path] = tuple(chunk.id for chunk in chunks)
        return _Indexed(
            parsed=parsed,
            chunks=chunks,
            new_ids=tuple(delta.new_chunk_ids),
            removed_ids=tuple(delta.removed_chunk_ids),
        )

    def _parse(
        self, path: str, text: str, language: str | None, acc: _Accumulator
    ) -> ParsedFile:
        """解析单文件：未知语言或抽取器不可用 → 兜底 ``ParsedFile``（不中断 ingest）。"""
        if language is None:
            return ParsedFile(path=path, language="fallback", fallback=True)
        try:
            parser = get_parser(language)
            parsed = parser.parse(path, text)
        except Exception as exc:  # ParserUnavailableError / 抽取器缺陷
            acc.errors.append(f"{path}: {type(exc).__name__}: {exc}")
            return ParsedFile(
                path=path,
                language=language,
                parse_errors=(f"{type(exc).__name__}: {exc}",),
                fallback=True,
            )
        if parsed.parse_errors:
            acc.errors.append(f"{path}: " + "; ".join(parsed.parse_errors))
        return parsed

    # ------------------------------------------------------------------ 删除

    def _delete_files(self, paths: Sequence[str], acc: _Accumulator) -> None:
        chunk_ids: list[str] = []
        for path in paths:
            known = self._known_chunks.pop(path, None)
            if known is None:
                acc.orphan_files.append(path)
            else:
                chunk_ids.extend(known)
        self._store.apply_deletions(list(paths))
        acc.deleted += len(paths)
        if chunk_ids:
            acc.vectors_deleted += self._vectors.delete(chunk_ids)

    # ------------------------------------------------------------------ 向量

    def _embed_new(self, acc: _Accumulator, indexed: Sequence[_Indexed]) -> None:
        """增量嵌入：只嵌需要向量的 chunk。

        判据是「向量库里该 chunk_id 的 content_hash 是否已是本次的 hash」：
        hash 变化 → 嵌；本轮新出现的 id（行号漂移导致，见 D-04）→ 向量库里没有该 id → 也嵌。
        后者是对 R4 "复用键是 hash 不是 id" 的落地细节：TASK-009 的 ``VectorStore`` 按 chunk_id
        存行、没有读回向量的原语，所以"同一 hash 换了 id"只能重嵌（代价一次性，已记入执行记录）。
        """
        candidates: dict[str, ChunkDef] = {}
        for result in indexed:
            for chunk in result.chunks:
                candidates.setdefault(chunk.id, chunk)
        if not candidates:
            return
        stored = self._vectors.get_hashes(list(candidates))
        pending = [
            chunk
            for chunk_id, chunk in candidates.items()
            if stored.get(chunk_id) != chunk.content_hash
        ]
        self._embed_and_upsert(pending, acc)

    def _rebuild_vectors(
        self, acc: _Accumulator, written: dict[str, ChunkDef], processed: set[str]
    ) -> None:
        """重建向量表并重嵌全部存量 chunk（reembed / full_reparse）。

        存量枚举方式：遍历 provider 清单重新解析切分拿到 chunk id（**不写 SQLite**），
        再用 ``Store.chunks_by_ids`` 取回库内权威内容后嵌入——解析口径未变是
        ``reembed`` 档位的前提（指纹保证），因此 id 与库内一致。
        """
        profile_dim = self._embedding.profile.dim
        self._vectors.rebuild(profile_dim)
        ids: list[str] = list(written)
        for path in self._source.list_files():
            if path in processed:
                continue
            try:
                data = self._source.read(path)
            except OSError as exc:
                acc.errors.append(f"{path}: {type(exc).__name__}: {exc}")
                continue
            text = _decode(data)
            if text is None:
                continue
            language = _language_for(path, "cpp" in self._languages)
            parsed = self._parse(path, text, language, acc)
            ids.extend(chunk.id for chunk in split_file(parsed, text))
        stored = self._store.chunks_by_ids(ids)
        self._embed_and_upsert(list(stored), acc)

    def _embed_and_upsert(self, chunks: Sequence[ChunkDef], acc: _Accumulator) -> None:
        pending = list(dict.fromkeys(chunk.id for chunk in chunks))
        by_id = {chunk.id: chunk for chunk in chunks}
        ordered = [by_id[chunk_id] for chunk_id in pending]
        if not ordered:
            return
        vectors = self._embedding.embed([embedding_text(chunk) for chunk in ordered])
        if len(vectors) != len(ordered):
            raise RuntimeError(
                f"embedding 返回行数不匹配：期望 {len(ordered)}，实际 {len(vectors)}"
            )
        rows = [
            VectorRow(chunk_id=chunk.id, content_hash=chunk.content_hash, vector=list(vector))
            for chunk, vector in zip(ordered, vectors, strict=True)
        ]
        acc.vectors_upserted += self._vectors.upsert(rows)

    # ------------------------------------------------------------------ 二阶段解析

    def _resolve(self, acc: _Accumulator, parsed_files: Sequence[ParsedFile]) -> None:
        pending = resolve_pending(self._store)
        names = [
            symbol.name for parsed in parsed_files for symbol in parsed.symbols
        ] + [symbol.fqn for parsed in parsed_files for symbol in parsed.symbols]
        retried = retry_failed(self._store, names) if names else None
        edges = resolve_edges(self._store)
        specs = link_spec_references(self._store, parsed_files)

        acc.unresolved_resolved += pending.resolved
        if retried is not None:
            acc.unresolved_resolved += retried.resolved
        acc.edges_retargeted += edges.edges_retargeted
        acc.spec_refs += specs.spec_refs
        acc.ambiguous_refs += len(pending.ambiguous) + len(edges.ambiguous)
        if retried is not None:
            acc.ambiguous_refs += len(retried.ambiguous)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _decode(data: bytes) -> str | None:
    """字节 → 文本；二进制（含 NUL）返回 None（跳过，不产兜底块）。"""
    if b"\x00" in data:
        return None
    return data.decode("utf-8", errors="replace")


def _language_for(path: str, repo_is_cpp: bool) -> str | None:
    """语言识别 + R1 仓库级抬升：C++ 仓库里 ``.h`` 按 ``cpp`` 解析。"""
    if repo_is_cpp and path.lower().endswith(H_EXTENSION):
        return "cpp"
    return detect_language(path)


def _load_languages(store: Store) -> set[str]:
    raw = store.get_config(LANGUAGES_KEY)
    if not raw:
        return set()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(parsed, list):
        return set()
    return {str(item) for item in parsed}
