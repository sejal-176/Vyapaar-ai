"""Daily Business Report API route for VyapaarAI."""
from datetime import datetime, timedelta, date as dt_date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import Merchant, Case
from backend.core.timeutil import IST
from backend.core.money import format_inr
from backend.analytics import latest_data_day, daily_summary, compare_periods, hourly_activity

router = APIRouter(prefix="/api/report", tags=["report"])


def _generate_report_text(
    merchant: Merchant,
    report_date: dt_date,
    prev_date: dt_date,
    summary: dict,
    prev_summary: dict,
    comparison: dict,
    peak_info: dict,
    open_cases: int,
) -> str:
    """Build a deterministic, plain text daily business report filled with real numbers.
    No LLM is used. Strict Rule 3 compliance (never use 'revenue', 'sales', or 'profit').
    """
    col_cur_paise = summary.get("collections_paise", 0)
    col_prev_paise = prev_summary.get("collections_paise", 0)
    delta_col_paise = comparison.get("delta_collections_paise", 0)

    if col_prev_paise > 0:
        pct_change = (delta_col_paise / col_prev_paise) * 100.0
        pct_str = f"{'+' if pct_change >= 0 else ''}{pct_change:.1f}%"
    else:
        pct_str = "N/A"

    change_sign = "+" if delta_col_paise >= 0 else ""
    change_formatted = f"{change_sign}{format_inr(delta_col_paise)} ({pct_str})"

    vol_effect = comparison.get("volume_effect", 0)
    tkt_effect = comparison.get("ticket_effect", 0)
    driver = comparison.get("main_driver", "mixed")
    driver_text = {
        "volume": "Primarily driven by change in transaction volume",
        "ticket_size": "Primarily driven by change in average ticket size",
        "mixed": "Balanced mix of volume and ticket size effects",
    }.get(driver, "Mixed factors")

    lines = [
        "============================================================",
        "VYAPAARAI DAILY BUSINESS REPORT",
        f"Merchant: {merchant.name}",
        f"VPA: {merchant.vpa}",
        f"Date: {report_date.isoformat()} (IST)",
        "============================================================",
        "",
        "1. DIGITAL COLLECTIONS SUMMARY",
        f"   - Digital Collections: {format_inr(col_cur_paise)}",
        f"   - Successful Payments: {summary.get('success_count', 0)}",
        f"   - Pending Transactions: {summary.get('pending_count', 0)}",
        f"   - Failed Transactions: {summary.get('failed_count', 0)}",
        f"   - Average Ticket Size: {format_inr(summary.get('avg_ticket_paise', 0))}",
        "",
        f"2. COMPARISON WITH PREVIOUS DAY ({prev_date.isoformat()})",
        f"   - Previous Collections: {format_inr(col_prev_paise)}",
        f"   - Net Change: {change_formatted}",
        f"   - Volume Effect: {format_inr(vol_effect)}",
        f"   - Average Ticket Effect: {format_inr(tkt_effect)}",
        f"   - Key Driver: {driver_text}",
        "",
        "3. PEAK HOURLY ACTIVITY",
        f"   - Busiest Window: {peak_info['peak_hour_display']}",
        f"   - Peak Collections: {format_inr(peak_info['amount_paise'])} ({peak_info['count']} successful payments)",
        "",
        "4. INTERNAL CASES & DISPUTES",
        f"   - Open Follow-up Cases: {open_cases}",
        "",
        "------------------------------------------------------------",
        "Notice: Numbers reflect recorded digital transactions only.",
        "Cash collections and other shop takings are outside this scope.",
        "============================================================",
    ]
    return "\n".join(lines)


@router.get("")
def get_report(
    merchant_id: int = Query(..., description="ID of merchant"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (IST)"),
    db: Session = Depends(get_db),
):
    """Generate a daily business summary report for a merchant.
    Returns structured section data and a pre-rendered plain text report.
    """
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    if date:
        try:
            report_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date format '{date}'. Expected YYYY-MM-DD.",
            )
    else:
        latest = latest_data_day(db, merchant_id)
        report_date = latest if latest is not None else datetime.now(IST).date()

    prev_date = report_date - timedelta(days=1)

    summary = daily_summary(db, merchant_id, report_date)
    prev_summary = daily_summary(db, merchant_id, prev_date)
    comparison = compare_periods(db, merchant_id, prev_date, report_date)

    hourly = hourly_activity(db, merchant_id, report_date)
    peak = max(hourly, key=lambda x: (x["amount_paise"], x["count"]))
    peak_hour = peak["hour_ist"]
    peak_info = {
        "hour_ist": peak_hour,
        "peak_hour_display": f"{peak_hour:02d}:00 to {peak_hour+1:02d}:00 IST",
        "amount_paise": peak["amount_paise"],
        "count": peak["count"],
    }

    open_cases = (
        db.query(Case)
        .filter(Case.merchant_id == merchant_id, Case.status == "OPEN")
        .count()
    )

    report_text = _generate_report_text(
        merchant=merchant,
        report_date=report_date,
        prev_date=prev_date,
        summary=summary,
        prev_summary=prev_summary,
        comparison=comparison,
        peak_info=peak_info,
        open_cases=open_cases,
    )

    return {
        "date": report_date.isoformat(),
        "sections": {
            "summary": summary,
            "comparison": comparison,
            "peak_hour": peak_info,
            "open_cases": open_cases,
        },
        "text": report_text,
    }

