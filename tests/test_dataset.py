"""Checks on the prepared QuixBugs data: every reference fix is labelled correct,
every buggy program fails, and every bug has visible and held-out tests."""
from pathlib import Path

import pytest

from bugfix import evaluate, load_bugs
from bugfix.systems.base import RepairResult

DATA = Path(__file__).resolve().parents[1] / "data" / "quixbugs" / "bugs.jsonl"
BUGS = load_bugs(DATA) if DATA.exists() else []


@pytest.mark.skipif(not BUGS, reason="run scripts/prepare_quixbugs.py first")
@pytest.mark.parametrize("bug", BUGS, ids=[b.func_name for b in BUGS])
def test_reference_correct_and_buggy_fails(bug):
    assert bug.visible_tests and bug.heldout_tests
    assert evaluate(bug, RepairResult("ref", bug.reference_code, True, "x"))["label"] == "correct"
    assert evaluate(bug, RepairResult("buggy", bug.buggy_code, False, "x"))["label"] == "failing"
