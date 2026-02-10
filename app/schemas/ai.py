# app/schemas/ai.py
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


AIContext = Literal["client", "business", "operator"]


class AiAskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: AIContext = Field(..., description="client | business | operator")
    question: str = Field(..., min_length=2, max_length=2000)

    phone: Optional[str] = Field(default=None, min_length=5, max_length=32)


class AiRecoOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    target: str
    why: str
    suggested_bonus: int = 0
    expected_effect: str
    risk: str


class AiAskOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["openai", "gemini", "heuristic", "error"]
    context: AIContext

    answer: str
    insights: list[str]
    recommendations: list[AiRecoOut]

    payload: dict[str, Any] | None = None
    llm_error: str | None = None
