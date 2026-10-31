"""Period comparison analytics.
Computes volume vs ticket size decomposition with exact-sum guarantee.
Rule 1: All money in integer paise.
Rule 9: Never invent numbers or causes; separate measured facts from possible explanations.
"""
from datetime import date
from typing import Optional
from sqlalchemy.orm import Session

from backend.analytics.summary import daily_summary


def compute_driver_summary(volume_effect: int, ticket_effect: int) -> str:
    """Build driver summary sentence in Python from absolute effects.
    Percentages are computed from abs(volume_effect) and abs(ticket_effect),
    rounded, and MUST sum to 100.
    If one effect is 0, say so plainly.
    If effects have opposite signs, say that one offset the other instead of using percentages.
    """
    abs_vol = abs(volume_effect)
    abs_tkt = abs(ticket_effect)

    # 1. Zero effects
    if abs_vol == 0 and abs_tkt == 0:
        return "There was no change in payment volume or average payment."
    if abs_vol == 0:
        dir_tkt = "higher" if ticket_effect > 0 else "lower"
        return f"The change was driven entirely by a {dir_tkt} average payment; payment volume did not change."
    if abs_tkt == 0:
        dir_vol = "more" if volume_effect > 0 else "fewer"
        return f"The change was driven entirely by {dir_vol} payments; the average payment did not change."

    # 2. Opposite signs -> use 'offset' wording instead of percentages
    if (volume_effect > 0 and ticket_effect < 0) or (volume_effect < 0 and ticket_effect > 0):
        if volume_effect < 0 and ticket_effect > 0:
            return "The drop in payments was partially offset by a higher average payment."
        else:
            return "The gain from more payments was partially offset by a lower average payment."

    # 3. Same sign -> percentages sum to 100
    total_abs = abs_vol + abs_tkt
    pct_vol = round((abs_vol / total_abs) * 100)
    pct_tkt = 100 - pct_vol

    vol_desc = "Fewer payments" if volume_effect < 0 else "More payments"
    tkt_desc = "a lower average payment" if ticket_effect < 0 else "a higher average payment"

    return f"{vol_desc} explain about {pct_vol}% of the change; {tkt_desc} explains about {pct_tkt}%."


def compare_periods(
    db: Session,
    merchant_id: int,
    day_a: date,
    day_b: date,
    up_to_hour: Optional[int] = None,
) -> dict:
    """Compare two days (day_a earlier, day_b later).
    Computes volume_effect and ticket_effect.

    Exact-sum rule:
    Algebraically, volume_effect = (count_b - count_a) * avg_a and
    ticket_effect = count_b * (avg_b - avg_a).
    Because avg_a and avg_b are rounded to integer paise (integer division),
    the raw formula could leave a small remainder (a few paise) differing from
    (collections_b - collections_a).
    To satisfy the non-negotiable rule that volume_effect + ticket_effect sums
    EXACTLY to delta_collections_paise, we absorb the rounding remainder into
    ticket_effect: ticket_effect = delta_collections_paise - volume_effect.
    """
    summary_a = daily_summary(db, merchant_id, day_a, up_to_hour=up_to_hour)
    summary_b = daily_summary(db, merchant_id, day_b, up_to_hour=up_to_hour)

    col_a = summary_a["collections_paise"]
    col_b = summary_b["collections_paise"]
    count_a = summary_a["success_count"]
    count_b = summary_b["success_count"]
    avg_a = summary_a["avg_ticket_paise"]
    avg_b = summary_b["avg_ticket_paise"]

    delta_collections_paise = col_b - col_a
    delta_success_count = count_b - count_a
    delta_avg_ticket_paise = avg_b - avg_a

    # Volume effect: impact of change in number of successful transactions at previous ticket average
    volume_effect = (count_b - count_a) * avg_a

    # Ticket effect: absorbs any integer division rounding remainder so sum is exact
    ticket_effect = delta_collections_paise - volume_effect

    # Main driver assessment: "volume" if |volume| > |ticket|, "ticket_size" if smaller,
    # "mixed" when within 10% of each other.
    abs_vol = abs(volume_effect)
    abs_tkt = abs(ticket_effect)
    max_effect = max(abs_vol, abs_tkt)

    if max_effect == 0:
        main_driver = "mixed"
    elif abs(abs_vol - abs_tkt) <= 0.10 * max_effect:
        main_driver = "mixed"
    elif abs_vol > abs_tkt:
        main_driver = "volume"
    else:
        main_driver = "ticket_size"

    note = (
        f"Comparison limited to activity up to hour {up_to_hour:02d}:00 IST."
        if up_to_hour is not None
        else None
    )

    day_complete = summary_b.get("day_complete", True) and (up_to_hour is None)
    compare_basis = "same_hours" if not day_complete or up_to_hour is not None else "full_day_vs_full_day"
    data_up_to_ist = summary_b.get("data_up_to_ist")

    driver_summary = compute_driver_summary(volume_effect, ticket_effect)

    return {
        "day_a": summary_a,
        "day_b": summary_b,
        "date_a": day_a.isoformat(),
        "date_b": day_b.isoformat(),
        "delta_collections_paise": delta_collections_paise,
        "delta_success_count": delta_success_count,
        "delta_avg_ticket_paise": delta_avg_ticket_paise,
        "volume_effect": volume_effect,
        "ticket_effect": ticket_effect,
        "main_driver": main_driver,
        "driver_summary": driver_summary,
        "compare_basis": compare_basis,
        "day_complete": day_complete,
        "data_up_to_ist": data_up_to_ist,
        "note": note,
    }
