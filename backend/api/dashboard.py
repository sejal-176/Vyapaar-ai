"""Dashboard API routes for VyapaarAI."""
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import Merchant, Transaction, IngestionReport
from backend.core.timeutil import IST, utc_to_ist
from backend.analytics import latest_data_day, daily_summary, collection_trend

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/merchants")
def list_merchants(db: Session = Depends(get_db)):
    """List available merchants for switcher."""
    merchants = db.query(Merchant).all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "business_type": m.business_type,
            "vpa": m.vpa,
        }
        for m in merchants
    ]


@router.get("/dashboard")
def get_dashboard(
    merchant_id: int = Query(..., description="ID of merchant (stands in for auth)"),
    db: Session = Depends(get_db),
):
    """Dashboard payload for selected merchant."""
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    ref_date = latest_data_day(db, merchant_id)
    if ref_date is None:
        ref_date = datetime.now(IST).date()

    prev_date = ref_date - timedelta(days=1)

    sum_today = daily_summary(db, merchant_id, ref_date)
    sum_prev = daily_summary(db, merchant_id, prev_date)

    trend = collection_trend(db, merchant_id, days=14, end_day=ref_date)

    recent_rows = (
        db.query(Transaction)
        .filter(Transaction.merchant_id == merchant_id)
        .order_by(Transaction.created_at_utc.desc())
        .limit(10)
        .all()
    )

    recent_transactions = [
        {
            "reference": tx.reference,
            "amount_paise": tx.amount_paise,
            "status": tx.status,
            "txn_type": tx.txn_type,
            "created_at_ist": utc_to_ist(tx.created_at_utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for tx in recent_rows
    ]

    latest_rep = (
        db.query(IngestionReport)
        .filter(IngestionReport.merchant_id == merchant_id)
        .order_by(IngestionReport.created_at.desc())
        .first()
    )

    if latest_rep:
        try:
            reasons = json.loads(latest_rep.reasons)
        except Exception:
            reasons = {}
        ingestion_report = {
            "accepted": latest_rep.accepted,
            "rejected": latest_rep.rejected,
            "reasons": reasons,
        }
    else:
        ingestion_report = {
            "accepted": 0,
            "rejected": 0,
            "reasons": {},
        }

    return {
        "merchant": {
            "id": merchant.id,
            "name": merchant.name,
            "business_type": merchant.business_type,
        },
        "reference_date": ref_date.isoformat(),
        "summary": {
            "collections_paise": sum_today["collections_paise"],
            "success_count": sum_today["success_count"],
            "pending_count": sum_today["pending_count"],
            "failed_count": sum_today["failed_count"],
            "refunded_count": sum_today["refunded_count"],
            "avg_ticket_paise": sum_today["avg_ticket_paise"],
        },
        "previous_summary": {
            "collections_paise": sum_prev["collections_paise"],
            "success_count": sum_prev["success_count"],
            "pending_count": sum_prev["pending_count"],
            "failed_count": sum_prev["failed_count"],
            "refunded_count": sum_prev["refunded_count"],
            "avg_ticket_paise": sum_prev["avg_ticket_paise"],
        },
        "trend": trend,
        "recent_transactions": recent_transactions,
        "ingestion_report": ingestion_report,
    }
