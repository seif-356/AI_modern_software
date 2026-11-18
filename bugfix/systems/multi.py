"""S2: LangGraph multi-agent pipeline  Localiser -> Fixer -> Test-runner (tool) -> Reviewer.
S2-R: the same graph without the Reviewer (ablation for RQ2).

Every LLM node charges the same per-bug Budget as S0/S1, so S2 cannot win by
simply making more calls (RQ1).
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from ..bugs import Bug
from ..llm import LLM, Budget, BudgetExceeded
from .. import prompts
from ..sandbox import RunReport
from .base import RepairResult, initial_run, step, test_patch


class State(TypedDict, total=False):
    initial: RunReport
    localisation: str
    history: list[str]          # feedback strings shown to the Fixer
    code: str                   # latest patch
    report: RunReport           # latest visible-test report
    best_code: str              # latest patch that passed visible tests (if any)
    approved: bool | None
    best_verdict: bool | None   # reviewer verdict on best_code (None = not reviewed)
    stop: str                   # stop reason once set
    trace: list[dict]


def build_graph(bug: Bug, llm: LLM, budget: Budget, with_reviewer: bool):
    def localise(s: State) -> State:
        msgs = [{"role": "system", "content": prompts.LOCALISER_SYSTEM},
                {"role": "user", "content": prompts.localiser_user(bug, s["initial"])}]
        try:
            reply = llm.chat(msgs, budget, role="localiser")
        except BudgetExceeded:
            return {"stop": "budget"}
        return {"localisation": reply.strip(), "trace": s["trace"] + [step("localiser", reply)]}

    def fix(s: State) -> State:
        msgs = [{"role": "system", "content": prompts.FIXER_SYSTEM},
                {"role": "user", "content": prompts.fixer_user(bug, s["initial"], s.get("localisation", ""),
                                                                s.get("history", []))}]
        try:
            reply = llm.chat(msgs, budget, role="fixer")
        except BudgetExceeded:
            return {"stop": "budget"}
        code, report = test_patch(bug, reply)
        update: State = {"code": code, "report": report,
                         "trace": s["trace"] + [step("fixer", reply, code),
                                                step("tool:tests", code=code, report=report)]}
        if report.all_passed:
            update["best_code"] = code
            update["best_verdict"] = None
        else:
            update["history"] = s.get("history", []) + [f"Test results:\n{report.feedback()}"]
        return update

    def review(s: State) -> State:
        msgs = [{"role": "system", "content": prompts.REVIEWER_SYSTEM},
                {"role": "user", "content": prompts.reviewer_user(bug, s["code"], s.get("localisation", ""))}]
        try:
            reply = llm.chat(msgs, budget, role="reviewer")
        except BudgetExceeded:
            return {"stop": "budget", "approved": None}
        ok = prompts.reviewer_approves(reply)
        update: State = {"approved": ok, "best_verdict": ok, "trace": s["trace"] + [step("reviewer", reply, approved=ok)]}
        if ok:
            update["stop"] = "approved"
        else:
            update["history"] = s.get("history", []) + [f"A reviewer rejected a patch that passed the "
                                                        f"visible tests:\n{reply.strip()}"]
        return update

    def after_fix(s: State) -> str:
        if s.get("stop"):
            return END
        if s["report"].all_passed:
            return "review" if with_reviewer else "done"
        return "fix"

    def mark_done(s: State) -> State:
        return {"stop": "visible_pass"}

    g = StateGraph(State)
    g.add_node("localise", localise)
    g.add_node("fix", fix)
    g.add_node("done", mark_done)
    g.set_entry_point("localise")
    g.add_conditional_edges("localise", lambda s: END if s.get("stop") else "fix", {END: END, "fix": "fix"})
    targets = {END: END, "fix": "fix", "done": "done"}
    if with_reviewer:
        g.add_node("review", review)
        targets["review"] = "review"
        g.add_conditional_edges("review", lambda s: END if s.get("stop") else "fix", {END: END, "fix": "fix"})
    g.add_conditional_edges("fix", after_fix, targets)
    g.add_edge("done", END)
    return g.compile()


def run_s2(bug: Bug, llm: LLM, budget: Budget, with_reviewer: bool = True) -> RepairResult:
    name = "s2" if with_reviewer else "s2r"
    initial = initial_run(bug)
    graph = build_graph(bug, llm, budget, with_reviewer)
    state = graph.invoke({"initial": initial, "history": [], "approved": None,
                          "trace": [step("tool:initial_tests", report=initial)]},
                         {"recursion_limit": 4 * budget.max_calls + 10})
    best = state.get("best_code")
    final = best or state.get("code") or bug.buggy_code
    approved = state.get("best_verdict") if (with_reviewer and best) else None
    return RepairResult(name, final, best is not None, state.get("stop", "budget"),
                        reviewer_approved=approved, trace=state["trace"], usage=budget.usage())


def run_s2r(bug: Bug, llm: LLM, budget: Budget) -> RepairResult:
    return run_s2(bug, llm, budget, with_reviewer=False)
