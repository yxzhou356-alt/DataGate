"""Tampering, revocation, stale approvals, duplicate/concurrent Send, failures, receipts."""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest

from conftest import failing_client, login, preview, send

from app import demo_control


# ---------------------------------------------------------------- tampering --
@pytest.mark.scenario("SEC-07")
def test_mandatory_redaction_cannot_be_undone_by_body_tampering(client, a, receiver):
    p = preview(client, a).json()
    rid = p["request_id"]
    tamper_reviews = [
        {"expected_review_revision": 1, "hide_message_indices": [], "unredact": True},
        {"expected_review_revision": 1, "hide_message_indices": [], "allow_email": True},
        {"expected_review_revision": 1, "hide_message_indices": [], "include_account_value": True},
        {"expected_review_revision": 1, "hide_message_indices": [], "messages": ["emma.lawson@example.com"]},
    ]
    for body in tamper_reviews:
        r = client.patch(f"/api/requests/{rid}/review", headers=a, json=body)
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
        assert "emma.lawson@example.com" not in r.text

    tamper_sends = [
        {"outbound_payload": {"messages": ["Contact emma.lawson@example.com"]}},
        {"messages": ["Contact emma.lawson@example.com"]},
        {"destination": "https://evil.example"},
    ]
    for extra in tamper_sends:
        r = send(client, a, p, **extra)
        assert r.status_code == 422
        assert "emma.lawson@example.com" not in r.text
    assert send(client, a, p, approve=False).status_code == 422
    assert send(client, a, p, approve="true").status_code == 422
    assert receiver.invocations == []

    assert send(client, a, p).status_code == 200
    sent = receiver.invocations[0][1].decode()
    assert "[EMAIL]" in sent and "@example" not in sent and "555-01" not in sent


# --------------------------------------------------------------- revocation --
@pytest.mark.scenario("SEC-08")
def test_revocation_after_preview_blocks_send_with_zero_calls(client, a, receiver, settings, monkeypatch):
    p = preview(client, a).json()
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(settings.data_dir))
    demo_control.main(["revoke", "--account", "analyst_a", "--dataset", "feedback_a"])

    r = send(client, a, p)
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCESS_REVOKED"
    assert receiver.invocations == []

    # Creator can still read the metadata receipt, which reflects the denial.
    rec = client.get(f"/api/requests/{p['request_id']}/receipt", headers=a).json()
    assert rec["decision"] == "block" and rec["status"] == "blocked"
    assert rec["reason_codes"] == ["ACCESS_REVOKED"]
    assert rec["policy_version"] == 2 and rec["preview_policy_version"] == 1
    assert rec["prepared_payload_hash"] == p["preview_hash"]
    assert rec["confirmed_sent_payload_hash"] is None and rec["receiver_attempts"] == 0

    # But cannot regenerate a preview or list the dataset anymore.
    assert preview(client, a).status_code == 403
    assert client.get("/api/datasets", headers=a).json()["datasets"] == []
    # Re-sending is not possible either.
    assert send(client, a, p).json()["error"]["code"] == "REQUEST_NOT_READY"

    demo_control.main(["grant", "--account", "analyst_a", "--dataset", "feedback_a"])
    p2 = preview(client, a).json()
    assert send(client, a, p2).status_code == 200
    assert len(receiver.invocations) == 1 and receiver.invocations[0][0] == p2["request_id"]


@pytest.mark.scenario("SEC-08")
def test_revocation_also_blocks_review(client, a, settings, monkeypatch):
    p = preview(client, a).json()
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(settings.data_dir))
    demo_control.main(["revoke", "--account", "analyst_a", "--dataset", "feedback_a"])
    r = client.patch(f"/api/requests/{p['request_id']}/review", headers=a,
                     json={"expected_review_revision": 1, "hide_message_indices": [1]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ACCESS_REVOKED"


@pytest.mark.scenario("SEC-06")
def test_policy_turning_to_no_sharing_after_preview_blocks_send(client, a, settings, receiver, monkeypatch):
    p = preview(client, a).json()
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(settings.data_dir))
    demo_control.main(["sharing", "--dataset", "feedback_a", "--mode", "none"])
    r = send(client, a, p)
    assert r.status_code == 403 and r.json()["error"]["code"] == "SHARING_PROHIBITED"
    rec = client.get(f"/api/requests/{p['request_id']}/receipt", headers=a).json()
    assert rec["decision"] == "block" and rec["reason_codes"] == ["SHARING_PROHIBITED"]
    assert receiver.invocations == []


# ---------------------------------------------------------- stale approvals --
@pytest.mark.scenario("SEC-09")
def test_changed_source_invalidates_approval(client, a, settings, receiver, monkeypatch):
    p = preview(client, a).json()
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(settings.data_dir))
    demo_control.main(["edit-source", "--dataset", "feedback_a"])
    r = send(client, a, p)
    assert r.status_code == 409 and r.json()["error"]["code"] == "DATASET_CHANGED"
    assert send(client, a, p).json()["error"]["code"] == "REQUEST_NOT_READY"  # stored stale
    assert receiver.invocations == []
    p2 = preview(client, a).json()
    assert p2["dataset_revision"] == 2 and len(p2["outbound_payload"]["messages"]) == 11


@pytest.mark.scenario("SEC-09")
def test_out_of_band_source_edit_without_revision_bump_is_detected(client, a, settings, receiver):
    p = preview(client, a).json()
    path = settings.sources_dir / "feedback_a.csv"
    path.write_bytes(path.read_bytes().replace(b"reset link expired", b"reset link broke"))
    r = send(client, a, p)
    assert r.status_code == 409 and r.json()["error"]["code"] == "DATASET_CHANGED"
    assert receiver.invocations == []


@pytest.mark.scenario("SEC-10")
def test_changed_policy_version_invalidates_approval(client, a, settings, receiver, monkeypatch):
    p = preview(client, a).json()
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(settings.data_dir))
    demo_control.main(["bump-policy", "--dataset", "feedback_a"])
    r = send(client, a, p)
    assert r.status_code == 409 and r.json()["error"]["code"] == "POLICY_CHANGED"
    assert receiver.invocations == []


@pytest.mark.scenario("SEC-10")
def test_out_of_band_policy_edit_detected_by_fingerprint(client, a, settings, receiver):
    p = preview(client, a).json()
    with sqlite3.connect(settings.db_path) as conn:  # no version bump
        conn.execute("UPDATE policies SET required_redactions='[\"EMAIL\"]' WHERE dataset_id='feedback_a'")
    r = send(client, a, p)
    assert r.status_code == 409 and r.json()["error"]["code"] == "POLICY_CHANGED"
    assert receiver.invocations == []


# ------------------------------------------------------------------ review --
@pytest.mark.scenario("SEC-11")
def test_review_hides_messages_and_invalidates_previous_approval(client, a, receiver):
    p1 = preview(client, a).json()
    rid = p1["request_id"]
    r = client.patch(f"/api/requests/{rid}/review", headers=a, json={"expected_review_revision": 1, "hide_message_indices": [3, 0, 3]})
    assert r.status_code == 200, r.text
    p2 = r.json()
    assert p2["review_revision"] == 2 and p2["hidden_message_indices"] == [0, 3]
    assert p2["outbound_payload"]["messages"][0] == "[HIDDEN_BY_USER]"
    assert p2["outbound_payload"]["messages"][3] == "[HIDDEN_BY_USER]"
    assert p2["preview_hash"] != p1["preview_hash"]
    assert p2["redaction_counts"] == p1["redaction_counts"]  # mandatory rule unaffected

    # Old approvals no longer work, and nothing is sent.
    assert send(client, a, p1).json()["error"]["code"] == "REVIEW_CHANGED"
    assert send(client, a, {**p2, "preview_hash": p1["preview_hash"]}).json()["error"]["code"] == "PREVIEW_CHANGED"
    r = client.patch(f"/api/requests/{rid}/review", headers=a, json={"expected_review_revision": 1, "hide_message_indices": []})
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVIEW_CHANGED"
    assert receiver.invocations == []

    assert send(client, a, p2).status_code == 200
    rec = client.get(f"/api/requests/{rid}/receipt", headers=a).json()
    assert rec["additional_hidden_messages"] == 2 and rec["review_revision"] == 2
    assert receiver.invocations[0][1].decode().count("[HIDDEN_BY_USER]") == 2


def test_review_validation(client, a):
    p = preview(client, a).json()
    url = f"/api/requests/{p['request_id']}/review"
    for bad in ([10], [-1]):
        r = client.patch(url, headers=a, json={"expected_review_revision": 1, "hide_message_indices": bad})
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REVIEW"
    for bad in ([True], ["1"], [1.0]):
        r = client.patch(url, headers=a, json={"expected_review_revision": 1, "hide_message_indices": bad})
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
    r = client.patch(url, headers=a, json={"expected_review_revision": 1, "hide_message_indices": list(range(10))})
    assert r.status_code == 422 and r.json()["error"]["code"] == "NO_CONTENT_TO_SEND"
    # Review left unchanged by the refused edit.
    r = client.patch(url, headers=a, json={"expected_review_revision": 1, "hide_message_indices": [2]})
    assert r.status_code == 200 and r.json()["review_revision"] == 2


# ------------------------------------------------------ duplicate/concurrent --
@pytest.mark.scenario("SEC-12")
def test_duplicate_send_does_not_invoke_twice(client, a, receiver):
    p = preview(client, a).json()
    assert send(client, a, p).status_code == 200
    r = send(client, a, p)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_DISPATCHED"
    r = client.patch(f"/api/requests/{p['request_id']}/review", headers=a, json={"expected_review_revision": 1, "hide_message_indices": [1]})
    assert r.json()["error"]["code"] == "REQUEST_NOT_READY"
    assert len(receiver.invocations) == 1


@pytest.mark.scenario("SEC-12")
def test_concurrent_sends_invoke_receiver_once(app, client, a, receiver):
    original = receiver.send

    def slow_send(request_id, payload_bytes):
        time.sleep(0.2)  # widen the race window
        return original(request_id, payload_bytes)

    receiver.send = slow_send
    p = preview(client, a).json()
    barrier = threading.Barrier(6)
    results: list[int] = []

    def worker():
        barrier.wait()
        results.append(send(client, a, p).status_code)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [200, 409, 409, 409, 409, 409]
    assert len(receiver.invocations) == 1


# ----------------------------------------------------------- receiver failure --
@pytest.mark.scenario("SEC-13")
def test_receiver_failure_is_reported_honestly(settings):
    client, rec = failing_client(settings)
    a = login(client, "analyst_a")
    p = preview(client, a).json()
    r = send(client, a, p)
    assert r.status_code == 502 and r.json()["error"]["code"] == "RECEIVER_FAILED"
    assert len(rec.invocations) == 1
    receipt = client.get(f"/api/requests/{p['request_id']}/receipt", headers=a).json()
    assert receipt["status"] == "send_failed" and receipt["receiver_attempts"] == 1
    assert receipt["confirmed_sent_payload_hash"] is None
    assert receipt["prepared_payload_hash"] == p["preview_hash"]
    # No automatic or manual resend of the same request.
    assert send(client, a, p).json()["error"]["code"] == "ALREADY_DISPATCHED"
    assert len(rec.invocations) == 1


# ------------------------------------------------------------------ receipts --
@pytest.mark.scenario("SEC-03", "SEC-14")
def test_receipt_is_metadata_only_and_creator_only(client, a, b):
    p = preview(client, a).json()
    rid = p["request_id"]
    r = client.get(f"/api/requests/{rid}/receipt", headers=a)
    assert r.status_code == 409 and r.json()["error"]["code"] == "RECEIPT_NOT_READY"
    send(client, a, p)
    r = client.get(f"/api/requests/{rid}/receipt", headers=a)
    assert r.status_code == 200
    text = r.text
    for forbidden in ["reset link", "[EMAIL]", "Emma", "@example", "555-01", "Summarize", "Bearer",
                      a["Authorization"].split()[1], "feedback_a.csv", '"messages"', "outbound_payload"]:
        assert forbidden not in text, forbidden
    rec = r.json()
    assert rec["confirmed_sent_payload_hash"] == rec["prepared_payload_hash"] == p["preview_hash"]
    assert rec["receiver_mode"] == "local_demo" and rec["account_id"] == "analyst_a"
    assert client.get(f"/api/requests/{rid}/receipt", headers=b).status_code == 403
