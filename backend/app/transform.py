"""Source loading, validation, minimization, redaction and canonical payloads.

Pipeline (always in this order, always on the backend):
1. Read the current source bytes and hash them.
2. Validate: ticket_id and a nonempty message on every row; no malformed rows.
   Rows are never silently repaired or dropped.
3. Keep only the policy's outbound fields for the purpose (baseline: message).
4. Redact required patterns inside retained text (EMAIL, PHONE).
5. Replace requester-hidden messages with [HIDDEN_BY_USER].
6. Serialize the canonical payload and hash it.

Requester choices are applied after mandatory redaction and can only hide more.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import detection

SCHEMA_VERSION = "1.0"
INSTRUCTIONS = {
    "feedback_summary": "Summarize the recurring product issues in the provided messages.",
}
HIDDEN_MARKER = "[HIDDEN_BY_USER]"
REQUIRED_COLUMNS = ("ticket_id", "message")

# Order matters: emails first so their digits are not mistaken for phone numbers.
PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}"),
    # North-American style 10-digit numbers with optional +1 and common separators.
    "PHONE": re.compile(r"(?<![\w+])(?:\+?1[\s.\-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.\-]?)\d{3}[\s.\-]?\d{4}(?!\w)"),
}


class SourceInvalid(Exception):
    """Source failed validation. Details are row/column positions only, never values."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass(frozen=True)
class SourceSnapshot:
    sha256: str
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class PreparedPayload:
    payload: dict
    canonical_bytes: bytes
    preview_hash: str
    redaction_counts: dict[str, int]
    dropped_fields: list[str]
    original_messages: list[str]
    findings: list[dict]


def read_source(path: Path) -> SourceSnapshot:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SourceInvalid(["source file is unavailable"]) from exc
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceInvalid(["source is not valid UTF-8"]) from exc

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        records = list(reader)
        header = records.pop(0)
    except IndexError as exc:
        raise SourceInvalid(["source is empty"]) from exc
    except csv.Error as exc:
        raise SourceInvalid(["source contains malformed CSV quoting"]) from exc
    header = [h.strip() for h in header]
    problems: list[str] = []
    for col in REQUIRED_COLUMNS:
        if col not in header:
            problems.append(f"missing required column '{col}'")
    if len(set(header)) != len(header):
        problems.append("duplicate column names")
    if problems:
        raise SourceInvalid(problems)

    rows: list[dict[str, str]] = []
    for line_no, values in enumerate(records, start=2):
        if not values:
            problems.append(f"row {line_no}: blank line")
            continue
        if len(values) != len(header):
            problems.append(f"row {line_no}: expected {len(header)} fields, found {len(values)}")
            continue
        row = dict(zip(header, values))
        if not row["ticket_id"].strip():
            problems.append(f"row {line_no}: empty ticket_id")
        if not row["message"].strip():
            problems.append(f"row {line_no}: empty message")
        rows.append(row)
    if not rows and not problems:
        problems.append("source has no data rows")
    if problems:
        raise SourceInvalid(problems)
    return SourceSnapshot(sha256=digest, columns=tuple(header), rows=tuple(rows))


def redact(text: str, redaction_types: tuple[str, ...]) -> tuple[str, dict[str, int]]:
    counts = {t: 0 for t in redaction_types}
    for rtype in PATTERNS:  # fixed order
        if rtype not in redaction_types:
            continue
        text, n = PATTERNS[rtype].subn(f"[{rtype}]", text)
        counts[rtype] += n
    return text, counts


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def pipeline_fingerprint() -> str:
    # Binds reviews to detector artifacts and transformation implementation too.
    return hashlib.sha256((hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                           + detection.detector_fingerprint()).encode()).hexdigest()


def normalize_spans(source: SourceSnapshot, spans: list[dict]) -> list[dict]:
    result = set()
    for span in spans:
        idx, start, end = (span.get(k) for k in ("message_index", "start", "end"))
        if (any(type(v) is not int for v in (idx, start, end)) or not 0 <= idx < len(source.rows)
                or not 0 <= start < end <= len(source.rows[idx]["message"])):
            raise ValueError("Invalid original-message span")
        result.add((idx, start, end))
    return [dict(message_index=i, start=s, end=e) for i, s, e in sorted(result)]


def prepare(
    source: SourceSnapshot, purpose: str, outbound_fields: list[str],
    required_redactions: tuple[str, ...], hidden_indices: list[int],
    manual_spans: list[dict] | None = None,
) -> PreparedPayload:
    if outbound_fields != ["message"] or purpose not in INSTRUCTIONS:
        raise ValueError("Unsupported payload template")
    if any(t not in (*PATTERNS, "PERSON") for t in required_redactions):
        raise ValueError("Unsupported mandatory detector")
    manual = normalize_spans(source, manual_spans or [])
    dropped = [c for c in source.columns if c not in outbound_fields]
    totals = {t: 0 for t in required_redactions}
    originals = [row["message"] for row in source.rows]
    findings, messages, identities = [], [], {}
    for idx, text in enumerate(originals):
        candidates = []
        for category, pattern in PATTERNS.items():
            if category in required_redactions:
                candidates.extend(dict(start=m.start(), end=m.end(), category=category, detector="regex:v1")
                                  for m in pattern.finditer(text))
        if "PERSON" in required_redactions:
            candidates.extend(dict(start=f["start"], end=f["end"], category="PERSON", detector=f["detector"])
                              for f in detection.person_spans(text))
        # Count original detector findings, independently of overlap resolution.
        # Identifier detectors take precedence only when they already cover the
        # entire later finding. Partial overlap must preserve ALL detected text.
        accepted = []
        for finding in candidates:
            totals[finding["category"]] += 1
            if any(f["start"] <= finding["start"] and finding["end"] <= f["end"] for f in accepted):
                continue
            overlaps = [f for f in accepted
                        if finding["start"] < f["end"] and f["start"] < finding["end"]]
            if overlaps:
                group = overlaps + [finding]
                categories = {category for item in group for category in item["category"].split("+")}
                merged = dict(
                    start=min(item["start"] for item in group),
                    end=max(item["end"] for item in group),
                    category="+".join(category for category in (*PATTERNS, "PERSON") if category in categories),
                    detector=";".join(sorted({item["detector"] for item in group})),
                )
                accepted = [f for f in accepted if f not in overlaps]
                accepted.append(merged)
            else:
                accepted.append(finding)
        accepted.sort(key=lambda f: (f["start"], f["end"]))
        for f in accepted:
            category = f["category"]
            replacement = "[REDACTED]" if "+" in category else f"[{category}]"
            if category == "PERSON":
                key = " ".join(text[f["start"]:f["end"]].casefold().split())
                if key not in identities:
                    identities[key] = f"[PERSON_{len(identities) + 1:03d}]"
                replacement = identities[key]
            f.update(id=f"m{idx}:{f['start']}:{f['end']}:{category}", message_index=idx,
                     replacement=replacement, mandatory=True)
            findings.append(dict(f))
        optional = [dict(id=f"manual:{idx}:{f['start']}:{f['end']}", message_index=idx,
                         start=f["start"], end=f["end"], category="MANUAL", replacement="[MANUAL]",
                         mandatory=False, detector="user") for f in manual if f["message_index"] == idx]
        findings.extend(optional)
        # Union overlapping spans; a manual span can extend coverage, never expose
        # an owner-mandated span. Keep mandatory findings separately for locked UI.
        unions = []
        for f in sorted(accepted + optional, key=lambda v: (v["start"], v["end"])):
            if unions and f["start"] < unions[-1]["end"]:
                unions[-1]["end"] = max(unions[-1]["end"], f["end"])
                unions[-1]["replacement"] = "[MANUAL]"
            else:
                unions.append(dict(f))
        chunks, cursor = [], 0
        for f in unions:
            chunks.extend((text[cursor:f["start"]], f["replacement"]))
            cursor = f["end"]
        chunks.append(text[cursor:])
        messages.append(HIDDEN_MARKER if idx in hidden_indices else "".join(chunks))
    payload = {"schema_version": SCHEMA_VERSION, "purpose": purpose,
               "instruction": INSTRUCTIONS[purpose], "messages": messages}
    body = canonical_bytes(payload)
    return PreparedPayload(payload, body, hashlib.sha256(body).hexdigest(), totals, dropped, originals, findings)
