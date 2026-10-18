"""Feature 4: local PERSON detection, overlap precedence, fail-closed behaviour, owner control."""

from __future__ import annotations

import sqlite3

import pytest

from conftest import PREVIEW_A, login, preview, send
from person_support import FlakyDetector, StubDetector, require_person, span, write_source

from app import demo_control, transform
from app.detectors import CHUNK_CHARS, DetectorError, LexiconPersonDetector, detect_persons
from app.person_eval import EVAL_PATH, evaluate, load_examples, parse_marked
from app.storage import Store

LEX = LexiconPersonDetector()
ALL = ("EMAIL", "PHONE", "PERSON")


def _redact(text, detector=LEX, types=ALL, style="generic"):
    return transform.redact(text, types, detector, style)


# ------------------------------------------------------------------ detector unit --
@pytest.mark.parametrize("text,names", [
    ("Emma reported a problem. Emma called again.", ["Emma", "Emma"]),
    ("emma and EMMA and Emma", ["emma", "EMMA", "Emma"]),
    ("Liam O'Brien and Anne-Marie wrote", ["Liam O'Brien", "Anne-Marie"]),
    ("Chloé Dubois, José García and Søren", ["Chloé Dubois", "José García", "Søren"]),
    ("Ask Dr. Patel or Ms O'Neil", ["Patel", "O'Neil"]),
    ("Thanks, Priya!", ["Priya"]),
    ("Emma's laptop", ["Emma"]),
    ("Maria de la Cruz paid", ["Maria de la Cruz"]),
    ("Grace Turner called. Grace period ended. I will check in May.", ["Grace Turner"]),
    ("Morgan Stanley, Johnson & Johnson, Victoria Bank and Alexa", []),
    ("The Export Settings page shows Error 500.", []),
    ("", []),
])
def test_lexicon_detector_cases(text, names):
    assert [text[s:e] for s, e in detect_persons(LEX, text)] == names


def test_detector_is_deterministic_and_versioned():
    text = "Emma contacted Liam O'Brien about Chloé's refund."
    assert detect_persons(LEX, text) == detect_persons(LexiconPersonDetector(), text)
    assert LEX.version.startswith("lexicon-") and LEX.version == LexiconPersonDetector().version


def test_unicode_offsets_are_code_points():
    text = "😀😀 Søren and Zoë wrote 𝔘"
    spans = detect_persons(LEX, text)
    assert [text[s:e] for s, e in spans] == ["Søren", "Zoë"]
    assert spans[0] == (3, 8)  # each emoji is one code point in Python


def test_long_messages_are_chunked_without_losing_or_duplicating_names():
    filler = "word " * (CHUNK_CHARS // 5 - 1)
    text = filler + "Emma Lawson met Liam " + filler + "and Priya " + filler
    assert len(text) > 2 * CHUNK_CHARS
    spans = detect_persons(LEX, text)
    assert [text[s:e] for s, e in spans] == ["Emma Lawson", "Liam", "Priya"]
    assert spans == sorted(set((s.start, s.end) for s in LEX.detect(text)))


@pytest.mark.parametrize("bad", [
    StubDetector(exc=RuntimeError("model not downloaded")),
    StubDetector(exc=MemoryError()),
    StubDetector(spans=[span(0, 99)]),            # past the end
    StubDetector(spans=[span(3, 3)]),             # empty
    StubDetector(spans=[span(-1, 2)]),
    StubDetector(spans=[span(True, 2)]),          # bool is not an offset
    StubDetector(spans=[span(0, 2, "ORG")]),      # wrong type
    StubDetector(spans=[span(0, 2, confidence=1.5)]),
    StubDetector(spans=[(0, 2)]),                 # not a DetectedSpan
])
def test_invalid_detector_output_fails_closed(bad):
    with pytest.raises(DetectorError):
        detect_persons(bad, "Emma wrote")
    with pytest.raises(transform.DetectorUnavailable):
        _redact("Emma wrote", detector=bad)


def test_missing_detector_fails_closed_only_when_person_is_required():
    with pytest.raises(transform.DetectorUnavailable):
        transform.redact("Emma wrote", ALL, None)
    boom = StubDetector(exc=RuntimeError())
    assert transform.redact("Emma wrote a@b.co", ("EMAIL", "PHONE"), boom)[0] == "Emma wrote [EMAIL]"
    assert boom.calls == 0


# ------------------------------------------------------------------- precedence --
def test_email_and_phone_win_and_no_name_fragment_leaks():
    out, counts = _redact("Contact emma.lawson@example.com or Emma at 213-555-0142.")
    assert out == "Contact [EMAIL] or [PERSON] at [PHONE]."
    assert counts == {"EMAIL": 1, "PHONE": 1, "PERSON": 1}
    # A detector span reaching into the email is trimmed, not dropped and not doubled.
    text = "Emma emma.lawson@example.com"
    out, counts = _redact(text, detector=StubDetector(spans=[span(0, 10)]))
    assert out == "[PERSON] [EMAIL]" and counts["PERSON"] == 1 and "emma" not in out.lower()


def test_overlapping_person_spans_are_merged_and_each_character_replaced_once():
    out, counts = _redact("Mary Ann Smith called", detector=StubDetector(spans=[span(0, 8), span(5, 14), span(0, 4)]))
    assert out == "[PERSON] called" and counts["PERSON"] == 1


def test_phone_digits_inside_email_are_not_a_phone():
    out, counts = _redact("mail 213-555-0142@example.com now")
    assert out == "mail [EMAIL] now" and counts["PHONE"] == 0


def test_source_authored_tokens_are_escaped_before_redaction():
    out, counts = _redact("Literal [EMAIL] and [person_1] and [REDACTED_BY_USER] from Emma")
    assert out == "Literal (EMAIL) and (person_1) and (REDACTED_BY_USER) from [PERSON]"
    assert counts["EMAIL"] == 0 and counts["PERSON"] == 1


def test_email_and_phone_rules_are_unchanged_without_person():
    out, counts = transform.redact("Emma: a@b.co, 213-555-0142", ("EMAIL", "PHONE"))
    assert out == "Emma: [EMAIL], [PHONE]" and counts == {"EMAIL": 1, "PHONE": 1}


# ------------------------------------------------------------------ API behaviour --
NAMED = ["Emma reported that the export fails.", "Liam O'Brien asked Emma to resend emma@example.com.",
         "Nothing personal here."]


def test_owner_policy_controls_person_redaction(client, a, settings, receiver):
    write_source(settings, NAMED)
    p = preview(client, a).json()
    assert "Emma" in p["outbound_payload"]["messages"][0]  # not required by this owner policy
    assert "PERSON" not in p["redaction_counts"]
    require_person(settings)
    p = preview(client, a).json()
    assert p["outbound_payload"]["messages"][:2] == [
        "[PERSON] reported that the export fails.", "[PERSON] asked [PERSON] to resend [EMAIL]."]
    assert p["redaction_counts"] == {"EMAIL": 1, "PHONE": 0, "PERSON": 3} and p["decision"] == "redact"
    ds = client.get("/api/datasets", headers=a).json()["datasets"][0]["passport"]
    assert ds["required_redactions"] == ["EMAIL", "PHONE", "PERSON"] and ds["person_style"] == "generic"
    assert send(client, a, p).status_code == 200
    sent = receiver.invocations[0][1].decode()
    assert "Emma" not in sent and "Liam" not in sent


@pytest.mark.scenario("SEC-15")
def test_detector_unavailable_at_preview_prepares_nothing(app, client, a, settings, receiver):
    write_source(settings, NAMED)
    require_person(settings)
    app.state.workflow.person_detector = StubDetector(exc=RuntimeError("model missing"))
    r = preview(client, a)
    assert r.status_code == 503 and r.json()["error"]["code"] == "DETECTOR_UNAVAILABLE"
    assert "Emma" not in r.text and "model missing" not in r.text
    assert client.get("/api/receipts", headers=a).json()["receipts"] == []
    assert receiver.invocations == []


@pytest.mark.scenario("SEC-15")
def test_detector_failure_at_send_blocks_dispatch(app, client, a, settings, receiver):
    write_source(settings, NAMED)
    require_person(settings)
    p = preview(client, a).json()
    app.state.workflow.person_detector = StubDetector(exc=RuntimeError(), version=LEX.version)  # same version, now failing
    r = send(client, a, p)
    assert r.status_code == 503 and r.json()["error"]["code"] == "DETECTOR_UNAVAILABLE"
    assert receiver.invocations == []
    assert send(client, a, p).json()["error"]["code"] == "REQUEST_NOT_READY"  # stored stale
    [item] = client.get("/api/receipts", headers=a).json()["receipts"]
    assert item["status"] == "stale" and item["reason_codes"] == ["DETECTOR_UNAVAILABLE"]


@pytest.mark.scenario("SEC-15")
def test_detector_marked_unavailable_at_send_blocks_dispatch(app, client, a, settings, receiver):
    from app.detectors import UnavailableDetector
    write_source(settings, NAMED)
    require_person(settings)
    p = preview(client, a).json()
    app.state.workflow.person_detector = UnavailableDetector()
    assert send(client, a, p).json()["error"]["code"] == "DETECTOR_UNAVAILABLE"
    assert receiver.invocations == []


@pytest.mark.scenario("SEC-15")
def test_detector_failure_during_review_fails_closed(app, client, a, settings, receiver):
    write_source(settings, NAMED)
    require_person(settings)
    p = preview(client, a).json()
    app.state.workflow.person_detector = StubDetector(exc=RuntimeError(), version=LEX.version)
    r = client.patch(f"/api/requests/{p['request_id']}/review", headers=a,
                     json={"expected_review_revision": 1, "hide_message_indices": [2]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "DETECTOR_UNAVAILABLE"
    assert send(client, a, p).json()["error"]["code"] == "REQUEST_NOT_READY"
    assert receiver.invocations == []


@pytest.mark.scenario("SEC-10")
def test_detector_version_change_invalidates_approval(app, client, a, settings, receiver):
    write_source(settings, NAMED)
    require_person(settings)
    p = preview(client, a).json()
    app.state.workflow.person_detector = StubDetector(version="lexicon-9.9:other")
    r = send(client, a, p)
    assert r.status_code == 409 and r.json()["error"]["code"] == "TRANSFORM_CHANGED"
    assert receiver.invocations == []


def test_nondeterministic_detector_never_sends_a_best_effort_rebuild(app, client, a, settings, receiver):
    write_source(settings, NAMED)
    require_person(settings)
    app.state.workflow.person_detector = FlakyDetector()
    p = preview(client, a).json()
    r = send(client, a, p)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PREVIEW_CHANGED"
    assert receiver.invocations == []


def test_detector_outage_does_not_affect_policies_without_person(app, client, a, receiver):
    app.state.workflow.person_detector = StubDetector(exc=RuntimeError())
    p = preview(client, a).json()
    assert p["status"] == "ready" and send(client, a, p).status_code == 200


@pytest.mark.scenario("SEC-14")
def test_receipts_and_lists_never_contain_detected_names(client, a, settings):
    write_source(settings, NAMED)
    require_person(settings)
    p = preview(client, a).json()
    send(client, a, p)
    for text in (client.get(f"/api/requests/{p['request_id']}/receipt", headers=a).text,
                 client.get("/api/receipts", headers=a).text):
        assert "Emma" not in text and "Liam" not in text and "O'Brien" not in text
    rec = client.get(f"/api/requests/{p['request_id']}/receipt", headers=a).json()
    assert rec["redaction_counts"]["PERSON"] == 3


def test_custom_redaction_cannot_cut_a_person_placeholder(client, a, settings):
    write_source(settings, NAMED)
    require_person(settings)
    p = preview(client, a).json()
    at = p["outbound_payload"]["messages"][0].index("[PERSON]")
    r = client.patch(f"/api/requests/{p['request_id']}/review", headers=a, json={
        "expected_review_revision": 1, "hide_message_indices": [],
        "custom_redactions": [{"message_index": 0, "start": at + 1, "end": at + 4}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REVIEW"


def test_older_policy_table_gains_person_style(tmp_path):
    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE policies (dataset_id TEXT PRIMARY KEY, policy_version INTEGER NOT NULL, "
                     "allowed_purposes TEXT NOT NULL, allowed_destinations TEXT NOT NULL, outbound_fields TEXT NOT NULL, "
                     "sharing_mode TEXT NOT NULL, required_redactions TEXT NOT NULL)")
        conn.execute("INSERT INTO policies VALUES ('d', 1, '[]', '[]', '{}', 'redacted_only', '[\"EMAIL\"]')")
    store = Store(db)
    assert store.get_policy("d").person_style == "generic"


def test_owner_cli_can_add_person_but_never_drop_email_or_phone(client, a, settings, monkeypatch):
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(settings.data_dir))
    with pytest.raises(SystemExit):
        demo_control.main(["redactions", "--dataset", "feedback_a", "--types", "EMAIL,PERSON"])
    demo_control.main(["redactions", "--dataset", "feedback_a", "--types", "PERSON,EMAIL,PHONE", "--person-style", "numbered"])
    demo_control.main(["add-named-row", "--dataset", "feedback_a"])
    p = preview(client, a).json()
    last = p["outbound_payload"]["messages"][-1]
    assert last == ("[PERSON_1] asked [PERSON_2] to check the export. [PERSON_2] said [PERSON_1] should "
                    "email [EMAIL]; Dr. [PERSON_3] will follow up with [PERSON_1].")


# ------------------------------------------------------------------- evaluation --
def test_evaluation_set_parses_and_scores_from_an_actual_run():
    assert parse_marked("Ask {Emma} and {Liam O'Brien}.") == ("Ask Emma and Liam O'Brien.", ((4, 8), (13, 25)))
    for bad in ("{Emma", "Emma}", "{}", "{{Emma}}"):
        with pytest.raises(ValueError):
            parse_marked(bad)
    examples = load_examples(EVAL_PATH)
    assert len(examples) >= 60 and any(not e.gold for e in examples)
    res = evaluate(LEX, examples)
    m = res["exact"]
    assert m["tp"] + m["fn"] == sum(len(e.gold) for e in examples)
    assert 0 <= m["precision"] <= 1 and 0 <= m["recall"] <= 1
    # The set deliberately includes names the lexicon cannot know: recall is not perfect.
    assert m["fn"] > 0 and res["by_category"]["unseen_name"]["recall"] == 0
