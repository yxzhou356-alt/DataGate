"""Request workflow: preview -> review -> approve & send -> receipt.

Each protected step re-reads the CURRENT policy, grants and source bytes.
Approval is bound to: account, dataset, source hash + revision, policy version
+ fingerprint, purpose, destination, review revision and canonical payload hash.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import policy as policy_mod
from . import transform
from .errors import ApiError
from .receiver import ReceiverAdapter
from .storage import Dataset, Policy, Store

FINAL_STATUSES = {"blocked", "sent", "send_failed"}
DISPATCHED_STATUSES = {"sending", "sent", "send_failed"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _source_sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


class Workflow:
    def __init__(self, store: Store, sources_dir: Path, receiver: ReceiverAdapter):
        self.store = store
        self.sources_dir = sources_dir
        self.receiver = receiver

    # ------------------------------------------------------------------ #
    # Datasets
    # ------------------------------------------------------------------ #
    def list_datasets(self, account_id: str) -> dict:
        out = []
        for ds in self.store.list_datasets_for(account_id):
            pol = self.store.get_policy(ds.dataset_id)
            if pol is None:
                continue
            out.append(
                {
                    "dataset_id": ds.dataset_id,
                    "display_name": ds.display_name,
                    "dataset_revision": ds.dataset_revision,
                    "passport": {
                        "declared_owner": ds.declared_owner,
                        "allowed_purposes": list(pol.allowed_purposes),
                        "allowed_destinations": list(pol.allowed_destinations),
                        "outbound_fields": sorted({f for fs in pol.outbound_fields.values() for f in fs}),
                        "required_redactions": list(pol.required_redactions),
                        "sharing_mode": pol.sharing_mode,
                        "policy_version": pol.policy_version,
                    },
                }
            )
        return {"datasets": out}

    # ------------------------------------------------------------------ #
    # Preview
    # ------------------------------------------------------------------ #
    def create_preview(self, account_id: str, dataset_id: str, purpose: str, destination: str) -> dict:
        ds = self.store.get_dataset(dataset_id)
        pol = self.store.get_policy(dataset_id) if ds else None
        if ds is None or pol is None:
            raise ApiError("DATASET_NOT_FOUND")
        decision = policy_mod.evaluate(pol, account_id, purpose, destination)
        if not decision.has_access:
            raise ApiError("DATASET_ACCESS_DENIED")

        request_id = "req_" + secrets.token_hex(12)
        base = {
            "request_id": request_id,
            "account_id": account_id,
            "dataset_id": dataset_id,
            "purpose": purpose,
            "destination": destination,
            "receiver_mode": self.receiver.mode,
            "receiver_attempts": 0,
            "created_at": _now(),
        }

        if not decision.allowed:
            # Owner policy forbids this operation: record it, never touch the receiver.
            self.store.insert_request(
                {
                    **base,
                    "status": "blocked",
                    "decision": "block",
                    "reason_codes": list(decision.reason_codes),
                    "dataset_revision": ds.dataset_revision,
                    "final_policy_version": pol.policy_version,
                    "occurred_at": _now(),
                }
            )
            return self._response(self.store.get_request(request_id), None)

        try:
            source = transform.read_source(self.sources_dir / ds.source_file)
        except transform.SourceInvalid as exc:
            raise ApiError("DATASET_INVALID", message="The source dataset failed validation: " + "; ".join(exc.problems[:5]))

        prepared = transform.prepare(source, purpose, pol.outbound_fields[purpose], pol.required_redactions, [])
        decision_label = "redact" if any(prepared.redaction_counts.values()) else "allow"
        self.store.insert_request(
            {
                **base,
                "status": "ready",
                "decision": decision_label,
                "reason_codes": ["REDACTION_REQUIRED"] if decision_label == "redact" else [],
                "dataset_revision": ds.dataset_revision,
                "source_sha256": source.sha256,
                "preview_policy_version": pol.policy_version,
                "preview_policy_fp": policy_mod.fingerprint(pol),
                "review_revision": 1,
                "hidden_indices": [],
                "redaction_counts": prepared.redaction_counts,
                "dropped_fields": prepared.dropped_fields,
                "preview_hash": prepared.preview_hash,
            }
        )
        return self._response(self.store.get_request(request_id), prepared)

    # ------------------------------------------------------------------ #
    # Review (additional whole-message hiding only)
    # ------------------------------------------------------------------ #
    def review(self, account_id: str, request_id: str, expected_revision: int, hide: list[int]) -> dict:
        req = self._owned(account_id, request_id)
        if req["status"] != "ready":
            raise ApiError("REQUEST_NOT_READY", request_id)
        if req["review_revision"] != expected_revision:
            raise ApiError("REVIEW_CHANGED", request_id)

        ds, pol, source = self._recheck_current(req)

        n = len(source.rows)
        if any(i < 0 or i >= n for i in hide):
            raise ApiError("INVALID_REVIEW", request_id)
        indices = sorted(set(hide))
        if len(indices) >= n:
            raise ApiError("NO_CONTENT_TO_SEND", request_id)

        prepared = transform.prepare(source, req["purpose"], pol.outbound_fields[req["purpose"]], pol.required_redactions, indices)
        ok = self.store.update_request_if(
            request_id,
            {"status": "ready", "review_revision": expected_revision},
            {
                "review_revision": expected_revision + 1,
                "hidden_indices": indices,
                "redaction_counts": prepared.redaction_counts,
                "preview_hash": prepared.preview_hash,
            },
        )
        if not ok:
            latest = self.store.get_request(request_id)
            raise ApiError("REVIEW_CHANGED" if latest and latest["status"] == "ready" else "REQUEST_NOT_READY", request_id)
        return self._response(self.store.get_request(request_id), prepared)

    # ------------------------------------------------------------------ #
    # Approve & send
    # ------------------------------------------------------------------ #
    def send(self, account_id: str, request_id: str, expected_revision: int, preview_hash: str) -> dict:
        req = self._owned(account_id, request_id)
        if req["status"] in DISPATCHED_STATUSES:
            raise ApiError("ALREADY_DISPATCHED", request_id)
        if req["status"] != "ready":
            raise ApiError("REQUEST_NOT_READY", request_id)
        if req["review_revision"] != expected_revision:
            raise ApiError("REVIEW_CHANGED", request_id)
        if req["preview_hash"] != preview_hash:
            raise ApiError("PREVIEW_CHANGED", request_id)

        ds, pol, source = self._recheck_current(req)

        # Rebuild from backend source + stored choices; never from client content.
        prepared = transform.prepare(
            source, req["purpose"], pol.outbound_fields[req["purpose"]], pol.required_redactions, req["hidden_indices"]
        )
        if prepared.preview_hash != req["preview_hash"]:
            self._mark_stale(req, "PREVIEW_CHANGED")
            raise ApiError("PREVIEW_CHANGED", request_id)

        # Atomic claim: exactly one competing Send can move ready -> sending.
        claimed = self.store.update_request_if(
            request_id,
            {"status": "ready", "review_revision": expected_revision, "preview_hash": preview_hash},
            {"status": "sending", "final_policy_version": pol.policy_version},
        )
        if not claimed:
            latest = self.store.get_request(request_id)
            if latest and latest["status"] in DISPATCHED_STATUSES:
                raise ApiError("ALREADY_DISPATCHED", request_id)
            raise ApiError("REQUEST_NOT_READY", request_id)

        # The ONLY place the receiver is invoked. No automatic retries.
        try:
            result = self.receiver.send(request_id, prepared.canonical_bytes)
        except Exception:
            self.store.update_request_if(
                request_id,
                {"status": "sending"},
                {"status": "send_failed", "receiver_attempts": 1, "occurred_at": _now()},
            )
            raise ApiError("RECEIVER_FAILED", request_id)

        acknowledged = bool(result.acknowledged)
        self.store.update_request_if(
            request_id,
            {"status": "sending"},
            {
                "status": "sent" if acknowledged else "send_failed",
                "receiver_attempts": 1,
                "receiver_result": result.as_dict(),
                "confirmed_sent_hash": prepared.preview_hash if acknowledged else None,
                "occurred_at": _now(),
            },
        )
        if not acknowledged:
            raise ApiError("RECEIVER_FAILED", request_id)
        final = self.store.get_request(request_id)
        return {
            "request_id": request_id,
            "decision": final["decision"],
            "status": final["status"],
            "receiver_mode": final["receiver_mode"],
            "receiver_attempts": final["receiver_attempts"],
            "receiver_result": result.as_dict(),
            "receipt_available": True,
        }

    # ------------------------------------------------------------------ #
    # Receipt (metadata only)
    # ------------------------------------------------------------------ #
    def receipt(self, account_id: str, request_id: str) -> dict:
        # Creator-only, but deliberately NOT gated on current dataset access.
        req = self.store.get_request(request_id)
        if req is None:
            raise ApiError("REQUEST_NOT_FOUND", request_id)
        if req["account_id"] != account_id:
            raise ApiError("REQUEST_ACCESS_DENIED", request_id)
        if req["status"] not in FINAL_STATUSES:
            raise ApiError("RECEIPT_NOT_READY", request_id)
        return {
            "schema_version": "1.0",
            "request_id": req["request_id"],
            "account_id": req["account_id"],
            "dataset_id": req["dataset_id"],
            "dataset_revision": req["dataset_revision"],
            "policy_version": req["final_policy_version"],
            "preview_policy_version": req["preview_policy_version"],
            "review_revision": req["review_revision"],
            "purpose": req["purpose"],
            "destination": req["destination"],
            "decision": req["decision"],
            "status": req["status"],
            "reason_codes": req["reason_codes"],
            "redaction_counts": req["redaction_counts"],
            "additional_hidden_messages": len(req["hidden_indices"]),
            "prepared_payload_hash": req["preview_hash"],
            "confirmed_sent_payload_hash": req["confirmed_sent_hash"],
            "receiver_mode": req["receiver_mode"],
            "receiver_attempts": req["receiver_attempts"],
            "occurred_at": req["occurred_at"],
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _owned(self, account_id: str, request_id: str) -> dict[str, Any]:
        req = self.store.get_request(request_id)
        if req is None:
            raise ApiError("REQUEST_NOT_FOUND", request_id)
        if req["account_id"] != account_id:
            raise ApiError("REQUEST_ACCESS_DENIED", request_id)
        return req

    def _recheck_current(self, req: dict[str, Any]) -> tuple[Dataset, Policy, transform.SourceSnapshot]:
        """Fresh access/policy/source check. Transitions the request on failure."""
        rid = req["request_id"]
        ds = self.store.get_dataset(req["dataset_id"])
        pol = self.store.get_policy(req["dataset_id"])
        if ds is None or pol is None:
            self._mark_stale(req, "DATASET_CHANGED")
            raise ApiError("DATASET_CHANGED", rid)

        decision = policy_mod.evaluate(pol, req["account_id"], req["purpose"], req["destination"])
        if not decision.has_access:
            self._mark_blocked(req, ["ACCESS_REVOKED"], pol.policy_version)
            raise ApiError("ACCESS_REVOKED", rid)
        if not decision.allowed:
            self._mark_blocked(req, list(decision.reason_codes), pol.policy_version)
            raise ApiError(decision.reason_codes[0], rid)

        current_sha = _source_sha(self.sources_dir / ds.source_file)
        if ds.dataset_revision != req["dataset_revision"] or current_sha != req["source_sha256"]:
            self._mark_stale(req, "DATASET_CHANGED")
            raise ApiError("DATASET_CHANGED", rid)
        if pol.policy_version != req["preview_policy_version"] or policy_mod.fingerprint(pol) != req["preview_policy_fp"]:
            self._mark_stale(req, "POLICY_CHANGED")
            raise ApiError("POLICY_CHANGED", rid)

        try:
            source = transform.read_source(self.sources_dir / ds.source_file)
        except transform.SourceInvalid:
            self._mark_stale(req, "DATASET_CHANGED")
            raise ApiError("DATASET_CHANGED", rid)
        if source.sha256 != req["source_sha256"]:  # changed between hash and parse
            self._mark_stale(req, "DATASET_CHANGED")
            raise ApiError("DATASET_CHANGED", rid)
        return ds, pol, source

    def _mark_blocked(self, req: dict[str, Any], codes: list[str], policy_version: int) -> None:
        self.store.update_request_if(
            req["request_id"],
            {"status": "ready"},
            {"status": "blocked", "decision": "block", "reason_codes": codes,
             "final_policy_version": policy_version, "occurred_at": _now()},
        )

    def _mark_stale(self, req: dict[str, Any], code: str) -> None:
        self.store.update_request_if(
            req["request_id"], {"status": "ready"}, {"status": "stale", "reason_codes": [code]}
        )

    def _response(self, req: dict[str, Any], prepared: transform.PreparedPayload | None) -> dict:
        return {
            "request_id": req["request_id"],
            "dataset_id": req["dataset_id"],
            "dataset_revision": req["dataset_revision"],
            "policy_version": req["preview_policy_version"] if prepared else req["final_policy_version"],
            "review_revision": req["review_revision"],
            "decision": req["decision"],
            "status": req["status"],
            "reason_codes": req["reason_codes"],
            "dropped_fields": req["dropped_fields"],
            "redaction_counts": req["redaction_counts"],
            "hidden_message_indices": req["hidden_indices"],
            "outbound_payload": prepared.payload if prepared else None,
            "preview_hash": prepared.preview_hash if prepared else None,
            "receiver_mode": req["receiver_mode"],
            "receiver_attempts": req["receiver_attempts"],
            "receipt_available": req["status"] in FINAL_STATUSES,
        }
