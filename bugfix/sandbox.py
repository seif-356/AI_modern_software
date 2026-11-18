"""Execute candidate programs against test cases in an isolated subprocess."""
from __future__ import annotations

import json
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
        (cand / "candidate.py").write_text(code)
        for name, text in (support_files or {}).items():
            (cand / name).write_text(text)
        tests_path, out_path = work / "tests.json", work / "out.json"
        tests_path.write_text(json.dumps(tests))
        overall = per_test_timeout * len(tests) + 10
        timed_out = False
        try:
            subprocess.run(
                [sys.executable, "-I", str(HARNESS), str(cand), "candidate", func_name,
                 str(tests_path), str(out_path), str(per_test_timeout)],
                cwd=cand, timeout=overall, capture_output=True,
            )
        except subprocess.TimeoutExpired:
            timed_out = True
        if not out_path.exists():
            return RunReport(passed=0, total=len(tests), import_error="Crash: no result (killed or timed out)",
                             timed_out=timed_out)
        report = json.loads(out_path.read_text())
        if report["import_error"]:
            return RunReport(passed=0, total=len(tests), import_error=report["import_error"])
        by_id = {t["id"]: t for t in tests}
        failures = [
            {"id": r["id"], "input": by_id[r["id"]]["input"], "expected": by_id[r["id"]]["output"],
             "got": r["got"], "error": r["error"]}
            for r in report["results"] if not r["passed"]
        ]
        passed = sum(r["passed"] for r in report["results"])
        return RunReport(passed=passed, total=len(tests), failures=failures, timed_out=timed_out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
