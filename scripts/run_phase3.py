"""Run one fixed, resumable model panel. Hosted credentials are read only for the chosen profile."""
import argparse
import getpass
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bugfix import SYSTEMS, Budget, evaluate, load_bugs
from bugfix.llm import OpenAICompatibleLLM
from run_experiment import git_commit

# Model aliases for llama-server --alias. The two endpoints only bind to loopback.
PROFILES = {
    "qwen": ("qwen2.5-coder-1.5b-instruct-q4_k_m", "http://127.0.0.1:18181/v1", None),
    "smollm2": ("smollm2-1.7b-instruct-q4_k_m", "http://127.0.0.1:18182/v1", None),
    "openai": ("gpt-5.4-nano-2026-03-17", "https://api.openai.com/v1", "OPENAI_API_KEY"),
    "orca": ("deepseek/deepseek-v4-flash-free", "https://api.orcarouter.ai/v1", "ORCAROUTER_API_KEY"),
    "deepseek": ("deepseek-flash", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "muse": ("muse-spark-1.3", "https://api.meta.ai/v1", "MODEL_API_KEY"),
}
MAX_CALLS, MAX_TOKENS, PER_CALL = 4, 1536, 512
TEMPERATURE = 0.2
DATA = ROOT / "data/phase3/bugs.jsonl"


def main():
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("--profile", required=True, choices=PROFILES)
    arg.add_argument("--workers", type=int, default=1, choices=range(1, 5))
    arg.add_argument("--cohort", choices=["panel", "breadth"], default="panel")
    arg.add_argument("--dry-run", action="store_true")
    args = arg.parse_args()
    model, base, var = PROFILES[args.profile]
    data = DATA if args.cohort == "panel" else ROOT / "data/condefects/bugs.jsonl"
    name = args.profile if args.cohort == "panel" else args.profile + "-breadth"
    out = ROOT / "results/phase3/raw" / (name + ".jsonl")
    meta = dict(model=model, profile=args.profile, data_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
                temperature=TEMPERATURE, max_calls=MAX_CALLS, max_output_tokens=MAX_TOKENS,
                per_call_max_tokens=PER_CALL)
    jobs = {(b.id, s, 0): b for b in load_bugs(data) for s in SYSTEMS}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            key = r["bug_id"], r["system"], r["run"]
            if any(r.get(k) != v for k, v in meta.items()) or key not in jobs:
                raise ValueError(f"Incompatible or duplicate record in {out.name}: {key}")
            del jobs[key]
    print(f"{args.profile}: {len(jobs)} attempts remaining", flush=True)
    if not jobs or args.dry_run:
        return
    secret = (os.getenv(var) or getpass.getpass(var + ": ")) if var else "local"
    free_route = args.profile == "orca"
    llm = OpenAICompatibleLLM(model=model, base_url=base, api_key=secret, temperature=TEMPERATURE,
                              per_call_max_tokens=PER_CALL, retries=4 if free_route else 1,
                              rpm=6 if free_route else 0, max_prompt_bytes=16384)
    # Validate the free route against the live catalog before sending any prompts.
    if args.profile == "orca":
        catalog = {m.id: m for m in llm.client.models.list()}
        price = getattr(catalog.get(model), "pricing", {}) or {}
        if not price or not ("request" in price or {"prompt", "completion"} <= price.keys()) or any(
                float(v) != 0 for v in price.values()):
            raise ValueError("The selected route does not advertise zero prices.")
    if not var:
        available = {m.id for m in llm.client.models.list()}
        if model not in available:
            raise ValueError(f"Expected local alias {model} on {base}")
    commit = git_commit()

    def run(key):
        bug_id, system, repetition = key
        bug = jobs[key]
        t0 = time.monotonic()
        budget = Budget(MAX_CALLS, MAX_TOKENS)
        result = SYSTEMS[system](bug, llm, budget)
        return dict(**meta, bug_id=bug_id, system=system, run=repetition, commit=commit,
                    timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    wall_s=round(time.monotonic() - t0, 2), stop_reason=result.stop_reason,
                    passed_visible=result.passed_visible, reviewer_approved=result.reviewer_approved,
                    usage=result.usage, **evaluate(bug, result), final_code=result.final_code,
                    trace=result.trace)

    out.parent.mkdir(parents=True, exist_ok=True)
    # Consume small batches so an unavailable provider stops the run promptly.
    keys = iter(jobs)
    from itertools import islice
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        while batch := list(islice(keys, args.workers)):
            futures = [pool.submit(run, key) for key in batch]
            errors = []
            for key, f in zip(batch, futures):
                try:
                    row = f.result()
                except Exception as exc:
                    # Provider bodies can echo auth details. Only expose the class and status.
                    cause = exc.__cause__ or exc
                    errors.append(f"{key}: {type(cause).__name__} (HTTP {getattr(cause, 'status_code', '?')})")
                    continue
                with out.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row) + "\n")
                print(key, row["label"], flush=True)
            if errors:
                raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()
