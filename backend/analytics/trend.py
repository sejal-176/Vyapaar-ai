"""Collection trend analytics over recent days."""
from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from backend.analytics.summary import latest_data_day, daily_summary


def collection_trend(
    db: Session,
    merchant_id: int,
    days: int = 14,
    end_day: Optional[date] = None,
) -> list[dict]:
    """Generate daily digital collections trend ending at latest_data_day (or end_day).
    Returns list of dicts: [{"date": "YYYY-MM-DD", "collections_paise": int}]
    """
    ref_day = end_day if end_day is not None else latest_data_day(db, merchant_id)
    if ref_day is None:
        return []

    start_day = ref_day - timedelta(days=days - 1)
    trend = []

    current_day = start_day
    while current_day <= ref_day:
        summary = daily_summary(db, merchant_id, current_day)
        trend.append({
            "date": current_day.isoformat(),
            "collections_paise": summary["collections_paise"],
        })
        current_day += timedelta(days=1)

    return trend

