"""Allowed path, auth, access isolation and blocked policies."""

from __future__ import annotations

import hashlib
import json
import sqlite3

from conftest import PREVIEW_A, login, preview, send

SENSITIVE_SOURCE_VALUES = [
    "Emma Lawson", "emma.lawson@example.com", "(213) 555-0142", "424-555-0110",
    "mason.backup@example.net", "(562) 555-0157", "58000", "MA-1001", "enterprise",
]


def test_allowed_request_reaches_receiver_exactly_once_with_previewed_bytes(client, a, receiver):
    p = preview(client, a).json()
    assert p["status"] == "ready" and p["decision"] == "redact"
    assert p["reason_codes"] == ["REDACTION_REQUIRED"]
    assert p["dropped_fields"] == ["ticket_id", "customer_name", "email", "phone", "plan_tier", "account_value", "product_area"]
    assert p["redaction_counts"] == {"EMAIL": 2, "PHONE": 2}
    assert p["receiver_attempts"] == 0 and receiver.invocations == []

    payload = p["outbound_payload"]
    assert set(payload) == {"schema_version", "purpose", "instruction", "messages"}
    assert len(payload["messages"]) == 10
    assert payload["messages"][0] == "The reset link expired. Please contact [EMAIL]."
    assert payload["messages"][9] == "The upgrade button does nothing; text me at [PHONE]."
    # Unicode survives untouched.
    assert "La app se cierra al abrir el panel — crashes" in payload["messages"][4]

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert p["preview_hash"] == hashlib.sha256(canonical).hexdigest()

    r = send(client, a, p)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "sent" and body["receiver_attempts"] == 1
    assert body["receiver_result"] == {
        "mode": "local_demo", "acknowledged": True, "message_count": 10,
        "note": "Local test receiver; no external AI model was called.",
    }

    assert len(receiver.invocations) == 1
    rid, sent_bytes = receiver.invocations[0]
    assert rid == p["request_id"]
    assert sent_bytes == canonical
    text = sent_bytes.decode()
    for value in SENSITIVE_SOURCE_VALUES:
        assert value not in text


def test_clean_dataset_is_allow_but_still_needs_approval(client, a, settings, receiver):
    path = settings.sources_dir / "feedback_a.csv"
    path.write_text(
        "ticket_id,customer_name,email,phone,plan_tier,account_value,product_area,message\n"
        "T1,X,x@example.com,213-555-0100,pro,1,a,Nothing sensitive here.\n",
        encoding="utf-8",
    )
    p = preview(client, a).json()
    assert p["decision"] == "allow" and p["status"] == "ready" and p["reason_codes"] == []
    assert receiver.invocations == []


def test_dataset_listing_is_scoped_to_account(client, a, b):
    la = client.get("/api/datasets", headers=a).json()["datasets"]
    lb = client.get("/api/datasets", headers=b).json()["datasets"]
    assert [d["dataset_id"] for d in la] == ["feedback_a"]
    assert [d["dataset_id"] for d in lb] == ["feedback_b"]
    assert "RiverCo" not in json.dumps(la) and "MapleCo" not in json.dumps(lb)
    assert la[0]["passport"]["outbound_fields"] == ["message"]


def test_auth_required_and_invalid_session(client):
    r = client.get("/api/datasets")
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_REQUIRED"
    r = client.get("/api/datasets", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_SESSION"
    assert "not-a-real-token" not in r.text
    r = client.post("/api/demo/session", json={"account_id": "admin"})
    assert r.status_code == 422


def test_identity_comes_from_token_not_body(client, b):
    # analyst_b cannot claim to be analyst_a through body fields.
    r = client.post("/api/requests/preview", headers=b, json={**PREVIEW_A, "user_id": "analyst_a"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
    r = client.post("/api/requests/preview", headers=b, json={**PREVIEW_A, "role": "admin"})
    assert r.status_code == 422


def test_cross_account_dataset_draft_review_receipt_are_denied(client, a, b, receiver):
    r = preview(client, b)  # b asks for feedback_a
    assert r.status_code == 403 and r.json()["error"]["code"] == "DATASET_ACCESS_DENIED"
    assert "outbound_payload" not in r.text

    p = preview(client, a).json()
    rid = p["request_id"]
    r = client.patch(f"/api/requests/{rid}/review", headers=b, json={"expected_review_revision": 1, "hide_message_indices": [0]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "REQUEST_ACCESS_DENIED"
    r = send(client, b, p)
    assert r.status_code == 403 and r.json()["error"]["code"] == "REQUEST_ACCESS_DENIED"
    assert receiver.invocations == []

    assert send(client, a, p).status_code == 200
    r = client.get(f"/api/requests/{rid}/receipt", headers=b)
    assert r.status_code == 403 and r.json()["error"]["code"] == "REQUEST_ACCESS_DENIED"
    assert len(receiver.invocations) == 1


def test_unknown_dataset_and_request(client, a):
    r = preview(client, a, {**PREVIEW_A, "dataset_id": "feedback_z"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "DATASET_NOT_FOUND"
    r = client.get("/api/requests/req_nope/receipt", headers=a)
    assert r.status_code == 404 and r.json()["error"]["code"] == "REQUEST_NOT_FOUND"


def _assert_blocked(client, headers, body, code, receiver):
    r = preview(client, headers, body)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["decision"] == "block" and p["status"] == "blocked"
    assert code in p["reason_codes"]
    assert p["outbound_payload"] is None and p["preview_hash"] is None
    assert p["receiver_attempts"] == 0 and p["receipt_available"] is True
    rec = client.get(f"/api/requests/{p['request_id']}/receipt", headers=headers).json()
    assert rec["decision"] == "block" and rec["prepared_payload_hash"] is None
    assert rec["confirmed_sent_payload_hash"] is None and rec["receiver_attempts"] == 0
    r = send(client, headers, {**p, "review_revision": 1, "preview_hash": "0" * 64})
    assert r.status_code == 409 and r.json()["error"]["code"] == "REQUEST_NOT_READY"
    assert receiver.invocations == []


def test_model_training_purpose_is_blocked_with_zero_calls(client, a, receiver):
    _assert_blocked(client, a, {**PREVIEW_A, "purpose": "model_training"}, "PURPOSE_NOT_ALLOWED", receiver)


def test_unapproved_destination_is_blocked_with_zero_calls(client, a, receiver):
    _assert_blocked(client, a, {**PREVIEW_A, "destination": "public_chatbot"}, "DESTINATION_NOT_ALLOWED", receiver)


def test_destination_url_is_rejected(client, a, receiver):
    r = preview(client, a, {**PREVIEW_A, "destination": "https://evil.example/collect"})
    assert r.status_code == 422 and "evil.example" not in r.text
    assert receiver.invocations == []


def test_sharing_none_blocks_even_redacted_data(client, a, settings, receiver):
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute("UPDATE policies SET sharing_mode='none', policy_version=policy_version+1 WHERE dataset_id='feedback_a'")
    _assert_blocked(client, a, PREVIEW_A, "SHARING_PROHIBITED", receiver)


def test_invalid_source_returns_422_without_echoing_values(client, a, settings, receiver):
    path = settings.sources_dir / "feedback_a.csv"
    path.write_text(
        "ticket_id,customer_name,email,phone,plan_tier,account_value,product_area,message\n"
        "T1,Secret Person,secret@example.com,213-555-0100,pro,1,a,\n",
        encoding="utf-8",
    )
    r = preview(client, a)
    assert r.status_code == 422 and r.json()["error"]["code"] == "DATASET_INVALID"
    assert "Secret Person" not in r.text and "secret@example.com" not in r.text
    assert receiver.invocations == []


def test_unexpected_columns_are_never_forwarded(client, a, settings, receiver):
    path = settings.sources_dir / "feedback_a.csv"
    path.write_text(
        "ticket_id,ssn,message\n"
        'T1,123-45-6789,"Quoted, with comma — and ünïcode"\n',
        encoding="utf-8",
    )
    p = preview(client, a).json()
    assert p["dropped_fields"] == ["ticket_id", "ssn"]
    assert p["outbound_payload"]["messages"] == ["Quoted, with comma — and ünïcode"]
    send(client, a, p)
    assert b"123-45-6789" not in receiver.invocations[0][1]
