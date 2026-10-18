"""Requester-selected custom redactions: spans of the mandatory-redacted text that are
replaced with [REDACTED_BY_USER] on the backend, in addition to owner rules."""

from __future__ import annotations

import sqlite3

import pytest

from conftest import login, preview, send

from app import transform
from app.storage import Store

CUSTOM = "[REDACTED_BY_USER]"


def _review(client, headers, rid, rev, hide=(), custom=None):
    body = {"expected_review_revision": rev, "hide_message_indices": list(hide)}
    if custom is not None:
        body["custom_redactions"] = custom
    return client.patch(f"/api/requests/{rid}/review", headers=headers, json=body)


def _span(messages, idx, phrase):
    start = messages[idx].index(phrase)
    return {"message_index": idx, "start": start, "end": start + len(phrase)}


@pytest.mark.scenario("SEC-11", "SEC-14")
def test_custom_span_is_redacted_on_backend_and_bound_to_new_revision(client, a, receiver):
    p1 = preview(client, a).json()
    msgs = p1["outbound_payload"]["messages"]
    assert p1["custom_redactions"] == []
    r = _review(client, a, p1["request_id"], 1, custom=[_span(msgs, 1, "charged twice")])
    assert r.status_code == 200, r.text
    p2 = r.json()
    assert p2["review_revision"] == 2 and p2["preview_hash"] != p1["preview_hash"]
    assert p2["outbound_payload"]["messages"][1] == msgs[1].replace("charged twice", CUSTOM)
    assert p2["redaction_counts"] == p1["redaction_counts"]  # owner counts unaffected
    assert p2["custom_redactions"] == [_span(msgs, 1, "charged twice")]

    # Old approval is stale; the new one sends exactly the redacted bytes.
    assert send(client, a, p1).json()["error"]["code"] == "REVIEW_CHANGED"
    assert send(client, a, p2).status_code == 200
    sent = receiver.invocations[0][1].decode()
    assert "charged twice" not in sent and CUSTOM in sent
    rec = client.get(f"/api/requests/{p1['request_id']}/receipt", headers=a).json()
    assert rec["additional_custom_redactions"] == 1
    assert "charged" not in str(rec) and CUSTOM not in str(rec)


def test_multiple_messages_and_overlapping_spans_are_normalised(client, a):
    p = preview(client, a).json()
    msgs = p["outbound_payload"]["messages"]
    s1 = _span(msgs, 1, "charged twice")
    s1b = {**s1, "start": s1["start"] + 3, "end": s1["end"] + 5}   # overlaps s1
    touching = {**s1, "start": s1b["end"], "end": s1b["end"] + 2}  # touches s1b
    s2 = _span(msgs, 2, "last week")
    r = _review(client, a, p["request_id"], 1, custom=[s2, touching, s1b, s1, s1])
    assert r.status_code == 200, r.text
    assert r.json()["custom_redactions"] == [
        {"message_index": 1, "start": s1["start"], "end": touching["end"]}, s2,
    ]
    out = r.json()["outbound_payload"]["messages"]
    assert out[1].count(CUSTOM) == 1 and out[2].count(CUSTOM) == 1


@pytest.mark.scenario("SEC-07")
def test_span_may_cover_but_not_cut_a_mandatory_placeholder(client, a):
    p = preview(client, a).json()
    msgs = p["outbound_payload"]["messages"]
    at = msgs[0].index("[EMAIL]")
    bad = {"message_index": 0, "start": at + 2, "end": at + 9}
    r = _review(client, a, p["request_id"], 1, custom=[bad])
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REVIEW"

    ok = _span(msgs, 0, "contact [EMAIL]")
    r = _review(client, a, p["request_id"], 1, custom=[ok])
    assert r.status_code == 200
    assert r.json()["outbound_payload"]["messages"][0].endswith(CUSTOM + ".")
    assert r.json()["redaction_counts"]["EMAIL"] == p["redaction_counts"]["EMAIL"]


def test_invalid_spans_are_rejected_and_leave_review_unchanged(client, a):
    p = preview(client, a).json()
    rid = p["request_id"]
    n = len(p["outbound_payload"]["messages"][1])
    for bad in (
        {"message_index": len(p["outbound_payload"]["messages"]), "start": 0, "end": 1},
        {"message_index": -1, "start": 0, "end": 1},
        {"message_index": 1, "start": -1, "end": 2},
        {"message_index": 1, "start": 3, "end": 3},
        {"message_index": 1, "start": 4, "end": 2},
        {"message_index": 1, "start": 0, "end": n + 1},
    ):
        r = _review(client, a, rid, 1, custom=[bad])
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REVIEW", bad
    for bad in (
        {"message_index": 1, "start": 0, "end": 2, "text": "x"},
        {"message_index": 1, "start": "0", "end": 2},
        {"message_index": True, "start": 0, "end": 2},
        {"message_index": 1, "start": 0},
    ):
        r = _review(client, a, rid, 1, custom=[bad])
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST", bad
    too_many = [{"message_index": 1, "start": i * 2, "end": i * 2 + 1} for i in range(transform.MAX_CUSTOM_PER_MESSAGE + 1)]
    r = _review(client, a, rid, 1, custom=too_many)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REVIEW"
    assert _review(client, a, rid, 1).json()["review_revision"] == 2  # refused edits left revision 1 in place


def test_omitted_keeps_spans_empty_list_clears_and_hide_keeps_them(client, a):
    p = preview(client, a).json()
    rid, msgs = p["request_id"], p["outbound_payload"]["messages"]
    span = _span(msgs, 1, "refund")
    p2 = _review(client, a, rid, 1, custom=[span]).json()
    p3 = _review(client, a, rid, 2, hide=[1]).json()  # custom omitted: kept
    assert p3["custom_redactions"] == [span]
    assert p3["outbound_payload"]["messages"][1] == "[HIDDEN_BY_USER]"
    p4 = _review(client, a, rid, 3, hide=[]).json()   # restored with the custom span
    assert p4["outbound_payload"] == p2["outbound_payload"] and p4["preview_hash"] == p2["preview_hash"]
    p5 = _review(client, a, rid, 4, custom=[]).json()
    assert p5["custom_redactions"] == [] and p5["preview_hash"] == p["preview_hash"]


def test_hidden_message_spans_are_not_counted_in_receipt(client, a):
    p = preview(client, a).json()
    rid, msgs = p["request_id"], p["outbound_payload"]["messages"]
    p2 = _review(client, a, rid, 1, hide=[2], custom=[_span(msgs, 1, "refund"), _span(msgs, 2, "last week")]).json()
    assert send(client, a, p2).status_code == 200
    assert client.get(f"/api/requests/{rid}/receipt", headers=a).json()["additional_custom_redactions"] == 1


def test_fully_redacting_every_remaining_message_is_no_content(client, a):
    p = preview(client, a).json()
    rid, msgs = p["request_id"], p["outbound_payload"]["messages"]
    last_index = len(msgs) - 1
    whole = [{"message_index": last_index, "start": 0, "end": len(msgs[last_index])}]
    r = _review(client, a, rid, 1, hide=list(range(last_index)), custom=whole)
    assert r.status_code == 422 and r.json()["error"]["code"] == "NO_CONTENT_TO_SEND"
    # A fully redacted message is fine while another message still has content.
    r = _review(client, a, rid, 1, hide=list(range(last_index - 1)), custom=whole)
    assert r.status_code == 200 and r.json()["review_revision"] == 2


@pytest.mark.scenario("SEC-03")
def test_other_account_cannot_add_custom_redactions(client, a):
    p = preview(client, a).json()
    b = login(client, "analyst_b")
    r = _review(client, b, p["request_id"], 1, custom=[{"message_index": 1, "start": 0, "end": 3}])
    assert r.status_code == 403 and r.json()["error"]["code"] == "REQUEST_ACCESS_DENIED"


def test_offsets_are_code_points_and_unicode_safe():
    base = ["Ça 😕 crashes à [EMAIL] 谢谢"]
    start = base[0].index("crashes")
    spans = transform.normalize_custom([(0, start, start + 7)], base, ("EMAIL", "PHONE"))
    assert transform.apply_custom(base[0], spans[0]) == f"Ça 😕 {CUSTOM} à [EMAIL] 谢谢"
    assert transform.has_content([CUSTOM + " " + "[HIDDEN_BY_USER]"]) is False
    assert transform.has_content(["[EMAIL]"]) is True


def test_existing_runtime_db_gains_custom_redactions_column(tmp_path):
    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE requests (request_id TEXT PRIMARY KEY, hidden_indices TEXT NOT NULL DEFAULT '[]')")
        conn.execute("INSERT INTO requests (request_id) VALUES ('req_old')")
    Store(db)
    Store(db)  # idempotent
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT custom_redactions FROM requests").fetchone()[0] == "[]"
