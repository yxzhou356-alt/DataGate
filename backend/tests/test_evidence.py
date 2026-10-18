"""Security evidence report: generation, validation, safety and the read-only endpoint."""

from __future__ import annotations

import fcntl
import json
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import DEFAULT_DATA_DIR, _assert_isolated

from app import evidence, security_report
from app.config import Settings
from app.main import create_app
from app.receiver import LocalCapturingReceiver

BACKEND = Path(__file__).resolve().parent.parent
COMMIT_A = "a" * 40
COMMIT_B = "b" * 40


def _scenario(sid, result="passed", summary=None):
    title = dict((s[0], s[1]) for s in evidence.SCENARIOS)[sid]
    return {"id": sid, "title": title, "claim": "c", "result": result, "duration_seconds": 0.01,
            "tests_total": 1, "tests_passed": int(result == "passed"), "tests_failed": int(result == "failed"),
            "tests_not_run": int(result == "not_run"), "evidence": ["test_x.py::test_y"], "failure_summary": summary}


def _report(commit=COMMIT_A, scenarios=None, run_status="complete", **extra):
    data = {
        "schema_version": "1.0", "report_type": evidence.REPORT_TYPE, "generated_at": "2026-10-18T08:00:00Z",
        "git": {"commit": commit, "dirty": False},
        "suite": {"id": "backend-pytest", "command": "python -m app.security_report", "run_status": run_status,
                  "pytest_exit_code": 0, "tests_collected": 14, "tests_passed": 14, "tests_failed": 0,
                  "tests_not_run": 0, "duration_seconds": 1.0},
        "isolation": {"storage": "temp", "receiver": "injected", "runtime_db_unchanged": True},
        "totals": {"passed": 14, "failed": 0, "not_run": 0},
        "scenarios": scenarios if scenarios is not None else [_scenario(s) for s in evidence.SCENARIO_IDS],
    }
    data.update(extra)
    return data


@pytest.fixture
def report_client(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "git_state", lambda cwd=None: {"commit": COMMIT_A, "dirty": False})
    path = tmp_path / "reports" / "security-report.json"
    settings = Settings(data_dir=tmp_path / "data", report_path=path)
    return TestClient(create_app(settings, LocalCapturingReceiver())), path


def _get(client):
    r = client.get("/api/evidence/security-report")  # no Authorization header needed
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    return r.json()


# ------------------------------------------------------------- endpoint states --
def test_missing_report_is_labelled_missing(report_client):
    client, _ = report_client
    v = _get(client)
    assert v["availability"] == "missing" and v["report"] is None and v["problem"]
    assert "not a universal" in v["disclaimer"]


def test_current_and_stale_reports(report_client):
    client, path = report_client
    evidence.atomic_write_json(path, _report(COMMIT_A))
    v = _get(client)
    assert v["availability"] == "available" and v["freshness"] == "current"
    assert v["report"]["totals"] == {"passed": 14, "failed": 0, "not_run": 0}
    evidence.atomic_write_json(path, _report(COMMIT_B))
    assert _get(client)["freshness"] == "stale"


def test_unknown_commit_is_not_called_current(report_client, monkeypatch):
    client, path = report_client
    evidence.atomic_write_json(path, _report(None))
    assert _get(client)["freshness"] == "unknown"
    monkeypatch.setattr(evidence, "git_state", lambda cwd=None: {"commit": None, "dirty": None})
    evidence.atomic_write_json(path, _report(COMMIT_A))
    v = _get(client)
    assert v["freshness"] == "unknown" and v["current_commit"] is None


@pytest.mark.parametrize("raw", [
    b"{not json", b"[]", b"\xff\xfe",
    json.dumps({**_report(), "schema_version": "2.0"}).encode(),
    json.dumps({**_report(), "scenarios": []}).encode(),
    json.dumps(_report(scenarios=[_scenario("SEC-01", result="green")])).encode(),
    json.dumps(_report(run_status="finished")).encode(),
    json.dumps(_report(commit="HEAD")).encode(),
    json.dumps({k: v for k, v in _report().items() if k != "suite"}).encode(),
    b" " * (evidence.MAX_REPORT_BYTES + 1),
])
def test_malformed_or_unsupported_reports_are_invalid(report_client, raw):
    client, path = report_client
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    v = _get(client)
    assert v["availability"] == "invalid" and v["report"] is None and v["problem"].startswith("The report file")


def test_totals_are_recomputed_and_absent_scenarios_shown_as_not_run(report_client):
    client, path = report_client
    data = _report(scenarios=[_scenario("SEC-01"), _scenario("SEC-02", "failed", "test_y failed during call (AssertionError).")])
    data["totals"] = {"passed": 14, "failed": 0, "not_run": 0}  # a lying total is ignored
    evidence.atomic_write_json(path, data)
    r = _get(client)["report"]
    assert r["totals"] == {"passed": 1, "failed": 1, "not_run": 12}
    assert {s["id"] for s in r["scenarios"]} == set(evidence.SCENARIO_IDS)


def test_report_containing_pii_is_not_served(report_client):
    client, path = report_client
    data = _report(scenarios=[_scenario("SEC-01", "failed", "expected emma.lawson@example.com in body")])
    evidence.atomic_write_json(path, data)
    r = client.get("/api/evidence/security-report")
    assert r.json()["availability"] == "invalid" and "emma.lawson" not in r.text


def test_reader_never_sees_a_partial_report_during_replacement(report_client):
    client, path = report_client
    evidence.atomic_write_json(path, _report(COMMIT_A))
    stop = threading.Event()

    def writer():
        i = 0
        while not stop.is_set():
            evidence.atomic_write_json(path, _report(COMMIT_A if i % 2 else COMMIT_B))
            i += 1

    t = threading.Thread(target=writer)
    t.start()
    try:
        seen = [_get(client)["availability"] for _ in range(60)]
    finally:
        stop.set()
        t.join()
    assert set(seen) == {"available"}
    assert not list(path.parent.glob(".security-report-*.tmp"))


# ------------------------------------------------------------------ generator --
FAKE_TESTS = '''
import pytest

@pytest.mark.scenario("SEC-01")
def test_ok():
    assert True

@pytest.mark.scenario("SEC-02")
def test_fails_with_pii_in_message():
    body = {"message": "Please contact emma.lawson@example.com or 213-555-0142"}
    raise ValueError(f"unexpected body {body}")

@pytest.mark.scenario("SEC-03")
def test_skipped():
    pytest.skip("not today")

@pytest.mark.scenario("SEC-04", "SEC-05")
def test_two_scenarios():
    assert 1 + 1 == 2
'''


def _run_generator(tmp_path, tests_source, name="r.json"):
    tests_dir = tmp_path / "fake_tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_fake.py").write_text(textwrap.dedent(tests_source))
    out = tmp_path / "out" / name
    proc = subprocess.run([sys.executable, "-m", "app.security_report", "--out", str(out), "--tests", str(tests_dir)],
                          cwd=BACKEND, capture_output=True, text=True, timeout=120)
    return proc, out


def test_generator_reports_pass_fail_not_run_without_leaking_exception_text(tmp_path):
    proc, out = _run_generator(tmp_path, FAKE_TESTS)
    assert proc.returncode == 1, proc.stderr
    raw = out.read_text()
    for leaked in ("emma.lawson", "213-555", "unexpected body", "Please contact"):
        assert leaked not in raw
    report = evidence.validate_report(raw.encode())
    by_id = {s["id"]: s for s in report["scenarios"]}
    assert by_id["SEC-01"]["result"] == "passed"
    assert by_id["SEC-02"]["result"] == "failed"
    assert by_id["SEC-02"]["failure_summary"] == "test_fake.py::test_fails_with_pii_in_message failed during call (ValueError)."
    assert by_id["SEC-03"]["result"] == "not_run" and "did not run" in by_id["SEC-03"]["failure_summary"]
    assert by_id["SEC-04"]["result"] == by_id["SEC-05"]["result"] == "passed"
    assert by_id["SEC-06"]["result"] == "not_run" and by_id["SEC-06"]["failure_summary"] == "No test is mapped to this scenario."
    assert report["suite"]["tests_collected"] == 4 and report["suite"]["tests_failed"] == 1
    assert report["isolation"]["runtime_db_unchanged"] in (True, None)


def test_interrupted_run_is_labelled_and_unreached_tests_not_run(tmp_path):
    source = '''
    import pytest

    @pytest.mark.scenario("SEC-01")
    def test_first():
        raise KeyboardInterrupt

    @pytest.mark.scenario("SEC-02")
    def test_never_reached():
        assert True
    '''
    proc, out = _run_generator(tmp_path, source)
    report = evidence.validate_report(out.read_bytes())
    assert proc.returncode == 2
    assert report["suite"]["run_status"] == "interrupted"
    assert report["totals"]["passed"] == 0
    assert {s["id"]: s["result"] for s in report["scenarios"]}["SEC-02"] == "not_run"


def test_unknown_scenario_marker_marks_run_as_error(tmp_path):
    proc, out = _run_generator(tmp_path, 'import pytest\n\n@pytest.mark.scenario("SEC-99")\ndef test_x():\n    assert True\n')
    assert evidence.validate_report(out.read_bytes())["suite"]["run_status"] == "error"
    assert proc.returncode == 2


def test_simultaneous_generation_is_refused_and_keeps_old_report(tmp_path):
    out = tmp_path / "out" / "r.json"
    evidence.atomic_write_json(out, _report())
    before = out.read_bytes()
    with open(out.with_name(out.name + ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert security_report.generate(out, tmp_path / "unused") == 3
    assert out.read_bytes() == before


def test_scrub_withholds_summaries_that_contain_prohibited_content():
    report = _report(scenarios=[_scenario("SEC-01", "failed", "saw Emma Lawson in the receipt")])
    safe = security_report._scrub(report)
    assert safe is not None and "Emma" not in json.dumps(safe)
    assert security_report._scrub(_report(scenarios=[{**_scenario("SEC-01"), "title": "Bearer abc"}])) is None


def test_isolation_guard_rejects_runtime_data_dir():
    with pytest.raises(RuntimeError):
        _assert_isolated(DEFAULT_DATA_DIR)
    with pytest.raises(RuntimeError):
        _assert_isolated(DEFAULT_DATA_DIR / "sub")
