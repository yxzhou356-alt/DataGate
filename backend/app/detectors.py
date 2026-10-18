"""Local PERSON-name detection behind a small, replaceable interface.

A detector returns typed spans (Unicode code-point offsets, end-exclusive) with an
optional confidence. Detection is always local: nothing is sent to an external
service. ``detect_persons`` validates every span and fails closed (DetectorError)
on exceptions, invalid offsets or wrong types; callers must not fall back to sending
the text unchanged.

The default ``LexiconPersonDetector`` is deliberately simple and deterministic:
- a committed given-name lexicon (``data/person_given_names.txt``), matched
  case-insensitively after Unicode NFC; ambiguous names (also everyday words or
  brands) need context: an honorific before them or a capitalized surname after;
- honorifics (Mr, Ms, Dr, ...) followed by capitalized words;
- extension over up to two following capitalized surname-like tokens (including
  hyphenated and apostrophe forms, and particles such as "van", "de");
- a guard that drops matches followed by an organization word (Inc, Bank, ...).

It does not understand meaning. It misses names absent from the lexicon and can
mislabel capitalized words; see the evaluation (python -m app.person_eval). A model
score or a clean result is never proof that a text contains no personal data.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

LEXICON_PATH = Path(__file__).resolve().parent / "data" / "person_given_names.txt"
# Bump when detection logic changes; with the lexicon hash it forms the detector version,
# which is part of the approval freshness check (TRANSFORM_CHANGED).
LEXICON_LOGIC_VERSION = "1.2"
CHUNK_CHARS = 2000
CHUNK_OVERLAP = 200


@dataclass(frozen=True)
class DetectedSpan:
    start: int
    end: int
    type: str = "PERSON"
    confidence: float | None = None


class DetectorError(Exception):
    """Detection could not be completed safely. The message never contains input text."""


class PersonDetector(Protocol):
    version: str

    def detect(self, text: str) -> list[DetectedSpan]: ...


# --------------------------------------------------------------------------- #
# Validation + chunking wrapper (used for every detector)
# --------------------------------------------------------------------------- #
def _validated(spans: object, text: str) -> list[DetectedSpan]:
    if not isinstance(spans, (list, tuple)):
        raise DetectorError("detector returned an unexpected result")
    out = []
    for s in spans:
        if not isinstance(s, DetectedSpan) or s.type != "PERSON":
            raise DetectorError("detector returned an unexpected span")
        if not (isinstance(s.start, int) and isinstance(s.end, int)) or isinstance(s.start, bool) or isinstance(s.end, bool):
            raise DetectorError("detector returned invalid offsets")
        if not 0 <= s.start < s.end <= len(text):
            raise DetectorError("detector returned invalid offsets")
        if s.confidence is not None and not (isinstance(s.confidence, (int, float)) and 0 <= s.confidence <= 1):
            raise DetectorError("detector returned an invalid confidence")
        out.append(s)
    return out


def _chunks(text: str) -> list[tuple[int, int]]:
    """Overlapping windows cut at whitespace, so a name near a boundary is seen whole."""
    if len(text) <= CHUNK_CHARS:
        return [(0, len(text))]
    windows, start = [], 0
    while start < len(text):
        end = min(len(text), start + CHUNK_CHARS)
        if end < len(text):
            cut = text.rfind(" ", start + CHUNK_CHARS // 2, end)
            end = cut if cut != -1 else end
        windows.append((start, end))
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return windows


def detect_persons(detector: PersonDetector, text: str) -> list[tuple[int, int]]:
    """Validated, merged PERSON spans for ``text``. Raises DetectorError, never returns partial output."""
    if not text:
        return []
    found: set[tuple[int, int]] = set()
    try:
        for c_start, c_end in _chunks(text):
            piece = text[c_start:c_end]
            for s in _validated(detector.detect(piece), piece):
                found.add((c_start + s.start, c_start + s.end))
    except DetectorError:
        raise
    except Exception as exc:  # noqa: BLE001 - any detector fault must fail closed
        raise DetectorError("detector failed") from exc
    merged: list[tuple[int, int]] = []
    for start, end in sorted(found):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


# --------------------------------------------------------------------------- #
# Default local detector
# --------------------------------------------------------------------------- #
# Letters plus combining marks, so decomposed (NFD) names tokenize like their NFC form.
_LETTER = r"(?:[^\W\d_]|[\u0300-\u036f])"
_TOKEN = re.compile(rf"{_LETTER}+(?:['’\-]{_LETTER}+)*")
HONORIFICS = {"mr", "mrs", "ms", "mx", "miss", "dr", "prof", "professor", "sir", "dame", "madam", "señor", "señora", "herr", "frau"}
PARTICLES = {"van", "von", "de", "da", "del", "della", "der", "di", "du", "la", "le", "bin", "binti", "ibn", "al"}
ORG_WORDS = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "bank", "labs", "group", "foundation",
             "university", "hospital", "airlines", "motors", "brand", "stanley", "&"}
# Capitalized words that are never treated as surnames when they follow a given name.
NOT_SURNAMES = {"i", "the", "a", "an", "and", "or", "but", "if", "when", "then", "please", "thanks", "thank", "hi",
                "hello", "dear", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                "november", "december", "android", "ios", "windows", "mac", "app", "pdf", "api", "csv", "support"}


def _norm(word: str) -> str:
    return unicodedata.normalize("NFC", word).casefold()


def _strip_possessive(token: str) -> str:
    return token[:-2] if len(token) > 2 and token[-2] in "'’" and token[-1] in "sS" else token


def _is_capitalized(token: str) -> bool:
    return token[:1].isupper()


class LexiconPersonDetector:
    """Deterministic lexicon + context detector. See module docstring for its limits."""

    def __init__(self, lexicon_path: Path = LEXICON_PATH):
        raw = lexicon_path.read_bytes()
        names, ambiguous = set(), set()
        for line in raw.decode("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            (ambiguous if line.startswith("?") else names).add(_norm(line.lstrip("?")))
        self.names = frozenset(names)
        self.ambiguous = frozenset(ambiguous)
        self.version = f"lexicon-{LEXICON_LOGIC_VERSION}:{hashlib.sha256(raw).hexdigest()[:12]}"

    def _given(self, token: str) -> str | None:
        """'certain' / 'ambiguous' / None for a token (hyphenated given names use their first part)."""
        base = _norm(_strip_possessive(token))
        for candidate in (base, base.split("-")[0]):
            if candidate in self.names:
                return "certain"
            if candidate in self.ambiguous:
                return "ambiguous"
        return None

    def detect(self, text: str) -> list[DetectedSpan]:
        tokens = [(m.start(), m.end(), m.group()) for m in _TOKEN.finditer(text)]
        spans: list[DetectedSpan] = []
        i = 0
        while i < len(tokens):
            start, end, tok = tokens[i]
            prev = tokens[i - 1][2] if i > 0 else ""
            after_honorific = _norm(prev) in HONORIFICS and _is_capitalized(tok)
            kind = self._given(tok)
            # Surname extension: following capitalized, single-space-separated tokens.
            j, last_end = i, end
            while j + 1 < len(tokens) and j - i < 2:
                n_start, n_end, n_tok = tokens[j + 1]
                gap = text[last_end:n_start]
                if gap != " ":
                    break
                # Up to two lowercase particles ("van", "de la") before a capitalized surname.
                k = j + 1
                while k < len(tokens) and k - j <= 2 and _norm(tokens[k][2]) in PARTICLES \
                        and k + 1 < len(tokens) and text[tokens[k][1]:tokens[k + 1][0]] == " ":
                    k += 1
                if k > j + 1 and k < len(tokens) and _is_capitalized(tokens[k][2]) \
                        and _norm(tokens[k][2]) not in NOT_SURNAMES | ORG_WORDS:
                    j, last_end = k, tokens[k][1]
                    continue
                if not _is_capitalized(n_tok) or _norm(_strip_possessive(n_tok)) in NOT_SURNAMES | ORG_WORDS:
                    break
                j, last_end = j + 1, n_end
            has_surname = j > i
            accept = (kind == "certain" or after_honorific
                      or (kind == "ambiguous" and _is_capitalized(tok) and has_surname))
            if accept:
                following = tokens[j + 1][2] if j + 1 < len(tokens) else ""
                between = text[last_end:tokens[j + 1][0]] if j + 1 < len(tokens) else ""
                if _norm(following) in ORG_WORDS or "&" in between:
                    i = j + 1
                    continue
                span_end = last_end
                last_tok = tokens[j][2]
                if _strip_possessive(last_tok) != last_tok:
                    span_end -= 2  # "Emma's" -> "Emma"
                confidence = 0.9 if kind == "certain" else 0.75 if after_honorific else 0.6
                spans.append(DetectedSpan(start, span_end, "PERSON", confidence))
                i = j + 1
                continue
            i += 1
        return spans


class UnavailableDetector:
    """Stands in when the configured detector cannot be loaded. Always fails closed."""

    version = "unavailable"

    def detect(self, text: str) -> list[DetectedSpan]:
        raise DetectorError("person detector is unavailable")


def build_person_detector(mode: str) -> PersonDetector:
    if mode == "lexicon":
        try:
            return LexiconPersonDetector()
        except OSError:
            return UnavailableDetector()
    return UnavailableDetector()  # "unavailable" (demo of fail-closed) or any unknown mode
