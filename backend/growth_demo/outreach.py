"""Outreach message drafting, margin guardrails, and status transitions for Growth Insights preview.
STRICT PRIVACY AND SAFETY RULES:
- The app NEVER sends messages. No HTTP or messaging libraries are imported.
- Only OPTED_IN customers may have drafts created or approved. Consent is re-checked at draft, approve, and mark_sent.
- Templates never include names, amounts, visit history, or surveillance words (track, monitor).
- Strict margin guardrail for percentage offers.
- State machine: DRAFT -> APPROVED -> MARKED_SENT (or DISMISSED). No backwards moves.
"""
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import json
from sqlalchemy.orm import Session

from backend.growth_demo.models import GDCustomer, GDInvoice, GDInvoiceItem, GDProduct, GDOutreach
from backend.growth_demo.config import (
    MAX_OFFER_PCT,
    MIN_MARGIN_LEFT_POINTS,
)

# Note: Hindi and Marathi wording must be checked by a native speaker.
TEMPLATES = {
    "NONE": {
        "en": (
            "Greetings from your neighborhood tea stall! We are open and look forward "
            "to serving your favorite cup of tea and snacks whenever you drop by."
        ),
        "hi": (
            "नमस्ते! आपकी चाय की दुकान पर आपका स्वागत है। "
            "जब भी समय मिले, अपनी पसंदीदा चाय और नाश्ते का आनंद लेने ज़रूर आएं।"
        ),
        "mr": (
            "नमस्कार! आपल्या चहाच्या दुकानात आपले स्वागत आहे. "
            "वेळ मिळेल तेव्हा आपल्या आवडत्या चहा आणि नाश्त्याचा आस्वाद घ्यायला नक्की या."
        ),
    },
    "LOYALTY_STAMP": {
        "en": (
            "Greetings! Collect a loyalty stamp on your next counter visit with any "
            "refreshment purchase."
        ),
        "hi": (
            "नमस्ते! अपनी अगली यात्रा पर काउंटर पर जलपान के साथ एक लॉयल्टी स्टाम्प प्राप्त करें।"
        ),
        "mr": (
            "नमस्कार! पुढील भेटीदरम्यान काउंटरवर कोणत्याही खरेदीसोबत लॉयल्टी स्टॅम्प मिळवा."
        ),
    },
    "PERCENT": {
        "en": (
            "Greetings! Enjoy a {offer_pct}% concession on your next counter order "
            "whenever you drop by."
        ),
        "hi": (
            "नमस्ते! जब भी आप आएं, अपनी अगली काउंटर खरीद पर {offer_pct}% की विशेष छूट का आनंद लें।"
        ),
        "mr": (
            "नमस्कार! जेव्हा आपण भेट द्याल, तेव्हा आपल्या पुढील काउंटर खरेदीवर {offer_pct}% सवलतीचा आनंद घ्या."
        ),
    },
}

ALLOWED_TRANSITIONS = {
    "DRAFT": ["APPROVED", "DISMISSED"],
    "APPROVED": ["MARKED_SENT", "DISMISSED"],
    "MARKED_SENT": [],
    "DISMISSED": [],
}


def evaluate_margin_guardrail(
    db: Session, customer_id: int, offer_pct: int
) -> Dict[str, Any]:
    """Check whether a percentage offer is safe based on the customer's last 5 baskets.
    Refuses if:
    - offer_pct > MAX_OFFER_PCT (10)
    - Any item in customer's last 5 invoices lacks a cost price
    - Remaining margin after discount < MIN_MARGIN_LEFT_POINTS (5 percentage points)
    """
    if offer_pct <= 0:
        return {
            "allowed": True,
            "reason": "No discount offered.",
            "margin_used": 0.0,
            "margin_left": 0.0,
        }

    if offer_pct > MAX_OFFER_PCT:
        return {
            "allowed": False,
            "reason": f"Offers cannot exceed {MAX_OFFER_PCT}%.",
            "margin_used": float(offer_pct),
            "margin_left": 0.0,
        }

    # Fetch last 5 invoices for this customer
    last_invoices = (
        db.query(GDInvoice)
        .filter(GDInvoice.customer_id == customer_id)
        .order_by(GDInvoice.invoice_date.desc(), GDInvoice.id.desc())
        .limit(5)
        .all()
    )

    if not last_invoices:
        return {
            "allowed": False,
            "reason": "No past invoices found for this customer to calculate margin.",
            "margin_used": float(offer_pct),
            "margin_left": 0.0,
        }

    total_price = 0
    total_cost = 0

    for inv in last_invoices:
        for item in inv.items:
            product = db.query(GDProduct).filter(GDProduct.id == item.product_id).first()
            if not product or product.cost_price_paise is None:
                return {
                    "allowed": False,
                    "reason": "Enter your item costs first. We can't check whether this offer would cost you money.",
                    "margin_used": float(offer_pct),
                    "margin_left": 0.0,
                }
            qty = item.quantity
            total_price += qty * item.unit_price_paise
            total_cost += qty * product.cost_price_paise

    if total_price == 0:
        return {
            "allowed": False,
            "reason": "Zero total value in past invoices.",
            "margin_used": float(offer_pct),
            "margin_left": 0.0,
        }

    basket_margin_pct = ((total_price - total_cost) / total_price) * 100.0
    margin_left = basket_margin_pct - offer_pct

    if margin_left < MIN_MARGIN_LEFT_POINTS:
        return {
            "allowed": False,
            "reason": (
                f"Offer leaves too little margin. Average basket margin is {basket_margin_pct:.1f}%, "
                f"which leaves only {margin_left:.1f}% (minimum required is {MIN_MARGIN_LEFT_POINTS}%)."
            ),
            "margin_used": float(offer_pct),
            "margin_left": round(margin_left, 1),
        }

    return {
        "allowed": True,
        "reason": f"Offer allowed. Basket margin is {basket_margin_pct:.1f}%, leaving {margin_left:.1f}% after offer.",
        "margin_used": float(offer_pct),
        "margin_left": round(margin_left, 1),
    }


def get_rendered_template(offer_type: str, language: str, offer_pct: int = 0) -> str:
    """Render plain text message template for the chosen language and offer."""
    lang = language if language in ("en", "hi", "mr") else "en"
    otype = offer_type if offer_type in TEMPLATES else "NONE"
    raw_template = TEMPLATES[otype][lang]
    if otype == "PERCENT":
        return raw_template.format(offer_pct=offer_pct)
    return raw_template


def create_outreach_draft(
    db: Session,
    customer_id: int,
    language: str = "en",
    offer_type: str = "NONE",
    offer_pct: int = 0,
    custom_text: Optional[str] = None,
) -> Tuple[Optional[GDOutreach], Optional[str]]:
    """Create a new outreach draft after validating customer consent and margin guardrail."""
    customer = db.query(GDCustomer).filter(GDCustomer.id == customer_id).first()
    if not customer:
        return None, "Customer not found."

    # Strict consent check: only OPTED_IN customers
    if customer.consent_status != "OPTED_IN":
        return None, "Customer has not opted in to receive messages."

    # Guardrail check for PERCENT offers
    guardrail = evaluate_margin_guardrail(db, customer_id, offer_pct if offer_type == "PERCENT" else 0)
    if offer_type == "PERCENT" and not guardrail["allowed"]:
        return None, guardrail["reason"]

    message_text = custom_text or get_rendered_template(offer_type, language, offer_pct)

    outreach = GDOutreach(
        customer_id=customer_id,
        status="DRAFT",
        language=language,
        offer_type=offer_type,
        offer_pct=offer_pct if offer_type == "PERCENT" else 0,
        message_text=message_text,
        evidence_json=json.dumps(guardrail),
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(outreach)
    db.commit()
    db.refresh(outreach)
    return outreach, None


def update_outreach_status(
    db: Session,
    outreach_id: int,
    action: str,  # "edit", "approve", "mark_sent", "dismiss"
    new_message_text: Optional[str] = None,
) -> Tuple[Optional[GDOutreach], Optional[str]]:
    """Transition outreach status along allowed state-machine paths.
    Re-checks consent at approve and mark_sent.
    """
    outreach = db.query(GDOutreach).filter(GDOutreach.id == outreach_id).first()
    if not outreach:
        return None, "Outreach record not found."

    customer = db.query(GDCustomer).filter(GDCustomer.id == outreach.customer_id).first()
    if not customer:
        return None, "Customer not found."

    current_status = outreach.status
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if action == "edit":
        if current_status not in ("DRAFT", "APPROVED"):
            return None, f"Cannot edit an outreach in status '{current_status}'."
        if new_message_text is not None:
            outreach.message_text = new_message_text
        db.commit()
        db.refresh(outreach)
        return outreach, None

    # Map actions to target statuses
    target_status_map = {
        "approve": "APPROVED",
        "mark_sent": "MARKED_SENT",
        "dismiss": "DISMISSED",
    }
    if action not in target_status_map:
        return None, f"Unknown action '{action}'."

    target_status = target_status_map[action]
    allowed_targets = ALLOWED_TRANSITIONS.get(current_status, [])
    if target_status not in allowed_targets:
        return None, f"Illegal status transition from '{current_status}' to '{target_status}'."

    # Re-verify consent
    if target_status in ("APPROVED", "MARKED_SENT"):
        if customer.consent_status != "OPTED_IN":
            return None, "Customer has not opted in to receive messages."

    outreach.status = target_status
    if target_status == "APPROVED":
        outreach.approved_at = now_str
    elif target_status == "MARKED_SENT":
        outreach.marked_sent_at = now_str

    db.commit()
    db.refresh(outreach)
    return outreach, None

