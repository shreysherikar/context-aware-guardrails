"""Internet search for the guardrail agent (DuckDuckGo — no API key)."""

from __future__ import annotations

import asyncio
import logging
import os
import re

from services.web_bridge.models import WebSearchResult, WebSource

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RESULTS = 5


def _max_results() -> int:
    return int(os.getenv("WEB_SEARCH_MAX_RESULTS", _DEFAULT_MAX_RESULTS))


def _search_sync(query: str, *, max_results: int) -> list[WebSource]:
    """Run DuckDuckGo text search (prefers the `ddgs` package)."""
    last_error: Exception | None = None
    for factory in (_ddgs_client, _legacy_ddgs_client):
        try:
            sources = factory(query, max_results=max_results)
            if sources:
                return sources
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.debug("Search backend failed: %s", exc)
    if last_error:
        raise last_error
    return []


def _parse_result_item(item: dict) -> WebSource | None:
    title = (item.get("title") or "").strip()
    url = (item.get("href") or item.get("link") or item.get("url") or "").strip()
    body = (item.get("body") or item.get("snippet") or "").strip()
    if title and url:
        return WebSource(title=title, url=url, snippet=body)
    return None


def _collect_results(items, *, max_results: int) -> list[WebSource]:
    sources: list[WebSource] = []
    for item in items:
        parsed = _parse_result_item(item)
        if parsed:
            sources.append(parsed)
        if len(sources) >= max_results:
            break
    return sources


def _ddgs_client(query: str, *, max_results: int) -> list[WebSource]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        return _collect_results(ddgs.text(query, max_results=max_results), max_results=max_results)


def _legacy_ddgs_client(query: str, *, max_results: int) -> list[WebSource]:
    from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        return _collect_results(ddgs.text(query, max_results=max_results), max_results=max_results)


def _build_context(sources: list[WebSource]) -> str:
    if not sources:
        return ""
    parts: list[str] = []
    for i, src in enumerate(sources, start=1):
        parts.append(f"[{i}] {src.title}\nURL: {src.url}\n{src.snippet}")
    return "\n\n".join(parts)


async def search_web(query: str, *, max_results: int | None = None) -> WebSearchResult:
    """Search the public web and return snippets for LLM grounding."""
    limit = max_results or _max_results()
    clean = query.strip()
    if not clean:
        return WebSearchResult(query=query, succeeded=False, error="Empty search query.")

    try:
        sources = await asyncio.to_thread(_search_sync, clean, max_results=limit)
        context = _build_context(sources)
        return WebSearchResult(
            query=clean,
            sources=sources,
            context=context,
            succeeded=bool(sources),
            error=None if sources else "No search results found.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Web search failed for query=%r", clean[:80])
        return WebSearchResult(
            query=clean,
            succeeded=False,
            error="Web search is temporarily unavailable.",
        )


_WEB_TRIGGER_PATTERNS = [
    r"\bsearch (the )?(web|internet)\b",
    r"\blook up\b",
    r"\bfind (online|on the web)\b",
    r"\blatest (news|updates|on)\b",
    r"\bcurrent (news|status|regulation)\b",
    r"\bwhat(?:'s| is) (?:the )?latest\b",
    r"\bnews about\b",
    r"\bonline research\b",
]


def should_search_web(prompt: str, *, explicit: bool = False) -> bool:
    """Decide whether to run a web search for this prompt."""
    if explicit:
        return True
    if os.getenv("WEB_SEARCH_AUTO", "true").strip().lower() in {"false", "0", "no"}:
        return False
    lower = prompt.lower()
    return any(re.search(p, lower) for p in _WEB_TRIGGER_PATTERNS)


def augment_prompt_with_web_context(*, user_prompt: str, web: WebSearchResult) -> str:
    """Inject search snippets into the LLM prompt (post-guardrail only)."""
    if not web.succeeded or not web.context:
        return user_prompt
    return (
        f"{user_prompt}\n\n"
        "---\n"
        "Public web search results (for background only — not approved promotional claims):\n"
        f"{web.context}\n"
        "---\n"
        "Answer the user using these sources where relevant. Cite source titles or URLs. "
        "If the sources are insufficient, say so. Do not invent clinical or regulatory claims."
    )
