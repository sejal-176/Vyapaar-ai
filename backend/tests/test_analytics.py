"""Tests for Layer 2: Analytics package."""
from datetime import date, datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base
from backend.models import Merchant, Transaction
from backend.core.timeutil import to_utc
from backend.analytics import (
    latest_data_day,
    daily_summary,
    compare_periods,
    hourly_activity,
    collection_trend,
)


@pytest.fixture
def db_session():
    """In-memory SQLite database session seeded with test fixture."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Merchants
    m1 = Merchant(id=1, name="Sharma Tea Stall", business_type="tea stall", vpa="sharmatea@demo")
    m2 = Merchant(id=2, name="Gupta Kirana Store", business_type="kirana", vpa="guptakirana@demo")
    session.add(m1)
    session.add(m2)
    session.commit()

    # 8-transaction fixture for Merchant 1:
    # Day A: 2026-10-24 IST
    # Tx 1: 09:00 IST -> 03:30 UTC. 4000 paise (₹40), SUCCESS
    # Tx 2: 10:00 IST -> 04:30 UTC. 6000 paise (₹60), SUCCESS
    # Tx 3: 11:00 IST -> 05:30 UTC. 2000 paise (₹20), PENDING
    # Tx 4: 12:00 IST -> 06:30 UTC. 3000 paise (₹30), FAILED
    # Tx 5: 13:00 IST -> 07:30 UTC. 1000 paise (₹10), REFUNDED (REFUND)
    #
    # Day B: 2026-10-25 IST
    # Tx 6: 00:30 IST -> 19:00 UTC on 2026-10-24. 3000 paise (₹30), SUCCESS (IST boundary case!)
    # Tx 7: 10:00 IST -> 04:30 UTC on 2026-10-25. 3000 paise (₹30), SUCCESS
    # Tx 8: 15:00 IST -> 09:30 UTC on 2026-10-25. 3000 paise (₹30), SUCCESS

    fixture_txns = [
        # Day A
        Transaction(
            merchant_id=1,
            reference="100000000001",
            amount_paise=4000,
            status="SUCCESS",
            txn_type="PAYMENT",
            created_at_utc=to_utc(datetime(2026, 10, 24, 9, 0, 0)).replace(tzinfo=None),
        ),
        Transaction(
            merchant_id=1,
            reference="100000000002",
            amount_paise=6000,
            status="SUCCESS",
            txn_type="PAYMENT",
            created_at_utc=to_utc(datetime(2026, 10, 24, 10, 0, 0)).replace(tzinfo=None),
        ),
        Transaction(
            merchant_id=1,
            reference="100000000003",
            amount_paise=2000,
            status="PENDING",
            txn_type="PAYMENT",
            created_at_utc=to_utc(datetime(2026, 10, 24, 11, 0, 0)).replace(tzinfo=None),
        ),
        Transaction(
            merchant_id=1,
            reference="100000000004",
            amount_paise=3000,
            status="FAILED",
            txn_type="PAYMENT",
            created_at_utc=to_utc(datetime(2026, 10, 24, 12, 0, 0)).replace(tzinfo=None),
        ),
        Transaction(
            merchant_id=1,
            reference="100000000005",
            amount_paise=1000,
            status="REFUNDED",
            txn_type="REFUND",
            created_at_utc=to_utc(datetime(2026, 10, 24, 13, 0, 0)).replace(tzinfo=None),
        ),
        # Day B
        Transaction(
            merchant_id=1,
            reference="100000000006",
            amount_paise=3000,
            status="SUCCESS",
            txn_type="PAYMENT",
            created_at_utc=to_utc(datetime(2026, 10, 25, 0, 30, 0)).replace(tzinfo=None),
        ),
        Transaction(
            merchant_id=1,
            reference="100000000007",
            amount_paise=3000,
            status="SUCCESS",
            txn_type="PAYMENT",
            created_at_utc=to_utc(datetime(2026, 10, 25, 10, 0, 0)).replace(tzinfo=None),
        ),
        Transaction(
            merchant_id=1,
            reference="100000000008",
            amount_paise=3000,
            status="SUCCESS",
            txn_type="PAYMENT",
            created_at_utc=to_utc(datetime(2026, 10, 25, 15, 0, 0)).replace(tzinfo=None),
        ),
    ]
    for tx in fixture_txns:
        session.add(tx)
    session.commit()

    yield session
    session.close()


def test_latest_data_day(db_session):
    # Tx 8 is at 15:00 IST on 2026-10-25
    ref_day = latest_data_day(db_session, merchant_id=1)
    assert ref_day == date(2026, 10, 25)

    # Merchant 2 has no data
    assert latest_data_day(db_session, merchant_id=2) is None


def test_daily_summary_hand_computed(db_session):
    # Day A
    sum_a = daily_summary(db_session, merchant_id=1, day=date(2026, 10, 24))
    assert sum_a["date"] == "2026-10-24"
    assert sum_a["collections_paise"] == 10000  # 4000 + 6000
    assert sum_a["success_count"] == 2
    assert sum_a["pending_count"] == 1
    assert sum_a["failed_count"] == 1
    assert sum_a["refunded_count"] == 1
    assert sum_a["refund_total_paise"] == 1000
    assert sum_a["avg_ticket_paise"] == 5000

    # Day B (verifying Tx 6 at 00:30 IST is correctly in Day B)
    sum_b = daily_summary(db_session, merchant_id=1, day=date(2026, 10, 25))
    assert sum_b["date"] == "2026-10-25"
    assert sum_b["collections_paise"] == 9000  # 3000 * 3
    assert sum_b["success_count"] == 3
    assert sum_b["pending_count"] == 0
    assert sum_b["failed_count"] == 0
    assert sum_b["refunded_count"] == 0
    assert sum_b["avg_ticket_paise"] == 3000


def test_ist_boundary_case(db_session):
    """Tx 6 is at 2026-10-25 00:30:00 IST.
    In UTC, it is 2026-10-24 19:00:00 UTC (previous UTC day).
    It must be included in 2026-10-25 IST, and NOT in 2026-10-24 IST.
    """
    sum_a = daily_summary(db_session, merchant_id=1, day=date(2026, 10, 24))
    sum_b = daily_summary(db_session, merchant_id=1, day=date(2026, 10, 25))

    # Tx 6 reference is 100000000006
    # Day A has 2 success txns (Tx 1 and Tx 2)
    assert sum_a["success_count"] == 2
    # Day B has 3 success txns (Tx 6, Tx 7, Tx 8)
    assert sum_b["success_count"] == 3


def test_compare_periods_and_exact_sum(db_session):
    cmp_res = compare_periods(
        db_session,
        merchant_id=1,
        day_a=date(2026, 10, 24),
        day_b=date(2026, 10, 25),
    )

    # Hand-computed expectations
    assert cmp_res["delta_collections_paise"] == -1000  # 9000 - 10000
    assert cmp_res["delta_success_count"] == 1  # 3 - 2
    assert cmp_res["delta_avg_ticket_paise"] == -2000  # 3000 - 5000
    assert cmp_res["volume_effect"] == 5000  # (3 - 2) * 5000
    assert cmp_res["ticket_effect"] == -6000  # -1000 - 5000

    # Non-negotiable rule: volume_effect + ticket_effect must sum EXACTLY to delta_collections_paise
    assert cmp_res["volume_effect"] + cmp_res["ticket_effect"] == cmp_res["delta_collections_paise"]
    assert cmp_res["main_driver"] == "ticket_size"
    assert cmp_res["note"] is None


def test_compare_periods_with_up_to_hour(db_session):
    # Only include transactions up to 10:00 IST
    # Day A: Tx 1 (09:00) and Tx 2 (10:00) included -> 10000 paise, count 2
    # Day B: Tx 6 (00:30) and Tx 7 (10:00) included -> 6000 paise, count 2 (Tx 8 at 15:00 excluded)
    cmp_res = compare_periods(
        db_session,
        merchant_id=1,
        day_a=date(2026, 10, 24),
        day_b=date(2026, 10, 25),
        up_to_hour=10,
    )
    assert cmp_res["day_b"]["success_count"] == 2
    assert cmp_res["day_b"]["collections_paise"] == 6000
    assert cmp_res["delta_collections_paise"] == -4000
    assert cmp_res["volume_effect"] + cmp_res["ticket_effect"] == cmp_res["delta_collections_paise"]
    assert "up to hour 10:00 IST" in cmp_res["note"]


def test_empty_day_handling(db_session):
    """Empty days must return 0 collections and 0 avg_ticket with no division by zero."""
    empty_day = date(2026, 10, 20)
    summary = daily_summary(db_session, merchant_id=1, day=empty_day)
    assert summary["collections_paise"] == 0
    assert summary["success_count"] == 0
    assert summary["avg_ticket_paise"] == 0

    # Compare an empty day with day_a
    cmp_res = compare_periods(
        db_session,
        merchant_id=1,
        day_a=empty_day,
        day_b=date(2026, 10, 24),
    )
    assert cmp_res["delta_collections_paise"] == 10000
    assert cmp_res["volume_effect"] + cmp_res["ticket_effect"] == 10000


def test_hourly_activity(db_session):
    hourly = hourly_activity(db_session, merchant_id=1, day=date(2026, 10, 25))
    assert len(hourly) == 24

    # Hour 0: Tx 6 at 00:30 IST
    assert hourly[0]["count"] == 1
    assert hourly[0]["amount_paise"] == 3000

    # Hour 10: Tx 7 at 10:00 IST
    assert hourly[10]["count"] == 1
    assert hourly[10]["amount_paise"] == 3000

    # Hour 15: Tx 8 at 15:00 IST
    assert hourly[15]["count"] == 1
    assert hourly[15]["amount_paise"] == 3000

    # Other hours should be 0
    assert hourly[1]["count"] == 0
    assert hourly[1]["amount_paise"] == 0


def test_collection_trend(db_session):
    trend = collection_trend(db_session, merchant_id=1, days=3, end_day=date(2026, 10, 25))
    assert len(trend) == 3
    assert trend[0]["date"] == "2026-10-23"
    assert trend[0]["collections_paise"] == 0
    assert trend[1]["date"] == "2026-10-24"
    assert trend[1]["collections_paise"] == 10000
    assert trend[2]["date"] == "2026-10-25"
    assert trend[2]["collections_paise"] == 9000


def test_cross_merchant_isolation_in_analytics(db_session):
    """Rule 11: Merchant 2 must see 0 collections even though Merchant 1 has transactions."""
    sum_m2 = daily_summary(db_session, merchant_id=2, day=date(2026, 10, 24))
    assert sum_m2["collections_paise"] == 0
    assert sum_m2["success_count"] == 0

    hourly_m2 = hourly_activity(db_session, merchant_id=2, day=date(2026, 10, 24))
    assert all(h["count"] == 0 for h in hourly_m2)

