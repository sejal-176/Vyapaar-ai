"""Ledger check for extracted payment claims against trusted database records.
Rule 11: Cross-merchant isolation; every query is scoped to merchant_id.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from backend.analytics.summary import latest_data_day
from backend.core.money import format_inr
from backend.core.timeutil import IST, utc_to_ist, ist_day_bounds_utc, to_utc
from backend.models import Transaction
from backend.scam.claims import Claim
from backend.verification.ledger import get_transaction


def _parse_claim_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse extracted timestamp string into UTC datetime assuming naive times are IST."""
    if not ts_str:
        return None

    # Formats to try:
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d %b %Y, %I:%M %p",
        "%d %B %Y, %I:%M %p",
        "%d %b %Y %I:%M %p",
        "%d %B %Y %I:%M %p",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
    ]

    clean_ts = ts_str.strip()
    for fmt in formats:
        try:
            dt = datetime.strptime(clean_ts, fmt)
            # Add IST timezone if naive
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)
            return to_utc(dt).replace(tzinfo=None)
        except Exception:
            continue
    return None


def check_claim(db: Session, merchant_id: int, claim: Claim) -> dict:
    """Evaluate extracted claim against transaction ledger in strict decision table order.

    Returns:
    {
        "outcome": "VERIFIED" | "UNVERIFIED" | "MISMATCH" | "NOT_CHECKABLE",
        "reason": str,
        "matched_fields": list[str],
        "conflicting_fields": list[str],
        "evidence": list[str],
        "ledger_record": dict | None,
        "candidates": list[dict],
        "possible_match": dict | None,
    }
    """
    matched_fields: list[str] = []
    conflicting_fields: list[str] = []
    evidence: list[str] = []

    # 1. No amount, no UTR, and direction unknown
    if claim.amount_paise is None and not claim.utr and claim.direction == "unknown":
        return {
            "outcome": "NOT_CHECKABLE",
            "reason": "No payment claim found in this message.",
            "matched_fields": [],
            "conflicting_fields": [],
            "evidence": ["Message contains no payment amount, reference number, or payment action."],
            "ledger_record": None,
            "candidates": [],
            "possible_match": None,
        }

    # 2. UTR present
    if claim.utr:
        tx = get_transaction(db, merchant_id, claim.utr)

        # 2a. Not found
        if not tx:
            conflicting_fields.append("reference")
            return {
                "outcome": "UNVERIFIED",
                "reason": "No matching transaction record.",
                "matched_fields": [],
                "conflicting_fields": conflicting_fields,
                "evidence": [f"UTR {claim.utr} was not found in your transaction ledger."],
                "ledger_record": None,
                "candidates": [],
                "possible_match": None,
            }

        # Format ledger record
        ledger_record = {
            "reference": tx.reference,
            "amount_paise": tx.amount_paise,
            "amount_inr": format_inr(tx.amount_paise),
            "status": tx.status,
            "txn_type": tx.txn_type,
            "created_at_ist": utc_to_ist(tx.created_at_utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
        matched_fields.append("reference")

        # 2b. Status is PENDING
        if tx.status == "PENDING":
            evidence.append(f"Transaction {tx.reference} exists in your ledger but is still pending settlement.")
            return {
                "outcome": "UNVERIFIED",
                "reason": "Payment is still pending in our records.",
                "matched_fields": matched_fields,
                "conflicting_fields": ["status"],
                "evidence": evidence,
                "ledger_record": ledger_record,
                "candidates": [],
                "possible_match": None,
            }

        # 2c. Status is FAILED or REFUNDED
        if tx.status in ("FAILED", "REFUNDED"):
            conflicting_fields.append("status")
            evidence.append(f"Ledger record shows status is {tx.status}, not SUCCESS.")
            return {
                "outcome": "MISMATCH",
                "reason": "Our record shows this payment as failed/refunded.",
                "matched_fields": matched_fields,
                "conflicting_fields": conflicting_fields,
                "evidence": evidence,
                "ledger_record": ledger_record,
                "candidates": [],
                "possible_match": None,
            }

        # 2d. Amount in message differs from record
        if claim.amount_paise is not None and claim.amount_paise != tx.amount_paise:
            conflicting_fields.append("amount")
            evidence.append(
                f"Claimed amount {format_inr(claim.amount_paise)} does not match ledger amount {format_inr(tx.amount_paise)}."
            )
            return {
                "outcome": "MISMATCH",
                "reason": "Amount in message differs from our record.",
                "matched_fields": matched_fields,
                "conflicting_fields": conflicting_fields,
                "evidence": evidence,
                "ledger_record": ledger_record,
                "candidates": [],
                "possible_match": None,
            }

        # 2e. Direction differs from record
        # (direction is credit but txn_type is REFUND, or direction is refund but txn_type is PAYMENT)
        if (claim.direction == "credit" and tx.txn_type == "REFUND") or (
            claim.direction == "refund" and tx.txn_type == "PAYMENT"
        ):
            conflicting_fields.append("direction")
            evidence.append(f"Claimed direction ({claim.direction}) conflicts with record type ({tx.txn_type}).")
            return {
                "outcome": "MISMATCH",
                "reason": "Direction differs from our record.",
                "matched_fields": matched_fields,
                "conflicting_fields": conflicting_fields,
                "evidence": evidence,
                "ledger_record": ledger_record,
                "candidates": [],
                "possible_match": None,
            }

        # 2f. SUCCESS, amount matches or no amount in message
        if claim.amount_paise is not None:
            matched_fields.append("amount")
            evidence.append(f"UTR and amount ({format_inr(tx.amount_paise)}) match your ledger record.")
        else:
            evidence.append("Amount could not be read from the message.")
            evidence.append(f"UTR matches successful transaction for {format_inr(tx.amount_paise)}.")

        return {
            "outcome": "VERIFIED",
            "reason": "This transaction exists in your records.",
            "matched_fields": matched_fields,
            "conflicting_fields": [],
            "evidence": evidence,
            "ledger_record": ledger_record,
            "candidates": [],
            "possible_match": None,
        }

    # 3. No UTR but an amount: candidate search on the same merchant for SUCCESS and PENDING payments with same amount
    if claim.amount_paise is not None:
        ts_utc = _parse_claim_timestamp(claim.timestamp)
        if ts_utc:
            start_utc = ts_utc - timedelta(minutes=30)
            end_utc = ts_utc + timedelta(minutes=30)
        else:
            ref_day = latest_data_day(db, merchant_id)
            if ref_day:
                s_utc, e_utc = ist_day_bounds_utc(ref_day)
                start_utc = s_utc.replace(tzinfo=None)
                end_utc = e_utc.replace(tzinfo=None)
            else:
                start_utc = datetime.min
                end_utc = datetime.max

        candidate_rows = (
            db.query(Transaction)
            .filter(
                Transaction.merchant_id == merchant_id,
                Transaction.status.in_(["SUCCESS", "PENDING"]),
                Transaction.amount_paise == claim.amount_paise,
                Transaction.created_at_utc >= start_utc,
                Transaction.created_at_utc <= end_utc,
            )
            .order_by(Transaction.created_at_utc.desc())
            .all()
        )

        candidates = [
            {
                "reference": c.reference,
                "amount_inr": format_inr(c.amount_paise),
                "status": c.status,
                "time_ist": utc_to_ist(c.created_at_utc).strftime("%Y-%m-%d %H:%M:%S"),
            }
            for c in candidate_rows[:5]
        ]

        if len(candidate_rows) == 1:
            matched_fields.append("amount")
            return {
                "outcome": "UNVERIFIED",
                "reason": "One possible match found. Amount alone is not proof. Check the reference number in your Paytm app.",
                "matched_fields": matched_fields,
                "conflicting_fields": ["reference"],
                "evidence": [
                    f"Found 1 transaction for {format_inr(claim.amount_paise)} within the matching window.",
                    "No reference number was in the message to confirm identity.",
                ],
                "ledger_record": None,
                "candidates": candidates,
                "possible_match": candidates[0],
            }
        elif len(candidate_rows) > 1:
            matched_fields.append("amount")
            return {
                "outcome": "UNVERIFIED",
                "reason": "Several possible matches. Cannot tell which one this message refers to.",
                "matched_fields": matched_fields,
                "conflicting_fields": ["reference"],
                "evidence": [
                    f"Found {len(candidate_rows)} transactions for {format_inr(claim.amount_paise)} within the window.",
                    "Without a reference number, the specific transaction cannot be identified.",
                ],
                "ledger_record": None,
                "candidates": candidates,
                "possible_match": None,
            }
        else:
            return {
                "outcome": "UNVERIFIED",
                "reason": "No matching transaction record.",
                "matched_fields": [],
                "conflicting_fields": ["reference", "amount"],
                "evidence": [f"No transactions found for {format_inr(claim.amount_paise)} in the search window."],
                "ledger_record": None,
                "candidates": [],
                "possible_match": None,
            }

    # Fallback if only direction was extracted but no amount and no UTR
    return {
        "outcome": "NOT_CHECKABLE",
        "reason": "No payment claim found in this message.",
        "matched_fields": [],
        "conflicting_fields": [],
        "evidence": ["Message indicates payment direction but contains no amount or reference number."],
        "ledger_record": None,
        "candidates": [],
        "possible_match": None,
    }

