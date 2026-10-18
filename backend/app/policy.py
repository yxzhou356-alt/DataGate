"""Owner policy evaluation.

Owner rules always win. This module answers one question: given the *current*
policy, may this account use this dataset for this purpose and destination?
It never looks at requester review choices; those can only hide more content.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from .storage import Policy

SUPPORTED_REDACTIONS = ("EMAIL", "PHONE", "PERSON")
MANDATORY_BASELINE = ("EMAIL", "PHONE")  # the owner CLI never removes these


@dataclass(frozen=True)
class PolicyDecision:
    has_access: bool
    allowed: bool                 # access AND purpose AND destination AND sharing permitted
    reason_codes: tuple[str, ...]  # policy denial codes, empty when allowed


def fingerprint(policy: Policy) -> str:
    """Internal digest of every policy field, including the account allow-list and
    person_style.

    policy_version is bumped for legitimate edits; the fingerprint additionally
    detects out-of-band edits made without a version bump. The transformation and
    detector versions are checked separately (transform.pipeline_id).
    """
    data = asdict(policy)
    data["allowed_accounts"] = sorted(data["allowed_accounts"])
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate(policy: Policy, account_id: str, purpose: str, destination: str) -> PolicyDecision:
    has_access = account_id in policy.allowed_accounts
    codes: list[str] = []
    if purpose not in policy.allowed_purposes:
        codes.append("PURPOSE_NOT_ALLOWED")
    if destination not in policy.allowed_destinations:
        codes.append("DESTINATION_NOT_ALLOWED")
    if policy.sharing_mode != "redacted_only":
        # "none" (or any unknown mode) blocks sharing even after redaction.
        codes.append("SHARING_PROHIBITED")
    if not policy.outbound_fields.get(purpose):
        if "PURPOSE_NOT_ALLOWED" not in codes:
            codes.append("PURPOSE_NOT_ALLOWED")
    return PolicyDecision(has_access=has_access, allowed=has_access and not codes, reason_codes=tuple(codes))
