"""Agent API endpoint for merchant conversational partner."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import Merchant
from backend.agent import run_agent

router = APIRouter(prefix="/api", tags=["agent"])


class AgentRequest(BaseModel):
    message: str = Field(..., description="User message or question for the business assistant")


class ToolUsed(BaseModel):
    name: str
    args: dict


class AgentResponse(BaseModel):
    answer: str
    tools_used: list[ToolUsed]
    mode: str  # "llm" or "rule-based"


@router.post("/agent", response_model=AgentResponse)
def handle_agent_message(
    body: AgentRequest,
    merchant_id: int = Query(..., description="ID of the merchant (stands in for auth)"),
    db: Session = Depends(get_db),
):
    """Processes natural language questions from merchants using tool calling.
    Falls back to deterministic rule-based mode when LLM is unavailable or unconfigured.
    """
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    result = run_agent(db=db, merchant_id=merchant_id, message=body.message)
    return result

