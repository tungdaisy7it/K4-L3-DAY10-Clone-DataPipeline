from __future__ import annotations

import math
import random
from typing import Any

import pandas as pd

from core.utils import now_utc, write_json
from ingestion.cleaning import CLEAN_COLUMNS, add_derived_columns

CORRUPTION_SEED = 42
DROP_LATEST_RATIO = 0.20
BLANK_SUMMARY_ROWS = 3
NOISE_ROWS = 3
TRUNCATE_TITLE_ROWS = 3
TRUNCATED_TITLE_CHARS = 6
STALE_RATIO = 0.30
STALE_SHIFT_DAYS = 365
DUPLICATE_ROWS = 3
NOISE_TOKENS = ["#@!%", "&&**", "~^^~", "Ã¢â‚¬â„¢", "��", "<?!>", "$$%%"]


def _inject_noise(text: str, rng: random.Random) -> str:
    words = text.split()
    noisy: list[str] = []
    for position, word in enumerate(words):
        if position % 3 == 0:
            noisy.append(rng.choice(NOISE_TOKENS))
        noisy.append(word)
    return " ".join(noisy)


def _shift_date(value: str, days: int) -> str:
    return (pd.Timestamp(value) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Apply six controlled, reproducible corruptions to a clean dataframe and log them.

    Scenarios 2-5 target disjoint rows so each failure mode stays attributable.
    """
    rng = random.Random(CORRUPTION_SEED)
    source = df.copy().reset_index(drop=True)
    source["authors"] = source["authors"].apply(list)
    source["categories"] = source["categories"].apply(list)
    input_rows = len(source)
    log: list[dict[str, Any]] = []

    # 1. Drop latest records: the freshest papers never reach the index.
    drop_count = max(1, math.ceil(input_rows * DROP_LATEST_RATIO)) if input_rows > 5 else 0
    latest = source.sort_values(["published", "paper_id"], ascending=[False, True]).head(drop_count)
    corrupted = source.drop(index=latest.index).reset_index(drop=True)
    log.append(
        {
            "type": "drop_latest_records",
            "description": f"Dropped the {drop_count} most recently published papers ({DROP_LATEST_RATIO:.0%}).",
            "params": {"ratio": DROP_LATEST_RATIO},
            "affected_count": drop_count,
            "affected_paper_ids": latest["paper_id"].tolist(),
        }
    )

    positions = list(range(len(corrupted)))
    rng.shuffle(positions)
    stale_count = math.ceil(len(corrupted) * STALE_RATIO)
    plan = {}
    cursor = 0
    for name, size in (
        ("blank_summary", BLANK_SUMMARY_ROWS),
        ("inject_noise", NOISE_ROWS),
        ("truncate_title", TRUNCATE_TITLE_ROWS),
        ("stale_date", stale_count),
    ):
        plan[name] = positions[cursor : cursor + size]
        cursor += size

    # 2. Blank summary: scraper returned an empty abstract.
    rows = plan["blank_summary"]
    corrupted.loc[rows, "summary"] = ""
    log.append(
        {
            "type": "blank_summary",
            "description": "Replaced the summary with an empty string.",
            "params": {"rows": BLANK_SUMMARY_ROWS},
            "affected_count": len(rows),
            "affected_paper_ids": corrupted.loc[rows, "paper_id"].tolist(),
        }
    )

    # 3. Inject noise: encoding garbage / junk tokens inside the summary.
    rows = plan["inject_noise"]
    for row in rows:
        corrupted.at[row, "summary"] = _inject_noise(corrupted.at[row, "summary"], rng)
    log.append(
        {
            "type": "inject_noise",
            "description": "Inserted junk/mojibake tokens before every third word of the summary.",
            "params": {"rows": NOISE_ROWS, "tokens": NOISE_TOKENS},
            "affected_count": len(rows),
            "affected_paper_ids": corrupted.loc[rows, "paper_id"].tolist(),
        }
    )

    # 4. Truncate title below 8 characters.
    rows = plan["truncate_title"]
    originals = corrupted.loc[rows, "title"].tolist()
    corrupted.loc[rows, "title"] = [title[:TRUNCATED_TITLE_CHARS] for title in originals]
    log.append(
        {
            "type": "truncate_title",
            "description": f"Truncated the title to {TRUNCATED_TITLE_CHARS} characters.",
            "params": {"rows": TRUNCATE_TITLE_ROWS, "max_chars": TRUNCATED_TITLE_CHARS},
            "affected_count": len(rows),
            "affected_paper_ids": corrupted.loc[rows, "paper_id"].tolist(),
            "examples": [
                {"before": before, "after": before[:TRUNCATED_TITLE_CHARS]} for before in originals
            ],
        }
    )

    # 5. Stale date: publication date pushed one year back.
    rows = plan["stale_date"]
    for row in rows:
        corrupted.at[row, "published"] = _shift_date(corrupted.at[row, "published"], STALE_SHIFT_DAYS)
        corrupted.at[row, "updated"] = _shift_date(corrupted.at[row, "updated"], STALE_SHIFT_DAYS)
        corrupted.at[row, "age_days"] = int(corrupted.at[row, "age_days"]) + STALE_SHIFT_DAYS
    log.append(
        {
            "type": "stale_date",
            "description": f"Shifted published/updated back by {STALE_SHIFT_DAYS} days.",
            "params": {"ratio": STALE_RATIO, "shift_days": STALE_SHIFT_DAYS},
            "affected_count": len(rows),
            "affected_paper_ids": corrupted.loc[rows, "paper_id"].tolist(),
        }
    )

    # 6. Duplicate rows: the same paper indexed twice.
    duplicate_positions = sorted(rng.sample(range(len(corrupted)), k=min(DUPLICATE_ROWS, len(corrupted))))
    duplicates = corrupted.loc[duplicate_positions].copy()
    corrupted = pd.concat([corrupted, duplicates], ignore_index=True)
    log.append(
        {
            "type": "duplicate_rows",
            "description": "Appended exact copies of existing rows.",
            "params": {"rows": DUPLICATE_ROWS},
            "affected_count": len(duplicates),
            "affected_paper_ids": duplicates["paper_id"].tolist(),
        }
    )

    # 7. Rebuild derived columns so the corruption reaches `text_for_embedding`.
    corrupted = add_derived_columns(corrupted)[CLEAN_COLUMNS]

    write_json(
        output_log_path,
        {
            "generated_at": now_utc().isoformat(),
            "seed": CORRUPTION_SEED,
            "input_rows": input_rows,
            "output_rows": len(corrupted),
            "corruption_types": len(log),
            "corruptions": log,
        },
    )
    return corrupted
