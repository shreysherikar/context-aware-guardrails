"""Trusted evidence corpus + retrieval (evidence plane only).

Approved-source material that generated claims will be verified against in a
later milestone. Loads a versioned corpus snapshot (YAML by default), returns
ranked RetrievalResults with full provenance (source_id, title, score,
corpus_version). No component here produces a PolicyAction or a
PolicyDecision; failures resolve conservatively to empty results.
"""
