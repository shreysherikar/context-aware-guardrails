"""Unified healthcare data sanitization (safe-context plane).

Produces sanitized representations for REWRITE. Never decides policy actions —
PolicyEngine remains the sole authority for ALLOW/REWRITE/REVIEW/BLOCK.
"""

from services.sanitization.engine import SanitizationEngine, SanitizationError
from services.sanitization.factory import get_sanitization_engine
from services.sanitization.models import (
    SanitizationFinding,
    SanitizationRequest,
    SanitizationResult,
)

__all__ = [
    "SanitizationEngine",
    "SanitizationError",
    "SanitizationFinding",
    "SanitizationRequest",
    "SanitizationResult",
    "get_sanitization_engine",
]
