"""Customer analytics for Growth Insights preview.
Identifies customers visiting less (lapsing) and shrinking baskets.
Follows all privacy rules (pseudonymous tokens only, OPTED_IN named, non-consented aggregate only)
and banned-words rules (no revenue, sales, profit, income, eligible, score, will return, bring back, guaranteed, because).
"""
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, List
from statistics import median
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.core.money import format_inr
from backend.growth_demo.models import GDCustomer, GDInvoice, GDInvoiceItem, GDProduct
from backend.growth_demo.config import (
    COMPARE_WINDOW_DAYS,
    MIN_PAST_VISITS,
    LAPSE_MULTIPLIER,
    MIN_LAPSE_DAYS,
    SHRINK_PCT,
    HOW_WE_MEASURE,
)

WORTH_CHECKING_QUESTIONS = [
    "Has the customer's routine changed?",
    "Did a price or an item change?",
    "Are they paying cash or with another app now?",
    "We can only see what changed, not why.",
]


def _get_ref_date(db: Session, ref_date_str: Optional[str] = None) -> Optional[date]:
    if ref_date_str:
        return datetime.strptime(ref_date_str, "%Y-%m-%d").date()
    max_d = db.query(func.max(GDInvoice.invoice_date)).scalar()
    if max_d:
        return datetime.strptime(max_d, "%Y-%m-%d").date()
    return None


def lapsing_customers(db: Session, ref_date_str: Optional[str] = None) -> Dict[str, Any]:
    """Find customers whose visit gap is significantly higher than their usual pattern.
    Only OPTED_IN customers are returned with details; non-consented customers are counted in aggregate.
    """
    ref_date = _get_ref_date(db, ref_date_str)
    if not ref_date:
        return {
            "named": [],
            "not_named_count": 0,
            "reference_date": None,
            "how_we_measure": HOW_WE_MEASURE["lapsing"],
        }

    customers = db.query(GDCustomer).all()
    named: List[Dict[str, Any]] = []
    not_named_count = 0

    for c in customers:
        # All distinct visit dates sorted ascending
        rows = (
            db.query(GDInvoice.invoice_date)
            .filter(GDInvoice.customer_id == c.id)
            .distinct()
            .order_by(GDInvoice.invoice_date.asc())
            .all()
        )
        if len(rows) < MIN_PAST_VISITS:
            continue

        visit_dates = [datetime.strptime(r[0], "%Y-%m-%d").date() for r in rows]
        gaps = [(visit_dates[i] - visit_dates[i - 1]).days for i in range(1, len(visit_dates))]
        if not gaps:
            continue

        usual_gap = median(gaps)
        last_visit_date = visit_dates[-1]
        days_since_last_visit = (ref_date - last_visit_date).days

        # Rule: days_since_last_visit > LAPSE_MULTIPLIER * median_gap and >= MIN_LAPSE_DAYS
        if (days_since_last_visit > (LAPSE_MULTIPLIER * usual_gap)) and (
            days_since_last_visit >= MIN_LAPSE_DAYS
        ):
            if c.consent_status == "OPTED_IN":
                change_data = customer_change(db, c.id, ref_date.isoformat())
                named.append({
                    "id": c.id,
                    "payer_token": c.payer_token,
                    "consent_status": c.consent_status,
                    "usual_gap_days": round(float(usual_gap), 1),
                    "days_since_last_visit": days_since_last_visit,
                    "last_visit_date": last_visit_date.isoformat(),
                    "visits_before": change_data["visits_old"] if change_data else 0,
                    "visits_now": change_data["visits_new"] if change_data else 0,
                    "spend_before_inr": change_data["spend_old_inr"] if change_data else "₹0.00",
                    "spend_now_inr": change_data["spend_new_inr"] if change_data else "₹0.00",
                    "spend_per_visit_before_inr": (
                        change_data["spend_per_visit_old_inr"] if change_data else "₹0.00"
                    ),
                    "spend_per_visit_now_inr": (
                        change_data["spend_per_visit_new_inr"] if change_data else "₹0.00"
                    ),
                    "main_driver": change_data["main_driver"] if change_data else "fewer_visits",
                    "driver_summary": change_data["driver_summary"] if change_data else "",
                })
            else:
                not_named_count += 1

    return {
        "named": named,
        "not_named_count": not_named_count,
        "reference_date": ref_date.isoformat(),
        "how_we_measure": HOW_WE_MEASURE["lapsing"],
    }


def customer_change(
    db: Session, customer_id: int, ref_date_str: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Compare visits, spend, and basket breakdown for a customer across last 14 vs prev 14 days."""
    customer = db.query(GDCustomer).filter(GDCustomer.id == customer_id).first()
    if not customer:
        return None

    ref_date = _get_ref_date(db, ref_date_str)
    if not ref_date:
        return None

    last14_start = ref_date - timedelta(days=COMPARE_WINDOW_DAYS - 1)
    prev14_start = ref_date - timedelta(days=(2 * COMPARE_WINDOW_DAYS) - 1)
    prev14_end = ref_date - timedelta(days=COMPARE_WINDOW_DAYS)

    # Invoices in last 14 days
    last14_invs = (
        db.query(GDInvoice)
        .filter(
            GDInvoice.customer_id == customer_id,
            GDInvoice.invoice_date >= last14_start.isoformat(),
            GDInvoice.invoice_date <= ref_date.isoformat(),
        )
        .all()
    )
    # Invoices in previous 14 days
    prev14_invs = (
        db.query(GDInvoice)
        .filter(
            GDInvoice.customer_id == customer_id,
            GDInvoice.invoice_date >= prev14_start.isoformat(),
            GDInvoice.invoice_date <= prev14_end.isoformat(),
        )
        .all()
    )

    v_new = len(set(i.invoice_date for i in last14_invs))
    spend_new_paise = sum(i.total_paise for i in last14_invs)
    spend_per_visit_new_paise = (spend_new_paise // v_new) if v_new > 0 else 0

    v_old = len(set(i.invoice_date for i in prev14_invs))
    spend_old_paise = sum(i.total_paise for i in prev14_invs)
    spend_per_visit_old_paise = (spend_old_paise // v_old) if v_old > 0 else 0

    spend_change_paise = spend_new_paise - spend_old_paise

    # Exact-sum decomposition:
    # visits_effect = (v_new - v_old) * spend_per_visit_old
    # basket_effect = spend_new - spend_old - visits_effect
    visits_effect_paise = (v_new - v_old) * spend_per_visit_old_paise
    basket_effect_paise = spend_change_paise - visits_effect_paise

    # Determine main_driver (fewer_visits, smaller_basket, mixed)
    abs_vis = abs(visits_effect_paise)
    abs_bsk = abs(basket_effect_paise)
    max_eff = max(abs_vis, abs_bsk)

    if max_eff == 0:
        main_driver = "mixed"
    else:
        diff_pct = abs(abs_vis - abs_bsk) / max_eff
        if diff_pct <= 0.10:
            main_driver = "mixed"
        elif abs_vis > abs_bsk:
            main_driver = "fewer_visits"
        else:
            main_driver = "smaller_basket"

    # Driver summary sentence built without banned words
    if spend_change_paise < 0:
        driver_summary = (
            f"Fewer visits explain {format_inr(abs(visits_effect_paise))} of the spend change, "
            f"while smaller baskets explain {format_inr(abs(basket_effect_paise))}."
        )
    elif spend_change_paise > 0:
        driver_summary = (
            f"More visits contribute {format_inr(visits_effect_paise)}, "
            f"with basket size contributing {format_inr(basket_effect_paise)}."
        )
    else:
        driver_summary = "Spend remained unchanged between both periods."

    # Products changed: top 3 products by absolute change in average quantity per visit
    # Aggregate quantities
    product_dict = {p.id: p.name for p in db.query(GDProduct).all()}

    def get_product_totals(invoices):
        totals = {}
        for inv in invoices:
            for item in inv.items:
                totals[item.product_id] = totals.get(item.product_id, 0) + item.quantity
        return totals

    old_ptotals = get_product_totals(prev14_invs)
    new_ptotals = get_product_totals(last14_invs)
    all_pids = set(old_ptotals.keys()) | set(new_ptotals.keys())

    p_changes = []
    for pid in all_pids:
        p_name = product_dict.get(pid, f"Product {pid}")
        old_qty = old_ptotals.get(pid, 0)
        new_qty = new_ptotals.get(pid, 0)

        before_avg = (old_qty / v_old) if v_old > 0 else 0.0
        now_avg = (new_qty / v_new) if v_new > 0 else 0.0
        diff = now_avg - before_avg

        p_changes.append({
            "product_name": p_name,
            "before_avg": round(before_avg, 1),
            "now_avg": round(now_avg, 1),
            "change": round(diff, 1),
            "abs_change": abs(diff),
        })

    p_changes.sort(key=lambda x: x["abs_change"], reverse=True)
    products_changed = [
        {
            "product_name": p["product_name"],
            "before_avg": p["before_avg"],
            "now_avg": p["now_avg"],
            "change": p["change"],
        }
        for p in p_changes[:3]
    ]

    return {
        "customer_id": customer.id,
        "payer_token": customer.payer_token,
        "consent_status": customer.consent_status,
        "reference_date": ref_date.isoformat(),
        "visits_old": v_old,
        "visits_new": v_new,
        "spend_old_paise": spend_old_paise,
        "spend_old_inr": format_inr(spend_old_paise),
        "spend_new_paise": spend_new_paise,
        "spend_new_inr": format_inr(spend_new_paise),
        "spend_change_paise": spend_change_paise,
        "spend_change_inr": format_inr(spend_change_paise),
        "spend_per_visit_old_paise": spend_per_visit_old_paise,
        "spend_per_visit_old_inr": format_inr(spend_per_visit_old_paise),
        "spend_per_visit_new_paise": spend_per_visit_new_paise,
        "spend_per_visit_new_inr": format_inr(spend_per_visit_new_paise),
        "visits_effect_paise": visits_effect_paise,
        "visits_effect_inr": format_inr(visits_effect_paise),
        "basket_effect_paise": basket_effect_paise,
        "basket_effect_inr": format_inr(basket_effect_paise),
        "main_driver": main_driver,
        "driver_summary": driver_summary,
        "products_changed": products_changed,
        "worth_checking": WORTH_CHECKING_QUESTIONS,
    }


def shrinking_customers(db: Session, ref_date_str: Optional[str] = None) -> List[Dict[str, Any]]:
    """List customers with at least 2 visits in the last 14 days whose spend per visit is down >= 25%."""
    ref_date = _get_ref_date(db, ref_date_str)
    if not ref_date:
        return []

    customers = db.query(GDCustomer).all()
    results = []

    for c in customers:
        ch = customer_change(db, c.id, ref_date.isoformat())
        if not ch:
            continue

        # Condition: at least 2 visits in last 14 days, had visits previously
        if ch["visits_new"] >= 2 and ch["visits_old"] > 0:
            spv_old = ch["spend_per_visit_old_paise"]
            spv_new = ch["spend_per_visit_new_paise"]
            if spv_old > 0:
                drop_pct = (spv_old - spv_new) / spv_old * 100.0
                if drop_pct >= SHRINK_PCT:
                    results.append({
                        "customer_id": c.id,
                        "payer_token": c.payer_token,
                        "consent_status": c.consent_status,
                        "visits_now": ch["visits_new"],
                        "spend_per_visit_before_inr": ch["spend_per_visit_old_inr"],
                        "spend_per_visit_now_inr": ch["spend_per_visit_new_inr"],
                        "drop_pct": round(drop_pct, 1),
                        "driver_summary": ch["driver_summary"],
                    })

    return results

