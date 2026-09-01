"""Web bridge models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WebSource(BaseModel):
    title: str
    url: str
    snippet: str = ""


class WebSearchResult(BaseModel):
    query: str
    sources: list[WebSource] = Field(default_factory=list)
    context: str = ""
    succeeded: bool = False
    error: str | None = None
