"""End-to-end plumbing: API, experiment record format and analysis script (ScriptedLLM only)."""
import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

import bugfix.api as api
from bugfix import Budget, ScriptedLLM, evaluate, toy_bug
from bugfix.systems import SYSTEMS

ROOT = Path(__file__).resolve().parents[1]
BUG = toy_bug()
FIX = "```python\n" + BUG.reference_code + "```"


def test_api_repair_s1(monkeypatch):
    monkeypatch.setattr(api, "get_llm", lambda: ScriptedLLM([FIX]))
    client = TestClient(api.app)
    assert client.get("/health").json()["status"] == "ok"
    body = {"code": BUG.buggy_code, "function_name": BUG.func_name, "mode": "s1",
            "visible_tests": [{"input": t["input"], "output": t["output"]} for t in BUG.visible_tests],
            "heldout_tests": [{"input": t["input"], "output": t["output"]} for t in BUG.heldout_tests]}
    r = client.post("/repair", json=body)
    assert r.status_code == 200 and r.json()["label"] == "correct"


def test_analyze_runs_on_records(tmp_path):
    replies = {"s0": [FIX], "s1": ["no code", FIX], "s2": ["LINES: 4", FIX, "APPROVE"], "s2r": ["LINES: 4", FIX]}
    raw = tmp_path / "raw.jsonl"
    with raw.open("w") as f:
        for run in range(2):
            for s, fn in SYSTEMS.items():
                res = fn(BUG, ScriptedLLM(list(replies[s])), Budget(max_calls=8))
                f.write(json.dumps({"bug_id": BUG.id, "system": s, "run": run, "model": "scripted",
                                    "max_calls": 8, "max_output_tokens": 8000, "wall_s": 0.1,
                                    "stop_reason": res.stop_reason, "passed_visible": res.passed_visible,
                                    "reviewer_approved": res.reviewer_approved, "usage": res.usage,
                                    **evaluate(BUG, res)}) + "\n")
    out = tmp_path / "res"
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "analyze.py"), "--raw", str(raw), "--out", str(out)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    for name in ["summary.csv", "per_bug.csv", "mcnemar.csv", "reviewer.csv", "summary.md",
                 "figures/correct_rate.png", "figures/outcomes.png"]:
        assert (out / name).exists(), name
