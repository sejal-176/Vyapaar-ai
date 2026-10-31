"""Tests for Part 6: SMS Scam Checker (Claims extraction, Ledger check, Signals, Safety)."""
from datetime import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.db import Base, SessionLocal
from backend.models import Merchant, Transaction, SMSCheck
from backend.core.timeutil import to_utc
from backend.core.money import format_inr
from backend.scam.claims import extract_claim
from backend.scam.check import check_claim
from backend.scam.signals import detect_signals
from backend.main import app

client = TestClient(app)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def db_session():
    """In-memory SQLite database session for isolated scam checker tests."""
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

    # Merchant 1 Transactions
    # 1. SUCCESS payment (amount 10000 paise = Rs 100)
    tx1 = Transaction(
        merchant_id=1,
        reference="111111111111",
        amount_paise=10000,
        status="SUCCESS",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 10, 0, 0)).replace(tzinfo=None),
    )
    # 2. PENDING payment
    tx2 = Transaction(
        merchant_id=1,
        reference="222222222222",
        amount_paise=5000,
        status="PENDING",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 11, 0, 0)).replace(tzinfo=None),
    )
    # 3. FAILED payment
    tx3 = Transaction(
        merchant_id=1,
        reference="333333333333",
        amount_paise=6000,
        status="FAILED",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 12, 0, 0)).replace(tzinfo=None),
    )
    # 4. REFUNDED payment
    tx4 = Transaction(
        merchant_id=1,
        reference="444444444444",
        amount_paise=7000,
        status="REFUNDED",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 13, 0, 0)).replace(tzinfo=None),
    )
    # 5. SUCCESS REFUND transaction
    tx5 = Transaction(
        merchant_id=1,
        reference="555555555555",
        amount_paise=8000,
        status="SUCCESS",
        txn_type="REFUND",
        created_at_utc=to_utc(datetime(2026, 10, 25, 14, 0, 0)).replace(tzinfo=None),
    )
    # 6. Ambiguous candidates: two payments of Rs 25 (2500 paise)
    tx6a = Transaction(
        merchant_id=1,
        reference="666666666666",
        amount_paise=2500,
        status="SUCCESS",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 15, 0, 0)).replace(tzinfo=None),
    )
    tx6b = Transaction(
        merchant_id=1,
        reference="666666666667",
        amount_paise=2500,
        status="SUCCESS",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 15, 30, 0)).replace(tzinfo=None),
    )

    # Merchant 2 Transactions (Isolation test)
    tx_m2 = Transaction(
        merchant_id=2,
        reference="888888888888",
        amount_paise=9000,
        status="SUCCESS",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 16, 0, 0)).replace(tzinfo=None),
    )
    tx_m2_same_amt = Transaction(
        merchant_id=2,
        reference="999999999999",
        amount_paise=10000,
        status="SUCCESS",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 10, 0, 0)).replace(tzinfo=None),
    )

    session.add_all([tx1, tx2, tx3, tx4, tx5, tx6a, tx6b, tx_m2, tx_m2_same_amt])
    session.commit()

    yield session
    session.close()


# -----------------------------------------------------------------------------
# Part 1 Tests: Claim Extraction
# -----------------------------------------------------------------------------
def test_claim_amount_formats():
    c1 = extract_claim("Rs 500 received in your account")
    assert c1.amount_paise == 50000
    assert format_inr(c1.amount_paise) == "₹500.00"

    c2 = extract_claim("Credited Rs. 1,250.50 to your A/c")
    assert c2.amount_paise == 125050

    c3 = extract_claim("INR 45 paid successfully")
    assert c3.amount_paise == 4500

    c4 = extract_claim("₹ 750 added to balance")
    assert c4.amount_paise == 75000


def test_claim_utr_formats():
    c1 = extract_claim("Payment of Rs 100 with 123456789012 completed")
    assert c1.utr == "123456789012"

    c2 = extract_claim("Rs 200 credited. UTR: 987654321098")
    assert c2.utr == "987654321098"

    c3 = extract_claim("Ref No 112233445566 received")
    assert c3.utr == "112233445566"

    c4 = extract_claim("Txn ID: 998877665544 credited")
    assert c4.utr == "998877665544"

    c5 = extract_claim("RRN 445566778899 success")
    assert c5.utr == "445566778899"


def test_claim_directions():
    assert extract_claim("Rs 100 credited").direction == "credit"
    assert extract_claim("Rs 100 received").direction == "credit"
    assert extract_claim("Rs 100 deposited").direction == "credit"
    assert extract_claim("Rs 100 added to your account").direction == "credit"
    assert extract_claim("Rs 100 debited").direction == "debit"
    assert extract_claim("Rs 100 paid").direction == "debit"
    assert extract_claim("Rs 100 sent").direction == "debit"
    assert extract_claim("Rs 100 withdrawn").direction == "debit"
    assert extract_claim("Rs 100 refund").direction == "refund"
    assert extract_claim("Rs 100 reversed").direction == "refund"

    # Hinglish
    assert extract_claim("Rs 100 aaya").direction == "credit"
    assert extract_claim("Rs 100 jama").direction == "credit"
    assert extract_claim("Rs 100 kat gaya").direction == "debit"
    assert extract_claim("Rs 100 wapas mila").direction == "refund"


def test_claim_counterparty():
    c1 = extract_claim("Rs 500 received from rahul@okhdfcbank")
    assert c1.counterparty == "rahul@okhdfcbank"

    c2 = extract_claim("Rs 500 sent by Amit Sharma")
    assert c2.counterparty == "Amit Sharma"


def test_claim_timestamp():
    c = extract_claim("Rs 500 credited on 25-10-2026 14:30:00")
    assert c.timestamp is not None
    assert "25-10-2026 14:30:00" in c.timestamp


def test_claim_multiple_amounts():
    msg = "Old bal Rs 200. Credited Rs 500. New bal Rs 700."
    c = extract_claim(msg)
    assert c.amount_paise == 50000  # First amount after direction
    assert len(c.raw_amounts_found) == 3


def test_claim_missing_fields():
    c = extract_claim("Good morning have a nice day")
    assert c.direction == "unknown"
    assert c.amount_paise is None
    assert c.utr is None
    assert c.timestamp is None
    assert c.counterparty is None


# -----------------------------------------------------------------------------
# Part 2 Tests: Ledger Decision Table
# -----------------------------------------------------------------------------
def test_ledger_genuine_match(db_session):
    claim = extract_claim("Credited Rs 100 UTR 111111111111")
    res = check_claim(db_session, 1, claim)
    assert res["outcome"] == "VERIFIED"
    assert "This transaction exists in your records" in res["reason"]
    # Wording rule: never say "genuine message"
    assert "genuine message" not in str(res).lower()


def test_ledger_wrong_amount(db_session):
    claim = extract_claim("Credited Rs 200 UTR 111111111111")
    res = check_claim(db_session, 1, claim)
    assert res["outcome"] == "MISMATCH"
    assert "Amount in message differs from our record" in res["reason"]


def test_ledger_unknown_utr(db_session):
    claim = extract_claim("Credited Rs 100 UTR 999111222333")
    res = check_claim(db_session, 1, claim)
    assert res["outcome"] == "UNVERIFIED"
    assert "No matching transaction record" in res["reason"]


def test_ledger_pending_utr(db_session):
    claim = extract_claim("Credited Rs 50 UTR 222222222222")
    res = check_claim(db_session, 1, claim)
    assert res["outcome"] == "UNVERIFIED"
    assert "Payment is still pending in our records" in res["reason"]


def test_ledger_failed_utr(db_session):
    claim = extract_claim("Credited Rs 60 UTR 333333333333")
    res = check_claim(db_session, 1, claim)
    assert res["outcome"] == "MISMATCH"
    assert "Our record shows this payment as failed/refunded" in res["reason"]


def test_ledger_refunded_utr(db_session):
    claim = extract_claim("Credited Rs 70 UTR 444444444444")
    res = check_claim(db_session, 1, claim)
    assert res["outcome"] == "MISMATCH"
    assert "Our record shows this payment as failed/refunded" in res["reason"]


def test_ledger_direction_conflict(db_session):
    # Claiming refund on a PAYMENT transaction
    claim1 = extract_claim("Refund Rs 100 UTR 111111111111")
    res1 = check_claim(db_session, 1, claim1)
    assert res1["outcome"] == "MISMATCH"
    assert "Direction differs from our record" in res1["reason"]

    # Claiming credit on a REFUND transaction
    claim2 = extract_claim("Credited Rs 80 UTR 555555555555")
    res2 = check_claim(db_session, 1, claim2)
    assert res2["outcome"] == "MISMATCH"
    assert "Direction differs from our record" in res2["reason"]


def test_ledger_candidate_one_match(db_session):
    # No UTR, Rs 100 matches tx1 exactly on latest data day (2026-10-25)
    claim = extract_claim("Credited Rs 100 to your account")
    res = check_claim(db_session, 1, claim)
    assert res["outcome"] == "UNVERIFIED"
    assert res["possible_match"] is not None
    assert res["possible_match"]["reference"] == "111111111111"


def test_ledger_candidate_multiple_matches(db_session):
    # No UTR, Rs 25 matches two transactions (tx6a and tx6b)
    claim = extract_claim("Credited Rs 25 received")
    res = check_claim(db_session, 1, claim)
    assert res["outcome"] == "UNVERIFIED"
    assert "Several possible matches" in res["reason"]
    assert len(res["candidates"]) == 2


def test_ledger_candidate_zero_matches(db_session):
    claim = extract_claim("Credited Rs 999 received")
    res = check_claim(db_session, 1, claim)
    assert res["outcome"] == "UNVERIFIED"
    assert "No matching transaction record" in res["reason"]


def test_ledger_not_checkable(db_session):
    claim = extract_claim("Thank you for visiting our store today")
    res = check_claim(db_session, 1, claim)
    assert res["outcome"] == "NOT_CHECKABLE"
    assert "No payment claim found in this message" in res["reason"]


# -----------------------------------------------------------------------------
# Part 3 & Isolation Tests
# -----------------------------------------------------------------------------
def test_cross_merchant_isolation(db_session):
    # Merchant 2 has tx_m2 (UTR 888888888888, Rs 90)
    # Checking as Merchant 1 MUST return UNVERIFIED (never finds m2's record)
    claim = extract_claim("Credited Rs 90 UTR 888888888888")
    res = check_claim(db_session, 1, claim)
    assert res["outcome"] == "UNVERIFIED"
    assert res["ledger_record"] is None

    # Candidate search for Rs 90 as Merchant 1 must find 0 matches
    claim_cand = extract_claim("Credited Rs 90")
    res_cand = check_claim(db_session, 1, claim_cand)
    assert res_cand["outcome"] == "UNVERIFIED"
    assert len(res_cand["candidates"]) == 0


def test_warning_signals_secrets():
    signals = detect_signals("Please share your OTP to accept payment")
    cats = [s["category"] for s in signals]
    assert "secrets" in cats


def test_warning_signals_pin_trick():
    signals = detect_signals("Enter your UPI PIN to receive money in your account")
    cats = [s["category"] for s in signals]
    assert "pin_trick" in cats


def test_warning_signals_bad_links():
    s1 = detect_signals("Click here http://bit.ly/claim-prize to receive funds")
    cats1 = [s["category"] for s in s1]
    assert "bad_link" in cats1

    s2 = detect_signals("Verify account at http://192.168.1.1/login")
    cats2 = [s["category"] for s in s2]
    assert "bad_link" in cats2


def test_warning_signals_official_domain():
    # Official domain should not be flagged as bad_link
    signals = detect_signals("Check details on https://paytm.com/help")
    cats = [s["category"] for s in signals]
    assert "bad_link" not in cats


def test_warning_signals_hinglish_urgency_secrets():
    signals = detect_signals("turant OTP bhejo nahi to account band ho jayega")
    cats = [s["category"] for s in signals]
    assert "urgency" in cats
    assert "secrets" in cats


# -----------------------------------------------------------------------------
# Part 5: Safety and API Tests
# -----------------------------------------------------------------------------
def test_api_html_handled_as_plain_text():
    # Script tag should be treated purely as string, without causing failure or execution
    payload = {"text": "<script>alert('hack')</script> Rs 100 received"}
    res = client.post("/api/scam-check?merchant_id=1", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["claim"]["amount_paise"] == 10000


def test_api_text_length_exceeded():
    long_text = "a" * 2001
    res = client.post("/api/scam-check?merchant_id=1", json={"text": long_text})
    assert res.status_code == 400


def test_api_empty_text():
    res = client.post("/api/scam-check?merchant_id=1", json={"text": "   "})
    assert res.status_code == 400


def test_api_no_percentages_or_scores():
    # Verify no % sign or confidence scores in entire API response
    payload = {"text": "Rs 500 received from customer"}
    res = client.post("/api/scam-check?merchant_id=1", json=payload)
    assert res.status_code == 200
    raw_json_str = res.text
    assert "%" not in raw_json_str
    assert "confidence" not in raw_json_str.lower()


def test_api_verified_never_says_genuine_message():
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter(Transaction.merchant_id == 1, Transaction.status == "SUCCESS").first()
        assert tx is not None
        inr_val = tx.amount_paise / 100
        payload = {"text": f"Credited Rs {inr_val:.2f} UTR {tx.reference}"}
        res = client.post("/api/scam-check?merchant_id=1", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["ledger_check"]["outcome"] == "VERIFIED"
        assert "genuine message" not in res.text.lower()
    finally:
        db.close()


def test_api_raw_text_not_stored_in_db():
    secret_content = "SuperSensitiveMerchantNote987"
    payload = {"text": f"Credited Rs 100 UTR 111111111111 {secret_content}"}
    res = client.post("/api/scam-check?merchant_id=1", json=payload)
    assert res.status_code == 200

    db = SessionLocal()
    try:
        row = db.query(SMSCheck).order_by(SMSCheck.id.desc()).first()
        assert row is not None
        assert row.text_hash is not None
        assert len(row.text_hash) == 64
        # Check all attributes of row to ensure secret_content is nowhere stored
        for col in ["id", "merchant_id", "text_hash", "outcome", "signal_categories"]:
            val = getattr(row, col)
            assert secret_content not in str(val)
    finally:
        db.close()
