"""Unit tests for agent quality improvements (Part 6).
LLM client mocked, no external network calls.
"""
from datetime import date
from decimal import Decimal
import pytest
from unittest.mock import MagicMock, patch

from backend.analytics.compare import compute_driver_summary, compare_periods
from backend.analytics.summary import daily_summary
from backend.analytics.hourly import hourly_activity
from backend.tools.registry import run_tool, _tool_get_hourly_activity, HourlyActivityInput
from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.guard import is_grounded, strip_markdown
from backend.agent.fallback import fallback_agent
from backend.agent.agent import run_agent
from backend.db import SessionLocal
from backend.models import Transaction


# 1. driver_summary percentages sum to 100; opposite-sign effects use the 'offset' wording; zero effects handled.
def test_driver_summary_percentages_sum_to_100():
    # Both negative
    s1 = compute_driver_summary(-136674, -25000)
    assert "explain about" in s1
    # Extract percentages
    import re
    pcts = [int(p) for p in re.findall(r"(\d+)%", s1)]
    assert len(pcts) == 2
    assert sum(pcts) == 100

    # Both positive
    s2 = compute_driver_summary(50000, 30000)
    pcts2 = [int(p) for p in re.findall(r"(\d+)%", s2)]
    assert len(pcts2) == 2
    assert sum(pcts2) == 100


def test_driver_summary_opposite_sign_offset():
    # Negative volume, positive ticket
    s = compute_driver_summary(-50000, 20000)
    assert "offset" in s
    assert "%" not in s

    # Positive volume, negative ticket
    s2 = compute_driver_summary(60000, -15000)
    assert "offset" in s2
    assert "%" not in s2


def test_driver_summary_zero_effects():
    # Both zero
    assert "no change" in compute_driver_summary(0, 0)

    # Volume zero
    s_vol0 = compute_driver_summary(0, 25000)
    assert "payment volume did not change" in s_vol0
    assert "higher average payment" in s_vol0

    # Ticket zero
    s_tkt0 = compute_driver_summary(-30000, 0)
    assert "average payment did not change" in s_tkt0
    assert "fewer payments" in s_tkt0


# 2. Peak hour tie flag is set when two hours tie on count.
def test_peak_hour_tie_on_count():
    db = SessionLocal()
    try:
        # Test tool implementation directly with mocked hourly_activity
        with patch("backend.tools.registry.hourly_activity") as mock_hourly:
            # Hour 10: count 5, amount 50000 paise (₹500)
            # Hour 18: count 5, amount 90000 paise (₹900) - peak by amount
            # Other hours: 0
            mock_data = [{"hour_ist": h, "count": 0, "amount_paise": 0} for h in range(24)]
            mock_data[10] = {"hour_ist": 10, "count": 5, "amount_paise": 50000}
            mock_data[18] = {"hour_ist": 18, "count": 5, "amount_paise": 90000}
            mock_hourly.return_value = mock_data

            res = _tool_get_hourly_activity(db, 1, HourlyActivityInput(date="2026-10-30"))
            peak = res["peak_hour"]
            assert peak["peak_by"] == "amount"
            assert peak["count"] == 5
            assert peak["amount_inr"] == "₹900.00"
            assert peak["tie_on_count"] is True
            assert peak["label"] == "6-7 PM"
    finally:
        db.close()


# 3. compare_periods with a partial day returns day_complete false and compare_basis "same_hours".
def test_compare_periods_partial_day():
    db = SessionLocal()
    try:
        # Explicit up_to_hour limits the window
        res = compare_periods(db, 1, date(2026, 10, 29), date(2026, 10, 30), up_to_hour=14)
        assert res["day_complete"] is False
        assert res["compare_basis"] == "same_hours"
        assert res["data_up_to_ist"] == "14:00 IST"
    finally:
        db.close()


# 4. A date with no records returns has_data false.
def test_daily_summary_no_records_has_data_false():
    db = SessionLocal()
    try:
        past_date = date(1999, 1, 1)
        res = daily_summary(db, 1, past_date)
        assert res["has_data"] is False
        assert res["collections_paise"] == 0

        tool_res = run_tool(db, 1, "get_daily_summary", {"date": "1999-01-01"})
        assert tool_res["has_data"] is False
        assert "No transaction records found" in tool_res["message"]
    finally:
        db.close()


# 5. is_grounded accepts an answer using only tool amounts and rejects an answer with an invented amount or count.
def test_is_grounded_validator():
    tool_outputs = [{
        "date": "2026-10-30",
        "collections_inr": "₹2,170.50",
        "collections_paise": 217050,
        "success_count": 21,
        "avg_ticket_inr": "₹103.35",
        "avg_ticket_paise": 10335,
    }]

    # Valid answer using only grounded values
    valid_ans = "On 2026-10-30, digital collections were ₹2,170.50 across 21 successful payments with average ticket of ₹103.35."
    assert is_grounded(valid_ans, tool_outputs) is True

    # Invented rupee amount
    invalid_amt = "On 2026-10-30, digital collections were ₹9,999.00 across 21 successful payments."
    assert is_grounded(invalid_amt, tool_outputs) is False

    # Invented payment count
    invalid_cnt = "On 2026-10-30, digital collections were ₹2,170.50 across 99 payments."
    assert is_grounded(invalid_cnt, tool_outputs) is False


# 6. A mocked answer containing markdown is stripped to plain text.
def test_strip_markdown():
    markdown_text = (
        "### Daily Collections\n"
        "| Date | Amount |\n"
        "|---|---|\n"
        "| 2026-10-30 | ₹2,170.50 |\n"
        "- **Total collections**: ₹2,170.50 across 21 payments.\n"
        "- *Status*: Verified."
    )
    cleaned = strip_markdown(markdown_text)
    assert "#" not in cleaned
    assert "|" not in cleaned
    assert "**" not in cleaned
    assert "*" not in cleaned
    assert "-" not in cleaned.split(" ")[0]  # No leading bullet
    assert "Daily Collections" in cleaned
    assert "₹2,170.50 across 21 payments" in cleaned


# 7. Fallback answers contain the closing line and the volume/ticket amounts.
def test_fallback_answers_structure():
    db = SessionLocal()
    try:
        # Comparison fallback
        res_comp = fallback_agent(db, 1, "Why were my collections lower than yesterday?")
        ans_comp = res_comp["answer"]
        assert "This covers digital payments only." in ans_comp
        assert "volume" in ans_comp.lower()
        assert "average" in ans_comp.lower()
        assert "Worth checking:" in ans_comp

        # Hourly fallback
        res_hour = fallback_agent(db, 1, "When do I get the most payments?")
        ans_hour = res_hour["answer"]
        assert "This covers digital payments only." in ans_hour
        assert "based on amount" in ans_hour

        # Hinglish fallback
        res_hi = fallback_agent(db, 1, "aaj kitna hua?")
        ans_hi = res_hi["answer"]
        assert "This covers digital payments only." in ans_hi
    finally:
        db.close()


# 8. The system prompt constant contains the strings "Never calculate", "Worth checking:" and "This covers digital payments only."
def test_system_prompt_strings():
    assert "Never calculate" in SYSTEM_PROMPT
    assert "Worth checking:" in SYSTEM_PROMPT
    assert "This covers digital payments only." in SYSTEM_PROMPT


# 9. Cross-merchant isolation still holds for every tool.
def test_cross_merchant_isolation_for_all_tools():
    db = SessionLocal()
    try:
        # Test daily summary
        res1 = run_tool(db, 1, "get_daily_summary", {"date": "2026-10-30"})
        res2 = run_tool(db, 2, "get_daily_summary", {"date": "2026-10-30"})
        assert res1["collections_paise"] != res2["collections_paise"]

        # Test payment status with a real transaction from merchant 1
        tx1 = db.query(Transaction).filter_by(merchant_id=1).first()
        assert tx1 is not None

        # Merchant 1 finds it
        status_m1 = run_tool(db, 1, "get_payment_status", {"utr": tx1.reference})
        assert status_m1["found"] is True

        # Merchant 2 cannot see Merchant 1's transaction
        status_m2 = run_tool(db, 2, "get_payment_status", {"utr": tx1.reference})
        assert status_m2["found"] is False

        # Test compare periods
        comp1 = run_tool(db, 1, "compare_periods", {"date_a": "2026-10-29", "date_b": "2026-10-30"})
        comp2 = run_tool(db, 2, "compare_periods", {"date_a": "2026-10-29", "date_b": "2026-10-30"})
        assert comp1["collections_a_paise"] != comp2["collections_a_paise"]
    finally:
        db.close()

