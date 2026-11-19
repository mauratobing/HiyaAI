"""Care: FastAPI backend + static front end.

Run:  uvicorn app.main:app --reload
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import customer
from .analyzer import analyze_call, build_recap

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
SCENARIOS = json.loads((Path(__file__).parent / "scenarios.json").read_text())

app = FastAPI(title="Care", docs_url=None, redoc_url=None)


class Turn(BaseModel):
    speaker: Literal["agent", "customer"] = "agent"
    text: str = Field(max_length=2000)
    duration_ms: Optional[int] = Field(default=None, ge=0, le=120_000)


class CallBody(BaseModel):
    turns: list[Turn] = Field(max_length=200)

    def as_dicts(self) -> list[dict]:
        return [t.model_dump() for t in self.turns]


@app.get("/api/personas")
def personas():
    return customer.list_personas()


class ReplyBody(CallBody):
    persona: str


@app.post("/api/customer_reply")
def customer_reply(body: ReplyBody):
    if body.persona not in customer.PERSONAS:
        raise HTTPException(status_code=404, detail="unknown persona")
    return customer.reply(body.persona, body.as_dicts())


@app.get("/api/scenarios")
def scenarios():
    return SCENARIOS


@app.post("/api/analyze")
def analyze(body: CallBody):
    return analyze_call(body.as_dicts())


@app.post("/api/recap")
def recap(body: CallBody):
    return build_recap(body.as_dicts())


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")
