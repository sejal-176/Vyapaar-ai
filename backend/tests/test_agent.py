"""Unit tests for tool registry and conversational agent (mocked LLM, no network)."""
from datetime import date, datetime
import json
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base
from backend.models import Merchant, Transaction, Case
from backend.core.timeutil import to_utc
from backend.tools.registry import run_tool, tool_specs
from backend.agent.agent import run_agent
from backend.agent.fallback import fallback_agent


@pytest.fixture
def db_session():
    """In-memory SQLite database session seeded with test data."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    m1 = Merchant(id=1, name="Sharma Tea Stall", business_type="tea stall", vpa="sharmatea@demo")
    m2 = Merchant(id=2, name="Gupta Kirana Store", business_type="kirana", vpa="guptakirana@demo")
    session.add_all([m1, m2])
    session.commit()

    # Seed transactions for Merchant 1 on 2026-10-24 and 2026-10-25
    tx1 = Transaction(
        merchant_id=1,
        reference="100000000001",
        amount_paise=4000,
        status="SUCCESS",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 24, 10, 0, 0)).replace(tzinfo=None),
    )
    tx2 = Transaction(
        merchant_id=1,
        reference="100000000002",
        amount_paise=6000,
        status="SUCCESS",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 10, 0, 0)).replace(tzinfo=None),
    )
    # Transaction for Merchant 2
    tx_m2 = Transaction(
        merchant_id=2,
        reference="200000000001",
        amount_paise=50000,
        status="SUCCESS",
        txn_type="PAYMENT",
        created_at_utc=to_utc(datetime(2026, 10, 25, 11, 0, 0)).replace(tzinfo=None),
    )

    session.add_all([tx1, tx2, tx_m2])
    session.commit()

    yield session
    session.close()


def test_tool_registry_specs():
    specs = tool_specs()
    assert len(specs) == 6
    tool_names = [s["function"]["name"] for s in specs]
    assert "get_daily_summary" in tool_names
    assert "compare_periods" in tool_names
    assert "get_hourly_activity" in tool_names
    assert "get_payment_status" in tool_names
    assert "create_followup_case" in tool_names
    assert "generate_daily_report" in tool_names

    # Check merchant_id is NEVER in tool schema
    for s in specs:
        properties = s["function"]["parameters"].get("properties", {})
        assert "merchant_id" not in properties


def test_tool_execution_and_formatted_inr(db_session):
    res = run_tool(db_session, merchant_id=1, name="get_daily_summary", raw_args={"date": "2026-10-25"})
    assert "error" not in res
    assert res["collections_paise"] == 6000
    assert res["collections_inr"] == "₹60.00"
    assert res["avg_ticket_inr"] == "₹60.00"


def test_tool_error_handling(db_session):
    # Unknown tool returns error dict, never raises
    res_unknown = run_tool(db_session, merchant_id=1, name="nonexistent_tool", raw_args={})
    assert "error" in res_unknown
    assert "Unknown tool" in res_unknown["error"]

    # Invalid arguments return error dict, never raises
    res_invalid = run_tool(db_session, merchant_id=1, name="get_daily_summary", raw_args="invalid json {")
    assert "error" in res_invalid

    # Missing required field
    res_missing = run_tool(db_session, merchant_id=1, name="get_daily_summary", raw_args={})
    assert "error" in res_missing


def test_tool_cross_merchant_isolation(db_session):
    """Rule 11: A UTR belonging to Merchant 2 cannot be accessed by Merchant 1."""
    res_m1 = run_tool(db_session, merchant_id=1, name="get_payment_status", raw_args={"utr": "200000000001"})
    assert res_m1.get("found") is False

    res_m2 = run_tool(db_session, merchant_id=2, name="get_payment_status", raw_args={"utr": "200000000001"})
    assert res_m2.get("found") is True
    assert res_m2["amount_inr"] == "₹500.00"


def test_tool_create_followup_case(db_session):
    res = run_tool(
        db_session,
        merchant_id=1,
        name="create_followup_case",
        raw_args={"description": "Customer says ₹500 was deducted twice", "related_reference": "100000000001"},
    )
    assert "error" not in res
    assert res["case_id"] is not None
    assert res["status"] == "OPEN"

    # Verify persisted in database
    case_row = db_session.query(Case).filter_by(id=res["case_id"]).first()
    assert case_row is not None
    assert case_row.merchant_id == 1


# --- Agent Mock Tests ---

def test_mocked_llm_tool_loop(db_session):
    """Mocked LLM executes a tool call and generates a grounded response."""
    # Step 1 response from LLM: request tool get_daily_summary
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_abc123"
    mock_tool_call.function.name = "get_daily_summary"
    mock_tool_call.function.arguments = json.dumps({"date": "2026-10-25"})

    msg_1 = MagicMock()
    msg_1.tool_calls = [mock_tool_call]
    msg_1.content = None

    # Step 2 response from LLM: final answer citing the tool result
    msg_2 = MagicMock()
    msg_2.tool_calls = None
    msg_2.content = "On 2026-10-25, your digital collections were ₹60.00 across 1 payment."

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=msg_1)]),
        MagicMock(choices=[MagicMock(message=msg_2)]),
    ]

    with patch("backend.agent.agent.get_llm_client", return_value=mock_client), \
         patch("backend.agent.agent.os.getenv", return_value="fake_api_key"):
        result = run_agent(db_session, merchant_id=1, message="What did I collect today?")

    assert result["mode"] == "llm"
    assert len(result["tools_used"]) == 1
    assert result["tools_used"][0]["name"] == "get_daily_summary"
    assert "₹60.00" in result["answer"]


def test_agent_unknown_tool_from_model(db_session):
    """If the model attempts to call an unknown tool name, the loop handles it via error response."""
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_unknown"
    mock_tool_call.function.name = "hack_database"
    mock_tool_call.function.arguments = "{}"

    msg_1 = MagicMock()
    msg_1.tool_calls = [mock_tool_call]
    msg_1.content = None

    msg_2 = MagicMock()
    msg_2.tool_calls = None
    msg_2.content = "I could not perform that action as it is not supported."

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=msg_1)]),
        MagicMock(choices=[MagicMock(message=msg_2)]),
    ]

    with patch("backend.agent.agent.get_llm_client", return_value=mock_client), \
         patch("backend.agent.agent.os.getenv", return_value="fake_api_key"):
        result = run_agent(db_session, merchant_id=1, message="Run SQL query")

    assert result["mode"] == "llm"
    assert result["tools_used"][0]["name"] == "hack_database"


def test_agent_fallback_on_exception(db_session):
    """When LLM API raises an error (network, rate limit, timeout), fallback triggers seamlessly."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("Groq API rate limit or network timeout")

    with patch("backend.agent.agent.get_llm_client", return_value=mock_client), \
         patch("backend.agent.agent.os.getenv", return_value="fake_api_key"):
        result = run_agent(db_session, merchant_id=1, message="Why were my collections lower than yesterday?")

    assert result["mode"] == "rule-based"
    assert "This covers digital payments only." in result["answer"]
    assert any(t["name"] == "compare_periods" for t in result["tools_used"])


def test_agent_max_iterations(db_session):
    """Max iterations (4) are strictly respected if the model keeps calling tools in a loop."""
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_loop"
    mock_tool_call.function.name = "get_daily_summary"
    mock_tool_call.function.arguments = json.dumps({"date": "2026-10-25"})

    msg_loop = MagicMock()
    msg_loop.tool_calls = [mock_tool_call]
    msg_loop.content = None

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=msg_loop)])

    with patch("backend.agent.agent.get_llm_client", return_value=mock_client), \
         patch("backend.agent.agent.os.getenv", return_value="fake_api_key"):
        result = run_agent(db_session, merchant_id=1, message="Test loop")

    # The loop should terminate after max 4 iterations and return fallback safely
    assert mock_client.chat.completions.create.call_count == 4

