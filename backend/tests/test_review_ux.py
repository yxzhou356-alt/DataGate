"""Review behaviour the interactive review cards rely on: hide/restore round-trips,
index normalisation, and no raw identifiers in any review response."""

from __future__ import annotations

import csv
from pathlib import Path

from conftest import preview

from app import transform

FIXTURE_A = Path(__file__).resolve().parent.parent / "fixtures" / "feedback_a.csv"


def _review(client, headers, rid, rev, hide):
    return client.patch(f"/api/requests/{rid}/review", headers=headers,
                        json={"expected_review_revision": rev, "hide_message_indices": hide})


def _raw_identifiers() -> list[str]:
    with FIXTURE_A.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r[c] for r in rows for c in ("customer_name", "email", "phone", "account_value") if r[c]]


def test_hide_then_restore_returns_server_redacted_version(client, a):
    p1 = preview(client, a).json()
    rid = p1["request_id"]
    original = p1["outbound_payload"]["messages"][0]
    assert "[EMAIL]" in original

    p2 = _review(client, a, rid, 1, [0]).json()
    assert p2["outbound_payload"]["messages"][0] == "[HIDDEN_BY_USER]"

    p3 = _review(client, a, rid, 2, []).json()
    assert p3["review_revision"] == 3 and p3["hidden_message_indices"] == []
    # Restoring yields exactly the mandatory-redacted text and the same canonical payload.
    assert p3["outbound_payload"] == p1["outbound_payload"]
    assert p3["preview_hash"] == p1["preview_hash"]
    assert p3["redaction_counts"] == p1["redaction_counts"]


def test_duplicate_and_unsorted_indices_are_normalised(client, a):
    p = preview(client, a).json()
    r = _review(client, a, p["request_id"], 1, [4, 1, 4, 1])
    assert r.status_code == 200
    assert r.json()["hidden_message_indices"] == [1, 4]
    assert r.json()["review_revision"] == 2


def test_review_responses_and_errors_never_contain_raw_identifiers(client, a):
    raw = _raw_identifiers()
    p = preview(client, a)
    rid = p.json()["request_id"]
    responses = [
        p,
        _review(client, a, rid, 1, [2]),
        _review(client, a, rid, 2, []),
        _review(client, a, rid, 3, list(range(10))),  # NO_CONTENT_TO_SEND
        _review(client, a, rid, 1, [0]),              # stale revision
    ]
    assert responses[3].json()["error"]["code"] == "NO_CONTENT_TO_SEND"
    assert responses[4].json()["error"]["code"] == "REVIEW_CHANGED"
    for r in responses:
        for value in raw:
            assert value not in r.text


def test_redaction_of_multiple_identifiers_html_and_unicode():
    text = "<b>Écrivez</b> à a.b@example.com ou c@example.org — 213-555-0142, (310) 555 0199 ✓"
    cleaned, counts = transform.redact(text, ("EMAIL", "PHONE"))
    assert cleaned == "<b>Écrivez</b> à [EMAIL] ou [EMAIL] — [PHONE], [PHONE] ✓"
    assert counts == {"EMAIL": 2, "PHONE": 2}
