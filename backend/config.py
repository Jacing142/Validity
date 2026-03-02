import logging
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    LLM_PROVIDER: Literal["openai", "anthropic", "mock"] = "openai"
    LLM_API_KEY: str = ""
    LLM_MODEL_COMPLEX: str = "gpt-4o"
    LLM_MODEL_STANDARD: str = "gpt-4o-mini"

    # Search
    SEARCH_PROVIDER: Literal["serper", "tavily", "you", "mock"] = "serper"
    SEARCH_API_KEY: str = ""

    # Application
    MAX_CLAIMS: int = 5
    MAX_SOURCES_PER_CLAIM: int = 5
    LOG_LEVEL: str = "info"


settings = Settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def get_llm(complexity: str = "standard"):
    """Return a LangChain chat model based on provider and complexity level.

    Args:
        complexity: "high" -> complex model, "standard" -> standard model
    """
    model = settings.LLM_MODEL_COMPLEX if complexity == "high" else settings.LLM_MODEL_STANDARD

    if settings.LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, api_key=settings.LLM_API_KEY, temperature=0)

    elif settings.LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, api_key=settings.LLM_API_KEY, temperature=0)

    elif settings.LLM_PROVIDER == "mock":
        from backend.llm.mock import MockChatModel

        return MockChatModel()

    else:
        raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")


def get_search_client():
    """Return the configured search client."""
    if settings.SEARCH_PROVIDER == "serper":
        from backend.search.serper import SerperSearchClient

        return SerperSearchClient(api_key=settings.SEARCH_API_KEY)

    elif settings.SEARCH_PROVIDER == "tavily":
        from backend.search.tavily import TavilySearchClient

        return TavilySearchClient()

    elif settings.SEARCH_PROVIDER == "you":
        from backend.search.you import YouSearchClient

        return YouSearchClient()

    elif settings.SEARCH_PROVIDER == "mock":
        from backend.search.mock import MockSearchClient

        return MockSearchClient()

    else:
        raise ValueError(f"Unsupported search provider: {settings.SEARCH_PROVIDER}")
