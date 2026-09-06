"""TF-IDF linear model trained on open-source cyber-offense prompts.

The coefficient file is produced by scripts/train_offensive_classifier.py.
Inference is pure Python so the runtime does not depend on scikit-learn.
"""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path

from domain.enums import RiskCategory
from services.risk_engine.offensive_patterns import is_benign_hack_context

_MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "offensive_ml_model.json"
_TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")
_EDU_ALLOW = re.compile(
    r"(?i)\b(what is|overview of|how (do we|to) detect|awareness training|"
    r"owasp top|report a (security|suspicious)|password manager)\b"
)
_CATEGORY = {
    "MALWARE": RiskCategory.MALWARE,
    "PHISHING": RiskCategory.PHISHING,
    "DATA_EXFILTRATION": RiskCategory.DATA_EXFILTRATION,
    "PROMPT_INJECTION": RiskCategory.PROMPT_INJECTION,
}


@lru_cache(maxsize=1)
def _load_model() -> dict | None:
    if not _MODEL_PATH.is_file():
        return None
    return json.loads(_MODEL_PATH.read_text(encoding="utf-8"))


def _ngrams(text: str, low: int, high: int) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    grams: list[str] = []
    for n in range(low, high + 1):
        grams.extend(" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1))
    return grams


def _tfidf_values(text: str, model: dict) -> dict[int, float] | None:
    vocab: dict[str, int] = model["vocabulary"]
    idf: list[float] = model["idf"]
    counts: dict[int, int] = {}
    low, high = model["ngram_range"]
    for gram in _ngrams(text, int(low), int(high)):
        index = vocab.get(gram)
        if index is None:
            continue
        counts[index] = counts.get(index, 0) + 1
    if not counts:
        return None
    values = {}
    for index, tf in counts.items():
        value = (1.0 + math.log(tf)) if model.get("sublinear_tf") else float(tf)
        values[index] = value * idf[index]
    if model.get("norm") == "l2":
        norm = math.sqrt(sum(v * v for v in values.values()))
        if norm:
            values = {index: value / norm for index, value in values.items()}
    return values


def _softmax(scores: list[float]) -> list[float]:
    peak = max(scores)
    exps = [math.exp(score - peak) for score in scores]
    total = sum(exps) or 1.0
    return [value / total for value in exps]


def predict_offensive_category(text: str) -> RiskCategory | None:
    """Return a risk category when the trained model is confident this is unsafe."""
    if not text or not text.strip():
        return None
    if _EDU_ALLOW.search(text):
        return None
    model = _load_model()
    if model is None:
        return None
    values = _tfidf_values(text, model)
    if values is None:
        return None
    classes: list[str] = model["classes"]
    intercept: list[float] = model["intercept"]
    coef: list[list[float]] = model["coef"]
    scores = []
    for class_i, bias in enumerate(intercept):
        score = bias
        row = coef[class_i]
        for index, value in values.items():
            score += row[index] * value
        scores.append(score)
    probs = _softmax(scores)
    best_i = max(range(len(probs)), key=lambda i: probs[i])
    label = classes[best_i]
    if label == "SAFE" or probs[best_i] < float(model.get("threshold", 0.72)):
        return None
    category = _CATEGORY.get(label)
    if category == RiskCategory.MALWARE and is_benign_hack_context(text):
        return None
    return category
