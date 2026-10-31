"""Agent coordinator for VyapaarAI.
Rule 3: Call it 'digital collections' only. Never mention revenue/profit.
Rule 4: No LLM-generated SQL; tool loop with typed tools only.
Rule 5: merchant_id injected by server, never visible to model.
Rule 7: Never pass untrusted OCR text or injection payloads as system instructions.
Rule 9: Separate measured facts from possible explanations.
"""
import json
import logging
import os
import re
from sqlalchemy.orm import Session

from backend.config import LLM_API_KEY
from backend.models import Merchant
from backend.analytics import latest_data_day
from backend.tools.registry import run_tool, tool_specs
from backend.agent.llm_client import get_llm_client, get_model_name
from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.guard import is_grounded, strip_markdown
from backend.agent.fallback import fallback_agent

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 4

DATA_KEYWORDS = [
    "collect", "payment", "amount", "ticket", "today", "yesterday", "date",
    "hour", "busy", "report", "status", "utr", "aaj", "kal", "kitna", "hua",
    "kam", "zyada", "drop", "lower", "higher", "compare", "summary", "how much", "when"
]


def run_agent(db: Session, merchant_id: int, message: str) -> dict:
    """Run agent tool loop with OpenAI-compatible client (Groq).
    Falls back to deterministic rule-based mode if API key is missing, invalid, or fails.
    Validates numbers with guard.py.

    Returns:
    {
        "answer": str,
        "tools_used": [{"name": str, "args": dict}],
        "mode": "llm" | "rule-based" | "template (AI answer rejected)"
    }
    """
    current_key = os.getenv("LLM_API_KEY", LLM_API_KEY).strip()
    if not current_key:
        return fallback_agent(db, merchant_id, message)

    ref_day = latest_data_day(db, merchant_id)
    if not ref_day:
        return fallback_agent(db, merchant_id, message)

    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    merchant_type = merchant.business_type if merchant else "retail store"

    system_context = (
        f"Context: Today's reference date is {ref_day.isoformat()} (IST). "
        f"The merchant business type is {merchant_type}. "
        "Data is from a synthetic demo history."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": system_context},
        {"role": "user", "content": message},
    ]

    tools_used = []
    tool_outputs = []
    is_data_question = any(k in message.lower() for k in DATA_KEYWORDS)
    retried_tool_prompt = False

    try:
        client = get_llm_client()
        model = get_model_name()
        specs = tool_specs()

        for _ in range(MAX_ITERATIONS):
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=specs,
                temperature=0,
            )

            choice = response.choices[0]
            resp_msg = choice.message

            # If tool calls were requested
            if resp_msg.tool_calls:
                messages.append(resp_msg)

                for tc in resp_msg.tool_calls:
                    fn_name = tc.function.name
                    fn_args_raw = tc.function.arguments

                    if isinstance(fn_args_raw, dict):
                        args_dict = fn_args_raw
                    elif isinstance(fn_args_raw, str):
                        try:
                            args_dict = json.loads(fn_args_raw)
                        except Exception:
                            args_dict = {"raw": fn_args_raw}
                    else:
                        args_dict = {}

                    tools_used.append({"name": fn_name, "args": args_dict})
                    tool_result = run_tool(db, merchant_id, fn_name, args_dict)
                    tool_outputs.append(tool_result)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_result),
                    })
            else:
                # If no tool call was produced for a data question on first try, retry once
                if not tools_used and is_data_question and not retried_tool_prompt:
                    retried_tool_prompt = True
                    messages.append(resp_msg)
                    messages.append({
                        "role": "user",
                        "content": "You must call one of the available tools to answer this question. Do not answer directly without calling a tool.",
                    })
                    continue

                # If generate_daily_report was called, return its exact report text per prompt rules
                for out in tool_outputs:
                    if isinstance(out, dict) and "report_text" in out:
                        return {
                            "answer": out["report_text"],
                            "tools_used": tools_used,
                            "mode": "llm",
                        }

                # Final text response from model
                raw_answer = resp_msg.content or ""
                # Strip markdown syntax if any was produced
                cleaned_answer = strip_markdown(raw_answer)

                # Append mandatory closing line if answer mentions numbers and doesn't already have it
                if re.search(r"\d", cleaned_answer) and "This covers digital payments only" not in cleaned_answer:
                    cleaned_answer = cleaned_answer.rstrip(". ") + ". This covers digital payments only."

                # Verify answer with numbers guard
                if not is_grounded(cleaned_answer, tool_outputs):
                    logger.warning("AI answer failed numbers grounding check; falling back to rule-based template.")
                    fb = fallback_agent(db, merchant_id, message)
                    return {
                        "answer": fb["answer"],
                        "tools_used": tools_used or fb["tools_used"],
                        "mode": "template (AI answer rejected)",
                    }

                return {
                    "answer": cleaned_answer,
                    "tools_used": tools_used,
                    "mode": "llm",
                }

        # Max iterations reached or loop ended: check last assistant message
        if messages and messages[-1].get("role") == "assistant" and messages[-1].get("content"):
            last_text = strip_markdown(messages[-1]["content"])
            if re.search(r"\d", last_text) and "This covers digital payments only" not in last_text:
                last_text = last_text.rstrip(". ") + ". This covers digital payments only."
            if is_grounded(last_text, tool_outputs):
                return {
                    "answer": last_text,
                    "tools_used": tools_used,
                    "mode": "llm",
                }

        fb = fallback_agent(db, merchant_id, message)
        return {
            "answer": fb["answer"],
            "tools_used": tools_used or fb["tools_used"],
            "mode": "template (AI answer rejected)",
        }

    except Exception as e:
        logger.warning(f"run_agent encountered exception: {e}; switching to rule-based fallback.")
        return fallback_agent(db, merchant_id, message)
