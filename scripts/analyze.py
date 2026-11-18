"""Turn raw run records into the tables and figures used in the report.

    python scripts/analyze.py --raw results/raw/quixbugs.jsonl --out results

Writes summary.csv, per_bug.csv, mcnemar.csv, reviewer.csv, summary.md and figures/*.png.
Confidence intervals: bootstrap over bugs (runs of the same bug are not independent).
Significance: exact McNemar test on paired (bug, run) correctness.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

import pandas as pd

ORDER = ["s0", "s1", "s2", "s2r"]
NAMES = {"s0": "S0 single-shot", "s1": "S1 single agent", "s2": "S2 multi-agent", "s2r": "S2-R no reviewer"}
FLAGS = ["H1_non_runnable", "H2_nonexistent_api", "H3_signature_changed", "H4_unchanged",
         "H5_reviewer_approved_wrong"]


def load(path: Path) -> pd.DataFrame:
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            u = r.pop("usage")
            r.pop("trace", None)
            r.pop("final_code", None)
            rows.append({**r, **{f"u_{k}": v for k, v in u.items()}})
    df = pd.DataFrame(rows)
    df["correct"] = df["label"] == "correct"
    df["plausible_incorrect"] = df["label"] == "plausible_incorrect"
    return df


def bootstrap_ci(df: pd.DataFrame, col: str, n: int = 2000, seed: int = 403) -> tuple[float, float]:
    per_bug = df.groupby("bug_id")[col].mean().to_numpy()
    if len(per_bug) == 0:
        return (math.nan, math.nan)
    rng = random.Random(seed)
    stats = sorted(sum(rng.choice(per_bug) for _ in per_bug) / len(per_bug) for _ in range(n))
    return stats[int(0.025 * n)], stats[int(0.975 * n) - 1]


def exact_mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="results/raw/quixbugs.jsonl")
    ap.add_argument("--out", default="results")
    ap.add_argument("--price-in", type=float, help="USD per 1M prompt tokens (optional)")
    ap.add_argument("--price-out", type=float, help="USD per 1M output tokens (optional)")
    args = ap.parse_args()
    out = Path(args.out)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    df = load(Path(args.raw))
    systems = [s for s in ORDER if s in set(df["system"])]

    rows = []
    for s in systems:
        d = df[df.system == s]
        lo, hi = bootstrap_ci(d, "correct")
        pc = d["plausible_incorrect"].sum()
        row = {
            "system": s, "name": NAMES[s], "bugs": d.bug_id.nunique(), "attempts": len(d),
            "correct_rate": d.correct.mean(), "ci95_low": lo, "ci95_high": hi,
            "plausible_incorrect_rate": d.plausible_incorrect.mean(),
            "failing_rate": (d.label == "failing").mean(),
            "overfitting_rate": pc / (pc + d.correct.sum()) if (pc + d.correct.sum()) else math.nan,
            "mean_calls": d.u_calls.mean(), "mean_prompt_tokens": d.u_prompt_tokens.mean(),
            "mean_output_tokens": d.u_output_tokens.mean(),
            "prompt_tokens_per_call": (d.u_prompt_tokens / d.u_calls.clip(lower=1)).mean(),
            "mean_wall_s": d.wall_s.mean(), "budget_exhausted_rate": (d.stop_reason == "budget").mean(),
            **{f: d[f].mean() for f in FLAGS}, "any_hallucination": d.any_hallucination.mean(),
        }
        if args.price_in is not None and args.price_out is not None:
            row["mean_cost_usd"] = (d.u_prompt_tokens * args.price_in + d.u_output_tokens * args.price_out).mean() / 1e6
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary.to_csv(out / "summary.csv", index=False, float_format="%.4f")

    per_bug = df.pivot_table(index="bug_id", columns="system", values="correct", aggfunc="sum").reindex(columns=systems)
    per_bug.to_csv(out / "per_bug.csv")

    pairs = [(a, b) for a, b in [("s1", "s2"), ("s2", "s2r"), ("s1", "s2r"), ("s0", "s1"), ("s0", "s2")]
             if a in systems and b in systems]
    mc = []
    for a, b in pairs:
        m = df[df.system.isin([a, b])].pivot_table(index=["bug_id", "run"], columns="system",
                                                    values="correct", aggfunc="first").dropna()
        only_a, only_b = int((m[a] & ~m[b].astype(bool)).sum()), int((m[b] & ~m[a].astype(bool)).sum())
        mc.append({"a": a, "b": b, "pairs": len(m), "only_a_correct": only_a, "only_b_correct": only_b,
                   "p_value_exact": exact_mcnemar(only_a, only_b)})
    pd.DataFrame(mc).to_csv(out / "mcnemar.csv", index=False, float_format="%.4f")

    rev = df[(df.system == "s2") & df.passed_visible & df.reviewer_approved.notna()]
    if len(rev):
        appr = rev.reviewer_approved.astype(bool)
        tp, fp = int((appr & rev.correct).sum()), int((appr & ~rev.correct).sum())
        fn, tn = int((~appr & rev.correct).sum()), int((~appr & ~rev.correct).sum())
        pd.DataFrame([{"reviewed_final_patches": len(rev), "approved_correct": tp, "approved_wrong": fp,
                       "rejected_correct": fn, "rejected_wrong": tn,
                       "approval_precision": tp / (tp + fp) if tp + fp else math.nan,
                       "wrong_patch_catch_rate": tn / (tn + fp) if tn + fp else math.nan}]
                     ).to_csv(out / "reviewer.csv", index=False, float_format="%.4f")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 3.5))
    x = range(len(summary))
    ax.bar(x, summary.correct_rate, yerr=[summary.correct_rate - summary.ci95_low,
                                          summary.ci95_high - summary.correct_rate], capsize=4, color="#3b6ea5")
    ax.set_xticks(list(x), summary.name, rotation=15)
    ax.set_ylabel("Correct fix rate (held-out tests)")
    ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(out / "figures" / "correct_rate.png", dpi=200)

    fig, ax = plt.subplots(figsize=(6, 3.5))
    bottom = [0.0] * len(summary)
    for col, color in [("correct_rate", "#3b6ea5"), ("plausible_incorrect_rate", "#e0a030"), ("failing_rate", "#b0b0b0")]:
        ax.bar(x, summary[col], bottom=bottom, color=color, label=col.replace("_rate", "").replace("_", " "))
        bottom = [b + v for b, v in zip(bottom, summary[col])]
    ax.set_xticks(list(x), summary.name, rotation=15)
    ax.set_ylabel("Share of attempts")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "figures" / "outcomes.png", dpi=200)

    model = df.model.iloc[0] if "model" in df else "?"
    lines = [f"# Results ({model}, budget {df.max_calls.iloc[0]} calls / {df.max_output_tokens.iloc[0]} output tokens)", "",
             summary[["name", "bugs", "attempts", "correct_rate", "ci95_low", "ci95_high", "plausible_incorrect_rate",
                      "overfitting_rate", "mean_calls", "mean_output_tokens", "any_hallucination"]]
             .to_markdown(index=False, floatfmt=".3f"), "", "## McNemar (exact, paired by bug and run)", "",
             pd.DataFrame(mc).to_markdown(index=False, floatfmt=".4f")]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
