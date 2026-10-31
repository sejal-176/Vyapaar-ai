"""Normalization utilities for transaction status and codes."""
from typing import Optional

_STATUS_MAP = {
    # SUCCESS variants
    "success": "SUCCESS",
    "successful": "SUCCESS",
    "completed": "SUCCESS",
    "paid": "SUCCESS",
    "done": "SUCCESS",
    # PENDING variants
    "pending": "PENDING",
    "processing": "PENDING",
    "in progress": "PENDING",
    "in-progress": "PENDING",
    # FAILED variants
    "failed": "FAILED",
    "declined": "FAILED",
    "failure": "FAILED",
    # REFUNDED variants
    "refunded": "REFUNDED",
    "refund": "REFUNDED",
    "reversed": "REFUNDED",
}


def normalize_status(text: Optional[str]) -> Optional[str]:
    """Trim and case-insensitively normalize status text to standard status:
    SUCCESS, PENDING, FAILED, REFUNDED.
    Returns None if text cannot be recognized.
    """
    if text is None:
        return None
    cleaned = str(text).strip().lower()
    return _STATUS_MAP.get(cleaned)

