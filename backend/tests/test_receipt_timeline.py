"""Creator-only receipt timeline (GET /api/receipts): authorization, metadata-only
content, filters, deterministic ordering, pagination and older rows."""

from __future__ import annotations

import secrets
import sqlite3

import pytest

from conftest import PREVIEW_A, failing_client, login, preview, send

from app import demo_control

URL = "/api/receipts"


def _list(client, headers, **params):
    return client.get(URL, headers=headers, params=params)


def _ids(resp):
    return [r["request_id"] for r in resp.json()["receipts"]]


def _seed_rows(app, account_id, n, ts="2026-10-18T08:00:00.000000Z", status="sent"):
    """Metadata-only outcome rows written directly, for ordering/size tests."""
    ids = []
    for _ in range(n):
        rid = "req_" + secrets.token_hex(12)
        app.state.store.insert_request({
            "request_id": rid, "account_id": account_id, "dataset_id": "feedback_a", "purpose": "feedback_summary",
            "destination": "demo_receiver", "status": status, "decision": "redact", "reason_codes": ["REDACTION_REQUIRED"],
            "receiver_mode": "local_demo", "receiver_attempts": 1, "created_at": ts, "occurred_at": ts,
        })
        ids.append(rid)
    return ids


# ------------------------------------------------------------------ authorization --
def test_requires_a_valid_session(client):
    assert client.get(URL).json()["error"]["code"] == "AUTH_REQUIRED"
    r = client.get(URL, headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_SESSION"


def test_empty_history(client, a):
    r = _list(client, a)
    assert r.status_code == 200 and r.json() == {"receipts": [], "next_cursor": None, "limit": 20}


@pytest.mark.scenario("SEC-03")
def test_other_account_cannot_list_or_infer_receipts(client, a, b, receiver):
    p = preview(client, a).json()
    send(client, a, p)
    preview(client, a, {**PREVIEW_A, "purpose": "model_training"})
    assert len(_ids(_list(client, a))) == 2

    assert _list(client, b).json()["receipts"] == []
    # Naming the other account's dataset gives the same empty page as an unknown dataset.
    assert _list(client, b, dataset_id="feedback_a").json() == _list(client, b, dataset_id="no_such_dataset").json()
    # Account selectors are not accepted at all.
    for params in ({"account_id": "analyst_a"}, {"user_id": "analyst_a"}, {"owner": "analyst_a"}):
        r = _list(client, b, **params)
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
    # A cursor built from the other account's newest item reveals nothing either.
    page = _list(client, a, limit=1).json()
    assert _list(client, b, cursor=page["next_cursor"]).json()["receipts"] == []
    assert p["request_id"] not in _list(client, b).text


# ---------------------------------------------------------------- outcome states --
def test_sent_blocked_without_preview_and_failed_outcomes(client, a, receiver, settings):
    p = preview(client, a).json()
    send(client, a, p)
    blocked = preview(client, a, {**PREVIEW_A, "destination": "public_chatbot"}).json()
    fclient, _ = failing_client(settings)
    fa = login(fclient, "analyst_a")
    fp = preview(fclient, fa).json()
    send(fclient, fa, fp)

    items = {r["request_id"]: r for r in _list(fclient, fa).json()["receipts"]}
    sent, blk, failed = items[p["request_id"]], items[blocked["request_id"]], items[fp["request_id"]]
    assert sent["status"] == "sent" and sent["receiver_attempts"] == 1
    assert sent["confirmed_sent_payload_hash"] == sent["prepared_payload_hash"] == p["preview_hash"]
    assert blk["status"] == "blocked" and blk["receiver_attempts"] == 0
    assert blk["prepared_payload_hash"] is None and blk["review_revision"] is None
    assert blk["preview_policy_version"] is None and blk["reason_codes"] == ["DESTINATION_NOT_ALLOWED"]
    assert failed["status"] == "send_failed" and failed["receiver_attempts"] == 1
    assert failed["confirmed_sent_payload_hash"] is None and failed["prepared_payload_hash"] == fp["preview_hash"]


def test_items_match_the_single_receipt_endpoint_exactly(client, a):
    p = preview(client, a).json()
    send(client, a, p)
    preview(client, a, {**PREVIEW_A, "purpose": "model_training"})
    for item in _list(client, a).json()["receipts"]:
        single = client.get(f"/api/requests/{item['request_id']}/receipt", headers=a).json()
        assert {k: v for k, v in item.items() if k != "recorded_at"} == single


def test_drafts_are_not_listed(client, a):
    preview(client, a)  # ready, never sent
    assert _list(client, a).json()["receipts"] == []


def test_revoked_creator_keeps_history_but_cannot_preview(client, a, receiver, settings, monkeypatch):
    p = preview(client, a).json()
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(settings.data_dir))
    demo_control.main(["revoke", "--account", "analyst_a", "--dataset", "feedback_a"])
    assert send(client, a, p).json()["error"]["code"] == "ACCESS_REVOKED"

    [item] = _list(client, a).json()["receipts"]
    assert item["status"] == "blocked" and item["reason_codes"] == ["ACCESS_REVOKED"]
    assert item["receiver_attempts"] == 0 and item["prepared_payload_hash"] == p["preview_hash"]
    assert item["confirmed_sent_payload_hash"] is None
    assert preview(client, a).json()["error"]["code"] == "DATASET_ACCESS_DENIED"
    assert receiver.invocations == []


def test_stale_outcomes_are_listed_but_single_receipt_behaviour_is_unchanged(client, a, settings, monkeypatch):
    p = preview(client, a).json()
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(settings.data_dir))
    demo_control.main(["bump-policy", "--dataset", "feedback_a"])
    assert send(client, a, p).json()["error"]["code"] == "POLICY_CHANGED"
    [item] = _list(client, a, status="stale").json()["receipts"]
    assert item["reason_codes"] == ["POLICY_CHANGED"] and item["occurred_at"] and item["receiver_attempts"] == 0
    r = client.get(f"/api/requests/{p['request_id']}/receipt", headers=a)
    assert r.status_code == 409 and r.json()["error"]["code"] == "RECEIPT_NOT_READY"


# ---------------------------------------------------------------------- content --
@pytest.mark.scenario("SEC-14")
def test_list_contains_metadata_only(client, a, settings):
    p = preview(client, a).json()
    client.patch(f"/api/requests/{p['request_id']}/review", headers=a, json={
        "expected_review_revision": 1, "hide_message_indices": [2],
        "custom_redactions": [{"message_index": 1, "start": 6, "end": 19}]})
    p2 = client.patch(f"/api/requests/{p['request_id']}/review", headers=a,
                      json={"expected_review_revision": 2, "hide_message_indices": [2]}).json()
    send(client, a, p2)
    preview(client, a, {**PREVIEW_A, "purpose": "model_training"})
    text = _list(client, a).text
    for forbidden in ("reset link", "charged twice", "[EMAIL]", "[REDACTED_BY_USER]", "[HIDDEN_BY_USER]", "Emma",
                      "@example", "555-01", "Summarize", '"messages"', "outbound_payload", '"custom_redactions"',
                      '"hidden_indices"', ".csv", str(settings.data_dir), "/sources", a["Authorization"].split()[1], "Bearer"):
        assert forbidden not in text, forbidden
    item = _list(client, a, status="sent").json()["receipts"][0]
    assert item["additional_hidden_messages"] == 1 and item["additional_custom_redactions"] == 1


# ------------------------------------------------------------- filters + validation --
def test_filters_narrow_own_records(client, a):
    p = preview(client, a).json()
    send(client, a, p)
    preview(client, a, {**PREVIEW_A, "purpose": "model_training"})
    assert _ids(_list(client, a, status="sent")) == [p["request_id"]]
    assert len(_ids(_list(client, a, decision="block"))) == 1
    assert len(_ids(_list(client, a, dataset_id="feedback_a"))) == 2
    assert _list(client, a, since="2999-01-01T00:00:00Z").json()["receipts"] == []
    assert len(_ids(_list(client, a, since="2000-01-01T00:00:00+00:00", until="2999-01-01T00:00:00Z"))) == 2


@pytest.mark.parametrize("params", [
    {"status": "ready"}, {"status": "sending"}, {"status": "SENT"}, {"decision": "maybe"},
    {"dataset_id": "../etc/passwd"}, {"dataset_id": "a" * 65}, {"since": "yesterday"},
    {"since": "2026-10-18T08:00:00"},  # no timezone
    {"since": "2026-10-19T00:00:00Z", "until": "2026-10-18T00:00:00Z"},
    {"limit": "0"}, {"limit": "101"}, {"limit": "-1"}, {"limit": "ten"},
    {"cursor": "not a cursor"}, {"cursor": "W10"}, {"cursor": "eyJhIjoxfQ"},
])
def test_invalid_filters_are_rejected_without_echo(client, a, params):
    r = _list(client, a, **params)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
    for value in params.values():
        if len(value) > 3:
            assert value not in r.text


def test_repeated_parameters_are_rejected(client, a):
    r = client.get(URL + "?status=sent&status=blocked", headers=a)
    assert r.status_code == 422


# --------------------------------------------------------- ordering + pagination --
def test_identical_timestamps_have_a_stable_order_and_no_duplicates(app, client, a):
    ids = _seed_rows(app, "analyst_a", 5)
    expected = sorted(ids, reverse=True)
    assert _ids(_list(client, a)) == expected
    seen, cursor = [], None
    while True:
        page = _list(client, a, limit=2, **({"cursor": cursor} if cursor else {})).json()
        seen += [r["request_id"] for r in page["receipts"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == expected


def test_pagination_boundary_has_no_empty_next_page(app, client, a):
    _seed_rows(app, "analyst_a", 2)
    assert _list(client, a, limit=2).json()["next_cursor"] is None
    first = _list(client, a, limit=1).json()
    assert first["next_cursor"] is not None
    second = _list(client, a, limit=1, cursor=first["next_cursor"]).json()
    assert len(second["receipts"]) == 1 and second["next_cursor"] is None


def test_large_history_pages_in_bounded_chunks(app, client, a):
    for minute in range(25):
        _seed_rows(app, "analyst_a", 10, ts=f"2026-10-18T08:{minute:02d}:00.000000Z")
    _seed_rows(app, "analyst_b", 30)
    assert _list(client, a, limit=500).status_code == 422
    seen, cursor, pages = [], None, 0
    while True:
        page = _list(client, a, limit=100, **({"cursor": cursor} if cursor else {})).json()
        pages += 1
        assert len(page["receipts"]) <= 100
        seen += [(r["recorded_at"], r["request_id"]) for r in page["receipts"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert pages == 3 and len(seen) == 250 and len(set(seen)) == 250
    assert seen == sorted(seen, reverse=True)


def test_older_rows_without_occurred_at_or_new_columns_are_listed(app, client, a, settings):
    p = preview(client, a).json()
    send(client, a, p)
    with sqlite3.connect(settings.db_path) as conn:  # an older stale row: no occurred_at, defaults elsewhere
        conn.execute(
            "INSERT INTO requests (request_id, account_id, dataset_id, purpose, destination, status, decision, "
            "reason_codes, receiver_mode, created_at) VALUES (?, 'analyst_a', 'feedback_a', 'feedback_summary', "
            "'demo_receiver', 'stale', 'redact', '[\"DATASET_CHANGED\"]', 'local_demo', '2026-01-01T00:00:00.000000Z')",
            ("req_" + "0" * 24,))
    items = _list(client, a).json()["receipts"]
    assert [i["status"] for i in items] == ["sent", "stale"]
    old = items[1]
    assert old["occurred_at"] is None and old["recorded_at"] == "2026-01-01T00:00:00.000000Z"
    assert old["additional_custom_redactions"] == 0 and old["redaction_counts"] == {}
