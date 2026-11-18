"""Optional AI second opinion.

The rule engine in analyzer.py is instant and offline. When ANTHROPIC_API_KEY is
set, the browser also asks for a second opinion from Claude on subtler things
the rules can't see (implied pressure, emotional manipulation, confusing
authority claims). It runs asynchronously, so it never slows the live nudges.

Privacy: with a key set, the transcript text (never audio) is sent to the API.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

SYSTEM = """You review a live business phone call transcript from the point of view of a customer who is wary of scams.
Find only SUBTLE trust problems that simple keyword rules would miss: implied pressure, emotional manipulation,
vague or inflated authority, evasive answers, talking over the customer, or confusing jargon.
Do not repeat obvious things like asking for a PIN or gift cards.
Reply with JSON only, in this shape:
{"concerns": [{"label": "short title", "severity": "low|medium|high", "quote": "short quote from the agent",
"why": "one sentence", "say": "a calmer way the agent could say it"}]}
Return at most 3 concerns, or {"concerns": []} if the call sounds fine."""


def available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def parse_concerns(raw: str) -> list[dict[str, Any]]:
    """Pull the JSON object out of a model reply and keep only well-formed concerns."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    for c in data.get("concerns", [])[:3]:
        if not isinstance(c, dict) or not c.get("label"):
            continue
        sev = c.get("severity") if c.get("severity") in ("low", "medium", "high") else "low"
        out.append({
            "label": str(c["label"])[:80],
            "severity": sev,
            "quote": str(c.get("quote", ""))[:200],
            "why": str(c.get("why", ""))[:240],
            "say": str(c.get("say", ""))[:300],
        })
    return out


def second_opinion(turns: list[dict]) -> list[dict[str, Any]]:
    if not available():
        return []
    import anthropic  # imported lazily so the app runs without the package

    transcript = "\n".join(
        f"{'AGENT' if t.get('speaker', 'agent') == 'agent' else 'CUSTOMER'}: {t['text']}"
        for t in turns[-12:] if (t.get("text") or "").strip()
    )
    client = anthropic.Anthropic(timeout=10.0, max_retries=0)
    msg = client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=SYSTEM,
        messages=[{"role": "user", "content": transcript}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return parse_concerns(raw)
