from __future__ import annotations

from typing import Any

from flock_blocker.llm import llm_text
from flock_blocker.models import PolicyNote
from flock_blocker.tools.web_search import search_web

POLICY_SYSTEM = """You explain publicly reported ALPR policy for a lay audience.
Cover data retention, sharing across agencies, and known controversies only as they
appear in the provided search snippets. Cite the source titles. Do not give legal advice.
Do not discuss how to evade cameras or interfere with investigations.
"""


def run_policy(query: str) -> dict[str, Any]:
    search_query = (
        f"{query} Flock Safety ALPR data sharing retention FOIA "
        "city policy ICE"
    )
    error = None
    hits: list[dict[str, str]] = []
    try:
        hits = search_web(search_query, max_results=6)
    except Exception as exc:
        error = str(exc)

    notes = [
        PolicyNote(
            title=hit["title"],
            url=hit["url"],
            summary=hit["snippet"],
        )
        for hit in hits
        if hit.get("url")
    ]
    llm_summary = llm_text(
        POLICY_SYSTEM,
        f"User question: {query}\nSources: {[n.model_dump() for n in notes]}",
    )
    if llm_summary:
        narrative = llm_summary
    elif notes:
        narrative = "Public policy / reporting sources:\n" + "\n".join(
            f"- {note.title}: {note.summary} ({note.url})" for note in notes[:5]
        )
    else:
        narrative = (
            "No public policy results were returned. Try a city name, e.g. "
            "'What is Austin's ALPR data-retention policy?'"
        )
        if error:
            narrative += f" Lookup issue: {error}"
    return {"narrative": narrative, "notes": [n.model_dump() for n in notes]}
