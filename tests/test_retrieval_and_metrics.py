from __future__ import annotations

from dataclasses import replace

import pytest

from core.config import normalized_provider, require_llm_credentials
from core.utils import read_json
from evaluation import metrics
from evaluation.metrics import JudgeVerdict, evaluate_pipeline
from evaluation.testset import build_test_set
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex
from retrieval.llm import MockChatModel, build_llm
from retrieval.qa import answer_question


@pytest.fixture
def index(settings, clean_df):
    return LocalEmbeddingIndex.build(clean_df, settings, settings.paths.embeddings_json)


def test_index_build_search_lookup_and_reload(settings, clean_df, index):
    assert index.collection_name == settings.baseline_collection_name
    assert index.collection.count() == 24
    top = clean_df.iloc[0]
    results = index.search(top["title"], top_k=3)
    # Its "Advanced Perspectives on ..." sibling is a near-duplicate, so only require top-3 membership.
    assert len(results) == 3 and top["paper_id"] in [r.paper_id for r in results]
    assert all(0.0 <= r.score <= 1.0 for r in results)
    assert index.lookup(top["paper_id"].upper())["title"] == top["title"]
    assert index.lookup(top["title"])["paper_id"] == top["paper_id"]
    assert index.lookup("unknown") is None

    manifest = read_json(settings.paths.embeddings_json)
    assert manifest["persist_path"] == "data/chroma"
    reloaded = LocalEmbeddingIndex.load(settings)
    assert [r.paper_id for r in reloaded.search(top["title"], top_k=3)] == [r.paper_id for r in results]


def test_answer_question_types(settings, clean_df, index):
    row = clean_df.iloc[3]
    ask = lambda q: answer_question(q.format(t=row["title"]), settings, index)  # noqa: E731
    assert ask("Who authored the paper '{t}'?").answer == row["authors_joined"]
    assert ask("When was the paper '{t}' published?").answer == row["published"]
    assert ask("What categories does the paper '{t}' belong to?").answer == row["categories_joined"]
    summary = ask("What is the summary of the paper '{t}'?")
    assert summary.retrieved_doc_ids[0] == row["paper_id"]
    assert summary.answer and summary.answer in row["summary"]


def test_agent_runs_with_mock_provider(settings, index):
    agent = build_agent(settings, index)
    assert "mock response" in run_agent_question(agent, "Which papers discuss freshness?")


def test_agent_answer_normalizes_content_blocks():
    class Message:
        content = [{"type": "text", "text": "Hello "}, "world"]

    class Agent:
        def invoke(self, payload):
            return {"messages": [Message()]}

    class EmptyAgent:
        def invoke(self, payload):
            return {"messages": []}

    assert run_agent_question(Agent(), "q") == "Hello world"
    assert run_agent_question(EmptyAgent(), "q") == ""


def test_rate_limiter_is_shared_and_optional(settings, monkeypatch):
    from retrieval import llm

    monkeypatch.delenv("LLM_REQUESTS_PER_MINUTE", raising=False)
    assert llm._rate_limit_kwargs() == {}
    monkeypatch.setenv("LLM_REQUESTS_PER_MINUTE", "4")
    first, second = llm._rate_limit_kwargs(), llm._rate_limit_kwargs()
    assert first["rate_limiter"] is second["rate_limiter"]
    configured = replace(settings, llm_provider="gemini", model_name="m", google_api_key="test-key")
    assert build_llm(configured).rate_limiter is first["rate_limiter"]


def test_llm_router(settings):
    assert isinstance(build_llm(settings), MockChatModel)
    for provider, key_field in (
        ("openai", "openai_api_key"),
        ("anthropic", "anthropic_api_key"),
        ("gemini", "google_api_key"),
        ("openrouter", "openrouter_api_key"),
    ):
        configured = replace(settings, llm_provider=provider, model_name="some-model", **{key_field: "test-key"})
        assert build_llm(configured) is not None
        with pytest.raises(RuntimeError):
            require_llm_credentials(replace(configured, **{key_field: None}))
    assert build_llm(replace(settings, llm_provider="ollama", model_name="llama3")) is not None
    assert build_llm(replace(settings, llm_provider="custom", custom_llm_base_url="http://localhost:1")) is not None
    with pytest.raises(RuntimeError):
        build_llm(replace(settings, llm_provider="custom", custom_llm_base_url=None))
    with pytest.raises(RuntimeError):
        build_llm(replace(settings, llm_provider="unknown"))
    assert normalized_provider(replace(settings, llm_provider="Anthorpic")) == "anthropic"
    assert normalized_provider(replace(settings, llm_provider="custom-llm")) == "custom"


def test_token_f1_and_judge_fallback(settings):
    assert metrics._token_f1("a b c", "a b c") == 1.0
    assert metrics._token_f1("a b", "c d") == 0.0
    assert metrics._token_f1("", "x") == 0.0
    verdict = metrics._judge_answer(settings, "q", "alpha beta", "alpha beta")
    assert verdict.score == 5 and verdict.correct and verdict.reasoning.startswith("Fallback")
    assert metrics._judge_answer(settings, "q", "alpha beta", "gamma").score == 1


def test_judge_uses_llm_when_available(settings, monkeypatch):
    class StructuredStub:
        def with_structured_output(self, schema):
            return self

        def invoke(self, prompt):
            return JudgeVerdict(score=4, correct=True, reasoning="llm")

    monkeypatch.setattr(metrics, "build_llm", lambda **kwargs: StructuredStub())
    assert metrics._judge_answer(settings, "q", "r", "p").reasoning == "llm"
    assert metrics._judge_backend([{"judge": {"reasoning": "llm"}}]) == "llm"
    assert metrics._judge_backend([{"judge": {"reasoning": "llm"}}, {"judge": {"reasoning": "Fallback heuristic judge"}}]).startswith("mixed")


def test_evaluate_pipeline_on_clean_index(settings, clean_df, index, monkeypatch):
    build_test_set(clean_df, settings.paths.eval_testset)
    bundle = evaluate_pipeline(
        settings, index, settings.paths.eval_testset, settings.paths.baseline_metrics, settings.paths.baseline_answers
    )
    assert bundle.summary["samples"] == 10
    assert bundle.summary["retrieval_hit_rate"] == 1.0
    assert bundle.summary["mean_token_f1"] == 1.0
    assert bundle.summary["judge_backend"] == "heuristic_fallback"
    assert "skipped" in bundle.summary["ragas"]
    assert read_json(settings.paths.baseline_metrics)["samples"] == 10

    monkeypatch.setenv("RUN_RAGAS", "1")
    monkeypatch.setattr(metrics, "Dataset", None)
    assert "error" in metrics._run_ragas(settings, bundle.answers)
