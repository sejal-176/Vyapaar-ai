"""Tests for Layer 0: Core utils (money, normalize, timeutil)."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from backend.core.money import to_paise, format_inr
from backend.core.normalize import normalize_status
from backend.core.timeutil import to_utc, to_ist, ist_day_bounds_utc, IST, UTC


def test_to_paise():
    # PLAN.md test specs
    assert to_paise("₹1,250.50") == 125050
    assert to_paise("Rs 40") == 4000
    assert to_paise("Rs. 40") == 4000
    assert to_paise("INR 100") == 10000
    assert to_paise("abc") is None
    assert to_paise("-5") == -500
    assert to_paise("") is None
    assert to_paise(None) is None
    assert to_paise("  ₹ 500.25 ") == 50025
    assert to_paise(10) == 1000


def test_format_inr():
    assert format_inr(125050) == "₹1,250.50"
    assert format_inr(4000) == "₹40.00"
    assert format_inr(0) == "₹0.00"
    assert format_inr(12500000) == "₹1,25,000.00"
    assert format_inr(-500) == "-₹5.00"


def test_normalize_status_variants():
    # Success variants
    for variant in ["success", "SUCCESS", "successful", "completed", "paid", "done", "  Paid  "]:
        assert normalize_status(variant) == "SUCCESS"

    # Pending variants
    for variant in ["pending", "PENDING", "processing", "in progress", "in-progress"]:
        assert normalize_status(variant) == "PENDING"

    # Failed variants
    for variant in ["failed", "FAILED", "declined", "failure"]:
        assert normalize_status(variant) == "FAILED"

    # Refunded variants
    for variant in ["refunded", "REFUNDED", "refund", "reversed"]:
        assert normalize_status(variant) == "REFUNDED"

    # Unrecognized / invalid
    assert normalize_status("chargeback") is None
    assert normalize_status("unknown") is None
    assert normalize_status("") is None
    assert normalize_status(None) is None


def test_timeutil_ist_utc_roundtrip():
    # Naive dt assumed IST: 10:30 IST is 05:00 UTC (10:30 - 5:30)
    naive_ist = datetime(2026, 10, 25, 10, 30, 0)
    utc_dt = to_utc(naive_ist)
    assert utc_dt.hour == 5
    assert utc_dt.minute == 0
    assert utc_dt.tzinfo == timezone.utc

    # Convert back to IST
    ist_dt = to_ist(utc_dt)
    assert ist_dt.hour == 10
    assert ist_dt.minute == 30
    assert ist_dt.tzinfo == IST

    # Aware UTC dt to IST: 18:30 UTC + 5:30 = 00:00 next day IST
    utc_aware = datetime(2026, 10, 25, 18, 30, 0, tzinfo=UTC)
    ist_aware = to_ist(utc_aware)
    assert ist_aware.day == 26
    assert ist_aware.hour == 0
    assert ist_aware.minute == 0


def test_ist_day_bounds_utc():
    target_date = date(2026, 10, 25)
    start_utc, end_utc = ist_day_bounds_utc(target_date)

    # 2026-10-25 00:00:00 IST is 2026-10-24 18:30:00 UTC
    assert start_utc.year == 2026
    assert start_utc.month == 10
    assert start_utc.day == 24
    assert start_utc.hour == 18
    assert start_utc.minute == 30
    assert start_utc.tzinfo == timezone.utc

    # 2026-10-26 00:00:00 IST is 2026-10-25 18:30:00 UTC
    assert end_utc.year == 2026
    assert end_utc.month == 10
    assert end_utc.day == 25
    assert end_utc.hour == 18
    assert end_utc.minute == 30
    assert end_utc.tzinfo == timezone.utc

    # Exactly 24 hours span
    assert (end_utc - start_utc).total_seconds() == 86400
