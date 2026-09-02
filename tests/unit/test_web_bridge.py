"""Web bridge unit tests."""

from unittest.mock import patch

import pytest

from services.web_bridge.models import WebSearchResult, WebSource
from services.web_bridge.search import (
    augment_prompt_with_web_context,
    search_web,
    should_search_web,
)


def test_should_search_web_explicit():
    assert should_search_web("hello", explicit=True) is True


def test_should_search_web_trigger_phrase():
    assert should_search_web("Search the web for FDA AI guidance") is True
    assert should_search_web("Summarize our internal doc") is False


@pytest.mark.anyio
async def test_search_web_mocked():
    fake = [
        WebSource(title="Example", url="https://example.com", snippet="Snippet text"),
    ]

    with patch("services.web_bridge.search._search_sync", return_value=fake):
        result = await search_web("test query")

    assert result.succeeded is True
    assert len(result.sources) == 1
    assert "Example" in result.context


def test_augment_prompt_includes_context():
    web = WebSearchResult(
        query="q",
        sources=[WebSource(title="T", url="https://t.com", snippet="body")],
        context="[1] T\nURL: https://t.com\nbody",
        succeeded=True,
    )
    out = augment_prompt_with_web_context(user_prompt="What is X?", web=web)
    assert "What is X?" in out
    assert "https://t.com" in out
