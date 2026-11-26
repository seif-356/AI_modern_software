"""Build a 100-submission breadth sample using independent contest examples.

Pin the upstream commit first. Selected case files are self-contained. A cache
outside the repository allows an interrupted public-example lookup to resume.
"""

import argparse
import ast
import hashlib
import json
import random
import subprocess
import sys
import textwrap
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bugfix.bugs import Bug
from bugfix.sandbox import run_tests
from prepare_phase3 import REVISION


# Keep the original script body visible as ordinary Python. Runs support input(),
# sys.stdin and early contest exits; each case restores its streams on exit.
def adapt(source):
    tree = ast.parse(source)
    if any(isinstance(n, (ast.Global, ast.Nonlocal)) for n in ast.walk(tree)):
        raise ValueError("unsupported module-level binding")
    body = []
    for node in tree.body:
        if isinstance(node, ast.If) and ast.unparse(node.test) in (
            "__name__ == '__main__'",
            "'__main__' == __name__",
        ):
            body.extend(node.body)
        else:
            body.append(node)
    module = ast.Module(body, [])
    code = ast.unparse(module)
    return (
        "import io\nimport sys\nfrom contextlib import redirect_stdout\n\n"
        "def solve(text):\n    def program():\n"
        + textwrap.indent(code, "        ")
        + "\n    previous = sys.stdin\n    output = io.StringIO()\n    try:\n"
        "        sys.stdin = io.StringIO(text)\n        with redirect_stdout(output):\n"
        "            program()\n    except SystemExit as status:\n        if status.code not in (None, 0):\n"
        "            raise\n    finally:\n        sys.stdin = previous\n    return output.getvalue().strip()\n"
    )


def public_examples(task, cache):
    url = f"https://atcoder.jp/contests/{task.split('_')[0]}/tasks/{task}?lang=en"
    dest = cache / (task + ".json")
    if dest.exists():
        return url, json.loads(dest.read_text(encoding="utf-8"))
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                html = BeautifulSoup(response.read(), "html.parser")
            break
        except (TimeoutError, OSError):
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    parts = {}
    for section in html.select("span.lang-en section"):
        if not section.h3 or not section.pre:
            continue
        title = section.h3.get_text(" ", strip=True).split()
        if (
            len(title) == 3
            and title[0] == "Sample"
            and title[1] in ("Input", "Output")
            and title[2].isdigit()
        ):
            parts.setdefault(int(title[2]), {})[title[1]] = (
                section.pre.get_text().replace("\r\n", "\n").strip("\n")
            )
    pairs = [(d["Input"] + "\n", d["Output"].strip()) for _, d in sorted(parts.items()) if len(d) == 2]
    dest.write_text(json.dumps(pairs), encoding="utf-8")
    return url, pairs


def select_task(task, src, cache):
    folder = src / "Code" / task / "Python"
    url, examples = public_examples(task, cache)
    tests = [{"id": i, "input": [x], "output": y} for i, (x, y) in enumerate(examples)]
    if (
        len(tests) < 2
        or len({x for x, _ in examples}) != len(examples)
        or max(len(x) + len(y) for x, y in examples) > 1200
    ):
        return None
    paths = sorted(folder.glob("*/faultyVersion.py"))
    random.Random("403/" + task).shuffle(paths)
    for path in paths:
        try:
            raw = path.read_text(encoding="utf-8-sig")
            ref = path.with_name("correctVersion.py").read_text(encoding="utf-8-sig")
            if max(len(raw), len(ref)) > 3500 or "from __future__" in raw + ref:
                continue
            faulty, correct = adapt(raw), adapt(ref)
        except (ValueError, SyntaxError, UnicodeError):
            continue
        wrong = run_tests(faulty, "solve", tests, per_test_timeout=0.8)
        if wrong.import_error or wrong.timed_out or wrong.all_passed:
            continue
        good = run_tests(correct, "solve", tests, per_test_timeout=0.8)
        if not good.all_passed:
            continue
        failed = {f["id"] for f in wrong.failures}
        # Prefer a distinct failing example on each side where possible.
        bad_tests = [t for t in tests if t["id"] in failed]
        other = [t for t in tests if t["id"] not in failed]
        split = bad_tests[: max(1, len(bad_tests) // 2)] + other[: len(other) // 2]
        held = [t for t in tests if t not in split]
        if not held:
            continue
        sid = path.parent.name
        return Bug(
            f"condefects/{task}/{sid}",
            "solve",
            faulty,
            correct,
            split,
            held,
            source="condefects",
            notes=[url, f"https://github.com/appmlk/ConDefects/tree/{REVISION}/Code/{task}/Python/{sid}"],
        )
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "data/condefects")
    args = ap.parse_args()
    rev = subprocess.check_output(["git", "-C", str(args.src), "rev-parse", "HEAD"], text=True).strip()
    if rev != REVISION:
        ap.error("unexpected upstream commit")
    args.cache.mkdir(parents=True, exist_ok=True)
    difficulties = {
        k: int(v)
        for k, v in (l.split() for l in (args.src / "difficulty.txt").read_text().splitlines())
        if v.lstrip("-").isdigit()
    }
    bands = [(0, 399, 60), (400, 1199, 30), (1200, 100000, 10)]
    selected = []

    def one(task):
        cache_key = args.cache / (task + ".selected-v1.json")
        if cache_key.exists():
            data = json.loads(cache_key.read_text(encoding="utf-8"))
            return Bug(**data) if data else None
        b = select_task(task, args.src, args.cache)
        cache_key.write_text(b.to_json() if b else "null", encoding="utf-8")
        return b

    for lo, hi, n in bands:
        candidates = sorted(
            k
            for k, v in difficulties.items()
            if lo <= v <= hi
            and k.startswith("abc")
            and (args.src / "Code" / k / "Python").is_dir()
            and k not in ("abc223_a", "abc223_b", "abc225_a")
        )
        random.Random(403 + lo).shuffle(candidates)
        count = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            for offset in range(0, len(candidates), 4):
                for bug in pool.map(one, candidates[offset : offset + 4]):
                    if bug and count < n:
                        selected.append(bug)
                        count += 1
                        print(lo, count, bug.id, flush=True)
                if count == n:
                    break
        if count < n:
            raise RuntimeError(f"Only {count} eligible tasks in difficulty band {lo}-{hi}")
    args.out.mkdir(parents=True, exist_ok=True)
    blob = "".join(b.to_json() + "\n" for b in selected).encode()
    (args.out / "bugs.jsonl").write_bytes(blob)
    (args.out / "manifest.json").write_text(
        json.dumps(
            dict(
                commit=rev,
                seed=403,
                bands=bands,
                sha256=hashlib.sha256(blob).hexdigest(),
                sample="One submission per task, eligible reference passes all examples, faulty submission fails a visible example.",
                source="ConDefects CC BY-SA 4.0, adapted to callable functions. Public AtCoder sample I/O; source URLs in each row.",
                tasks=[dict(bug=b.id, difficulty=difficulties[b.id.split("/")[1]]) for b in selected],
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
