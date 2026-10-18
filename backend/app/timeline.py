"""Creator-only receipt timeline: query parsing and opaque keyset cursors.

The list never takes an account from the request; the workflow passes the
token's account. Every filter only narrows the caller's own records, so a filter
on a dataset the caller never used returns the same empty page as an unknown id.
Invalid input raises INVALID_REQUEST without echoing the submitted value.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .errors import ApiError

TIMELINE_STATUSES = ("blocked", "stale", "sent", "send_failed")  # outcomes; drafts are excluded
DECISIONS = ("allow", "redact", "block")
ALLOWED_PARAMS = {"limit", "cursor", "status", "decision", "dataset_id", "since", "until"}
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")  # storage format (workflow._now)
_REQUEST_ID = re.compile(r"^req_[0-9a-f]{24}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_INVALID = "Invalid filter, limit or cursor."


@dataclass(frozen=True)
class TimelineQuery:
    limit: int = DEFAULT_LIMIT
    before: tuple[str, str] | None = None  # (recorded_at, request_id) of the last item already seen
    statuses: tuple[str, ...] = TIMELINE_STATUSES
    decision: str | None = None
    dataset_id: str | None = None
    since: str | None = None  # inclusive, storage format
    until: str | None = None  # exclusive, storage format


def _bad() -> ApiError:
    return ApiError("INVALID_REQUEST", message=_INVALID)


def to_storage_ts(value: str) -> str:
    """ISO-8601 with an explicit timezone -> the UTC storage format used for ordering."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _bad()
    if parsed.tzinfo is None:
        raise _bad()  # ambiguous local time
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def encode_cursor(recorded_at: str, request_id: str) -> str:
    raw = json.dumps([recorded_at, request_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,200}", cursor):
        raise _bad()
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise _bad()
    if (not isinstance(value, list) or len(value) != 2 or not all(isinstance(v, str) for v in value)
            or not _TS.match(value[0]) or not _REQUEST_ID.match(value[1])):
        raise _bad()
    return value[0], value[1]


def parse_query(params: list[tuple[str, str]]) -> TimelineQuery:
    """Validate raw query pairs. Unknown keys (including account_id) and repeats are rejected."""
    keys = [k for k, _ in params]
    if set(keys) - ALLOWED_PARAMS or len(keys) != len(set(keys)):
        raise _bad()
    q = dict(params)
    limit = DEFAULT_LIMIT
    if "limit" in q:
        if not re.fullmatch(r"\d{1,3}", q["limit"]) or not 1 <= int(q["limit"]) <= MAX_LIMIT:
            raise _bad()
        limit = int(q["limit"])
    statuses = TIMELINE_STATUSES
    if "status" in q:
        if q["status"] not in TIMELINE_STATUSES:
            raise _bad()
        statuses = (q["status"],)
    if "decision" in q and q["decision"] not in DECISIONS:
        raise _bad()
    if "dataset_id" in q and not _IDENTIFIER.match(q["dataset_id"]):
        raise _bad()
    since = to_storage_ts(q["since"]) if "since" in q else None
    until = to_storage_ts(q["until"]) if "until" in q else None
    if since and until and since >= until:
        raise _bad()
    return TimelineQuery(
        limit=limit,
        before=decode_cursor(q["cursor"]) if "cursor" in q else None,
        statuses=statuses,
        decision=q.get("decision"),
        dataset_id=q.get("dataset_id"),
        since=since,
        until=until,
    )
