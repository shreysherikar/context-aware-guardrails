"""GxP compliance review — highlight non-compliant language and suggest corrections."""

from services.gxp.reviewer import GxpReviewer, review_text

__all__ = ["GxpReviewer", "review_text"]
