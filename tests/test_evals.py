"""Tests for evaluation harness runner and metrics aggregation."""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from evals.metrics import QueryEvalResult, compute_mode_metrics, lexical_faithfulness
from evals.runner import EvalRunner, compare_to_baseline


def test_compute_mode_metrics():
    results = [
        QueryEvalResult(
            query_id="q1",
            question="What is FastAPI?",
            category="easy",
            should_refuse=False,
            actually_refused=False,
            is_hit_at_1=True,
            is_hit_at_3=True,
            is_hit_at_5=True,
            reciprocal_rank=1.0,
            citation_valid=True,
            latency_ms=12.5,
            top_score=0.9,
        ),
        QueryEvalResult(
            query_id="q2",
            question="How to configure quantum computer?",
            category="refusal",
            should_refuse=True,
            actually_refused=True,
            is_hit_at_1=False,
            is_hit_at_3=False,
            is_hit_at_5=False,
            reciprocal_rank=0.0,
            citation_valid=False,
            latency_ms=8.0,
            top_score=0.01,
        ),
    ]

    summary = compute_mode_metrics("hybrid", results)
    assert summary.total_queries == 2
    assert summary.answerable_queries == 1
    assert summary.unanswerable_queries == 1
    assert summary.hit_at_1 == 1.0
    assert summary.mrr == 1.0
    assert summary.refusal_accuracy == 1.0
    assert summary.citation_validity_rate == 1.0


@pytest.mark.asyncio
async def test_eval_runner_execution(db_session: AsyncSession, tmp_path: Path):
    runner = EvalRunner(db_session)
    await runner.ensure_sample_docs_ingested("./sample_docs/fastapi_tutorial")

    # Run on hybrid mode
    metrics = await runner.run_evaluation(modes=["hybrid"])
    assert "hybrid" in metrics
    hybrid_m = metrics["hybrid"]

    # Quality thresholds live in the baseline gate (scripts/run_evals.py), not here
    assert hybrid_m.total_queries >= 50
    assert hybrid_m.answerable_queries + hybrid_m.unanswerable_queries == hybrid_m.total_queries
    assert "easy_lookup" in hybrid_m.hit_at_3_by_category

    # Test report generation
    report_file = tmp_path / "test_report.md"
    md_content = runner.generate_markdown_report(metrics, output_path=str(report_file))
    assert "# DocsQA Evaluation Harness Report" in md_content
    assert report_file.exists()


def test_baseline_gate_flags_regressions_only():
    def summary(hit3: float, false_refusals: float):
        r = QueryEvalResult("q", "?", "easy", False, False, True, True, True, 1.0, True, 1.0, 1.0)
        m = compute_mode_metrics("hybrid", [r])
        m.hit_at_3, m.false_refusal_rate = hit3, false_refusals
        return m

    from dataclasses import asdict
    baseline = {"modes": {"hybrid": asdict(summary(0.90, 0.05))}}

    assert compare_to_baseline({"hybrid": summary(0.90, 0.05)}, baseline) == []
    assert compare_to_baseline({"hybrid": summary(0.95, 0.00)}, baseline) == []  # improvements pass
    failures = compare_to_baseline({"hybrid": summary(0.875, 0.10)}, baseline)
    assert any("hit_at_3" in f for f in failures)
    assert any("false_refusal_rate" in f for f in failures)


def test_lexical_faithfulness():
    source = ["FastAPI uses Starlette for routing and Pydantic for validation."]
    assert lexical_faithfulness("FastAPI uses Starlette for routing [1]", source) == 1.0
    assert lexical_faithfulness("Django handles migrations automatically", source) == 0.0
