"""Runs inside a separate, isolated Python process (python -I).

Usage: python -I harness.py <candidate_dir> <module_name> <func_name> <tests.json> <out.json> <per_test_timeout_s>

Imports the candidate module, runs every test case with a per-test timeout and
writes one result per test to <out.json>. Candidate code is untrusted, so it
never shares a process with the experiment runner.
"""
import importlib
import json
import math
import signal
import sys
import types

try:
    import resource
except ImportError:  # Windows uses parent-enforced case timeouts.
    resource = None


def timer(seconds):
    if hasattr(signal, "setitimer"):
        signal.setitimer(signal.ITIMER_REAL, seconds)


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def _plain(value):
    """Make generators/tuples/sets comparable with JSON test data."""
    if isinstance(value, types.GeneratorType):
        value = list(value)
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(v) for v in value), key=repr)
    return value


def equal(got, expected):
    if isinstance(got, bool) or isinstance(expected, bool):
        return got == expected
    if isinstance(got, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(got, expected, rel_tol=1e-6, abs_tol=1e-9)
    if isinstance(got, list) and isinstance(expected, list):
        return len(got) == len(expected) and all(equal(g, e) for g, e in zip(got, expected))
    return got == expected


def main():
    cand_dir, module, func, tests_path, out_path, per_test = sys.argv[1:7]
    per_test = float(per_test)
    # 1 GiB address space, no core dumps.
    try:
        if resource is not None:
            resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ValueError, OSError):
        pass
    sys.setrecursionlimit(5000)
    sys.path.insert(0, cand_dir)
    with open(tests_path) as f:
        tests = json.load(f)

    report = {"import_error": None, "results": []}
    try:
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, _alarm)
        timer(per_test * 2)
        mod = importlib.import_module(module)
        timer(0)
        fn = getattr(mod, func)
    except BaseException as err:  # noqa: BLE001 - we want every failure mode
        timer(0)
        report["import_error"] = f"{type(err).__name__}: {err}"[:300]
        with open(out_path, "w") as f:
            json.dump(report, f)
        return

    for case in tests:
        args = case["input"] if isinstance(case["input"], list) else [case["input"]]
        res = {"id": case["id"], "passed": False, "error": None, "got": None}
        try:
            timer(per_test)
            got = _plain(fn(*json.loads(json.dumps(args))))
            timer(0)
            if "abs_tol" in case and isinstance(got, (int, float)):
                res["passed"] = math.isclose(got, case["output"], rel_tol=0, abs_tol=case["abs_tol"])
            else:
                res["passed"] = equal(got, case["output"])
            res["got"] = repr(got)[:200]
        except _Timeout:
            res["error"] = "Timeout"
        except BaseException as err:  # noqa: BLE001
            timer(0)
            res["error"] = f"{type(err).__name__}: {err}"[:200]
        report["results"].append(res)

    with open(out_path, "w") as f:
        json.dump(report, f)


if __name__ == "__main__":
    main()
