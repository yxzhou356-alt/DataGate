"""API-level governance regressions using isolated source copies and databases.

PERSON recognition is replaced with a deterministic local model here so these
tests measure authorization, review binding and transformation integration. The
separate detector evaluation measures the installed pretrained model itself.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from types import SimpleNamespace

import pytest

from app import demo_control, detection, security_report, transform
from conftest import PREVIEW_A, preview, send


MESSAGES = [
    "Hi, Alice Jones here. Login fails for contract ORCHID-42; contact alice.jones@example.com or 213-555-0101.",
    "Alice Jones says exports fail. Bob Smith agrees.",
    "Emoji 😀 then ALPHA-7 is slow.",
]
PRIVATE_VALUES = [
    "Alice Jones", "Bob Smith", "alice.jones@example.com", "213-555-0101",
    "ORCHID-42", "ALPHA-7", "Secret Column Person", "column-only-secret@private.example",
]


class _LocalTestModel:
    """A test double, deliberately not a claimed pretrained-model result."""

    meta = {"version": "integration-test-ner-1"}
    path = None

    def __init__(self):
        self.meta = dict(type(self).meta)

    def __call__(self, text):
        return SimpleNamespace(ents=[
            SimpleNamespace(start_char=m.start(), end_char=m.end(), label_="PERSON")
            for m in re.finditer(r"\b(?:Alice Jones|Bob Smith)\b", text)
        ])


@pytest.fixture(autouse=True)
def deterministic_person_model(monkeypatch):
    model = _LocalTestModel()
    monkeypatch.setattr(detection, "load_model", lambda: model)
    return model


def _write_messages(settings, dataset="feedback_a", messages=None):
    messages = MESSAGES if messages is None else messages
    path = settings.sources_dir / f"{dataset}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "ticket_id", "customer_name", "email", "phone", "plan_tier",
            "account_value", "product_area", "message",
        ])
        for index, message in enumerate(messages):
            writer.writerow([
                f"T{index:03}", "Secret Column Person", "column-only-secret@private.example",
                "310-555-0123", "enterprise", "94000", "authentication", message,
            ])


def _require_person(settings, dataset="feedback_a"):
    with sqlite3.connect(settings.db_path) as conn:
        current = json.loads(conn.execute(
            "SELECT required_redactions FROM policies WHERE dataset_id=?", (dataset,),
        ).fetchone()[0])
        if "PERSON" not in current:
            conn.execute(
                "UPDATE policies SET required_redactions=?,policy_version=policy_version+1 WHERE dataset_id=?",
                (json.dumps([*current, "PERSON"]), dataset),
            )


def _prepared(client, a, settings):
    _write_messages(settings)
    _require_person(settings)
    response = preview(client, a)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ready", result
    return result


def _review(client, headers, prepared, spans=None, **changes):
    body = {
        "expected_review_revision": prepared["review_revision"],
        "expected_preview_hash": prepared["preview_hash"],
        "hide_message_indices": [],
        "manual_spans": [] if spans is None else spans,
    }
    body.update(changes)
    return client.patch(
        f"/api/requests/{prepared['request_id']}/review", headers=headers, json=body,
    )


def _span(message_index, value):
    start = MESSAGES[message_index].index(value)
    return {"message_index": message_index, "start": start, "end": start + len(value)}


def _assert_no_customer_content(value):
    serialized = json.dumps(value, ensure_ascii=False)
    for forbidden in PRIVATE_VALUES + MESSAGES:
        assert forbidden not in serialized, forbidden
    def assert_keys(item):
        if isinstance(item, dict):
            forbidden = {"original_messages", "outbound_payload", "payload_bytes", "pseudonym_mapping"}
            assert not forbidden.intersection(item)
            for nested in item.values():
                assert_keys(nested)
        elif isinstance(item, list):
            for nested in item:
                assert_keys(nested)
    assert_keys(value)


def test_raw_view_requires_separate_grant_and_never_exposes_dropped_columns(client, a, b, settings):
    pa = _prepared(client, a, settings)
    assert pa["raw_view_allowed"] is True
    assert pa["original_messages"] == MESSAGES
    assert "column-only-secret@private.example" not in json.dumps(pa)
    assert pa["findings"] and pa["detector_status"]["available"] is True
    assert pa["policy_explanations"]

    _write_messages(settings, "feedback_b")
    _require_person(settings, "feedback_b")
    pb = preview(client, b, {**PREVIEW_A, "dataset_id": "feedback_b"})
    assert pb.status_code == 200, pb.text
    body = pb.json()
    assert body["status"] == "ready"  # Processing access still exists.
    assert body["raw_view_allowed"] is False
    assert body["original_messages"] is None
    for forbidden in ("Alice Jones", "Bob Smith", "alice.jones@example.com", "213-555-0101", "Secret Column Person"):
        assert forbidden not in json.dumps(body), forbidden
    manual = _review(client, b, body, [{"message_index": 0, "start": 0, "end": 2}])
    assert manual.status_code == 403 and manual.json()["error"]["code"] == "RAW_ACCESS_DENIED"
    assert preview(client, b).status_code == 403


def test_raw_grant_changes_invalidate_approval_without_revoking_processing(client, a, settings, receiver, monkeypatch):
    p = _prepared(client, a, settings)
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(settings.data_dir))
    demo_control.main(["raw-revoke", "--account", "analyst_a", "--dataset", "feedback_a"])
    response = send(client, a, p)
    assert response.status_code == 409 and response.json()["error"]["code"] == "POLICY_CHANGED"
    assert receiver.invocations == []
    fresh = preview(client, a)
    assert fresh.status_code == 200 and fresh.json()["status"] == "ready"
    assert fresh.json()["raw_view_allowed"] is False
    assert fresh.json()["original_messages"] is None


def test_unicode_manual_span_is_applied_without_restoring_locked_entities(client, a, settings, receiver):
    p = _prepared(client, a, settings)
    spans = [_span(0, "ORCHID-42"), _span(2, "ALPHA-7")]
    response = _review(client, a, p, spans)
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["review_revision"] == p["review_revision"] + 1
    assert reviewed["preview_hash"] != p["preview_hash"]
    messages = reviewed["outbound_payload"]["messages"]
    assert "Emoji 😀 then " in messages[2]
    assert "ORCHID-42" not in messages[0] and "ALPHA-7" not in messages[2]
    assert " is slow." in messages[2]
    for forbidden in ("Alice Jones", "alice.jones@example.com", "213-555-0101"):
        assert forbidden not in json.dumps(reviewed["outbound_payload"])
    assert send(client, a, reviewed).status_code == 200
    captured = receiver.invocations[0][1].decode("utf-8")
    for forbidden in ("Alice Jones", "alice.jones@example.com", "213-555-0101", "ORCHID-42", "ALPHA-7"):
        assert forbidden not in captured


@pytest.mark.parametrize("span", [
    {"message_index": -1, "start": 0, "end": 1},
    {"message_index": 99, "start": 0, "end": 1},
    {"message_index": 0, "start": -1, "end": 3},
    {"message_index": 0, "start": 3, "end": 3},
    {"message_index": 0, "start": 0, "end": 10000},
    {"message_index": True, "start": 0, "end": 1},
    {"message_index": 0, "start": False, "end": 1},
])
def test_invalid_manual_span_cannot_mutate_review(client, a, settings, receiver, span):
    p = _prepared(client, a, settings)
    response = _review(client, a, p, [span])
    assert response.status_code == 422, response.text
    assert receiver.invocations == []
    # A valid edit still uses revision 1, proving invalid input was not committed.
    valid = _review(client, a, p, [_span(0, "ORCHID-42")])
    assert valid.status_code == 200, valid.text
    assert valid.json()["review_revision"] == 2


def test_stale_preview_hash_and_cross_source_span_are_rejected(client, a, settings, receiver):
    p = _prepared(client, a, settings)
    mismatch = _review(client, a, p, [_span(0, "ORCHID-42")], expected_preview_hash="0" * 64)
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "PREVIEW_CHANGED"
    # Offsets from the old source may not be reused after even a same-length edit.
    source = settings.sources_dir / "feedback_a.csv"
    source.write_bytes(source.read_bytes().replace(b"ORCHID-42", b"VIOLET-17"))
    stale = _review(client, a, p, [_span(0, "ORCHID-42")])
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "DATASET_CHANGED"
    assert receiver.invocations == []


def test_person_pseudonyms_are_consistent_and_survive_additional_hiding(client, a, settings, receiver):
    p = _prepared(client, a, settings)
    messages = p["outbound_payload"]["messages"]
    first = re.findall(r"\[PERSON_\d+\]", messages[0])
    second = re.findall(r"\[PERSON_\d+\]", messages[1])
    assert len(first) == 1 and len(second) == 2
    assert first[0] == second[0] and second[0] != second[1]
    response = _review(client, a, p, hide_message_indices=[0])
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["outbound_payload"]["messages"][0] == "[HIDDEN_BY_USER]"
    assert re.findall(r"\[PERSON_\d+\]", reviewed["outbound_payload"]["messages"][1]) == second
    assert send(client, a, p).status_code == 409  # Old review approval cannot send.
    assert receiver.invocations == []
    assert send(client, a, reviewed).status_code == 200


def test_detector_fingerprint_change_invalidates_reviewed_dispatch(client, a, settings, receiver, deterministic_person_model):
    p = _prepared(client, a, settings)
    deterministic_person_model.meta["version"] = "integration-test-ner-2"
    response = send(client, a, p)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "PREVIEW_CHANGED"
    assert receiver.invocations == []


def test_revocation_during_send_payload_rebuild_is_rechecked_before_dispatch(
    client, a, settings, receiver, monkeypatch,
):
    p = _prepared(client, a, settings)
    real_prepare = transform.prepare
    rebuilds = []

    def prepare_then_revoke(*args, **kwargs):
        prepared = real_prepare(*args, **kwargs)
        rebuilds.append(True)
        # Simulate an owner revocation after initial checks, during preparation.
        with sqlite3.connect(settings.db_path) as conn:
            conn.execute("DELETE FROM grants WHERE dataset_id='feedback_a' AND account_id='analyst_a'")
            conn.execute("UPDATE policies SET policy_version=policy_version+1 WHERE dataset_id='feedback_a'")
        return prepared

    monkeypatch.setattr(transform, "prepare", prepare_then_revoke)
    response = send(client, a, p)
    assert rebuilds == [True]
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "ACCESS_REVOKED"
    assert receiver.invocations == []
    receipt = client.get(f"/api/requests/{p['request_id']}/receipt", headers=a)
    assert receipt.status_code == 200, receipt.text
    metadata = receipt.json()
    assert metadata["status"] == "blocked" and metadata["decision"] == "block"
    assert metadata["reason_codes"] == ["ACCESS_REVOKED"]
    assert metadata["receiver_attempts"] == 0 and metadata["confirmed_sent_payload_hash"] is None


def test_required_person_detector_unavailability_never_becomes_empty_success(client, a, settings, receiver, monkeypatch):
    _write_messages(settings)
    _require_person(settings)

    def unavailable():
        raise detection.DetectorUnavailable("Synthetic test failure")

    monkeypatch.setattr(detection, "load_model", unavailable)
    response = preview(client, a)
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "DETECTOR_UNAVAILABLE"
    assert "Synthetic test failure" not in response.text
    assert receiver.invocations == []


@pytest.mark.parametrize("operation", ["review", "send"])
def test_person_inference_failure_blocks_review_or_send_with_a_receipt(
    client, a, settings, receiver, monkeypatch, operation,
):
    p = _prepared(client, a, settings)

    def inference_failure(_self, _text):
        # Loading and fingerprinting still succeed; only inference fails.
        raise RuntimeError("PRIVATE-INFERENCE-DETAIL")

    monkeypatch.setattr(_LocalTestModel, "__call__", inference_failure)
    response = _review(client, a, p) if operation == "review" else send(client, a, p)
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "DETECTOR_UNAVAILABLE"
    assert "PRIVATE-INFERENCE-DETAIL" not in response.text
    assert receiver.invocations == []
    receipt = client.get(f"/api/requests/{p['request_id']}/receipt", headers=a)
    assert receipt.status_code == 200, receipt.text
    metadata = receipt.json()
    assert metadata["status"] == "blocked" and metadata["decision"] == "block"
    assert metadata["reason_codes"] == ["DETECTOR_UNAVAILABLE"]
    assert metadata["receiver_attempts"] == 0 and metadata["confirmed_sent_payload_hash"] is None
    _assert_no_customer_content(metadata)


def test_overlapping_person_and_email_spans_do_not_leak_person_prefix(
    client, a, settings, receiver, monkeypatch,
):
    text = "Alice alice@example.com"
    _write_messages(settings, messages=[text, "The export button is slow."])
    _require_person(settings)

    def person_overlapping_email(_self, message):
        entities = [SimpleNamespace(start_char=0, end_char=len(text), label_="PERSON")] if message == text else []
        return SimpleNamespace(ents=entities)

    monkeypatch.setattr(_LocalTestModel, "__call__", person_overlapping_email)
    response = preview(client, a)
    assert response.status_code == 200, response.text
    p = response.json()
    assert p["status"] == "ready"
    outbound = json.dumps(p["outbound_payload"])
    assert "Alice" not in outbound and "alice@example.com" not in outbound
    assert send(client, a, p).status_code == 200
    assert len(receiver.invocations) == 1
    sent = receiver.invocations[0][1].decode("utf-8")
    assert "Alice" not in sent and "alice@example.com" not in sent


def test_unsupported_required_detector_fails_closed(client, a, settings, receiver):
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            "UPDATE policies SET required_redactions=?,policy_version=policy_version+1 WHERE dataset_id='feedback_a'",
            (json.dumps(["EMAIL", "PHONE", "SECRET_TOKEN_UNKNOWN"]),),
        )
    response = preview(client, a)
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "block"
    assert response.json()["reason_codes"] == ["UNSUPPORTED_POLICY"]
    assert response.json()["outbound_payload"] is None
    assert receiver.invocations == []


def test_unknown_configured_operation_is_denied_instead_of_server_error(client, a, settings, receiver):
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            "UPDATE policies SET allowed_purposes=?,outbound_fields=? WHERE dataset_id='feedback_a'",
            (json.dumps(["feedback_summary", "unknown_operation"]),
             json.dumps({"feedback_summary": ["message"], "unknown_operation": ["message"]})),
        )
    response = preview(client, a, {**PREVIEW_A, "purpose": "unknown_operation"})
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "block"
    assert "UNSUPPORTED_POLICY" in response.json()["reason_codes"]
    assert receiver.invocations == []


def test_unterminated_csv_quote_is_a_validation_failure(client, a, settings, receiver):
    (settings.sources_dir / "feedback_a.csv").write_text(
        'ticket_id,message\nT1,"unterminated', encoding="utf-8",
    )
    response = preview(client, a)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "DATASET_INVALID"
    assert "unterminated" not in response.text
    assert receiver.invocations == []


def test_history_timeline_and_export_are_metadata_only_and_creator_scoped(client, a, b, settings, receiver):
    p = _prepared(client, a, settings)
    reviewed = _review(client, a, p, [_span(0, "ORCHID-42")]).json()
    assert send(client, a, reviewed).status_code == 200
    pb = preview(client, b, {**PREVIEW_A, "dataset_id": "feedback_b"}).json()
    rid = p["request_id"]
    history = client.get("/api/history", headers=a)
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["total"] >= 1
    ids = {request["request_id"] for request in body["requests"]}
    assert rid in ids and pb["request_id"] not in ids
    _assert_no_customer_content(body)
    denied = client.get("/api/history", headers=a, params={"user_id": "analyst_b"})
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "REQUEST_ACCESS_DENIED"
    filtered = client.get("/api/history", headers=a, params={"dataset_id": "feedback_a", "decision": "redact"})
    assert filtered.status_code == 200 and rid in {r["request_id"] for r in filtered.json()["requests"]}

    timeline = client.get(f"/api/requests/{rid}/timeline", headers=a)
    assert timeline.status_code == 200, timeline.text
    assert timeline.json()["request_id"] == rid
    events = timeline.json()["events"]
    assert [event["event_type"] for event in events] == ["preview", "review", "send_claimed", "send"]
    assert events[0]["metadata"]["review_revision"] == 1
    assert events[1]["metadata"]["review_revision"] == 2
    _assert_no_customer_content(timeline.json())
    audit = client.get(f"/api/requests/{rid}/audit", headers=a)
    assert audit.status_code == 200, audit.text
    exported = audit.json()
    assert exported["schema_version"] == "1.1" and exported["request"]["request_id"] == rid
    assert exported["receipt"]["status"] == "sent"
    assert exported["receipt"]["receiver_attempts"] == 1
    _assert_no_customer_content(exported)
    for suffix in ("timeline", "audit", "receipt"):
        assert client.get(f"/api/requests/{rid}/{suffix}", headers=b).status_code == 403


def test_owner_revocation_is_logged_without_an_analyst_impersonation(client, a, settings, receiver, monkeypatch):
    p = _prepared(client, a, settings)
    monkeypatch.setenv("DATAGATE_DATA_DIR", str(settings.data_dir))
    demo_control.main(["revoke", "--account", "analyst_a", "--dataset", "feedback_a"])
    blocked = send(client, a, p)
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "ACCESS_REVOKED"
    assert receiver.invocations == []
    audit = client.get(f"/api/requests/{p['request_id']}/audit", headers=a)
    assert audit.status_code == 200, audit.text
    body = audit.json()
    assert body["receipt"]["decision"] == "block"
    assert body["receipt"]["receiver_attempts"] == 0
    _assert_no_customer_content(body)
    permission_events = [event for event in body["events"] if event["event_type"] == "permission_changed"]
    assert len(permission_events) == 1
    assert permission_events[0]["actor_kind"] == "local_operator"
    assert permission_events[0]["actor_id"] == "demo_control"


@pytest.mark.parametrize("route", ["/api/history", "/api/security/report"])
def test_new_global_views_require_authentication(client, route):
    response = client.get(route)
    assert response.status_code == 401


def test_security_report_missing_does_not_run_tests_or_mutate_live_requests(client, a, settings, receiver, monkeypatch, tmp_path):
    p = _prepared(client, a, settings)
    monkeypatch.setattr(security_report, "ROOT", tmp_path / "no-report-project")
    def forbid_test_execution(*_args, **_kwargs):
        raise AssertionError("A report GET must never launch tests or shell commands")
    monkeypatch.setattr(security_report.subprocess, "run", forbid_test_execution)
    with sqlite3.connect(settings.db_path) as conn:
        before = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    response = client.get("/api/security/report", headers=a)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["available"] is False and report["stale"] is False
    assert report["report"] is None
    assert re.fullmatch(r"[0-9a-f]{64}", report["source_fingerprint"])
    with sqlite3.connect(settings.db_path) as conn:
        after = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    assert after == before and receiver.invocations == []
    assert send(client, a, p).status_code == 200  # Live draft was not revoked/mutated.


@pytest.mark.parametrize("stale", [False, True])
def test_security_report_reads_saved_fixture_and_marks_staleness(client, a, settings, monkeypatch, tmp_path, stale):
    # This is a synthetic serialization fixture, not claimed test-run evidence.
    monkeypatch.setattr(security_report, "ROOT", tmp_path / "report-project")
    current = security_report.source_fingerprint()
    artifact = {
        "schema_version": "1.1", "source_fingerprint": "0" * 64 if stale else current,
        "receiver_mode": "local_demo", "tests": [], "controls": [],
        "generated_at": "2026-10-18T01:00:00Z",
    }
    (settings.data_dir / "security-report.json").write_text(json.dumps(artifact), encoding="utf-8")
    def forbid_test_execution(*_args, **_kwargs):
        raise AssertionError("Reading a report must not launch its runner")
    monkeypatch.setattr(security_report.subprocess, "run", forbid_test_execution)
    response = client.get("/api/security/report", headers=a)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["available"] is True and report["stale"] is stale
    assert report["source_fingerprint"] == current
    assert report["report"] == artifact
