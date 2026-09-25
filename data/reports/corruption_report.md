# Corruption Report — Baseline vs Corrupted vs Repaired

_Generated at 2026-09-25T08:56:57.986861+00:00 by `script/run_corruption_flow.py`. All three states are evaluated on the same `data/eval/test_set.json`._

## 1. Three-state comparison

| Metric / signal | Baseline | Corrupted | Repaired | Δ corruption | Recovery |
| --- | --- | --- | --- | --- | --- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | -0.2000 | 100% |
| `mean_token_f1` | 1.0000 | 0.7519 | 1.0000 | -0.2481 | 100% |
| `judge_accuracy` | 1.0000 | 0.8000 | 1.0000 | -0.2000 | 100% |
| `mean_judge_score` | 5 | 4.2000 | 5 | -0.8000 | 100% |
| Rows in dataset | 24 | 22 | 24 |  |  |
| Quality gate | PASS (0 failed) | FAIL (5 failed) | PASS (0 failed) |  |  |
| Source coverage | 1.0000 | 0.7917 | 1.0000 |  |  |
| Freshness is_fresh | PASS | FAIL | PASS |  |  |
| Stale ratio | 0.0417 | 0.3182 | 0.0417 |  |  |
| Latest published | 2026-07-22 | 2026-06-12 | 2026-07-22 |  |  |

_Recovery = (repaired − corrupted) / (baseline − corrupted)._

## 2. Observability signals per check

| Check | Baseline | Corrupted | Repaired |
| --- | --- | --- | --- |
| `expect_table_row_count_to_be_between` | PASS | PASS | PASS |
| `expect_column_values_to_not_be_null(paper_id)` | PASS | PASS | PASS |
| `expect_column_values_to_be_unique(paper_id)` | PASS | FAIL | PASS |
| `expect_column_values_to_not_be_null(title)` | PASS | PASS | PASS |
| `expect_column_value_lengths_to_be_between(title)` | PASS | FAIL | PASS |
| `expect_column_values_to_not_be_null(summary)` | PASS | PASS | PASS |
| `expect_column_value_lengths_to_be_between(summary)` | PASS | FAIL | PASS |
| `expect_column_values_to_not_match_regex(summary)` | PASS | FAIL | PASS |
| `expect_column_values_to_not_be_null(published)` | PASS | PASS | PASS |
| `expect_column_values_to_match_regex(published)` | PASS | PASS | PASS |
| `expect_column_values_to_not_be_null(text_for_embedding)` | PASS | PASS | PASS |
| `source_reconciliation` | PASS | FAIL | PASS |
| `freshness_sla` | PASS | FAIL | PASS |

## 3. Injected corruptions and detection

Seed `42` — 24 clean rows → 22 corrupted rows (`data/results/corruption_log.json`).

| Corruption | What changed | Rows | Expected detector | Detected? |
| --- | --- | --- | --- | --- |
| `drop_latest_records` | Dropped the 5 most recently published papers (20%). | 5 | `source_reconciliation` | YES |
| `blank_summary` | Replaced the summary with an empty string. | 3 | `expect_column_value_lengths_to_be_between(summary)` | YES |
| `inject_noise` | Inserted junk/mojibake tokens before every third word of the summary. | 3 | `expect_column_values_to_not_match_regex(summary)` | YES |
| `truncate_title` | Truncated the title to 6 characters. | 3 | `expect_column_value_lengths_to_be_between(title)` | YES |
| `stale_date` | Shifted published/updated back by 365 days. | 6 | `freshness_sla` | YES |
| `duplicate_rows` | Appended exact copies of existing rows. | 3 | `expect_column_values_to_be_unique(paper_id)` | YES |

## 4. Impact by question type

| question_type | n | F1 base | F1 corrupt | F1 repair | Hit base | Hit corrupt | Hit repair |
| --- | --- | --- | --- | --- | --- | --- | --- |
| authors | 3 | 1.0000 | 0.6667 | 1.0000 | 1.0000 | 0.6667 | 1.0000 |
| categories | 2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| date | 2 | 1.0000 | 0.5000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| summary | 3 | 1.0000 | 0.8395 | 1.0000 | 1.0000 | 0.6667 | 1.0000 |

## 5. Per-question root cause

| id | type | Corruption on ground-truth doc | F1 base | F1 corrupt | F1 repair | Hit corrupt | Corrupted answer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| eval_001 | summary | drop_latest_records | 1.0000 | 0.7407 | 1.0000 | FAIL | An extended empirical study on tatic benchmarks fail to capt |
| eval_002 | authors | drop_latest_records | 1.0000 | 0.0000 | 1.0000 | FAIL | Anh Tran, Quoc Pham |
| eval_003 | date | none | 1.0000 | 1.0000 | 1.0000 | PASS | 2026-06-12 |
| eval_004 | categories | none | 1.0000 | 1.0000 | 1.0000 | PASS | Information Retrieval, Natural Language Processing |
| eval_005 | summary | inject_noise | 1.0000 | 0.8889 | 1.0000 | PASS | $$%% An extended empirical #@!% study on single $$%% LLM is  |
| eval_006 | authors | duplicate_rows | 1.0000 | 1.0000 | 1.0000 | PASS | Tuan Phan, Mai Bui |
| eval_007 | date | stale_date | 1.0000 | 0.0000 | 1.0000 | PASS | 2025-06-03 |
| eval_008 | categories | blank_summary | 1.0000 | 1.0000 | 1.0000 | PASS | Artificial Intelligence, Information Retrieval |
| eval_009 | summary | inject_noise | 1.0000 | 0.8889 | 1.0000 | PASS | ~^^~ Connecting LLMs directly #@!% to raw warehouse #@!% tab |
| eval_010 | authors | stale_date | 1.0000 | 1.0000 | 1.0000 | PASS | Tuan Phan, Mai Bui |

## 6. Repair verification

| Field | Value |
| --- | --- |
| trigger | gate tripped: quality check failed: expect_column_values_to_be_unique(paper_id); quality check failed: expect_column_value_lengths_to_be_between(title); quality check failed: expect_column_value_lengths_to_be_between(summary); quality check failed: expect_column_values_to_not_match_regex(summary); quality check failed: source_reconciliation; freshness SLA breached: 7/22 papers older than 180 days (> 25%); refresh the source. |
| source | data/raw/crossref_records.json |
| raw_records_sha256 | 87b6413046082aa8 |
| repaired_rows | 24 |
| repaired_fingerprint | ea92631af1cabd78 |
| idempotent (2 repair runs identical) | PASS |
| matches baseline content | PASS |
| repaired_collection | papers-repaired |
| repaired_vectors | 24 |

## 7. Analysis

1. **Corruption → quality signal → agent metric.** The corrupted dataset tripped 6 observability checks (`expect_column_values_to_be_unique(paper_id)`, `expect_column_value_lengths_to_be_between(title)`, `expect_column_value_lengths_to_be_between(summary)`, `expect_column_values_to_not_match_regex(summary)`, `source_reconciliation`, `freshness_sla`). Without the gate, the agent still answered every question without raising an error, but `retrieval_hit_rate` went 1.0000 → 0.8000 and `mean_token_f1` 1.0000 → 0.7519 — a silent failure.
2. **Repair → signal recovery → metric recovery.** Rebuilding from the raw snapshot left 0 failing checks (none); `retrieval_hit_rate` = 1.0000 and `mean_token_f1` = 1.0000 versus baseline 1.0000 / 1.0000.
3. **Coverage of the gate.** Every injected corruption was caught by its expected detector.
