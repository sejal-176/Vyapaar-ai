"""Rule-based fallback router when LLM API is unavailable, throttled, or unconfigured.
Follows exact parity with agent prompt structure, wording constraints, and closing lines.
Rule 3: Say 'digital collections', never 'revenue', 'sales', or 'profit'.
Rule 4: Never invent numbers; all values sourced from typed backend tools.
Rule 9: Separate measured facts from possible explanations.
"""
from datetime import timedelta, date as dt_date
import re
from sqlalchemy.orm import Session

from backend.analytics import latest_data_day
from backend.tools.registry import run_tool


def fallback_agent(db: Session, merchant_id: int, message: str) -> dict:
    """Deterministic intent router and response generator with Hinglish keyword mapping.
    Always returns:
    {
        "answer": str,
        "tools_used": [{"name": str, "args": dict}],
        "mode": "rule-based"
    }
    """
    msg_lower = message.lower().strip()
    ref_day = latest_data_day(db, merchant_id)
    if not ref_day:
        return {
            "answer": "No transaction records were found for this merchant. This covers digital payments only.",
            "tools_used": [],
            "mode": "rule-based",
        }

    ref_day_str = ref_day.isoformat()
    prev_day_str = (ref_day - timedelta(days=1)).isoformat()
    tools_used = []

    # Detect specific date in message (e.g. 2020-01-01, 1 January 2020, etc.)
    target_date_str = ref_day_str
    iso_date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", message)
    if iso_date_match:
        target_date_str = iso_date_match.group(1)
    else:
        # Check text month e.g. "1 January 2020" or "Jan 2020"
        m_match = re.search(r"\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})\b", msg_lower)
        if m_match:
            months = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
                      "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
            try:
                target_date_str = f"{int(m_match.group(3)):04d}-{months[m_match.group(2)]:02d}-{int(m_match.group(1)):02d}"
            except Exception:
                pass

    # Detect Hinglish phrasing
    is_hinglish = any(k in msg_lower for k in ["aaj", "kal", "kitna", "hua", "aaya", "kam", "zyada", "ghanta"])

    # 1. Report generation request ("report", "daily report")
    if any(k in msg_lower for k in ["report", "daily report"]):
        args = {"date": target_date_str}
        res = run_tool(db, merchant_id, "generate_daily_report", args)
        tools_used.append({"name": "generate_daily_report", "args": args})

        if "error" in res:
            answer = f"Could not generate report for {target_date_str}: {res['error']}"
        else:
            answer = res.get("report_text", "")
        return {"answer": answer, "tools_used": tools_used, "mode": "rule-based"}

    # 2. Specific UTR search (12-digit number or "status", "utr")
    utr_match = re.search(r"\b(\d{12})\b", message)
    if utr_match:
        utr = utr_match.group(1)
        args = {"utr": utr}
        res = run_tool(db, merchant_id, "get_payment_status", args)
        tools_used.append({"name": "get_payment_status", "args": args})

        if res.get("found"):
            answer = (
                f"Record shows transaction {res['reference']} of {res['amount_inr']} is {res['status']} on {res['created_at_ist']}. "
                "This covers digital payments only."
            )
        else:
            answer = (
                f"No transaction record was found for reference {utr}. "
                "This covers digital payments only."
            )
        return {"answer": answer, "tools_used": tools_used, "mode": "rule-based"}

    # 3. Compare periods / lower than yesterday / kam / zyada
    compare_triggers = ["lower", "drop", "fell", "decrease", "compare", "difference", "less", "kam", "zyada", "badha"]
    if any(k in msg_lower for k in compare_triggers) or ("yesterday" in msg_lower and "today" in msg_lower) or ("kal" in msg_lower and "aaj" in msg_lower):
        date_a = prev_day_str
        date_b = ref_day_str
        # Check if message mentions specific dates
        args = {"date_a": date_a, "date_b": date_b}
        res = run_tool(db, merchant_id, "compare_periods", args)
        tools_used.append({"name": "compare_periods", "args": args})

        if "error" in res:
            answer = f"Could not compare periods: {res['error']}"
        else:
            so_far = f" so far (until {res['data_up_to_ist']})" if not res.get("day_complete") and res.get("data_up_to_ist") else ""
            driver_summary = res["driver_summary"]

            if is_hinglish:
                answer = (
                    f"{res['date_b']} ko digital collections {res['collections_b_inr']}{so_far} the, "
                    f"jabki {res['date_a']} ko {res['collections_a_inr']} the, kul badlav {res['change_inr']} ka raha. "
                    f"{driver_summary} "
                    f"Volume ka prabhav {res['volume_effect_inr']} aur average payment ka prabhav {res['ticket_effect_inr']} raha. "
                    "Worth checking: shop hours, cash payments, weather, or festivals? "
                    "This covers digital payments only."
                )
            else:
                answer = (
                    f"On {res['date_b']}, digital collections were {res['collections_b_inr']}{so_far} compared to {res['collections_a_inr']} on {res['date_a']}, a change of {res['change_inr']}. "
                    f"{driver_summary} "
                    f"The difference reflects {res['volume_effect_inr']} from payment volume and {res['ticket_effect_inr']} from average payment size. "
                    "Worth checking: shop hours, cash payments, weather, or local footfall? "
                    "This covers digital payments only."
                )
        return {"answer": answer, "tools_used": tools_used, "mode": "rule-based"}

    # 4. Hourly activity / peak hours / busy / ghanta / when / time
    if any(k in msg_lower for k in ["hour", "busy", "peak", "time", "when", "ghanta"]):
        args = {"date": target_date_str}
        res = run_tool(db, merchant_id, "get_hourly_activity", args)
        tools_used.append({"name": "get_hourly_activity", "args": args})

        if "error" in res:
            answer = f"Could not retrieve hourly activity: {res['error']}"
        else:
            peak = res["peak_hour"]
            tie_sentence = " There was a tie on payment count with another hour." if peak.get("tie_on_count") else ""

            if is_hinglish:
                answer = (
                    f"{res['date']} ko sabse zyada digital collections {peak['label']} ke dauran amount ke adhar par {peak['amount_inr']} ke sath hue across {peak['count']} successful payments.{tie_sentence} "
                    "This covers digital payments only."
                )
            else:
                answer = (
                    f"On {res['date']}, the peak activity based on amount was {peak['label']} with {peak['amount_inr']} across {peak['count']} successful payments.{tie_sentence} "
                    "This covers digital payments only."
                )
        return {"answer": answer, "tools_used": tools_used, "mode": "rule-based"}

    # 5. Daily summary (aaj, kal, kitna, hua, aaya, collection, today)
    query_date = target_date_str
    if "kal" in msg_lower and "aaj" not in msg_lower:
        query_date = prev_day_str
    elif "yesterday" in msg_lower and "today" not in msg_lower:
        query_date = prev_day_str

    args = {"date": query_date}
    res = run_tool(db, merchant_id, "get_daily_summary", args)
    tools_used.append({"name": "get_daily_summary", "args": args})

    if "error" in res:
        answer = f"Could not retrieve summary: {res['error']}"
    elif not res.get("has_data", False):
        answer = f"No transaction records were found for {query_date} in the demo history. The latest available date with data is {ref_day_str}."
    else:
        so_far = f" so far (until {res['data_up_to_ist']})" if not res.get("day_complete") and res.get("data_up_to_ist") else ""
        pending_text = f" Pending payments stand at {res['pending_inr']} across {res['pending_count']} payments." if res.get("pending_count", 0) > 0 else ""

        if is_hinglish:
            answer = (
                f"{res['date']} ko digital collections {res['collections_inr']}{so_far} rahe across {res['success_count']} successful payments, average ticket {res['avg_ticket_inr']} ke sath.{pending_text} "
                "This covers digital payments only."
            )
        else:
            answer = (
                f"On {res['date']}, digital collections were {res['collections_inr']}{so_far} across {res['success_count']} successful payments, with an average ticket of {res['avg_ticket_inr']}.{pending_text} "
                "This covers digital payments only."
            )

    return {"answer": answer, "tools_used": tools_used, "mode": "rule-based"}
