"""Plot correctness by ConDefects difficulty with task-level Wilson intervals."""

import json
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analyze_phase3 import OUT, ROOT, records, save


def wilson(k, n):
    z = 1.96
    center = (k + z * z / 2) / (n + z * z)
    radius = z * math.sqrt(k * (n - k) / n + z * z / 4) / (n + z * z)
    return max(0, center - radius), min(1, center + radius)


def main():
    tasks = json.loads((ROOT / "data/condefects/manifest.json").read_text())["tasks"]
    ratings = {t["bug"]: t["difficulty"] for t in tasks}
    runs = records(OUT / "raw/openai-breadth.jsonl")
    rows = []
    bands = [(0, 399, "0–399"), (400, 1199, "400–1199"), (1200, 100000, "1200+")]
    fig, ax = plt.subplots(figsize=(5.25, 3), layout="constrained")
    for system, offset, color in [
        ("s0", -0.21, "#566771"),
        ("s1", -0.07, "#007169"),
        ("s2", 0.07, "#b3552c"),
        ("s2r", 0.21, "#735882"),
    ]:
        for pos, (low, high, label) in enumerate(bands):
            group = [r for r in runs if r["system"] == system and low <= ratings[r["bug_id"]] <= high]
            if not group:
                continue
            n = len(group)
            k = sum(r["label"] == "correct" for r in group)
            a, b = wilson(k, n)
            rows.append(
                dict(
                    system=system,
                    min_difficulty=low,
                    max_difficulty=high,
                    n=n,
                    correct=k,
                    proportion=k / n,
                    wilson_low=a,
                    wilson_high=b,
                )
            )
            ax.errorbar(
                pos + offset,
                k / n,
                [[max(0, k / n - a)], [max(0, b - k / n)]],
                fmt="o",
                color=color,
                capsize=2.5,
                markersize=5,
                label=system.upper().replace("S2R", "S2-R") if pos == 0 else None,
            )
    ax.set_xticks(range(3), [t[2] for t in bands])
    ax.set_xlabel("Upstream task difficulty")
    ax.set_ylabel("Share passing both test sets")
    ax.set_ylim(-0.04, 1.06)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
    ax.grid(axis="y", alpha=0.22)
    ax.spines[["right", "top"]].set_visible(False)
    ax.legend(ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.23))
    save(OUT / "difficulty.csv", rows)
    figures = OUT / "figures"
    figures.mkdir(exist_ok=True)
    fig.savefig(figures / "difficulty.pdf", metadata={"CreationDate": None})
    plt.close(fig)


if __name__ == "__main__":
    main()
