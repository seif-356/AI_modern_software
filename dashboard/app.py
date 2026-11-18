"""Streamlit dashboard (course 'Dashboard / Visualization').

    streamlit run dashboard/app.py
"""
import difflib
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze import FLAGS, NAMES, load  # noqa: E402

st.set_page_config(page_title="Multi-Agent Bug Fixing", layout="wide")
st.title("Multi-agent vs single-agent bug fixing")

raw_files = sorted((ROOT / "results" / "raw").glob("*.jsonl"))
if not raw_files:
    st.info("No results yet. Run scripts/run_experiment.py first.")
    st.stop()
raw_path = st.sidebar.selectbox("Results file", raw_files, format_func=lambda p: p.name)
df = load(raw_path)
records = [json.loads(l) for l in raw_path.read_text().splitlines() if l.strip()]
st.sidebar.write(f"Model: `{df.model.iloc[0]}`")
st.sidebar.write(f"Budget: {df.max_calls.iloc[0]} calls / {df.max_output_tokens.iloc[0]} output tokens")
st.sidebar.write(f"{df.bug_id.nunique()} bugs, {len(df)} attempts")

agg = df.groupby("system").agg(
    attempts=("label", "size"), correct=("correct", "mean"), plausible_incorrect=("plausible_incorrect", "mean"),
    failing=("label", lambda s: (s == "failing").mean()), calls=("u_calls", "mean"),
    output_tokens=("u_output_tokens", "mean"), wall_s=("wall_s", "mean"),
    hallucination=("any_hallucination", "mean")).reset_index()
agg["name"] = agg.system.map(NAMES)

c = st.columns(len(agg))
for col, (_, r) in zip(c, agg.iterrows()):
    col.metric(r["name"], f"{r['correct']:.0%} correct", f"{r['plausible_incorrect']:.0%} plausible-but-wrong",
               delta_color="off")

st.subheader("Outcomes per system")
st.bar_chart(agg.set_index("name")[["correct", "plausible_incorrect", "failing"]])
st.dataframe(agg.set_index("name").drop(columns="system").style.format("{:.3f}", subset=pd.IndexSlice[:, [
    "correct", "plausible_incorrect", "failing", "hallucination"]]), use_container_width=True)

st.subheader("Hallucination flags (share of attempts)")
st.bar_chart(df.groupby("system")[FLAGS].mean().rename(index=NAMES))

summary_dir = raw_path.parent.parent
for name, title in [("mcnemar.csv", "McNemar tests"), ("reviewer.csv", "Reviewer agent (S2)")]:
    if (summary_dir / name).exists():
        st.subheader(title)
        st.dataframe(pd.read_csv(summary_dir / name), use_container_width=True)

st.subheader("Per bug: correct runs")
st.dataframe(df.pivot_table(index="bug_id", columns="system", values="correct", aggfunc="sum"),
             use_container_width=True)

st.subheader("Errors and logs")
err = df[df.error_types.map(len) > 0][["bug_id", "system", "run", "label", "error_types"]]
st.dataframe(err, use_container_width=True)

st.subheader("Inspect one attempt")
bug_id = st.selectbox("Bug", sorted(df.bug_id.unique()))
system = st.selectbox("System", [s for s in NAMES if s in set(df.system)], format_func=NAMES.get)
runs = sorted(df[(df.bug_id == bug_id) & (df.system == system)].run)
run = st.selectbox("Run", runs) if runs else None
rec = next((r for r in records if r["bug_id"] == bug_id and r["system"] == system and r["run"] == run), None)
if rec:
    st.write(f"**{rec['label']}** · stop: {rec['stop_reason']} · visible {rec['visible_passed']}/{rec['visible_total']}"
             f" · held-out {rec['heldout_passed']}/{rec['heldout_total']} · calls {rec['usage']['calls']}")
    data = ROOT / "data" / "quixbugs" / "bugs.jsonl"
    buggy = ""
    if data.exists():
        for line in data.read_text().splitlines():
            b = json.loads(line)
            if b["id"] == bug_id:
                buggy = b["buggy_code"]
    st.code("".join(difflib.unified_diff(buggy.splitlines(True), rec["final_code"].splitlines(True),
                                         "buggy", "final patch")) or rec["final_code"], language="diff")
    for i, s in enumerate(rec["trace"]):
        with st.expander(f"{i}. {s['role']}" + (f" (visible {s.get('visible_passed')}/{s.get('visible_total')})"
                                                 if "visible_total" in s else "")):
            st.text(s.get("reply") or s.get("load_error") or "")
