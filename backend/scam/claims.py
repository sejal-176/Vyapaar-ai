"""Claim extraction from untrusted SMS text using deterministic regex only.
No AI or LLM is involved.
"""
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Optional

from backend.core.money import to_paise
from backend.core.timeutil import IST

# Reuse timestamp regexes from verification/extract.py
RE_TIMESTAMPS = [
    # YYYY-MM-DD HH:MM:SS or YYYY-MM-DD HH:MM
    re.compile(r"\b\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?\b"),
    # 12 Mar 2025, 06:42 PM or 12 March 2025 06:42 PM
    re.compile(
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\b",
        re.IGNORECASE,
    ),
    # 12/03/2025 18:42 or 12-03-2025 18:42
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?\b"),
]

# Direction phrases (order matters: check longer/specific phrases first)
CREDIT_PHRASES = [
    r"\badded\s+to\s+your\s+account\b",
    r"\bcredited\b",
    r"\breceived\b",
    r"\bdeposited\b",
    r"\bcredit\b",
    r"\baaya\b",
    r"\baaye\b",
    r"\bjama\b",
]

DEBIT_PHRASES = [
    r"\bdebited\b",
    r"\bpaid\b",
    r"\bsent\b",
    r"\bwithdrawn\b",
    r"\bdebit\b",
    r"\bkat\s+gaya\b",
    r"\bkata\b",
]

REFUND_PHRASES = [
    r"\breversed\b",
    r"\breversal\b",
    r"\brefunded\b",
    r"\brefund\b",
    r"\bwapas\b",
]

# Amount patterns: require at least one leading digit to avoid matching punctuation like commas
RE_AMOUNT = re.compile(
    r"(?:₹|Rs\.?|INR)\s*(\d[\d,]*(?:\.\d{1,2})?)|(\d[\d,]*(?:\.\d{1,2})?)\s*(?:₹|Rs\.?|INR)",
    re.IGNORECASE,
)

# Labelled UTR patterns (take precedence over plain 12-digits)
RE_LABELLED_UTR = re.compile(
    r"(?i)\b(?:utr|ref(?:\s*no)?|txn(?:\s*id)?|rrn)[:\s#-]*(\d{12})\b"
)
RE_PLAIN_UTR = re.compile(r"\b(\d{12})\b")

# Counterparty: UPI ID or text after "from" / "by"
RE_UPI_ID = re.compile(r"\b([a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,})\b")
RE_FROM_BY = re.compile(
    r"(?i)\b(?:from|by)[:\s]+([a-zA-Z0-9_\-\.\s]{2,40})"
)


@dataclass
class Claim:
    direction: str = "unknown"  # "credit" | "debit" | "refund" | "unknown"
    amount_paise: Optional[int] = None
    utr: Optional[str] = None
    timestamp: Optional[str] = None
    counterparty: Optional[str] = None
    raw_amounts_found: list[int] = field(default_factory=list)


def extract_claim(text: str) -> Claim:
    """Extract factual payment claims from untrusted plain text SMS."""
    if not text:
        return Claim()

    clean_text = text.strip()

    # 1. Direction & its position
    direction = "unknown"
    dir_pos = -1

    # Check refunds first
    for pat in REFUND_PHRASES:
        m = re.search(pat, clean_text, re.IGNORECASE)
        if m:
            direction = "refund"
            dir_pos = m.start()
            break

    # Check debits
    if direction == "unknown":
        for pat in DEBIT_PHRASES:
            m = re.search(pat, clean_text, re.IGNORECASE)
            if m:
                direction = "debit"
                dir_pos = m.start()
                break

    # Check credits
    if direction == "unknown":
        for pat in CREDIT_PHRASES:
            m = re.search(pat, clean_text, re.IGNORECASE)
            if m:
                direction = "credit"
                dir_pos = m.start()
                break

    # 2. Amounts
    # Find all amounts with their start positions
    raw_amounts_found: list[int] = []
    amounts_with_pos: list[tuple[int, int]] = []  # (start_pos, paise)

    for m in RE_AMOUNT.finditer(clean_text):
        num_str = m.group(1) or m.group(2)
        if num_str:
            paise = to_paise(num_str)
            if paise is not None and paise > 0:
                raw_amounts_found.append(paise)
                amounts_with_pos.append((m.start(), paise))

    amount_paise = None
    if amounts_with_pos:
        if dir_pos >= 0:
            # First amount that follows the direction word
            following = [paise for pos, paise in amounts_with_pos if pos >= dir_pos]
            if following:
                amount_paise = following[0]
            else:
                amount_paise = amounts_with_pos[0][1]
        else:
            amount_paise = amounts_with_pos[0][1]

    # 3. UTR
    utr = None
    labelled_m = RE_LABELLED_UTR.search(clean_text)
    if labelled_m:
        utr = labelled_m.group(1)
    else:
        plain_m = RE_PLAIN_UTR.search(clean_text)
        if plain_m:
            utr = plain_m.group(1)

    # 4. Timestamp
    timestamp = None
    for ts_pattern in RE_TIMESTAMPS:
        ts_m = ts_pattern.search(clean_text)
        if ts_m:
            timestamp = ts_m.group(0).strip()
            break

    # 5. Counterparty
    counterparty = None
    upi_m = RE_UPI_ID.search(clean_text)
    if upi_m:
        counterparty = upi_m.group(1).strip()
    else:
        from_m = RE_FROM_BY.search(clean_text)
        if from_m:
            raw_party = from_m.group(1).strip()
            # Clean trailing noise words like ref, utr, on, date, at, upi
            cleaned_party = re.sub(
                r"(?i)\s+(?:utr|ref|date|on|at|upi|via|inr|rs).*", "", raw_party
            ).strip()
            if cleaned_party:
                counterparty = cleaned_party

    return Claim(
        direction=direction,
        amount_paise=amount_paise,
        utr=utr,
        timestamp=timestamp,
        counterparty=counterparty,
        raw_amounts_found=raw_amounts_found,
    )
