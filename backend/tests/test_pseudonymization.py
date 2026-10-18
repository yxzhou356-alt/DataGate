"""Feature 5: request-scoped numbered PERSON placeholders ([PERSON_1], [PERSON_2], ...)."""

from __future__ import annotations

import threading
import unicodedata

import pytest

from conftest import PREVIEW_A, login, preview, send
from person_support import StubDetector, require_person, span, write_source

from app import demo_control, transform
from app.detectors import LexiconPersonDetector

LEX = LexiconPersonDetector()
ALL = ("EMAIL", "PHONE", "PERSON")


def _num(messages, detector=LEX):
    return transform.mandatory_redact(messages, ALL, detector, "numbered")


# ---------------------------------------------------------------- numbering rules --
def test_repeated_person_keeps_one_number():
    out, counts = _num(["Emma reported a problem. Emma called again."])
    assert out == ["[PERSON_1] reported a problem. [PERSON_1] called again."] and counts["PERSON"] == 2


def test_two_people_are_numbered_in_order_of_first_appearance():
    out, _ = _num(["Emma contacted Liam. Liam replied to Emma."])
    assert out == ["[PERSON_1] contacted [PERSON_2]. [PERSON_2] replied to [PERSON_1]."]


def test_numbers_are_stable_across_messages_and_case_and_unicode_forms():
    nfd = unicodedata.normalize("NFD", "Zoë")
    out, _ = _num(["Zoë and EMMA", "emma met " + nfd, "Emma"])
    assert out == ["[PERSON_1] and [PERSON_2]", "[PERSON_2] met [PERSON_1]", "[PERSON_2]"]


def test_ann_and_anna_are_different_people():
    assert _num(["Ann spoke with Anna."])[0] == ["[PERSON_1] spoke with [PERSON_2]."]


def test_no_alias_or_substring_merging_is_attempted():
    # Documented limitation: a shortened name is a different entity.
    out, _ = _num(["Emma Lawson called. Emma called back."])
    assert out == ["[PERSON_1] called. [PERSON_2] called back."]


def test_identical_names_share_a_placeholder():
    # Documented limitation: two different people called Emma cannot be told apart.
    assert _num(["Emma from billing and Emma from sales"])[0] == ["[PERSON_1] from billing and [PERSON_1] from sales"]


def test_more_than_nine_people_get_multi_digit_numbers():
    names = ["Emma", "Liam", "Noah", "Olivia", "Sofia", "Omar", "Priya", "Yuki", "Carlos", "Fatima", "Wei"]
    out, counts = _num([" and ".join(names) + ". Wei and Emma again."])
    assert out[0].startswith("[PERSON_1] and [PERSON_2]") and "[PERSON_10] and [PERSON_11]." in out[0]
    assert out[0].endswith("[PERSON_11] and [PERSON_1] again.") and counts["PERSON"] == 13


def test_zero_people_leaves_text_and_counts_zero():
    out, counts = _num(["The export button is greyed out."])
    assert out == ["The export button is greyed out."] and counts == {"EMAIL": 0, "PHONE": 0, "PERSON": 0}


def test_literal_placeholder_in_source_cannot_collide():
    out, _ = _num(["Customer wrote [PERSON_1] in the form; Emma replied."])
    assert out == ["Customer wrote (PERSON_1) in the form; [PERSON_1] replied."]
    assert out[0].count("[PERSON_1]") == 1


def test_email_precedence_in_numbered_mode():
    out, counts = _num(["Emma emma.lawson@example.com"], StubDetector(spans=[span(0, 10)]))
    assert out == ["[PERSON_1] [EMAIL]"] and "emma" not in out[0].lower() and counts["PERSON"] == 1


def test_nested_detector_spans_resolve_to_one_entity():
    out, _ = _num(["Mary Ann Smith called"], StubDetector(spans=[span(0, 14), span(5, 8)]))
    assert out == ["[PERSON_1] called"]


def test_mapping_is_rebuilt_identically_and_never_returned():
    msgs = ["Emma contacted Liam.", "Liam replied to Emma about Priya."]
    first, second = _num(msgs), _num(msgs)
    assert first == second
    assert isinstance(first, tuple) and len(first) == 2  # texts + counts only; no mapping object


def test_reordered_rows_renumber_from_the_new_source_order():
    assert _num(["Liam", "Emma"])[0] == ["[PERSON_1]", "[PERSON_2]"]
    assert _num(["Emma", "Liam"])[0] == ["[PERSON_1]", "[PERSON_2]"]  # same numbers, different people


# --------------------------------------------------------------- end-to-end via API --
MSGS = ["Emma reported that the export fails for Liam.", "Liam asked Priya to check.", "Priya and Emma agreed."]


@pytest.fixture
def numbered(client, a, settings):
    write_source(settings, MSGS)
    require_person(settings, style="numbered")
    return settings


def test_hiding_the_first_mention_does_not_renumber_later_people(client, a, numbered):
    p = preview(client, a).json()
    assert p["outbound_payload"]["messages"] == [
        "[PERSON_1] reported that the export fails for [PERSON_2].",
        "[PERSON_2] asked [PERSON_3] to check.",
        "[PERSON_3] and [PERSON_1] agreed."]
    r = client.patch(f"/api/requests/{p['request_id']}/review", headers=a,
                     json={"expected_review_revision": 1, "hide_message_indices": [0]}).json()
    assert r["outbound_payload"]["messages"][1:] == p["outbound_payload"]["messages"][1:]
    r2 = client.patch(f"/api/requests/{p['request_id']}/review", headers=a,
                      json={"expected_review_revision": 2, "hide_message_indices": []}).json()
    assert r2["outbound_payload"] == p["outbound_payload"] and r2["preview_hash"] == p["preview_hash"]
    assert r2["decision"] == "redact"


def test_preview_review_and_delivered_bytes_match(client, a, numbered, receiver):
    p = preview(client, a).json()
    at = p["outbound_payload"]["messages"][1].index("check")
    r = client.patch(f"/api/requests/{p['request_id']}/review", headers=a, json={
        "expected_review_revision": 1, "hide_message_indices": [2],
        "custom_redactions": [{"message_index": 1, "start": at, "end": at + 5}]}).json()
    assert r["outbound_payload"]["messages"][1] == "[PERSON_2] asked [PERSON_3] to [REDACTED_BY_USER]."
    assert send(client, a, r).status_code == 200
    delivered = receiver.invocations[0][1]
    assert delivered == transform.canonical_bytes(r["outbound_payload"])
    assert transform.hashlib.sha256(delivered).hexdigest() == r["preview_hash"]


def test_requests_do_not_share_a_global_person_table(client, a, b, settings):
    write_source(settings, ["Emma and Liam"], "feedback_a")
    write_source(settings, ["Liam and Emma"], "feedback_b")
    require_person(settings, "numbered", "feedback_a")
    require_person(settings, "numbered", "feedback_b")
    pa = preview(client, a).json()["outbound_payload"]["messages"]
    pb = preview(client, b, {**PREVIEW_A, "dataset_id": "feedback_b"}).json()["outbound_payload"]["messages"]
    assert pa == pb == ["[PERSON_1] and [PERSON_2]"]  # numbers are per request, not per real person


def test_style_change_source_change_and_detector_change_make_approval_stale(app, client, a, numbered, receiver, monkeypatch):
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(numbered.data_dir))
    p = preview(client, a).json()
    demo_control.main(["redactions", "--dataset", "feedback_a", "--types", "EMAIL,PHONE,PERSON", "--person-style", "generic"])
    assert send(client, a, p).json()["error"]["code"] == "POLICY_CHANGED"

    p = preview(client, a).json()
    write_source(numbered, list(reversed(MSGS)))  # reordered rows: different numbering
    assert send(client, a, p).json()["error"]["code"] == "DATASET_CHANGED"

    p = preview(client, a).json()
    app.state.workflow.person_detector = StubDetector(version="other-detector")
    assert send(client, a, p).json()["error"]["code"] == "TRANSFORM_CHANGED"
    assert receiver.invocations == []


def test_transform_version_change_makes_approval_stale(client, a, numbered, receiver, monkeypatch):
    p = preview(client, a).json()
    monkeypatch.setattr(transform, "TRANSFORM_VERSION", "999")
    assert send(client, a, p).json()["error"]["code"] == "TRANSFORM_CHANGED"
    assert receiver.invocations == []


def test_revocation_after_preview_blocks_send(client, a, numbered, receiver, monkeypatch):
    p = preview(client, a).json()
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(numbered.data_dir))
    demo_control.main(["revoke", "--account", "analyst_a", "--dataset", "feedback_a"])
    assert send(client, a, p).json()["error"]["code"] == "ACCESS_REVOKED"
    assert receiver.invocations == []


def test_concurrent_sends_still_invoke_receiver_once(client, a, numbered, receiver):
    p = preview(client, a).json()
    barrier, codes = threading.Barrier(5), []

    def go():
        barrier.wait()
        codes.append(send(client, a, p).status_code)

    threads = [threading.Thread(target=go) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200, 409, 409, 409, 409] and len(receiver.invocations) == 1


@pytest.mark.scenario("SEC-07")
def test_browser_cannot_supply_a_mapping_or_replacement_text(client, a, numbered):
    p = preview(client, a).json()
    for extra in ({"person_mapping": {"Emma": "[PERSON_9]"}}, {"pseudonyms": ["Emma"]},
                  {"messages": ["Emma"]}, {"person_style": "generic"}):
        r = client.patch(f"/api/requests/{p['request_id']}/review", headers=a,
                         json={"expected_review_revision": 1, "hide_message_indices": [], **extra})
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST" and "Emma" not in r.text


@pytest.mark.scenario("SEC-14")
def test_receipts_contain_counts_and_hashes_but_no_names_or_mapping(client, a, numbered):
    p = preview(client, a).json()
    send(client, a, p)
    for text in (client.get(f"/api/requests/{p['request_id']}/receipt", headers=a).text,
                 client.get("/api/receipts", headers=a).text):
        for forbidden in ("Emma", "Liam", "Priya", "PERSON_1", "mapping"):
            assert forbidden not in text
    rec = client.get(f"/api/requests/{p['request_id']}/receipt", headers=a).json()
    assert rec["redaction_counts"]["PERSON"] == 6 and rec["prepared_payload_hash"] == p["preview_hash"]


def test_other_account_still_cannot_see_numbered_previews(client, a, numbered):
    p = preview(client, a).json()
    b = login(client, "analyst_b")
    r = client.patch(f"/api/requests/{p['request_id']}/review", headers=b,
                     json={"expected_review_revision": 1, "hide_message_indices": []})
    assert r.status_code == 403 and "PERSON" not in r.text
