"""Evidence relationship assessment (evidence plane only).

Judges whether approved-source passages support, contradict, conflict with,
or are insufficient to judge one extracted claim. Returns structured metadata
only (EvidenceRelationshipResult); nothing here produces a PolicyAction or a
PolicyDecision, and failures degrade conservatively to INSUFFICIENT, never to
SUPPORTS.
"""
