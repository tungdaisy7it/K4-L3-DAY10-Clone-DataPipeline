from __future__ import annotations

from functools import lru_cache
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from core.config import Settings, normalized_provider, require_llm_credentials


@lru_cache(maxsize=4)
def _shared_rate_limiter(requests_per_minute: float) -> InMemoryRateLimiter:
    return InMemoryRateLimiter(requests_per_second=requests_per_minute / 60, check_every_n_seconds=0.5, max_bucket_size=1)


def _rate_limit_kwargs() -> dict:
    """Optional client-side throttle shared by every model instance, e.g. LLM_REQUESTS_PER_MINUTE=4 for free tiers."""
    value = os.getenv("LLM_REQUESTS_PER_MINUTE", "").strip()
    if not value or float(value) <= 0:
        return {}
    return {"rate_limiter": _shared_rate_limiter(float(value))}


def build_llm(settings: Settings, temperature: float = 0.0):
    provider = normalized_provider(settings)
    require_llm_credentials(settings)
    throttle = _rate_limit_kwargs()

    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=settings.model_name,
            google_api_key=settings.google_api_key,
            temperature=temperature,
            max_retries=6,
            **throttle,
        )
    if provider == "openai":
        return ChatOpenAI(
            model=settings.model_name,
            api_key=settings.openai_api_key,
            temperature=temperature,
            **throttle,
        )
    if provider == "anthropic":
        return ChatAnthropic(
            model=settings.model_name,
            api_key=settings.anthropic_api_key,
            temperature=temperature,
            **throttle,
        )
    if provider == "openrouter":
        return ChatOpenAI(
            model=settings.model_name,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=temperature,
            **throttle,
        )
    if provider == "ollama":
        return ChatOllama(
            model=settings.model_name,
            base_url=settings.ollama_base_url,
            temperature=temperature,
            **throttle,
        )
    if provider == "custom":
        return ChatOpenAI(
            model=settings.model_name,
            api_key=settings.custom_llm_api_key or "unused",
            base_url=settings.custom_llm_base_url,
            temperature=temperature,
            **throttle,
        )
    if provider == "mock":
        return MockChatModel(responses=["This is a mock response from the scholarly corpus."])
    raise RuntimeError(f"Unsupported LLM provider: {settings.llm_provider}")


class MockChatModel(FakeListChatModel):
    """Offline chat model; accepts tool binding so the LangChain agent can run without API keys."""

    def bind_tools(self, tools, **kwargs):
        return self
