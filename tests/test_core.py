"""Plumbing tests. They use ScriptedLLM (canned replies), never a real model,
so they check the machinery, not repair ability."""
import pytest

from bugfix import Budget, BudgetExceeded, ScriptedLLM, evaluate, toy_bug
from bugfix.patching import extract_code
from bugfix.sandbox import run_tests
from bugfix.systems import run_s0, run_s1, run_s2, run_s2r

BUG = toy_bug()
FIX = "```python\n" + BUG.reference_code + "```"
WRONG = "```python\ndef find_max(xs):\n    return xs[0]\n```"
# Passes visible tests ([1,3,2] -> 3, [5] -> 5) but not held-out ones.
OVERFIT = "```python\ndef find_max(xs):\n    return 3 if len(xs) > 1 else xs[0]\n```"


def test_sandbox_buggy_and_reference():
    assert not run_tests(BUG.buggy_code, BUG.func_name, BUG.visible_tests).all_passed
    assert run_tests(BUG.reference_code, BUG.func_name, BUG.visible_tests + BUG.heldout_tests).all_passed


def test_sandbox_timeout_and_syntax_error():
    loop = "def find_max(xs):\n    while True:\n        pass\n"
    rep = run_tests(loop, "find_max", BUG.visible_tests, per_test_timeout=0.5)
    assert rep.passed == 0 and all(f["error"] == "Timeout" for f in rep.failures)
    bad = run_tests("def find_max(xs)\n    return 1\n", "find_max", BUG.visible_tests)
    assert bad.import_error and bad.import_error.startswith("SyntaxError")


def test_extract_code_takes_last_block():
    assert extract_code("x\n```python\na=1\n```\ny\n```python\nb=2\n```") == "b=2\n"


def test_budget_is_enforced():
    b = Budget(max_calls=1)
    llm = ScriptedLLM(["a", "b"])
    llm.chat([], b, "x")
    with pytest.raises(BudgetExceeded):
        llm.chat([], b, "x")


def test_s0_single_call():
    r = run_s0(BUG, ScriptedLLM([FIX]), Budget(max_calls=8))
    assert r.passed_visible and r.usage["calls"] == 1
    assert evaluate(BUG, r)["label"] == "correct"


def test_s1_retries_with_feedback_until_pass():
    llm = ScriptedLLM([WRONG, FIX])
    r = run_s1(BUG, llm, Budget(max_calls=8))
    assert r.passed_visible and r.usage["calls"] == 2
    assert "visible tests pass" in llm.seen[1][-1]["content"]


def test_s1_stops_at_budget():
    r = run_s1(BUG, ScriptedLLM([WRONG] * 10), Budget(max_calls=3))
    assert r.usage["calls"] == 3 and not r.passed_visible and r.stop_reason == "budget"


def test_s2_reviewer_rejects_overfit_then_fix_is_approved():
    llm = ScriptedLLM(["LINES: 4\nCAUSE: comparison reversed", OVERFIT, "REJECT: hard-codes 3",
                       FIX, "APPROVE: correct"])
    r = run_s2(BUG, llm, Budget(max_calls=8))
    assert r.stop_reason == "approved" and r.reviewer_approved is True
    assert [s["role"] for s in r.trace if not s["role"].startswith("tool")] == \
        ["localiser", "fixer", "reviewer", "fixer", "reviewer"]
    assert evaluate(BUG, r)["label"] == "correct"


def test_s2_approving_an_overfit_patch_is_flagged_h5():
    llm = ScriptedLLM(["LINES: 4\nCAUSE: x", OVERFIT, "APPROVE"])
    r = run_s2(BUG, llm, Budget(max_calls=8))
    ev = evaluate(BUG, r)
    assert ev["label"] == "plausible_incorrect" and ev["H5_reviewer_approved_wrong"]


def test_s2r_has_no_reviewer_and_shares_budget():
    r = run_s2r(BUG, ScriptedLLM(["LINES: 4", WRONG, WRONG, WRONG]), Budget(max_calls=3))
    assert r.usage["calls"] == 3 and r.stop_reason == "budget"
    assert not any(s["role"] == "reviewer" for s in r.trace)


def test_hallucination_flags():
    from bugfix.systems.base import RepairResult
    unchanged = evaluate(BUG, RepairResult("x", BUG.buggy_code, False, "budget"))
    assert unchanged["H4_unchanged"]
    fake_api = evaluate(BUG, RepairResult("x", "import numpyy\ndef find_max(xs):\n    return max(xs)\n", False, "b"))
    assert fake_api["H2_nonexistent_api"] and fake_api["H1_non_runnable"]
    sig = evaluate(BUG, RepairResult("x", "def find_max(xs, k=0):\n    return max(xs)\n", True, "b"))
    assert sig["H3_signature_changed"] and sig["label"] == "correct"
