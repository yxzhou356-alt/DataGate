"""Unit tests for the redaction patterns and CSV validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import transform


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Please contact emma@example.com.", "Please contact [EMAIL]."),
        ("mail first.last+tag@sub.example.co.uk now", "mail [EMAIL] now"),
        ("Call (213) 555-0142 today", "Call [PHONE] today"),
        ("Call 213-555-0142", "Call [PHONE]"),
        ("Call 213.555.0142", "Call [PHONE]"),
        ("Call +1 310 555 0199", "Call [PHONE]"),
        ("order 12345 and ticket MA-1001", "order 12345 and ticket MA-1001"),
        ("loads in over 30 seconds on Android 15", "loads in over 30 seconds on Android 15"),
    ],
)
def test_redaction_patterns(text, expected):
    out, _ = transform.redact(text, ("EMAIL", "PHONE"))
    assert out == expected


def test_only_required_types_are_redacted():
    out, counts = transform.redact("a@b.com 213-555-0142", ("EMAIL",))
    assert out == "[EMAIL] 213-555-0142" and counts == {"EMAIL": 1}


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "s.csv"
    p.write_text(text, encoding="utf-8")
    return p


@pytest.mark.parametrize(
    "text",
    [
        "ticket_id,body\nT1,hi\n",                 # missing message column
        "ticket_id,message\n,hello\n",            # empty ticket_id
        "ticket_id,message\nT1,   \n",            # empty message
        "ticket_id,message\nT1,hello,extra\n",    # ragged row
        "ticket_id,message\n",                    # no rows
        "",                                       # empty file
    ],
)
def test_invalid_sources_are_rejected_not_repaired(tmp_path, text):
    with pytest.raises(transform.SourceInvalid):
        transform.read_source(_write(tmp_path, text))


def test_quoted_fields_and_unicode_are_preserved(tmp_path):
    snap = transform.read_source(_write(tmp_path, 'ticket_id,message\nT1,"Line, with ""quotes"" — ü"\n'))
    assert snap.rows[0]["message"] == 'Line, with "quotes" — ü'
