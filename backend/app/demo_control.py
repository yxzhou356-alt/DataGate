"""Local owner/operator CLI for live demonstrations.

This edits the shared runtime SQLite DB (and runtime source copies). It has
local operator authority and is NOT an analyst-facing API. The running backend
sees changes at its next protected operation.

    python -m app.demo_control revoke --account analyst_a --dataset feedback_a
    python -m app.demo_control grant  --account analyst_a --dataset feedback_a
    python -m app.demo_control sharing --dataset feedback_a --mode none
    python -m app.demo_control bump-policy --dataset feedback_a
    python -m app.demo_control edit-source --dataset feedback_a
    python -m app.demo_control redactions --dataset feedback_a --types EMAIL,PHONE,PERSON --person-style numbered
    python -m app.demo_control add-named-row --dataset feedback_a
    python -m app.demo_control status
"""

from __future__ import annotations

import argparse
import json

from .config import settings_from_env
from .policy import MANDATORY_BASELINE, SUPPORTED_REDACTIONS
from .seed import seed

# Synthetic names only (see the PERSON evaluation); appended for demos by add-named-row.
NAMED_MESSAGE = ("Ana asked Liam O'Brien to check the export. Liam O'Brien said Ana should "
                 "email ana.souza@example.com; Dr. Patel will follow up with Ana.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.demo_control")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("revoke", "grant"):
        p = sub.add_parser(name)
        p.add_argument("--account", required=True)
        p.add_argument("--dataset", required=True)
    p = sub.add_parser("sharing", help="set sharing_mode (redacted_only | none)")
    p.add_argument("--dataset", required=True)
    p.add_argument("--mode", required=True, choices=["redacted_only", "none"])
    p = sub.add_parser("bump-policy", help="increment policy_version without other changes")
    p.add_argument("--dataset", required=True)
    p = sub.add_parser("edit-source", help="append one synthetic row to the runtime source and bump its revision")
    p.add_argument("--dataset", required=True)
    p = sub.add_parser("redactions", help="set required redaction types (EMAIL and PHONE always stay) and PERSON style")
    p.add_argument("--dataset", required=True)
    p.add_argument("--types", required=True, help="comma-separated, e.g. EMAIL,PHONE,PERSON")
    p.add_argument("--person-style", choices=["generic", "numbered"], default="generic")
    p = sub.add_parser("add-named-row", help="append one synthetic row that mentions people and bump the revision")
    p.add_argument("--dataset", required=True)
    sub.add_parser("status")
    args = parser.parse_args(argv)

    settings = settings_from_env()
    store = seed(settings)

    with store.connect() as conn:
        if args.cmd == "status":
            for row in conn.execute("SELECT * FROM datasets ORDER BY dataset_id"):
                pol = store.get_policy(row["dataset_id"])
                print(json.dumps({
                    "dataset_id": row["dataset_id"], "dataset_revision": row["dataset_revision"],
                    "policy_version": pol.policy_version, "sharing_mode": pol.sharing_mode,
                    "allowed_accounts": list(pol.allowed_accounts),
                    "required_redactions": list(pol.required_redactions), "person_style": pol.person_style,
                }))
            return

        ds = conn.execute("SELECT * FROM datasets WHERE dataset_id = ?", (args.dataset,)).fetchone()
        if ds is None:
            raise SystemExit(f"unknown dataset {args.dataset}")
        conn.execute("BEGIN IMMEDIATE")
        if args.cmd in ("revoke", "grant"):
            if conn.execute("SELECT 1 FROM accounts WHERE account_id = ?", (args.account,)).fetchone() is None:
                conn.execute("ROLLBACK")
                raise SystemExit(f"unknown account {args.account}")
            if args.cmd == "revoke":
                conn.execute("DELETE FROM grants WHERE dataset_id = ? AND account_id = ?", (args.dataset, args.account))
            else:
                conn.execute("INSERT OR IGNORE INTO grants VALUES (?, ?)", (args.dataset, args.account))
            version = store.bump_policy_version(conn, args.dataset)
        elif args.cmd == "sharing":
            conn.execute("UPDATE policies SET sharing_mode = ? WHERE dataset_id = ?", (args.mode, args.dataset))
            version = store.bump_policy_version(conn, args.dataset)
        elif args.cmd == "bump-policy":
            version = store.bump_policy_version(conn, args.dataset)
        elif args.cmd == "redactions":
            types = [t.strip().upper() for t in args.types.split(",") if t.strip()]
            unknown = [t for t in types if t not in SUPPORTED_REDACTIONS]
            if unknown or not set(MANDATORY_BASELINE) <= set(types):
                conn.execute("ROLLBACK")
                raise SystemExit(f"types must be from {', '.join(SUPPORTED_REDACTIONS)} and include EMAIL and PHONE")
            ordered = [t for t in SUPPORTED_REDACTIONS if t in types]
            conn.execute("UPDATE policies SET required_redactions = ?, person_style = ? WHERE dataset_id = ?",
                         (json.dumps(ordered), args.person_style, args.dataset))
            version = store.bump_policy_version(conn, args.dataset)
        elif args.cmd == "add-named-row":
            path = settings.sources_dir / ds["source_file"]
            n = sum(1 for _ in path.open(encoding="utf-8")) - 1
            prefix = "MA" if args.dataset.endswith("_a") else "RC"
            with path.open("a", encoding="utf-8", newline="") as fh:
                fh.write(f'{prefix}-8{n:03d},Ana Souza,ana.souza@example.com,000-555-0101,pro,0,export,"{NAMED_MESSAGE}"\n')
            conn.execute("UPDATE datasets SET dataset_revision = dataset_revision + 1 WHERE dataset_id = ?", (args.dataset,))
            version = conn.execute("SELECT policy_version FROM policies WHERE dataset_id = ?", (args.dataset,)).fetchone()[0]
        elif args.cmd == "edit-source":
            path = settings.sources_dir / ds["source_file"]
            n = sum(1 for _ in path.open(encoding="utf-8")) - 1
            prefix = "MA" if args.dataset.endswith("_a") else "RC"
            with path.open("a", encoding="utf-8", newline="") as fh:
                fh.write(f"{prefix}-9{n:03d},Demo Customer,demo{n}@example.com,000-555-0100,basic,0,other,"
                         f"New synthetic ticket {n}: the export button is greyed out.\n")
            conn.execute("UPDATE datasets SET dataset_revision = dataset_revision + 1 WHERE dataset_id = ?", (args.dataset,))
            version = conn.execute("SELECT policy_version FROM policies WHERE dataset_id = ?", (args.dataset,)).fetchone()[0]
        conn.execute("COMMIT")
    print(f"{args.cmd}: dataset={args.dataset} policy_version={version}")


if __name__ == "__main__":
    main()
