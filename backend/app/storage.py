"""SQLite persistence for accounts, datasets, owner policies, grants and requests.

Design notes
- The DB holds metadata only. Drafts store the *choices* needed to rebuild a
  payload (dataset, hidden indices, hashes, versions), never the payload text,
  so no customer content is persisted outside the source CSV itself.
- Every call opens a short-lived connection. Policy/source state is always read
  fresh, so CLI edits by the owner are seen at the next protected operation.
- Status transitions use conditional UPDATEs (compare-and-set) so that only one
  competing Send can claim dispatch.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id   TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id       TEXT PRIMARY KEY,
    display_name     TEXT NOT NULL,
    declared_owner   TEXT NOT NULL,
    source_file      TEXT NOT NULL,      -- file name inside the runtime sources dir
    dataset_revision INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS policies (
    dataset_id           TEXT PRIMARY KEY REFERENCES datasets(dataset_id),
    policy_version       INTEGER NOT NULL,
    allowed_purposes     TEXT NOT NULL,  -- JSON list
    allowed_destinations TEXT NOT NULL,  -- JSON list
    outbound_fields      TEXT NOT NULL,  -- JSON object purpose -> list of fields
    sharing_mode         TEXT NOT NULL,  -- redacted_only | none
    required_redactions  TEXT NOT NULL   -- JSON list
);

CREATE TABLE IF NOT EXISTS grants (
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    PRIMARY KEY (dataset_id, account_id)
);

CREATE TABLE IF NOT EXISTS requests (
    request_id             TEXT PRIMARY KEY,
    account_id             TEXT NOT NULL,
    dataset_id             TEXT NOT NULL,
    purpose                TEXT NOT NULL,
    destination            TEXT NOT NULL,
    status                 TEXT NOT NULL,
    decision               TEXT NOT NULL,
    reason_codes           TEXT NOT NULL,          -- JSON list
    dataset_revision       INTEGER,
    source_sha256          TEXT,
    preview_policy_version INTEGER,
    preview_policy_fp      TEXT,
    final_policy_version   INTEGER,
    review_revision        INTEGER,
    hidden_indices         TEXT NOT NULL DEFAULT '[]',
    redaction_counts       TEXT NOT NULL DEFAULT '{}',
    dropped_fields         TEXT NOT NULL DEFAULT '[]',
    preview_hash           TEXT,
    confirmed_sent_hash    TEXT,
    receiver_mode          TEXT NOT NULL,
    receiver_attempts      INTEGER NOT NULL DEFAULT 0,
    receiver_result        TEXT,                   -- JSON acknowledgement metadata
    created_at             TEXT NOT NULL,
    occurred_at            TEXT
);
"""

JSON_COLUMNS = {
    "reason_codes", "hidden_indices", "redaction_counts", "dropped_fields", "receiver_result",
    "allowed_purposes", "allowed_destinations", "outbound_fields", "required_redactions",
}


@dataclass(frozen=True)
class Policy:
    dataset_id: str
    policy_version: int
    allowed_accounts: tuple[str, ...]
    allowed_purposes: tuple[str, ...]
    allowed_destinations: tuple[str, ...]
    outbound_fields: dict[str, list[str]]
    sharing_mode: str
    required_redactions: tuple[str, ...]


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    display_name: str
    declared_owner: str
    source_file: str
    dataset_revision: int


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    for key in JSON_COLUMNS & out.keys():
        if out[key] is not None:
            out[key] = json.loads(out[key])
    return out


class Store:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ---- accounts -------------------------------------------------------
    def get_account(self, account_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        return dict(row) if row else None

    # ---- datasets / policies -------------------------------------------
    def get_dataset(self, dataset_id: str) -> Dataset | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)).fetchone()
        return Dataset(**dict(row)) if row else None

    def list_datasets_for(self, account_id: str) -> list[Dataset]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT d.* FROM datasets d JOIN grants g ON g.dataset_id = d.dataset_id "
                "WHERE g.account_id = ? ORDER BY d.dataset_id",
                (account_id,),
            ).fetchall()
        return [Dataset(**dict(r)) for r in rows]

    def get_policy(self, dataset_id: str) -> Policy | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM policies WHERE dataset_id = ?", (dataset_id,)).fetchone()
            if not row:
                return None
            accounts = [
                r["account_id"]
                for r in conn.execute(
                    "SELECT account_id FROM grants WHERE dataset_id = ? ORDER BY account_id", (dataset_id,)
                )
            ]
        p = _decode(row)
        return Policy(
            dataset_id=p["dataset_id"],
            policy_version=p["policy_version"],
            allowed_accounts=tuple(accounts),
            allowed_purposes=tuple(p["allowed_purposes"]),
            allowed_destinations=tuple(p["allowed_destinations"]),
            outbound_fields=p["outbound_fields"],
            sharing_mode=p["sharing_mode"],
            required_redactions=tuple(p["required_redactions"]),
        )

    # ---- owner operations (used by seed + demo_control CLI) -------------
    def bump_policy_version(self, conn: sqlite3.Connection, dataset_id: str) -> int:
        conn.execute("UPDATE policies SET policy_version = policy_version + 1 WHERE dataset_id = ?", (dataset_id,))
        return conn.execute("SELECT policy_version FROM policies WHERE dataset_id = ?", (dataset_id,)).fetchone()[0]

    # ---- requests -------------------------------------------------------
    def insert_request(self, values: dict[str, Any]) -> None:
        encoded = {k: (json.dumps(v) if k in JSON_COLUMNS and v is not None else v) for k, v in values.items()}
        cols = ", ".join(encoded)
        marks = ", ".join("?" for _ in encoded)
        with self.connect() as conn:
            conn.execute(f"INSERT INTO requests ({cols}) VALUES ({marks})", tuple(encoded.values()))

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM requests WHERE request_id = ?", (request_id,)).fetchone()
        return _decode(row) if row else None

    def update_request_if(self, request_id: str, expected: dict[str, Any], values: dict[str, Any]) -> bool:
        """Compare-and-set update. Returns True only if the row still matched ``expected``."""
        encoded = {k: (json.dumps(v) if k in JSON_COLUMNS and v is not None else v) for k, v in values.items()}
        sets = ", ".join(f"{k} = ?" for k in encoded)
        where = " AND ".join(f"{k} = ?" for k in expected)
        sql = f"UPDATE requests SET {sets} WHERE request_id = ?" + (f" AND {where}" if where else "")
        with self.connect() as conn:
            cur = conn.execute(sql, (*encoded.values(), request_id, *expected.values()))
            return cur.rowcount == 1
