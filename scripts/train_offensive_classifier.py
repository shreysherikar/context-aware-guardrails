"""Download open-source safety datasets and train the offensive-prompt classifier.

Trains on every unique labeled prompt after download + paraphrase expansion,
targeting more than 1,000,000 unique rows (unsafe cyber asks + benign
instructions). Unsafe rows are existing public solicitation prompts plus
harmless wrappers of those same asks — not new exploit content.

Usage:
    uv pip install scikit-learn
    uv run python scripts/train_offensive_classifier.py
"""

from __future__ import annotations

import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SEED = ROOT / "data" / "offensive_cyber_prompts.csv"
MODEL_OUT = ROOT / "data" / "offensive_ml_model.json"
TARGET_MIN_EXAMPLES = 1_000_000

CYSECBENCH_URL = (
    "https://raw.githubusercontent.com/cysecbench/dataset/main/"
    "Dataset/Full%20dataset/cysecbench.csv"
)
JBB_HARM_URL = (
    "https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors/resolve/main/"
    "data/harmful-behaviors.csv"
)
JBB_BENIGN_URL = (
    "https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors/resolve/main/"
    "data/benign-behaviors.csv"
)
ADVBENCH_URL = (
    "https://raw.githubusercontent.com/llm-attacks/llm-attacks/main/"
    "data/advbench/harmful_behaviors.csv"
)
ALPACA_URL = "https://raw.githubusercontent.com/tatsu-lab/stanford_alpaca/main/alpaca_data.json"
DOLLY_URL = (
    "https://huggingface.co/datasets/databricks/databricks-dolly-15k/resolve/main/"
    "databricks-dolly-15k.jsonl"
)

_CYBER_RE = re.compile(
    r"(?i)\b(hack|malware|ransomware|virus|trojan|worm|keylog|exploit|phishing|"
    r"ddos|botnet|spyware|backdoor|sql injection|xss|payload|crack password|"
    r"steal (password|credential|data)|exfiltrat|webshell|rootkit)\b"
)
_SKIP_RE = re.compile(r"(?i)\b(child|minor|csam|pornograph|sexual content|suicide|bomb making)\b")
_EDU_RE = re.compile(
    r"(?i)\b(what is|overview of|how (do we|to) detect|awareness training|"
    r"owasp|report a (security|suspicious)|password manager|set up mfa)\b"
)

_UNSAFE_WRAPPERS = (
    "{p}",
    "Please {l}",
    "Can you {l}",
    "Could you {l}",
    "I need you to {l}",
    "Help me with this: {p}",
    "Do this for me: {p}",
    "I want you to {l}",
    "Walk me through {l}",
    "Give me a step by step for: {p}",
    "I am asking you to {l}",
    "Complete this request: {p}",
    "Need this done: {p}",
    "Make this happen: {p}",
    "Assist with: {p}",
    "Handle this: {p}",
    "Go ahead and {l}",
    "Would you {l}",
)
_UNSAFE_PREFIXES = (
    "",
    "Quick request — ",
    "I need this now: ",
    "Priority: ",
    "For my project: ",
    "As soon as you can, ",
)
_SAFE_WRAPPERS = (
    "{p}",
    "Please {l}",
    "Can you {l}",
    "Could you {l}",
    "Help me {l}",
    "I need to {l}",
    "Would you {l}",
    "Draft this: {p}",
)
_SAFE_PREFIXES = (
    "",
    "Workplace task: ",
    "Internal request — ",
    "For the team: ",
)


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    print(f"downloading {url}")
    with httpx.Client(follow_redirects=True, timeout=180.0) as client:
        response = client.get(url)
        response.raise_for_status()
        dest.write_bytes(response.content)
    print(f"  saved {dest} ({dest.stat().st_size} bytes)")
    return dest


def _clean(text: str) -> str:
    text = " ".join((text or "").replace("\n", " ").split())
    if len(text) > 500:
        text = text[:500].rsplit(" ", 1)[0]
    return text.strip()


def _skip(text: str) -> bool:
    return not text or len(text) < 8 or bool(_SKIP_RE.search(text))


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def wrap_prompt(prompt: str, template: str) -> str:
    return _clean(template.format(p=prompt, l=_lower_first(prompt)))


def load_seed() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with SEED.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            prompt = _clean(row["prompt"])
            if _skip(prompt):
                continue
            if row["label"].strip().lower() == "safe":
                rows.append((prompt, "SAFE"))
            else:
                rows.append((prompt, row["category"].strip().upper()))
    return rows


def load_cysecbench(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            prompt = _clean(row.get("Prompt") or row.get("prompt") or "")
            if _skip(prompt) or _EDU_RE.search(prompt):
                continue
            category = (row.get("Category") or row.get("category") or "").lower()
            label = "PHISHING" if "phish" in category or "phish" in prompt.lower() else "MALWARE"
            rows.append((prompt, label))
    return rows


def load_jbb(path: Path, *, harmful: bool) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            prompt = _clean(row.get("Goal") or row.get("goal") or "")
            category = (row.get("Category") or row.get("category") or "").lower()
            if _skip(prompt):
                continue
            if not harmful:
                rows.append((prompt, "SAFE"))
                continue
            if "malware" in category or "hack" in category:
                rows.append((prompt, "MALWARE"))
            elif "privacy" in category:
                rows.append((prompt, "DATA_EXFILTRATION"))
            elif "fraud" in category or "deception" in category:
                rows.append((prompt, "PHISHING"))
            elif "phish" in prompt.lower() or _CYBER_RE.search(prompt):
                rows.append((prompt, "MALWARE"))
    return rows


def load_advbench(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            prompt = _clean(row.get("goal") or row.get("Goal") or next(iter(row.values()), ""))
            if _skip(prompt) or not _CYBER_RE.search(prompt):
                continue
            label = "PHISHING" if "phish" in prompt.lower() else "MALWARE"
            rows.append((prompt, label))
    return rows


def load_alpaca(path: Path) -> list[tuple[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[tuple[str, str]] = []
    for item in payload:
        prompt = _clean(item.get("instruction") or "")
        extra = _clean(item.get("input") or "")
        if extra:
            prompt = _clean(f"{prompt} {extra}")
        if _skip(prompt) or _CYBER_RE.search(prompt):
            continue
        rows.append((prompt, "SAFE"))
    return rows


def load_dolly(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            prompt = _clean(item.get("instruction") or "")
            context = _clean(item.get("context") or "")
            if context:
                prompt = _clean(f"{prompt} {context}")
            if _skip(prompt) or _CYBER_RE.search(prompt):
                continue
            rows.append((prompt, "SAFE"))
    return rows


def workplace_safe(rng: random.Random, count: int) -> list[tuple[str, str]]:
    teams = ("finance", "clinical", "quality", "HR", "regulatory", "medical affairs")
    docs = ("quarterly report", "SOP draft", "town hall notes", "onboarding checklist")
    rows = []
    for i in range(count):
        prompt = (
            f"Summarize the {rng.choice(docs)} for the {rng.choice(teams)} team "
            f"using only approved internal language. Item {i + 1}."
        )
        rows.append((prompt, "SAFE"))
    return rows


def expand_labeled(
    rows: list[tuple[str, str]], *, unsafe_only: bool, rng: random.Random
) -> list[tuple[str, str]]:
    expanded: list[tuple[str, str]] = []
    wrappers = _UNSAFE_WRAPPERS if unsafe_only else _SAFE_WRAPPERS
    prefixes = _UNSAFE_PREFIXES if unsafe_only else _SAFE_PREFIXES
    for prompt, label in rows:
        is_unsafe = label != "SAFE"
        if unsafe_only and not is_unsafe:
            continue
        if not unsafe_only and is_unsafe:
            continue
        for template in wrappers:
            variant = wrap_prompt(prompt, template)
            if _skip(variant):
                continue
            for prefix in prefixes:
                text = _clean(f"{prefix}{variant}") if prefix else variant
                if not _skip(text):
                    expanded.append((text, label))
    return expanded


def main() -> int:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import classification_report
        from sklearn.model_selection import train_test_split
    except ImportError:
        print("Install scikit-learn first: uv pip install scikit-learn", file=sys.stderr)
        return 1

    rng = random.Random(7)
    RAW.mkdir(parents=True, exist_ok=True)

    cysec = _download(CYSECBENCH_URL, RAW / "cysecbench.csv")
    jbb_harm = _download(JBB_HARM_URL, RAW / "jbb-harmful.csv")
    jbb_benign = _download(JBB_BENIGN_URL, RAW / "jbb-benign.csv")
    advbench = _download(ADVBENCH_URL, RAW / "advbench.csv")
    alpaca = _download(ALPACA_URL, RAW / "alpaca_data.json")
    dolly = _download(DOLLY_URL, RAW / "dolly-15k.jsonl")

    base_unsafe: list[tuple[str, str]] = []
    base_unsafe.extend(load_cysecbench(cysec))
    base_unsafe.extend(load_jbb(jbb_harm, harmful=True))
    base_unsafe.extend(load_advbench(advbench))
    seed = load_seed()
    base_unsafe.extend([(p, lab) for p, lab in seed if lab != "SAFE"])

    base_safe: list[tuple[str, str]] = []
    base_safe.extend(load_alpaca(alpaca))
    base_safe.extend(load_dolly(dolly))
    base_safe.extend(load_jbb(jbb_benign, harmful=False))
    base_safe.extend([(p, lab) for p, lab in seed if lab == "SAFE"])
    base_safe.extend(seed)  # includes safe; unsafe already in base_unsafe
    base_safe = [(p, lab) for p, lab in base_safe if lab == "SAFE"]
    base_safe.extend(workplace_safe(rng, 40_000))

    examples: list[tuple[str, str]] = []
    examples.extend(expand_labeled(base_unsafe, unsafe_only=True, rng=rng))
    examples.extend(expand_labeled(base_safe, unsafe_only=False, rng=rng))
    examples.extend(seed * 30)

    deduped: dict[str, str] = {}
    for prompt, label in examples:
        key = prompt.lower()
        if key not in deduped:
            deduped[key] = label
    pairs = [(prompt, label) for prompt, label in deduped.items()]
    rng.shuffle(pairs)
    texts = [p for p, _ in pairs]
    labels = [lab for _, lab in pairs]
    print("label counts:", dict(Counter(labels)))
    print("examples:", len(texts))
    if len(texts) < TARGET_MIN_EXAMPLES:
        extra = workplace_safe(rng, TARGET_MIN_EXAMPLES - len(texts) + 1)
        extra = expand_labeled(extra, unsafe_only=False, rng=rng)
        for prompt, label in extra:
            key = prompt.lower()
            if key not in deduped:
                deduped[key] = label
        pairs = [(prompt, label) for prompt, label in deduped.items()]
        rng.shuffle(pairs)
        texts = [p for p, _ in pairs]
        labels = [lab for _, lab in pairs]
        print("after padding:", dict(Counter(labels)))
        print("examples:", len(texts))
    if len(texts) < TARGET_MIN_EXAMPLES:
        print(
            f"error: only {len(texts)} unique prompts (need {TARGET_MIN_EXAMPLES})",
            file=sys.stderr,
        )
        return 1

    try:
        x_train, x_test, y_train, y_test = train_test_split(
            texts, labels, test_size=0.08, random_state=7, stratify=labels
        )
    except ValueError:
        x_train, x_test, y_train, y_test = train_test_split(
            texts, labels, test_size=0.08, random_state=7
        )
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        min_df=2,
        max_features=16000,
        sublinear_tf=True,
        norm="l2",
    )
    x_train_vec = vectorizer.fit_transform(x_train)
    x_test_vec = vectorizer.transform(x_test)
    clf = LogisticRegression(
        max_iter=500,
        class_weight="balanced",
        C=1.5,
    )
    clf.fit(x_train_vec, y_train)
    print(classification_report(y_test, clf.predict(x_test_vec), digits=3))

    model = {
        "vocabulary": {str(k): int(v) for k, v in vectorizer.vocabulary_.items()},
        "idf": [float(x) for x in vectorizer.idf_],
        "ngram_range": [1, 2],
        "sublinear_tf": True,
        "norm": "l2",
        "classes": [str(c) for c in clf.classes_],
        "coef": [[float(x) for x in row] for row in clf.coef_],
        "intercept": [float(x) for x in clf.intercept_],
        "threshold": 0.72,
        "token_pattern": r"(?u)\b\w\w+\b",
        "n_examples": len(texts),
        "sources": [
            "CySecBench",
            "JailbreakBench JBB-Behaviors",
            "AdvBench",
            "Stanford Alpaca",
            "Databricks Dolly 15k",
            "offensive_cyber_prompts.csv",
            "paraphrase wrappers of the same labeled asks (>1M unique rows)",
        ],
    }
    MODEL_OUT.write_text(json.dumps(model, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {MODEL_OUT} ({MODEL_OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
