"""Tests for Cases and Report API endpoints."""
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_create_case_success():
    payload = {
        "case_type": "MISMATCH",
        "description": "Customer screenshot shows ₹550 but ledger recorded ₹50",
        "status": "OPEN",
        "related_reference": "202610151234",
        "note": "Awaiting customer call back",
    }
    response = client.post("/api/cases?merchant_id=1", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["merchant_id"] == 1
    assert data["case_type"] == "MISMATCH"
    assert data["status"] == "OPEN"
    assert data["related_reference"] == "202610151234"
    assert data["note"] == "Awaiting customer call back"
    assert "id" in data
    assert "created_at_ist" in data


def test_create_case_invalid_status():
    payload = {
        "case_type": "MANUAL",
        "description": "Test case with invalid status",
        "status": "INVALID_STATUS",
    }
    response = client.post("/api/cases?merchant_id=1", json=payload)
    assert response.status_code == 400
    assert "Invalid status" in response.json()["detail"]


def test_create_case_merchant_not_found():
    payload = {
        "description": "Merchant does not exist",
    }
    response = client.post("/api/cases?merchant_id=99999", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Merchant not found"


def test_list_cases_isolation():
    # Create case for merchant 1
    c1 = client.post(
        "/api/cases?merchant_id=1",
        json={"description": "Merchant 1 specific case", "status": "OPEN"},
    ).json()

    # Create case for merchant 2
    c2 = client.post(
        "/api/cases?merchant_id=2",
        json={"description": "Merchant 2 specific case", "status": "OPEN"},
    ).json()

    # List merchant 1 cases
    res1 = client.get("/api/cases?merchant_id=1")
    assert res1.status_code == 200
    ids_1 = [c["id"] for c in res1.json()]
    assert c1["id"] in ids_1
    assert c2["id"] not in ids_1

    # List merchant 2 cases
    res2 = client.get("/api/cases?merchant_id=2")
    assert res2.status_code == 200
    ids_2 = [c["id"] for c in res2.json()]
    assert c2["id"] in ids_2
    assert c1["id"] not in ids_2


def test_cross_merchant_case_access():
    # Merchant 1 creates a case
    created = client.post(
        "/api/cases?merchant_id=1",
        json={"description": "Merchant 1 confidential dispute", "status": "OPEN"},
    ).json()
    case_id = created["id"]

    # Merchant 2 tries to PATCH merchant 1's case -> MUST return 404
    response = client.patch(
        f"/api/cases/{case_id}?merchant_id=2",
        json={"status": "RESOLVED"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Case not found"


def test_patch_case_update():
    created = client.post(
        "/api/cases?merchant_id=1",
        json={"description": "Case to be updated", "status": "OPEN"},
    ).json()
    case_id = created["id"]

    # Update status to UNDER_REVIEW and update note
    res = client.patch(
        f"/api/cases/{case_id}?merchant_id=1",
        json={"status": "UNDER_REVIEW", "note": "Contacted payment desk"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "UNDER_REVIEW"
    assert data["note"] == "Contacted payment desk"

    # Update to RESOLVED
    res2 = client.patch(
        f"/api/cases/{case_id}?merchant_id=1",
        json={"status": "RESOLVED"},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "RESOLVED"


def test_patch_case_invalid_status():
    created = client.post(
        "/api/cases?merchant_id=1",
        json={"description": "Case test invalid patch", "status": "OPEN"},
    ).json()
    case_id = created["id"]

    res = client.patch(
        f"/api/cases/{case_id}?merchant_id=1",
        json={"status": "CLOSED"},  # not in OPEN, UNDER_REVIEW, RESOLVED
    )
    assert res.status_code == 400
    assert "Invalid status" in res.json()["detail"]


def test_get_report_success():
    res = client.get("/api/report?merchant_id=1")
    assert res.status_code == 200
    data = res.json()

    # Exact response shape per PLAN.md section 9:
    # {"date": "", "sections": {"summary": {}, "comparison": {}, "peak_hour": {}, "open_cases": 0}, "text": ""}
    assert "date" in data
    assert "sections" in data
    sections = data["sections"]
    assert "summary" in sections
    assert "comparison" in sections
    assert "peak_hour" in sections
    assert "open_cases" in sections
    assert isinstance(sections["open_cases"], int)
    assert "text" in data
    assert isinstance(data["text"], str)

    # Check text contents
    text = data["text"]
    assert "VYAPAARAI DAILY BUSINESS REPORT" in text
    assert "DIGITAL COLLECTIONS SUMMARY" in text
    assert "COMPARISON WITH PREVIOUS DAY" in text
    assert "PEAK HOURLY ACTIVITY" in text
    assert "INTERNAL CASES & DISPUTES" in text


def test_get_report_invalid_date():
    res = client.get("/api/report?merchant_id=1&date=invalid-date")
    assert res.status_code == 400
    assert "Invalid date format" in res.json()["detail"]


def test_get_report_merchant_not_found():
    res = client.get("/api/report?merchant_id=99999")
    assert res.status_code == 404
    assert res.json()["detail"] == "Merchant not found"

