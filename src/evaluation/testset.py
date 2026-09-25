from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json

TEST_SET_SIZE = 10
MIN_DOCUMENTS = 4
QUESTION_TYPES = ["summary", "authors", "date", "categories"]
REQUIRED_COLUMNS = {
    "paper_id", "title", "summary", "authors_joined", "published", "categories_joined",
}

# Phrasings must stay aligned with `retrieval.qa._extract_answer`.
QUESTION_TEMPLATES = {
    "summary": "What is the summary of the paper '{title}'?",
    "authors": "Who authored the paper '{title}'?",
    "date": "When was the paper '{title}' published?",
    "categories": "What categories does the paper '{title}' belong to?",
}


def _ground_truth(row: pd.Series, question_type: str) -> str:
    if question_type == "summary":
        return first_sentence(row["summary"])
    if question_type == "authors":
        return row["authors_joined"]
    if question_type == "date":
        return row["published"]
    return row["categories_joined"]


def _validate_input(df: pd.DataFrame) -> None:
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"Clean dataframe is missing required columns: {", ".join(missing)}.")


def _has_ground_truth(row: pd.Series, question_type: str) -> bool:
    value = _ground_truth(row, question_type)
    return pd.notna(value) and bool(str(value).strip())


def _nearest_eligible_position(papers: pd.DataFrame, preferred_position: int, question_type: str, used_positions: set[int]) -> int:
    candidates = [position for position in range(len(papers)) if position not in used_positions and _has_ground_truth(papers.iloc[position], question_type)]
    if not candidates:
        raise ValueError(f"No unused paper has a non-empty ground truth for question type {question_type!r}.")
    return min(candidates, key=lambda position: (abs(position - preferred_position), position))


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build a fixed benchmark from the clean dataframe.

    Papers are picked at evenly spaced positions of the newest-first ordering so the
    set covers fresh and older papers; question types rotate summary -> authors -> date
    -> categories. The same file is reused for baseline, corrupted and repaired runs.
    """
    _validate_input(df)
    papers = df.drop_duplicates(subset="paper_id").sort_values(["published", "paper_id"], ascending=[False, True])
    # QA extracts the title between single quotes, so titles containing "'" cannot be asked about.
    usable_id = papers["paper_id"].notna() & papers["paper_id"].astype(str).str.strip().ne("")
    usable_title = papers["title"].notna() & papers["title"].astype(str).str.strip().ne("")
    no_apostrophe = ~papers["title"].fillna("").astype(str).str.contains("'", regex=False)
    papers = papers[usable_id & usable_title & no_apostrophe].reset_index(drop=True)
    if len(papers) < MIN_DOCUMENTS:
        raise ValueError(f"Need at least {MIN_DOCUMENTS} clean papers to build a test set, got {len(papers)}.")

    size = min(TEST_SET_SIZE, len(papers))
    step = (len(papers) - 1) / (size - 1) if size > 1 else 0
    preferred_picks = [round(i * step) for i in range(size)]

    test_set: list[dict[str, Any]] = []
    used_positions: set[int] = set()
    for number, preferred_position in enumerate(preferred_picks, start=1):
        question_type = QUESTION_TYPES[(number - 1) % len(QUESTION_TYPES)]
        position = _nearest_eligible_position(papers, preferred_position, question_type, used_positions)
        used_positions.add(position)
        row = papers.iloc[position]
        test_set.append(
            {
                "id": f"eval_{number:03d}",
                "question_type": question_type,
                "question": QUESTION_TEMPLATES[question_type].format(title=row["title"]),
                "ground_truth": _ground_truth(row, question_type),
                "ground_truth_doc_ids": [row["paper_id"]],
            }
        )

    write_json(output_path, test_set)
    return test_set
