"""Web bridge — search the internet and ground agent answers."""

from services.web_bridge.models import WebSearchResult, WebSource
from services.web_bridge.search import (
    augment_prompt_with_web_context,
    search_web,
    should_search_web,
)

__all__ = [
    "WebSearchResult",
    "WebSource",
    "augment_prompt_with_web_context",
    "search_web",
    "should_search_web",
]
