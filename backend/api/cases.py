"""Case management API routes for VyapaarAI."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import Merchant, Case, utc_now
from backend.core.timeutil import utc_to_ist

router = APIRouter(prefix="/api/cases", tags=["cases"])

VALID_STATUSES = {"OPEN", "UNDER_REVIEW", "RESOLVED"}


class CreateCaseRequest(BaseModel):
    case_type: Optional[str] = Field("MANUAL", description="Type of case (e.g. MISMATCH, MANUAL, AGENT_FOLLOWUP)")
    description: str = Field(..., min_length=1, description="Description of the issue or dispute")
    status: Optional[str] = Field("OPEN", description="Initial case status (OPEN, UNDER_REVIEW, RESOLVED)")
    related_reference: Optional[str] = Field(None, description="Related 12-digit UTR reference if applicable")
    note: Optional[str] = Field(None, description="Optional merchant note or comment")


class UpdateCaseRequest(BaseModel):
    status: Optional[str] = Field(None, description="Updated status (OPEN, UNDER_REVIEW, RESOLVED)")
    note: Optional[str] = Field(None, description="Updated internal note")


def _serialize_case(c: Case) -> dict:
    return {
        "id": c.id,
        "merchant_id": c.merchant_id,
        "case_type": c.case_type,
        "description": c.description,
        "status": c.status,
        "related_reference": c.related_reference,
        "note": c.note,
        "created_at_ist": (
            utc_to_ist(c.created_at).strftime("%Y-%m-%d %H:%M:%S") if c.created_at else None
        ),
        "updated_at_ist": (
            utc_to_ist(c.updated_at).strftime("%Y-%m-%d %H:%M:%S") if c.updated_at else None
        ),
    }


@router.get("")
def list_cases(
    merchant_id: int = Query(..., description="ID of merchant"),
    db: Session = Depends(get_db),
):
    """List all internal cases for the specified merchant."""
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    cases = (
        db.query(Case)
        .filter(Case.merchant_id == merchant_id)
        .order_by(Case.created_at.desc(), Case.id.desc())
        .all()
    )
    return [_serialize_case(c) for c in cases]


@router.post("", status_code=201)
def create_case(
    payload: CreateCaseRequest,
    merchant_id: int = Query(..., description="ID of merchant"),
    db: Session = Depends(get_db),
):
    """Create a new internal case for the specified merchant."""
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    status = (payload.status or "OPEN").strip().upper()
    if status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{payload.status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )

    case = Case(
        merchant_id=merchant_id,
        case_type=(payload.case_type or "MANUAL").strip(),
        description=payload.description.strip(),
        status=status,
        related_reference=payload.related_reference.strip() if payload.related_reference else None,
        note=payload.note.strip() if payload.note else None,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return _serialize_case(case)


@router.patch("/{case_id}")
def update_case(
    case_id: int,
    payload: UpdateCaseRequest,
    merchant_id: int = Query(..., description="ID of merchant"),
    db: Session = Depends(get_db),
):
    """Update case status or internal note.
    Scoped strictly to merchant_id; cases belonging to another merchant return 404.
    """
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    case = db.query(Case).filter(Case.id == case_id, Case.merchant_id == merchant_id).first()
    # Cross-merchant isolation: a case belonging to another merchant returns 404
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if payload.status is not None:
        status = payload.status.strip().upper()
        if status not in VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{payload.status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
            )
        case.status = status

    if payload.note is not None:
        case.note = payload.note.strip() if payload.note.strip() else None

    case.updated_at = utc_now()
    db.commit()
    db.refresh(case)
    return _serialize_case(case)

