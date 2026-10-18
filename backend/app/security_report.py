"""Fixed isolated test runner. HTTP only reads sanitized reports; it cannot run tests."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
CONTROLS = {
    "tenant_isolation": ("Cross-customer access is blocked", ("cross_account", "creator", "history_is_scoped", "raw_access")),
    "revocation": ("Revocation is enforced at Send", ("revocation", "raw_grant_changes")),
    "policy": ("Forbidden purposes and destinations are blocked", ("purpose", "destination", "sharing_none", "unsupported", "unknown_required")),
    "redaction": ("Mandatory redactions cannot be bypassed", ("mandatory", "manual", "pseudonym", "pipeline", "model_unavailable")),
    "single_dispatch": ("Duplicate and concurrent Send call the receiver once", ("duplicate_send", "concurrent_sends")),
    "metadata_privacy": ("Receipts and audit exports contain metadata only", ("receipt_is_metadata", "audit", "timeline")),
}


def source_fingerprint():
    digest, paths = hashlib.sha256(), []
    for directory in ("backend/app", "backend/tests", "backend/fixtures", "backend/evaluation", "frontend/src"):
        paths.extend(p for p in (ROOT / directory).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix != ".pyc"
                     and p.name != "heldout-results.json")
    paths.extend(ROOT / name for name in ("backend/requirements.txt", "backend/requirements.lock",
                 "frontend/package.json", "frontend/package-lock.json", "frontend/vite.config.ts"))
    for path in sorted(set(paths)):
        if path.exists():
            digest.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def read_report(data_dir):
    current = source_fingerprint()
    for path in (data_dir / "security-report.json", ROOT / "backend/reports/security-report.json"):
        try:
            report = json.loads(path.read_text())
            if report.get("schema_version") != "1.1" or not isinstance(report.get("tests"), list):
                continue
        except (OSError, ValueError, TypeError):
            continue
        return {"available": True, "stale": report.get("source_fingerprint") != current,
                "source_fingerprint": current, "report": report}
    return {"available": False, "stale": False, "source_fingerprint": current, "report": None}


def _git(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def main(argv=None):
    import argparse
    from .config import settings_from_env
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    output = args.output or settings_from_env().data_dir / "security-report.json"
    initial, started = source_fingerprint(), time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="datagate-checks-") as directory:
        junit = Path(directory) / "results.xml"
        env = {**os.environ, "DATAGATE_DATA_DIR": str(Path(directory) / "runtime")}
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests", "--junitxml", str(junit)],
                                cwd=ROOT / "backend", env=env, capture_output=True, text=True)
        tests = []
        if junit.exists():
            for case in ET.parse(junit).getroot().iter("testcase"):
                status = "failed" if case.find("failure") is not None or case.find("error") is not None else (
                         "skipped" if case.find("skipped") is not None else "passed")
                # Parameter IDs may contain submitted values; export function names only.
                identifier = case.attrib.get("classname", "") + "::" + case.attrib["name"].split("[")[0]
                n = sum(t["id"].split("#")[0] == identifier for t in tests) + 1
                tests.append({"id": identifier + f"#{n}", "status": status,
                              "duration_seconds": float(case.attrib.get("time", 0))})
        controls = []
        for control_id, (title, fragments) in CONTROLS.items():
            matched = [t for t in tests if any(f in t["id"] for f in fragments)]
            status = "failed" if any(t["status"] == "failed" for t in matched) else (
                "passed" if matched and all(t["status"] == "passed" for t in matched) else "not_run")
            controls.append({"id": control_id, "title": title, "status": status, "tests": len(matched)})
        report = {"schema_version": "1.1", "generated_at": datetime.now(timezone.utc).isoformat(),
                  "source_revision": _git("rev-parse", "HEAD"), "working_tree_dirty": bool(_git("status", "--porcelain")),
                  "source_fingerprint": initial, "total": len(tests),
                  **{key: sum(t["status"] == key for t in tests) for key in ("passed", "failed", "skipped")},
                  "duration_seconds": round(time.perf_counter() - started, 3),
                  "receiver_mode": "local_demo", "controls": controls, "tests": tests}
        if source_fingerprint() != initial:
            print("Source changed during tests; no report published. Run again.", file=sys.stderr)
            return 2
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(output)
        print(json.dumps({k: report[k] for k in ("total", "passed", "failed", "skipped", "source_fingerprint")}))
        return 0 if result.returncode == 0 and tests and all(c["status"] == "passed" for c in controls) else 1


if __name__ == "__main__":
    raise SystemExit(main())
