"""Run repair systems on a dataset and append one JSON record per (bug, system, run).

    python scripts/run_experiment.py --systems s0 s1 s2 s2r --runs 3 \
        --max-calls 8 --max-tokens 8000 --out results/raw/quixbugs.jsonl

Resumable: (bug, system, run) triples already in --out are skipped.
Needs LLM_MODEL and an API key (see README). --dry-run checks everything
without calling a model.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bugfix import SYSTEMS, Budget, evaluate, load_bugs  # noqa: E402
from bugfix.llm import OpenAICompatibleLLM  # noqa: E402


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def done_keys(path: Path) -> set[tuple]:
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            keys.add((r["bug_id"], r["system"], r["run"]))
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/quixbugs/bugs.jsonl")
    ap.add_argument("--systems", nargs="+", default=list(SYSTEMS))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--max-calls", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=8000, help="output-token budget per bug")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--bugs", nargs="*")
    ap.add_argument("--out", default="results/raw/quixbugs.jsonl")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    bugs = load_bugs(args.data, ids=args.bugs, limit=args.limit)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    skip = done_keys(out)
    jobs = [(b, s, r) for r in range(args.runs) for b in bugs for s in args.systems if (b.id, s, r) not in skip]
    print(f"{len(bugs)} bugs x {len(args.systems)} systems x {args.runs} runs: {len(jobs)} to do, {len(skip)} done")
    if args.dry_run:
        return
    llm = OpenAICompatibleLLM(temperature=args.temperature)
    meta = {"model": llm.model, "temperature": args.temperature, "max_calls": args.max_calls,
            "max_output_tokens": args.max_tokens, "commit": git_commit()}
    lock = threading.Lock()

    def one(bug, system, run):
        budget = Budget(max_calls=args.max_calls, max_output_tokens=args.max_tokens)
        t0 = time.time()
        res = SYSTEMS[system](bug, llm, budget)
        rec = {"bug_id": bug.id, "system": system, "run": run, **meta,
               "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "wall_s": round(time.time() - t0, 2), "stop_reason": res.stop_reason,
               "passed_visible": res.passed_visible, "reviewer_approved": res.reviewer_approved,
               "usage": res.usage, **evaluate(bug, res), "final_code": res.final_code, "trace": res.trace}
        with lock, out.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(one, *j): j for j in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            bug, system, run = futures[fut]
            try:
                r = fut.result()
                print(f"[{i}/{len(jobs)}] {bug.id} {system} run{run}: {r['label']} "
                      f"({r['usage']['calls']} calls, {r['usage']['output_tokens']} out tok)")
            except Exception as err:  # keep going; the triple stays missing and is retried on resume
                print(f"[{i}/{len(jobs)}] {bug.id} {system} run{run}: ERROR {err}")


if __name__ == "__main__":
    main()
