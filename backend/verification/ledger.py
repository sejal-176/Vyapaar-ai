"""Ledger lookup service.
This is the single swap point for a real payment API.
Rule 11: Cross-merchant isolation; every query filters by merchant_id.
"""
from typing import Optional
from sqlalchemy.orm import Session
from backend.models import Transaction


def get_transaction(db: Session, merchant_id: int, utr: str) -> Optional[Transaction]:
    """Lookup a transaction in the local ledger by merchant_id and 12-digit UTR reference.
    Stands in for a real Paytm/bank payment status API.
    A UTR belonging to another merchant will not match.
    """
    if not utr:
        return None

    clean_utr = utr.strip()
    return (
        db.query(Transaction)
        .filter(
            Transaction.merchant_id == merchant_id,
            Transaction.reference == clean_utr,
        )
        .first()
    )

