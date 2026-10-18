"""Owner setup: seed demo accounts, datasets and owner policies.

Usage:
    python -m app.seed            # seed if the runtime DB is empty
    python -m app.seed --reset    # wipe runtime DB + runtime sources, then seed
"""

from __future__ import annotations

import argparse
import json
import shutil

from .config import Settings, settings_from_env
from .storage import Store

ACCOUNTS = [
    ("analyst_a", "MapleCo analyst"),
    ("analyst_b", "RiverCo analyst"),
]

DATASETS = [
    # dataset_id, display_name, declared_owner, source file, allowed account
    ("feedback_a", "MapleCo feedback", "MapleCo support", "feedback_a.csv", "analyst_a"),
    ("feedback_b", "RiverCo feedback", "RiverCo support", "feedback_b.csv", "analyst_b"),
]

DEFAULT_POLICY = {
    "allowed_purposes": ["feedback_summary"],
    "allowed_destinations": ["demo_receiver"],
    "outbound_fields": {"feedback_summary": ["message"]},
    "sharing_mode": "redacted_only",
    "required_redactions": ["EMAIL", "PHONE"],
}


def seed(settings: Settings, reset: bool = False) -> Store:
    if reset:
        if settings.db_path.exists():
            settings.db_path.unlink()
        if settings.sources_dir.exists():
            shutil.rmtree(settings.sources_dir)
    settings.sources_dir.mkdir(parents=True, exist_ok=True)
    store = Store(settings.db_path)
    with store.connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]:
            return store  # already seeded; never overwrite owner edits
        conn.execute("BEGIN")
        conn.executemany("INSERT INTO accounts VALUES (?, ?)", ACCOUNTS)
        for dataset_id, name, owner, source_file, account in DATASETS:
            target = settings.sources_dir / source_file
            if not target.exists():
                shutil.copyfile(settings.fixtures_dir / source_file, target)
            conn.execute("INSERT INTO datasets VALUES (?, ?, ?, ?, 1)", (dataset_id, name, owner, source_file))
            conn.execute(
                "INSERT INTO policies VALUES (?, 1, ?, ?, ?, ?, ?)",
                (
                    dataset_id,
                    json.dumps(DEFAULT_POLICY["allowed_purposes"]),
                    json.dumps(DEFAULT_POLICY["allowed_destinations"]),
                    json.dumps(DEFAULT_POLICY["outbound_fields"]),
                    DEFAULT_POLICY["sharing_mode"],
                    json.dumps(DEFAULT_POLICY["required_redactions"]),
                ),
            )
            conn.execute("INSERT INTO grants VALUES (?, ?)", (dataset_id, account))
        conn.execute("COMMIT")
    return store


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the DataGate demo database.")
    parser.add_argument("--reset", action="store_true", help="delete runtime DB and sources first")
    args = parser.parse_args()
    settings = settings_from_env()
    seed(settings, reset=args.reset)
    print(f"Seeded {settings.db_path}")


if __name__ == "__main__":
    main()
