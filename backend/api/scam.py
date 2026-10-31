"""SMS and message verification API route for VyapaarAI."""
import hashlib
import json
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.money import format_inr
from backend.db import get_db
from backend.models import Merchant, SMSCheck, utc_now
from backend.scam.claims import extract_claim
from backend.scam.check import check_claim
from backend.scam.signals import detect_signals

router = APIRouter(prefix="/api/scam-check", tags=["scam-check"])

MAX_MESSAGE_LENGTH = 2000

NEXT_STEPS = {
    "VERIFIED": "This transaction exists in your records. Still confirm it in your Paytm app before handing over goods if the message asked for anything.",
    "UNVERIFIED": "We could not verify this. Check your Paytm app or bank statement directly before acting.",
    "MISMATCH": "This message conflicts with your records. Do not rely on it. Create a case.",
    "NOT_CHECKABLE": "This message does not claim a payment, so there is nothing to check in your records. Review the warning signs below.",
}

MANDATORY_ADVICE = "Never share your UPI PIN or OTP to receive money."
MANDATORY_DISCLAIMER = "This checks messages against your demo ledger and simple warning patterns. It cannot prove a message is genuine."


class ScamCheckRequest(BaseModel):
    text: str = Field(..., description="Raw SMS message text to inspect")


@router.post("")
def check_sms_message(
    payload: ScamCheckRequest,
    merchant_id: int = Query(..., description="ID of merchant (stands in for auth)"),
    db: Session = Depends(get_db),
):
    """Inspect an untrusted SMS message for claimed payment details, verify against the ledger,
    and detect warning signals. Plain-text only; no network calls or LLM used.
    """
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    raw_text = payload.text
    if not raw_text or not raw_text.strip():
        raise HTTPException(status_code=400, detail="Message text cannot be empty.")

    if len(raw_text) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Message length ({len(raw_text)} chars) exceeds the maximum limit of {MAX_MESSAGE_LENGTH} characters.",
        )

    # Strip non-printable control characters (except newline, tab, carriage return)
    cleaned_text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", raw_text).strip()
    if not cleaned_text:
        raise HTTPException(status_code=400, detail="Message text contains no valid characters.")

    # 1. Deterministic Claim Extraction
    claim = extract_claim(cleaned_text)

    # 2. Trusted Ledger Lookup & Verification
    ledger_result = check_claim(db, merchant_id, claim)
    outcome = ledger_result["outcome"]

    # 3. Rule-based Warning Signals
    signals = detect_signals(cleaned_text)
    warning_level = "Warning signs found" if signals else "No warning signs found"

    # 4. Next Step, Advice & Disclaimer
    next_step = NEXT_STEPS.get(outcome, NEXT_STEPS["UNVERIFIED"])

    # 5. Persist audit record to sms_checks table (SHA-256 only; never store raw text)
    text_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()
    signal_cats = list({s["category"] for s in signals})

    check_row = SMSCheck(
        merchant_id=merchant_id,
        text_hash=text_hash,
        outcome=outcome,
        signal_categories=json.dumps(signal_cats),
        created_at=utc_now(),
    )
    db.add(check_row)
    db.commit()

    # Build claim dict with formatted INR
    claim_dict = {
        "direction": claim.direction,
        "amount_paise": claim.amount_paise,
        "amount_inr": format_inr(claim.amount_paise) if claim.amount_paise is not None else None,
        "utr": claim.utr,
        "timestamp": claim.timestamp,
        "counterparty": claim.counterparty,
        "raw_amounts_found": [format_inr(p) for p in claim.raw_amounts_found],
    }

    return {
        "claim": claim_dict,
        "ledger_check": ledger_result,
        "signals": signals,
        "warning_level": warning_level,
        "next_step": next_step,
        "advice": MANDATORY_ADVICE,
        "disclaimer": MANDATORY_DISCLAIMER,
    }

