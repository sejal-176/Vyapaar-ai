"""Deterministic verification decision engine for payment screenshots.
Rule 6: Verification outcome comes from a deterministic decision table.
No LLM involvement. NO AI confidence scores.
Rule 8: A screenshot alone never proves payment; only the ledger does.
Rule 11: Cross-merchant isolation; ledger lookup filters by merchant_id.
"""
from typing import Optional
from sqlalchemy.orm import Session

from backend.models import Merchant, Submission, Transaction
from backend.core.timeutil import utc_to_ist
from backend.verification.extract import ExtractedFields
from backend.verification.ledger import get_transaction


def verify(
    db: Session,
    merchant_id: int,
    fields: ExtractedFields,
    image_hash: str,
    raw_text: str = "",
) -> dict:
    """Evaluate extracted screenshot fields against the database ledger using
    the exact 9-step decision table from PLAN.md section 7.
    Records a row in the submissions table.
    """
    evidence = []
    matched_fields = []
    conflicting_fields = []

    # Step 1: Duplicate check (record flag, but still evaluate the rest)
    existing_submission = (
        db.query(Submission)
        .filter(
            Submission.merchant_id == merchant_id,
            Submission.image_hash == image_hash,
        )
        .first()
    )
    duplicate_flag = existing_submission is not None
    if duplicate_flag:
        evidence.append("This screenshot has been submitted previously.")

    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    merchant_name = merchant.name if merchant else ""
    merchant_vpa = merchant.vpa if merchant else ""

    outcome = "UNVERIFIED"
    reason = ""
    next_step = ""
    ledger_record_data = None

    # Step 2: no UTR extracted -> UNVERIFIED
    if not fields.utr:
        outcome = "UNVERIFIED"
        reason = "Not enough information in the image"
        next_step = "Do not hand over goods yet. Check your Paytm app or bank statement directly."
        evidence.append("No 12-digit UPI reference (UTR) could be detected in the screenshot.")

    else:
        # Step 3: Lookup record in ledger
        record = get_transaction(db, merchant_id, fields.utr)

        # Step 4: record is None -> UNVERIFIED
        if record is None:
            outcome = "UNVERIFIED"
            reason = "No matching transaction record"
            next_step = "Do not hand over goods yet. Check your Paytm app or bank statement directly."
            evidence.append(f"No transaction with UTR {fields.utr} exists in your records.")

        else:
            # We found a matching ledger record
            matched_fields.append("utr")
            ledger_record_data = {
                "reference": record.reference,
                "amount_paise": record.amount_paise,
                "status": record.status,
                "created_at_ist": utc_to_ist(record.created_at_utc).strftime("%Y-%m-%d %H:%M:%S"),
            }
            evidence.append(f"Found transaction record for UTR {fields.utr} (status: {record.status}).")

            # Step 5: record.status == PENDING -> UNVERIFIED
            if record.status == "PENDING":
                outcome = "UNVERIFIED"
                reason = "Payment is still pending in our records"
                next_step = "Do not hand over goods yet. Check your Paytm app or bank statement directly."
                evidence.append("The transaction is marked as PENDING in your account.")

            # Step 6: record.status in (FAILED, REFUNDED) -> MISMATCH
            elif record.status in ("FAILED", "REFUNDED"):
                outcome = "MISMATCH"
                reason = "Our record shows this payment as failed/refunded"
                next_step = "Do not accept this payment. Create a case."
                conflicting_fields.append("status")
                evidence.append(f"The transaction is recorded as {record.status} in your ledger.")

            # Step 7: amount extracted and amount != record.amount -> MISMATCH
            elif fields.amount_paise is not None and fields.amount_paise != record.amount_paise:
                outcome = "MISMATCH"
                reason = "Amount in image differs from our record"
                next_step = "Do not accept this payment. Create a case."
                conflicting_fields.append("amount")
                evidence.append(
                    f"Screenshot amount (₹{fields.amount_paise / 100:.2f}) differs from "
                    f"ledger amount (₹{record.amount_paise / 100:.2f})."
                )

            # Step 8: recipient extracted and does not match merchant name or VPA -> MISMATCH
            elif fields.recipient and not (
                fields.recipient.lower() in merchant_name.lower()
                or merchant_name.lower() in fields.recipient.lower()
                or fields.recipient.lower() in merchant_vpa.lower()
            ):
                outcome = "MISMATCH"
                reason = "Recipient differs"
                next_step = "Do not accept this payment. Create a case."
                conflicting_fields.append("recipient")
                evidence.append(
                    f"Recipient '{fields.recipient}' does not match your business name '{merchant_name}' or VPA."
                )

            # Step 9: otherwise (SUCCESS, UTR matches, amount matches or not extracted) -> VERIFIED
            else:
                outcome = "VERIFIED"
                reason = "Payment verified against ledger record"
                next_step = "Matches the transaction record. Safe to proceed."
                if fields.amount_paise is not None:
                    matched_fields.append("amount")
                    evidence.append(f"Amount matches ledger record (₹{record.amount_paise / 100:.2f}).")
                else:
                    evidence.append("Amount could not be read from the image.")

    # Save to submissions table
    submission = Submission(
        merchant_id=merchant_id,
        image_hash=image_hash,
        utr=fields.utr,
        outcome=outcome,
    )
    db.add(submission)
    db.commit()

    return {
        "outcome": outcome,
        "reason": reason,
        "matched_fields": matched_fields,
        "conflicting_fields": conflicting_fields,
        "evidence": evidence,
        "next_step": next_step,
        "duplicate_flag": duplicate_flag,
        "extracted": {
            "amount_paise": fields.amount_paise,
            "utr": fields.utr,
            "timestamp": fields.timestamp,
            "status_text": fields.status_text,
            "recipient": fields.recipient,
        },
        "ledger_record": ledger_record_data,
        "raw_text": raw_text or fields.raw_text,
    }

