"""FastAPI router for Growth Insights preview.
Mounted at /api/growth.
All responses are computed live from growth_demo.db.
Follows all project rules and banned-words guidelines.
"""
import os
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.growth_demo.db import get_growth_db, DB_FILE
from backend.growth_demo.models import GDOutreach, GDCustomer
from backend.growth_demo.customers import lapsing_customers, customer_change, shrinking_customers
from backend.growth_demo.inventory import get_inventory_insights
from backend.growth_demo.outreach import (
    create_outreach_draft,
    update_outreach_status,
    evaluate_margin_guardrail,
    get_rendered_template,
)

router = APIRouter(prefix="/api/growth", tags=["growth_demo"])


def _check_db_exists():
    if not DB_FILE.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Run python scripts/make_growth_demo.py",
        )


class DraftRequest(BaseModel):
    customer_id: int
    language: str = Field(default="en")
    offer_type: str = Field(default="NONE")
    offer_pct: int = Field(default=0)
    custom_text: Optional[str] = None


class PatchOutreachRequest(BaseModel):
    action: str = Field(..., description="edit, approve, mark_sent, dismiss")
    message_text: Optional[str] = None


class GuardrailCheckRequest(BaseModel):
    customer_id: int
    offer_pct: int = Field(default=0)


class TemplatePreviewRequest(BaseModel):
    offer_type: str = Field(default="NONE")
    language: str = Field(default="en")
    offer_pct: int = Field(default=0)


@router.get("/customers/lapsing")
def get_lapsing_customers(db: Session = Depends(get_growth_db)):
    """List lapsing customers (named OPTED_IN and count of non-consented), plus shrinking customers."""
    _check_db_exists()
    data = lapsing_customers(db)
    data["shrinking"] = shrinking_customers(db)
    return data


@router.get("/customers/{customer_id}/change")
def get_customer_change(customer_id: int, db: Session = Depends(get_growth_db)):
    """Get visits, spend, and basket breakdown for a specific customer across last 14 vs prev 14 days."""
    _check_db_exists()
    data = customer_change(db, customer_id)
    if not data:
        raise HTTPException(status_code=404, detail="Customer not found")
    return data


@router.get("/inventory")
def get_inventory(db: Session = Depends(get_growth_db)):
    """Get product inventory, velocity, days left, low stock, and slow movers."""
    _check_db_exists()
    return get_inventory_insights(db)


@router.post("/outreach/template-preview")
def preview_template(req: TemplatePreviewRequest):
    """Render a template for the draft modal."""
    _check_db_exists()
    text = get_rendered_template(req.offer_type, req.language, req.offer_pct)
    return {"message_text": text}


@router.post("/outreach/guardrail-check")
def check_guardrail(req: GuardrailCheckRequest, db: Session = Depends(get_growth_db)):
    """Evaluate margin guardrail live as the merchant types an offer."""
    _check_db_exists()
    cust = db.query(GDCustomer).filter(GDCustomer.id == req.customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    result = evaluate_margin_guardrail(db, req.customer_id, req.offer_pct)
    return result


@router.post("/outreach/draft")
def create_draft(req: DraftRequest, db: Session = Depends(get_growth_db)):
    """Create a new outreach draft for an OPTED_IN customer."""
    _check_db_exists()
    outreach, err = create_outreach_draft(
        db=db,
        customer_id=req.customer_id,
        language=req.language,
        offer_type=req.offer_type,
        offer_pct=req.offer_pct,
        custom_text=req.custom_text,
    )
    if err:
        if "not found" in err.lower():
            raise HTTPException(status_code=404, detail=err)
        raise HTTPException(status_code=400, detail=err)

    return _serialize_outreach(outreach, db)


@router.get("/outreach")
def list_outreach(db: Session = Depends(get_growth_db)):
    """List all created outreach records, newest first."""
    _check_db_exists()
    records = db.query(GDOutreach).order_by(GDOutreach.id.desc()).all()
    return [_serialize_outreach(r, db) for r in records]


@router.patch("/outreach/{outreach_id}")
def update_outreach(
    outreach_id: int, req: PatchOutreachRequest, db: Session = Depends(get_growth_db)
):
    """Update outreach status or edit message text."""
    _check_db_exists()
    outreach, err = update_outreach_status(
        db=db,
        outreach_id=outreach_id,
        action=req.action,
        new_message_text=req.message_text,
    )
    if err:
        if "not found" in err.lower():
            raise HTTPException(status_code=404, detail=err)
        raise HTTPException(status_code=400, detail=err)

    return _serialize_outreach(outreach, db)


def _serialize_outreach(r: GDOutreach, db: Session) -> dict:
    customer = db.query(GDCustomer).filter(GDCustomer.id == r.customer_id).first()
    token = customer.payer_token if customer else "Unknown"
    evidence = {}
    try:
        evidence = json.loads(r.evidence_json) if r.evidence_json else {}
    except Exception:
        pass

    return {
        "id": r.id,
        "customer_id": r.customer_id,
        "payer_token": token,
        "status": r.status,
        "language": r.language,
        "offer_type": r.offer_type,
        "offer_pct": r.offer_pct,
        "message_text": r.message_text,
        "evidence": evidence,
        "created_at": r.created_at,
        "approved_at": r.approved_at,
        "marked_sent_at": r.marked_sent_at,
    }

