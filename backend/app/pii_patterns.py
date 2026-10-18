"""Deterministic, local detectors for structured identifiers: SSN, CREDIT_CARD, ADDRESS,
IP_ADDRESS and DOB. Each returns (start, end) spans in Unicode code points.

They are rule-based (format + checksum/validation + context words), standard library
only, and intentionally conservative. A match is a redaction decision, not proof that
the value is real: a Luhn-valid number is not necessarily an issued card, and an
SSN-shaped value need not be an issued SSN. Values that do not match are not proven
safe; see the documented limits in README.md.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import date

Span = tuple[int, int]
_CONTEXT_BEFORE = 40


def _context(text: str, start: int, pattern: re.Pattern[str], before: int = _CONTEXT_BEFORE, after: int = 0,
             end: int | None = None) -> bool:
    window = text[max(0, start - before):start]
    if after and end is not None:
        window += " " + text[end:end + after]
    return bool(pattern.search(window))


# --------------------------------------------------------------------------- #
# SSN
# --------------------------------------------------------------------------- #
_SSN = re.compile(r"(?<![\w-])(\d{3})([- ]?)(\d{2})\2(\d{4})(?![\w-])")
_SSN_CONTEXT = re.compile(r"(?i)\b(?:ssn|ss#|ss no|social security(?: number| no)?|soc\.? ?sec\.?|itin)\b")
# Reference-number labels right before the value: such numbers are not treated as SSNs
# unless an SSN cue is also present.
_REFERENCE_CONTEXT = re.compile(r"(?i)\b(?:order|ticket|invoice|tracking|confirmation|case|ref(?:erence)?|po|sku|account|acct)\b[\s#:no.]*$")


def _ssn_issuable(area: str, group: str, serial: str) -> bool:
    """SSA rules: area not 000, 666 or 900-999; group not 00; serial not 0000."""
    return area not in ("000", "666") and not area.startswith("9") and group != "00" and serial != "0000"


def find_ssn(text: str) -> list[Span]:
    """With an SSN context word shortly before: any 3-2-4 digit shape (dashed, spaced or
    bare), including ITIN-style 9xx areas, except all-zero groups. Without context: only
    the dashed form ddd-dd-dddd that passes the SSA issuance rules and is not labelled as
    an order/ticket/invoice/... number. A bare nine-digit number without SSN context
    (order, ticket or national ID numbers) is never matched.
    """
    out = []
    for m in _SSN.finditer(text):
        area, sep, group, serial = m.groups()
        if group == "00" or serial == "0000" or area == "000":
            continue
        if _context(text, m.start(), _SSN_CONTEXT):
            out.append((m.start(), m.end()))
        elif sep == "-" and _ssn_issuable(area, group, serial) \
                and not _REFERENCE_CONTEXT.search(text[max(0, m.start() - 24):m.start()]):
            out.append((m.start(), m.end()))
    return out


# --------------------------------------------------------------------------- #
# Credit card
# --------------------------------------------------------------------------- #
_CARD = re.compile(r"(?<![\w-])\d(?:[ -]?\d){12,18}(?![\w-])")
_PAYMENT_CONTEXT = re.compile(
    r"(?i)\b(?:card|credit|debit|visa|master ?card|amex|american express|discover|payment|paid|pay|charged?|"
    r"charges|billing|billed|refund(?:ed)?|cvv|expir\w*)\b")
_GROUPINGS = ([4, 4, 4, 4], [4, 4, 4, 4, 3], [4, 6, 5], [4, 6, 4], [4, 4, 4, 2], [4, 4, 4, 1])


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _issuer_plausible(d: str) -> bool:
    """Major network prefixes (IIN ranges) and lengths."""
    n = len(d)
    two, four, six = int(d[:2]), int(d[:4]), int(d[:6])
    return ((d[0] == "4" and n in (13, 16, 19))                                   # Visa
            or ((51 <= two <= 55 or 2221 <= four <= 2720) and n == 16)            # Mastercard
            or (two in (34, 37) and n == 15)                                      # Amex
            or ((d.startswith("6011") or d.startswith("65") or 644 <= int(d[:3]) <= 649
                 or 622126 <= six <= 622925) and 16 <= n <= 19)                   # Discover
            or (3528 <= four <= 3589 and 16 <= n <= 19)                           # JCB
            or ((300 <= int(d[:3]) <= 305 or two in (36, 38)) and 14 <= n <= 19)) # Diners


def find_credit_cards(text: str) -> list[Span]:
    """13-19 digits that pass Luhn and a known issuer prefix. Card-style grouping
    (4-4-4-4, 4-6-5, ... with one consistent separator) is enough; an ungrouped or
    irregularly grouped number also needs a payment word nearby (card, charged, refund...).
    """
    out = []
    for m in _CARD.finditer(text):
        raw = m.group()
        digits = re.sub(r"\D", "", raw)
        if not 13 <= len(digits) <= 19 or not luhn_valid(digits) or not _issuer_plausible(digits):
            continue
        seps = set(re.findall(r"[ -]", raw))
        grouped = len(seps) == 1 and [len(g) for g in re.split(r"[ -]", raw)] in _GROUPINGS
        if grouped or _context(text, m.start(), _PAYMENT_CONTEXT, before=60, after=30, end=m.end()):
            out.append((m.start(), m.end()))
    return out


# --------------------------------------------------------------------------- #
# US street address
# --------------------------------------------------------------------------- #
_SUFFIX = (r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Place|Pl|Way|Terrace|Ter|"
           r"Parkway|Pkwy|Circle|Cir|Highway|Hwy|Square|Sq|Trail|Trl|Alley|Aly)")
_DIR = r"(?:N|S|E|W|NE|NW|SE|SW|North|South|East|West)\.?"
_NAME_WORD = r"(?:[A-Z][A-Za-z'’\-]*|\d{1,3}(?:st|nd|rd|th))"
_UNIT = r"(?:Apt|Apartment|Suite|Ste|Unit|Fl|Floor|Rm|Room|#)\.?\s*#?\s*[A-Za-z0-9][A-Za-z0-9\-]{0,5}"
_STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
           "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR GU VI AS MP").split()
_STATE = r"(?:" + "|".join(_STATES) + r")"
_CITY = r"[A-Z][A-Za-z.'’\-]*(?:\s[A-Z][A-Za-z.'’\-]*){0,2}"
_ADDRESS = re.compile(
    rf"(?<![\w#-])"
    rf"(?:{_UNIT},?\s+)?"                                        # unit written first: "Apt 4B, 184 ..."
    rf"\d{{1,6}}[A-Za-z]?(?:-\d{{1,4}})?\s+(?:{_DIR}\s+)?"       # house number, optional direction
    rf"{_NAME_WORD}(?:\s+{_NAME_WORD}){{0,3}}\s+{_SUFFIX}\b\.?"   # 1-4 street-name words + suffix
    rf"(?:\s+{_DIR}(?![\w]))?"
    rf"(?:,?\s+{_UNIT})?"                                        # "..., Apt 4B"
    rf"(?:,\s+{_CITY},?\s+{_STATE}(?:\s+\d{{5}}(?:-\d{{4}})?)?(?![\w-])"  # ", City(,) ST [ZIP]"
    rf"|,?\s+\d{{5}}(?:-\d{{4}})?(?![\w-]))?"                   # or just a ZIP
)
_PO_BOX = re.compile(r"(?i)(?<![\w])P\.?\s?O\.?\s+Box\s+\d{1,6}(?![\w])")


def find_addresses(text: str) -> list[Span]:
    """US-style street addresses: house number + capitalized street name + street suffix,
    with an optional unit (before or after) and an optional ", City, ST ZIP" tail; plus
    PO boxes. A city, state or ZIP on its own ("Los Angeles", "Los Angeles, CA 90012") is
    not a full street address and is not matched. Lowercase and non-US formats are missed.
    """
    spans = [(m.start(), m.end()) for m in _ADDRESS.finditer(text)]
    spans += [(m.start(), m.end()) for m in _PO_BOX.finditer(text)]
    return sorted(spans)


# --------------------------------------------------------------------------- #
# IP address
# --------------------------------------------------------------------------- #
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w]|\.\d)")
_IPV6 = re.compile(r"(?<![\w:.])(?:[0-9A-Fa-f]{1,4}|:)?(?::[0-9A-Fa-f]{0,4}){2,7}(?:%[\w.]+)?(?![\w:])")
_VERSION_CONTEXT = re.compile(r"(?i)\b(?:version|ver\.?|v|build|release|firmware|android|ios)\s*$")


def find_ip_addresses(text: str) -> list[Span]:
    """IPv4/IPv6 candidates validated with the standard ``ipaddress`` module. Dotted
    numbers right after "version", "build", "v" ... are treated as version strings."""
    out = []
    for m in _IPV4.finditer(text):
        try:
            ipaddress.IPv4Address(m.group())
        except ValueError:
            continue
        if not _VERSION_CONTEXT.search(text[max(0, m.start() - 12):m.start()]):
            out.append((m.start(), m.end()))
    for m in _IPV6.finditer(text):
        candidate = m.group().split("%")[0]
        if not re.search(r"[0-9A-Fa-f]", candidate):
            continue  # "::" alone or ":::" punctuation
        try:
            ipaddress.IPv6Address(candidate)
        except ValueError:
            continue  # times like 12:30:45 and MAC addresses fail validation
        out.append((m.start(), m.end()))
    return sorted(out)


# --------------------------------------------------------------------------- #
# Date of birth
# --------------------------------------------------------------------------- #
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], start=1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
_DATE = re.compile(
    rf"(?i)(?<![\w/.-])(?:"
    rf"(?P<y1>\d{{4}})[-/.](?P<m1>\d{{1,2}})[-/.](?P<d1>\d{{1,2}})"                 # 1990-02-14
    rf"|(?P<a2>\d{{1,2}})[-/.](?P<b2>\d{{1,2}})[-/.](?P<y2>\d{{4}}|\d{{2}})"         # 02/14/1990, 14.02.90
    rf"|(?P<mon3>{_MON})\s+(?P<d3>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<y3>\d{{4}})"    # Feb 14, 1990
    rf"|(?P<d4>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<mon4>{_MON})\s+(?P<y4>\d{{4}})"      # 14 February 1990
    rf")(?![\w/-])")
_DOB_CONTEXT = re.compile(r"(?i)(?:\bdob\b|\bd\.o\.b\.?|date of birth|birth ?date|\bborn(?: on)?\b|\bbirthday\b)[\s:,-]*(?:is\s+|was\s+|of\s+|on\s+)?$")


def _valid_date(y: int, m: int, d: int, two_digit_year: bool) -> bool:
    if not two_digit_year and not 1900 <= y <= date.today().year:
        return False
    try:
        date(2000 if two_digit_year else y, m, d)
        return True
    except ValueError:
        return False


def find_dobs(text: str) -> list[Span]:
    """A real calendar date immediately preceded by a birth-date cue (DOB, date of birth,
    born on, birthday ...). Dates without that cue (purchase, outage, renewal dates) are
    left alone; a birth year on its own is not matched."""
    out = []
    for m in _DATE.finditer(text):
        g = m.groupdict()
        if g["y1"]:
            ok = _valid_date(int(g["y1"]), int(g["m1"]), int(g["d1"]), False)
        elif g["y2"]:
            short = len(g["y2"]) == 2
            a, b, y = int(g["a2"]), int(g["b2"]), int(g["y2"])
            ok = _valid_date(y, a, b, short) or _valid_date(y, b, a, short)  # US or day-first
        else:
            mon = (g["mon3"] or g["mon4"]).rstrip(".").lower()
            ok = _valid_date(int(g["y3"] or g["y4"]), _MONTHS[mon[:4] if mon[:4] == "sept" else mon[:3]],
                             int(g["d3"] or g["d4"]), False)
        if ok and _DOB_CONTEXT.search(text[max(0, m.start() - _CONTEXT_BEFORE):m.start()]):
            out.append((m.start(), m.end()))
    return out


# Precedence for overlapping matches, highest first (EMAIL and PHONE live in transform.PATTERNS).
FINDERS = {
    "SSN": find_ssn,
    "CREDIT_CARD": find_credit_cards,
    "IP_ADDRESS": find_ip_addresses,
    "DOB": find_dobs,
    "ADDRESS": find_addresses,
}
