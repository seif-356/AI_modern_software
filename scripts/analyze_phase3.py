"""Rebuild the evidence tables and blinded two-reader packet from the raw attempts."""

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

from analyze import exact_mcnemar, FLAGS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/phase3"
ARCHIVE = ROOT / "results/raw/quixbugs_gemini-3.5-flash-lite.jsonl"
PANEL = ROOT / "data/phase3/bugs.jsonl"


def records(path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]


def save(path, rows, fields=None):
    if fields is None:
        fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def pairs(group, left, right, **key):
    matched = [v for v in group.values() if left in v and right in v]
    a = sum(v[left] and not v[right] for v in matched)
    b = sum(v[right] and not v[left] for v in matched)
    return dict(
        **key,
        left=left,
        right=right,
        n_pairs=len(matched),
        left_only=a,
        right_only=b,
        delta_right_minus_left=round((b - a) / len(matched), 4) if matched else "",
        exact_p=round(exact_mcnemar(a, b), 6) if matched else "",
    )


def agree(packet, file_a, file_b):
    identifiers = {r["sample_id"] for r in packet}

    def read(file):
        rows = list(csv.DictReader(file.open(encoding="utf-8-sig")))
        scores = {r["sample_id"]: r["label"].strip() for r in rows}
        if (
            set(scores) != identifiers
            or len(rows) != len(scores)
            or any(s not in {"correct", "incorrect"} for s in scores.values())
        ):
            raise ValueError("Both raters must independently label every sample correct or incorrect.")
        return scores

    a, b = read(file_a), read(file_b)
    n = len(a)
    observed = sum(a[k] == b[k] for k in a) / n
    expected = sum(Counter(a.values())[x] * Counter(b.values())[x] / n**2 for x in ("correct", "incorrect"))
    return dict(
        n=n, agreement=observed, kappa=(observed - expected) / (1 - expected) if expected < 1 else None
    )


def mast_evidence(profile, record):
    """Conservative trace-level coding. A test failure alone does not assign a cause."""
    findings = {}
    if record["H5_reviewer_approved_wrong"]:
        findings["FM-3.3"] = "The final approval conflicts with a reserved test."
    failed_hashes = [
        step["code_hash"]
        for step in record["trace"]
        if step["role"] == "tool:tests" and step["visible_passed"] < step["visible_total"]
    ]
    if len(failed_hashes) != len(set(failed_hashes)):
        findings["FM-1.3"] = "An identical candidate was sent back to failing visible tests."
    if record["H3_signature_changed"]:
        findings["FM-1.1"] = "The final candidate violates the required entry-point signature."
    if profile == "archive-gemini" and record["bug_id"] == "quixbugs/wrap":
        findings["FC2"] = "The fix follows the localiser's whitespace diagnosis; see paper discussion."
    return dict(
        profile=profile,
        bug_id=record["bug_id"],
        run=record["run"],
        outcome=record["label"],
        codes=", ".join(findings) or "unresolved",
        evidence=" ".join(findings.values()) or "Available trace signals do not isolate a MAST mode.",
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ratings", type=Path, nargs=2, metavar=("RATER_A", "RATER_B"))
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    datasets = [ROOT / "data/quixbugs/bugs.jsonl", PANEL]
    breadth = ROOT / "data/condefects/bugs.jsonl"
    if breadth.exists():
        datasets.append(breadth)
    bugs = {r["id"]: r for path in datasets for r in records(path)}
    groups, systems, variants = (
        defaultdict(list),
        defaultdict(lambda: defaultdict(dict)),
        defaultdict(lambda: defaultdict(dict)),
    )
    sample_pool, inventory, seen, audit = [], [], set(), []
    reviewers = defaultdict(Counter)
    mast = []
    for path in [ARCHIVE, *sorted((OUT / "raw").glob("*.jsonl"))]:
        raw = records(path)
        profile = "archive-gemini" if path == ARCHIVE else path.stem
        expected = (
            372 if path == ARCHIVE else 4 * len(records(breadth if profile.endswith("-breadth") else PANEL))
        )
        inventory.append(
            dict(
                profile=profile,
                model=raw[0]["model"],
                attempts=len(raw),
                expected=expected,
                complete=len(raw) == expected,
                prompt_tokens=sum(r["usage"]["prompt_tokens"] for r in raw),
                output_tokens=sum(r["usage"]["output_tokens"] for r in raw),
            )
        )
        for r in raw:
            bug, system, run = r["bug_id"], r["system"], r["run"]
            usage = r["usage"]
            cap = min(r["max_output_tokens"], usage["calls"] * r.get("per_call_max_tokens", 1500))
            violation = (
                usage["output_tokens"] > cap
                or usage["calls"] > r["max_calls"]
                or usage.get("provider_limit_violations", 0) > 0
            )
            audit.append(
                dict(
                    profile=profile,
                    bug=bug,
                    system=system,
                    run=run,
                    calls=usage["calls"],
                    output_tokens=usage["output_tokens"],
                    max_for_completed_calls=cap,
                    known_violation=violation,
                    equal_budget_comparison=profile != "orca" and not violation,
                )
            )
            sid = json.dumps([profile, bug, system, run])
            if sid in seen:
                raise ValueError(f"Duplicate attempt {sid}")
            seen.add(sid)
            source = bug.split("/")[0]
            variant = "renamed" if bug.endswith("/renamed") else "original"
            groups[profile, source, variant, system].append(r)
            if system == "s2":
                if r["label"] != "correct":
                    mast.append(mast_evidence(profile, r))
                verdict = r["reviewer_approved"]
                if verdict is None or not r["passed_visible"]:
                    reviewers[profile]["unreviewed_final"] += 1
                else:
                    side = "approved" if verdict else "rejected"
                    outcome = "correct" if r["label"] == "correct" else "wrong"
                    reviewers[profile][f"{side}_{outcome}"] += 1
            ok = r["label"] == "correct"
            if profile != "orca" and not violation:
                systems[profile, source, variant][bug, run][system] = ok
                variants[profile, source, system][bug.removesuffix("/renamed"), run][variant] = ok
            if r["label"] in ("correct", "plausible_incorrect"):
                sample_pool.append((sid, r))
    save(OUT / "inventory.csv", inventory)
    save(OUT / "budget_audit.csv", audit)
    save(OUT / "mast_failures.csv", mast)
    categories = [
        "approved_correct",
        "approved_wrong",
        "rejected_correct",
        "rejected_wrong",
        "unreviewed_final",
    ]
    save(
        OUT / "reviewers.csv",
        [dict(profile=m, **{k: counts[k] for k in categories}) for m, counts in sorted(reviewers.items())],
    )
    summary = []
    for (profile, dataset, variant, system), rows in sorted(groups.items()):
        labels = Counter(r["label"] for r in rows)
        summary.append(
            dict(
                profile=profile,
                dataset=dataset,
                variant=variant,
                system=system,
                n=len(rows),
                correct=labels["correct"],
                plausible_incorrect=labels["plausible_incorrect"],
                failing=labels["failing"],
                mean_calls=round(sum(r["usage"]["calls"] for r in rows) / len(rows), 3),
                mean_output_tokens=round(sum(r["usage"]["output_tokens"] for r in rows) / len(rows), 2),
                **{f: sum(r[f] for r in rows) for f in FLAGS},
            )
        )
    save(OUT / "outcomes.csv", summary)
    system_rows = [
        pairs(group, a, b, profile=m, dataset=d, variant=v)
        for (m, d, v), group in sorted(systems.items())
        for a, b in [("s1", "s2"), ("s2", "s2r")]
    ]
    save(OUT / "system_pairs.csv", system_rows)
    probe = [
        pairs(group, "original", "renamed", profile=m, dataset=d, system=s)
        for (m, d, s), group in sorted(variants.items())
        if m != "archive-gemini" and not m.endswith("-breadth")
    ]
    save(
        OUT / "renaming_pairs.csv",
        probe,
        [
            "profile",
            "dataset",
            "system",
            "left",
            "right",
            "n_pairs",
            "left_only",
            "right_only",
            "delta_right_minus_left",
            "exact_p",
        ],
    )
    # Sorting makes selection independent of completion order. Keep code and reference, blind system and tests outcome.
    chosen = random.Random(403).sample(
        sorted(sample_pool, key=lambda pair: pair[0]), math.ceil(0.2 * len(sample_pool))
    )
    packet, key = [], []
    for sid, r in chosen:
        anonymous = hashlib.sha256(("sw403-review-" + sid).encode()).hexdigest()[:14]
        bug = bugs[r["bug_id"]]
        case_id = r["bug_id"].removesuffix("/renamed").split("/")
        task_url = (
            f"https://atcoder.jp/contests/{case_id[1].split('_')[0]}/tasks/{case_id[1]}?lang=en"
            if case_id[0] == "condefects"
            else f"https://github.com/jkoppel/QuixBugs/blob/4257f44/python_programs/{case_id[1]}.py"
        )
        packet.append(
            dict(
                sample_id=anonymous,
                specification=task_url,
                original=bug["buggy_code"],
                reference=bug["reference_code"],
                patch=r["final_code"],
                label="",
                rationale="",
            )
        )
        key.append(dict(sample_id=anonymous, attempt=json.loads(sid)))
    save(OUT / "review_packet.csv", packet)
    (OUT / "review_key.json").write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    print(
        f"{sum(r['attempts'] for r in inventory)} attempts; {len(packet)}/{len(sample_pool)} visible-passing attempts sampled."
    )
    if args.ratings:
        print(json.dumps(agree(packet, *args.ratings), indent=2))


if __name__ == "__main__":
    main()
