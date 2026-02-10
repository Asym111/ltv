# app/ai/openai_client.py
from __future__ import annotations

from typing import Any
import json
import re

import httpx
from openai import AsyncOpenAI


class OpenAIError(RuntimeError):
    pass


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_text(text: str) -> str:
    t = (text or "").strip()

    # 1) ```json { ... } ```
    m = _JSON_FENCE_RE.search(t)
    if m:
        return m.group(1).strip()

    # 2) вырежем первый {...} блок
    first = t.find("{")
    last = t.rfind("}")
    if first != -1 and last != -1 and last > first:
        return t[first:last + 1].strip()

    return t


def _schema() -> dict[str, Any]:
    # строгая форма под app.schemas.ai.AiAskOut
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "insights": {
                "type": "array",
                "items": {"type": "string"},
            },
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "action": {"type": "string"},
                        "target": {"type": "string"},
                        "why": {"type": "string"},
                        "suggested_bonus": {"type": "integer"},
                        "expected_effect": {"type": "string"},
                        "risk": {"type": "string"},
                    },
                    "required": [
                        "action",
                        "target",
                        "why",
                        "suggested_bonus",
                        "expected_effect",
                        "risk",
                    ],
                },
            },
        },
        "required": ["answer", "insights", "recommendations"],
    }


async def openai_generate_json(
    system_prompt: str,
    user_prompt: str,
    *,
    api_key: str | None,
    model: str | None,
    timeout_s: int = 30,
) -> dict[str, Any]:
    key = (api_key or "").strip()
    if not key:
        raise OpenAIError("OPENAI_API_KEY is missing")

    m = (model or "").strip() or "gpt-4o-mini"

    client = AsyncOpenAI(
        api_key=key,
        timeout=httpx.Timeout(timeout_s),
    )

    # Responses API + JSON Schema (строгое структурирование)
    # см. official docs: responses.create + text.format json_schema :contentReference[oaicite:1]{index=1}
    try:
        resp = await client.responses.create(
            model=m,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ltv_ai_response",
                    "schema": _schema(),
                    "strict": True,
                }
            },
            temperature=0.25,
            max_output_tokens=900,
        )
    except Exception as e:
        raise OpenAIError(str(e))

    text = (getattr(resp, "output_text", None) or "").strip()
    if not text:
        raise OpenAIError("OpenAI returned empty output_text")

    # Обычно тут уже чистый JSON, но оставим защиту
    json_text = _extract_json_text(text)
    try:
        obj = json.loads(json_text)
    except Exception as e:
        raise OpenAIError(f"OpenAI returned non-JSON: {e}")

    if not isinstance(obj, dict):
        raise OpenAIError("OpenAI JSON root must be an object")

    return obj
