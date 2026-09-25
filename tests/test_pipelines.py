from __future__ import annotations

import pytest

from core.utils import read_json, write_json
from pipelines import corruption_flow, phase1


def test_end_to_end_baseline_corruption_and_repair(settings):
    baseline = phase1.main(settings)
    paths = settings.paths
    for path in (
        paths.clean_csv,
        paths.clean_json,
        paths.eval_testset,
        paths.baseline_metrics,
        paths.baseline_answers,
        paths.baseline_quality_report,
        paths.freshness_report,
        paths.baseline_report,
        paths.demo_answers,
    ):
        assert path.exists(), path
    assert baseline["retrieval_hit_rate"] == 1.0
    assert "Phase 1 Report" in paths.baseline_report.read_text(encoding="utf-8")

    results = corruption_flow.main(settings)
    assert results["corrupted"]["mean_token_f1"] < results["baseline"]["mean_token_f1"]
    assert results["corrupted"]["retrieval_hit_rate"] < results["baseline"]["retrieval_hit_rate"]
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        assert results["repaired"][key] == results["baseline"][key]
    assert len(read_json(paths.corruption_log)["corruptions"]) == 6
    assert read_json(paths.corrupted_quality_report)["success"] is False
    report = paths.comparison_report.read_text(encoding="utf-8")
    assert "| Metric / signal | Baseline | Corrupted | Repaired |" in report
    assert "idempotent (2 repair runs identical) | PASS" in report

    # Phase 1 is re-runnable and keeps the fixed benchmark.
    test_set = read_json(paths.eval_testset)
    phase1.main(settings)
    assert read_json(paths.eval_testset) == test_set


def test_phase1_rebuilds_stale_test_set_and_blocks_bad_data(settings, monkeypatch):
    write_json(settings.paths.eval_testset, [{"ground_truth_doc_ids": ["10.0/unknown"]}])
    monkeypatch.setattr(phase1, "evaluate_pipeline", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop")))
    with pytest.raises(RuntimeError, match="stop"):
        phase1.main(settings)
    assert len(read_json(settings.paths.eval_testset)) == 10

    monkeypatch.setattr(
        phase1, "run_data_quality_checks", lambda df, s, name: {"success": False, "failed_checks": ["x"]}
    )
    with pytest.raises(SystemExit, match="Quality gate FAILED"):
        phase1.main(settings)


def test_corruption_flow_requires_baseline(settings):
    with pytest.raises(SystemExit, match="run_phase1"):
        corruption_flow.main(settings)


def test_agent_demo_reports_unavailable_provider(settings, monkeypatch):
    monkeypatch.setattr(phase1, "build_agent", lambda s, i: (_ for _ in ()).throw(RuntimeError("no key")))
    demo = phase1.run_agent_demo(settings, index=None, questions=["q1", "q2"])
    assert [item["error"] for item in demo] == ["agent unavailable: RuntimeError: no key"] * 2
