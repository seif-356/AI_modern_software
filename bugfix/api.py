"""FastAPI service (course 'AI Service Wrapping').

    uvicorn bugfix.api:app --reload

POST /repair   {code, function_name, visible_tests, heldout_tests?, mode, max_calls, max_output_tokens}
             -> {patch, label, passed_visible, reviewer_approved, stop_reason, usage, evaluation, trace}
GET  /health
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .bugs import Bug
from .evaluate import evaluate
from .llm import Budget, OpenAICompatibleLLM
from .systems import SYSTEMS

app = FastAPI(title="Multi-Agent Bug Fixing", version="0.2.0")
_llm = None


def get_llm():
    """Lazily create the model client (tests replace this)."""
    global _llm
    if _llm is None:
        _llm = OpenAICompatibleLLM()
    return _llm


class TestCase(BaseModel):
    input: list[Any] = Field(description="positional arguments")
    output: Any


class RepairRequest(BaseModel):
    code: str
    function_name: str
    visible_tests: list[TestCase] = Field(min_length=1)
    heldout_tests: list[TestCase] = []
    mode: Literal["s0", "s1", "s2", "s2r"] = "s2"
    max_calls: int = Field(8, ge=1, le=30)
    max_output_tokens: int = Field(8000, ge=100, le=50000)


@app.get("/health")
def health():
    return {"status": "ok", "systems": list(SYSTEMS)}


@app.post("/repair")
def repair(req: RepairRequest):
    vis = [{"id": i, **t.model_dump()} for i, t in enumerate(req.visible_tests)]
    held = [{"id": len(vis) + i, **t.model_dump()} for i, t in enumerate(req.heldout_tests)]
    bug = Bug(id="api", func_name=req.function_name, buggy_code=req.code, reference_code="",
              visible_tests=vis, heldout_tests=held, source="api")
    try:
        llm = get_llm()
    except ValueError as err:
        raise HTTPException(status_code=503, detail=str(err))
    budget = Budget(max_calls=req.max_calls, max_output_tokens=req.max_output_tokens)
    res = SYSTEMS[req.mode](bug, llm, budget)
    ev = evaluate(bug, res)
    return {"patch": res.final_code, "label": ev["label"], "passed_visible": res.passed_visible,
            "reviewer_approved": res.reviewer_approved, "stop_reason": res.stop_reason,
            "usage": res.usage, "evaluation": ev, "trace": res.trace}
