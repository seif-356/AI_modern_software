"""Prompt templates. All systems receive the same information about a bug:
the buggy function and the visible tests with the buggy program's results on them."""
from __future__ import annotations

import json

from .bugs import Bug
from .sandbox import RunReport

CODE_RULES = (
    "Return the complete corrected program in a single ```python code block. "
    "Keep the function name and signature unchanged. Do not add tests or example usage."
)


def numbered(code: str) -> str:
    return "\n".join(f"{i:>3}| {line}" for i, line in enumerate(code.splitlines(), 1))


def tests_block(bug: Bug) -> str:
    return "\n".join(f"- {bug.func_name}(*{json.dumps(t['input'])}) should return {json.dumps(t['output'])}"
                     for t in bug.visible_tests)


def bug_context(bug: Bug, initial: RunReport) -> str:
    return (
        f"The Python function `{bug.func_name}` below contains a bug.\n\n"
        f"```python\n{bug.buggy_code}```\n\n"
        f"Visible tests:\n{tests_block(bug)}\n\n"
        f"Result of running the buggy program on the visible tests:\n{initial.feedback()}\n"
    )


# --- S0 / S1 ---------------------------------------------------------------
REPAIR_SYSTEM = "You are an expert Python developer who fixes bugs. " + CODE_RULES


def repair_user(bug: Bug, initial: RunReport) -> str:
    return bug_context(bug, initial) + "\nFix the bug. " + CODE_RULES


def retry_user(report: RunReport) -> str:
    return ("Your program was run on the visible tests.\n" + report.feedback() +
            "\n\nFix the remaining problem. " + CODE_RULES)


# --- S2 agents ---------------------------------------------------------------
LOCALISER_SYSTEM = (
    "You are a fault-localisation agent. You do not write code. Identify the line(s) most likely "
    "responsible for the failures and explain the root cause in at most three sentences. "
    "Answer in the form:\nLINES: <comma-separated line numbers>\nCAUSE: <explanation>"
)


def localiser_user(bug: Bug, initial: RunReport) -> str:
    return (f"The function `{bug.func_name}` is buggy. Numbered source:\n\n{numbered(bug.buggy_code)}\n\n"
            f"Visible tests:\n{tests_block(bug)}\n\nResults on the buggy program:\n{initial.feedback()}\n")


FIXER_SYSTEM = "You are a repair agent. You receive a fault localisation and must write the fix. " + CODE_RULES


def fixer_user(bug: Bug, initial: RunReport, localisation: str, history: list[str]) -> str:
    text = bug_context(bug, initial) + f"\nFault localisation from a colleague:\n{localisation}\n"
    if history:
        text += "\nFeedback on your previous attempts (most recent last):\n" + "\n\n".join(history) + "\n"
    return text + "\nWrite the fix. " + CODE_RULES


REVIEWER_SYSTEM = (
    "You are a code-review agent. A patch already passes the visible tests. Decide whether it fixes "
    "the root cause for ALL valid inputs, or only special-cases the visible tests or introduces new "
    "problems. Reply with exactly one first line: APPROVE or REJECT. Then give at most three sentences of reasons."
)


def reviewer_user(bug: Bug, patch: str, localisation: str) -> str:
    return (f"Original buggy function:\n```python\n{bug.buggy_code}```\n\n"
            f"Proposed patch:\n```python\n{patch}```\n\n"
            f"Fault localisation: {localisation}\n\nVisible tests (all pass with the patch):\n{tests_block(bug)}\n")


def reviewer_approves(reply: str) -> bool:
    first = (reply or "").strip().splitlines()[0].upper() if (reply or "").strip() else ""
    return first.startswith("APPROVE")
