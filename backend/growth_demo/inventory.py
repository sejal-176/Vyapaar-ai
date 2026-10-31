"""Inventory analytics for Growth Insights preview.
Calculates product velocity (usual pace), days left of stock, low stock warnings,
slow movers, and trends.
Follows all project rules:
- No banned words (revenue, sales, profit, income, eligible, score, will return, bring back, guaranteed, because)
- Guard every division by zero
- Wording: 'based on the stock you entered on <date> and the usual pace', never 'order now'.
"""
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, List
from statistics import median
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.core.money import format_inr
from backend.growth_demo.models import GDProduct, GDInvoice, GDInvoiceItem
from backend.growth_demo.config import (
    COMPARE_WINDOW_DAYS,
    VELOCITY_WINDOW_DAYS,
    DAYS_LEFT_WARN,
    SLOW_MOVER_DROP_PCT,
    SLOW_MOVER_MIN_PREV_UNITS,
    HOW_WE_MEASURE,
)


def _get_ref_date(db: Session, ref_date_str: Optional[str] = None) -> Optional[date]:
    if ref_date_str:
        return datetime.strptime(ref_date_str, "%Y-%m-%d").date()
    max_d = db.query(func.max(GDInvoice.invoice_date)).scalar()
    if max_d:
        return datetime.strptime(max_d, "%Y-%m-%d").date()
    return None


def get_inventory_insights(db: Session, ref_date_str: Optional[str] = None) -> Dict[str, Any]:
    """Calculate velocity, days left, slow movers, and trends across all products."""
    ref_date = _get_ref_date(db, ref_date_str)
    if not ref_date:
        return {
            "products": [],
            "slow_movers": [],
            "reference_date": None,
            "how_we_measure": HOW_WE_MEASURE["inventory"],
            "note": "Based on stock you entered and billed items only.",
        }

    # Time boundaries
    vel28_start = ref_date - timedelta(days=VELOCITY_WINDOW_DAYS - 1)
    last14_start = ref_date - timedelta(days=COMPARE_WINDOW_DAYS - 1)
    prev14_start = ref_date - timedelta(days=(2 * COMPARE_WINDOW_DAYS) - 1)
    prev14_end = ref_date - timedelta(days=COMPARE_WINDOW_DAYS)

    products = db.query(GDProduct).order_by(GDProduct.id.asc()).all()
    product_rows: List[Dict[str, Any]] = []
    slow_movers: List[Dict[str, Any]] = []

    for p in products:
        # 1. Velocity over last 28 days: median units per active selling day
        active_day_rows = (
            db.query(GDInvoice.invoice_date, func.sum(GDInvoiceItem.quantity))
            .join(GDInvoice, GDInvoice.id == GDInvoiceItem.invoice_id)
            .filter(
                GDInvoiceItem.product_id == p.id,
                GDInvoice.invoice_date >= vel28_start.isoformat(),
                GDInvoice.invoice_date <= ref_date.isoformat(),
            )
            .group_by(GDInvoice.invoice_date)
            .all()
        )
        daily_quantities = [r[1] for r in active_day_rows if r[1] and r[1] > 0]
        velocity = float(median(daily_quantities)) if daily_quantities else 0.0

        # 2. Days left = stock_on_hand / velocity
        days_left = None
        if velocity > 0:
            days_left = round(p.stock_on_hand / velocity, 1)

        # 3. Status label: "Low stock", "OK", or "No recent units"
        if velocity == 0:
            status_label = "No recent units"
        elif days_left is not None and days_left < DAYS_LEFT_WARN:
            status_label = "Low stock"
        else:
            status_label = "OK"

        # 4. Units last 14 vs prev 14
        units_last14 = (
            db.query(func.sum(GDInvoiceItem.quantity))
            .join(GDInvoice, GDInvoice.id == GDInvoiceItem.invoice_id)
            .filter(
                GDInvoiceItem.product_id == p.id,
                GDInvoice.invoice_date >= last14_start.isoformat(),
                GDInvoice.invoice_date <= ref_date.isoformat(),
            )
            .scalar()
            or 0
        )
        units_prev14 = (
            db.query(func.sum(GDInvoiceItem.quantity))
            .join(GDInvoice, GDInvoice.id == GDInvoiceItem.invoice_id)
            .filter(
                GDInvoiceItem.product_id == p.id,
                GDInvoice.invoice_date >= prev14_start.isoformat(),
                GDInvoice.invoice_date <= prev14_end.isoformat(),
            )
            .scalar()
            or 0
        )

        trend_pct = None
        if units_prev14 > 0:
            trend_pct = round(((units_last14 - units_prev14) / units_prev14) * 100.0, 1)

        # 5. Slow mover detection: drop >= 30% and prev units >= 10
        if units_prev14 >= SLOW_MOVER_MIN_PREV_UNITS and trend_pct is not None:
            if trend_pct <= -SLOW_MOVER_DROP_PCT:
                slow_movers.append({
                    "product_id": p.id,
                    "product_name": p.name,
                    "unit": p.unit,
                    "units_prev14": units_prev14,
                    "units_last14": units_last14,
                    "drop_pct": abs(trend_pct),
                    "note": f"Units billed dropped by {abs(trend_pct)}% in the last 14 days.",
                })

        # 6. Item margin (only if cost price is entered)
        margin_per_unit_paise = None
        margin_per_unit_inr = None
        margin_pct = None
        if p.cost_price_paise is not None:
            margin_per_unit_paise = p.price_paise - p.cost_price_paise
            margin_per_unit_inr = format_inr(margin_per_unit_paise)
            if p.price_paise > 0:
                margin_pct = round((margin_per_unit_paise / p.price_paise) * 100.0, 1)

        product_rows.append({
            "id": p.id,
            "name": p.name,
            "unit": p.unit,
            "price_paise": p.price_paise,
            "price_inr": format_inr(p.price_paise),
            "cost_price_paise": p.cost_price_paise,
            "cost_price_inr": format_inr(p.cost_price_paise) if p.cost_price_paise is not None else None,
            "margin_per_unit_inr": margin_per_unit_inr,
            "margin_pct": margin_pct,
            "stock_on_hand": p.stock_on_hand,
            "stock_updated_on": p.stock_updated_on,
            "velocity": round(velocity, 1),
            "days_left": days_left,
            "status": status_label,
            "units_last14": units_last14,
            "units_prev14": units_prev14,
            "trend_pct": trend_pct,
            "explanation": f"Based on the stock you entered on {p.stock_updated_on} and the usual pace.",
        })

    return {
        "products": product_rows,
        "slow_movers": slow_movers,
        "reference_date": ref_date.isoformat(),
        "how_we_measure": HOW_WE_MEASURE["inventory"],
        "note": "Based on stock you entered and billed items only.",
    }

