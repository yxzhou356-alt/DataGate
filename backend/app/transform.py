"""Source loading, validation, minimization, redaction and canonical payloads.

Pipeline (always in this order, always on the backend):
1. Read the current source bytes and hash them.
2. Validate: ticket_id and a nonempty message on every row; no malformed rows.
   Rows are never silently repaired or dropped.
3. Keep only the policy's outbound fields for the purpose (baseline: message).
4. Redact required patterns inside retained text (EMAIL, PHONE).
5. Replace requester-selected spans of the redacted text with [REDACTED_BY_USER].
6. Replace requester-hidden messages with [HIDDEN_BY_USER].
7. Serialize the canonical payload and hash it.

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
CUSTOM_MARKER = "[REDACTED_BY_USER]"
MAX_CUSTOM_PER_MESSAGE = 20
MAX_CUSTOM_TOTAL = 200
_NO_CONTENT = re.compile(r"\[REDACTED_BY_USER\]|\[HIDDEN_BY_USER\]|\s")
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
    custom_redaction_count: int = 0  # requester spans applied to messages that are not hidden


class CustomRedactionInvalid(Exception):
    """A requester span is out of range, cuts through a mandatory placeholder, or exceeds limits."""


CustomSpans = dict[int, list[tuple[int, int]]]


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


def redacted_messages(source: SourceSnapshot, required_redactions: tuple[str, ...]) -> list[str]:
    """The mandatory-redacted text of every message: the base that requester spans refer to."""
    return [redact(row["message"], required_redactions)[0] for row in source.rows]


def placeholder_spans(text: str, required_redactions: tuple[str, ...]) -> list[tuple[int, int]]:
    spans = []
    for rtype in required_redactions:
        token = f"[{rtype}]"
        at = text.find(token)
        while at != -1:
            spans.append((at, at + len(token)))
            at = text.find(token, at + len(token))
    return spans


def normalize_custom(
    spans: list[tuple[int, int, int]], base: list[str], required_redactions: tuple[str, ...]
) -> CustomSpans:
    """Validate (message_index, start, end) spans against the redacted base text.

    Offsets are Unicode code points, end-exclusive. Overlapping or touching spans in
    one message are merged. A span may cover a mandatory placeholder completely but
    may not cut through one. Raises CustomRedactionInvalid; never echoes text.
    """
    grouped: CustomSpans = {}
    for idx, start, end in spans:
        if not 0 <= idx < len(base) or not 0 <= start < end <= len(base[idx]):
            raise CustomRedactionInvalid("span out of range")
        grouped.setdefault(idx, []).append((start, end))
    out: CustomSpans = {}
    for idx in sorted(grouped):
        merged: list[tuple[int, int]] = []
        for start, end in sorted(grouped[idx]):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        if len(merged) > MAX_CUSTOM_PER_MESSAGE:
            raise CustomRedactionInvalid("too many spans in one message")
        for p_start, p_end in placeholder_spans(base[idx], required_redactions):
            for start, end in merged:
                if start < p_end and p_start < end and not (start <= p_start and p_end <= end):
                    raise CustomRedactionInvalid("span cuts through a mandatory placeholder")
        out[idx] = merged
    if sum(len(v) for v in out.values()) > MAX_CUSTOM_TOTAL:
        raise CustomRedactionInvalid("too many spans")
    return out


def custom_to_wire(custom: CustomSpans) -> list[dict[str, int]]:
    return [{"message_index": i, "start": s, "end": e} for i in sorted(custom) for s, e in custom[i]]


def custom_from_wire(items: list[dict[str, int]]) -> CustomSpans:
    out: CustomSpans = {}
    for item in items:
        out.setdefault(item["message_index"], []).append((item["start"], item["end"]))
    return out


def apply_custom(text: str, spans: list[tuple[int, int]]) -> str:
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + CUSTOM_MARKER + text[end:]
    return text


def has_content(messages: list[str]) -> bool:
    """True if at least one message keeps something besides requester markers and whitespace."""
    return any(_NO_CONTENT.sub("", m) for m in messages)


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def prepare(
    source: SourceSnapshot,
    purpose: str,
    outbound_fields: list[str],
    required_redactions: tuple[str, ...],
    hidden_indices: list[int],
    custom: CustomSpans | None = None,
) -> PreparedPayload:
    if outbound_fields != ["message"]:
        # The v1 payload template carries messages only. Any other configuration
        # must be added through a coordinated contract change, not forwarded.
        raise ValueError("v1 payload supports outbound_fields == ['message'] only")
    dropped = [c for c in source.columns if c not in outbound_fields]
    totals = {t: 0 for t in required_redactions}
    hidden = set(hidden_indices)
    messages: list[str] = []
    custom = custom or {}
    custom_count = 0
    for idx, row in enumerate(source.rows):
        # Mandatory redaction runs on every retained message, hidden or not, so
        # the counts reflect the owner rule independent of requester choices.
        cleaned, counts = redact(row["message"], required_redactions)
        for k, v in counts.items():
            totals[k] += v
        if idx in hidden:
            messages.append(HIDDEN_MARKER)
        else:
            # Requester spans refer to the mandatory-redacted text and can only remove more.
            messages.append(apply_custom(cleaned, custom.get(idx, [])))
            custom_count += len(custom.get(idx, []))
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
        custom_redaction_count=custom_count,
    )
