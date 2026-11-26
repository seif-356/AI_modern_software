"""Audit Phase 3 model coverage for the 31 original QuixBugs and 100 ConDefects inputs."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from run_phase3 import COHORT_DATA, PROFILES, ROOT

FULL = ROOT / "results/phase3/full-models"
RAW = ROOT / "results/phase3/raw"
MODES = ("s0", "s1", "s2", "s2r")
PROFILES_TO_REPORT = ("openai", "qwen", "smollm2", "deepseek-coder", "orca", "archive-gemini",
                      "muse-web", "muse", "deepseek")


def records(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def audit(missing_file=None):
    panel = {b["id"]: b for b in records(COHORT_DATA["panel"])}
    summary, missing = [], []
    for dataset, size in (("quixbugs", 31), ("condefects", 100)):
        data = COHORT_DATA["full-" + dataset]
        subjects = {b["id"]: b for b in records(data)}
        if len(subjects) != size:
            raise ValueError(f"Unexpected size for {dataset}")
        lf = data.read_bytes().replace(b"\r\n", b"\n")
        hashes = {hashlib.sha256(b).hexdigest() for b in (lf, lf.replace(b"\n", b"\r\n"))}
        target = {(bug, mode) for bug in subjects for mode in MODES}
        for profile in PROFILES_TO_REPORT:
            files = [(RAW / (profile + ".jsonl"), "panel"),
                     (FULL / f"{profile}-full-{dataset}.jsonl", "extension")]
            if dataset == "condefects":
                files.append((RAW / (profile + "-breadth.jsonl"), "breadth"))
            if profile == "archive-gemini" and dataset == "quixbugs":
                files.append((ROOT / "results/raw/quixbugs_gemini-3.5-flash-lite.jsonl", "archive"))
            if profile == "muse-web":
                files = [(p, "browser") for p in sorted((FULL.parent / "muse-web-full").glob("*-scores.jsonl"))]
            cells, new_rows = {}, []
            for path, source in files:
                if not path.exists():
                    continue
                for row in records(path):
                    bug, mode = row["bug_id"], row["system"]
                    if source == "panel" and (bug not in subjects or panel.get(bug) != subjects[bug]):
                        continue
                    if source == "browser" and row["cohort"] != dataset:
                        continue
                    if source == "archive" and row["run"] != 0:
                        continue  # Coverage and pass counts use one prespecified repeat per cell.
                    key = bug, mode
                    if key not in target or key in cells:
                        raise ValueError(f"Invalid or duplicate cell: {path.name}, {key}")
                    if source == "extension":
                        if row["data_sha256"] not in hashes or row["model"] != PROFILES[profile][0]:
                            raise ValueError(f"Input/model mismatch in {path.name}")
                        new_rows.append(row)
                    cells[key] = row
            for bug, mode in sorted(target - cells.keys()):
                missing.append(dict(profile=profile, dataset=dataset, bug_id=bug, system=mode))
            correct = Counter(mode for (_, mode), r in cells.items() if r["label"] == "correct")
            summary.append(dict(profile=profile, dataset=dataset, planned=len(target), completed=len(cells),
                                missing=len(target)-len(cells), newly_collected=len(new_rows),
                                **{f"{mode}_correct": correct[mode] for mode in MODES},
                                new_prompt_tokens=sum(r["usage"]["prompt_tokens"] for r in new_rows),
                                new_output_tokens=sum(r["usage"]["output_tokens"] for r in new_rows)))
    FULL.mkdir(parents=True, exist_ok=True)
    for path, rows, fields in [(FULL / "coverage.csv", summary, summary[0].keys()),
                               (missing_file, missing, ("profile", "dataset", "bug_id", "system"))]:
        if path:
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--missing", type=Path, help="Also write the individual missing task/workflow cells.")
    audit(parser.parse_args().missing)
