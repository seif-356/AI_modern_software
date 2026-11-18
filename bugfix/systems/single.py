"""S0 (single-shot) and S1 (single agent with test feedback)."""
from __future__ import annotations

from ..bugs import Bug
from ..llm import LLM, Budget, BudgetExceeded
from .. import prompts
from .base import RepairResult, initial_run, step, test_patch


def run_s0(bug: Bug, llm: LLM, budget: Budget) -> RepairResult:
    initial = initial_run(bug)
    trace = [step("tool:initial_tests", report=initial)]
    messages = [{"role": "system", "content": prompts.REPAIR_SYSTEM},
                {"role": "user", "content": prompts.repair_user(bug, initial)}]
    try:
        reply = llm.chat(messages, budget, role="repair")
    except BudgetExceeded:
        return RepairResult("s0", bug.buggy_code, False, "budget", trace=trace, usage=budget.usage())
    code, report = test_patch(bug, reply)
    trace += [step("repair", reply, code), step("tool:tests", code=code, report=report)]
    return RepairResult("s0", code, report.all_passed, "single_shot", trace=trace, usage=budget.usage())


def run_s1(bug: Bug, llm: LLM, budget: Budget) -> RepairResult:
    """One agent, one growing conversation: patch -> run visible tests -> feedback -> patch ..."""
    initial = initial_run(bug)
    trace = [step("tool:initial_tests", report=initial)]
    messages = [{"role": "system", "content": prompts.REPAIR_SYSTEM},
                {"role": "user", "content": prompts.repair_user(bug, initial)}]
    best_code, best_pass = bug.buggy_code, False
    while True:
        try:
            reply = llm.chat(messages, budget, role="repair")
        except BudgetExceeded:
            return RepairResult("s1", best_code, best_pass, "budget", trace=trace, usage=budget.usage())
        code, report = test_patch(bug, reply)
        trace += [step("repair", reply, code), step("tool:tests", code=code, report=report)]
        if report.all_passed:
            return RepairResult("s1", code, True, "visible_pass", trace=trace, usage=budget.usage())
        best_code = code
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": prompts.retry_user(report)}]
