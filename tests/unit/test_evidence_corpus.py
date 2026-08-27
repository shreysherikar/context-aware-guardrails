"""Unit tests for the trusted evidence corpus + retrieval subsystem.

Pins the guarantees this plane must keep before the verification stage exists:

- structural constraint: nothing here can carry policy authority (checked via
  attributes, declared model fields, AND referenced identifiers — AST-level,
  so docstring mentions can't hide real usage)
- corpus snapshots validate loudly (unique source IDs, required fields/version)
- scoring is deterministic lexical coverage with strict reproducible ordering
- failures degrade to explicit empty results (absence of evidence can only
  push verification toward UNVERIFIABLE — the conservative direction)
- the shipped default YAML corpus parses offline and serves provenance
"""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

import services.evidence_corpus as ec_package
import services.evidence_corpus.models as ec_models
import services.evidence_corpus.retrieval as ec_retrieval
import services.evidence_corpus.store as ec_store
from domain.models import Claim, Evidence
from services.evidence_corpus.models import (
    RETRIEVAL_VERSION,
    EvidenceCorpus,
    EvidenceDocument,
    RetrievalResult,
    RetrievedEvidence,
)
from services.evidence_corpus.retrieval import (
    DEFAULT_EVIDENCE_CORPUS_PATH,
    DEFAULT_MAX_RESULTS,
    DEFAULT_MIN_SCORE,
    EvidenceRetriever,
    tokenize,
)
from services.evidence_corpus.store import (
    CorpusValidationError,
    EvidenceStore,
    InMemoryEvidenceStore,
    YamlFileEvidenceStore,
)

_FORBIDDEN_AUTHORITY_FIELDS = frozenset({"action", "decision", "policy_id", "policy_version"})
_PACKAGE_MODULES = (ec_package, ec_models, ec_retrieval, ec_store)


def _doc(
    source_id: str = "SRC-A",
    *,
    title: str = "Approved passage",
    text: str = "glyxtra renal dosing requires adjustment",
    topics: list[str] | None = None,
) -> EvidenceDocument:
    return EvidenceDocument(source_id=source_id, title=title, text=text, topics=topics or [])


def _retriever(
    documents: list[EvidenceDocument],
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    min_score: float = DEFAULT_MIN_SCORE,
) -> EvidenceRetriever:
    store = InMemoryEvidenceStore(documents, version="test-1.0")
    return EvidenceRetriever(store, max_results=max_results, min_score=min_score)


# --- structural constraint: evidence only, never a decision -------------------


def test_no_contract_instance_carries_policy_authority_attributes():
    samples: list[object] = [
        _doc(),
        EvidenceCorpus(version="1", documents=[_doc()]),
        RetrievedEvidence(source_id="s", text="t"),
        RetrievalResult(query="q"),
    ]
    for sample in samples:
        for field in _FORBIDDEN_AUTHORITY_FIELDS:
            assert not hasattr(sample, field)


def test_declared_model_fields_can_never_gain_authority_fields():
    models = [EvidenceDocument, EvidenceCorpus, RetrievedEvidence, RetrievalResult]
    for model in models:
        assert _FORBIDDEN_AUTHORITY_FIELDS.isdisjoint(model.model_fields), model.__name__


def test_package_modules_never_reference_policy_authority_identifiers():
    def identifiers(module_path: str) -> set[str]:
        tree = ast.parse(Path(module_path).read_text())
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                found.add(node.id)
            elif isinstance(node, ast.Attribute):
                found.add(node.attr)
        return found

    for module in _PACKAGE_MODULES:
        clash = identifiers(str(module.__file__)) & _FORBIDDEN_AUTHORITY_FIELDS
        assert not clash, f"{module.__name__} references {clash}"


def test_retrieved_evidence_still_satisfies_the_domain_evidence_contract():
    assert isinstance(RetrievedEvidence(source_id="s", text="t", confidence=0.5), Evidence)


def test_results_record_the_retriever_component_version():
    assert RetrievalResult(query="q").retriever_version == RETRIEVAL_VERSION


# --- corpus snapshot validation ------------------------------------------------


def test_duplicate_source_ids_are_rejected_at_validation_time():
    with pytest.raises(ValidationError):
        EvidenceCorpus(version="1", documents=[_doc("DUP"), _doc("DUP")])


@pytest.mark.parametrize(
    ("source_id", "title", "text"),
    [("", "t", "x"), ("id", "", "x"), ("id", "t", "")],
)
def test_required_document_fields_have_a_minimum_length(source_id, title, text):
    with pytest.raises(ValidationError):
        EvidenceDocument(source_id=source_id, title=title, text=text)


def test_in_memory_store_round_trips_ordering_and_is_repeatable():
    store = InMemoryEvidenceStore([_doc("B"), _doc("A")], version="9.9")

    first = store.load()
    second = store.load()

    assert first.version == "9.9"
    assert [document.source_id for document in first.documents] == ["B", "A"]
    assert second == first


def _write(tmp_path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_yaml_store_loads_versioned_sources(tmp_path):
    body = (
        'version: "2.0"\n'
        "sources:\n"
        "  - source_id: S-ONE\n"
        "    title: First\n"
        "    text: alpha beta\n"
        "    topics: [alpha]\n"
        "  - source_id: S-TWO\n"
        "    title: Second\n"
        "    text: gamma\n"
    )
    corpus = YamlFileEvidenceStore(_write(tmp_path, "ok.yaml", body)).load()

    assert corpus.version == "2.0"
    assert [document.source_id for document in corpus.documents] == ["S-ONE", "S-TWO"]
    assert corpus.documents[0].topics == ["alpha"]
    assert corpus.documents[1].topics == []


@pytest.mark.parametrize(
    "body",
    [
        # duplicate source_id across two entries
        'version: "1"\nsources:\n'
        "  - {source_id: D, title: t, text: x}\n  - {source_id: D, title: u, text: y}\n",
        # missing version entirely
        "sources: []\n",
        # empty version (min_length=1)
        'version: ""\nsources: []\n',
        # wrong top-level key (documents silently empty is NOT tolerated)
        "version: '1'\ncorpus: []\n",
        # malformed YAML
        "version: [unterminated\n",
    ],
)
def test_invalid_corpus_files_raise_a_specific_error(tmp_path, body):
    store = YamlFileEvidenceStore(_write(tmp_path, "bad.yaml", body))
    with pytest.raises(CorpusValidationError):
        store.load()


def test_missing_corpus_file_raises_a_specific_error(tmp_path):
    with pytest.raises(CorpusValidationError):
        YamlFileEvidenceStore(tmp_path / "does_not_exist.yaml").load()


def test_stores_remain_behind_the_abstract_interface():
    assert isinstance(InMemoryEvidenceStore([]), EvidenceStore)
    assert isinstance(YamlFileEvidenceStore(DEFAULT_EVIDENCE_CORPUS_PATH), EvidenceStore)


# --- deterministic scoring / ordering ------------------------------------------


def test_full_overlap_scores_one_and_zero_overlap_is_excluded():
    renal = _doc("GLY-CDS", title="GLYXTRA core sheet", text="renal dose adjustment required")
    flu = _doc("FLU-VAX", title="Flu guidance", text="annual vaccination schedule adults")

    result = _retriever([flu, renal]).retrieve("renal dose adjustment")

    assert result.succeeded is True
    assert [match.source_id for match in result.matches] == ["GLY-CDS"]
    match = result.matches[0]
    assert match.score == pytest.approx(1.0)
    assert match.confidence == match.score


def test_higher_coverage_ranks_first_and_scores_are_exact_fractions():
    addendum = _doc(
        "VAS-ADD",
        title="VAS warnings addendum",
        text="vascuten bruising hepatic impairment warning",
    )
    sheet = _doc("VAS-CDS", title="VAS core sheet", text="vascuten stroke prevention surgery")
    unrelated = _doc("GLY-X", title="Other", text="glyxtra tablets maximum dosing")

    result = _retriever([unrelated, sheet, addendum]).retrieve("vascuten bruising hepatic")

    assert [(match.source_id, match.score) for match in result.matches] == [
        ("VAS-ADD", pytest.approx(1.0)),
        ("VAS-CDS", pytest.approx(1 / 3)),
    ]
    assert result.total_candidates == 3
    assert result.corpus_version == "test-1.0"


def test_equal_scores_tie_break_alphabetically_by_source_id():
    late = _doc("ZULU", text="liver monitoring protocol")
    early = _doc("ALPHA", text="device monitoring protocol")

    result = _retriever([late, early]).retrieve("monitoring")

    assert [match.source_id for match in result.matches] == ["ALPHA", "ZULU"]


def test_max_results_caps_output_but_reports_full_candidate_count():
    documents = [_doc(f"SRC-{name}", text=f"safety review {name}") for name in ("A", "B", "C")]

    result = _retriever(documents, max_results=2).retrieve("safety")

    assert [match.source_id for match in result.matches] == ["SRC-A", "SRC-B"]
    assert result.total_candidates == 3


def test_min_score_filters_weak_matches_without_failing():
    strong = _doc("ALL-3", text="hepatic renal cardiac monitoring")
    weak = _doc("OF-3", text="hepatic renal functions listed nowhere else")

    filtered = _retriever([weak, strong], min_score=0.7).retrieve("hepatic renal cardiac")
    unfiltered = _retriever([weak, strong]).retrieve("hepatic renal cardiac")

    assert [match.source_id for match in filtered.matches] == ["ALL-3"]
    assert filtered.succeeded is True
    assert [match.source_id for match in unfiltered.matches] == ["ALL-3", "OF-3"]


def test_repeated_calls_return_identical_results_byte_for_byte():
    documents = [_doc("B", text="shared warning"), _doc("A", text="shared warning")]
    retriever = _retriever(documents)

    assert retriever.retrieve("shared warning") == retriever.retrieve("shared warning")


def test_case_and_punctuation_do_not_change_results():
    documents = [_doc("ONE", text="vascuten bruising hepatic impairment")]
    retriever = _retriever(documents)

    punctuated = retriever.retrieve("VASCUTEN!! bruising... hepatic?")
    plain = retriever.retrieve("vascuten bruising hepatic")

    # The recorded query strings differ by design; ranking must not.
    assert punctuated.matches == plain.matches


def test_stopword_only_and_empty_queries_return_clean_empty_results():
    retriever = _retriever([_doc("X")])

    for query in ("the of and can it may", "", "!?."):
        result = retriever.retrieve(query)
        assert result.succeeded is True
        assert result.matches == []
        assert result.error_kind is None


def test_tokenize_is_case_insensitive_and_drops_grammar_words():
    assert tokenize("Hepatitis-B B12! THE") == {"hepatitis", "b", "b12"}
    assert "dose" in tokenize("The DOSE")
    assert "the" not in tokenize("the dose")


def test_retrieve_for_claim_maps_claim_text_as_the_query():
    documents = [_doc("VAS-ADD", text="vascuten bruising hepatic impairment warning")]
    retriever = _retriever(documents)
    claim = Claim(text="vascuten bruising hepatic", confidence=0.9)

    result = retriever.retrieve_for_claim(claim)

    assert result.query == claim.text
    assert result == retriever.retrieve(claim.text)
    assert result.matches[0].source_id == "VAS-ADD"


# --- conservative failure handling ---------------------------------------------


class _ExplodingStore(EvidenceStore):
    def load(self) -> EvidenceCorpus:
        raise RuntimeError("corpus backend down")


class _InvalidStore(EvidenceStore):
    def load(self) -> EvidenceCorpus:
        raise CorpusValidationError("corpus failed validation")


@pytest.mark.parametrize("store", [_ExplodingStore(), _InvalidStore()])
def test_store_failures_degrade_to_explicit_empty_results(store):
    result = EvidenceRetriever(store).retrieve("anything at all")

    # No evidence can never look like approval: empty matches keep the later
    # verification stage conservative (UNVERIFIABLE, not SUPPORTED).
    assert result.succeeded is False
    assert result.error_kind == "corpus_load_failed"
    assert result.matches == []
    assert result.corpus_version is None
    assert result.total_candidates == 0
    for field in _FORBIDDEN_AUTHORITY_FIELDS:
        assert not hasattr(result, field)


# --- shipped default corpus (offline integration) ------------------------------


def _default_retriever() -> EvidenceRetriever:
    return EvidenceRetriever(YamlFileEvidenceStore(DEFAULT_EVIDENCE_CORPUS_PATH))


def test_shipped_corpus_loads_and_serves_ranked_matches_with_provenance():
    result = _default_retriever().retrieve("glyxtra maximum daily dose")

    assert result.succeeded is True
    assert result.corpus_version == "1.0.0"
    assert result.total_candidates >= 5
    best = result.matches[0]
    assert isinstance(best, RetrievedEvidence)
    assert best.source_id == "CCDS-GLYXTRA-V3"
    assert best.score == pytest.approx(1.0)
    assert best.title  # provenance present
    assert 0.0 < best.confidence <= 1.0


def test_two_fresh_retrievers_against_the_shipped_corpus_agree_exactly():
    first = _default_retriever().retrieve("vascuten bruising hepatic")
    second = _default_retriever().retrieve("vascuten bruising hepatic")

    assert first == second


def test_shipped_corpus_conservatively_reports_unmatched_queries():
    result = _default_retriever().retrieve("quantum cryptocurrency unicorns")

    assert result.succeeded is True
    assert result.matches == []
