from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from core.utils import now_utc, write_text

METRIC_KEYS = ["retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"]

# Which observability signal is expected to catch each corruption scenario.
DETECTORS = {
    "drop_latest_records": "source_reconciliation",
    "blank_summary": "expect_column_value_lengths_to_be_between(summary)",
    "inject_noise": "expect_column_values_to_not_match_regex(summary)",
    "truncate_title": "expect_column_value_lengths_to_be_between(title)",
    "stale_date": "freshness_sla",
    "duplicate_rows": "expect_column_values_to_be_unique(paper_id)",
}


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, float):
        return f"{value:.4f}"
    if value is None:
        return "-"
    return str(value)


def _delta(new: Any, old: Any) -> str:
    if isinstance(new, (int, float)) and isinstance(old, (int, float)) and not isinstance(new, bool):
        return f"{new - old:+.4f}"
    return "-"


def _recovery(baseline: Any, corrupted: Any, repaired: Any) -> str:
    numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (baseline, corrupted, repaired))
    if not numeric:
        return "-"
    drop = baseline - corrupted
    if abs(drop) < 1e-9:
        return "n/a (no drop)"
    return f"{(repaired - corrupted) / drop:.0%}"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    lines += ["| " + " | ".join(_fmt(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def _check_key(item: dict[str, Any]) -> str:
    return f"{item['expectation']}({item['column']})" if item.get("column") else item["expectation"]


def _threshold(kwargs: dict[str, Any]) -> str:
    parts = [f"{key}={value}" for key, value in kwargs.items() if key != "column" and value is not None]
    return ", ".join(parts) or "-"


def _per_type(answers: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in answers:
        groups[item["question_type"]].append(item)
    return {
        qtype: {
            "n": len(items),
            "hit_rate": mean(1.0 if i["retrieval_hit"] else 0.0 for i in items),
            "token_f1": mean(i["token_f1"] for i in items),
            "judge_accuracy": mean(1.0 if i["judge"]["correct"] else 0.0 for i in items),
        }
        for qtype, items in groups.items()
    }


def _quality_rows(quality: dict[str, Any]) -> list[list[Any]]:
    rows = []
    for item in quality.get("expectations", []):
        observed = item.get("observed_value")
        if observed is None and item.get("unexpected_count") is not None:
            observed = f"{item['unexpected_count']} unexpected"
        rows.append([item["expectation"], item.get("column") or "table", _threshold(item["kwargs"]), item["success"], observed])
    recon = quality.get("source_reconciliation", {})
    if recon and "skipped" not in recon:
        rows.append(
            [
                "source_reconciliation",
                "paper_id",
                f"coverage>={recon['min_coverage']}",
                recon["success"],
                f"coverage={recon['coverage']} ({recon['missing_count']} missing)",
            ]
        )
    return rows


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
    answers: list[dict[str, Any]] | None = None,
    agent_demo: list[dict[str, Any]] | None = None,
) -> None:
    """Write the baseline (phase 1) Markdown report."""
    lines = [
        "# Phase 1 Report — Baseline Data Pipeline",
        "",
        f"_Generated at {now_utc().isoformat()} by `script/run_phase1.py`._",
        "",
        "## 1. Source & lineage",
        "",
        _table(["Field", "Value"], [[key, value] for key, value in source_summary.items()]),
        "",
        "## 2. Baseline RAG metrics",
        "",
        _table(
            ["Metric", "Value"],
            [[key, metrics.get(key)] for key in ["samples", *METRIC_KEYS, "judge_backend"] if key in metrics],
        ),
        "",
        f"Ragas: `{metrics.get('ragas')}`",
        "",
    ]

    if answers:
        per_type = _per_type(answers)
        lines += [
            "### Breakdown by question type",
            "",
            _table(
                ["question_type", "n", "hit_rate", "token_f1", "judge_accuracy"],
                [[qt, v["n"], v["hit_rate"], v["token_f1"], v["judge_accuracy"]] for qt, v in sorted(per_type.items())],
            ),
            "",
            "### Per-question results",
            "",
            _table(
                ["id", "type", "hit", "token_f1", "judge", "answer"],
                [
                    [a["id"], a["question_type"], a["retrieval_hit"], a["token_f1"], a["judge"]["score"], a["answer"][:80]]
                    for a in answers
                ],
            ),
            "",
        ]

    lines += [
        "## 3. Data quality gate (Great Expectations 1.x)",
        "",
        f"- Engine: {quality.get('engine')}",
        f"- Rows validated: {quality.get('row_count')}",
        f"- **Gate status: {'PASS' if quality.get('success') else 'FAIL'}** "
        f"({quality['statistics']['successful_checks']}/{quality['statistics']['evaluated_checks']} checks passed)",
        "",
        _table(["Check", "Column", "Threshold", "Status", "Observed"], _quality_rows(quality)),
        "",
        "## 4. Freshness SLA",
        "",
        _table(
            ["Field", "Value"],
            [
                ["threshold_days", freshness.get("threshold_days")],
                ["max_stale_ratio", freshness.get("max_stale_ratio")],
                ["total_rows", freshness.get("total_rows")],
                ["stale_rows", freshness.get("stale_rows")],
                ["stale_ratio", freshness.get("stale_ratio")],
                ["latest_published", freshness.get("latest_published")],
                ["oldest_published", freshness.get("oldest_published")],
                ["median_age_days", freshness.get("median_age_days")],
                ["is_fresh", freshness.get("is_fresh")],
            ],
        ),
        "",
        "Age distribution (days): "
        + ", ".join(f"`{bucket}`: {count}" for bucket, count in (freshness.get("age_distribution") or {}).items()),
        "",
    ]

    if agent_demo:
        lines += ["## 5. Agent demo (LangChain tool-calling agent)", ""]
        for item in agent_demo:
            lines += [f"- **Q:** {item['question']}", f"  - **A:** {item.get('answer') or item.get('error')}"]
        lines.append("")

    write_text(report_path, "\n".join(lines))


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    baseline_quality: dict[str, Any] | None = None,
    baseline_freshness: dict[str, Any] | None = None,
    corruption_log: dict[str, Any] | None = None,
    answers: dict[str, list[dict[str, Any]]] | None = None,
    repair_summary: dict[str, Any] | None = None,
) -> None:
    """Write the Baseline vs Corrupted vs Repaired comparison report."""
    baseline_quality = baseline_quality or {}
    baseline_freshness = baseline_freshness or baseline_quality.get("freshness", {})
    states = {
        "baseline": (baseline_metrics, baseline_quality, baseline_freshness),
        "corrupted": (corrupted_metrics, corrupted_quality, corrupted_freshness),
        "repaired": (repaired_metrics, repaired_quality, repaired_freshness),
    }

    metric_rows = []
    for key in METRIC_KEYS:
        b, c, r = (states[s][0].get(key) for s in states)
        metric_rows.append([f"`{key}`", b, c, r, _delta(c, b), _recovery(b, c, r)])

    def gate(quality: dict[str, Any]) -> str:
        if not quality:
            return "-"
        stats = quality.get("statistics", {})
        return f"{'PASS' if quality.get('success') else 'FAIL'} ({stats.get('failed_checks', '?')} failed)"

    signal_rows = [
        ["Rows in dataset", *(states[s][1].get("row_count") for s in states), "", ""],
        ["Quality gate", *(gate(states[s][1]) for s in states), "", ""],
        [
            "Source coverage",
            *(states[s][1].get("source_reconciliation", {}).get("coverage") for s in states),
            "",
            "",
        ],
        ["Freshness is_fresh", *(states[s][2].get("is_fresh") for s in states), "", ""],
        ["Stale ratio", *(states[s][2].get("stale_ratio") for s in states), "", ""],
        ["Latest published", *(states[s][2].get("latest_published") for s in states), "", ""],
    ]

    lines = [
        "# Corruption Report — Baseline vs Corrupted vs Repaired",
        "",
        f"_Generated at {now_utc().isoformat()} by `script/run_corruption_flow.py`. "
        "All three states are evaluated on the same `data/eval/test_set.json`._",
        "",
        "## 1. Three-state comparison",
        "",
        _table(
            ["Metric / signal", "Baseline", "Corrupted", "Repaired", "Δ corruption", "Recovery"],
            metric_rows + signal_rows,
        ),
        "",
        "_Recovery = (repaired − corrupted) / (baseline − corrupted)._",
        "",
    ]

    # Per-check matrix across states.
    check_status: dict[str, dict[str, bool]] = defaultdict(dict)
    for state, (_, quality, freshness) in states.items():
        for item in quality.get("expectations", []):
            check_status[_check_key(item)][state] = item["success"]
        recon = quality.get("source_reconciliation", {})
        if recon and "skipped" not in recon:
            check_status["source_reconciliation"][state] = recon["success"]
        if freshness:
            check_status["freshness_sla"][state] = freshness.get("is_fresh")
    lines += [
        "## 2. Observability signals per check",
        "",
        _table(
            ["Check", "Baseline", "Corrupted", "Repaired"],
            [[f"`{name}`", *(status.get(s) for s in states)] for name, status in check_status.items()],
        ),
        "",
    ]

    corruptions = (corruption_log or {}).get("corruptions", [])
    if corruptions:
        detection_rows = []
        for item in corruptions:
            detector = DETECTORS.get(item["type"], "-")
            caught = check_status.get(detector, {}).get("corrupted")
            detection_rows.append(
                [f"`{item['type']}`", item["description"], item["affected_count"], f"`{detector}`", "YES" if caught is False else "NO"]
            )
        lines += [
            "## 3. Injected corruptions and detection",
            "",
            f"Seed `{corruption_log.get('seed')}` — {corruption_log.get('input_rows')} clean rows → "
            f"{corruption_log.get('output_rows')} corrupted rows (`data/results/corruption_log.json`).",
            "",
            _table(["Corruption", "What changed", "Rows", "Expected detector", "Detected?"], detection_rows),
            "",
        ]

    if answers and all(state in answers for state in states):
        per_type = {state: _per_type(answers[state]) for state in states}
        type_rows = []
        for qtype in sorted(per_type["baseline"]):
            type_rows.append(
                [
                    qtype,
                    per_type["baseline"][qtype]["n"],
                    *(per_type[s].get(qtype, {}).get("token_f1") for s in states),
                    *(per_type[s].get(qtype, {}).get("hit_rate") for s in states),
                ]
            )
        lines += [
            "## 4. Impact by question type",
            "",
            _table(
                ["question_type", "n", "F1 base", "F1 corrupt", "F1 repair", "Hit base", "Hit corrupt", "Hit repair"],
                type_rows,
            ),
            "",
        ]

        doc_to_corruptions: dict[str, list[str]] = defaultdict(list)
        for item in corruptions:
            for paper_id in item["affected_paper_ids"]:
                if item["type"] not in doc_to_corruptions[paper_id]:
                    doc_to_corruptions[paper_id].append(item["type"])
        by_id = {state: {a["id"]: a for a in answers[state]} for state in states}
        question_rows = []
        for base in answers["baseline"]:
            corrupted = by_id["corrupted"].get(base["id"], {})
            repaired = by_id["repaired"].get(base["id"], {})
            causes = [c for doc in base["ground_truth_doc_ids"] for c in doc_to_corruptions.get(doc, [])]
            question_rows.append(
                [
                    base["id"],
                    base["question_type"],
                    ", ".join(causes) or "none",
                    base["token_f1"],
                    corrupted.get("token_f1"),
                    repaired.get("token_f1"),
                    corrupted.get("retrieval_hit"),
                    (corrupted.get("answer") or "")[:60].replace("|", "/"),
                ]
            )
        lines += [
            "## 5. Per-question root cause",
            "",
            _table(
                ["id", "type", "Corruption on ground-truth doc", "F1 base", "F1 corrupt", "F1 repair", "Hit corrupt", "Corrupted answer"],
                question_rows,
            ),
            "",
        ]

    if repair_summary:
        lines += [
            "## 6. Repair verification",
            "",
            _table(["Field", "Value"], [[key, value] for key, value in repair_summary.items()]),
            "",
        ]

    lines += ["## 7. Analysis", ""] + _analysis(states, corruptions, check_status)
    write_text(report_path, "\n".join(lines) + "\n")


def _analysis(states, corruptions, check_status) -> list[str]:
    base, corrupt, repair = (states[s][0] for s in ("baseline", "corrupted", "repaired"))
    out = []
    failed_checks = [name for name, status in check_status.items() if status.get("corrupted") is False]
    out.append(
        f"1. **Corruption → quality signal → agent metric.** The corrupted dataset tripped "
        f"{len(failed_checks)} observability checks ({', '.join(f'`{c}`' for c in failed_checks) or 'none'}). "
        f"Without the gate, the agent still answered every question without raising an error, but "
        f"`retrieval_hit_rate` went {_fmt(base.get('retrieval_hit_rate'))} → {_fmt(corrupt.get('retrieval_hit_rate'))} and "
        f"`mean_token_f1` {_fmt(base.get('mean_token_f1'))} → {_fmt(corrupt.get('mean_token_f1'))} — a silent failure."
    )
    repaired_failed = [name for name, status in check_status.items() if status.get("repaired") is False]
    out.append(
        f"2. **Repair → signal recovery → metric recovery.** Rebuilding from the raw snapshot left "
        f"{len(repaired_failed)} failing checks ({', '.join(f'`{c}`' for c in repaired_failed) or 'none'}); "
        f"`retrieval_hit_rate` = {_fmt(repair.get('retrieval_hit_rate'))} and `mean_token_f1` = "
        f"{_fmt(repair.get('mean_token_f1'))} versus baseline {_fmt(base.get('retrieval_hit_rate'))} / "
        f"{_fmt(base.get('mean_token_f1'))}."
    )
    undetected = [c["type"] for c in corruptions if check_status.get(DETECTORS.get(c["type"], ""), {}).get("corrupted") is not False]
    out.append(
        "3. **Coverage of the gate.** "
        + (
            "Every injected corruption was caught by its expected detector."
            if not undetected
            else f"Not caught by the expected detector: {', '.join(undetected)}."
        )
    )
    return out
