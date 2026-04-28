"""Evaluation harness: runs the golden set across Vector, Full-Text and Hybrid RRF, gates against a stored baseline."""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Chunk
from app.db.session import AsyncSessionLocal, init_db
from app.ingestion.pipeline import IngestionPipeline
from app.models_adapter import get_model_adapter
from app.retrieval.engine import RetrievalEngine
from evals.metrics import (
    ModeSummaryMetrics,
    QueryEvalResult,
    compute_mode_metrics,
    lexical_faithfulness,
)

BASELINE_PATH = Path("evals/baseline.json")
# Per-metric allowed drop before the gate fails. The stub model is deterministic, so any
# single-question regression (1/40 = 0.025) trips the gate; 0.01 only absorbs rounding.
TOLERANCE = 0.01
HIGHER_IS_BETTER = ("hit_at_3", "mrr", "refusal_accuracy", "faithfulness")
LOWER_IS_BETTER = ("false_refusal_rate",)


def eval_environment(session: AsyncSession) -> dict[str, str]:
    """What the numbers depend on; a baseline is only comparable within the same environment."""
    adapter = get_model_adapter()
    return {
        "database": session.bind.dialect.name if session.bind else "unknown",
        "model_provider": settings.MODEL_PROVIDER,
        "embedding_model": f"{adapter.model_name}@{adapter.model_version}",
    }


def _norm(heading: str) -> str:
    return heading.replace("`", "").lower()


class EvalRunner:
    """Runs golden question dataset across retrieval modes and generates reports."""

    def __init__(self, session: AsyncSession, dataset_path: str = "evals/dataset.json"):
        self.session = session
        self.dataset_path = Path(dataset_path)

    async def ensure_sample_docs_ingested(self, docs_path: str = settings.SAMPLE_DOCS_PATH) -> None:
        """Ensure sample documentation is indexed before running evaluations."""
        await IngestionPipeline(self.session).ingest_directory(docs_path)

    async def _chunk_texts(self, chunk_ids: list[str]) -> list[str]:
        if not chunk_ids:
            return []
        res = await self.session.execute(select(Chunk.content).where(Chunk.id.in_(chunk_ids)))
        return list(res.scalars().all())

    async def run_evaluation(self, modes: list[str] | None = None) -> dict[str, ModeSummaryMetrics]:
        modes = modes or ["vector", "fts", "hybrid"]
        dataset: list[dict[str, Any]] = json.loads(self.dataset_path.read_text(encoding="utf-8"))

        engine = RetrievalEngine(self.session)
        mode_metrics: dict[str, ModeSummaryMetrics] = {}

        for mode in modes:
            results: list[QueryEvalResult] = []
            for item in dataset:
                expected_sources = item.get("expected_sources", [])
                expected_headings = item.get("expected_headings", [])
                should_refuse = item.get("should_refuse", False)

                start = time.perf_counter()
                res = await engine.query(query_text=item["question"], mode=mode, top_k=5)  # type: ignore[arg-type]
                latency_ms = (time.perf_counter() - start) * 1000.0

                # A hit needs the right file AND (when given) the right section
                ranks = [
                    rank
                    for rank, rc in enumerate(res.retrieved_chunks, start=1)
                    if any(src in rc.source_url for src in expected_sources)
                    and (not expected_headings or any(_norm(h) in _norm(rc.heading) for h in expected_headings))
                ]
                first = ranks[0] if ranks and not should_refuse else None

                answered = not res.refused and bool(res.citations)
                retrieved_ids = {rc.chunk_id for rc in res.retrieved_chunks}
                faithfulness = None
                if answered:
                    cited = await self._chunk_texts([c.chunk_id for c in res.citations])
                    faithfulness = lexical_faithfulness(res.answer, cited)

                results.append(
                    QueryEvalResult(
                        query_id=item["id"],
                        question=item["question"],
                        category=item.get("category", "standard"),
                        should_refuse=should_refuse,
                        actually_refused=res.refused,
                        is_hit_at_1=first is not None and first <= 1,
                        is_hit_at_3=first is not None and first <= 3,
                        is_hit_at_5=first is not None and first <= 5,
                        reciprocal_rank=1.0 / first if first else 0.0,
                        citation_valid=answered and all(c.chunk_id in retrieved_ids for c in res.citations),
                        latency_ms=latency_ms,
                        top_score=res.top_score,
                        faithfulness=faithfulness,
                        retrieved_sources=[rc.source_url for rc in res.retrieved_chunks],
                    )
                )

            mode_metrics[mode] = compute_mode_metrics(mode=mode, results=results)

        return mode_metrics

    def generate_markdown_report(
        self,
        mode_metrics: dict[str, ModeSummaryMetrics],
        environment: dict[str, str] | None = None,
        output_path: str = "evals/latest_report.md",
    ) -> str:
        environment = environment or {}
        any_m = next(iter(mode_metrics.values()))
        lines = [
            "# DocsQA Evaluation Harness Report",
            f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            (
                f"**Golden set:** {any_m.total_queries} questions "
                f"({any_m.answerable_queries} answerable, {any_m.unanswerable_queries} should be refused)"
            ),
            "**Environment:** " + ", ".join(f"{k}=`{v}`" for k, v in environment.items()),
            "",
            "| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | Refusal acc. | False refusals | Valid citations | Faithfulness | Avg latency | P95 latency |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for mode, m in mode_metrics.items():
            lines.append(
                f"| {mode} | {m.hit_at_1:.1%} | {m.hit_at_3:.1%} | {m.hit_at_5:.1%} | {m.mrr:.3f} | "
                f"{m.refusal_accuracy:.1%} | {m.false_refusal_rate:.1%} | {m.citation_validity_rate:.1%} | "
                f"{m.faithfulness:.1%} | {m.avg_latency_ms:.1f}ms | {m.p95_latency_ms:.1f}ms |"
            )

        categories = sorted({c for m in mode_metrics.values() for c in m.hit_at_3_by_category})
        lines += [
            "",
            "### Hit@3 by question category",
            "",
            "| Mode | " + " | ".join(categories) + " |",
            "|---|" + "---|" * len(categories),
        ]
        for mode, m in mode_metrics.items():
            lines.append(f"| {mode} | " + " | ".join(f"{m.hit_at_3_by_category.get(c, 0):.1%}" for c in categories) + " |")

        lines += [
            "",
            (
                "A hit means a retrieved chunk is from an expected file and section. Faithfulness is a "
                "lexical proxy (share of answer words found in the cited chunks); with the stub model, "
                "answers are extracted from the context, so it is high by construction. Retrieval hits are scored on what was retrieved, even when the generator then refused."
            ),
        ]

        report_md = "\n".join(lines) + "\n"
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(report_md, encoding="utf-8")
        out_file.with_suffix(".json").write_text(
            json.dumps({"environment": environment, "modes": {k: asdict(v) for k, v in mode_metrics.items()}}, indent=2),
            encoding="utf-8",
        )
        return report_md


def compare_to_baseline(
    metrics: dict[str, ModeSummaryMetrics], baseline: dict[str, Any], tolerance: float = TOLERANCE
) -> list[str]:
    """Return one message per metric that regressed beyond tolerance."""
    failures = []
    for mode, base in baseline["modes"].items():
        current = metrics.get(mode)
        if current is None:
            failures.append(f"{mode}: missing from current run")
            continue
        for name in HIGHER_IS_BETTER:
            if getattr(current, name) < base[name] - tolerance:
                failures.append(f"{mode}.{name}: {getattr(current, name):.4f} < baseline {base[name]:.4f}")
        for name in LOWER_IS_BETTER:
            if getattr(current, name) > base[name] + tolerance:
                failures.append(f"{mode}.{name}: {getattr(current, name):.4f} > baseline {base[name]:.4f}")
    return failures


async def run_evals_cli(argv: list[str] | None = None) -> int:
    """Entry point for CLI and the CI gate. Exit 1 on regression, 2 on unusable baseline."""
    parser = argparse.ArgumentParser(description="Run the DocsQA golden-set evaluation.")
    parser.add_argument("--update-baseline", action="store_true", help="Write this run as the new baseline.")
    parser.add_argument("--report", default="evals/latest_report.md", help="Markdown report path (JSON written alongside).")
    parser.add_argument("--no-gate", action="store_true", help="Only report; skip the baseline comparison.")
    args = parser.parse_args(argv)

    await init_db()
    async with AsyncSessionLocal() as session:
        runner = EvalRunner(session)
        await runner.ensure_sample_docs_ingested()
        metrics = await runner.run_evaluation()
        env = eval_environment(session)
        print(runner.generate_markdown_report(metrics, environment=env, output_path=args.report))

    current = {"environment": env, "modes": {k: asdict(v) for k, v in metrics.items()}}
    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"Baseline written to {BASELINE_PATH}")
        return 0
    if args.no_gate:
        return 0

    if not BASELINE_PATH.exists():
        print(f"No baseline at {BASELINE_PATH}; run with --update-baseline and commit it.")
        return 2
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if baseline.get("environment") != env:
        print(f"Baseline environment {baseline.get('environment')} != current {env}; numbers are not comparable.")
        return 2

    failures = compare_to_baseline(metrics, baseline)
    if failures:
        print("Eval gate FAILED, regressions against baseline:\n  " + "\n  ".join(failures))
        return 1
    print("Eval gate passed: no metric regressed against the baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_evals_cli()))
