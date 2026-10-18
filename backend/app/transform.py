"""Source loading, validation, minimization, redaction and canonical payloads.

Pipeline (always in this order, always on the backend):
1. Read the current source bytes and hash them.
2. Validate: ticket_id and a nonempty message on every row; no malformed rows.
   Rows are never silently repaired or dropped.
3. Keep only the policy's outbound fields for the purpose (baseline: message).
4. Rewrite source-authored placeholder-like tokens ("[PERSON_1]" -> "(PERSON_1)") so
   square-bracket tokens in outbound text only ever come from DataGate.
5. Mandatory redaction by span offsets on each message: EMAIL, then PHONE, then PERSON.
   Precedence: EMAIL > PHONE > PERSON. A PHONE match overlapping an EMAIL is dropped;
   PERSON spans are trimmed to exclude EMAIL/PHONE ranges (no name fragment survives
   next to an address), and overlapping PERSON spans are merged. Each source character
   is replaced at most once, right to left by offset.
   PERSON style "numbered" assigns [PERSON_1], [PERSON_2], ... over ALL messages in
   source order (before hiding) by normalized name; the mapping lives only in memory.
6. Replace requester-selected spans of the redacted text with [REDACTED_BY_USER].
7. Replace requester-hidden messages with [HIDDEN_BY_USER].
8. Serialize the canonical payload and hash it.

Requester choices are applied after mandatory redaction and can only hide more.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .detectors import DetectorError, PersonDetector, detect_persons

SCHEMA_VERSION = "1.0"
INSTRUCTIONS = {
    "feedback_summary": "Summarize the recurring product issues in the provided messages.",
}
# Bump when the transformation changes output for the same source + policy; it is part of
# the freshness check, so open approvals become stale (TRANSFORM_CHANGED).
TRANSFORM_VERSION = "2"
PERSON_STYLES = ("generic", "numbered")
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


class DetectorUnavailable(Exception):
    """PERSON redaction is required but detection failed. Nothing may be prepared or sent."""


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


_SOURCE_TOKEN = re.compile(r"\[(EMAIL|PHONE|PERSON(?:_\d+)?|HIDDEN_BY_USER|REDACTED_BY_USER)\]", re.IGNORECASE)
_EDGE = " \t\n\r.,;:!?()[]{}\"'’-"


def escape_source_tokens(text: str) -> str:
    """'[PERSON_1]' written in the source becomes '(PERSON_1)', so the receiver cannot
    mistake it for a DataGate token (case-insensitive, all DataGate token names)."""
    return _SOURCE_TOKEN.sub(lambda m: f"({m.group(1)})", text)


def normalize_person(name: str) -> str:
    """Conservative equality for numbering: NFC, trimmed, internal whitespace collapsed,
    case-folded. No substring/alias merging: 'Ann' != 'Anna', 'Emma' != 'Emma Lawson'."""
    return " ".join(unicodedata.normalize("NFC", name).split()).casefold()


def pipeline_id(required_redactions: tuple[str, ...], person_detector: PersonDetector | None) -> str:
    """Identifies the transformation in force; part of the approval freshness check."""
    detector = None
    if "PERSON" in required_redactions:
        detector = person_detector.version if person_detector is not None else "unavailable"
    body = json.dumps({"transform": TRANSFORM_VERSION, "person_detector": detector}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def _subtract(span: tuple[int, int], blockers: list[tuple[int, int]], text: str) -> list[tuple[int, int]]:
    """Parts of ``span`` outside every blocker, trimmed of whitespace/punctuation edges."""
    parts = [span]
    for b_start, b_end in blockers:
        next_parts = []
        for start, end in parts:
            if b_end <= start or end <= b_start:
                next_parts.append((start, end))
                continue
            if start < b_start:
                next_parts.append((start, b_start))
            if b_end < end:
                next_parts.append((b_end, end))
        parts = next_parts
    trimmed = []
    for start, end in parts:
        while start < end and text[start] in _EDGE:
            start += 1
        while end > start and text[end - 1] in _EDGE:
            end -= 1
        if start < end:
            trimmed.append((start, end))
    return trimmed


def _message_spans(text: str, required: tuple[str, ...], person_detector: PersonDetector | None) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    emails = [(m.start(), m.end()) for m in PATTERNS["EMAIL"].finditer(text)] if "EMAIL" in required else []
    spans += [(s, e, "EMAIL") for s, e in emails]
    phones: list[tuple[int, int]] = []
    if "PHONE" in required:
        masked = list(text)
        for s, e in emails:  # an email's digits are never read as a phone number
            masked[s:e] = "\x00" * (e - s)
        phones = [(m.start(), m.end()) for m in PATTERNS["PHONE"].finditer("".join(masked))]
        spans += [(s, e, "PHONE") for s, e in phones]
    if "PERSON" in required:
        if person_detector is None:
            raise DetectorUnavailable()
        try:
            persons = detect_persons(person_detector, text)
        except DetectorError:
            raise DetectorUnavailable()
        protected = sorted(emails + phones)
        trimmed = sorted({p for span in persons for p in _subtract(span, protected, text)})
        merged: list[tuple[int, int]] = []
        for s, e in trimmed:
            if merged and s < merged[-1][1]:
                merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
            else:
                merged.append((s, e))
        spans += [(s, e, "PERSON") for s, e in merged]
    return sorted(spans)


def mandatory_redact(
    messages: list[str],
    required_redactions: tuple[str, ...],
    person_detector: PersonDetector | None = None,
    person_style: str = "generic",
) -> tuple[list[str], dict[str, int]]:
    """Owner-required redaction of every message (all rows, before any hiding).

    Returns the redacted texts and span counts per type. The person-to-number mapping is
    built here from source order and discarded; it is never returned or stored.
    Raises DetectorUnavailable if PERSON is required and detection fails.
    """
    if person_style not in PERSON_STYLES:
        raise ValueError("unknown person style")
    counts = {t: 0 for t in required_redactions}
    plans = []
    for message in messages:
        text = escape_source_tokens(message)
        plans.append((text, _message_spans(text, required_redactions, person_detector)))

    numbers: dict[str, int] = {}
    if person_style == "numbered":
        for text, spans in plans:  # source order, then offset order
            for start, end, rtype in spans:
                if rtype == "PERSON":
                    numbers.setdefault(normalize_person(text[start:end]), len(numbers) + 1)

    out = []
    for text, spans in plans:
        for start, end, rtype in reversed(spans):  # right to left: offsets stay valid
            if rtype == "PERSON" and person_style == "numbered":
                token = f"[PERSON_{numbers[normalize_person(text[start:end])]}]"
            else:
                token = f"[{rtype}]"
            text = text[:start] + token + text[end:]
            counts[rtype] += 1
        out.append(text)
    return out, counts


def redact(
    text: str,
    redaction_types: tuple[str, ...],
    person_detector: PersonDetector | None = None,
    person_style: str = "generic",
) -> tuple[str, dict[str, int]]:
    """Mandatory redaction of a single message (see mandatory_redact)."""
    texts, counts = mandatory_redact([text], redaction_types, person_detector, person_style)
    return texts[0], counts


def redacted_messages(
    source: SourceSnapshot,
    required_redactions: tuple[str, ...],
    person_detector: PersonDetector | None = None,
    person_style: str = "generic",
) -> list[str]:
    """The mandatory-redacted text of every message: the base that requester spans refer to."""
    return mandatory_redact([row["message"] for row in source.rows], required_redactions, person_detector, person_style)[0]


_PLACEHOLDER = re.compile(r"\[(EMAIL|PHONE|PERSON(?:_\d+)?)\]")


def placeholder_spans(text: str, required_redactions: tuple[str, ...]) -> list[tuple[int, int]]:
    spans = []
    for m in _PLACEHOLDER.finditer(text):
        if m.group(1).split("_")[0] in required_redactions:
            spans.append((m.start(), m.end()))
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
    person_detector: PersonDetector | None = None,
    person_style: str = "generic",
) -> PreparedPayload:
    if outbound_fields != ["message"]:
        # The v1 payload template carries messages only. Any other configuration
        # must be added through a coordinated contract change, not forwarded.
        raise ValueError("v1 payload supports outbound_fields == ['message'] only")
    dropped = [c for c in source.columns if c not in outbound_fields]
    # Mandatory redaction runs on every retained message, hidden or not, so counts and
    # PERSON numbering reflect the owner rule independent of requester choices.
    cleaned, totals = mandatory_redact(
        [row["message"] for row in source.rows], required_redactions, person_detector, person_style
    )
    hidden = set(hidden_indices)
    messages: list[str] = []
    custom = custom or {}
    custom_count = 0
    for idx, text in enumerate(cleaned):
        if idx in hidden:
            messages.append(HIDDEN_MARKER)
        else:
            # Requester spans refer to the mandatory-redacted text and can only remove more.
            messages.append(apply_custom(text, custom.get(idx, [])))
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
