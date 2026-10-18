"""Shared helpers for PERSON detection / pseudonymization tests (isolated storage only)."""

from __future__ import annotations

import csv
import io
import sqlite3

from app.detectors import DetectedSpan, LexiconPersonDetector

HEADER = ["ticket_id", "customer_name", "email", "phone", "plan_tier", "account_value", "product_area", "message"]


def write_source(settings, messages, dataset="feedback_a"):
    """Replace the runtime source copy (never the committed fixture) with synthetic messages."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(HEADER)
    for i, m in enumerate(messages):
        w.writerow([f"T-{i:03d}", "Synthetic Person", f"user{i}@example.com", "000-555-0100", "pro", "0", "x", m])
    (settings.sources_dir / f"{dataset}.csv").write_text(buf.getvalue(), encoding="utf-8")


def require_person(settings, style="generic", dataset="feedback_a"):
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            "UPDATE policies SET required_redactions = '[\"EMAIL\", \"PHONE\", \"PERSON\"]', person_style = ?, "
            "policy_version = policy_version + 1 WHERE dataset_id = ?", (style, dataset))


class StubDetector:
    """Returns fixed spans (or raises) to exercise validation and overlap rules."""

    def __init__(self, spans=None, exc=None, version="stub-1"):
        self.spans, self.exc, self.version = spans or [], exc, version
        self.calls = 0

    def detect(self, text):
        self.calls += 1
        if self.exc:
            raise self.exc
        return list(self.spans)


class FlakyDetector:
    """Different output on every call: a nondeterministic detector."""

    version = "flaky-1"

    def __init__(self):
        self.inner = LexiconPersonDetector()
        self.n = 0

    def detect(self, text):
        self.n += 1
        spans = self.inner.detect(text)
        return spans if self.n % 2 else spans[:1]


def span(start, end, type_="PERSON", confidence=None):
    return DetectedSpan(start, end, type_, confidence)
