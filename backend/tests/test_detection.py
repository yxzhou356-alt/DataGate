"""Detector availability, Unicode offsets, pseudonym scope, and honest scoring."""

import json
from types import SimpleNamespace

import pytest

from app import detection
from evaluation.corpus import examples
from evaluation.run import score


def span(text, value, category="PERSON"):
    start = text.index(value)
    return {"start": start, "end": start + len(value), "entity_type": category}


def test_missing_model_is_an_error_even_for_empty_input(monkeypatch):
    def unavailable():
        raise detection.DetectorUnavailable("Missing local model")

    monkeypatch.setattr(detection, "load_model", unavailable)
    for value in ("My name is Alice Johnson.", ""):
        with pytest.raises(detection.DetectorUnavailable):
            detection.person_spans(value)
    status = detection.detector_status()
    assert status["available"] is False
    assert status["reason_code"] == "PERSON_MODEL_UNAVAILABLE"
    assert len(status["fingerprint"]) == 64
    assert detection.detector_fingerprint() == status["fingerprint"]


def test_person_spans_use_codepoint_offsets_and_exclude_other_entities(monkeypatch):
    text = "👋 Zoë Chen called from Paris."
    person = SimpleNamespace(start_char=text.index("Zoë"), end_char=text.index(" called"), label_="PERSON")
    place = SimpleNamespace(start_char=text.index("Paris"), end_char=text.index("Paris") + 5, label_="GPE")

    class Model:
        meta = {"version": "test-only"}

        def __call__(self, value):
            assert value == text
            return SimpleNamespace(ents=[person, place])

    monkeypatch.setattr(detection, "load_model", lambda: Model())
    findings = detection.person_spans(text)
    assert len(findings) == 1
    assert text[findings[0]["start"]:findings[0]["end"]] == "Zoë Chen"
    assert findings[0]["start"] == 2  # An emoji is one Python code point.
    assert findings[0]["entity_type"] == "PERSON"
    assert findings[0]["detector"].startswith("spacy:en_core_web_sm:")
    assert "Zoë Chen" not in json.dumps(findings)


def test_inference_failure_is_not_silently_converted_to_empty_findings(monkeypatch):
    class BrokenModel:
        def __call__(self, _text):
            raise ValueError("Synthetic inference failure")

    monkeypatch.setattr(detection, "load_model", lambda: BrokenModel())
    with pytest.raises(detection.DetectorUnavailable):
        detection.person_spans("Synthetic customer content")


def test_pseudonyms_are_request_wide_source_ordered_and_category_separated():
    messages = ["Alice Chen uses alice@example.com.", "ALICE CHEN spoke with Ben Moore.", "Email ALICE@example.com again."]
    findings = [
        [span(messages[0], "Alice Chen"), span(messages[0], "alice@example.com", "EMAIL")],
        [span(messages[1], "ALICE CHEN"), span(messages[1], "Ben Moore")],
        [span(messages[2], "ALICE@example.com", "EMAIL")],
    ]
    assert detection.pseudonymize_messages(messages, findings) == [
        "[PERSON_001] uses [EMAIL_001].", "[PERSON_001] spoke with [PERSON_002].", "Email [EMAIL_001] again.",
    ]
    # A new request resets numbering; no module-level map persists raw values.
    assert detection.pseudonymize_messages(["Ben Moore"], [[span("Ben Moore", "Ben Moore")]]) == ["[PERSON_001]"]


def test_phone_pseudonyms_normalize_documented_us_formats():
    messages = ["+1 (213) 555-0105", "213-555-0105"]
    findings = [[span(text, text, "PHONE")] for text in messages]
    assert detection.pseudonymize_messages(messages, findings) == ["[PHONE_001]", "[PHONE_001]"]


def test_pseudonym_replacements_preserve_unicode_and_surrounding_text():
    text = "👋 Zoë Chen: café issue."
    assert detection.pseudonymize_messages([text], [[span(text, "Zoë Chen")]]) == ["👋 [PERSON_001]: café issue."]


@pytest.mark.parametrize("finding", [
    {"start": True, "end": 3, "entity_type": "PERSON"},
    {"start": -1, "end": 3, "entity_type": "PERSON"},
    {"start": 0, "end": 999, "entity_type": "PERSON"},
    {"start": 0, "end": 1, "entity_type": "UNSUPPORTED"},
])
def test_invalid_pseudonym_findings_fail_instead_of_leaking_or_corrupting_text(finding):
    with pytest.raises(ValueError):
        detection.pseudonymize_messages(["Alice"], [[finding]])


def test_pseudonymizer_requires_resolved_overlaps_and_aligned_messages():
    with pytest.raises(ValueError):
        detection.pseudonymize_messages(["Alice Chen"], [[span("Alice Chen", "Alice"), span("Alice Chen", "Alice Chen")]])
    with pytest.raises(ValueError):
        detection.pseudonymize_messages(["Alice"], [])


def test_explicit_corpus_labels_are_valid_and_splits_have_distinct_texts():
    development, heldout = examples("development"), examples("heldout")
    assert len(development) == 16
    assert len(heldout) == 40
    assert not {example["text"] for example in development} & {example["text"] for example in heldout}
    for example in development + heldout:
        assert "[[" not in example["text"]
        for entity in example["entities"]:
            assert 0 <= entity["start"] < entity["end"] <= len(example["text"])
            assert entity["entity_type"] in {"PERSON", "EMAIL", "PHONE"}


def test_exact_span_metrics_count_boundary_mismatch_as_false_positive_and_miss():
    dataset = [{"id": "synthetic-1", "text": "SECRET_PERSON", "entities": [{"start": 0, "end": 13, "entity_type": "PERSON"}]}]
    result = score(dataset, lambda _: [{"start": 0, "end": 6, "entity_type": "PERSON"}])
    assert result["per_category"]["PERSON"] == {"tp": 0, "fp": 1, "fn": 1, "support": 1, "precision": 0, "recall": 0, "f1": 0}
    assert len(result["errors"]) == 2
    assert "SECRET_PERSON" not in json.dumps(result)


def test_undefined_metrics_are_null_instead_of_fabricated_perfect_scores():
    result = score([{"id": "none", "text": "No identifiers", "entities": []}], lambda _: [])
    assert result["micro"]["precision"] is None
    assert result["micro"]["recall"] is None
    assert result["micro"]["f1"] is None


def test_missing_model_evaluation_has_no_fake_hybrid_metrics(monkeypatch):
    from evaluation import run

    monkeypatch.setattr(run, "detector_status", lambda: {"available": False, "model": "en_core_web_sm", "reason_code": "PERSON_MODEL_UNAVAILABLE"})
    report = run.evaluate("heldout")
    assert report["status"] == "model_unavailable"
    assert report["rules_plus_ner"] is None
    assert report["rules_only"]["per_category"]["PERSON"]["fn"] > 0
    assert "Chloe Davis" not in json.dumps(report)


def test_installed_pretrained_model_produces_real_person_findings():
    if not detection.detector_status()["available"]:
        pytest.skip("Local pretrained model not installed; explicit-unavailable tests still run")
    text = "My name is Alice Johnson."
    findings = detection.person_spans(text)
    assert any(text[item["start"]:item["end"]] == "Alice Johnson" for item in findings)
