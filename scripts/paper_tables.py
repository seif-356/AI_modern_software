"""Generate the LaTeX values used by the paper and talk directly from saved runs."""
import csv
import json
from collections import Counter
from pathlib import Path

from analyze_phase3 import OUT, ROOT, ARCHIVE, records
from analyze import exact_mcnemar

NAMES={"openai":"GPT-5.4 nano","orca":"DeepSeek V4 Flash","qwen":"Qwen2.5-Coder 1.5B","smollm2":"SmolLM2 1.7B",
       "deepseek-coder":"DeepSeek Coder 1.3B","muse":"Muse Spark 1.3"}
MODES=["s0","s1","s2","s2r"]


def main():
    raw={p.stem:records(p) for p in sorted((OUT/"raw").glob("*.jsonl"))}
    total=sum(map(len,raw.values()))
    archive=records(ARCHIVE)
    values={}
    values["NewAttempts"]=total
    values["TotalAttempts"]=total+len(archive)
    values["ReviewEligible"]=sum(r["label"] in ["correct","plausible_incorrect"] for rows in [archive,*raw.values()] for r in rows)
    with (OUT/"review_packet.csv").open(newline="",encoding="utf-8") as f:
        values["ReviewSample"]=sum(1 for _ in csv.DictReader(f))
    panel=[]
    probe=[]
    for name,rows in raw.items():
        if name.endswith("-breadth"):
            continue
        counts=[f"{sum(r['label']=='correct' for r in rows if r['system']==s)}/{sum(r['system']==s for r in rows)}"
                for s in MODES]
        panel.append(" & ".join([NAMES[name],*counts])+r" \\")
        if name=="orca":
            continue  # Gateway usage exceeded requested limits; descriptive counts only.
        for dataset in ("quixbugs","condefects"):
            lookup={(r["bug_id"],r["system"]):r["label"]=="correct" for r in rows if r["bug_id"].startswith(dataset+"/")}
            matched=[(ok,lookup[k+"/renamed",s]) for (k,s),ok in lookup.items() if (k+"/renamed",s) in lookup]
            dataset_title = {"quixbugs":"QuixBugs", "condefects":"ConDefects"}[dataset]
            probe.append(" & ".join(map(str,[NAMES[name],dataset_title,len(matched),
                        sum(a and not b for a,b in matched),sum(b and not a for a,b in matched)]))+r" \\")
    wide=raw.get("openai-breadth",[])
    values["BreadthAttempts"]=len(wide)
    breadth=[]
    for s in MODES:
        rows=[r for r in wide if r["system"]==s]
        if not rows:
            continue
        c=Counter(r["label"] for r in rows)
        breadth.append(" & ".join(map(str,[s.upper().replace("S2R","S2-R"),len(rows),c["correct"],c["plausible_incorrect"],
                    c["failing"],f"{sum(r['usage']['calls'] for r in rows)/len(rows):.2f}"]))+r" \\")
    paired=[]
    for a,b in [("s1","s2"),("s2","s2r")]:
        l={r["bug_id"]:r["label"]=="correct" for r in wide if r["system"]==a}
        r={r["bug_id"]:r["label"]=="correct" for r in wide if r["system"]==b}
        keys=l.keys() & r.keys()
        only_l=sum(l[k] and not r[k] for k in keys)
        only_r=sum(r[k] and not l[k] for k in keys)
        paired.append(" & ".join(map(str,[a.upper(),b.upper().replace("S2R","S2-R"),len(keys),only_l,only_r,
                                                f"{exact_mcnemar(only_l,only_r):.3f}"]))+r" \\")
    output=ROOT/"docs/phase3"
    output.mkdir(parents=True,exist_ok=True)
    values.update(PanelRows="\n".join(panel),ProbeRows="\n".join(probe),
                  BreadthRows="\n".join(breadth),WidePairs="\n".join(paired))
    text="".join("\\newcommand{\\"+k+"}{"+str(v)+"}\n" for k,v in values.items())
    (output/"evidence.tex").write_text(text,encoding="utf-8")


if __name__=="__main__":
    main()
