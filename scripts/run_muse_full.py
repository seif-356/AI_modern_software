"""Replay or collect one of four disjoint lanes of the full Muse browser study."""
import argparse
import hashlib
import json
import tempfile
import threading
from pathlib import Path

from filelock import FileLock

from run_muse_web import DATA, OUT, ROOT, FormModel, append, serve
from bugfix import SYSTEMS, Budget, evaluate, load_bugs
from bugfix.systems.base import RepairResult

FULL = ROOT / "results/phase3/muse-web-full"
COHORTS = ("quixbugs", "condefects")
MODES = ("s0", "s1", "s2", "s2r")


class FullPanelModel(FormModel):
    def same_prompt(self, stored, current):
        if stored == current:
            return True
        # This faulty submission prints a Python set. Each isolated test process
        # can display its two members in either order in the failure feedback.
        if self.bug != "condefects/abc283_d/45462979":
            return False
        def normalize(prompt):
            return "\n".join(
                line.replace("{'b', 'a'}", "{'a', 'b'}") if line.startswith("- input ") and ", returned " in line else line
                for line in prompt.split("\n")
            )
        return normalize(stored) == normalize(current)


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def fingerprint(bug):
    # All fields, including support files and both test partitions, enter the identity.
    return hashlib.sha256(json.dumps(vars(bug), sort_keys=True).encode()).hexdigest()


def run_lane(lane, collecting, port):
    FULL.mkdir(exist_ok=True)
    path = FULL / f"lane-{lane}-scores.jsonl"
    calls = FULL / f"lane-{lane}-calls.jsonl"
    model = FullPanelModel(not collecting, calls)
    prior = {(r["bug_id"], r["system"]): r for r in jsonl(OUT / "muse-web-panel.jsonl")}
    panel = {b.id: fingerprint(b) for b in load_bugs(DATA)}
    records = jsonl(path) if path.exists() else []
    saved = {(r["bug_id"], r["system"]): r for r in records}
    if len(records) != len(saved):
        raise ValueError(f"Duplicate workflow score in {path.name}")
    if collecting:
        server = serve(model, port)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    seen = set()
    for cohort in COHORTS:
        subjects = load_bugs(ROOT / "data" / cohort / "bugs.jsonl")
        for index, bug in enumerate(subjects):
            same = panel.get(bug.id) == fingerprint(bug)
            if index % 4 != lane:
                continue
            for system in MODES:
                key = bug.id, system
                seen.add(key)
                old = prior.get(key) if same else None
                if collecting and key in saved:
                    if saved[key]["input_sha256"] != fingerprint(bug):
                        raise ValueError(f"Input changed for {key}")
                    if not old:
                        for call in range(1, saved[key]["browser_submissions"] + 1):
                            call_id = f"{bug.id}/{system}/{call}"
                            if call_id not in model.saved:
                                raise ValueError(f"Missing stored reply for {call_id}")
                            model.used.add(call_id)
                    continue
                if old:
                    result = RepairResult(system, old["final_code"], old["visible_passed"] == old["visible_total"],
                                          old["stop_reason"], old["reviewer_approved"])
                    submissions = old["browser_submissions"]
                else:
                    model.bug, model.system = key
                    budget = Budget(max_calls=4)
                    result = SYSTEMS[system](bug, model, budget)
                    submissions = budget.calls
                score = dict(cohort=cohort, bug_id=bug.id, system=system, input_sha256=fingerprint(bug),
                             reused_matched_panel=bool(old), browser_submissions=submissions,
                             stop_reason=result.stop_reason, reviewer_approved=result.reviewer_approved,
                             final_code=result.final_code, **evaluate(bug, result))
                if key in saved:
                    if saved[key] != score:
                        changes = {k for k in score if saved[key][k] != score[k]}
                        timing_fields = {"label", "heldout_passed", "error_types",
                                         "H5_reviewer_approved_wrong", "any_hallucination"}
                        known_timeout = (bug.id == "quixbugs/levenshtein"
                                         and saved[key]["error_types"] == ["Timeout"]
                                         and score["error_types"] == []
                                         and score["heldout_passed"] == score["heldout_total"]
                                         and score["label"] == "correct")
                        if not (known_timeout and changes <= timing_fields):
                            raise ValueError(f"Replay disagrees with stored score: {key}, {sorted(changes)}")
                        print(f"Held-out timeout variation {key}: {saved[key]['heldout_passed']} stored, "
                              f"{score['heldout_passed']} replayed", flush=True)
                elif collecting:
                    append(path, score)
                else:
                    raise ValueError(f"Missing score: {key}")
                print(cohort, bug.id, system, score["label"], flush=True)
    if not set(saved) <= seen or set(model.saved) != model.used:
        raise ValueError("Unexpected scores or replies outside the lane")
    model.done = True
    if collecting:
        print("Collection complete", flush=True)
        server.shutdown()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lane", type=int, choices=range(4), required=True)
    ap.add_argument("--collect", action="store_true")
    args = ap.parse_args()
    lock_id = hashlib.sha256(str(FULL).encode()).hexdigest()[:16]
    with FileLock(Path(tempfile.gettempdir()) / f"sw403-{lock_id}-{args.lane}.lock", timeout=0):
        run_lane(args.lane, args.collect, 18220 + args.lane)
