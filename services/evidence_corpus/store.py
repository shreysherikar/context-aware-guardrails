"""Trusted evidence stores — where the approved corpus comes from.

Mirrors services/optical_guardrail/providers.py: an abstract interface plus a
deterministic, dependency-free implementation. The default implementation
reads a version-controlled YAML file; a second requires no system binaries and
exists for tests. Loading validates the whole corpus up front (including the
unique-source-id invariant) so a malformed corpus fails loudly here rather
than leaking ambiguous provenance into later stages.

Stores deliberately re-load on every call (like PolicyEngine.reload()): no
hidden global state, every decision reproducible from explicitly named inputs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

import yaml

from services.evidence_corpus.models import EvidenceCorpus, EvidenceDocument


class CorpusValidationError(Exception):
    """Raised when a trusted corpus cannot be loaded or fails validation."""


class EvidenceStore(ABC):
    """Abstract source of the trusted corpus. Returns snapshots, never decisions."""

    @abstractmethod
    def load(self) -> EvidenceCorpus:
        """Return the full corpus snapshot. Raises CorpusValidationError on failure."""


class InMemoryEvidenceStore(EvidenceStore):
    """Directly supplied corpus — the offline/test analogue of MockOCRProvider."""

    def __init__(
        self,
        documents: Sequence[EvidenceDocument],
        *,
        version: str = "in-memory",
    ):
        self._corpus = EvidenceCorpus(version=version, documents=list(documents))

    def load(self) -> EvidenceCorpus:
        return self._corpus


class YamlFileEvidenceStore(EvidenceStore):
    """Loads a corpus snapshot from a version-controlled YAML file."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load(self) -> EvidenceCorpus:
        try:
            with open(self.path) as f:
                raw = yaml.safe_load(f)
        except FileNotFoundError as exc:
            raise CorpusValidationError(f"Evidence corpus file not found: {self.path}") from exc
        except yaml.YAMLError as exc:
            raise CorpusValidationError(f"Evidence corpus is malformed YAML: {exc}") from exc

        # An empty or sources-less snapshot would silently disable verification
        # downstream; require the key explicitly instead of defaulting to [].
        if not isinstance(raw, dict) or not raw.get("sources"):
            raise CorpusValidationError(
                f"Evidence corpus must be a mapping with a non-empty 'sources' list ({self.path})"
            )

        try:
            return EvidenceCorpus.model_validate(
                {
                    "version": (raw or {}).get("version"),
                    "documents": (raw or {}).get("sources", []),
                }
            )
        except Exception as exc:  # noqa: BLE001 - pydantic errors are the expected failure mode
            raise CorpusValidationError(f"Evidence corpus is invalid ({self.path}): {exc}") from exc
