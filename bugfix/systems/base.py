"""Shared result type and helpers for all repair systems."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from ..bugs import Bug
from ..llm import Budget
from ..patching import extract_code
from ..sandbox import RunReport, run_tests

TRACE_TEXT_LIMIT = 2000


@dataclass
class RepairResult:
    system: str
    final_code: str
    passed_visible: bool
    stop_reason: str                       # "visible_pass", "approved", "budget", "single_shot"
    reviewer_approved: bool | None = None  # S2 only: verdict on the final patch
    trace: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


def code_hash(code: str) -> str:
    return hashlib.sha1(code.encode()).hexdigest()[:10]


def step(role: str, reply: str = "", code: str | None = None, report: RunReport | None = None, **extra) -> dict:
    entry = {"role": role, "reply": (reply or "")[:TRACE_TEXT_LIMIT]}
    if code is not None:
        entry["code_hash"] = code_hash(code)
    if report is not None:
        entry["visible_passed"] = report.passed
        entry["visible_total"] = report.total
        entry["load_error"] = report.import_error
    entry.update(extra)
    return entry


def initial_run(bug: Bug) -> RunReport:
    """Tool call (no LLM): run the buggy program on the visible tests."""
    return run_tests(bug.buggy_code, bug.func_name, bug.visible_tests, bug.support_files)


def test_patch(bug: Bug, reply: str) -> tuple[str, RunReport]:
    code = extract_code(reply)
    return code, run_tests(code, bug.func_name, bug.visible_tests, bug.support_files)


def new_budget(max_calls: int, max_output_tokens: int) -> Budget:
    return Budget(max_calls=max_calls, max_output_tokens=max_output_tokens)
