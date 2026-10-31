"""Daily summary and reference date analytics.
Rule 1: Money stored as integer paise.
Rule 2: Time stored as UTC; day bounds defined in IST.
Rule 3: Digital collections = SUM(amount_paise) where status = SUCCESS and txn_type = PAYMENT.
Rule 11: Cross-merchant isolation; always filter by merchant_id.
"""
from datetime import date, datetime, time, timedelta
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.timeutil import IST, utc_to_ist, ist_day_bounds_utc, to_utc
from backend.models import Transaction


def latest_data_day(db: Session, merchant_id: int) -> Optional[date]:
    """Find the latest date that has transaction data for the merchant.
    Uses IST calendar day of the latest transaction's UTC timestamp.
    Returns None if no transactions exist.
    """
    latest_utc = (
        db.query(func.max(Transaction.created_at_utc))
        .filter(Transaction.merchant_id == merchant_id)
        .scalar()
    )
    if latest_utc is None:
        return None
    # Convert DB UTC datetime to IST calendar day
    ist_dt = utc_to_ist(latest_utc)
    return ist_dt.date()


def daily_summary(
    db: Session,
    merchant_id: int,
    day: date,
    up_to_hour: Optional[int] = None,
) -> dict:
    """Compute daily summary for a given IST day.
    If up_to_hour is provided (0-23), only include activity up to that IST hour (inclusive).
    Never hardcode numbers: all values computed from database.
    Avg ticket = collections_paise // success_count (0 if no successes).
    """
    if up_to_hour is not None:
        start_ist = datetime.combine(day, time.min, tzinfo=IST)
        # up_to_hour is inclusive (e.g. up_to_hour=14 means through 14:59:59, so < 15:00:00)
        end_ist = start_ist + timedelta(hours=up_to_hour + 1)
        start_utc = to_utc(start_ist).replace(tzinfo=None)
        end_utc = to_utc(end_ist).replace(tzinfo=None)
    else:
        s_utc, e_utc = ist_day_bounds_utc(day)
        start_utc = s_utc.replace(tzinfo=None)
        end_utc = e_utc.replace(tzinfo=None)

    # Base query for merchant on this day
    q = db.query(Transaction).filter(
        Transaction.merchant_id == merchant_id,
        Transaction.created_at_utc >= start_utc,
        Transaction.created_at_utc < end_utc,
    )
    rows = q.all()
    has_data = len(rows) > 0

    collections_paise = 0
    success_count = 0
    pending_count = 0
    pending_paise = 0
    failed_count = 0
    refunded_count = 0
    refund_total_paise = 0
    latest_tx_utc = None

    for tx in rows:
        if latest_tx_utc is None or tx.created_at_utc > latest_tx_utc:
            latest_tx_utc = tx.created_at_utc
        if tx.status == "SUCCESS" and tx.txn_type == "PAYMENT":
            collections_paise += tx.amount_paise
            success_count += 1
        elif tx.status == "PENDING":
            pending_count += 1
            pending_paise += tx.amount_paise
        elif tx.status == "FAILED":
            failed_count += 1
        elif tx.status == "REFUNDED" or tx.txn_type == "REFUND":
            refunded_count += 1
            refund_total_paise += tx.amount_paise

    avg_ticket_paise = (collections_paise // success_count) if success_count > 0 else 0

    today_ist = datetime.now(IST).date()
    if up_to_hour is not None:
        day_complete = False
        data_up_to_ist = f"{up_to_hour:02d}:00 IST"
    elif day == today_ist:
        day_complete = False
        data_up_to_ist = (
            utc_to_ist(latest_tx_utc).strftime("%I:%M %p IST").lstrip("0")
            if latest_tx_utc else None
        )
    else:
        day_complete = True
        data_up_to_ist = None

    return {
        "date": day.isoformat(),
        "has_data": has_data,
        "collections_paise": collections_paise,
        "success_count": success_count,
        "pending_count": pending_count,
        "pending_paise": pending_paise,
        "failed_count": failed_count,
        "refunded_count": refunded_count,
        "refund_total_paise": refund_total_paise,
        "avg_ticket_paise": avg_ticket_paise,
        "day_complete": day_complete,
        "data_up_to_ist": data_up_to_ist,
    }
