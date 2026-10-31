"""Tests for FastAPI endpoints: /api/merchants, /api/dashboard, /api/verify."""
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)
SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent.parent / "testdata" / "screenshots"


def test_list_merchants():
    response = client.get("/api/merchants")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    ids = [m["id"] for m in data]
    assert 1 in ids
    assert 2 in ids


def test_get_dashboard_merchant_1():
    response = client.get("/api/dashboard?merchant_id=1")
    assert response.status_code == 200
    data = response.json()

    # Exact response shape per PLAN.md section 9
    assert "merchant" in data
    assert data["merchant"]["id"] == 1
    assert data["merchant"]["name"] == "Sharma Tea Stall"

    assert "reference_date" in data
    assert "summary" in data
    assert "previous_summary" in data
    assert "trend" in data
    assert "recent_transactions" in data
    assert "ingestion_report" in data


def test_get_dashboard_not_found():
    response = client.get("/api/dashboard?merchant_id=999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Merchant not found"


def test_verify_real_screenshot():
    img_path = SCREENSHOTS_DIR / "01_match.png"
    if not img_path.exists():
        return

    with open(img_path, "rb") as f:
        response = client.post(
            "/api/verify?merchant_id=1",
            files={"file": ("01_match.png", f, "image/png")},
        )

    assert response.status_code == 200
    data = response.json()

    # Exact response shape per PLAN.md section 7
    assert data["outcome"] == "VERIFIED"
    assert "reason" in data
    assert "matched_fields" in data
    assert "conflicting_fields" in data
    assert "evidence" in data
    assert "next_step" in data
    assert "duplicate_flag" in data
    assert "extracted" in data
    assert "ledger_record" in data
    assert "raw_text" in data


def test_verify_invalid_extension():
    response = client.post(
        "/api/verify?merchant_id=1",
        files={"file": ("test.txt", b"plain text content", "text/plain")},
    )
    assert response.status_code == 400
    assert "Invalid file extension" in response.json()["detail"]


def test_verify_undecodable_bytes():
    response = client.post(
        "/api/verify?merchant_id=1",
        files={"file": ("corrupt.png", b"not a real image", "image/png")},
    )
    assert response.status_code == 400
    assert "Failed to decode image" in response.json()["detail"]


def test_verify_merchant_not_found():
    response = client.post(
        "/api/verify?merchant_id=999999",
        files={"file": ("test.png", b"dummy", "image/png")},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Merchant not found"
