#!/usr/bin/env python
"""按题库里**标注的工具**跑分：`search` 走检索，`ask` 走 service 的 grounded 总结。

为什么单独一个脚本：`zace-core eval` 只覆盖 search（检索命中率）；
而题库里有一批题标注为 `ask`（需要跨文件综合解释），必须走
`service/zace_service/answer.py` 的真实 LLM 路径才测得准。判定口径：

- `search` 组：复用 core 的 `first_hit_rank` —— 期望路径出现在**装填顺序** top-k 内即命中；
- `ask` 组：同一条 query 先检索再喂给 LLM，**两个指标分开记**：
  - `pack_rank`：检索层有没有把它捞进包（失败说明是召回问题，不是 LLM 问题）；
  - `answer_hit`：LLM 产出的答案正文里有没有出现期望路径（失败说明 LLM 没用上证据）。

用法：
    uv run python benches/golden/qa_probe.py \
        --golden benches/golden/langchain/langchain.jsonl \
        --project-id ca2050db0db5b1e2 \
        --data /root/.zace/bench/voyage-4-lite-d1024 \
        --out benches/results/raw/qa-probe/langchain.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "service"))

from zace_core.cli.eval import (  # noqa: E402
    first_hit_rank,
    load_cases,
    ordered_evidence,
    run_golden,
)
from zace_core.embedding.factory import EmbeddingConfig, create_provider  # noqa: E402
from zace_core.engine import Engine  # noqa: E402
from zace_service.answer import AnswerError, answer_question, build_provider  # noqa: E402
from zace_service.config import Settings  # noqa: E402


def tools_of(golden: Path) -> dict[str, str]:
    """从 JSONL 里取每条用例的 `tool` 字段（core 的 GoldenCase 不认这个字段）。"""
    out: dict[str, str] = {}
    for line in golden.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            out[str(payload["id"])] = str(payload.get("tool") or "search")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="按题库标注的工具跑分（search / ask）")
    ap.add_argument("--golden", type=Path, required=True)
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--report", type=Path, help="可选：输出一段 Markdown 摘要")
    ap.add_argument("--max-tokens", type=int, default=10_000)
    ap.add_argument("--top-k", type=int, default=10)
    args = ap.parse_args()

    cases = load_cases(args.golden)
    tools = tools_of(args.golden)
    search_cases = [c for c in cases if tools.get(c.id, "search") == "search"]
    ask_cases = [c for c in cases if tools.get(c.id) == "ask"]

    provider = create_provider(EmbeddingConfig.from_env())
    engine = Engine.open(args.data, provider=provider)
    payload: dict[str, Any] = {
        "schema": 1,
        "golden": str(args.golden),
        "project_id": args.project_id,
        "data_root": str(args.data),
        "counts": {"total": len(cases), "search": len(search_cases), "ask": len(ask_cases)},
    }
    try:
        # ---- tool=search：走 core 的评估判定 ----
        report = run_golden(
            search_cases,
            lambda q: engine.search_with_trace(args.project_id, q, args.max_tokens),
            golden=str(args.golden),
            project_id=args.project_id,
            max_tokens=args.max_tokens,
            top_k=args.top_k,
        )
        overall = report.overall
        payload["search"] = {
            "cases": len(search_cases),
            "recall_at_5": round(overall.recall_at_5, 4),
            "recall_at_10": round(overall.recall_at_10, 4),
            "mrr": round(overall.mrr, 4),
            "negatives_passed": report.negative_pass_count,
            "negatives_total": len(report.negatives),
            "degraded": report.degraded_count,
            "per_case": [
                {
                    "id": r.case.id,
                    "category": r.case.category,
                    "rank": r.rank,
                    "hit": r.hit,
                    "passed": r.passed,
                    "answerable": r.answerable,
                    "top3": list(r.top),
                    "error": r.error,
                }
                for r in report.results
            ],
        }

        # ---- tool=ask：检索 + LLM（与 service 同一条实现） ----
        settings = Settings.from_env()
        answerer = build_provider(settings)
        ask_rows: list[dict[str, Any]] = []
        for case in ask_cases:
            trace = engine.search_with_trace(args.project_id, case.query, args.max_tokens)
            pack = trace.pack
            expected_paths = [e.path for e in case.expected]
            row: dict[str, Any] = {
                "id": case.id,
                "category": case.category,
                "question": case.query,
                "expected": expected_paths,
                "pack_rank": first_hit_rank(ordered_evidence(pack), case, top_k=args.top_k),
                "pack_answerable": pack.answerable,
                "evidence_count": len(pack.evidence) + len(pack.docs),
            }
            if answerer is None:
                row["status"] = "degraded"
                row["reason"] = "ANSWER_* 未配置（走 D-26 降级包，不调 LLM）"
            else:
                try:
                    outcome = answer_question(
                        provider=answerer, settings=settings, pack=pack, question=case.query
                    )
                    row.update(
                        status="answered",
                        answer_hit=any(p and p in outcome.answer for p in expected_paths),
                        latency_ms=round(outcome.latency_ms, 1),
                        answer_tokens=outcome.answer_tokens,
                        valid_citations=outcome.valid_citations,
                        invalid_citations=outcome.invalid_citations,
                        citation_coverage=outcome.citation_coverage,
                        answer=outcome.answer,
                    )
                except AnswerError as exc:
                    row.update(status="degraded", reason=f"{type(exc).__name__}: {exc}"[:300])
            row["pack_answerable"] = bool(row["pack_answerable"])
            ask_rows.append(row)
            print(f"  [{case.id}] {row['status']} pack_rank={row.get('pack_rank')} "
                  f"answer_hit={row.get('answer_hit')}", flush=True)
        payload["ask"] = {
            "cases": len(ask_rows),
            "answered": sum(1 for r in ask_rows if r["status"] == "answered"),
            "answer_hits": sum(1 for r in ask_rows if r.get("answer_hit")),
            "pack_hits": sum(1 for r in ask_rows if r.get("pack_rank")),
            "per_case": ask_rows,
        }
    finally:
        try:
            provider.close()
        except Exception:  # noqa: BLE001
            pass

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    s = payload["search"]
    a = payload.get("ask", {})
    print(f"\nsearch：recall@5={s['recall_at_5']} recall@10={s['recall_at_10']} MRR={s['mrr']} "
          f"负例 {s['negatives_passed']}/{s['negatives_total']}")
    if a:
        print(
            f"ask   ：{a['answered']}/{a['cases']} 有答案，"
            f"answer_hit {a['answer_hits']}/{a['cases']}，pack_hit {a['pack_hits']}/{a['cases']}"
        )
    print(f"已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
