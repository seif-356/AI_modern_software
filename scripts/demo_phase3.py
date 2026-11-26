"""Replay the observed reviewer error and rerun its visible and held-out tests offline."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bugfix import load_bugs
from bugfix.sandbox import run_tests


def main():
    raw = ROOT / "results/raw/quixbugs_gemini-3.5-flash-lite.jsonl"
    row = next(
        r
        for r in map(json.loads, raw.read_text(encoding="utf-8").splitlines())
        if r["H5_reviewer_approved_wrong"]
    )
    (bug,) = load_bugs(ROOT / "data/quixbugs/bugs.jsonl", [row["bug_id"]])
    print(f"Archived {row['model']} | {row['bug_id']} | {row['system']} | run {row['run']}")
    print("\nFinal candidate\n" + row["final_code"])
    verdicts = [s["reply"] for s in row["trace"] if s["role"] == "reviewer"]
    print("Final reviewer response\n" + verdicts[-1])
    visible = run_tests(row["final_code"], bug.func_name, bug.visible_tests)
    held = run_tests(row["final_code"], bug.func_name, bug.heldout_tests)
    print(f"\nRe-executed visible tests: {visible.passed}/{visible.total}")
    print(f"Re-executed held-out tests: {held.passed}/{held.total}")
    for f in held.failures:
        print(f"  {f['input']} -> got {f['got']}, expected {f['expected']}")
    if not visible.all_passed or held.all_passed:
        raise SystemExit("The replay disagrees with the archived outcome.")


if __name__ == "__main__":
    main()
