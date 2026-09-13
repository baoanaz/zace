"""索引范围策略：三层忽略规则引擎 + 大小/二进制阈值（TASK-037）。

设计依据：

- ``docs/design/Module/05-MCP与同步.md`` §3.1（D-28 三层忽略；``>128KB`` / ``>10%`` 不可打印判
  二进制）；
- ``docs/plan/contracts.md`` §3.9 **R42**（本地模式落 Python 实现；契约是"忽略语义"不是库）
  与 **R43**（阈值下推 core，跳过必须如实进 ``skipped_files`` 并带原因）；
- 边界说明见 ``docs/tasks/TASK-037-索引范围策略.md`` §A/§B。

为什么在 core 落地（R42 的依据）：D-28 把 ``.gitignore`` 真实解析放在 client（Rust ``ignore``
crate），
但 M2a 本地模式没有 client（R38），而本地模式的索引就在 core 里发生。**本模块定义的是一份可对照的
"忽略语义清单"**——将来 client 用 ``ignore`` crate 时，两侧行为必须一致（见
``core/tests/pipeline/test_ignore.py``）。

三层优先级（高 → 低，后写的规则覆盖先写的）：

```text
1. {repo}/.zaceignore                 项目自定义（语法同 gitignore）
2. {repo}/**/.gitignore               真实解析：注释 / ! 否定 / 目录尾 / / ** / 前导 / / 字符类
3. 内置默认（DEFAULT_SKIP_DIRS + 常见产物模式）
```

V1 明确不读（与卡内 §A 一致，简化理由写在执行记录）：``{repo}/.git/info/exclude`` 与全局
``core.excludesFile``。

本模块只做**语义实现**，不引入第三方依赖（``pathspec`` 等）：内置匹配器覆盖 gitignore 的
主要形态，行为由测试逐条锁定；偏离 ``git`` 的边角（见 ``_Pattern`` 的注释）在报告里标注。
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "BINARY_RATIO",
    "DEFAULT_SKIP_DIRS",
    "DEFAULT_SKIP_DIR_PATTERNS",
    "DEFAULT_MAX_FILE_BYTES",
    "IGNORE_FILENAME",
    "GITIGNORE_FILENAME",
    "IgnoreRules",
    "IndexScope",
    "SKIP_REASON_BINARY",
    "SKIP_REASON_OVERSIZE",
    "binary_reason",
    "oversize_reason",
    "reason_from_entry",
]

#: gitignore 语法所用的文件名（D-28 第 2 层）。
GITIGNORE_FILENAME = ".gitignore"
#: 项目自定义忽略文件名（D-28 第 1 层，优先级最高）。
IGNORE_FILENAME = ".zaceignore"

#: 默认大小阈值：``> 128 KB`` 跳过（Module/05 §3.1 / R43，与 client 同口径）。
DEFAULT_MAX_FILE_BYTES = 128 * 1024
#: 二进制判定的不可打印字符比例上限（Module/05 §3.1：``> 10%`` 判二进制）。
BINARY_RATIO = 0.10
#: 二进制探测只读前 8 KB（避免为一个 308 MB 的文件读全量；R43 / TASK-036 §C.1）。
BINARY_PROBE_BYTES = 8 * 1024

#: ``skipped_files`` 条目里的原因分隔符（``"{path}:{reason}"``）。
_REASON_SEPARATOR = ":"

#: 原因标签：超限（含字节数，让运维一眼看出多大）。
SKIP_REASON_OVERSIZE = "oversize"
#: 原因标签：二进制 / 不可解码。
SKIP_REASON_BINARY = "binary"

#: ``oversize`` 原因的形状（``oversize:<字节数>``），供 :func:`reason_from_entry` 识别。
_OVERSIZE_TAIL_RE = re.compile(rf"{SKIP_REASON_OVERSIZE}{_REASON_SEPARATOR}\d+$")


def oversize_reason(size: int) -> str:
    """``"oversize:134217728"``——带真实字节数（R43 示例形态）。"""
    return f"{SKIP_REASON_OVERSIZE}{_REASON_SEPARATOR}{size}"


def binary_reason() -> str:
    """``"binary"``——不可解码 / 高比例不可打印字符。"""
    return SKIP_REASON_BINARY


def reason_from_entry(entry: str) -> str:
    """从 ``skipped_files`` 条目取原因标签（``"a/b.png:oversize:2048"`` → ``"oversize"``）。

    兼容裸路径（无原因）：返回 ``SKIP_REASON_BINARY``——旧报告里的 ``skipped_files`` 全部是
    二进制/不可解码跳过（TASK-007 的既有语义），沿用该默认值可让按原因分组的消费方不必区分新旧。

    路径本身可能含 ``:``（Linux 合法文件名），因此靠**原因标签的形状**匹配，而不是靠 ``split``。
    """
    if entry.endswith(f"{_REASON_SEPARATOR}{SKIP_REASON_BINARY}"):
        return SKIP_REASON_BINARY
    if _OVERSIZE_TAIL_RE.search(entry):
        return SKIP_REASON_OVERSIZE
    return SKIP_REASON_BINARY


# ---------------------------------------------------------------------------
# 内置默认（第 3 层）
# ---------------------------------------------------------------------------

#: 目录扫描默认跳过的目录名（工程噪声；D-28 第 3 层的现有部分）。
DEFAULT_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".eggs",
        "dist",
        "build",
        "target",
        ".idea",
        ".vscode",
        ".zace",
    }
)

#: 目录名**模式**（第 3 层补齐 TASK-036 §C.3 的实测缺口）。
#:
#: ``build`` 这类固定名靠 :data:`DEFAULT_SKIP_DIRS` 挡住，但真实仓库里的构建产物是**变体**
#: （``cmake-build-release`` / ``build-debug`` / ``out`` / ``.cache`` …）。**用模式而不是穷举**
#: 是 TASK-037 §A 的明文要求。``bin`` / ``obj`` / ``lib`` 刻意**不在**列表里：它们是合法的
#: 源码目录名（Python 包里的 ``lib/``、C 项目的 ``bin/`` 头文件），误伤代价高于收益。
#:
#: **为什么不设内置的“产物文件名模式”（``*.a`` / ``*.min.js`` 之类）**：卡内 §A 把内置层限定为
#: “常见产物**目录**”，而 R43 要求跳过必须**如实进 ``skipped_files`` 并带原因**。若在目录列举阶段
#: 就按文件名模式剪掉，``lib/libcv.a`` 这类文件会**静默消失**、不产生任何原因——比不剪更差。
#: 因此二进制 / 超大文件的裁决统一走 §B 阈值（大小 + 内容），理由可观测。
DEFAULT_SKIP_DIR_PATTERNS: tuple[str, ...] = (
    "cmake-build-*",   # CLion/CMake 默认产物目录（TASK-036 §C.3 的直接输入）
    "build-*",         # build-debug / build-release …
    "out",             # 通用产物目录
    "htmlcov",         # coverage html（.gitignore 常见条目）
    ".cache",          # 工具缓存
    ".gradle",         # JVM 构建缓存
    ".next",           # Next.js 构建产物
    ".nuxt",           # Nuxt 构建产物
    ".turbo",          # Turborepo 缓存
    ".parcel-cache",   # Parcel 缓存
    "__pypackages__",  # PDM 本地包目录
)


# ---------------------------------------------------------------------------
# gitignore 语法
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Pattern:
    """一条（已编译的）忽略规则。

    ``negated`` = ``!pattern``：git 语义里**后面的规则覆盖前面的**，因此求值必须顺序扫描、
    命中即刷新结论。``directory_only`` = 尾 ``/``；``anchor`` = 前导 ``/``（或模式内部含 ``/``）。
    ``base`` = 该规则所在目录（仓库相对，根为 ``""``）——``sub/.gitignore`` 里的规则只作用于
    ``sub/`` 之下，这是 git 的按目录作用域语义。
    """

    pattern: str
    negated: bool
    directory_only: bool
    anchor: bool
    has_slash: bool
    base: str = ""


def _compile(line: str, *, base: str = "") -> _Pattern | None:
    """一行 ``.gitignore`` 文本 → 规则；空行/注释/纯 ``!`` 返回 ``None``（跳过）。"""
    text = line.rstrip("\n")
    if text.endswith("\r"):  # 容错 CRLF
        text = text[:-1]
    if not text.strip():
        return None
    if text.lstrip().startswith("#"):  # 注释（首字符 #；git 允许前导空白）
        return None
    # 行尾未转义的空白被忽略（git 语义）；``\ `` 可保留尾部空格，V1 不处理转义空格。
    text = text.rstrip()
    if not text:
        return None
    negated = text.startswith("!")
    if negated:
        text = text[1:]
    if not text:
        return None
    if text.startswith("\\") and len(text) > 1 and text[1] in "#!":  # ``\#`` / ``\!`` 字面量
        text = text[1:]
    directory_only = text.endswith("/")
    if directory_only:
        text = text[:-1]
    if not text:
        return None
    has_slash = "/" in text
    anchor = text.startswith("/")
    if anchor:
        text = text[1:]
    if not text:
        return None
    return _Pattern(
        pattern=text,
        negated=negated,
        directory_only=directory_only,
        anchor=anchor,
        has_slash=has_slash,
        base=base,
    )


def _glob_to_regex(pattern: str) -> str:
    """gitignore 的 glob → 正则片段。

    按 ``/`` 切段处理，因为 ``**`` 的语义是**跨段**的（段内的 ``*`` 不跨 ``/``）：

    - ``**/`` 在开头 → 零个或多个前导目录（``**/gen/x.py`` 命中 ``a/b/gen/x.py``）；
    - ``/**`` 在结尾 → 其下所有内容（``logs/**`` 命中 ``logs/a/b``，不包括 ``logs`` 自身）；
    - ``/**/`` 在中间 → 零个或多个中间目录（``a/**/b`` 命 ``a/b`` 与 ``a/x/y/b``）；
    - 其余段内的 ``*`` 不跨 ``/``，``?`` 匹配单个非 ``/`` 字符，``[]``/``[!]`` 是字符类。
    """
    segments = pattern.split("/")
    pieces: list[str | None] = []
    for segment in segments:
        # ``**`` 单独成段才有跨段语义；段内出现的 ``**``（如 ``a**b``）按普通 ``*`` 处理。
        pieces.append(None if segment == "**" else _segment_to_regex(segment))

    out: list[str] = []
    last = len(pieces) - 1
    for index, piece in enumerate(pieces):
        if piece is None:
            if index == 0 and last == 0:
                out.append(".*")
            elif index == 0:
                out.append("(?:.*/)?")  # 自带分隔符，后续段不必再加
            elif index == last:
                out.append("/.*")
            else:
                out.append("/(?:.*/)?")
            continue
        if index == 0:
            out.append(piece)
        elif pieces[index - 1] is None:
            out.append(piece)  # globstar 已处理过分隔符
        else:
            out.append("/" + piece)
    return "".join(out)


def _segment_to_regex(segment: str) -> str:
    """单个路径段内的 glob → 正则（``*`` 不跨 ``/``；字符类与转义照旧）。"""
    out: list[str] = []
    index = 0
    length = len(segment)
    while index < length:
        char = segment[index]
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            end = _find_class_end(segment, index)
            if end is None:
                out.append(re.escape(char))
            else:
                out.append(_class_body_to_regex(segment[index + 1 : end]))
                index = end
        elif char == "\\" and index + 1 < length:
            out.append(re.escape(segment[index + 1]))
            index += 1
        else:
            out.append(re.escape(char))
        index += 1
    return "".join(out)


def _find_class_end(pattern: str, start: int) -> int | None:
    """``[`` 的配对 ``]`` 下标；未闭合返回 ``None``（按字面量处理）。"""
    index = start + 1
    if index < len(pattern) and pattern[index] == "!":
        index += 1
    if index < len(pattern) and pattern[index] == "]":  # ``[]]``：首个 ] 是字符
        index += 1
    while index < len(pattern):
        if pattern[index] == "]":
            return index
        index += 1
    return None


def _class_body_to_regex(body: str) -> str:
    """字符类体 → 正则字符类（``!`` 前缀表示取反）。"""
    if not body:
        return r"\[\]"
    negate = body.startswith("!")
    if negate:
        body = body[1:]
    escaped = "".join(
        re.escape(char) if char in "\\^]" else char for char in body
    )
    return f"[^{escaped}]" if negate else f"[{escaped}]"


def _compile_matcher(pattern: _Pattern) -> _Compiled:
    """规则 → 两个正则：匹配**自身**与匹配**其后代**（git 语义：忽略目录即忽略其内容）。

    含 ``/`` 或前导 ``/`` → 锚定到规则所在目录；无 ``/`` → 匹配该目录下**任意层级**的同名条目
    （git 语义：``*.log`` 匹配 ``sub/`` 下任何深度的 ``.log``）。
    """
    body = _glob_to_regex(pattern.pattern)
    prefix = re.escape(pattern.base) + "/" if pattern.base else ""
    if pattern.directory_only:
        # 尾 ``/`` 规则：命中该目录本身及其下任何内容；**不**匹配同名普通文件（git 语义）。
        # 无 ``/``（且非前导 ``/``）时匹配任意深度的同名目录（``memory/`` 命中 ``a/b/memory/``）。
        if not (pattern.has_slash or pattern.anchor):
            head = f"{prefix}(?:.*/)?{body}"
        else:
            head = f"{prefix}{body}"
        return _Compiled(
            pattern=pattern,
            itself=re.compile(rf"^{head}$"),
            subtree=re.compile(rf"^{head}/.*$"),
        )
    if pattern.has_slash or pattern.anchor:
        return _Compiled(
            pattern=pattern,
            itself=None,
            subtree=re.compile(rf"^{prefix}{body}(?:/.*)?$"),
        )
    return _Compiled(
        pattern=pattern,
        itself=None,
        subtree=re.compile(rf"^{prefix}(?:.*/)?{body}(?:/.*)?$"),
    )


@dataclass(frozen=True, slots=True)
class _Compiled:
    """一条规则的已编译匹配器。"""

    pattern: _Pattern
    #: 尾 ``/`` 规则的"目录本身"匹配（仅当 ``is_dir=True`` 时使用）；其余规则为 ``None``。
    itself: re.Pattern[str] | None
    #: 匹配该规则命中的路径及其所有后代（对非目录规则等价于自身匹配）。
    subtree: re.Pattern[str]


# ---------------------------------------------------------------------------
# 规则集
# ---------------------------------------------------------------------------


class IgnoreRules:
    """一个仓库的三层忽略规则（``from_root`` 构建一次，之后只读）。"""

    __slots__ = (
        "_builtin_dirs",
        "_builtin_dir_patterns",
        "_custom",
        "_gitignore",
        "_root",
    )

    def __init__(
        self,
        root: str | Path,
        *,
        custom: Sequence[str | tuple[str, str]] = (),
        gitignore: Sequence[str | tuple[str, str]] = (),
        builtin_dirs: frozenset[str] = DEFAULT_SKIP_DIRS,
        builtin_dir_patterns: Sequence[str] = DEFAULT_SKIP_DIR_PATTERNS,
    ) -> None:
        self._root = Path(root)
        self._builtin_dirs = builtin_dirs
        self._builtin_dir_patterns = tuple(builtin_dir_patterns)
        #: 第 1 层（.zaceignore）+ 第 2 层（各层 .gitignore），按优先级从高到低排列。
        #: 求值时先扫高优先层；同层内后写的规则覆盖先写的（git 语义）。
        self._custom = _Layer(_as_pairs(custom))
        self._gitignore = _Layer(_as_pairs(gitignore))

    # ---------------------------------------------------------------- 构建

    @classmethod
    def from_root(
        cls,
        root: str | Path,
        *,
        builtin_dirs: frozenset[str] = DEFAULT_SKIP_DIRS,
        builtin_dir_patterns: Sequence[str] = DEFAULT_SKIP_DIR_PATTERNS,
    ) -> IgnoreRules:
        """扫描 ``root``，解析 ``.zaceignore`` 与**所有层级**的 ``.gitignore``。

        ``.gitignore`` / ``.zaceignore`` 不存在时**不报错**（与"忽略规则未引入前"的行为一致），
        只是该层为空。读取失败的忽略文件同样按"该层为空"处理——忽略规则文件坏了不该让索引整体失败。
        """
        root_path = Path(root)
        custom: list[tuple[str, str]] = []
        gitignore: list[tuple[str, str]] = []
        for directory in _walk_dirs(root_path):
            relative = directory.relative_to(root_path).as_posix() if directory != root_path else ""
            for name, sink in (
                (IGNORE_FILENAME, custom),        # 第 1 层：优先级最高
                (GITIGNORE_FILENAME, gitignore),  # 第 2 层
            ):
                candidate = directory / name
                if not candidate.is_file():
                    continue
                try:
                    text = candidate.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for raw in text.splitlines():
                    sink.append((raw, relative))
        return cls(
            root_path,
            custom=custom,
            gitignore=gitignore,
            builtin_dirs=builtin_dirs,
            builtin_dir_patterns=builtin_dir_patterns,
        )

    # ---------------------------------------------------------------- 求值

    @property
    def root(self) -> Path:
        return self._root

    def is_ignored(self, path: str, *, is_dir: bool) -> bool:
        """``path``（仓库相对、正斜杠）是否被忽略。``is_dir`` 决定目录专属规则的适用性。"""
        normalized = _normalize(path)
        if not normalized:
            return False

        # 第 3 层（最低）：内置目录名 + 目录模式。
        # 注：内置层只判目录（卡内 §A 限定为“常见产物**目录**”）；文件级裁决走 §B 阈值，
        # 这样被跳过的文件才会带得上原因（否则会静默消失）。
        # 但“在被内置忽略的目录**里面**”的文件也算被忽略（否则 ``is_ignored`` 作为
        # 独立 API 会与遍历结果不一致：``DirectorySource`` 早把该目录剪掉了）。
        if self._builtin_dir_hit(normalized, is_dir=is_dir):
            builtin = True
        else:
            builtin = False

        # 第 2 层：.gitignore（否定可救回内置命中的条目）。
        decision = self._gitignore.decide(normalized, is_dir=is_dir, initial=builtin)
        # 第 1 层：.zaceignore（最高优先级，可覆盖前两层）。
        return self._custom.decide(normalized, is_dir=is_dir, initial=decision)

    def reason_for(self, path: str) -> str | None:
        """被忽略的**原因标签**（``"gitignore"`` / ``"zaceignore"`` / ``"builtin"``）。

        未忽略返回 ``None``。
        """
        normalized = _normalize(path)
        if not normalized:
            return None
        is_dir = (self._root / normalized).is_dir()
        if not self.is_ignored(normalized, is_dir=is_dir):
            return None
        if self._custom.decide(normalized, is_dir=is_dir, initial=False):
            return "zaceignore"
        if self._gitignore.decide(normalized, is_dir=is_dir, initial=False):
            return "gitignore"
        return "builtin"

    def _builtin_dir_hit(self, path: str, *, is_dir: bool) -> bool:
        """路径自身（目录）或其任一祖先目录是否命中内置目录规则。"""
        parts = path.split("/")
        directory_parts = parts if is_dir else parts[:-1]
        return any(
            self._matches_builtin_dir("/".join(parts[:depth]))
            for depth in range(1, len(directory_parts) + 1)
        )

    def _matches_builtin_dir(self, path: str) -> bool:
        parts = path.split("/")
        if any(part in self._builtin_dirs for part in parts):
            return True
        name = parts[-1]
        return any(fnmatch.fnmatchcase(name, pattern) for pattern in self._builtin_dir_patterns)


class _Layer:
    """一层规则（已编译，可顺序求值）。"""

    __slots__ = ("_matchers",)

    def __init__(self, entries: Sequence[tuple[str, str]]) -> None:
        matchers: list[_Compiled] = []
        for line, base in entries:
            compiled = _compile(line, base=base)
            if compiled is None:
                continue
            matchers.append(_compile_matcher(compiled))
        self._matchers = tuple(matchers)

    def __bool__(self) -> bool:
        return bool(self._matchers)

    def decide(self, path: str, *, is_dir: bool, initial: bool) -> bool:
        """顺序扫描：命中规则即把结论刷新为该规则的取反值（``!`` → 取消忽略）。

        ``!`` 不能救回**父目录被排除**的文件（git 明文语义："It is not possible to re-include
        a file if a parent directory of that file is excluded"）。该判定只在真的被 ``!`` 救回过
        （``rescued``）时才走--否则每个路径都要穷举祖先，代价无意义。

        注：``DirectorySource`` 先判目录再剪枝，因此它不会对"已忽略目录下的文件"调用本方法；
        这条规则是为 ``is_ignored`` 作为**独立 API** 的语义正确性而实现（R42 要求两侧行为一致）。
        """
        result = initial
        rescued = False
        for compiled in self._matchers:
            pattern = compiled.pattern
            if pattern.directory_only:
                # 尾 ``/`` 规则：目录自身 / 其下任何内容都算命中；同名普通文件不算（git 语义）。
                matched = bool(
                    compiled.subtree.match(path)
                    or (is_dir and compiled.itself is not None and compiled.itself.match(path))
                )
            else:
                matched = bool(compiled.subtree.match(path))
            if matched:
                result = not pattern.negated
                rescued = pattern.negated
        if rescued and self._excluded_ancestor(path):
            return True
        return result

    def _excluded_ancestor(self, path: str) -> bool:
        """本层规则是否排除了 ``path`` 的某个祖先目录（仅祖先，不含自身）。"""
        parts = path.split("/")
        for depth in range(1, len(parts)):
            ancestor = "/".join(parts[:depth])
            for compiled in self._matchers:
                if compiled.itself is not None and compiled.itself.match(ancestor):
                    if not compiled.pattern.negated:
                        return True
        return False


def _as_pairs(entries: Sequence[str | tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """允许 ``IgnoreRules`` 直接吃裸行（测试/手工构造）或 ``(line, base)`` 对。"""
    pairs: list[tuple[str, str]] = []
    for entry in entries:
        if isinstance(entry, str):
            pairs.append((entry, ""))
        else:
            pairs.append((entry[0], entry[1]))
    return tuple(pairs)


def _normalize(path: str) -> str:
    return path.strip("/").replace("\\", "/")


def _walk_dirs(root: Path):
    """遍历 ``root`` 下的目录（含 root），**跳过默认噪声目录**（否则 ``node_modules`` 会拖死构建）。

    这里只用最内层的内置目录名做剪枝：忽略规则文件本身不可能出现在 ``.git`` / ``.venv`` 里。
    """
    if not root.is_dir():
        return
    stack = [root]
    seen: set[Path] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        yield current
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir() or entry.is_symlink():
                continue
            if entry.name in DEFAULT_SKIP_DIRS:
                continue
            stack.append(entry)


# ---------------------------------------------------------------------------
# 通用过滤阈值（R43）
# ---------------------------------------------------------------------------


class IndexScope:
    """大小 / 二进制阈值（Module/05 §3.1 同口径，参数可配置）。

    ``should_read`` 只在**读取之前**做纯元数据判定（大小）；二进制判定需要字节，因此由
    :meth:`check_bytes` 在拿到内容后判定——两段的返回值都是 ``(可索引, 原因)``。
    """

    __slots__ = ("_max_bytes", "_binary_ratio", "_probe_bytes")

    def __init__(
        self,
        *,
        max_bytes: int = DEFAULT_MAX_FILE_BYTES,
        binary_ratio: float = BINARY_RATIO,
        probe_bytes: int = BINARY_PROBE_BYTES,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError(f"max_bytes 必须为正整数，收到 {max_bytes}")
        if not 0.0 <= binary_ratio <= 1.0:
            raise ValueError(f"binary_ratio 必须在 [0, 1]，收到 {binary_ratio}")
        if probe_bytes <= 0:
            raise ValueError(f"probe_bytes 必须为正整数，收到 {probe_bytes}")
        self._max_bytes = max_bytes
        self._binary_ratio = binary_ratio
        self._probe_bytes = probe_bytes

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> IndexScope:
        """从环境变量构造（``ZACE_MAX_FILE_BYTES`` / ``ZACE_BINARY_RATIO``）。

        可配置性是 R43 的明文要求（"参数可配置"）；读取失败**回落默认值**而不是报错——
        一个打错的调试环境变量不该让索引起不来。
        """
        import os

        source = os.environ if env is None else env
        raw_bytes = source.get("ZACE_MAX_FILE_BYTES")
        raw_ratio = source.get("ZACE_BINARY_RATIO")
        max_bytes = DEFAULT_MAX_FILE_BYTES
        binary_ratio = BINARY_RATIO
        if raw_bytes:
            try:
                parsed = int(raw_bytes)
            except ValueError:
                parsed = 0
            if parsed > 0:
                max_bytes = parsed
        if raw_ratio:
            try:
                ratio = float(raw_ratio)
            except ValueError:
                ratio = -1.0
            if 0.0 <= ratio <= 1.0:
                binary_ratio = ratio
        return cls(max_bytes=max_bytes, binary_ratio=binary_ratio)

    def should_read(self, path: str, size: int) -> tuple[bool, str | None]:
        """纯元数据判定：``size > max_bytes`` → ``(False, "oversize:<size>")``。"""
        if size > self._max_bytes:
            return False, oversize_reason(size)
        return True, None

    def check_bytes(self, data: bytes) -> tuple[bool, str | None]:
        """内容判定：前 ``probe_bytes`` 中不可打印字符比例 ``> binary_ratio`` → 二进制。"""
        if _is_binary(data, ratio=self._binary_ratio, probe=self._probe_bytes):
            return False, binary_reason()
        return True, None


def _is_binary(data: bytes, *, ratio: float, probe: int) -> bool:
    """前 ``probe`` 字节里不可打印字符比例是否 ``> ratio``。

    判据与 notace 参数同口径（Module/05 §3.1）：先看 NUL——一个 NUL 就足以定性（文本文件不会有），
    否则按不可打印字符（``str.isprintable()`` 之外的 ASCII 控制符）比例判定。UTF-8 多字节字符的
    高位字节**不算**不可打印（否则中文文档会被整片误判为二进制）。
    """
    window = data[:probe]
    if not window:
        return False
    if b"\x00" in window:
        return True
    control = sum(1 for byte in window if byte < 0x20 and byte not in (0x09, 0x0A, 0x0D))
    return control / len(window) > ratio
