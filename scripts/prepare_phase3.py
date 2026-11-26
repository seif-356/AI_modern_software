"""Rebuild the fixed matched panel from the Phase 2 data and pinned ConDefects checkout."""
import argparse
import ast
import dataclasses
import hashlib
import io
import itertools
import json
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bugfix.bugs import Bug, load_bugs
from bugfix.sandbox import run_tests

REVISION = "43f0834a82c5e3bc4516c079fe7765f63b1a15cd"
QUIX = ["gcd", "is_valid_parenthesization", "max_sublist_sum"]
# Fixed before inference. Each contest case uses an independent task-level oracle.
TASKS = [
    ("abc223_a", "45813374", ["100", "101", "0", "99"], ["200", "201", "1", "500"]),
    ("abc223_b", "53513467", ["ba", "aa", "cab"], ["za", "baca", "zz", "a"]),
    ("abc225_a", "44428733", ["aaa", "abc", "aab"], ["zzz", "aba", "xyz", "bba"]),
]


def expected(task, text):
    if task == "abc223_a":
        return "Yes" if int(text) > 0 and int(text) % 100 == 0 else "No"
    if task == "abc223_b":
        rotations = [text[i:] + text[:i] for i in range(len(text))]
        return min(rotations) + "\n" + max(rotations)
    assert task == "abc225_a"
    return str(len(set(itertools.permutations(text))))


class FunctionAdapter(ast.NodeTransformer):
    """Adapt the selected scripts' one input() and plain single-argument prints."""
    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == "input":
            assert not node.args and not node.keywords
            return ast.Name(id="text", ctx=ast.Load())
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            assert len(node.args) == 1 and not node.keywords
            return ast.Call(ast.Attribute(ast.Name(id="output", ctx=ast.Load()), "append", ast.Load()),
                            [ast.Call(ast.Name(id="str", ctx=ast.Load()), node.args, [])], [])
        return node


def adapt(source):
    body = FunctionAdapter().visit(ast.parse(source)).body
    wrapper = ast.parse("def solve(text):\n    output = []\n    return '\\n'.join(output)\n")
    wrapper.body[0].body[1:1] = body
    return ast.unparse(ast.fix_missing_locations(wrapper)) + "\n"


def renamed(bug):
    # This restricted panel contains no reflection, keyword invocations or
    # shadowed imports. Preserve whitespace, comments, prose and string literals.
    names = []
    for code in (bug.buggy_code, bug.reference_code):
        for node in ast.walk(ast.parse(code)):
            name = None
            if isinstance(node, ast.FunctionDef):
                name = node.name
            elif isinstance(node, ast.arg):
                name = node.arg
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                name = node.id
            if name and name not in names:
                names.append(name)
    table = {name: f"v{i}" for i, name in enumerate(names)}
    def rewrite(code):
        tokens = tokenize.generate_tokens(io.StringIO(code).readline)
        return tokenize.untokenize(t._replace(string=table[t.string])
                                   if t.type == tokenize.NAME and t.string in table else t for t in tokens)
    return dataclasses.replace(bug, id=bug.id + "/renamed", func_name=table[bug.func_name],
                               buggy_code=rewrite(bug.buggy_code), reference_code=rewrite(bug.reference_code))


def checked(bug):
    tests = bug.visible_tests + bug.heldout_tests
    assert run_tests(bug.reference_code, bug.func_name, tests).all_passed, bug.id
    bad = run_tests(bug.buggy_code, bug.func_name, tests)
    failures = {f["id"] for f in bad.failures}
    assert failures.intersection(t["id"] for t in bug.visible_tests), bug.id
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "data/phase3")
    args = parser.parse_args()
    revision = subprocess.check_output(["git", "-C", str(args.src), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        parser.error(f"expected ConDefects at {REVISION}, got {revision}")
    cases = load_bugs(ROOT / "data/quixbugs/bugs.jsonl", ids=["quixbugs/" + n for n in QUIX])
    sources = {}
    for task, sid, visible, held in TASKS:
        stem = f"Code/{task}/Python/{sid}"
        folder = args.src / stem
        def read(name):
            return (folder / (name + "Version.py")).read_text(encoding="utf-8-sig")
        tests = [{"id": i, "input": [v], "output": expected(task, v)} for i, v in enumerate(visible + held)]
        bug_id = f"condefects/{task}/{sid}"
        cases.append(Bug(bug_id, "solve", adapt(read("faulty")), adapt(read("correct")),
                         tests[:len(visible)], tests[len(visible):], source="condefects"))
        sources[bug_id] = f"https://github.com/appmlk/ConDefects/tree/{revision}/{stem}"
    rows = []
    for bug in cases:
        twin = renamed(bug)
        assert checked(bug) == checked(twin), bug.id
        rows.extend([bug, twin])
    args.out.mkdir(parents=True, exist_ok=True)
    payload = "".join(b.to_json() + "\n" for b in rows).encode("utf-8")
    (args.out / "bugs.jsonl").write_bytes(payload)
    (args.out / "manifest.json").write_text(json.dumps({
        "sha256": hashlib.sha256(payload).hexdigest(), "upstream_commit": revision,
        "selection": "Purposive six-bug panel, three per dataset. Every original has an identifier-renamed twin.",
        "inputs": "QuixBugs uses its archived split. Contest inputs and expected outputs are study-authored.",
        "adaptation": "One input line becomes a positional string. Captured print lines become the returned string.",
        "license": "ConDefects adaptations: CC BY-SA 4.0. QuixBugs adaptations: MIT (see ../quixbugs/QUIXBUGS_LICENSE).",
        "sources": sources, "ids": [b.id for b in rows]}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
