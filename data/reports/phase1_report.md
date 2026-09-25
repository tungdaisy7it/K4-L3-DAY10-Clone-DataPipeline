# Phase 1 Report — Baseline Data Pipeline

_Generated at 2026-09-25T08:54:12.580282+00:00 by `script/run_phase1.py`._

## 1. Source & lineage

| Field | Value |
| --- | --- |
| source_api | Crossref REST API |
| mode | offline snapshot |
| query | agentic retrieval augmented generation large language model |
| filter | from-pub-date:2026-03-29,has-abstract:true |
| max_results | 24 |
| raw_records | 24 |
| clean_rows | 24 |
| dropped_by_cleaning | 0 |
| run_date | 2026-09-25 |
| raw_response_sha256 | d968be684bff7d7f |
| embedding_model | sentence-transformers/all-MiniLM-L6-v2 |
| collection | papers-baseline |
| top_k | 4 |
| llm_provider | gemini / gemini-3.5-flash-lite |

## 2. Baseline RAG metrics

| Metric | Value |
| --- | --- |
| samples | 10 |
| retrieval_hit_rate | 1.0000 |
| mean_token_f1 | 1.0000 |
| judge_accuracy | 1.0000 |
| mean_judge_score | 5 |
| judge_backend | llm |

Ragas: `{'skipped': 'Set RUN_RAGAS=1 to enable the slower Ragas pass.'}`

### Breakdown by question type

| question_type | n | hit_rate | token_f1 | judge_accuracy |
| --- | --- | --- | --- | --- |
| authors | 3 | 1.0000 | 1.0000 | 1.0000 |
| categories | 2 | 1.0000 | 1.0000 | 1.0000 |
| date | 2 | 1.0000 | 1.0000 | 1.0000 |
| summary | 3 | 1.0000 | 1.0000 | 1.0000 |

### Per-question results

| id | type | hit | token_f1 | judge | answer |
| --- | --- | --- | --- | --- | --- |
| eval_001 | summary | PASS | 1.0000 | 5 | Static benchmarks fail to capture domain drift in enterprise knowledge bases. |
| eval_002 | authors | PASS | 1.0000 | 5 | Kien Duong, Vy Ly |
| eval_003 | date | PASS | 1.0000 | 5 | 2026-06-12 |
| eval_004 | categories | PASS | 1.0000 | 5 | Information Retrieval, Natural Language Processing |
| eval_005 | summary | PASS | 1.0000 | 5 | An extended empirical study on single LLM is susceptible to confirmation bias wh |
| eval_006 | authors | PASS | 1.0000 | 5 | Tuan Phan, Mai Bui |
| eval_007 | date | PASS | 1.0000 | 5 | 2026-06-03 |
| eval_008 | categories | PASS | 1.0000 | 5 | Artificial Intelligence, Information Retrieval |
| eval_009 | summary | PASS | 1.0000 | 5 | Connecting LLMs directly to raw warehouse tables often results in schema misunde |
| eval_010 | authors | PASS | 1.0000 | 5 | Tuan Phan, Mai Bui |

## 3. Data quality gate (Great Expectations 1.x)

- Engine: great_expectations 1.23.1 (ephemeral context)
- Rows validated: 24
- **Gate status: PASS** (12/12 checks passed)

| Check | Column | Threshold | Status | Observed |
| --- | --- | --- | --- | --- |
| expect_table_row_count_to_be_between | table | min_value=5, max_value=5000 | PASS | 24 |
| expect_column_values_to_not_be_null | paper_id | - | PASS | 0 unexpected |
| expect_column_values_to_be_unique | paper_id | - | PASS | 0 unexpected |
| expect_column_values_to_not_be_null | title | - | PASS | 0 unexpected |
| expect_column_value_lengths_to_be_between | title | min_value=8 | PASS | 0 unexpected |
| expect_column_values_to_not_be_null | summary | - | PASS | 0 unexpected |
| expect_column_value_lengths_to_be_between | summary | min_value=30 | PASS | 0 unexpected |
| expect_column_values_to_not_match_regex | summary | regex=[#@!%&*~^$<>?]{2,}|�|Ã | PASS | 0 unexpected |
| expect_column_values_to_not_be_null | published | - | PASS | 0 unexpected |
| expect_column_values_to_match_regex | published | regex=^\d{4}-\d{2}-\d{2}$ | PASS | 0 unexpected |
| expect_column_values_to_not_be_null | text_for_embedding | - | PASS | 0 unexpected |
| source_reconciliation | paper_id | coverage>=0.95 | PASS | coverage=1.0 (0 missing) |

## 4. Freshness SLA

| Field | Value |
| --- | --- |
| threshold_days | 180 |
| max_stale_ratio | 0.2500 |
| total_rows | 24 |
| stale_rows | 1 |
| stale_ratio | 0.0417 |
| latest_published | 2026-07-22 |
| oldest_published | 2026-03-28 |
| median_age_days | 110.5000 |
| is_fresh | PASS |

Age distribution (days): `0-30`: 0, `31-90`: 3, `91-180`: 20, `181-365`: 1, `>365`: 0

## 5. Agent demo (LangChain tool-calling agent)

- **Q:** What is the summary of the paper 'Continuous Benchmark Evaluation for Enterprise Retrieval Pipelines'?
  - **A:** **Summary of "Continuous Benchmark Evaluation for Enterprise Retrieval Pipelines"**

Static benchmarks fail to capture domain drift in enterprise knowledge bases. To address this, the paper establishes a synthetic test generator that automatically creates paired evaluation sets whenever new corpora are ingested, enabling continuous benchmark evaluation for enterprise retrieval pipelines.
- **Q:** Which indexed papers discuss data quality gates for RAG pipelines?
  - **A:** Based on the indexed papers in the corpus, the following papers specifically discuss data quality gates for Retrieval-Augmented Generation (RAG) pipelines:

1. **"Data Observability and Quality Gates for Production RAG Systems"** 
   * **Authors:** Anh Tran, Quoc Pham
   * **Published:** June 12, 2026
   * **Summary:** Discusses how silent data corruption in RAG pipelines degrades LLM answer faithfulness without throwing runtime errors, and introduces automated quality gates using Great Expectations 1.x to catch stale and malformed embeddings before serving.

2. **"Advanced Perspectives on Data Observability and Quality Gates for Production RAG Systems"** 
   * **Authors:** Anh Tran, Quoc Pham
   * **Published:** June 2, 2026
   * **Summary:** An extended empirical study by the same authors covering the same topic with further analysis on scaling parameters.
