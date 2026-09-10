"""索引流水线：首次 / 增量 / 删除 / 幂等 / 指纹 / 解析失败 / R1 抬升（TASK-007）。

DoD 覆盖：首次 ingest 行数、改 1 个函数只嵌 1 个 chunk、改注释 0 次嵌入、删文件清向量与
spec 引用 stale、同变更集二次 ingest 零成本、指纹两档失效、语法错误不中断 ingest。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from zace_core.chunking import PARSER_CONFIG_KEY, embedding_text, split_file
from zace_core.interfaces import EmbeddingProfile
from zace_core.parsing.registry import get_parser
from zace_core.pipeline import LANGUAGES_KEY, DirectorySource, Indexer, IngestReport
from zace_core.storage import Store
from zace_core.text import segment
from zace_core.types import ChangeSet, ParsedFile
from zace_core.vectors import VectorStore

from .conftest import DOC_MD, PY_MODULE, TEST_PROFILE, CountingEmbedding, write_repo

ChangeSetFactory = Callable[..., ChangeSet]


def _parse(path: str, source: str) -> ParsedFile:
    language = path.rsplit(".", 1)[-1]
    parser_language = {"py": "python", "md": "markdown", "c": "c", "cpp": "cpp", "h": "c"}[
        language
    ]
    return get_parser(parser_language).parse(path, source)


def _chunk_count(path: str, source: str) -> int:
    return len(split_file(_parse(path, source), source))


def _ingest_files(
    indexer: Indexer, changes: ChangeSetFactory, files: dict[str, str], repo: Path | None = None
) -> IngestReport:
    """写盘 + 按变更集索引（磁盘副本是全量重解析/reembed 的输入，贴近 CLI 真实形态）。"""
    if repo is not None:
        write_repo(repo, files)
    return indexer.ingest(changes(added=files))


# ---------------------------------------------------------------------------
# 首次 ingest
# ---------------------------------------------------------------------------


def test_first_ingest_populates_all_indexes(
    indexer: Indexer,
    change_set: ChangeSetFactory,
    store: Store,
    vectors: VectorStore,
    repo: Path,
) -> None:
    report = _ingest_files(
        indexer, change_set, {"pkg/mod.py": PY_MODULE, "docs/design.md": DOC_MD}, repo
    )
    expected_chunks = _chunk_count("pkg/mod.py", PY_MODULE) + _chunk_count(
        "docs/design.md", DOC_MD
    )
    counts = store.counts()

    assert (report.added, report.modified, report.deleted) == (2, 0, 0)
    assert report.files_parsed == 2
    assert counts["files"] == 2
    assert counts["chunks"] == expected_chunks
    assert report.chunks_new == counts["chunks"]
    assert report.chunks_reused == 0
    assert vectors.count() == counts["chunks"]
    assert report.vectors_upserted == counts["chunks"]
    # FTS 可检索（jieba 预分词 + 中文/标识符混合）
    assert store.fts_search(segment("helper"))
    assert store.fts_search(segment("设计"))
    # 二阶段解析：Service.run 里的裸名调用 helper 已 fqn 化
    assert any(edge.target == "helper" for edge in store.edges_for("Service.run"))
    # spec_references 已从 markdown 的 mentioned 建立
    assert report.spec_refs > 0
    assert counts["edges"] > 0


def test_languages_are_persisted_for_repo_level_uplift(
    indexer: Indexer, change_set: ChangeSetFactory, store: Store
) -> None:
    report = _ingest_files(indexer, change_set, {"pkg/mod.py": PY_MODULE})

    assert report.languages == ("python",)
    assert indexer.languages == ("python",)
    assert store.get_config(LANGUAGES_KEY) == '["python"]'


# ---------------------------------------------------------------------------
# 增量
# ---------------------------------------------------------------------------


def test_changing_one_function_embeds_exactly_one_chunk(
    indexer: Indexer,
    change_set: ChangeSetFactory,
    embedding: CountingEmbedding,
    store: Store,
    vectors: VectorStore,
) -> None:
    _ingest_files(indexer, change_set, {"pkg/mod.py": PY_MODULE})
    before_calls = embedding.calls

    updated = PY_MODULE.replace("return value + 1", "return value + 2")
    report = indexer.ingest(change_set(modified={"pkg/mod.py": updated}))

    assert report.chunks_new == 1
    assert report.chunks_reused > 0
    assert embedding.calls == before_calls + 1
    assert len(embedding.batches[-1]) == 1
    assert "value + 2" in embedding.batches[-1][0]
    assert vectors.count() == store.counts()["chunks"]


def test_comment_change_outside_any_chunk_costs_zero_embeddings(
    indexer: Indexer,
    change_set: ChangeSetFactory,
    embedding: CountingEmbedding,
    store: Store,
) -> None:
    """注释落在类级空隙（不属于任何 chunk 区间）→ 文件 hash 变但零嵌入。"""
    source = "class C:\n    def m(self): return 1\n    # note v1\n    def n(self): return 2\n"
    _ingest_files(indexer, change_set, {"pkg/c.py": source})
    before = (embedding.calls, dict(store.counts()))

    report = indexer.ingest(change_set(modified={"pkg/c.py": source.replace("v1", "v2")}))

    assert report.chunks_new == 0
    assert embedding.calls == before[0]
    assert dict(store.counts()) == before[1]


def test_removing_a_function_deletes_its_vector_without_embedding(
    indexer: Indexer,
    change_set: ChangeSetFactory,
    embedding: CountingEmbedding,
    store: Store,
    vectors: VectorStore,
) -> None:
    _ingest_files(indexer, change_set, {"pkg/mod.py": PY_MODULE})
    helper_id = next(
        chunk.id
        for chunk in split_file(_parse("pkg/mod.py", PY_MODULE), PY_MODULE)
        if chunk.symbol_fqn == "helper"
    )
    assert vectors.get_hashes([helper_id])

    helper = '''def helper(value: int) -> int:
    """返回 +1。"""
    return value + 1


'''
    report = indexer.ingest(change_set(modified={"pkg/mod.py": PY_MODULE.replace(helper, "")}))

    # 内容没有变化，只是 helper 消失 + 后续 chunk 行号漂移（D-04：id 含 start_line）
    assert report.chunks_new == 0
    assert report.chunks_removed == 3
    assert report.vectors_deleted == 3
    assert vectors.get_hashes([helper_id]) == {}  # 该 chunk 的向量已删
    assert vectors.count() == store.counts()["chunks"]
    assert embedding.calls > 0  # 漂移后的新 id 需要重建向量（见执行记录的口径说明）


def test_repeated_change_set_is_idempotent(
    indexer: Indexer,
    change_set: ChangeSetFactory,
    embedding: CountingEmbedding,
    store: Store,
    vectors: VectorStore,
) -> None:
    changes = change_set(added={"pkg/mod.py": PY_MODULE, "docs/design.md": DOC_MD})
    indexer.ingest(changes)
    before_counts = dict(store.counts())
    before_calls = embedding.calls
    before_vectors = vectors.count()

    report = indexer.ingest(changes)

    assert report.chunks_new == 0
    assert report.chunks_reused == before_counts["chunks"]
    assert embedding.calls == before_calls
    assert dict(store.counts()) == before_counts
    assert vectors.count() == before_vectors


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------


def test_delete_file_clears_rows_vectors_and_marks_spec_refs_stale(
    indexer: Indexer,
    change_set: ChangeSetFactory,
    store: Store,
    vectors: VectorStore,
) -> None:
    _ingest_files(indexer, change_set, {"pkg/mod.py": PY_MODULE, "docs/design.md": DOC_MD})
    block = _parse("docs/design.md", DOC_MD).spec_blocks[0]
    spec_block_id = f"docs/design.md:{block.heading_path}:{block.start_line}"
    assert any(not row.stale for row in store.spec_refs_for_spec(spec_block_id))

    report = indexer.ingest(change_set(deleted=["pkg/mod.py"]))

    counts = store.counts()
    assert (report.deleted, counts["files"]) == (1, 1)
    assert counts["symbols"] == 0  # 只剩 markdown（无符号行）
    assert report.vectors_deleted > 0
    assert vectors.count() == counts["chunks"]
    # 被删符号的 spec 引用置 stale=1（行保留，供 MissingEvidence 警告）
    assert all(row.stale for row in store.spec_refs_for_spec(spec_block_id))
    # 代码文件的 FTS 行已清，残留命中均来自 markdown 文档
    assert all(hit.startswith("docs/design.md") for hit, _ in store.fts_search(segment("helper")))
    assert store.chunk_by_id("pkg/mod.py:Service:16") is None


def test_delete_unknown_file_reports_orphans(
    indexer: Indexer, change_set: ChangeSetFactory
) -> None:
    """本进程未见过该文件的 chunk id → 记入 orphan_files（诚实标注，不假装清干净）。"""
    report = indexer.ingest(change_set(deleted=["not/indexed.py"]))

    assert report.deleted == 1
    assert report.orphan_files == ("not/indexed.py",)


# ---------------------------------------------------------------------------
# 配置指纹（D-07）
# ---------------------------------------------------------------------------


def test_tampered_parser_hash_triggers_full_reparse(
    indexer: Indexer,
    change_set: ChangeSetFactory,
    store: Store,
    vectors: VectorStore,
    repo: Path,
) -> None:
    _ingest_files(
        indexer, change_set, {"pkg/mod.py": PY_MODULE, "docs/design.md": DOC_MD}, repo
    )
    store.set_config(PARSER_CONFIG_KEY, "tampered")

    report = indexer.ingest(ChangeSet())

    assert report.invalidation.value == "full_reparse"
    assert report.files_parsed == 2  # 遍历 provider 全量
    assert vectors.count() == store.counts()["chunks"]
    # 指纹已刷新 → 紧接的增量不再全量
    assert indexer.ingest(ChangeSet()).invalidation.value == "none"


def test_embedding_profile_change_only_reembeds(
    store: Store, repo: Path, change_set: ChangeSetFactory
) -> None:
    vectors = VectorStore.open(store.project_dir, dim=TEST_PROFILE.dim)
    try:
        indexer = Indexer(store, CountingEmbedding(), vectors, DirectorySource(repo))
        _ingest_files(
            indexer, change_set, {"pkg/mod.py": PY_MODULE, "docs/design.md": DOC_MD}, repo
        )
        counts_before = dict(store.counts())

        switched = CountingEmbedding(
            EmbeddingProfile(model_id="local:other", dim=TEST_PROFILE.dim, max_input_tokens=512)
        )
        reporter = Indexer(store, switched, vectors, DirectorySource(repo))
        report = reporter.ingest(ChangeSet())

        assert report.invalidation.value == "reembed"
        assert report.files_parsed == 0  # 不重解析、不写 SQLite
        assert dict(store.counts()) == counts_before
        assert switched.calls == 1
        assert report.vectors_upserted == counts_before["chunks"]
        assert vectors.count() == counts_before["chunks"]
        # 指纹已对齐 → 常规增量
        assert reporter.ingest(ChangeSet()).invalidation.value == "none"
    finally:
        vectors.close()


def test_reembed_does_not_write_sqlite_rows(
    store: Store,
    repo: Path,
    change_set: ChangeSetFactory,
    embedding: CountingEmbedding,
    vectors: VectorStore,
) -> None:
    indexer = Indexer(store, embedding, vectors, DirectorySource(repo))
    _ingest_files(indexer, change_set, {"pkg/mod.py": PY_MODULE}, repo)
    counts_before = dict(store.counts())

    report = indexer.reembed()

    assert report.invalidation.value == "reembed"
    assert dict(store.counts()) == counts_before
    assert report.vectors_upserted == counts_before["chunks"]


# ---------------------------------------------------------------------------
# 解析失败与语言抬升（R1）
# ---------------------------------------------------------------------------


def test_syntax_error_does_not_abort_ingest(
    indexer: Indexer, change_set: ChangeSetFactory, store: Store
) -> None:
    broken = "def broken(:\n    pass\n"
    report = indexer.ingest(
        change_set(added={"pkg/broken.py": broken, "pkg/mod.py": PY_MODULE})
    )

    assert report.errors and report.errors[0].startswith("pkg/broken.py")
    assert report.added == 2
    assert store.chunk_by_id("pkg/broken.py:(module):1") is not None
    assert store.counts()["symbols"] > 0  # 另一个文件照常入库


def test_binary_files_are_skipped(
    indexer: Indexer, change_set: ChangeSetFactory, store: Store
) -> None:
    report = indexer.ingest(
        change_set(added={"assets/logo.bin": "\x00\x01\x02", "pkg/mod.py": PY_MODULE})
    )

    assert report.skipped_files == ("assets/logo.bin",)
    assert report.added == 1
    assert store.counts()["files"] == 1


CPP_SOURCE = """class Vec {
public:
    int size() const;
};

int Vec::size() const {
    return 1;
}
"""

HEADER_SOURCE = """#pragma once

class Widget {
public:
    int size() const { return 1; }
};
"""


def test_h_files_follow_repo_language(
    indexer: Indexer, change_set: ChangeSetFactory, store: Store
) -> None:
    """R1：仓库出现 C++ 扩展名后，``.h`` 按 C++ 解析。"""
    header = "include/widget.h"
    indexer.ingest(change_set(added={header: HEADER_SOURCE}))
    assert store.exact_symbols("size") == []  # 仅 .h 的 C 仓库：C 抽取器不认类方法

    report = indexer.ingest(
        change_set(added={"src/vec.cpp": CPP_SOURCE}, modified={header: HEADER_SOURCE})
    )

    assert "cpp" in report.languages
    fqns = {row.fqn for row in store.exact_symbols("size")}
    assert "Widget::size" in fqns  # .h 已按 C++ 解析
    assert "Vec::size" in fqns
    assert report.invalidation.value == "none"


def test_c_only_repo_keeps_h_as_c(
    indexer: Indexer, change_set: ChangeSetFactory
) -> None:
    report = indexer.ingest(change_set(added={"src/a.c": "int add(int a) { return a; }\n"}))

    assert report.languages == ("c",)
    assert indexer.languages == ("c",)


# ---------------------------------------------------------------------------
# 输入边界
# ---------------------------------------------------------------------------


def test_change_set_blob_does_not_need_disk_file(
    indexer: Indexer, change_set: ChangeSetFactory, store: Store, repo: Path
) -> None:
    """Phase 2 service 形态：内容来自上传的 blob，磁盘上没有该文件。"""
    report = indexer.ingest(change_set(added={"virtual/mod.py": PY_MODULE}))

    assert report.added == 1
    assert store.counts()["files"] == 1
    assert not (repo / "virtual/mod.py").exists()


def test_directory_source_lists_and_reads_repo_files(repo: Path) -> None:
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (repo / ".venv").mkdir()
    (repo / ".venv" / "junk.py").write_text("junk\n", encoding="utf-8")
    source = DirectorySource(repo)

    assert source.list_files() == ("src/a.py",)
    assert source.read("src/a.py") == b"x = 1\n"
    with pytest.raises(Exception, match="非法仓库相对路径"):
        source.read("../outside.py")


def test_embedding_inputs_match_embedding_text(
    indexer: Indexer, change_set: ChangeSetFactory, embedding: CountingEmbedding
) -> None:
    """索引侧 embedding 输入 = ``embedding_text(chunk)``，且一律走 ``embed()``（R2）。"""
    _ingest_files(indexer, change_set, {"pkg/mod.py": PY_MODULE})
    expected = {
        embedding_text(chunk) for chunk in split_file(_parse("pkg/mod.py", PY_MODULE), PY_MODULE)
    }

    assert set(embedding.texts) == expected
    assert any("def helper" in text for text in embedding.texts)
    assert any("class Service" in text for text in embedding.texts)
