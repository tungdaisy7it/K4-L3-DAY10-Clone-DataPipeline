from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from pipelines.common import file_sha256, save_dataframe
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex


def load_or_build_test_set(df: pd.DataFrame, settings: Settings) -> list[dict[str, Any]]:
    """Keep the benchmark fixed across runs; rebuild only on request or when it no longer matches the corpus."""
    path = settings.paths.eval_testset
    if path.exists() and not settings.refresh_test_set:
        test_set = read_json(path)
        known_ids = set(df["paper_id"])
        if test_set and all(set(item["ground_truth_doc_ids"]) <= known_ids for item in test_set):
            print(f"  reusing fixed test set ({len(test_set)} questions)")
            return test_set
        print("  existing test set references unknown papers -> rebuilding")
    test_set = build_test_set(df, path)
    print(f"  built test set ({len(test_set)} questions)")
    return test_set


def run_agent_demo(settings: Settings, index: LocalEmbeddingIndex, questions: list[str]) -> list[dict[str, Any]]:
    demo: list[dict[str, Any]] = []
    try:
        agent = build_agent(settings, index)
    except Exception as exc:
        agent = None
        error = f"agent unavailable: {type(exc).__name__}: {exc}"[:300]
    for question in questions:
        if agent is None:
            demo.append({"question": question, "answer": None, "error": error})
            continue
        try:
            demo.append({"question": question, "answer": run_agent_question(agent, question), "error": None})
        except Exception as exc:
            demo.append({"question": question, "answer": None, "error": f"{type(exc).__name__}: {exc}"[:300]})
    write_json(settings.paths.demo_answers, demo)
    return demo


def main(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    run_date = now_utc()

    print("[phase1] 1/7 Ingestion (raw preservation)")
    records = fetch_source_records(settings)
    print(f"  {len(records)} raw records -> {settings.paths.raw_records_json.name}")

    print("[phase1] 2/7 Cleaning")
    df = build_clean_dataframe(records, run_date)
    save_dataframe(df, settings.paths.clean_csv, settings.paths.clean_json)
    print(f"  {len(df)} clean rows -> {settings.paths.clean_csv.name}")

    print("[phase1] 3/7 Quality gate (GX 1.x) + freshness SLA")
    quality = run_data_quality_checks(df, settings, "baseline")
    freshness = build_freshness_report(df, settings, settings.paths.freshness_report)
    print(f"  quality success={quality['success']} | is_fresh={freshness['is_fresh']} (stale_ratio={freshness['stale_ratio']})")
    if not quality["success"]:
        raise SystemExit(f"[phase1] Quality gate FAILED {quality['failed_checks']}; refusing to index bad data.")
    if not freshness["is_fresh"]:
        print(f"  [WARN] {freshness['alert']}")

    print("[phase1] 4/7 Embedding + ChromaDB index")
    index = LocalEmbeddingIndex.build(df, settings, settings.paths.embeddings_json)
    print(f"  collection '{index.collection_name}' holds {index.collection.count()} vectors")

    print("[phase1] 5/7 Evaluation set")
    test_set = load_or_build_test_set(df, settings)

    print("[phase1] 6/7 Baseline evaluation")
    bundle = evaluate_pipeline(
        settings,
        index,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.baseline_answers,
    )
    summary = bundle.summary

    print("[phase1] 7/7 Agent demo + report")
    demo = run_agent_demo(
        settings,
        index,
        [test_set[0]["question"], "Which indexed papers discuss data quality gates for RAG pipelines?"],
    )
    source_summary = {
        "source_api": settings.source_api,
        "mode": "live Crossref API (REFRESH_SOURCE=1)" if settings.refresh_source else "offline snapshot",
        "query": settings.source_query,
        "filter": settings.source_filter,
        "max_results": settings.max_results,
        "raw_records": len(records),
        "clean_rows": len(df),
        "dropped_by_cleaning": len(records) - len(df),
        "run_date": run_date.date().isoformat(),
        "raw_response_sha256": file_sha256(settings.paths.raw_api_response)[:16],
        "embedding_model": settings.embedding_model,
        "collection": index.collection_name,
        "top_k": settings.top_k,
        "llm_provider": f"{settings.llm_provider} / {settings.model_name}",
    }
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary,
        summary,
        quality,
        freshness,
        answers=bundle.answers,
        agent_demo=demo,
    )

    print(
        "[phase1] DONE "
        f"hit_rate={summary['retrieval_hit_rate']:.4f} token_f1={summary['mean_token_f1']:.4f} "
        f"judge_acc={summary['judge_accuracy']:.4f} judge={summary['judge_backend']}"
    )
    print(f"  report -> {settings.paths.baseline_report.relative_to(settings.paths.project_dir).as_posix()}")
    return summary
