"""Evaluation script for assistant answers against live database and LLM.
Evaluates the 6 required questions against strict quality, grounding, and wording rules.
"""
import re
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db import SessionLocal
from backend.agent.agent import run_agent
from backend.agent.guard import is_grounded
from backend.tools.registry import run_tool

FORBIDDEN_REGEX = re.compile(r"\b(revenue|sales|profit|because|reason)\b", re.IGNORECASE)

QUESTIONS = [
    "How much did I collect today?",
    "aaj kitna hua?",
    "Why were my collections lower than yesterday?",
    "When do I get the most payments?",
    "Create a daily report",
    "Collections for 1 January 2020",
]


def count_sentences(text: str) -> int:
    """Count sentences by splitting on terminal punctuation (. ! ?)."""
    # Clean out periods in amounts/decimals e.g. ₹2,170.50 or numbers like 10.5
    cleaned = re.sub(r"\d+\.\d+", "NUM", text)
    cleaned = re.sub(r"\b(?:Rs|INR|IST|AM|PM)\.", "", cleaned, flags=re.IGNORECASE)
    parts = [s.strip() for s in re.split(r"[.!?]+", cleaned) if s.strip()]
    return len(parts)


def check_no_markdown(text: str) -> bool:
    """Check that text does not contain markdown formatting."""
    # Headings
    if re.search(r"^#{1,6}\s", text, re.MULTILINE):
        return False
    # Tables
    if "|---" in text or text.count("|") >= 4:
        return False
    # Bold / Italics
    if "**" in text or "__" in text:
        return False
    # Bullets
    if re.search(r"^[\*\-\+]\s+", text, re.MULTILINE):
        return False
    return True


def evaluate_question(db, merchant_id: int, q_idx: int, question: str) -> tuple[dict, bool, list[str]]:
    result = run_agent(db, merchant_id, question)
    answer = result["answer"]
    tools_used = result["tools_used"]
    mode = result["mode"]

    failures = []
    is_report = (q_idx == 4)  # "Create a daily report"
    is_no_data = (q_idx == 5)  # "Collections for 1 January 2020"

    # 1. At most 4 sentences (except report)
    if not is_report:
        num_sentences = count_sentences(answer)
        if num_sentences > 4:
            failures.append(f"Too many sentences ({num_sentences} > 4)")

    # 2. No markdown (except report template which uses plain text dashes)
    if not is_report and not check_no_markdown(answer):
        failures.append("Contains markdown formatting")

    # 3. No forbidden words (revenue, sales, profit, because, reason)
    forbidden_matches = FORBIDDEN_REGEX.findall(answer)
    if forbidden_matches:
        failures.append(f"Contains forbidden words: {forbidden_matches}")

    # 4. Ends with closing line when numbers are present
    has_numbers = bool(re.search(r"\d", answer))
    if has_numbers and not is_report:
        if "This covers digital payments only" not in answer:
            failures.append("Missing closing line 'This covers digital payments only.'")

    # 5. Passes is_grounded
    # Re-fetch tool outputs
    tool_outputs = []
    for t in tools_used:
        tool_outputs.append(run_tool(db, merchant_id, t["name"], t.get("args", {})))

    if not is_grounded(answer, tool_outputs):
        failures.append("Failed numbers grounding check")

    # 6. No-data question mentions no records
    if is_no_data:
        ans_lower = answer.lower()
        if not ("no" in ans_lower and ("record" in ans_lower or "transaction" in ans_lower or "data" in ans_lower)):
            failures.append("Did not state no records exist for that date")

    passed = len(failures) == 0
    return result, passed, failures


def main():
    db = SessionLocal()
    merchant_id = 1
    pass_count = 0

    print("=" * 80)
    print("EVALUATING VYAPAARAI ASSISTANT ON REAL QUESTIONS")
    print("=" * 80)

    try:
        for idx, q in enumerate(QUESTIONS):
            print(f"\n[{idx + 1}/6] QUESTION: \"{q}\"")
            result, passed, failures = evaluate_question(db, merchant_id, idx, q)

            print(f"MODE: {result['mode']}")
            tools_str = ", ".join(f"{t['name']}({t.get('args', {})})" for t in result["tools_used"]) or "None"
            print(f"TOOLS: {tools_str}")
            print("ANSWER:")
            print("-" * 60)
            print(result["answer"])
            print("-" * 60)

            if passed:
                print("STATUS: PASS")
                pass_count += 1
            else:
                print(f"STATUS: FAIL - Reasons: {', '.join(failures)}")

        print("\n" + "=" * 80)
        print(f"SUMMARY: {pass_count}/{len(QUESTIONS)} questions PASSED quality criteria.")
        print("=" * 80)

    finally:
        db.close()

    if pass_count < len(QUESTIONS):
        sys.exit(1)


if __name__ == "__main__":
    main()
