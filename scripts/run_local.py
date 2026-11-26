"""Serve a pinned local GGUF on loopback, run its panel, and stop the server."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from pathlib import Path

from run_phase3 import PROFILES, ROOT

WEIGHTS = {
    "deepseek-coder": (
        "deepseek-coder-1.3b-instruct.Q4_K_M.gguf",
        "04cebb6fafa40ae628cf6bfeb76032ec792852f54020c559ad0a56b9f2839118",
    ),
    "qwen": (
        "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        "cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046",
    ),
    "smollm2": (
        "smollm2-1.7b-instruct-q4_k_m.gguf",
        "decd2598bc2c8ed08c19adc3c8fdd461ee19ed5708679d1c54ef54a5a30d4f33",
    ),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", choices=WEIGHTS, required=True)
    ap.add_argument("--server", default="llama-server")
    ap.add_argument("--weights", type=Path, required=True, help="directory containing the pinned GGUF")
    ap.add_argument("--cohort", nargs="+", choices=["panel", "breadth", "full-quixbugs", "full-condefects"],
                    default=["panel"])
    args = ap.parse_args()
    filename, digest = WEIGHTS[args.profile]
    path = args.weights / filename
    with path.open("rb") as f:
        if hashlib.file_digest(f, "sha256").hexdigest() != digest:
            ap.error("GGUF checksum mismatch")
    alias, base, _ = PROFILES[args.profile]
    port = urlparse(base).port
    command = [
        args.server,
        "--model",
        str(path),
        "--alias",
        alias,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--ctx-size",
        "8192",
        "--parallel",
        "2",
        "--batch-size",
        "256",
        "--n-gpu-layers",
        "99",
        "--seed",
        "403",
    ]
    with tempfile.TemporaryFile() as log:
        server = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(180):
                if server.poll() is not None:
                    log.seek(0)
                    raise RuntimeError(log.read().decode(errors="replace")[-2500:])
                try:
                    with urllib.request.urlopen(base + "/models", timeout=2) as response:
                        if alias in {m["id"] for m in json.load(response)["data"]}:
                            break
                except (urllib.error.URLError, TimeoutError):
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Local model did not become ready")
            for cohort in args.cohort:
                subprocess.run(
                    [sys.executable, "-u", str(ROOT / "scripts/run_phase3.py"),
                     "--profile", args.profile, "--workers", "2", "--cohort", cohort],
                    check=True, cwd=ROOT,
                )
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
