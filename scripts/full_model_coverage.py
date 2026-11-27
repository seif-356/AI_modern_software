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
ADDITIONAL_MODELS = {"gpt4o-mini": "GPT-4o mini", "gpt41-mini": "GPT-4.1 mini", "olmo": "OLMo 2 1B",
                     "granite": "Granite 3.3 2B", "phi3": "Phi-3 mini"}
PROFILES_TO_REPORT = ("openai", "qwen", "smollm2", *ADDITIONAL_MODELS,
                      "archive-gemini", "muse-web", "muse")
MODEL_NAMES = {profile: config[0] for profile, config in PROFILES.items()}
MODEL_NAMES.update({"archive-gemini": "gemini-3.5-flash-lite", "muse-web": "Muse web (Edge)",
                    "muse": "muse-spark-1.3 (Meta API)", "deepseek": "DeepSeek direct (no model run)"})


def records(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def audit(missing_file=None, paper=False):
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
                missing.append(dict(model_or_route=MODEL_NAMES[profile], dataset=dataset, task_id=bug,
                                    missing_workflow=mode))
            correct = Counter(mode for (_, mode), r in cells.items() if r["label"] == "correct")
            observed = Counter(mode for _, mode in cells)
            violations = sum(
                bool(r["usage"].get("provider_limit_violations"))
                or r["usage"]["output_tokens"] > min(r["max_output_tokens"],
                                                    r["usage"]["calls"] * r.get("per_call_max_tokens", 1500))
                or r["usage"]["calls"] > r["max_calls"]
                for r in cells.values() if "usage" in r
            )
            summary.append(dict(profile=profile, model_or_route=MODEL_NAMES[profile], dataset=dataset,
                                planned=len(target), completed=len(cells),
                                missing=len(target)-len(cells), newly_collected=len(new_rows),
                                **{f"{mode}_correct": correct[mode] for mode in MODES},
                                **{f"{mode}_observed": observed[mode] for mode in MODES},
                                known_budget_violations=violations if profile != "muse-web" else "",
                                new_prompt_tokens=sum(r["usage"]["prompt_tokens"] for r in new_rows),
                                new_output_tokens=sum(r["usage"]["output_tokens"] for r in new_rows)))
    FULL.mkdir(parents=True, exist_ok=True)
    for path, rows, fields in [(FULL / "coverage.csv", summary, summary[0].keys()),
                               (missing_file, missing, ("model_or_route", "dataset", "task_id", "missing_workflow"))]:
        if path:
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
    if paper:
        names = {"openai": "GPT-5.4 nano", "qwen": "Qwen Coder", "smollm2": "SmolLM2"}
        lines = []
        for row in summary:
            if row["profile"] not in names:
                continue
            if row["missing"]:
                raise ValueError(f"Incomplete paper sample: {row['profile']} {row['dataset']}")
            cohort = "QuixBugs" if row["dataset"] == "quixbugs" else "ConDefects"
            values = [str(row[mode + "_correct"]) for mode in MODES]
            lines.append(" & ".join([cohort, names[row["profile"]], *values]) + r"\\")
        path = ROOT / "docs/phase3/full_model_rows.tex"
        path.write_text("\\newcommand{\\FullModelRows}{%\n" + "\n".join(lines) + "%\n}\n", encoding="utf-8")
        lines = []
        for row in summary:
            if row["profile"] not in ADDITIONAL_MODELS:
                continue
            dataset = "QuixBugs" if row["dataset"] == "quixbugs" else "ConDefects"
            scores = [f"{row[m + '_correct']}/{row[m + '_observed']}" if row[m + '_observed'] else "--"
                      for m in MODES]
            lines.append(" & ".join([dataset, ADDITIONAL_MODELS[row["profile"]], *scores]) + r"\\")
        path = ROOT / "docs/phase3/additional_model_rows.tex"
        path.write_text("\\newcommand{\\AdditionalModelRows}{%\n" + "\n".join(lines) + "%\n}\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--missing", type=Path, help="Also write the individual missing task/workflow cells.")
    parser.add_argument("--paper", action="store_true", help="Generate the full-dataset table after collection.")
    args = parser.parse_args()
    audit(args.missing, args.paper)
