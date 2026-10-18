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

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise SourceInvalid(["source is empty"]) from exc
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
    for line_no, values in enumerate(reader, start=2):
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


def prepare(
    source: SourceSnapshot,
    purpose: str,
    outbound_fields: list[str],
    required_redactions: tuple[str, ...],
    hidden_indices: list[int],
) -> PreparedPayload:
    if outbound_fields != ["message"]:
        # The v1 payload template carries messages only. Any other configuration
        # must be added through a coordinated contract change, not forwarded.
        raise ValueError("v1 payload supports outbound_fields == ['message'] only")
    dropped = [c for c in source.columns if c not in outbound_fields]
    totals = {t: 0 for t in required_redactions}
    hidden = set(hidden_indices)
    messages: list[str] = []
    for idx, row in enumerate(source.rows):
        # Mandatory redaction runs on every retained message, hidden or not, so
        # the counts reflect the owner rule independent of requester choices.
        cleaned, counts = redact(row["message"], required_redactions)
        for k, v in counts.items():
            totals[k] += v
        messages.append(HIDDEN_MARKER if idx in hidden else cleaned)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "purpose": purpose,
        "instruction": INSTRUCTIONS[purpose],
        "messages": messages,
    }
    body = canonical_bytes(payload)
    return PreparedPayload(
        payload=payload,
        canonical_bytes=body,
        preview_hash=hashlib.sha256(body).hexdigest(),
        redaction_counts=totals,
        dropped_fields=dropped,
    )
