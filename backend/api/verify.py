"""Verification API endpoint for payment screenshots."""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import Merchant
from backend.verification import preprocess, extract_fields, verify

router = APIRouter(prefix="/api", tags=["verification"])


@router.post("/verify")
async def verify_screenshot(
    file: UploadFile = File(..., description="Payment screenshot image (PNG, JPG, JPEG)"),
    merchant_id: int = Query(..., description="ID of the merchant (stands in for auth)"),
    db: Session = Depends(get_db),
):
    """Verify customer payment screenshot against the merchant's ledger record.
    Uses deterministic 9-step decision table.
    Rule 6: Deterministic decision table, no AI confidence scores.
    Rule 7: OCR text parsed with regex only.
    Rule 8: Screenshot alone never proves payment; only the ledger does.
    """
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    filename = file.filename or "upload.png"
    image_bytes = await file.read()

    try:
        prep_result = preprocess(image_bytes, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    fields = extract_fields(prep_result["variants"])

    result = verify(
        db=db,
        merchant_id=merchant_id,
        fields=fields,
        image_hash=prep_result["image_hash"],
        raw_text=fields.raw_text,
    )

    return result

