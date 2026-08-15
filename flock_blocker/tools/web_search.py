from __future__ import annotations

from flock_blocker.config import get_settings


def search_web(query: str, max_results: int = 6) -> list[dict[str, str]]:
    """Search the public web for reported ALPR / Flock camera coverage.

    Uses DuckDuckGo via the `ddgs` package (no API key). Results are news and
    public pages only — this does not access Flock, police, or private systems.
    """
    settings = get_settings()
    try:
        from ddgs import DDGS
    except ImportError:  # pragma: no cover
        from duckduckgo_search import DDGS  # type: ignore

    results: list[dict[str, str]] = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, max_results=max_results):
            results.append(
                {
                    "title": item.get("title") or "",
                    "url": item.get("href") or item.get("url") or "",
                    "snippet": item.get("body") or item.get("snippet") or "",
                    "user_agent": settings.user_agent,
                }
            )
    return results
