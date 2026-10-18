"""Run with: python -m evaluation.run --split heldout --output runtime/ner-evaluation.json"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.detection import DetectorUnavailable, detector_status, person_spans
from app import detection, transform
from app.transform import PATTERNS
from .corpus import examples

CATEGORIES = ("EMAIL", "PHONE", "PERSON")


def predictions(text: str, *, include_person: bool) -> list[dict]:
    candidates = [
        {"start": match.start(), "end": match.end(), "entity_type": category}
        for category, pattern in PATTERNS.items() for match in pattern.finditer(text)
    ]
    if include_person:
        candidates.extend(person_spans(text))
    # EMAIL > PHONE > PERSON for overlaps, matching the gateway's precedence.
    chosen = []
    for finding in sorted(candidates, key=lambda item: (CATEGORIES.index(item["entity_type"]), item["start"], item["end"])):
        if not any(finding["start"] < item["end"] and item["start"] < finding["end"] for item in chosen):
            chosen.append(finding)
    return chosen


def score(dataset: list[dict], predict) -> dict:
    counts = {category: {"tp": 0, "fp": 0, "fn": 0} for category in CATEGORIES}
    errors = []
    for example in dataset:
        expected = {(entity["start"], entity["end"], entity["entity_type"]) for entity in example["entities"]}
        actual = {(entity["start"], entity["end"], entity["entity_type"]) for entity in predict(example["text"])}
        for label, items in (("tp", actual & expected), ("fp", actual - expected), ("fn", expected - actual)):
            for start, end, category in sorted(items):
                counts[category][label] += 1
                if label != "tp":
                    errors.append({"example_id": example["id"], "kind": label, "entity_type": category, "start": start, "end": end})

    def metrics(item):
        tp, fp, fn = item["tp"], item["fp"], item["fn"]
        return {
            **item, "support": tp + fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        }

    micro = {key: sum(item[key] for item in counts.values()) for key in ("tp", "fp", "fn")}
    return {"per_category": {key: metrics(value) for key, value in counts.items()}, "micro": metrics(micro), "errors": errors}


def _revision() -> dict:
    try:
        root = Path(__file__).resolve().parents[2]
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True).stdout.strip())
        return {"commit": revision, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def evaluate(split="heldout") -> dict:
    dataset = examples(split)
    status = detector_status()
    report = {
        "schema_version": "1.0", "generated_at": datetime.now(timezone.utc).isoformat(),
        "revision": _revision(), "split": split, "example_count": len(dataset),
        "implementation_hashes": {
            "detector": hashlib.sha256(Path(detection.__file__).read_bytes()).hexdigest(),
            "rules": hashlib.sha256(Path(transform.__file__).read_bytes()).hexdigest(),
            "evaluator": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "corpus_sha256": hashlib.sha256(json.dumps(dataset, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "matching": "exact_start_end_and_category", "offset_unit": "unicode_codepoint",
        "model": status, "status": "complete" if status["available"] else "model_unavailable",
        "rules_only": score(dataset, lambda text: predictions(text, include_person=False)),
        "rules_plus_ner": None,
        "limitations": ["Small hand-labelled synthetic convenience set; not production accuracy.",
                        "No model training or tuning on this heldout set; template diversity is limited.",
                        "Exact-span errors include partial-name boundary mismatches.",
                        "Undefined precision/recall is null; no text or raw entity values in this report."],
    }
    if status["available"]:
        try:
            report["rules_plus_ner"] = score(dataset, lambda text: predictions(text, include_person=True))
        except DetectorUnavailable:
            report["status"] = "model_unavailable"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["development", "heldout"], default="heldout")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "example_count": report["example_count"], "output": str(args.output)}))
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
