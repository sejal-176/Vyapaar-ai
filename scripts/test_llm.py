"""Script to test agent execution in both LLM mode and rule-based fallback mode."""
import sys
from pathlib import Path
import json
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

from backend.db import SessionLocal
from backend.agent import run_agent
from backend.config import LLM_API_KEY


def test_agent_run():
    db = SessionLocal()
    merchant_id = 1
    query = "Why were my collections lower than yesterday?"

    print("=" * 60)
    print("RUN 1: Live agent call with Groq LLM API")
    print("=" * 60)
    print(f"Query: {query}")
    res1 = run_agent(db, merchant_id, query)
    print(f"Mode: {res1['mode']}")
    print(f"Tools Used: {json.dumps(res1['tools_used'], indent=2)}")
    print(f"Answer:\n{res1['answer']}")

    print("\n" + "=" * 60)
    print("RUN 2: Agent call with invalid LLM_API_KEY ('gsk_invalid_test_key_123')")
    print("=" * 60)
    original_key = os.environ.get("LLM_API_KEY", LLM_API_KEY)
    os.environ["LLM_API_KEY"] = "gsk_invalid_test_key_123"

    try:
        res2 = run_agent(db, merchant_id, query)
        print(f"Mode: {res2['mode']}")
        print(f"Tools Used: {json.dumps(res2['tools_used'], indent=2)}")
        print(f"Answer:\n{res2['answer']}")
    finally:
        if original_key is not None:
            os.environ["LLM_API_KEY"] = original_key
        else:
            os.environ.pop("LLM_API_KEY", None)

    print("=" * 60)
    print("Original API key restored.")
    db.close()


if __name__ == "__main__":
    test_agent_run()
