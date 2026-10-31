"""Numbers guard and grounding validator for the agent.
Rule 4: Never invent numbers; all values sourced from typed backend tools.
"""
from decimal import Decimal, InvalidOperation
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def strip_markdown(text: str) -> str:
    """Reject/strip markdown formatting (headings, table lines, bullets, bold).
    Converts markdown into clean plain text.
    """
    if not text:
        return ""

    lines = []
    for line in text.splitlines():
        trimmed = line.strip()

        # Skip table divider rows (e.g. |---|---|)
        if re.match(r"^\|?[\s\-:|]+\|?$", trimmed):
            continue

        # Strip table cell formatting if a table line
        if trimmed.startswith("|") and trimmed.endswith("|"):
            cells = [c.strip() for c in trimmed.strip("|").split("|")]
            trimmed = " ".join(c for c in cells if c)

        # Strip heading markers: #, ##, etc.
        trimmed = re.sub(r"^#{1,6}\s*", "", trimmed)

        # Strip bullet points: -, *, +
        trimmed = re.sub(r"^[\*\-\+]\s+", "", trimmed)

        # Strip bold/italic markdown: **text**, *text*, __text__, _text_
        trimmed = re.sub(r"\*\*([^*]+)\*\*", r"\1", trimmed)
        trimmed = re.sub(r"\*([^*]+)\*", r"\1", trimmed)
        trimmed = re.sub(r"__([^_]+)__", r"\1", trimmed)
        trimmed = re.sub(r"_([^_]+)_", r"\1", trimmed)

        if trimmed:
            lines.append(trimmed)

    return "\n".join(lines)


def _collect_allowed_numbers(tool_outputs: list[dict]) -> tuple[set[Decimal], set[int]]:
    """Traverse all tool outputs and collect allowed rupee amounts (as Decimals)
    and allowed transaction counts (as ints).
    """
    allowed_amounts: set[Decimal] = set()
    allowed_counts: set[int] = set()

    def _add_amount(d: Decimal):
        allowed_amounts.add(d)
        allowed_amounts.add(abs(d))

    def _scan(obj: Any, key_name: str = ""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _scan(v, k)
        elif isinstance(obj, list):
            for item in obj:
                _scan(item, key_name)
        elif isinstance(obj, (int, float)):
            # If key indicates paise, convert to rupees
            if key_name.endswith("_paise") or key_name in ("collections_paise", "amount_paise", "pending_paise", "refund_total_paise", "volume_effect", "ticket_effect", "delta_collections_paise"):
                try:
                    dec = Decimal(str(obj)) / Decimal(100)
                    _add_amount(dec)
                except Exception:
                    pass
            # If key indicates a count
            if "count" in key_name or key_name in ("count_a", "count_b", "delta_success_count", "open_cases"):
                try:
                    cnt = int(obj)
                    allowed_counts.add(cnt)
                    allowed_counts.add(abs(cnt))
                except Exception:
                    pass
        elif isinstance(obj, str):
            # Scan text for rupee amounts: e.g. "₹2,170.50"
            for m in re.finditer(r"₹\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?)", obj):
                try:
                    raw = m.group(1).replace(",", "")
                    _add_amount(Decimal(raw))
                except Exception:
                    pass
            # Scan text for counts: e.g. "48 payments"
            for m in re.finditer(r"\b([0-9]+)\s+(?:successful\s+)?(?:payments?|transactions?)", obj, re.IGNORECASE):
                try:
                    allowed_counts.add(int(m.group(1)))
                except Exception:
                    pass

    for out in tool_outputs:
        _scan(out)

    return allowed_amounts, allowed_counts


def is_grounded(answer: str, tool_outputs: list[dict]) -> bool:
    """Validate that every rupee amount and payment count in `answer`
    originates strictly from the turn's `tool_outputs`.
    """
    if not answer:
        return True

    # If any tool output is a pre-rendered report_text and answer matches or contains it, accept immediately
    for out in tool_outputs:
        if isinstance(out, dict) and "report_text" in out:
            if out["report_text"].strip() in answer.strip() or answer.strip() in out["report_text"].strip():
                return True

    # 1. Extract all rupee amounts from answer
    rupee_matches = re.findall(r"₹\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?)", answer)

    # 2. Extract all counts followed by "payments" or "transactions" (never preceded by a decimal point)
    count_matches = re.findall(r"(?<!\.)\b([0-9]+)\s+(?:successful\s+)?(?:payments?|transactions?)\b", answer, re.IGNORECASE)

    # If answer mentions no amounts and no counts, it is inherently grounded (e.g. no data message)
    if not rupee_matches and not count_matches:
        return True

    # If answer contains numbers but no tools were executed, reject
    if not tool_outputs:
        logger.warning("Grounding check failed: Answer mentions numbers/counts but tool_outputs is empty.")
        return False

    allowed_amounts, allowed_counts = _collect_allowed_numbers(tool_outputs)

    # Check each rupee amount
    for raw in rupee_matches:
        try:
            amt = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            logger.warning(f"Grounding check failed: Unparseable rupee amount '{raw}'.")
            return False

        # Match against allowed amounts with small float/decimal epsilon
        matched = any(abs(amt - allowed) < Decimal("0.001") for allowed in allowed_amounts)
        if not matched:
            logger.warning(
                f"Grounding check failed: Rupee amount ₹{amt} in answer not found in tool outputs. Allowed: {allowed_amounts}"
            )
            return False

    # Check each count
    for raw in count_matches:
        try:
            cnt = int(raw)
        except ValueError:
            logger.warning(f"Grounding check failed: Unparseable count '{raw}'.")
            return False

        if cnt not in allowed_counts:
            logger.warning(
                f"Grounding check failed: Payment count '{cnt}' in answer not found in tool outputs. Allowed: {allowed_counts}"
            )
            return False

    return True

