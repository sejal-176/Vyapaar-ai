"""Tool registry for the LLM agent.
Rule 4: No LLM-generated SQL; the LLM only calls these typed tools.
Rule 5: merchant_id is never a tool parameter the model can see or set.
        The server injects it.
Rule 11: Cross-merchant isolation; all tools filter by merchant_id.
"""
from datetime import date, datetime, timedelta
import json
from typing import Optional
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from backend.core.money import format_inr
from backend.core.timeutil import utc_to_ist
from backend.models import Case, Merchant, Transaction
from backend.analytics import (
    daily_summary,
    compare_periods,
    hourly_activity,
)
from backend.api.report import _generate_report_text
from backend.verification.ledger import get_transaction


# --- Helper for 12-hour window label (e.g. 18 -> "6-7 PM") ---
def format_hour_window(h: int) -> str:
    start_num = 12 if h % 12 == 0 else h % 12
    end_h = (h + 1) % 24
    end_num = 12 if end_h % 12 == 0 else end_h % 12
    start_am_pm = "AM" if h < 12 else "PM"
    end_am_pm = "AM" if end_h < 12 else "PM"
    if start_am_pm == end_am_pm:
        return f"{start_num}-{end_num} {end_am_pm}"
    return f"{start_num} {start_am_pm}-{end_num} {end_am_pm}"


# --- Pydantic Input Models (NO merchant_id field exposed) ---

class DailySummaryInput(BaseModel):
    date: str = Field(..., description="IST calendar date in YYYY-MM-DD format (e.g. '2026-10-30')")


class ComparePeriodsInput(BaseModel):
    date_a: str = Field(..., description="Earlier IST date in YYYY-MM-DD format (e.g. yesterday)")
    date_b: str = Field(..., description="Later IST date in YYYY-MM-DD format (e.g. today / latest data day)")
    up_to_hour: Optional[int] = Field(None, description="Optional IST hour limit (0-23) for partial day comparisons")


class HourlyActivityInput(BaseModel):
    date: str = Field(..., description="IST calendar date in YYYY-MM-DD format")


class PaymentStatusInput(BaseModel):
    utr: str = Field(..., description="12-digit numeric UPI reference / UTR")


class CreateFollowupCaseInput(BaseModel):
    description: str = Field(..., description="Detailed description of the issue or payment discrepancy")
    related_reference: Optional[str] = Field(None, description="Optional 12-digit UTR reference related to this case")


class GenerateDailyReportInput(BaseModel):
    date: str = Field(..., description="IST calendar date in YYYY-MM-DD format (e.g. '2026-10-30')")


# --- Tool Implementations (merchant_id injected by server) ---

def _tool_get_daily_summary(db: Session, merchant_id: int, args: DailySummaryInput) -> dict:
    try:
        d = date.fromisoformat(args.date.strip())
    except ValueError:
        return {"error": f"Invalid date format '{args.date}'. Expected YYYY-MM-DD."}

    summary = daily_summary(db, merchant_id, d)
    if not summary.get("has_data", False):
        return {
            "date": summary["date"],
            "has_data": False,
            "day_complete": summary.get("day_complete", True),
            "data_up_to_ist": summary.get("data_up_to_ist"),
            "message": f"No transaction records found for {summary['date']}.",
        }

    return {
        "date": summary["date"],
        "has_data": True,
        "collections_paise": summary["collections_paise"],
        "collections_inr": format_inr(summary["collections_paise"]),
        "success_count": summary["success_count"],
        "pending_count": summary["pending_count"],
        "pending_paise": summary.get("pending_paise", 0),
        "pending_inr": format_inr(summary.get("pending_paise", 0)),
        "failed_count": summary["failed_count"],
        "refunded_count": summary["refunded_count"],
        "refund_total_paise": summary["refund_total_paise"],
        "refund_total_inr": format_inr(summary["refund_total_paise"]),
        "avg_ticket_paise": summary["avg_ticket_paise"],
        "avg_ticket_inr": format_inr(summary["avg_ticket_paise"]),
        "day_complete": summary.get("day_complete", True),
        "data_up_to_ist": summary.get("data_up_to_ist"),
    }


def _tool_compare_periods(db: Session, merchant_id: int, args: ComparePeriodsInput) -> dict:
    try:
        d_a = date.fromisoformat(args.date_a.strip())
        d_b = date.fromisoformat(args.date_b.strip())
    except ValueError:
        return {"error": f"Invalid date format. Expected YYYY-MM-DD for date_a ('{args.date_a}') and date_b ('{args.date_b}')."}

    res = compare_periods(db, merchant_id, d_a, d_b, up_to_hour=args.up_to_hour)
    change_paise = res["delta_collections_paise"]
    change_inr = format_inr(change_paise)

    return {
        "date_a": res["date_a"],
        "date_b": res["date_b"],
        "collections_a_paise": res["day_a"]["collections_paise"],
        "collections_a_inr": format_inr(res["day_a"]["collections_paise"]),
        "collections_b_paise": res["day_b"]["collections_paise"],
        "collections_b_inr": format_inr(res["day_b"]["collections_paise"]),
        "change_paise": change_paise,
        "change_inr": change_inr,
        "count_a": res["day_a"]["success_count"],
        "count_b": res["day_b"]["success_count"],
        "delta_success_count": res["delta_success_count"],
        "avg_ticket_a_paise": res["day_a"]["avg_ticket_paise"],
        "avg_ticket_a_inr": format_inr(res["day_a"]["avg_ticket_paise"]),
        "avg_ticket_b_paise": res["day_b"]["avg_ticket_paise"],
        "avg_ticket_b_inr": format_inr(res["day_b"]["avg_ticket_paise"]),
        "volume_effect_paise": res["volume_effect"],
        "volume_effect_inr": format_inr(res["volume_effect"]),
        "ticket_effect_paise": res["ticket_effect"],
        "ticket_effect_inr": format_inr(res["ticket_effect"]),
        "driver_summary": res["driver_summary"],
        "main_driver": res["main_driver"],
        "compare_basis": res["compare_basis"],
        "day_complete": res["day_complete"],
        "data_up_to_ist": res["data_up_to_ist"],
        "note": res.get("note"),
    }


def _tool_get_hourly_activity(db: Session, merchant_id: int, args: HourlyActivityInput) -> dict:
    try:
        d = date.fromisoformat(args.date.strip())
    except ValueError:
        return {"error": f"Invalid date format '{args.date}'. Expected YYYY-MM-DD."}

    hourly = hourly_activity(db, merchant_id, d)
    peak = max(hourly, key=lambda x: (x["amount_paise"], x["count"]))
    peak_count = peak["count"]
    tie_on_count = any(
        h["hour_ist"] != peak["hour_ist"] and h["count"] == peak_count
        for h in hourly
        if peak_count > 0
    )

    peak_hour = {
        "label": format_hour_window(peak["hour_ist"]),
        "count": peak["count"],
        "amount_paise": peak["amount_paise"],
        "amount_inr": format_inr(peak["amount_paise"]),
        "peak_by": "amount",
        "tie_on_count": tie_on_count,
    }

    return {
        "date": d.isoformat(),
        "peak_hour": peak_hour,
    }


def _tool_get_payment_status(db: Session, merchant_id: int, args: PaymentStatusInput) -> dict:
    tx = get_transaction(db, merchant_id, args.utr)
    if not tx:
        return {"found": False, "reference": args.utr}

    return {
        "found": True,
        "reference": tx.reference,
        "amount_paise": tx.amount_paise,
        "amount_inr": format_inr(tx.amount_paise),
        "status": tx.status,
        "txn_type": tx.txn_type,
        "created_at_ist": utc_to_ist(tx.created_at_utc).strftime("%Y-%m-%d %H:%M:%S"),
    }


def _tool_create_followup_case(db: Session, merchant_id: int, args: CreateFollowupCaseInput) -> dict:
    case = Case(
        merchant_id=merchant_id,
        case_type="AGENT_FOLLOWUP",
        description=args.description.strip(),
        related_reference=args.related_reference.strip() if args.related_reference else None,
        status="OPEN",
    )
    db.add(case)
    db.commit()
    return {
        "case_id": case.id,
        "merchant_id": case.merchant_id,
        "case_type": case.case_type,
        "status": case.status,
        "description": case.description,
        "related_reference": case.related_reference,
    }


def _tool_generate_daily_report(db: Session, merchant_id: int, args: GenerateDailyReportInput) -> dict:
    try:
        report_date = date.fromisoformat(args.date.strip())
    except ValueError:
        return {"error": f"Invalid date format '{args.date}'. Expected YYYY-MM-DD."}

    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        return {"error": f"Merchant {merchant_id} not found."}

    prev_date = report_date - timedelta(days=1)
    summary = daily_summary(db, merchant_id, report_date)
    prev_summary = daily_summary(db, merchant_id, prev_date)
    comparison = compare_periods(db, merchant_id, prev_date, report_date)

    hourly = hourly_activity(db, merchant_id, report_date)
    peak = max(hourly, key=lambda x: (x["amount_paise"], x["count"]))
    peak_hour = peak["hour_ist"]
    peak_info = {
        "hour_ist": peak_hour,
        "peak_hour_display": f"{peak_hour:02d}:00 to {peak_hour+1:02d}:00 IST",
        "amount_paise": peak["amount_paise"],
        "count": peak["count"],
    }

    open_cases = (
        db.query(Case)
        .filter(Case.merchant_id == merchant_id, Case.status == "OPEN")
        .count()
    )

    report_text = _generate_report_text(
        merchant=merchant,
        report_date=report_date,
        prev_date=prev_date,
        summary=summary,
        prev_summary=prev_summary,
        comparison=comparison,
        peak_info=peak_info,
        open_cases=open_cases,
    )

    return {
        "date": report_date.isoformat(),
        "report_text": report_text,
    }


TOOL_REGISTRY = {
    "get_daily_summary": {
        "description": "Get digital payment collections, counts, and average ticket for a given IST date.",
        "model": DailySummaryInput,
        "handler": _tool_get_daily_summary,
    },
    "compare_periods": {
        "description": "Compare digital collections between two IST dates with volume vs ticket size decomposition, driver summary and percentage breakdown.",
        "model": ComparePeriodsInput,
        "handler": _tool_compare_periods,
    },
    "get_hourly_activity": {
        "description": "Get peak hourly activity by amount and count tie indicator for a given IST date.",
        "model": HourlyActivityInput,
        "handler": _tool_get_hourly_activity,
    },
    "get_payment_status": {
        "description": "Lookup the ledger status and amount of a specific 12-digit UTR payment reference.",
        "model": PaymentStatusInput,
        "handler": _tool_get_payment_status,
    },
    "create_followup_case": {
        "description": "Create an internal demo dispute or follow-up case for a discrepancy.",
        "model": CreateFollowupCaseInput,
        "handler": _tool_create_followup_case,
    },
    "generate_daily_report": {
        "description": "Generate a complete deterministic daily business report text for a given IST date.",
        "model": GenerateDailyReportInput,
        "handler": _tool_generate_daily_report,
    },
}


def tool_specs() -> list[dict]:
    """Build OpenAI-compatible tool specifications from Pydantic schemas."""
    specs = []
    for name, info in TOOL_REGISTRY.items():
        model_cls: type[BaseModel] = info["model"]
        schema = model_cls.model_json_schema()
        # Keep schema clean
        schema.pop("title", None)
        specs.append({
            "type": "function",
            "function": {
                "name": name,
                "description": info["description"],
                "parameters": schema,
            },
        })
    return specs


def run_tool(db: Session, merchant_id: int, name: str, raw_args: dict | str) -> dict:
    """Validate raw arguments with the tool's Pydantic model and execute.
    - Errors are always returned as {"error": "..."}, never raised.
    - Injects merchant_id (never seen by LLM).
    """
    if name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool '{name}'. Available tools: {list(TOOL_REGISTRY.keys())}"}

    tool_info = TOOL_REGISTRY[name]
    model_cls: type[BaseModel] = tool_info["model"]

    # Parse arguments if passed as JSON string
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except Exception as e:
            return {"error": f"Invalid JSON string in tool arguments: {e}"}

    try:
        validated_model = model_cls.model_validate(raw_args or {})
    except ValidationError as e:
        return {"error": f"Argument validation failed for tool '{name}': {e.errors()}"}

    try:
        result = tool_info["handler"](db, merchant_id, validated_model)
        return result
    except Exception as e:
        return {"error": f"Tool execution failed for '{name}': {str(e)}"}
