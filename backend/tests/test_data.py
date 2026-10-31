"""Tests for Layer 1: Data generator and ingestion."""
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base
from backend.models import Merchant, Transaction, Quarantine, IngestionReport
from backend.data.generator import generate_merchant_csv
from backend.data.ingest import ingest_csv


@pytest.fixture
def db_session():
    """In-memory SQLite database session for isolated testing."""
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

    yield session
    session.close()


def test_ingest_6_row_fixture(tmp_path, db_session):
    """Test a 6-row fixture CSV with known hand-computed report:
    1 valid row, 5 rejected rows (one for each quarantine reason).
    """
    csv_file = tmp_path / "test_fixture.csv"
    csv_content = (
        "reference,amount,status,timestamp\n"
        "123456789001,100,SUCCESS,2026-10-25 10:00:00\n"  # 1. Accepted
        "123456789001,50,SUCCESS,2026-10-25 11:00:00\n"   # 2. Duplicate reference in file
        "123456789002,-50,SUCCESS,2026-10-25 12:00:00\n"  # 3. Negative amount (invalid_amount)
        "123456789003,75,SUCCESS,\n"                       # 4. Missing timestamp (missing_time)
        ",80,SUCCESS,2026-10-25 13:00:00\n"               # 5. Blank reference (blank_reference)
        "123456789004,90,DISPUTED,2026-10-25 14:00:00\n"  # 6. Unknown status (unknown_status)
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    report = ingest_csv(csv_file, merchant_id=1, db=db_session)

    assert report["accepted"] == 1
    assert report["rejected"] == 5
    assert report["reasons"]["duplicate"] == 1
    assert report["reasons"]["invalid_amount"] == 1
    assert report["reasons"]["missing_time"] == 1
    assert report["reasons"]["blank_reference"] == 1
    assert report["reasons"]["unknown_status"] == 1

    # Verify transaction in DB
    txns = db_session.query(Transaction).filter_by(merchant_id=1).all()
    assert len(txns) == 1
    assert txns[0].reference == "123456789001"
    assert txns[0].amount_paise == 10000
    assert txns[0].status == "SUCCESS"
    assert txns[0].txn_type == "PAYMENT"

    # Verify quarantine entries in DB
    quarantines = db_session.query(Quarantine).filter_by(merchant_id=1).all()
    assert len(quarantines) == 5
    reasons = {q.reason for q in quarantines}
    assert reasons == {"duplicate", "invalid_amount", "missing_time", "blank_reference", "unknown_status"}

    # Verify IngestionReport persisted
    rep_records = db_session.query(IngestionReport).filter_by(merchant_id=1).all()
    assert len(rep_records) == 1
    assert rep_records[0].accepted == 1
    assert rep_records[0].rejected == 5
    parsed_reasons = json.loads(rep_records[0].reasons)
    assert parsed_reasons["duplicate"] == 1


def test_duplicate_against_existing_db_record(tmp_path, db_session):
    """Test that a reference already in the DB is rejected as duplicate on subsequent ingest."""
    # First file with valid row
    file1 = tmp_path / "file1.csv"
    file1.write_text("reference,amount,status,timestamp\n999888777666,50,SUCCESS,2026-10-25 10:00:00\n", encoding="utf-8")
    report1 = ingest_csv(file1, merchant_id=1, db=db_session)
    assert report1["accepted"] == 1

    # Second file with same reference for same merchant
    file2 = tmp_path / "file2.csv"
    file2.write_text("reference,amount,status,timestamp\n999888777666,70,SUCCESS,2026-10-25 12:00:00\n", encoding="utf-8")
    report2 = ingest_csv(file2, merchant_id=1, db=db_session)
    assert report2["accepted"] == 0
    assert report2["rejected"] == 1
    assert report2["reasons"]["duplicate"] == 1


def test_cross_merchant_reference_isolation(tmp_path, db_session):
    """Test Rule 11: A reference belonging to merchant 1 does not collide with merchant 2."""
    ref = "111222333444"
    file1 = tmp_path / "m1.csv"
    file1.write_text(f"reference,amount,status,timestamp\n{ref},50,SUCCESS,2026-10-25 10:00:00\n", encoding="utf-8")
    report1 = ingest_csv(file1, merchant_id=1, db=db_session)
    assert report1["accepted"] == 1

    file2 = tmp_path / "m2.csv"
    file2.write_text(f"reference,amount,status,timestamp\n{ref},100,SUCCESS,2026-10-25 11:00:00\n", encoding="utf-8")
    report2 = ingest_csv(file2, merchant_id=2, db=db_session)
    assert report2["accepted"] == 1

    # Both merchants should have their independent record
    tx_m1 = db_session.query(Transaction).filter_by(merchant_id=1, reference=ref).first()
    tx_m2 = db_session.query(Transaction).filter_by(merchant_id=2, reference=ref).first()
    assert tx_m1 is not None and tx_m1.amount_paise == 5000
    assert tx_m2 is not None and tx_m2.amount_paise == 10000


def test_generator_and_full_ingestion(tmp_path, db_session):
    """Test generating 30-day CSV and ingesting it."""
    csv_file = tmp_path / "gen_m1.csv"
    generate_merchant_csv(merchant_id=1, output_path=csv_file, seed=42)

    report = ingest_csv(csv_file, merchant_id=1, db=db_session)

    # Should have over 1000 accepted transactions
    assert report["accepted"] > 500
    # Dirty rows should be rejected (duplicate, invalid_amount, missing_time, unknown_status, blank_reference)
    assert report["rejected"] >= 8
    assert report["reasons"]["duplicate"] >= 2
    assert report["reasons"]["invalid_amount"] >= 2
    assert report["reasons"]["missing_time"] >= 2
    assert report["reasons"]["blank_reference"] >= 1
    assert report["reasons"]["unknown_status"] >= 1

