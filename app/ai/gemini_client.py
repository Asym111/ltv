# app/ai/gemini_client.py
from __future__ import annotations

from typing import Any
import json
import re
import httpx

from app.core.config import settings


class GeminiError(RuntimeError):
    pass


def _get_api_key() -> str:
    key = getattr(settings, "GEMINI_API_KEY", None)
    return (key or "").strip()


def _get_model() -> str:
    m = getattr(settings, "GEMINI_MODEL", None)
    return (m or "gemini-2.5-flash").strip()


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_text(text: str) -> str:
    t = (text or "").strip()

    m = _JSON_FENCE_RE.search(t)
    if m:
        return m.group(1).strip()

    first = t.find("{")
    last = t.rfind("}")
    if first != -1 and last != -1 and last > first:
        return t[first:last + 1].strip()

    return t


async def gemini_generate_json(system_prompt: str, user_prompt: str, timeout_s: int = 30) -> dict[str, Any]:
    api_key = _get_api_key()
    if not api_key:
        raise GeminiError("GEMINI_API_KEY is not set")

    model = _get_model()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}],
            }
        ],
        "generationConfig": {
            "temperature": 0.25,
            "maxOutputTokens": 900,
        },
    }

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        r = await client.post(url, json=body)
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            msg = (data.get("error", {}) or {}).get("message")
            raise GeminiError(msg or f"{r.status_code} Gemini error")

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        raise GeminiError(f"Unexpected Gemini response shape: {e}")

    json_text = _extract_json_text(text)

    try:
        obj = json.loads(json_text)
    except Exception as e:
        raise GeminiError(f"Gemini returned non-JSON: {e}")

    if not isinstance(obj, dict):
        raise GeminiError("Gemini JSON root must be an object")

    return obj
