"""Money conversion and formatting utilities.
Rule 1: Money is stored as integer paise. Never use floats for money.
Use Decimal when parsing text.
"""
from decimal import Decimal, InvalidOperation
import re


def to_paise(text: str | int | float | None) -> int | None:
    """Parse text/number into integer paise.
    Strips currency symbols (₹, Rs, Rs., INR), commas, spaces.
    Returns None if text cannot be parsed into a numeric amount.
    Negative values parse as negative ints (for ingestion rejection).
    """
    if text is None:
        return None
    if isinstance(text, int):
        return text * 100
    if isinstance(text, float):
        text = str(text)
    elif not isinstance(text, str):
        text = str(text)

    cleaned = text.strip()
    if not cleaned:
        return None

    # Strip currency prefixes: Rs., Rs, INR, Rupees, ₹
    cleaned = re.sub(r'(?i)\b(?:inr|rupees?)\b', '', cleaned)
    cleaned = re.sub(r'(?i)\brs\.?', '', cleaned)
    cleaned = cleaned.replace('₹', '')
    # Remove commas and spaces
    cleaned = cleaned.replace(',', '').replace(' ', '')
    if not cleaned:
        return None

    try:
        dec = Decimal(cleaned)
        if not dec.is_finite():
            return None
        # Convert rupees to paise (multiply by 100)
        paise_dec = dec * Decimal(100)
        return int(paise_dec.to_integral_value())
    except (InvalidOperation, ValueError, TypeError):
        return None


def format_inr(paise: int) -> str:
    """Format paise into INR string with Indian digit grouping (e.g. ₹1,250.50)."""
    is_negative = paise < 0
    abs_paise = abs(paise)
    rupees = abs_paise // 100
    cents = abs_paise % 100

    s_rupees = str(rupees)
    if len(s_rupees) <= 3:
        formatted_rupees = s_rupees
    else:
        last3 = s_rupees[-3:]
        remaining = s_rupees[:-3]
        groups = []
        while len(remaining) > 2:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.append(remaining)
        formatted_rupees = ",".join(reversed(groups)) + "," + last3

    sign = "-" if is_negative else ""
    return f"{sign}₹{formatted_rupees}.{cents:02d}"
