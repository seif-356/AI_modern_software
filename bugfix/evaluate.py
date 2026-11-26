"""Automatic output checker (course 'Evaluation Module').

Labels each final patch against visible AND held-out tests, which the systems
never see, and flags hallucination types H1-H5 from the proposal.
"""
from __future__ import annotations

import sys

from .bugs import Bug
from .patching import defined_functions, imported_modules, normalise, parses
from .sandbox import run_tests
from .systems.base import RepairResult

API_ERRORS = {"NameError", "AttributeError", "ImportError", "ModuleNotFoundError"}
STDLIB = set(getattr(sys, "stdlib_module_names", ()))


def evaluate(bug: Bug, result: RepairResult, *, per_test_timeout: float = 2.0) -> dict:
    code = result.final_code
    vis = run_tests(code, bug.func_name, bug.visible_tests, bug.support_files, per_test_timeout)
    held = run_tests(code, bug.func_name, bug.heldout_tests, bug.support_files, per_test_timeout)

    held_ok = held.all_passed if bug.heldout_tests else vis.all_passed
    if vis.all_passed and held_ok:
        label = "correct"
    elif vis.all_passed:
        label = "plausible_incorrect"
    else:
        label = "failing"

    funcs = defined_functions(code)
    original = defined_functions(bug.buggy_code)
    errors = vis.error_types() | held.error_types()
    third_party = sorted(m for m in imported_modules(code) - imported_modules(bug.buggy_code)
                         if m not in STDLIB and m not in {n.removesuffix(".py") for n in bug.support_files})
    flags = {
        "H1_non_runnable": (not parses(code)) or bool(vis.import_error),
        "H2_nonexistent_api": bool(errors & API_ERRORS) or bool(third_party),
        "H3_signature_changed": funcs.get(bug.func_name) != original.get(bug.func_name),
        "H4_unchanged": normalise(code) == normalise(bug.buggy_code),
        "H5_reviewer_approved_wrong": result.reviewer_approved is True and label != "correct",
    }
    return {
        "label": label,
        "visible_passed": vis.passed, "visible_total": vis.total,
        "heldout_passed": held.passed, "heldout_total": held.total,
        "error_types": sorted(errors),
        "third_party_imports": third_party,
        **flags,
        "any_hallucination": any(flags.values()),
    }
