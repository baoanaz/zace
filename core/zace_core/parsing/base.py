"""tree-sitter 解析基座与公共工具（TASK-002 交付物，所有权归泳道 B/解析线）。

基类职责：

- grammar 懒加载（每进程每 grammar 一次）与 Parser 实例复用；
- 语法错误检测：ERROR / MISSING 节点 → 整个文件 ``fallback=True`` + ``parse_errors``
  （诚实优先：宁可不抽，不抽半可信）；
- 公共工具：UTF-8 字节切片取文本、行号、前序遍历；
- 结果收口：去重 + 按行号稳定排序，保证同一输入两次 parse 结果逐字节相等。

子类契约（TASK-003/004/005）：

- 类属性 ``language`` / ``grammar_module``；
- 实现 ``extract(root, ctx, out)``；取原文一律走 ``ctx.text()``
  （tree-sitter 位置按字节计，含中文注释时必须字节切片再解码）；
- 不修改本文件；需要新能力时在各自任务卡"执行记录"里提出，由编排者协调。
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import ClassVar

import tree_sitter as ts

from zace_core.types import EdgeDef, ParsedFile, SymbolDef, UnresolvedRef

#: 单文件最多回报的语法错误条数（防病态文件撑爆 parse_errors）
MAX_PARSE_ERRORS = 20

#: 边/引用名长度上限（避免把整段表达式写进 name）
NAME_LIMIT = 120


@dataclass(frozen=True, slots=True)
class FileContext:
    """单次 parse 的不可变上下文（无共享可变状态，同一 parser 实例可并发使用）。"""

    path: str
    language: str
    source: bytes

    def text(self, node: ts.Node) -> str:
        """取节点原文（source 为 UTF-8 字节，节点位置按字节计）。"""
        return self.source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def line_of(node: ts.Node) -> int:
    """节点起始行（1-based，与 SymbolDef.start_line 口径一致）。"""
    return node.start_point[0] + 1


def end_line_of(node: ts.Node) -> int:
    """节点结束行（1-based，含）。"""
    return node.end_point[0] + 1


def normalize_name(text: str, limit: int = NAME_LIMIT) -> str:
    """把目标名/表达式折叠空白并截断（edge target_name / unresolved name 统一口径）。"""
    collapsed = " ".join(text.split())
    return collapsed[:limit]


def walk(node: ts.Node) -> Iterator[ts.Node]:
    """前序（文档序）遍历 node 及其全部后代，含匿名节点。"""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def collect_parse_errors(
    root: ts.Node, source: bytes, limit: int = MAX_PARSE_ERRORS
) -> list[str]:
    """收集语法错误（ERROR / MISSING 节点），带 1-based 行号与片段。"""
    errors: list[str] = []
    stack = [root]
    while stack and len(errors) < limit:
        node = stack.pop()
        if node.is_missing:
            errors.append(f"L{line_of(node)}: missing {node.type}")
            continue
        if node.is_error:
            snippet = normalize_name(_text(node, source))
            errors.append(f"L{line_of(node)}: syntax error near {snippet!r}")
            continue
        if node.has_error:
            stack.extend(reversed(node.children))
    if len(errors) >= limit:
        errors.append(f"... 错误过多，仅回报前 {limit} 条")
    return errors


def _text(node: ts.Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


@dataclass
class Extraction:
    """抽取中间容器：语言抽取器往里追加，基类统一收口排序/去重。"""

    symbols: list[SymbolDef] = field(default_factory=list)
    edges: list[EdgeDef] = field(default_factory=list)
    unresolved: list[UnresolvedRef] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)

    def add_symbol(self, symbol: SymbolDef) -> None:
        self.symbols.append(symbol)

    def add_edge(
        self,
        source_fqn: str,
        target_name: str,
        kind: str,
        line: int | None = None,
        provenance: str = "parsed",
    ) -> None:
        self.edges.append(
            EdgeDef(
                source_fqn=source_fqn,
                target_name=normalize_name(target_name),
                kind=kind,
                line=line,
                provenance=provenance,
            )
        )

    def add_unresolved(
        self, from_fqn: str, name: str, kind: str, line: int | None = None
    ) -> None:
        self.unresolved.append(
            UnresolvedRef(
                from_fqn=from_fqn, name=normalize_name(name), kind=kind, line=line
            )
        )


class TreeSitterParser:
    """tree-sitter 抽取器基类（Parser 协议实现：parse 永不抛异常）。"""

    #: ParsedFile.language 值（python / c / cpp / markdown）
    language: ClassVar[str] = ""
    #: grammar 包名，如 tree_sitter_python
    grammar_module: ClassVar[str] = ""
    #: grammar 包内取 Language 的函数名
    grammar_function: ClassVar[str] = "language"

    _grammar_cache: ClassVar[dict[str, ts.Language]] = {}

    def __init__(self) -> None:
        self._parser: ts.Parser | None = None

    @classmethod
    def grammar(cls) -> ts.Language:
        cached = TreeSitterParser._grammar_cache.get(cls.grammar_module)
        if cached is None:
            module = importlib.import_module(cls.grammar_module)
            getter = getattr(module, cls.grammar_function)
            cached = ts.Language(getter())
            TreeSitterParser._grammar_cache[cls.grammar_module] = cached
        return cached

    def parser(self) -> ts.Parser:
        if self._parser is None:
            self._parser = ts.Parser(self.grammar())
        return self._parser

    # -- Parser 协议 ---------------------------------------------------------

    def parse(self, path: str, content: str) -> ParsedFile:
        """解析单文件；失败/语法错误 → ``fallback=True`` + ``parse_errors``，绝不抛异常。"""
        language = self.language or "fallback"
        source = content.encode("utf-8")
        try:
            tree = self.parser().parse(source)
        except Exception as exc:  # grammar 加载失败 / 解析器异常
            return ParsedFile(
                path=path,
                language=language,
                parse_errors=(f"{type(exc).__name__}: {exc}",),
                fallback=True,
            )

        errors = collect_parse_errors(tree.root_node, source)
        if errors:
            # 语法错误文件不产半可信符号：整体交 TASK-006 兜底切分
            return ParsedFile(
                path=path,
                language=language,
                parse_errors=tuple(errors),
                fallback=True,
            )

        ctx = FileContext(path=path, language=language, source=source)
        out = Extraction()
        try:
            self.extract(tree.root_node, ctx, out)
        except Exception as exc:  # 抽取器缺陷同样不得向上抛
            return ParsedFile(
                path=path,
                language=language,
                parse_errors=(f"extractor failure: {type(exc).__name__}: {exc}",),
                fallback=True,
            )

        return ParsedFile(
            path=path,
            language=language,
            symbols=finalize_symbols(out.symbols),
            edges=finalize_edges(out.edges),
            unresolved=finalize_unresolved(out.unresolved),
            parse_errors=tuple(out.parse_errors),
        )

    def extract(self, root: ts.Node, ctx: FileContext, out: Extraction) -> None:
        """子类实现：把符号/边/unresolved 写进 ``out``。"""
        raise NotImplementedError


def _dedupe(items: list, key) -> list:
    seen = set()
    result = []
    for item in items:
        marker = key(item)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def finalize_symbols(items: list[SymbolDef]) -> tuple[SymbolDef, ...]:
    """去重（fqn+kind+行区间）+ 按行号稳定排序。"""
    unique = _dedupe(items, lambda s: (s.fqn, s.kind, s.start_line, s.end_line))
    return tuple(sorted(unique, key=lambda s: (s.start_line, s.end_line, s.fqn, s.kind)))


def finalize_edges(items: list[EdgeDef]) -> tuple[EdgeDef, ...]:
    """去重（与 edges 表唯一索引同口径）+ 按行号稳定排序。"""
    unique = _dedupe(
        items, lambda e: (e.source_fqn, e.target_name, e.kind, e.line, e.provenance)
    )
    return tuple(
        sorted(
            unique,
            key=lambda e: (e.line or 0, e.source_fqn, e.kind, e.target_name, e.provenance),
        )
    )


def finalize_unresolved(items: list[UnresolvedRef]) -> tuple[UnresolvedRef, ...]:
    """去重（from_fqn+name+kind+line）+ 按行号稳定排序。"""
    unique = _dedupe(items, lambda r: (r.from_fqn, r.name, r.kind, r.line))
    return tuple(
        sorted(unique, key=lambda r: (r.line or 0, r.from_fqn, r.kind, r.name))
    )
