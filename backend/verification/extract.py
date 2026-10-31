"""OCR text extraction pipeline for payment screenshots.
Rule 6: Deterministic extraction, NO AI confidence scores.
Rule 7: OCR text is untrusted data; parse with regex only.
"""
from dataclasses import dataclass
from typing import Optional
import re
import pytesseract

from backend.config import TESSERACT_CMD
from backend.core.money import to_paise

# Configure tesseract executable path
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


@dataclass
class ExtractedFields:
    amount_paise: Optional[int] = None
    utr: Optional[str] = None
    timestamp: Optional[str] = None
    status_text: Optional[str] = None
    recipient: Optional[str] = None
    raw_text: str = ""


# Regex patterns per PLAN.md Layer 3
RE_AMOUNT_PRIMARY = re.compile(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
RE_AMOUNT_FALLBACK = re.compile(r"(?i)(?:paid|amount)[^\d\n\r]*([\d,]+(?:\.\d{1,2})?)")
RE_UTR = re.compile(r"\b(\d{12})\b")
RE_STATUS = re.compile(r"(?i)\b(success(?:ful)?|completed|pending|failed|refunded)\b")
RE_RECIPIENT = re.compile(r"(?i)(?:paid\s+to|to)[:\s]+([^\n\r,]+)")

RE_TIMESTAMPS = [
    # YYYY-MM-DD HH:MM:SS or YYYY-MM-DD HH:MM
    re.compile(r"\b\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?\b"),
    # 12 Mar 2025, 06:42 PM
    re.compile(
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\b"
    ),
    # 12/03/2025 18:42 or 12-03-2025 18:42
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?\b"),
]


def _extract_from_text(text: str) -> ExtractedFields:
    """Parse raw OCR text with deterministic regexes only."""
    # 1. Amount
    amt_match = RE_AMOUNT_PRIMARY.search(text)
    if not amt_match:
        amt_match = RE_AMOUNT_FALLBACK.search(text)

    amount_paise = None
    if amt_match:
        amount_paise = to_paise(amt_match.group(1))

    # 2. UTR (12 digits)
    utr_match = RE_UTR.search(text)
    utr = utr_match.group(1) if utr_match else None

    # 3. Status text
    status_match = RE_STATUS.search(text)
    status_text = status_match.group(1).upper() if status_match else None

    # 4. Recipient
    rec_match = RE_RECIPIENT.search(text)
    recipient = None
    if rec_match:
        raw_rec = rec_match.group(1).strip()
        # Clean up any trailing labels that might have been captured
        recipient = re.sub(r"(?i)\s+(?:utr|ref|date|amount|upi).*", "", raw_rec).strip()

    # 5. Timestamp
    timestamp = None
    for ts_pattern in RE_TIMESTAMPS:
        ts_match = ts_pattern.search(text)
        if ts_match:
            timestamp = ts_match.group(0).strip()
            break

    return ExtractedFields(
        amount_paise=amount_paise,
        utr=utr,
        timestamp=timestamp,
        status_text=status_text,
        recipient=recipient,
        raw_text=text,
    )


def extract_fields(variants: dict) -> ExtractedFields:
    """Run pytesseract OCR with --psm 6 on each image variant.
    Selects the candidate that extracts the highest number of non-null fields.
    """
    candidates = []
    for var_name, var_img in variants.items():
        try:
            text = pytesseract.image_to_string(var_img, config="--psm 6")
        except Exception:
            text = ""
        fields = _extract_from_text(text)
        score = sum(
            1 for v in [fields.amount_paise, fields.utr, fields.timestamp, fields.status_text, fields.recipient]
            if v is not None
        )
        candidates.append((score, fields))

    # Choose candidate with the highest number of extracted non-null fields
    candidates.sort(key=lambda c: c[0], reverse=True)
    best_candidate = candidates[0][1] if candidates else ExtractedFields()
    return best_candidate

