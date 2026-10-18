"""Generate the security regression evidence report from an actually executed test run.

    python -m app.security_report [--out PATH] [--tests PATH]

Runs the backend pytest suite in-process with a collector plugin, maps tests to the
scenario catalogue through ``@pytest.mark.scenario("SEC-xx")`` markers and writes a
metadata-only JSON report atomically (default: backend/var/reports/security-report.json).

Safety:
- Tests always use per-test temporary storage and injected receivers (conftest.py). This
  command additionally points DATAGATE_DATA_DIR at a throwaway directory for the run and
  records whether the runtime demo DB changed.
- Failure summaries contain only the test name, the phase and the exception class name.
  Exception messages and tracebacks (which may hold request bodies or synthetic PII) are
  never read into the report. The finished report is scanned before it is written.
- A lock file prevents simultaneous generation; readers always see a complete file.

Exit codes: 0 all scenarios passed; 1 a scenario failed; 2 incomplete (not run/interrupted);
3 another generation is running; 4 the report failed the prohibited-content check.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BACKEND_DIR, DEFAULT_DATA_DIR, report_path_from_env
from .evidence import (
    DISCLAIMER, REPORT_TYPE, SCENARIO_IDS, SCENARIOS, SCHEMA_VERSION,
    atomic_write_json, git_state, prohibited_findings,
)

SUITE_ID = "backend-pytest"
COMMAND = "python -m app.security_report"
TESTS_DIR = BACKEND_DIR / "tests"


def _safe_test_name(nodeid: str) -> str:
    """'tests/test_flow.py::test_x[param]' -> 'test_flow.py::test_x' (parameters may hold data)."""
    path, _, name = nodeid.partition("::")
    return f"{Path(path).name}::{name.split('[', 1)[0]}"


class Collector:
    """Pytest plugin recording outcomes as metadata only."""

    def __init__(self) -> None:
        self.scenarios_by_test: dict[str, tuple[str, ...]] = {}
        self.unknown_markers: set[str] = set()
        self.outcome: dict[str, str] = {}           # nodeid -> passed | failed | skipped
        self.duration: dict[str, float] = {}
        self.failure: dict[str, str] = {}           # nodeid -> safe summary
        self.exit_status: int | None = None

    def pytest_configure(self, config: Any) -> None:
        config.addinivalue_line("markers", "scenario(*ids): security evidence scenario ids (SEC-xx)")

    def pytest_collection_modifyitems(self, items: list[Any]) -> None:
        for item in items:
            ids = tuple(a for m in item.iter_markers("scenario") for a in m.args)
            self.unknown_markers.update(i for i in ids if i not in SCENARIO_IDS)
            self.scenarios_by_test[item.nodeid] = tuple(i for i in ids if i in SCENARIO_IDS)

    def pytest_runtest_makereport(self, item: Any, call: Any) -> None:
        if call.excinfo is not None and item.nodeid not in self.failure:
            # Only the exception *class* name: its message may contain request bodies or PII.
            typename = re.sub(r"[^A-Za-z0-9_.]", "", call.excinfo.typename)[:60] or "Exception"
            self.failure[item.nodeid] = f"{_safe_test_name(item.nodeid)} failed during {call.when} ({typename})."

    def pytest_runtest_logreport(self, report: Any) -> None:
        nid = report.nodeid
        self.duration[nid] = self.duration.get(nid, 0.0) + float(report.duration or 0)
        if report.failed:
            self.outcome[nid] = "failed"
        elif report.skipped and self.outcome.get(nid) != "failed":
            self.outcome[nid] = "skipped"
        elif report.when == "call" and report.passed and nid not in self.outcome:
            self.outcome[nid] = "passed"

    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
        self.exit_status = int(exitstatus)


def _file_fingerprint(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def build_report(collector: Collector, *, started: float, finished: float, run_status: str,
                 runtime_db_unchanged: bool | None, git: dict[str, Any]) -> dict[str, Any]:
    tests = collector.scenarios_by_test
    passed_tests = [t for t in tests if collector.outcome.get(t) == "passed"]
    failed_tests = [t for t in tests if collector.outcome.get(t) == "failed"]
    scenarios = []
    for sid, title, claim in SCENARIOS:
        mapped = [t for t, ids in tests.items() if sid in ids]
        ok = [t for t in mapped if collector.outcome.get(t) == "passed"]
        bad = [t for t in mapped if collector.outcome.get(t) == "failed"]
        missing = [t for t in mapped if t not in ok and t not in bad]
        if bad:
            result = "failed"
            summary = " ".join(collector.failure.get(t, f"{_safe_test_name(t)} failed.") for t in bad[:3])
        elif mapped and not missing:
            result, summary = "passed", None
        else:
            result = "not_run"
            summary = ("No test is mapped to this scenario." if not mapped
                       else f"{len(missing)} of {len(mapped)} mapped tests did not run.")
        scenarios.append({
            "id": sid, "title": title, "claim": claim, "result": result,
            "duration_seconds": round(sum(collector.duration.get(t, 0.0) for t in mapped), 4),
            "tests_total": len(mapped), "tests_passed": len(ok), "tests_failed": len(bad),
            "tests_not_run": len(missing),
            "evidence": sorted({_safe_test_name(t) for t in mapped}),
            "failure_summary": summary,
        })
    if collector.unknown_markers and run_status == "complete":
        run_status = "error"  # a typo in a marker must not silently drop evidence
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": REPORT_TYPE,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git": git,
        "suite": {
            "id": SUITE_ID,
            "command": COMMAND,
            "run_status": run_status,
            "pytest_exit_code": collector.exit_status,
            "tests_collected": len(tests),
            "tests_passed": len(passed_tests),
            "tests_failed": len(failed_tests),
            "tests_not_run": len(tests) - len(passed_tests) - len(failed_tests),
            "duration_seconds": round(finished - started, 3),
        },
        "isolation": {
            "storage": "Per-test temporary database and source copies; DATAGATE_DATA_DIR pointed at a throwaway directory.",
            "receiver": "Injected local capturing or failing test receiver; no external service.",
            "runtime_db_unchanged": runtime_db_unchanged,
        },
        "totals": {r: sum(1 for s in scenarios if s["result"] == r) for r in ("passed", "failed", "not_run")},
        "scenarios": scenarios,
        "disclaimer": DISCLAIMER,
    }


def _scrub(report: dict[str, Any]) -> dict[str, Any] | None:
    """Final defense: withhold failure summaries if anything prohibited slipped in; None if still unsafe."""
    if not prohibited_findings(json.dumps(report, ensure_ascii=False)):
        return report
    for s in report["scenarios"]:
        if s["failure_summary"]:
            s["failure_summary"] = "Summary withheld: it did not pass the prohibited-content check."
    return None if prohibited_findings(json.dumps(report, ensure_ascii=False)) else report


def generate(out: Path, tests: Path = TESTS_DIR) -> int:
    import pytest  # test-only dependency; imported here so the API never needs it

    out.parent.mkdir(parents=True, exist_ok=True)
    lock_path = out.with_name(out.name + ".lock")
    with open(lock_path, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another security report generation is already running; nothing was written.", file=sys.stderr)
            return 3

        runtime_db = DEFAULT_DATA_DIR / "datagate.sqlite3"
        before = _file_fingerprint(runtime_db)
        collector = Collector()
        started = time.time()
        old_env = os.environ.get("DATAGATE_DATA_DIR")
        with tempfile.TemporaryDirectory(prefix="datagate-evidence-") as scratch:
            # Anything that reads the environment (e.g. the owner CLI) gets throwaway storage.
            os.environ["DATAGATE_DATA_DIR"] = scratch
            try:
                code = pytest.main(
                    [str(tests), "-q", "-p", "no:cacheprovider", "--no-header", "-o", "console_output_style=classic"],
                    plugins=[collector],
                )
                run_status = {0: "complete", 1: "complete", 2: "interrupted"}.get(int(code), "error")
            except KeyboardInterrupt:
                run_status = "interrupted"
            finally:
                if old_env is None:
                    os.environ.pop("DATAGATE_DATA_DIR", None)
                else:
                    os.environ["DATAGATE_DATA_DIR"] = old_env
        after = _file_fingerprint(runtime_db)
        unchanged = None if before is None and after is None else before == after

        report = build_report(collector, started=started, finished=time.time(), run_status=run_status,
                              runtime_db_unchanged=unchanged, git=git_state())
        safe = _scrub(report)
        if safe is None:
            print("The report failed the prohibited-content check; nothing was written.", file=sys.stderr)
            return 4
        atomic_write_json(out, safe)

    totals = safe["totals"]
    print(f"Security report written to {out}: {totals['passed']} passed, {totals['failed']} failed, "
          f"{totals['not_run']} not run ({safe['suite']['run_status']}).")
    if totals["failed"]:
        return 1
    if totals["not_run"] or safe["suite"]["run_status"] != "complete":
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=COMMAND, description="Generate the DataGate security evidence report.")
    parser.add_argument("--out", type=Path, default=report_path_from_env(),
                        help="report path (default: DATAGATE_REPORT_PATH or backend/var/reports/security-report.json)")
    parser.add_argument("--tests", type=Path, default=TESTS_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    return generate(args.out.resolve(), args.tests.resolve())


if __name__ == "__main__":
    sys.exit(main())
