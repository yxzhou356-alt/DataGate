"""Evaluate the local PERSON detector on the committed synthetic labeled set.

    python -m app.person_eval [--json PATH] [--show-errors]

Gold spans are marked with {braces} in backend/eval/person_eval.jsonl (honorifics are
outside the braces: they stay visible as context). Scores are computed from an actual
run of the detector:
- exact: a predicted span counts only if its offsets equal a gold span;
- overlap: a predicted span counts if it overlaps any gold span (lenient).

LIMITS: 70 short synthetic English-centric messages, written by the same team that
wrote the detector. Results describe this set only. They are not a measure of
real-world name-detection accuracy, and a clean result is not proof that a message
contains no personal data. --json writes counts and scores only, never message text.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import BACKEND_DIR
from .detectors import LexiconPersonDetector, PersonDetector, detect_persons

EVAL_PATH = BACKEND_DIR / "eval" / "person_eval.jsonl"


@dataclass(frozen=True)
class Example:
    id: str
    category: str
    text: str
    gold: tuple[tuple[int, int], ...]


def parse_marked(marked: str) -> tuple[str, tuple[tuple[int, int], ...]]:
    """'Ask {Emma} now' -> ('Ask Emma now', ((4, 8),)). Offsets are code points."""
    out, gold, start = [], [], None
    for ch in marked:
        if ch == "{":
            if start is not None:
                raise ValueError("nested gold span")
            start = len(out)
        elif ch == "}":
            if start is None or start == len(out):
                raise ValueError("unbalanced or empty gold span")
            gold.append((start, len(out)))
            start = None
        else:
            out.append(ch)
    if start is not None:
        raise ValueError("unclosed gold span")
    return "".join(out), tuple(gold)


def load_examples(path: Path = EVAL_PATH) -> list[Example]:
    examples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            text, gold = parse_marked(row["text"])
            examples.append(Example(row["id"], row["category"], text, gold))
    return examples


def _scores(tp: int, fp: int, fn: int) -> dict[str, float | None]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"precision": p, "recall": r, "f1": f1}


def evaluate(detector: PersonDetector, examples: list[Example]) -> dict:
    exact = {"tp": 0, "fp": 0, "fn": 0}
    overlap = {"tp": 0, "fp": 0, "fn": 0}
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"examples": 0, "tp": 0, "fp": 0, "fn": 0})
    errors = []
    for ex in examples:
        pred = set(detect_persons(detector, ex.text))
        gold = set(ex.gold)
        tp = len(pred & gold)
        fp, fn = len(pred - gold), len(gold - pred)
        for k, v in (("tp", tp), ("fp", fp), ("fn", fn)):
            exact[k] += v
            by_cat[ex.category][k] += v
        by_cat[ex.category]["examples"] += 1
        hits = lambda a, others: any(a[0] < b[1] and b[0] < a[1] for b in others)  # noqa: E731
        overlap["tp"] += sum(1 for s in pred if hits(s, gold))
        overlap["fp"] += sum(1 for s in pred if not hits(s, gold))
        overlap["fn"] += sum(1 for g in gold if not hits(g, pred))
        if fp or fn:
            errors.append((ex, sorted(pred), sorted(gold)))
    return {
        "exact": {**exact, **_scores(exact["tp"], exact["fp"], exact["fn"])},
        "overlap": {**overlap, **_scores(overlap["tp"], overlap["fp"], overlap["fn"])},
        "by_category": {c: {**v, **_scores(v["tp"], v["fp"], v["fn"])} for c, v in sorted(by_cat.items())},
        "_errors": errors,
    }


def _fmt(x: float | None) -> str:
    return "  n/a" if x is None else f"{x:5.3f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.person_eval")
    parser.add_argument("--json", type=Path, help="also write counts and scores (no text) to this file")
    parser.add_argument("--show-errors", action="store_true", help="print misses and false positives (synthetic text)")
    args = parser.parse_args(argv)

    detector = LexiconPersonDetector()
    examples = load_examples()
    res = evaluate(detector, examples)
    print(f"PERSON detector evaluation: {detector.version} on {len(examples)} synthetic examples "
          f"({sum(len(e.gold) for e in examples)} gold spans)")
    print("SYNTHETIC AND LIMITED: describes this set only, not real-world accuracy.\n")
    for name in ("exact", "overlap"):
        m = res[name]
        print(f"{name:8s} P={_fmt(m['precision'])} R={_fmt(m['recall'])} F1={_fmt(m['f1'])}  "
              f"(tp={m['tp']} fp={m['fp']} fn={m['fn']})")
    print("\nby category (exact):")
    for cat, m in res["by_category"].items():
        print(f"  {cat:18s} n={m['examples']:2d} tp={m['tp']:2d} fp={m['fp']:2d} fn={m['fn']:2d} "
              f"P={_fmt(m['precision'])} R={_fmt(m['recall'])}")
    if args.show_errors:
        print("\nerrors (synthetic examples):")
        for ex, pred, gold in res["_errors"]:
            show = lambda spans: [ex.text[s:e] for s, e in spans]  # noqa: E731
            print(f"  {ex.id} [{ex.category}] predicted={show(pred)} gold={show(gold)}")
    if args.json:
        out = {k: v for k, v in res.items() if k != "_errors"}
        out.update(detector_version=detector.version, examples=len(examples),
                   generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   note="Synthetic, limited evaluation; not a real-world accuracy claim.")
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
