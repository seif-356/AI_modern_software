import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from analyze_phase3 import agree, pairs
from prepare_phase3 import expected, renamed
from bugfix.bugs import load_bugs, toy_bug
from bugfix.sandbox import run_tests


def test_matched_panel_manifest_and_source_pairs():
    path=ROOT/"data/phase3/bugs.jsonl"
    digest=json.loads(path.with_name("manifest.json").read_text())["sha256"]
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    rows={b.id:b for b in load_bugs(path)}
    assert len(rows)==12
    for key,bug in rows.items():
        if key.endswith("/renamed"):
            continue
        twin=rows[key+"/renamed"]
        assert twin==renamed(bug)
        assert twin.func_name!=bug.func_name
        assert {t["id"] for t in twin.visible_tests}.isdisjoint(t["id"] for t in twin.heldout_tests)


def test_local_renaming_keeps_recursive_calls():
    bug=load_bugs(ROOT/"data/quixbugs/bugs.jsonl",["quixbugs/gcd"])[0]
    twin=renamed(bug)
    assert run_tests(twin.reference_code,twin.func_name,twin.heldout_tests).all_passed


def test_oracles_cover_the_contest_edge_cases():
    assert expected("abc223_a","201")=="No"
    assert expected("abc223_b","za")=="az\nza"
    assert expected("abc225_a","aba")=="3"


def test_candidate_does_not_inherit_provider_environment(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY","test-only")
    code="import os\ndef f():\n    return 'LLM_API_KEY' in os.environ\n"
    assert run_tests(code,"f",[{"id":0,"input":[],"output":False}]).all_passed


def test_pairing_excludes_missing_attempts():
    counts=pairs({1:{"s1":True,"s2":False},2:{"s1":False},3:{"s1":True,"s2":True}},"s1","s2")
    assert (counts["n_pairs"],counts["left_only"],counts["right_only"])==(2,1,0)


def test_kappa_requires_two_complete_rating_files(tmp_path):
    packet=[{"sample_id":"aa"},{"sample_id":"bb"}]
    a,b=tmp_path/"a.csv",tmp_path/"b.csv"
    a.write_text("sample_id,label\naa,correct\nbb,incorrect\n")
    b.write_text("sample_id,label\naa,correct\nbb,incorrect\n")
    assert agree(packet,a,b)["kappa"]==1
    b.write_text("sample_id,label\naa,correct\n")
    with pytest.raises(ValueError):
        agree(packet,a,b)
