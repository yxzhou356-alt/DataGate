"""Structured identifiers: SSN, CREDIT_CARD, ADDRESS, IP_ADDRESS, DOB (owner-required, rule-based)."""

from __future__ import annotations

import sqlite3

import pytest

from conftest import preview, send
from person_support import write_source

from app import evidence, transform
from app.pii_patterns import find_addresses, find_credit_cards, find_dobs, find_ip_addresses, find_ssn, luhn_valid
from app.policy import SUPPORTED_REDACTIONS

ALL = tuple(t for t in SUPPORTED_REDACTIONS if t != "PERSON")


def _hits(fn, text):
    return [text[s:e] for s, e in fn(text)]


# ------------------------------------------------------------------------- SSN --
@pytest.mark.parametrize("text,expected", [
    ("SSN 900-12-3456 was rejected", ["900-12-3456"]),            # context: ITIN-style 9xx still redacted
    ("my social security number is 123 45 6789", ["123 45 6789"]),
    ("ssn: 123456789", ["123456789"]),
    ("my 123-45-6789 was rejected", ["123-45-6789"]),               # dashed + issuable, no label
    ("Order 123456789 shipped; ticket #987654321.", []),            # bare nine digits, no SSN cue
    ("Order 123-45-6789 is wrong", []),                             # labelled reference number
    ("national ID 900123456", []),
    ("value 666-12-3456 and 123-00-4567 and 123-45-0000", []),     # never-issued shapes, no cue
    ("SSN 000-12-3456", []),
    ("phone 213-555-0142", []),
])
def test_ssn(text, expected):
    assert _hits(find_ssn, text) == expected


# ----------------------------------------------------------------- credit card --
@pytest.mark.parametrize("text,expected", [
    ("card 4242 4242 4242 4242, bank 000046281935", ["4242 4242 4242 4242"]),
    ("4111-1111-1111-1111", ["4111-1111-1111-1111"]),               # grouped: no context needed
    ("Amex 3782 822463 10005 was charged", ["3782 822463 10005"]),
    ("charged card 4111111111111111 twice", ["4111111111111111"]),  # ungrouped + payment context
    ("invoice 4111111111111111 total", []),                         # ungrouped, no payment context
    ("card 4111 1111 1111 1112", []),                                # Luhn fails
    ("card 1234 5678 9012 3452", []),                                # Luhn ok, no issuer prefix
    ("tracking 9400 1000 0000 0000 0000 00", []),
])
def test_credit_cards(text, expected):
    assert _hits(find_credit_cards, text) == expected


def test_luhn():
    assert luhn_valid("4111111111111111") and luhn_valid("378282246310005") and not luhn_valid("4111111111111112")


# --------------------------------------------------------------------- address --
@pytest.mark.parametrize("text,expected", [
    ("wrong address: 28 Cedar Road, Irvine CA 92602.", ["28 Cedar Road, Irvine CA 92602"]),
    ("invoices miss Apt 4B, 184 Willow Lane, Pasadena CA 91101.", ["Apt 4B, 184 Willow Lane, Pasadena CA 91101"]),
    ("ship to 1600 Pennsylvania Avenue NW, Washington, DC 20500", ["1600 Pennsylvania Avenue NW, Washington, DC 20500"]),
    ("at 350 5th Ave, Suite 3300 today", ["350 5th Ave, Suite 3300"]),
    ("mail PO Box 4471 please", ["PO Box 4471"]),
    ("We moved to Los Angeles last year.", []),
    ("Office in Los Angeles, CA 90012.", []),                       # city/state/ZIP alone is not a street address
    ("I paid 20 dollars on Main St yesterday", []),
    ("Main Street is closed", []),
    ("3 Way adapter broke", []),
])
def test_addresses(text, expected):
    assert _hits(find_addresses, text) == expected


# ---------------------------------------------------------------------- IP --
@pytest.mark.parametrize("text,expected", [
    ("uploads crawl at 192.0.2.42, user x", ["192.0.2.42"]),
    ("router 10.0.0.1:8080 drops", ["10.0.0.1"]),
    ("sync drops on 2001:db8::84. ok", ["2001:db8::84"]),
    ("loopback ::1 and fe80::1%en0", ["::1", "fe80::1%en0"]),
    ("App version 1.2.3.4 crashes; build 10.0.0.1 too", []),
    ("bad 999.1.1.1 and 12:30:45 and aa:bb:cc:dd:ee:ff and ::", []),
])
def test_ip_addresses(text, expected):
    assert _hits(find_ip_addresses, text) == expected


# ---------------------------------------------------------------------- DOB --
@pytest.mark.parametrize("text,expected", [
    ("verifying SSN and DOB 1990-02-14 took days", ["1990-02-14"]),
    ("Date of birth: March 5, 1990.", ["March 5, 1990"]),
    ("born on 5 March 1990", ["5 March 1990"]),
    ("birthday is 04/12/88", ["04/12/88"]),
    ("D.O.B. 14.02.1990", ["14.02.1990"]),
    ("Bought on 2024-03-14 and it broke 03/15/2024.", []),          # dates without a birth cue
    ("DOB 02/30/1990", []),                                         # not a real date
    ("born in 1990", []),                                           # a year alone
    ("DOB 2999-01-01", []),                                         # future
])
def test_dobs(text, expected):
    assert _hits(find_dobs, text) == expected


# -------------------------------------------------------------- precedence --
def test_precedence_masks_lower_rules_and_keeps_context_words():
    text = ("SSN 900-12-3456, card 4242 4242 4242 4242, IP 192.0.2.42, call 213-555-0142, "
            "DOB 1990-02-14, ship to 28 Cedar Road, Irvine CA 92602, mail a@b.co")
    out, counts = transform.redact(text, ALL)
    assert out == ("SSN [SSN], card [CREDIT_CARD], IP [IP_ADDRESS], call [PHONE], "
                   "DOB [DOB], ship to [ADDRESS], mail [EMAIL]")
    assert counts == {t: 1 for t in ALL}


def test_only_owner_required_types_run():
    text = "SSN 900-12-3456 and card 4242 4242 4242 4242"
    assert transform.redact(text, ("EMAIL", "PHONE"))[0] == text
    assert transform.redact(text, ("EMAIL", "PHONE", "SSN"))[0] == "SSN [SSN] and card 4242 4242 4242 4242"


def test_higher_priority_match_is_never_split_by_a_lower_one():
    # A 10-digit card fragment must not be re-read as a phone once the card is masked.
    out, counts = transform.redact("card 4111 1111 1111 1111", ("CREDIT_CARD", "PHONE"))
    assert out == "card [CREDIT_CARD]" and counts == {"CREDIT_CARD": 1, "PHONE": 0}


def test_source_literals_for_new_tokens_are_escaped():
    out, _ = transform.redact("Customer typed [SSN] and [credit_card] and [IP_ADDRESS]", ALL)
    assert out == "Customer typed (SSN) and (credit_card) and (IP_ADDRESS)"


# ------------------------------------------------------------- end to end --
def _require(settings, types):
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute("UPDATE policies SET required_redactions = ?, policy_version = policy_version + 1 "
                     "WHERE dataset_id = 'feedback_a'", (str(list(types)).replace("'", '"'),))


def test_fixtures_with_all_structured_types(client, a, settings, receiver):
    _require(settings, ALL)
    p = preview(client, a).json()
    assert p["redaction_counts"] == {"EMAIL": 3, "SSN": 1, "CREDIT_CARD": 1, "IP_ADDRESS": 2,
                                     "PHONE": 3, "DOB": 1, "ADDRESS": 2}
    joined = " ".join(p["outbound_payload"]["messages"])
    for raw in ("900-12-3456", "4242 4242 4242 4242", "192.0.2.42", "2001:db8::42", "1990-02-14",
                "28 Cedar Road", "184 Willow Lane"):
        assert raw not in joined
    # Not in scope: national ID, bank account and passport numbers stay for analyst review.
    assert "900123456" in joined and "000046281935" in joined and "X80001427" in joined
    assert send(client, a, p).status_code == 200
    receipt = client.get(f"/api/requests/{p['request_id']}/receipt", headers=a).text
    for raw in ("900-12-3456", "4242", "192.0.2.42", "Cedar", "1990-02-14"):
        assert raw not in receipt


def test_custom_redaction_cannot_cut_a_structured_placeholder(client, a, settings):
    write_source(settings, ["Refund card 4242 4242 4242 4242 please"])
    _require(settings, ("EMAIL", "PHONE", "CREDIT_CARD"))
    p = preview(client, a).json()
    msg = p["outbound_payload"]["messages"][0]
    at = msg.index("[CREDIT_CARD]")
    r = client.patch(f"/api/requests/{p['request_id']}/review", headers=a, json={
        "expected_review_revision": 1, "hide_message_indices": [],
        "custom_redactions": [{"message_index": 0, "start": at + 2, "end": at + 8}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REVIEW"
    ok = client.patch(f"/api/requests/{p['request_id']}/review", headers=a, json={
        "expected_review_revision": 1, "hide_message_indices": [],
        "custom_redactions": [{"message_index": 0, "start": at - 5, "end": at + 13}]})
    assert ok.status_code == 200


def test_transform_version_change_invalidates_old_approvals(client, a, receiver, monkeypatch):
    p = preview(client, a).json()
    monkeypatch.setattr(transform, "TRANSFORM_VERSION", "test-next")
    assert send(client, a, p).json()["error"]["code"] == "TRANSFORM_CHANGED"
    assert receiver.invocations == []


# ------------------------------------------------- evidence scan regression --
def test_evidence_scan_matches_whole_values_only():
    assert evidence.prohibited_findings('{"commit": "a160b", "duration_seconds": 0.0160}') == []
    assert evidence.prohibited_findings("summary mentions Ava Kim") == ["fixture customer value or message text"]
