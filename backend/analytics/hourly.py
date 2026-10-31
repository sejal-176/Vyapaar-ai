"""Hourly activity analytics for a single IST day.
Returns 24 buckets (0-23) for successful payments only.
"""
from datetime import date
from sqlalchemy.orm import Session

from backend.core.timeutil import ist_day_bounds_utc, utc_to_ist
from backend.models import Transaction


def hourly_activity(db: Session, merchant_id: int, day: date) -> list[dict]:
    """Returns 24 entries [{hour_ist: 0..23, count: int, amount_paise: int}]
    for successful digital payment transactions on the given IST day.
    """
    s_utc, e_utc = ist_day_bounds_utc(day)
    start_utc = s_utc.replace(tzinfo=None)
    end_utc = e_utc.replace(tzinfo=None)

    rows = (
        db.query(Transaction)
        .filter(
            Transaction.merchant_id == merchant_id,
            Transaction.status == "SUCCESS",
            Transaction.txn_type == "PAYMENT",
            Transaction.created_at_utc >= start_utc,
            Transaction.created_at_utc < end_utc,
        )
        .all()
    )

    # Initialize 24 hour buckets
    buckets = [{"hour_ist": h, "count": 0, "amount_paise": 0} for h in range(24)]

    for tx in rows:
        ist_dt = utc_to_ist(tx.created_at_utc)
        h = ist_dt.hour
        buckets[h]["count"] += 1
        buckets[h]["amount_paise"] += tx.amount_paise

    return buckets
