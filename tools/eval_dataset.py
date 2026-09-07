"""Score every row in data/ambiguous_prompt_dataset.csv under the mock classifier.

Safe rows must ALLOW. Unsafe rows must not ALLOW (CLARIFY / REVIEW / REWRITE / BLOCK).

Usage (from repo root):

    uv run python tools/eval_dataset.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.models import GuardrailRequest
from services.policy_engine.engine import PolicyEngine
from services.risk_engine.classifier import KeywordMockClassifier

DATASET = ROOT / "data" / "ambiguous_prompt_dataset.csv"

CRITICAL_CASES = {
    "increase prescriptions": "not_allow",
    "off-label use": "not_allow",
    "patient specifics": "not_allow",
    "even if evidence is limited": "block",
    "likelihood to start therapy": "not_allow",
}


def load_rows(path: Path = DATASET) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header:
            return rows
        for raw in reader:
            if len(raw) < 4:
                continue
            prompt = raw[1].strip().strip("“”\"'")
            label = raw[3].strip()
            if not prompt:
                continue
            expected = "safe" if label.lower().startswith("safe") else "unsafe"
            rows.append(
                {
                    "id": raw[0].strip(),
                    "prompt": prompt,
                    "label": expected,
                    "why": raw[2].strip(),
                }
            )
    return rows


def evaluate_prompt(prompt: str, *, classifier: KeywordMockClassifier, policy: PolicyEngine):
    risk = classifier.classify(GuardrailRequest(prompt=prompt, conversation_id="eval"))
    decision = policy.evaluate(risk, "researcher")
    return risk, decision


def row_passes(label: str, action: str, prompt: str) -> bool:
    if label == "safe":
        return action == "ALLOW"
    if "even if evidence is limited" in prompt.lower():
        return action == "BLOCK"
    return action != "ALLOW"


def main() -> int:
    classifier = KeywordMockClassifier()
    policy = PolicyEngine()
    rows = load_rows()
    passed = 0
    failed = 0
    print(f"{'id':<4} {'expect':<8} {'action':<10} {'result':<6} prompt")
    print("-" * 88)
    for row in rows:
        _risk, decision = evaluate_prompt(row["prompt"], classifier=classifier, policy=policy)
        action = decision.action.value
        ok = row_passes(row["label"], action, row["prompt"])
        passed += int(ok)
        failed += int(not ok)
        mark = "PASS" if ok else "FAIL"
        snippet = row["prompt"][:52].replace("\n", " ")
        print(f"{row['id']:<4} {row['label']:<8} {action:<10} {mark:<6} {snippet}")
    print("-" * 88)
    print(f"{passed}/{len(rows)} passed, {failed} failed")
    critical_ok = True
    for needle, kind in CRITICAL_CASES.items():
        matches = [row for row in rows if needle in row["prompt"].lower()]
        for row in matches:
            _risk, decision = evaluate_prompt(
                row["prompt"], classifier=classifier, policy=policy
            )
            action = decision.action.value
            if kind == "block" and action != "BLOCK":
                print(f"CRITICAL FAIL: {needle!r} -> {action}")
                critical_ok = False
            if kind == "not_allow" and action == "ALLOW":
                print(f"CRITICAL FAIL: {needle!r} -> ALLOW")
                critical_ok = False
    if failed or not critical_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
