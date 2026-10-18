"""Local pretrained PERSON detection and request-scoped pseudonyms.

No model is fetched at runtime. Missing dependencies raise DetectorUnavailable
when person_spans is called; callers must block if their policy requires PERSON.
Offsets are Python/Unicode code points, not UTF-16 browser string positions.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Sequence

MODEL_NAME = "en_core_web_sm"
DETECTOR_VERSION = "person-v1"
_LOCK = threading.RLock()
_TYPES = {"EMAIL", "PHONE", "PERSON"}


class DetectorUnavailable(RuntimeError):
    """Required local model cannot run; this is not an empty detection result."""


@lru_cache(maxsize=1)
def load_model():
    try:
        import spacy

        model = spacy.load(MODEL_NAME, exclude=["tagger", "parser", "attribute_ruler", "lemmatizer"])
        if "ner" not in model.pipe_names:
            raise DetectorUnavailable("The installed local model has no NER component.")
        return model
    except (ImportError, OSError, ValueError) as exc:
        raise DetectorUnavailable(
            "Local PERSON detection is unavailable. Install spaCy and en_core_web_sm before enabling PERSON."
        ) from exc


@lru_cache(maxsize=4)
def _artifact_hashes(model_path: str) -> dict[str, str]:
    path = Path(model_path)
    return {
        filename: hashlib.sha256((path / filename).read_bytes()).hexdigest()
        for filename in ("config.cfg", "ner/model", "tok2vec/model")
        if (path / filename).is_file()
    }


def _descriptor() -> dict:
    try:
        spacy_version = metadata.version("spacy")
    except metadata.PackageNotFoundError:
        spacy_version = None
    result = {
        "available": False, "model": MODEL_NAME, "model_version": None,
        "version": None,
        "spacy_version": spacy_version, "detector_version": DETECTOR_VERSION,
        "language": "en", "offset_unit": "unicode_codepoint",
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    try:
        model = load_model()
    except DetectorUnavailable:
        result["reason_code"] = "PERSON_MODEL_UNAVAILABLE"
        return result
    result.update(available=True, model_version=model.meta.get("version"), version=model.meta.get("version"))
    model_path = getattr(model, "path", None)
    result["artifact_hashes"] = _artifact_hashes(str(model_path)) if model_path else {}
    return result


def detector_status() -> dict:
    """Public metadata contains no input text or machine-specific filesystem path."""
    result = _descriptor()
    result["fingerprint"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return result


def detector_fingerprint() -> str:
    """Stable configuration/model fingerprint, including explicit unavailability."""
    return detector_status()["fingerprint"]


def person_spans(text: str) -> list[dict]:
    model = load_model()  # Deliberately raises even for empty text if unavailable.
    try:
        with _LOCK:
            document = model(text)
    except Exception as exc:
        raise DetectorUnavailable("The local PERSON detector could not process this input.") from exc
    method = f"spacy:{MODEL_NAME}:{model.meta.get('version', 'unknown')}"
    return [
        {"start": entity.start_char, "end": entity.end_char, "entity_type": "PERSON", "detector": method}
        for entity in document.ents if entity.label_ == "PERSON"
    ]


def _entity_key(entity_type: str, value: str) -> str:
    if entity_type == "PHONE":
        digits = re.sub(r"\D", "", value)
        return digits[1:] if len(digits) == 11 and digits.startswith("1") else digits
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def pseudonymize_messages(messages: Sequence[str], findings_by_message: Sequence[Sequence[dict]]) -> list[str]:
    """Replace already-resolved nonoverlapping findings before optional hiding.

    Tokens are stable within this call in source order. Equal normalized surfaces
    in the same category share a token; aliases are not resolved. No mapping is
    returned or persisted. These linkable tokens do not establish anonymity.
    EMAIL/PHONE/PERSON overlap precedence belongs to the calling detector merger.
    """
    if len(messages) != len(findings_by_message):
        raise ValueError("Messages and finding groups must have equal lengths.")
    tokens: dict[tuple[str, str], str] = {}
    counts: dict[str, int] = {}
    output: list[str] = []
    for text, findings in zip(messages, findings_by_message):
        spans = []
        for finding in findings:
            start, end = finding.get("start"), finding.get("end")
            category = finding.get("entity_type")
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
                raise ValueError("Invalid entity offsets.")
            if category not in _TYPES:
                raise ValueError("Unsupported pseudonym category.")
            spans.append((start, end, category))
        spans.sort(key=lambda span: (span[0], span[1], span[2]))
        chunks, cursor = [], 0
        for start, end, category in spans:
            if start < cursor:
                raise ValueError("Resolve overlapping findings before pseudonymizing.")
            key = (category, _entity_key(category, text[start:end]))
            if key not in tokens:
                counts[category] = counts.get(category, 0) + 1
                tokens[key] = f"[{category}_{counts[category]:03d}]"
            chunks.extend((text[cursor:start], tokens[key]))
            cursor = end
        chunks.append(text[cursor:])
        output.append("".join(chunks))
    return output
