"""zace-core CLI（TASK-013 §B）：M1 验收的唯一人工入口。

设计依据：``docs/design/Module/06-服务化与部署.md`` §1（core 是纯库；CLI 是**调试形态**，
不是产品面；Phase 2 的 service 复用同一 :class:`~zace_core.engine.Engine`）。

四个子命令（card 冻结形态）：

```text
zace-core ingest --repo <PATH> [--data <ROOT>] [--full]     # 全量/增量索引（--full 忽略增量）
zace-core search "<query>" --repo <PATH> [--data <ROOT>] [--max-tokens N] [--json]
zace-core status --repo <PATH> [--data <ROOT>] [--json]
zace-core eval --golden <DIR|FILE> --repo <PATH> --report <FILE>
```

退出码：``0`` 成功 / ``1`` 运行错误 / ``2`` 参数错误（argparse 原生）。错误信息只含路径与
异常摘要，不打印任何 token / 凭据。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from zace_core.cli.eval import GoldenError, load_cases, render_report, run_golden, write_report
from zace_core.contextpack import render_markdown, to_json
from zace_core.engine import Engine, EngineError, resolve_data_root

__all__ = ["EXIT_ERROR", "EXIT_OK", "EXIT_USAGE", "build_parser", "main"]

PROG = "zace-core"
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

#: 默认检索预算（token；``--max-tokens`` 透传 ContextPack 组装预算 D-23）。
DEFAULT_MAX_TOKENS = 10_000

#: 引擎工厂（测试注入 fake embedding provider 的接缝）。
EngineFactory = Callable[[Path], Engine]


def main(argv: Sequence[str] | None = None, *, engine_factory: EngineFactory | None = None) -> int:
    """CLI 入口（``zace-core`` console script 指向本函数）。"""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    factory: EngineFactory = engine_factory or Engine.open
    try:
        return args.handler(args, factory)
    except (EngineError, GoldenError) as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except (OSError, RuntimeError, ValueError) as exc:  # 运行期故障（含 embedding/lancedb）
        print(f"{PROG}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:  # pragma: no cover - 交互中断
        print(f"{PROG}: 已中断", file=sys.stderr)
        return EXIT_ERROR


# ---------------------------------------------------------------------------
# 参数
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="zace 核心引擎调试入口（索引 / 检索 / 状态 / golden 评估）",
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, metavar="{ingest,search,status,eval}"
    )

    ingest = subparsers.add_parser("ingest", help="全量/增量索引本地仓库")
    _add_common(ingest)
    ingest.add_argument("--full", action="store_true", help="忽略增量：全量重解析 + 重建向量表")
    ingest.set_defaults(handler=_cmd_ingest)

    search = subparsers.add_parser("search", help="检索并输出 ContextPack")
    search.add_argument("query", help="自然语言查询（可含反引号包裹的符号/路径）")
    _add_common(search)
    search.add_argument(
        "--max-tokens",
        type=_positive_int,
        default=DEFAULT_MAX_TOKENS,
        help=f"ContextPack 预算上限（默认 {DEFAULT_MAX_TOKENS}）",
    )
    search.add_argument("--json", action="store_true", help="输出 CF-03 JSON（默认 Markdown）")
    search.set_defaults(handler=_cmd_search)

    status = subparsers.add_parser(
        "status", help="输出索引现状（files/chunks/symbols/edges/freshness）"
    )
    _add_common(status)
    status.add_argument("--json", action="store_true", help="输出 JSON（字段同 SyncStatus）")
    status.set_defaults(handler=_cmd_status)

    evaluate = subparsers.add_parser("eval", help="跑 golden set 并写指标报告")
    _add_common(evaluate)
    evaluate.add_argument("--golden", type=Path, required=True, help="golden 文件或目录（*.jsonl）")
    evaluate.add_argument("--report", type=Path, required=True, help="Markdown 报告输出路径")
    evaluate.set_defaults(handler=_cmd_eval)
    return parser


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=Path, required=True, help="本地仓库路径")
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="数据根（默认 $ZACE_DATA_ROOT，否则 ~/.zace）",
    )


def _positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"必须是整数：{raw!r}") from None
    if value <= 0:
        raise argparse.ArgumentTypeError(f"必须为正整数：{raw!r}")
    return value


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------


def _engine(args: argparse.Namespace, factory: EngineFactory) -> Engine:
    return factory(resolve_data_root(args.data))


def _resolved_repo(args: argparse.Namespace) -> Path:
    repo = Path(args.repo).expanduser()
    if not repo.is_dir():
        raise EngineError(f"--repo 不是目录：{repo}")
    return repo.resolve()


def _cmd_ingest(args: argparse.Namespace, factory: EngineFactory) -> int:
    engine = _engine(args, factory)
    repo = _resolved_repo(args)
    handle, identity = engine.resolve_repo(repo)
    started = time.perf_counter()
    report = engine.ingest_repo(handle.project_id, repo, full=args.full)
    elapsed = time.perf_counter() - started

    print(f"project: {handle.project_id}{' (created)' if handle.created else ''}")
    print(f"repo: {repo}")
    if identity.remote_url:
        print(f"identity: git remote {identity.remote_url} (path {identity.repo_path or '.'})")
    else:
        print("identity: 无 git remote（按绝对路径 hash）")
    mode = "full_reparse" if args.full else "incremental"
    print(f"mode: {mode} (invalidation={report.invalidation.value})")
    print(
        f"files: added={report.added} modified={report.modified} "
        f"deleted={report.deleted} parsed={report.files_parsed}"
    )
    print(
        f"chunks: new={report.chunks_new} reused={report.chunks_reused} "
        f"removed={report.chunks_removed}"
    )
    print(f"vectors: upserted={report.vectors_upserted} deleted={report.vectors_deleted}")
    print(
        f"graph: edges_retargeted={report.edges_retargeted} "
        f"unresolved_resolved={report.unresolved_resolved} spec_refs={report.spec_refs} "
        f"ambiguous={report.ambiguous_refs}"
    )
    if report.skipped_files:
        print(f"skipped: {len(report.skipped_files)} 个二进制/不可解码文件")
    if report.orphan_files:
        print(
            f"warning: {len(report.orphan_files)} 个删除文件的向量无法枚举"
            "（跨进程删除留孤儿，下一次全量重建清理）",
            file=sys.stderr,
        )
    for warning in report.errors[:5]:
        print(f"warning: {warning}", file=sys.stderr)
    if len(report.errors) > 5:
        print(f"warning: 另有 {len(report.errors) - 5} 条解析/读取告警", file=sys.stderr)
    print(f"elapsed: {elapsed:.1f}s")
    return EXIT_OK


def _cmd_search(args: argparse.Namespace, factory: EngineFactory) -> int:
    engine = _engine(args, factory)
    repo = _resolved_repo(args)
    handle, _identity = engine.resolve_repo(repo)
    trace = engine.search_with_trace(handle.project_id, args.query, args.max_tokens)
    if trace.degraded:
        print(f"warning: {trace.degraded_reason}", file=sys.stderr)
    if args.json:
        print(json.dumps(to_json(trace.pack), ensure_ascii=False, indent=2))
    else:
        print(render_markdown(trace.pack))
    return EXIT_OK


def _cmd_status(args: argparse.Namespace, factory: EngineFactory) -> int:
    engine = _engine(args, factory)
    repo = _resolved_repo(args)
    handle, _identity = engine.resolve_repo(repo)
    status = engine.sync_status(handle.project_id)
    if args.json:
        print(json.dumps(dataclasses.asdict(status), ensure_ascii=False, indent=2))
        return EXIT_OK
    print(f"project: {status.project_id}")
    print(f"repo: {repo}")
    print(f"files: {status.files_indexed}")
    print(f"chunks: {status.chunks}")
    print(f"symbols: {status.symbols}")
    print(f"edges: {status.edges}")
    print(f"pending_jobs: {status.pending_jobs}")
    print(f"freshness: {_freshness_label(status.last_indexed_at)}")
    return EXIT_OK


def _cmd_eval(args: argparse.Namespace, factory: EngineFactory) -> int:
    engine = _engine(args, factory)
    repo = _resolved_repo(args)
    handle, _identity = engine.resolve_repo(repo)
    status = engine.sync_status(handle.project_id)
    if status.files_indexed == 0:
        print(
            f"{PROG}: 项目尚未索引（{handle.project_id}）："
            f"先运行 `{PROG} ingest --repo {repo}`。",
            file=sys.stderr,
        )
        return EXIT_ERROR
    cases = load_cases(args.golden)
    if not cases:
        raise GoldenError(f"golden 集为空：{args.golden}")
    report = run_golden(
        cases,
        lambda query: engine.search_with_trace(handle.project_id, query, DEFAULT_MAX_TOKENS),
        golden=str(args.golden),
        repo=str(repo),
        project_id=handle.project_id,
        max_tokens=DEFAULT_MAX_TOKENS,
    )
    written = write_report(report, args.report)
    print(render_report(report), end="")
    print(f"report: {written}")
    return EXIT_OK


def _freshness_label(indexed_at: int | None) -> str:
    if indexed_at is None:
        return "unknown（尚无索引）"
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(indexed_at))
    age = max(int(time.time()) - indexed_at, 0)
    return f"{stamp}（{age}s ago）"


if __name__ == "__main__":  # pragma: no cover - 直接运行（python -m zace_core.cli.app）
    sys.exit(main())
