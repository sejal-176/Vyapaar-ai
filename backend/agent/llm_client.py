"""OpenAI SDK client configuration for LLM provider (Groq or compatible)."""
import os
from openai import OpenAI
from backend.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


def get_llm_client() -> OpenAI:
    """Instantiate OpenAI-compatible client.
    Provider is swappable via .env only.
    """
    api_key = os.getenv("LLM_API_KEY", LLM_API_KEY)
    base_url = os.getenv("LLM_BASE_URL", LLM_BASE_URL)
    return OpenAI(
        base_url=base_url,
        api_key=api_key or "missing_key",
        timeout=20.0,
    )


def get_model_name() -> str:
    return os.getenv("LLM_MODEL", LLM_MODEL)
