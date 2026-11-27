import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_phase3 import agree, pairs
from prepare_phase3 import expected, renamed
from bugfix.bugs import load_bugs
from bugfix.sandbox import run_tests


def test_shared_credit_ceiling_survives_concurrent_reservations_and_restart(tmp_path, monkeypatch):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import closing
    from types import SimpleNamespace
    import phase3_credit as credit

    path = tmp_path / "calls.sqlite"
    model = "gpt-4.1-mini-2025-04-14"
    messages = [{"role": "user", "content": "x"}]
    monkeypatch.setattr(credit, "CAP", 1_000_000)

    def attempt(_):
        try:
            return credit.CreditLedger(path).reserve(model, messages, 512)
        except credit.CreditLimitReached:
            return None

    with ThreadPoolExecutor(4) as pool:
        accepted = [r for r in pool.map(attempt, range(4)) if r is not None]
    assert len(accepted) == 1
    ledger = credit.CreditLedger(path)
    ledger.settle(accepted[0], model, None)
    assert attempt(0) is None
    ledger.settle(accepted[0], model, SimpleNamespace(prompt_tokens=10, completion_tokens=20))
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT SUM(amount) FROM calls").fetchone()[0] == 36_000
    assert attempt(0) is not None


def test_full_dataset_dry_runs_reuse_only_identical_inputs(monkeypatch, capsys, tmp_path):
    from argparse import Namespace
    import run_phase3

    # Use the frozen original results and empty extension files. A dry run
    # must never request credentials, even with work left to do.
    for cohort, count in [("full-quixbugs", 112), ("full-condefects", 0)]:
        args = Namespace(profile="openai", cohort=cohort, dry_run=True)
        run_phase3.run_cohort(args, tmp_path / "new.jsonl")
        assert f"{count} attempts remaining" in capsys.readouterr().out
    paths = []
    monkeypatch.setattr(run_phase3, "ROOT", tmp_path)
    monkeypatch.setattr(run_phase3, "run_cohort", lambda args, out: paths.append(out))
    for cohort in ("full-quixbugs", "full-condefects"):
        monkeypatch.setattr(sys, "argv", ["run_phase3", "--profile", "openai", "--cohort", cohort, "--dry-run"])
        run_phase3.main()
    assert [p.name for p in paths] == ["openai-full-quixbugs.jsonl", "openai-full-condefects.jsonl"]


def test_matched_panel_manifest_and_source_pairs():
    path = ROOT / "data/phase3/bugs.jsonl"
    digest = json.loads(path.with_name("manifest.json").read_text())["sha256"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    rows = {b.id: b for b in load_bugs(path)}
    assert len(rows) == 12
    for key, bug in rows.items():
        if key.endswith("/renamed"):
            continue
        twin = rows[key + "/renamed"]
        assert twin == renamed(bug)
        assert twin.func_name != bug.func_name
        assert {t["id"] for t in twin.visible_tests}.isdisjoint(t["id"] for t in twin.heldout_tests)


def test_full_cohort_input_limit_preserves_observed_attempt():
    from bugfix.llm import Budget, BudgetExceeded, OpenAICompatibleLLM

    client = OpenAICompatibleLLM(model="local", base_url="http://127.0.0.1:1/v1", api_key="local",
                                 max_prompt_bytes=8, stop_at_prompt_limit=True)
    budget = Budget(4, 1536)
    messages = [{"role": "user", "content": "Example input"}]
    with pytest.raises(ValueError, match="input limit"):
        client.chat(messages, budget, "repair")
    budget.charge("repair", 20, 5, 0)
    with pytest.raises(BudgetExceeded, match="input limit"):
        client.chat(messages, budget, "repair")
    assert budget.input_limit_reached and budget.calls == 1


def test_later_context_rejection_preserves_existing_calls(monkeypatch):
    from bugfix.llm import Budget, BudgetExceeded, OpenAICompatibleLLM

    class ContextRejection(Exception):
        status_code = 400
        body = {"type": "exceed_context_size_error"}

    def reject(**kwargs):
        raise ContextRejection()

    client = OpenAICompatibleLLM(model="local", base_url="http://127.0.0.1:1/v1", api_key="local",
                                 retries=1, stop_at_prompt_limit=True)
    monkeypatch.setattr(client.client.chat.completions, "create", reject)
    budget = Budget(4, 1536)
    budget.charge("localiser", 20, 5, 0)
    with pytest.raises(BudgetExceeded, match="context window"):
        client.chat([{"role": "user", "content": "fix"}], budget, "fixer")
    assert budget.context_limit_reached and budget.calls == 1


def test_long_rate_window_stops_without_early_retries(monkeypatch):
    from types import SimpleNamespace
    from bugfix.llm import Budget, OpenAICompatibleLLM, QuotaExhausted

    class RateWindow(Exception):
        status_code = 429
        response = SimpleNamespace(headers={"retry-after": "2700"})

    calls = []

    def reject(**kwargs):
        calls.append(kwargs)
        raise RateWindow("HTTP 429")

    client = OpenAICompatibleLLM(model="local", base_url="http://127.0.0.1:1/v1", api_key="local",
                                 retries=4)
    monkeypatch.setattr(client.client.chat.completions, "create", reject)
    budget = Budget()
    with pytest.raises(QuotaExhausted, match="rate window"):
        client.chat([{"role": "user", "content": "fix"}], budget, "fixer")
    assert len(calls) == 1 and budget.calls == 0


def test_local_renaming_keeps_recursive_calls():
    bug = load_bugs(ROOT / "data/quixbugs/bugs.jsonl", ["quixbugs/gcd"])[0]
    twin = renamed(bug)
    assert run_tests(twin.reference_code, twin.func_name, twin.heldout_tests).all_passed


def test_breadth_sample_has_distinct_tasks_and_matches_its_manifest():
    path = ROOT / "data/condefects/bugs.jsonl"
    manifest = json.loads(path.with_name("manifest.json").read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["sha256"]
    bugs = load_bugs(path)
    assert len(bugs) == len({b.id.split("/")[1] for b in bugs}) == 100
    assert {b.id for b in bugs} == {row["bug"] for row in manifest["tasks"]}
    for lo, hi, expected_count in manifest["bands"]:
        assert sum(lo <= t["difficulty"] <= hi for t in manifest["tasks"]) == expected_count


def test_oracles_cover_the_contest_edge_cases():
    assert expected("abc223_a", "201") == "No"
    assert expected("abc223_b", "za") == "az\nza"
    assert expected("abc225_a", "aba") == "3"


def test_candidate_does_not_inherit_provider_environment(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only")
    code = "import os\ndef f():\n    return 'LLM_API_KEY' in os.environ\n"
    assert run_tests(code, "f", [{"id": 0, "input": [], "output": False}]).all_passed


def test_pairing_excludes_missing_attempts():
    counts = pairs({1: {"s1": True, "s2": False}, 2: {"s1": False}, 3: {"s1": True, "s2": True}}, "s1", "s2")
    assert (counts["n_pairs"], counts["left_only"], counts["right_only"]) == (2, 1, 0)


def test_archived_bootstrap_samples_by_bug():
    import pandas as pd
    from analyze import bootstrap_ci

    rows = pd.DataFrame({"bug_id": ["a", "a", "b", "b"], "correct": [True, False, True, True]})
    assert bootstrap_ci(rows, "correct", n=100) == (0.5, 1.0)


def test_over_limit_completion_is_charged_and_stops_the_attempt(monkeypatch):
    from types import SimpleNamespace
    from bugfix.llm import Budget, BudgetExceeded, OpenAICompatibleLLM

    client = OpenAICompatibleLLM(
        model="local", base_url="http://127.0.0.1:1/v1", api_key="local", per_call_max_tokens=10
    )
    reply = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))],
        usage=SimpleNamespace(completion_tokens=15, prompt_tokens=5),
    )
    monkeypatch.setattr(client.client.chat.completions, "create", lambda **kwargs: reply)
    budget = Budget(4, 100)
    with pytest.raises(BudgetExceeded):
        client.chat([], budget, "fixer")
    assert budget.output_tokens == 15
    assert budget.usage()["provider_limit_violations"] == 1
    with pytest.raises(BudgetExceeded):
        budget.check()


def test_kappa_requires_two_complete_rating_files(tmp_path):
    packet = [{"sample_id": "aa"}, {"sample_id": "bb"}]
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("sample_id,label\naa,correct\nbb,incorrect\n")
    b.write_text("sample_id,label\naa,correct\nbb,incorrect\n")
    assert agree(packet, a, b)["kappa"] == 1
    b.write_text("sample_id,label\naa,correct\n")
    with pytest.raises(ValueError):
        agree(packet, a, b)
