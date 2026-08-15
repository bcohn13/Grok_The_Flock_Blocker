from __future__ import annotations

from typing import Any

from flock_blocker.config import get_settings


def get_chat_model() -> Any | None:
    """Return a LangChain chat model when an API key is configured."""
    settings = get_settings()
    if not settings.has_llm:
        return None
    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=settings.anthropic_model, temperature=0)
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=settings.openai_model, temperature=0)


def llm_text(system: str, user: str) -> str | None:
    model = get_chat_model()
    if model is None:
        return None
    from langchain_core.messages import HumanMessage, SystemMessage

    result = model.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = result.content
    if isinstance(content, str):
        return content
    return str(content)
