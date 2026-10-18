"""Security regression evidence: scenario catalogue, report validation, safe I/O.

The report is produced by ``python -m app.security_report`` from an actually executed
pytest run (isolated temporary storage, injected receivers). This module only holds the
shared pieces: what the scenarios are, how a report file is validated, how it is written
atomically, and how it is scanned for prohibited content. It never runs tests.

Passing fixture tests is evidence that these implemented cases behave as described. It is
not a universal security or privacy guarantee.
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import BACKEND_DIR, DEFAULT_REPORT_PATH, FIXTURES_DIR

SCHEMA_VERSION = "1.0"
REPORT_TYPE = "datagate-security-regression"
RESULTS = ("passed", "failed", "not_run")
RUN_STATUSES = ("complete", "interrupted", "error")
MAX_REPORT_BYTES = 256 * 1024

DISCLAIMER = (
    "Passing these fixture-based checks is evidence that the listed cases are implemented and "
    "behaved as described in this run. It is not a universal security or privacy guarantee."
)

# (id, title, what a pass demonstrates). Tests opt in with @pytest.mark.scenario("SEC-xx").
SCENARIOS: tuple[tuple[str, str, str], ...] = (
    ("SEC-01", "Authorized analyst can preview their own dataset",
     "A permitted analyst gets a real transformed preview and only their own dataset is listed."),
    ("SEC-02", "Cross-account dataset access is blocked",
     "Another analyst cannot list or preview the dataset; identity comes from the token, not the body."),
    ("SEC-03", "Cross-account draft, review and receipt access is blocked",
     "Another analyst cannot review, send or read the receipt of someone else's request."),
    ("SEC-04", "Forbidden purpose makes zero receiver calls",
     "A model_training request is blocked at preview and the receiver is never invoked."),
    ("SEC-05", "Forbidden destination makes zero receiver calls",
     "An unapproved destination or a caller-supplied URL is refused with no receiver call."),
    ("SEC-06", "sharing_mode=none makes zero receiver calls",
     "A no-sharing policy blocks even redacted data, at preview and at send."),
    ("SEC-07", "Mandatory redaction cannot be bypassed by body tampering",
     "Unredact/allow fields and replacement payloads are rejected; custom spans cannot cut owner placeholders."),
    ("SEC-08", "Revocation after preview blocks Send with zero calls",
     "Access revoked between preview and send blocks the request; review is blocked too."),
    ("SEC-09", "Source change invalidates approval",
     "A changed source (with or without a revision bump) makes the approval stale; nothing is sent."),
    ("SEC-10", "Policy change invalidates approval",
     "A policy version bump or an out-of-band policy edit makes the approval stale; nothing is sent."),
    ("SEC-11", "Stale review revision or payload hash is rejected",
     "Approvals bound to an older review revision or hash are refused without a receiver call."),
    ("SEC-12", "Repeated or concurrent Send invokes the receiver exactly once",
     "A duplicate Send and six concurrent Sends produce one receiver invocation."),
    ("SEC-13", "Receiver failure is reported honestly",
     "A failing receiver yields send_failed with one recorded attempt, no confirmed hash and no resend."),
    ("SEC-14", "Receipts contain no prohibited content",
     "Receipts hold metadata only: no messages, identifiers, prompts, tokens or file names; creator-only."),
)
SCENARIO_IDS = tuple(s[0] for s in SCENARIOS)

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<![\w+])(?:\+?1[\s.\-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.\-])\d{3}[\s.\-]?\d{4}(?!\w)")
_SECRETISH = re.compile(r"(?i)\bbearer\s+\S+|authorization|api[_-]?key|password|secret")


# --------------------------------------------------------------------------- #
# Prohibited-content scan
# --------------------------------------------------------------------------- #
def _fixture_values(fixtures_dir: Path = FIXTURES_DIR) -> set[str]:
    """Synthetic customer values and message fragments that must never appear in a report."""
    values: set[str] = set()
    for path in sorted(fixtures_dir.glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                for column, value in row.items():
                    if column in ("plan_tier", "product_area") or not value:
                        continue  # generic category words, not identifying
                    value = value.strip()
                    if column == "message":
                        values.update(w for w in re.split(r"[.!?]", value) if len(w.strip()) >= 12)
                    elif len(value) >= 3:
                        values.add(value)
    return {v.strip() for v in values if v.strip()}


def prohibited_findings(text: str, fixtures_dir: Path = FIXTURES_DIR) -> list[str]:
    """Kinds of prohibited content found in ``text`` (kinds only, never the matched values)."""
    found = []
    if _EMAIL.search(text):
        found.append("email-like value")
    if _PHONE.search(text):
        found.append("phone-like value")
    if _SECRETISH.search(text):
        found.append("credential-like text")
    if any(v in text for v in _fixture_values(fixtures_dir)):
        found.append("fixture customer value or message text")
    return found


# --------------------------------------------------------------------------- #
# Git metadata
# --------------------------------------------------------------------------- #
def git_state(cwd: Path = BACKEND_DIR) -> dict[str, Any]:
    """Current commit and whether tracked files differ from it. None when unavailable."""
    def run(*args: str) -> str | None:
        try:
            out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    commit = run("rev-parse", "HEAD")
    if commit is None or not re.fullmatch(r"[0-9a-f]{40}", commit):
        return {"commit": None, "dirty": None}
    status = run("status", "--porcelain", "--untracked-files=no")
    return {"commit": commit, "dirty": None if status is None else bool(status)}


# --------------------------------------------------------------------------- #
# Atomic write
# --------------------------------------------------------------------------- #
def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write to a temp file in the same directory, fsync, then os.replace.

    Readers see either the complete old report or the complete new one, never a partial file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=".security-report-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- #
# Validation (used by the read-only endpoint)
# --------------------------------------------------------------------------- #
class ReportInvalid(Exception):
    """The report file is malformed or uses an unsupported schema. Message is safe to show."""


def _req(obj: dict, key: str, kinds: type | tuple[type, ...], nullable: bool = False) -> Any:
    if key not in obj:
        raise ReportInvalid(f"missing field '{key}'")
    value = obj[key]
    if value is None and nullable:
        return None
    if isinstance(value, bool) and bool not in (kinds if isinstance(kinds, tuple) else (kinds,)):
        raise ReportInvalid(f"field '{key}' has the wrong type")
    if not isinstance(value, kinds):
        raise ReportInvalid(f"field '{key}' has the wrong type")
    return value


def validate_report(raw: bytes) -> dict[str, Any]:
    """Parse and validate a report; returns a normalized copy with totals recomputed."""
    if len(raw) > MAX_REPORT_BYTES:
        raise ReportInvalid("report file is too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ReportInvalid("report file is not valid JSON")
    if not isinstance(data, dict):
        raise ReportInvalid("report is not a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION or data.get("report_type") != REPORT_TYPE:
        raise ReportInvalid("unsupported report schema")

    generated_at = _req(data, "generated_at", str)
    git = _req(data, "git", dict)
    suite = _req(data, "suite", dict)
    isolation = _req(data, "isolation", dict)
    commit = _req(git, "commit", str, nullable=True)
    if commit is not None and not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReportInvalid("field 'commit' is not a commit id")
    run_status = _req(suite, "run_status", str)
    if run_status not in RUN_STATUSES:
        raise ReportInvalid("unknown run status")

    scenarios = _req(data, "scenarios", list)
    out_scenarios = []
    seen = set()
    for item in scenarios:
        if not isinstance(item, dict):
            raise ReportInvalid("scenario entry is not an object")
        sid = _req(item, "id", str)
        result = _req(item, "result", str)
        if result not in RESULTS:
            raise ReportInvalid("unknown scenario result")
        if sid in seen:
            raise ReportInvalid("duplicate scenario id")
        seen.add(sid)
        out_scenarios.append({
            "id": sid,
            "title": _req(item, "title", str),
            "claim": _req(item, "claim", str),
            "result": result,
            "duration_seconds": _req(item, "duration_seconds", (int, float)),
            "tests_total": _req(item, "tests_total", int),
            "tests_passed": _req(item, "tests_passed", int),
            "tests_failed": _req(item, "tests_failed", int),
            "tests_not_run": _req(item, "tests_not_run", int),
            "evidence": [e for e in _req(item, "evidence", list) if isinstance(e, str)],
            "failure_summary": _req(item, "failure_summary", str, nullable=True),
        })
    if not out_scenarios:
        raise ReportInvalid("report contains no scenarios")
    # Every catalogue scenario must be accounted for; a missing one is shown as not run.
    for sid, title, claim in SCENARIOS:
        if sid not in seen:
            out_scenarios.append({
                "id": sid, "title": title, "claim": claim, "result": "not_run", "duration_seconds": 0,
                "tests_total": 0, "tests_passed": 0, "tests_failed": 0, "tests_not_run": 0, "evidence": [],
                "failure_summary": "Not present in this report.",
            })

    totals = {r: sum(1 for s in out_scenarios if s["result"] == r) for r in RESULTS}
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": REPORT_TYPE,
        "generated_at": generated_at,
        "git": {"commit": commit, "dirty": _req(git, "dirty", bool, nullable=True)},
        "suite": {
            "id": _req(suite, "id", str),
            "command": _req(suite, "command", str),
            "run_status": run_status,
            "pytest_exit_code": _req(suite, "pytest_exit_code", int, nullable=True),
            "tests_collected": _req(suite, "tests_collected", int),
            "tests_passed": _req(suite, "tests_passed", int),
            "tests_failed": _req(suite, "tests_failed", int),
            "tests_not_run": _req(suite, "tests_not_run", int),
            "duration_seconds": _req(suite, "duration_seconds", (int, float)),
        },
        "isolation": {
            "storage": _req(isolation, "storage", str),
            "receiver": _req(isolation, "receiver", str),
            "runtime_db_unchanged": _req(isolation, "runtime_db_unchanged", bool, nullable=True),
        },
        "totals": totals,
        "scenarios": out_scenarios,
        "disclaimer": DISCLAIMER,
    }


def read_report_view(path: Path) -> dict[str, Any]:
    """The read-only endpoint payload. Reads the file once; never runs tests."""
    current = git_state()
    view: dict[str, Any] = {
        "availability": "missing",
        "problem": None,
        "current_commit": current["commit"],
        "current_dirty": current["dirty"],
        "freshness": "unknown",
        "report": None,
        "disclaimer": DISCLAIMER,
    }
    try:
        raw = path.read_bytes()  # one read: an atomic replace yields old or new, never a mix
    except FileNotFoundError:
        view["problem"] = "No report has been generated yet."
        return view
    except OSError:
        view["problem"] = "The report file could not be read."
        return view
    try:
        report = validate_report(raw)
    except ReportInvalid as exc:
        view.update(availability="invalid", problem=f"The report file is unusable: {exc}.")
        return view
    if prohibited_findings(json.dumps(report, ensure_ascii=False)):
        view.update(availability="invalid", problem="The report file failed the prohibited-content check and is not shown.")
        return view
    view["availability"] = "available"
    view["report"] = report
    if report["git"]["commit"] and current["commit"]:
        view["freshness"] = "current" if report["git"]["commit"] == current["commit"] else "stale"
    return view
