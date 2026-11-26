"""Execute candidate programs against test cases in an isolated subprocess."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HARNESS = Path(__file__).with_name("harness.py")


@dataclass
class RunReport:
    passed: int
    total: int
    import_error: str | None = None
    failures: list[dict] = field(default_factory=list)  # {id, input, expected, got, error}
    timed_out: bool = False

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.passed == self.total and not self.import_error

    def error_types(self) -> set[str]:
        types = set()
        if self.import_error:
            types.add(self.import_error.split(":")[0])
        for f in self.failures:
            if f.get("error"):
                types.add(f["error"].split(":")[0])
        return types

    def feedback(self, limit: int = 3) -> str:
        """Short, human-readable failure summary handed back to the model."""
        if self.import_error:
            return f"The program failed to load: {self.import_error}"
        lines = [f"{self.passed}/{self.total} visible tests pass."]
        for f in self.failures[:limit]:
            outcome = f["error"] or f"returned {f['got']}"
            lines.append(f"- input {json.dumps(f['input'])}: expected {json.dumps(f['expected'])}, {outcome}")
        return "\n".join(lines)


def run_tests(code: str, func_name: str, tests: list[dict], support_files: dict[str, str] | None = None,
              per_test_timeout: float = 2.0) -> RunReport:
    """Run `func_name` from `code` on tests [{id, input, output}]."""
    if not tests:
        return RunReport(passed=0, total=0)
    work = Path(tempfile.mkdtemp(prefix="bugfix_"))
    try:
        cand = work / "cand"
        cand.mkdir()
        (cand / "candidate.py").write_text(code, encoding="utf-8")
        for name, text in (support_files or {}).items():
            (cand / name).write_text(text)
        tests_path, out_path = work / "tests.json", work / "out.json"
        # Windows has no SIGALRM. A separate process per case prevents a loop
        # from consuming the remaining cases' time allowance.
        batches = ([case] for case in tests) if os.name == "nt" else [tests]
        child_env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH")
                     if k in os.environ}
        timed_out = False
        results = []
        for batch in batches:
            tests_path.write_text(json.dumps(batch), encoding="utf-8")
            out_path.unlink(missing_ok=True)
            timeout = per_test_timeout + 0.5 if os.name == "nt" else per_test_timeout * len(batch) + 10
            try:
                subprocess.run(
                    [sys.executable, "-I", str(HARNESS), str(cand), "candidate", func_name,
                     str(tests_path), str(out_path), str(per_test_timeout)],
                    cwd=cand, timeout=timeout, env=child_env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except subprocess.TimeoutExpired:
                timed_out = True
                results.extend({"id": t["id"], "passed": False, "got": None, "error": "Timeout"} for t in batch)
                continue
            if not out_path.exists():
                return RunReport(0, len(tests), import_error="Crash: no result")
            report = json.loads(out_path.read_text())
            if report["import_error"]:
                return RunReport(0, len(tests), import_error=report["import_error"])
            results.extend(report["results"])
        by_id = {t["id"]: t for t in tests}
        failures = [
            {"id": r["id"], "input": by_id[r["id"]]["input"], "expected": by_id[r["id"]]["output"],
             "got": r["got"], "error": r["error"]}
            for r in results if not r["passed"]
        ]
        passed = sum(r["passed"] for r in results)
        return RunReport(passed=passed, total=len(tests), failures=failures, timed_out=timed_out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
