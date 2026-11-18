"""Build data/quixbugs/bugs.jsonl from a QuixBugs checkout.

    python scripts/prepare_quixbugs.py --src path/to/QuixBugs --out data/quixbugs

For every Python program with JSON test cases:
  1. keep only tests the reference (correct) program passes (cleans the data and
     validates our harness),
  2. drop the bug if the buggy program passes every remaining test (not exposed),
  3. split tests into visible / held-out, deterministically per bug (seeded):
     about half of the failing and half of the passing tests become visible,
     with at least one failing test visible and at least one test held out.
Programs without JSON tests (the graph programs that use node.py) are listed
as excluded in data/quixbugs/manifest.json.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bugfix.bugs import Bug  # noqa: E402
from bugfix.sandbox import run_tests  # noqa: E402


# Official QuixBugs tests compare sqrt with pytest.approx(abs=epsilon); all others exactly.
ABS_TOL_FROM_LAST_ARG = {"sqrt"}


def load_cases(path: Path, name: str) -> list[dict]:
    cases = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        inp, out = json.loads(line)
        inp = inp if isinstance(inp, list) else [inp]
        case = {"id": len(cases), "input": inp, "output": out}
        if name in ABS_TOL_FROM_LAST_ARG:
            case["abs_tol"] = inp[-1]
        cases.append(case)
    return cases


def source_commit(src: Path) -> str:
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def split(cases, failing_ids, rng):
    fail = [c for c in cases if c["id"] in failing_ids]
    ok = [c for c in cases if c["id"] not in failing_ids]
    rng.shuffle(fail)
    rng.shuffle(ok)
    n_fail_vis = max(1, math.ceil(len(fail) / 2))
    n_ok_vis = len(ok) // 2
    visible = fail[:n_fail_vis] + ok[:n_ok_vis]
    heldout = fail[n_fail_vis:] + ok[n_ok_vis:]
    if not heldout and len(visible) > 1:  # keep at least one held-out test
        heldout = [visible.pop()]
    renumber = lambda xs, start: [{**c, "id": start + i} for i, c in enumerate(xs)]  # noqa: E731
    visible = renumber(sorted(visible, key=lambda c: c["id"]), 0)
    return visible, renumber(sorted(heldout, key=lambda c: c["id"]), len(visible))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default="data/quixbugs")
    ap.add_argument("--seed", type=int, default=403)
    ap.add_argument("--timeout", type=float, default=3.0)
    args = ap.parse_args()
    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    bugs, excluded = [], {}
    for prog in sorted((src / "python_programs").glob("*.py")):
        name = prog.stem
        if name == "node" or name.endswith("_test"):
            continue
        tests_file, ref_file = src / "json_testcases" / f"{name}.json", src / "correct_python_programs" / f"{name}.py"
        if not tests_file.exists():
            excluded[name] = "no JSON test cases (graph program using node.py)"
            continue
        if not ref_file.exists():
            excluded[name] = "no reference program"
            continue
        buggy, ref = prog.read_text(), ref_file.read_text()
        cases = load_cases(tests_file, name)
        ref_run = run_tests(ref, name, cases, per_test_timeout=args.timeout)
        if ref_run.import_error:
            excluded[name] = f"reference does not load: {ref_run.import_error}"
            continue
        bad_ref = {f["id"] for f in ref_run.failures}
        valid = [c for c in cases if c["id"] not in bad_ref]
        notes = [f"dropped {len(bad_ref)} test(s) the reference program fails"] if bad_ref else []
        bug_run = run_tests(buggy, name, valid, per_test_timeout=args.timeout)
        failing = {c["id"] for c in valid} if bug_run.import_error else {f["id"] for f in bug_run.failures}
        if not failing:
            excluded[name] = "buggy program passes all valid tests (bug not exposed)"
            continue
        visible, heldout = split(valid, failing, random.Random(f"{args.seed}:{name}"))
        if not heldout:
            notes.append("no held-out tests: correctness = visible tests only")
        bugs.append(Bug(id=f"quixbugs/{name}", func_name=name, buggy_code=buggy, reference_code=ref,
                        visible_tests=visible, heldout_tests=heldout, source="quixbugs", notes=notes))
        print(f"{name:28s} tests={len(valid):3d} failing={len(failing):3d} "
              f"visible={len(visible):3d} heldout={len(heldout):3d} {'; '.join(notes)}")

    (out / "bugs.jsonl").write_text("".join(b.to_json() + "\n" for b in bugs))
    (out / "manifest.json").write_text(json.dumps(
        {"source": "QuixBugs (github.com/jkoppel/QuixBugs)", "commit": source_commit(src), "seed": args.seed, "n_bugs": len(bugs),
         "included": [b.func_name for b in bugs], "excluded": excluded}, indent=2))
    for extra in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        if (src / extra).exists():
            shutil.copy(src / extra, out / "QUIXBUGS_LICENSE")
    print(f"\n{len(bugs)} bugs written, {len(excluded)} excluded -> {out}")


if __name__ == "__main__":
    main()
