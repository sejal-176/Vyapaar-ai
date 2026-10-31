"""Data ingestion pipeline for VyapaarAI.
Rule 1: Money stored as integer paise.
Rule 2: Time stored as UTC.
Rule 10: Bad input rows are never silently dropped; they go to quarantine with a reason.
Rule 11: Cross-merchant isolation; reference uniqueness is per-merchant.
"""
import csv
import json
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session

from backend.core.money import to_paise
from backend.core.normalize import normalize_status
from backend.core.timeutil import to_utc
from backend.models import IngestionReport, Quarantine, Transaction


DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d",
]


def _parse_timestamp(raw_text: str | None) -> datetime | None:
    """Parse raw timestamp string to UTC datetime (naive in UTC for DB).
    Naive inputs are assumed IST, then converted to UTC.
    """
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    if not cleaned:
        return None

    # Try fromisoformat first
    try:
        dt = datetime.fromisoformat(cleaned)
        return to_utc(dt).replace(tzinfo=None)
    except (ValueError, TypeError):
        pass

    for fmt in DATETIME_FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return to_utc(dt).replace(tzinfo=None)
        except (ValueError, TypeError):
            continue

    return None


def ingest_csv(path: str | Path, merchant_id: int, db: Session) -> dict:
    """Ingest transactions from CSV file for given merchant.
    Validates every row, quarantines any invalid rows with a reason,
    saves valid transactions, and records an IngestionReport.

    Returns dict:
    {
        "accepted": int,
        "rejected": int,
        "reasons": {
            "duplicate": int,
            "invalid_amount": int,
            "missing_time": int,
            "unknown_status": int,
            "blank_reference": int
        }
    }
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    # Track seen references for this merchant: load existing from DB + this file
    existing_refs = {
        r[0] for r in db.query(Transaction.reference)
        .filter(Transaction.merchant_id == merchant_id)
        .all()
    }
    seen_references = set(existing_refs)

    accepted_count = 0
    rejected_count = 0
    reasons_count = {
        "duplicate": 0,
        "invalid_amount": 0,
        "missing_time": 0,
        "unknown_status": 0,
        "blank_reference": 0,
    }

    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_row_str = json.dumps(row)
            ref_raw = row.get("reference")
            ref = ref_raw.strip() if ref_raw is not None else ""

            # Check 1: blank reference
            if not ref:
                reasons_count["blank_reference"] += 1
                rejected_count += 1
                db.add(Quarantine(
                    merchant_id=merchant_id,
                    raw_row=raw_row_str,
                    reason="blank_reference",
                ))
                continue

            # Check 2: duplicate reference
            if ref in seen_references:
                reasons_count["duplicate"] += 1
                rejected_count += 1
                db.add(Quarantine(
                    merchant_id=merchant_id,
                    raw_row=raw_row_str,
                    reason="duplicate",
                ))
                continue

            # Check 3: invalid amount
            amt_paise = to_paise(row.get("amount"))
            if amt_paise is None or amt_paise <= 0:
                reasons_count["invalid_amount"] += 1
                rejected_count += 1
                db.add(Quarantine(
                    merchant_id=merchant_id,
                    raw_row=raw_row_str,
                    reason="invalid_amount",
                ))
                continue

            # Check 4: unknown status
            status = normalize_status(row.get("status"))
            if status is None:
                reasons_count["unknown_status"] += 1
                rejected_count += 1
                db.add(Quarantine(
                    merchant_id=merchant_id,
                    raw_row=raw_row_str,
                    reason="unknown_status",
                ))
                continue

            # Check 5: missing/invalid timestamp
            dt_utc = _parse_timestamp(row.get("timestamp"))
            if dt_utc is None:
                reasons_count["missing_time"] += 1
                rejected_count += 1
                db.add(Quarantine(
                    merchant_id=merchant_id,
                    raw_row=raw_row_str,
                    reason="missing_time",
                ))
                continue

            # All checks passed: accept row
            txn_type = "REFUND" if status == "REFUNDED" else "PAYMENT"
            tx = Transaction(
                merchant_id=merchant_id,
                reference=ref,
                amount_paise=amt_paise,
                status=status,
                txn_type=txn_type,
                created_at_utc=dt_utc,
            )
            db.add(tx)
            seen_references.add(ref)
            accepted_count += 1

    # Save IngestionReport
    report = IngestionReport(
        merchant_id=merchant_id,
        accepted=accepted_count,
        rejected=rejected_count,
        reasons=json.dumps(reasons_count),
    )
    db.add(report)
    db.commit()

    return {
        "accepted": accepted_count,
        "rejected": rejected_count,
        "reasons": reasons_count,
    }

