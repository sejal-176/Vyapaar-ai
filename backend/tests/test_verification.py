"""Tests for Layer 3: Deterministic verification and preprocessing."""
from datetime import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base
from backend.models import Merchant, Transaction, Submission
from backend.core.timeutil import to_utc
from backend.verification.extract import ExtractedFields
from backend.verification.ledger import get_transaction
from backend.verification.verify import verify
from backend.verification.preprocess import preprocess


@pytest.fixture
def db_session():
    """In-memory SQLite database session for isolated verification tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create demo merchants
    m1 = Merchant(id=1, name="Sharma Tea Stall", business_type="tea stall", vpa="sharmatea@demo")
    m2 = Merchant(id=2, name="Gupta Kirana Store", business_type="kirana", vpa="guptakirana@demo")
    session.add(m1)
    session.add(m2)
    session.commit()

    # Seed test transactions for merchant 1
    # 1. SUCCESS payment (amount 10000 paise = Rs 100)
    tx_success = Transaction(
        merchant_id=1,
        reference="111111111111",
        amount_paise=10000,
        status="SUCCESS",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 10, 0, 0)).replace(tzinfo=None),
    )
    # 2. PENDING payment
    tx_pending = Transaction(
        merchant_id=1,
        reference="222222222222",
        amount_paise=5000,
        status="PENDING",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 11, 0, 0)).replace(tzinfo=None),
    )
    # 3. FAILED payment
    tx_failed = Transaction(
        merchant_id=1,
        reference="333333333333",
        amount_paise=6000,
        status="FAILED",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 12, 0, 0)).replace(tzinfo=None),
    )
    # 4. REFUNDED payment
    tx_refunded = Transaction(
        merchant_id=1,
        reference="444444444444",
        amount_paise=7000,
        status="REFUNDED",
        txn_type="REFUND",
        created_at_utc=to_utc(datetime(2026, 10, 25, 13, 0, 0)).replace(tzinfo=None),
    )
    # Transaction for Merchant 2 (for cross-merchant isolation)
    tx_m2 = Transaction(
        merchant_id=2,
        reference="555555555555",
        amount_paise=12000,
        status="SUCCESS",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 14, 0, 0)).replace(tzinfo=None),
    )

    session.add_all([tx_success, tx_pending, tx_failed, tx_refunded, tx_m2])
    session.commit()

    yield session
    session.close()


def test_decision_step_2_no_utr(db_session):
    """Step 2: No UTR extracted -> UNVERIFIED."""
    fields = ExtractedFields(utr=None, amount_paise=10000, recipient="Sharma Tea Stall")
    res = verify(db_session, merchant_id=1, fields=fields, image_hash="hash_step2")
    assert res["outcome"] == "UNVERIFIED"
    assert "Not enough information in the image" in res["reason"]


def test_decision_step_4_record_none(db_session):
    """Step 4: UTR not found in merchant ledger -> UNVERIFIED."""
    fields = ExtractedFields(utr="999999999999", amount_paise=10000, recipient="Sharma Tea Stall")
    res = verify(db_session, merchant_id=1, fields=fields, image_hash="hash_step4")
    assert res["outcome"] == "UNVERIFIED"
    assert "No matching transaction record" in res["reason"]


def test_decision_step_5_status_pending(db_session):
    """Step 5: Record status is PENDING -> UNVERIFIED."""
    fields = ExtractedFields(utr="222222222222", amount_paise=5000, recipient="Sharma Tea Stall")
    res = verify(db_session, merchant_id=1, fields=fields, image_hash="hash_step5")
    assert res["outcome"] == "UNVERIFIED"
    assert "pending" in res["reason"].lower()


def test_decision_step_6_status_failed(db_session):
    """Step 6: Record status is FAILED -> MISMATCH."""
    fields = ExtractedFields(utr="333333333333", amount_paise=6000, recipient="Sharma Tea Stall")
    res = verify(db_session, merchant_id=1, fields=fields, image_hash="hash_step6a")
    assert res["outcome"] == "MISMATCH"
    assert "failed" in res["reason"].lower()
    assert "status" in res["conflicting_fields"]


def test_decision_step_6_status_refunded(db_session):
    """Step 6: Record status is REFUNDED -> MISMATCH."""
    fields = ExtractedFields(utr="444444444444", amount_paise=7000, recipient="Sharma Tea Stall")
    res = verify(db_session, merchant_id=1, fields=fields, image_hash="hash_step6b")
    assert res["outcome"] == "MISMATCH"
    assert "failed/refunded" in res["reason"].lower()
    assert "status" in res["conflicting_fields"]


def test_decision_step_7_amount_mismatch(db_session):
    """Step 7: Amount extracted != record amount -> MISMATCH."""
    # Ledger amount is 10000 paise (Rs 100); screenshot shows 15000 paise (Rs 150)
    fields = ExtractedFields(utr="111111111111", amount_paise=15000, recipient="Sharma Tea Stall")
    res = verify(db_session, merchant_id=1, fields=fields, image_hash="hash_step7")
    assert res["outcome"] == "MISMATCH"
    assert "Amount in image differs" in res["reason"]
    assert "amount" in res["conflicting_fields"]


def test_decision_step_8_recipient_mismatch(db_session):
    """Step 8: Recipient does not match merchant name or VPA -> MISMATCH."""
    fields = ExtractedFields(utr="111111111111", amount_paise=10000, recipient="Wrong Merchant Store")
    res = verify(db_session, merchant_id=1, fields=fields, image_hash="hash_step8")
    assert res["outcome"] == "MISMATCH"
    assert "Recipient differs" in res["reason"]
    assert "recipient" in res["conflicting_fields"]


def test_decision_step_9_verified_full_match(db_session):
    """Step 9: Real SUCCESS row with matching amount and recipient -> VERIFIED."""
    fields = ExtractedFields(utr="111111111111", amount_paise=10000, recipient="Sharma Tea Stall")
    res = verify(db_session, merchant_id=1, fields=fields, image_hash="hash_step9a")
    assert res["outcome"] == "VERIFIED"
    assert "utr" in res["matched_fields"]
    assert "amount" in res["matched_fields"]
    assert len(res["conflicting_fields"]) == 0


def test_decision_step_9_verified_amount_not_extracted(db_session):
    """Step 9 note: Amount not extracted, but UTR matches SUCCESS row -> VERIFIED with note."""
    fields = ExtractedFields(utr="111111111111", amount_paise=None, recipient="Sharma Tea Stall")
    res = verify(db_session, merchant_id=1, fields=fields, image_hash="hash_step9b")
    assert res["outcome"] == "VERIFIED"
    assert "utr" in res["matched_fields"]
    assert any("Amount could not be read" in ev for ev in res["evidence"])


def test_duplicate_submission_flag(db_session):
    """Step 1: Duplicate submission flag is set when image_hash was already submitted."""
    fields = ExtractedFields(utr="111111111111", amount_paise=10000, recipient="Sharma Tea Stall")
    first = verify(db_session, merchant_id=1, fields=fields, image_hash="dup_hash_123")
    assert first["duplicate_flag"] is False

    second = verify(db_session, merchant_id=1, fields=fields, image_hash="dup_hash_123")
    assert second["duplicate_flag"] is True
    assert any("previously" in ev for ev in second["evidence"])


def test_cross_merchant_isolation(db_session):
    """Rule 11: A UTR belonging to merchant 2 must be UNVERIFIED when merchant 1 searches."""
    # UTR 555555555555 belongs to Merchant 2
    ledger_m1 = get_transaction(db_session, merchant_id=1, utr="555555555555")
    assert ledger_m1 is None

    ledger_m2 = get_transaction(db_session, merchant_id=2, utr="555555555555")
    assert ledger_m2 is not None

    fields = ExtractedFields(utr="555555555555", amount_paise=12000, recipient="Sharma Tea Stall")
    res_m1 = verify(db_session, merchant_id=1, fields=fields, image_hash="m2_utr_hash")
    assert res_m1["outcome"] == "UNVERIFIED"


def test_preprocess_validation_errors():
    """Test preprocess error conditions: extension, file size, undecodable bytes."""
    # 1. Invalid extension
    with pytest.raises(ValueError, match="Invalid file extension"):
        preprocess(b"data", "receipt.pdf")

    with pytest.raises(ValueError, match="Invalid file extension"):
        preprocess(b"data", "receipt.txt")

    # 2. Oversize bytes (> 5 MB)
    oversize_bytes = b"0" * (5 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="exceeds the 5 MB"):
        preprocess(oversize_bytes, "receipt.png")

    # 3. Undecodable bytes
    with pytest.raises(ValueError, match="Failed to decode image"):
        preprocess(b"not a valid image byte array", "receipt.png")

