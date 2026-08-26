"""Sanitization engine factory."""

from __future__ import annotations

from services.sanitization.engine import SanitizationEngine


def get_sanitization_engine() -> SanitizationEngine:
    """Return the default deterministic sanitization engine."""
    return SanitizationEngine()
