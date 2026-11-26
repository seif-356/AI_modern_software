"""Run one fixed, resumable model panel. Hosted credentials are read only for the chosen profile."""

import argparse
import getpass
import hashlib
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from filelock import FileLock, Timeout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bugfix import SYSTEMS, Budget, evaluate, load_bugs
from bugfix.llm import OpenAICompatibleLLM
from run_experiment import git_commit

# The local llama-server profiles use pinned aliases and bind to loopback.
PROFILES = {
    "qwen": ("qwen2.5-coder-1.5b-instruct-q4_k_m", "http://127.0.0.1:18181/v1", None),
    "smollm2": ("smollm2-1.7b-instruct-q4_k_m", "http://127.0.0.1:18182/v1", None),
    "deepseek-coder": ("deepseek-coder-1.3b-instruct-q4_k_m", "http://127.0.0.1:18183/v1", None),
    "openai": ("gpt-5.4-nano-2026-03-17", "https://api.openai.com/v1", "OPENAI_API_KEY"),
    "orca": ("deepseek/deepseek-v4-flash-free", "https://api.orcarouter.ai/v1", "ORCAROUTER_API_KEY"),
    "deepseek": ("deepseek-flash", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "muse": ("muse-spark-1.3", "https://api.meta.ai/v1", "MODEL_API_KEY"),
}
MAX_CALLS, MAX_TOKENS, PER_CALL = 4, 1536, 512
TEMPERATURE = 0.2
DATA = ROOT / "data/phase3/bugs.jsonl"
COHORT_DATA = {
    "panel": DATA,
    "breadth": ROOT / "data/condefects/bugs.jsonl",
    "full-quixbugs": ROOT / "data/quixbugs/bugs.jsonl",
    "full-condefects": ROOT / "data/condefects/bugs.jsonl",
}


def main():
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("--profile", required=True, choices=PROFILES)
    arg.add_argument("--workers", type=int, default=1, choices=range(1, 5))
    arg.add_argument("--cohort", choices=COHORT_DATA, default="panel")
    arg.add_argument("--dry-run", action="store_true")
    args = arg.parse_args()
    name = args.profile if args.cohort == "panel" else args.profile + "-" + args.cohort
    directory = "full-models" if args.cohort.startswith("full-") else "raw"
    out = ROOT / "results/phase3" / directory / (name + ".jsonl")
    identity = hashlib.sha256(os.path.normcase(str(out)).encode()).hexdigest()[:24]
    lock = Path(tempfile.gettempdir()) / f"sw403-{identity}.lock"
    try:
        with FileLock(lock, timeout=0):
            run_cohort(args, out)
    except Timeout:
        arg.exit(1, f"Another process is already running {name}.\n")


def run_cohort(args, out):
    model, base, var = PROFILES[args.profile]
    data = COHORT_DATA[args.cohort]
    meta = dict(
        model=model,
        profile=args.profile,
        data_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
        temperature=TEMPERATURE,
        max_calls=MAX_CALLS,
        max_output_tokens=MAX_TOKENS,
        per_call_max_tokens=PER_CALL,
    )
    jobs = {(b.id, s, 0): b for b in load_bugs(data) for s in SYSTEMS}
    if args.cohort.startswith("full-"):
        for suffix, original_data in [("", DATA), ("-breadth", ROOT / "data/condefects/bugs.jsonl")]:
            source = ROOT / "results/phase3/raw" / (args.profile + suffix + ".jsonl")
            if not source.exists():
                continue
            source_bugs = {b.id: b for b in load_bugs(original_data)}
            expected = dict(meta, data_sha256=hashlib.sha256(original_data.read_bytes()).hexdigest())
            for line in source.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                key = row["bug_id"], row["system"], row["run"]
                if key in jobs and source_bugs.get(key[0]) == jobs[key]:
                    if any(row.get(k) != v for k, v in expected.items()):
                        raise ValueError(f"Incompatible source record in {source.name}: {key}")
                    del jobs[key]
    if out.exists():
        valid_hashes = {meta["data_sha256"]}
        if args.cohort == "full-quixbugs":
            # Git auto-converts this archived file on Windows. Preserve each
            # row's measured byte hash and accept either checkout line ending.
            lf = data.read_bytes().replace(b"\r\n", b"\n")
            valid_hashes.update(hashlib.sha256(b).hexdigest() for b in (lf, lf.replace(b"\n", b"\r\n")))
        for line in out.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            key = r["bug_id"], r["system"], r["run"]
            compatible = r.get("data_sha256") in valid_hashes and all(
                r.get(k) == v for k, v in meta.items() if k != "data_sha256")
            if not compatible or key not in jobs:
                raise ValueError(f"Incompatible or duplicate record in {out.name}: {key}")
            del jobs[key]
    print(f"{args.profile}: {len(jobs)} attempts remaining", flush=True)
    if not jobs or args.dry_run:
        return
    secret = (os.getenv(var) or getpass.getpass(var + ": ")) if var else "local"
    free_route = args.profile == "orca"
    llm = OpenAICompatibleLLM(
        model=model,
        base_url=base,
        api_key=secret,
        temperature=TEMPERATURE,
        per_call_max_tokens=PER_CALL,
        retries=4 if free_route else 1,
        rpm=6 if free_route else 0,
        max_prompt_bytes=16384,
        stop_at_prompt_limit=args.cohort.startswith("full-"),
    )
    # Validate the free route against the live catalog before sending any prompts.
    if args.profile == "orca":
        catalog = {m.id: m for m in llm.client.models.list()}
        price = getattr(catalog.get(model), "pricing", {}) or {}
        if (
            not price
            or not ("request" in price or {"prompt", "completion"} <= price.keys())
            or any(float(v) != 0 for v in price.values())
        ):
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
        stop_reason = result.stop_reason
        if budget.input_limit_reached:
            stop_reason = "input_limit"
        if budget.context_limit_reached:
            stop_reason = "context_limit"
        return dict(
            **meta,
            bug_id=bug_id,
            system=system,
            run=repetition,
            commit=commit,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            wall_s=round(time.monotonic() - t0, 2),
            stop_reason=stop_reason,
            passed_visible=result.passed_visible,
            reviewer_approved=result.reviewer_approved,
            usage=result.usage,
            call_usage=budget.log,
            **evaluate(bug, result),
            final_code=result.final_code,
            trace=result.trace,
        )

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
                    status = getattr(cause, "status_code", None)
                    message = f"{key}: {type(cause).__name__} (HTTP {status or '?'})"
                    if not var and status in {400, 413}:
                        detail = getattr(cause, "body", {}) or {}
                        if isinstance(detail, dict):
                            message += f" local error type={detail.get('type', 'unknown')}"
                    if not var and isinstance(cause, (ValueError, UnicodeError)):
                        message += f" {str(cause)[:180]}"
                    if status == 402:
                        body = getattr(cause, "body", None)
                        if isinstance(body, dict):
                            detail = body.get("error", body)
                            if isinstance(detail, dict):
                                message += " " + str(detail.get("message", "")).replace(secret, "[redacted]")[:350]
                    if status == 429:
                        headers = cause.response.headers
                        message += f"; retry-after={headers.get('retry-after', 'unspecified')}"
                    errors.append(message)
                    continue
                with out.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row) + "\n")
                print(key, row["label"], flush=True)
            if errors:
                raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()
