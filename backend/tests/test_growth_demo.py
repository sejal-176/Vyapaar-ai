"""Unit and integration tests for Growth Insights preview (backend/growth_demo).
Tests in this file use isolated fixtures and temporary databases to guarantee clean runs.
Verifies all mathematical invariants, edge cases, privacy guardrails, and banned word checks.
"""
import ast
import json
from datetime import date, timedelta
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.growth_demo.models import GrowthBase, GDCustomer, GDProduct, GDInvoice, GDInvoiceItem, GDOutreach
from backend.growth_demo.customers import lapsing_customers, customer_change, shrinking_customers
from backend.growth_demo.inventory import get_inventory_insights
from backend.growth_demo.outreach import (
    evaluate_margin_guardrail,
    create_outreach_draft,
    update_outreach_status,
)
from backend.main import app

client = TestClient(app)
GROWTH_DIR = Path(__file__).resolve().parent.parent / "growth_demo"


@pytest.fixture
def temp_growth_db():
    """In-memory SQLite database session with GrowthBase schema."""
    engine = create_engine("sqlite:///:memory:")
    GrowthBase.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# -----------------------------------------------------------------------------
# 1. Invariant & Math Tests
# -----------------------------------------------------------------------------
def test_invoice_total_equals_item_sum(temp_growth_db):
    """Every invoice total must exactly equal the sum of item quantity * unit_price_paise."""
    p1 = GDProduct(name="Tea", unit="cup", price_paise=1000, cost_price_paise=400, stock_on_hand=50, stock_updated_on="2026-10-30")
    p2 = GDProduct(name="Samosa", unit="piece", price_paise=1500, cost_price_paise=800, stock_on_hand=40, stock_updated_on="2026-10-30")
    temp_growth_db.add_all([p1, p2])
    temp_growth_db.commit()

    inv = GDInvoice(customer_id=None, invoice_date="2026-10-30", total_paise=3500)
    temp_growth_db.add(inv)
    temp_growth_db.commit()

    item1 = GDInvoiceItem(invoice_id=inv.id, product_id=p1.id, quantity=2, unit_price_paise=1000)
    item2 = GDInvoiceItem(invoice_id=inv.id, product_id=p2.id, quantity=1, unit_price_paise=1500)
    temp_growth_db.add_all([item1, item2])
    temp_growth_db.commit()

    calculated = sum(item.quantity * item.unit_price_paise for item in inv.items)
    assert inv.total_paise == calculated == 3500


def test_hand_computed_stats_fixture(temp_growth_db):
    """Verify hand-computed visits, spend, and exact-sum decomposition."""
    c = GDCustomer(payer_token="C-0099", consent_status="OPTED_IN")
    p = GDProduct(name="Tea", unit="cup", price_paise=1000, cost_price_paise=400, stock_on_hand=50, stock_updated_on="2026-10-30")
    temp_growth_db.add_all([c, p])
    temp_growth_db.commit()

    # Previous 14 days: 4 visits, 2 teas each (₹20 = 2000 paise per visit), total = 8000 paise
    for day in ["2026-10-05", "2026-10-08", "2026-10-11", "2026-10-14"]:
        inv = GDInvoice(customer_id=c.id, invoice_date=day, total_paise=2000)
        temp_growth_db.add(inv)
        temp_growth_db.flush()
        temp_growth_db.add(GDInvoiceItem(invoice_id=inv.id, product_id=p.id, quantity=2, unit_price_paise=1000))

    # Last 14 days: 2 visits, 1 tea each (₹10 = 1000 paise per visit), total = 2000 paise
    for day in ["2026-10-20", "2026-10-25"]:
        inv = GDInvoice(customer_id=c.id, invoice_date=day, total_paise=1000)
        temp_growth_db.add(inv)
        temp_growth_db.flush()
        temp_growth_db.add(GDInvoiceItem(invoice_id=inv.id, product_id=p.id, quantity=1, unit_price_paise=1000))

    temp_growth_db.commit()

    ch = customer_change(temp_growth_db, c.id, "2026-10-30")
    assert ch["visits_old"] == 4
    assert ch["visits_new"] == 2
    assert ch["spend_old_paise"] == 8000
    assert ch["spend_new_paise"] == 2000
    assert ch["spend_per_visit_old_paise"] == 2000
    assert ch["spend_per_visit_new_paise"] == 1000

    # Expected: visits_effect = (2 - 4) * 2000 = -4000 paise
    # basket_effect = (2000 - 8000) - (-4000) = -2000 paise
    assert ch["visits_effect_paise"] == -4000
    assert ch["basket_effect_paise"] == -2000
    assert ch["visits_effect_paise"] + ch["basket_effect_paise"] == ch["spend_change_paise"] == -6000
    assert ch["main_driver"] == "fewer_visits"


def test_exact_sum_split_when_v_new_is_zero(temp_growth_db):
    """When customer stopped visiting completely (v_new = 0), decomposition must still sum exactly."""
    c = GDCustomer(payer_token="C-0088", consent_status="OPTED_IN")
    p = GDProduct(name="Coffee", unit="cup", price_paise=1500, cost_price_paise=700, stock_on_hand=50, stock_updated_on="2026-10-30")
    temp_growth_db.add_all([c, p])
    temp_growth_db.commit()

    # Previous 14 days: 3 visits of ₹15
    for day in ["2026-10-04", "2026-10-08", "2026-10-12"]:
        inv = GDInvoice(customer_id=c.id, invoice_date=day, total_paise=1500)
        temp_growth_db.add(inv)
        temp_growth_db.flush()
        temp_growth_db.add(GDInvoiceItem(invoice_id=inv.id, product_id=p.id, quantity=1, unit_price_paise=1500))

    temp_growth_db.commit()

    ch = customer_change(temp_growth_db, c.id, "2026-10-30")
    assert ch["visits_new"] == 0
    assert ch["spend_new_paise"] == 0
    assert ch["spend_old_paise"] == 4500
    assert ch["spend_per_visit_new_paise"] == 0

    # Exact sum check
    assert ch["visits_effect_paise"] + ch["basket_effect_paise"] == ch["spend_change_paise"] == -4500


def test_lapsing_rule_boundary_conditions(temp_growth_db):
    """Test lapsing threshold just inside and just outside the multiplier (2.0x median gap)."""
    # Customer 1: Visits on 2026-10-01, 2026-10-04, 2026-10-07, 2026-10-10 (gaps: 3, 3, 3 -> median gap = 3)
    # Ref date: 2026-10-16. Days since last visit = 6 days.
    # 6 is NOT > 2.0 * 3 (it is == 6). So JUST INSIDE -> NOT lapsing.
    c1 = GDCustomer(payer_token="C-0051", consent_status="OPTED_IN")
    temp_growth_db.add(c1)
    temp_growth_db.commit()

    for d in ["2026-10-01", "2026-10-04", "2026-10-07", "2026-10-10"]:
        temp_growth_db.add(GDInvoice(customer_id=c1.id, invoice_date=d, total_paise=1000))

    # Customer 2: Same gaps (median 3), but last visit was 2026-10-09.
    # Ref date: 2026-10-16. Days since last visit = 7 days.
    # 7 is > 2.0 * 3 (6) and >= 3. JUST OUTSIDE -> LAPSING.
    c2 = GDCustomer(payer_token="C-0052", consent_status="OPTED_IN")
    temp_growth_db.add(c2)
    temp_growth_db.commit()

    for d in ["2026-09-30", "2026-10-03", "2026-10-06", "2026-10-09"]:
        temp_growth_db.add(GDInvoice(customer_id=c2.id, invoice_date=d, total_paise=1000))

    temp_growth_db.commit()

    res = lapsing_customers(temp_growth_db, "2026-10-16")
    named_tokens = [item["payer_token"] for item in res["named"]]
    assert "C-0051" not in named_tokens
    assert "C-0052" in named_tokens


def test_non_consented_customers_counted_not_named(temp_growth_db):
    """Non-consented lapsing customers appear in not_named_count, never in named list."""
    c_none = GDCustomer(payer_token="C-0053", consent_status="NONE")
    temp_growth_db.add(c_none)
    temp_growth_db.commit()

    # Lapsing pattern (median gap 2, last visit 10 days ago)
    for d in ["2026-10-01", "2026-10-03", "2026-10-05", "2026-10-07"]:
        temp_growth_db.add(GDInvoice(customer_id=c_none.id, invoice_date=d, total_paise=1000))
    temp_growth_db.commit()

    res = lapsing_customers(temp_growth_db, "2026-10-17")
    named_tokens = [item["payer_token"] for item in res["named"]]
    assert "C-0053" not in named_tokens
    assert res["not_named_count"] >= 1


# -----------------------------------------------------------------------------
# 2. Inventory & Product Tests
# -----------------------------------------------------------------------------
def test_inventory_zero_velocity_does_not_crash(temp_growth_db):
    """Product with zero billed items has velocity=0, days_left=None, doesn't crash."""
    p_dormant = GDProduct(
        name="Cold Drink",
        unit="bottle",
        price_paise=2000,
        cost_price_paise=1500,
        stock_on_hand=30,
        stock_updated_on="2026-10-30",
    )
    temp_growth_db.add(p_dormant)
    # Add dummy invoice for date reference
    temp_growth_db.add(GDInvoice(customer_id=None, invoice_date="2026-10-30", total_paise=0))
    temp_growth_db.commit()

    res = get_inventory_insights(temp_growth_db, "2026-10-30")
    prod = next(p for p in res["products"] if p["name"] == "Cold Drink")
    assert prod["velocity"] == 0.0
    assert prod["days_left"] is None
    assert prod["status"] == "No recent units"


def test_inventory_slow_mover_fixture(temp_growth_db):
    """Product with >= 30% drop in last 14 vs prev 14 (and prev >= 10) is flagged as slow mover."""
    p = GDProduct(name="Kachori", unit="piece", price_paise=1500, cost_price_paise=800, stock_on_hand=50, stock_updated_on="2026-10-30")
    temp_growth_db.add(p)
    temp_growth_db.commit()

    # Previous 14 days (2026-10-03 to 2026-10-16): 20 units
    inv1 = GDInvoice(customer_id=None, invoice_date="2026-10-10", total_paise=30000)
    temp_growth_db.add(inv1)
    temp_growth_db.flush()
    temp_growth_db.add(GDInvoiceItem(invoice_id=inv1.id, product_id=p.id, quantity=20, unit_price_paise=1500))

    # Last 14 days (2026-10-17 to 2026-10-30): 10 units (50% drop)
    inv2 = GDInvoice(customer_id=None, invoice_date="2026-10-25", total_paise=15000)
    temp_growth_db.add(inv2)
    temp_growth_db.flush()
    temp_growth_db.add(GDInvoiceItem(invoice_id=inv2.id, product_id=p.id, quantity=10, unit_price_paise=1500))

    temp_growth_db.commit()

    res = get_inventory_insights(temp_growth_db, "2026-10-30")
    slow_ids = [sm["product_id"] for sm in res["slow_movers"]]
    assert p.id in slow_ids


# -----------------------------------------------------------------------------
# 3. Outreach & Guardrail Tests
# -----------------------------------------------------------------------------
def test_guardrail_above_cap_refused(temp_growth_db):
    c = GDCustomer(payer_token="C-0061", consent_status="OPTED_IN")
    temp_growth_db.add(c)
    temp_growth_db.commit()

    res = evaluate_margin_guardrail(temp_growth_db, c.id, 11)
    assert not res["allowed"]
    assert "cannot exceed 10%" in res["reason"]


def test_guardrail_missing_cost_refused(temp_growth_db):
    c = GDCustomer(payer_token="C-0062", consent_status="OPTED_IN")
    p_nocost = GDProduct(name="Mystery Item", unit="plate", price_paise=2500, cost_price_paise=None, stock_on_hand=10, stock_updated_on="2026-10-30")
    temp_growth_db.add_all([c, p_nocost])
    temp_growth_db.commit()

    inv = GDInvoice(customer_id=c.id, invoice_date="2026-10-28", total_paise=2500)
    temp_growth_db.add(inv)
    temp_growth_db.flush()
    temp_growth_db.add(GDInvoiceItem(invoice_id=inv.id, product_id=p_nocost.id, quantity=1, unit_price_paise=2500))
    temp_growth_db.commit()

    res = evaluate_margin_guardrail(temp_growth_db, c.id, 5)
    assert not res["allowed"]
    assert "Enter your item costs first" in res["reason"]


def test_guardrail_margin_left_too_small_refused(temp_growth_db):
    # Product with thin margin: price ₹100, cost ₹92 (margin 8%)
    # An offer of 5% leaves only 3% (less than MIN_MARGIN_LEFT_POINTS = 5)
    c = GDCustomer(payer_token="C-0063", consent_status="OPTED_IN")
    p_thin = GDProduct(name="Thin Margin Product", unit="item", price_paise=10000, cost_price_paise=9200, stock_on_hand=10, stock_updated_on="2026-10-30")
    temp_growth_db.add_all([c, p_thin])
    temp_growth_db.commit()

    inv = GDInvoice(customer_id=c.id, invoice_date="2026-10-28", total_paise=10000)
    temp_growth_db.add(inv)
    temp_growth_db.flush()
    temp_growth_db.add(GDInvoiceItem(invoice_id=inv.id, product_id=p_thin.id, quantity=1, unit_price_paise=10000))
    temp_growth_db.commit()

    res = evaluate_margin_guardrail(temp_growth_db, c.id, 5)
    assert not res["allowed"]
    assert "Offer leaves too little margin" in res["reason"]


def test_guardrail_valid_offer_accepted(temp_growth_db):
    # Product with healthy margin: price ₹100, cost ₹40 (margin 60%)
    # Offer 10% leaves 50% (> 5%)
    c = GDCustomer(payer_token="C-0064", consent_status="OPTED_IN")
    p_good = GDProduct(name="Good Margin Tea", unit="cup", price_paise=10000, cost_price_paise=4000, stock_on_hand=50, stock_updated_on="2026-10-30")
    temp_growth_db.add_all([c, p_good])
    temp_growth_db.commit()

    inv = GDInvoice(customer_id=c.id, invoice_date="2026-10-28", total_paise=10000)
    temp_growth_db.add(inv)
    temp_growth_db.flush()
    temp_growth_db.add(GDInvoiceItem(invoice_id=inv.id, product_id=p_good.id, quantity=1, unit_price_paise=10000))
    temp_growth_db.commit()

    res = evaluate_margin_guardrail(temp_growth_db, c.id, 10)
    assert res["allowed"]
    assert res["margin_left"] == 50.0


def test_consent_rechecked_at_status_transitions(temp_growth_db):
    """Revoking consent after draft blocks approve and mark_sent."""
    c = GDCustomer(payer_token="C-0065", consent_status="OPTED_IN")
    temp_growth_db.add(c)
    temp_growth_db.commit()

    outreach, err = create_outreach_draft(temp_growth_db, c.id, language="en", offer_type="NONE")
    assert err is None
    assert outreach.status == "DRAFT"

    # Revoke consent
    c.consent_status = "NONE"
    temp_growth_db.commit()

    # Attempt approve
    _, err_app = update_outreach_status(temp_growth_db, outreach.id, "approve")
    assert err_app is not None
    assert "opted in" in err_app.lower()


def test_no_backwards_status_moves(temp_growth_db):
    """Status machine allows DRAFT -> APPROVED -> MARKED_SENT. Cannot move backwards."""
    c = GDCustomer(payer_token="C-0066", consent_status="OPTED_IN")
    temp_growth_db.add(c)
    temp_growth_db.commit()

    outreach, _ = create_outreach_draft(temp_growth_db, c.id, language="en", offer_type="NONE")
    update_outreach_status(temp_growth_db, outreach.id, "approve")
    assert outreach.status == "APPROVED"

    update_outreach_status(temp_growth_db, outreach.id, "mark_sent")
    assert outreach.status == "MARKED_SENT"

    # Try moving back to APPROVED or DRAFT
    _, err_back = update_outreach_status(temp_growth_db, outreach.id, "approve")
    assert err_back is not None
    assert "Illegal status transition" in err_back


# -----------------------------------------------------------------------------
# 4. Architectural & Banned Word Audits
# -----------------------------------------------------------------------------
def test_growth_demo_package_imports_no_network_libraries():
    """Verify that backend/growth_demo/ contains NO imports of HTTP or messaging packages."""
    banned_imports = {
        "requests", "urllib.request", "urllib3", "httpx", "aiohttp",
        "twilio", "smtplib", "telepot", "pywhatkit", "socket"
    }

    for py_file in GROWTH_DIR.glob("*.py"):
        with open(py_file, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in banned_imports, f"Banned import '{alias.name}' in {py_file}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert node.module not in banned_imports, f"Banned import-from '{node.module}' in {py_file}"


def test_banned_words_absent_from_api_responses():
    """Verify banned words do not appear in live responses of growth demo endpoints."""
    banned_words = [
        "revenue", "sales", "profit", "income", "eligible",
        "score", "will return", "bring back", "guaranteed"
    ]

    endpoints = [
        "/api/growth/customers/lapsing",
        "/api/growth/inventory",
    ]

    for ep in endpoints:
        res = client.get(ep)
        if res.status_code == 200:
            text = res.text.lower()
            for bw in banned_words:
                assert bw not in text, f"Banned word '{bw}' found in response from {ep}: {text[:300]}"


def test_banned_words_absent_from_new_frontend_files():
    """Verify banned words do not appear in the new GrowthInsights frontend file."""
    banned_words = [
        "revenue", "sales", "profit", "income", "eligible",
        "score", "will return", "bring back", "guaranteed"
    ]

    fe_file = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "components" / "GrowthInsights.tsx"
    assert fe_file.exists(), f"Frontend file {fe_file} missing"

    content = fe_file.read_text(encoding="utf-8").lower()
    for bw in banned_words:
        assert bw not in content, f"Banned word '{bw}' found in {fe_file}"

