"""Bug records: buggy code, reference fix and the visible / held-out test split."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Bug:
    id: str
    func_name: str
    buggy_code: str
    reference_code: str
    visible_tests: list[dict]      # given to every system
    heldout_tests: list[dict]      # used only by the evaluator
    source: str = "quixbugs"
    support_files: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def load_bugs(path: str | Path, ids: list[str] | None = None, limit: int | None = None) -> list[Bug]:
    bugs = [Bug(**json.loads(line)) for line in Path(path).read_text().splitlines() if line.strip()]
    if ids:
        wanted = set(ids)
        bugs = [b for b in bugs if b.id in wanted]
    return bugs[:limit] if limit else bugs


def toy_bug() -> Bug:
    """A tiny bug used by unit tests and the API example (not part of any dataset)."""
    return Bug(
        id="toy_max",
        func_name="find_max",
        buggy_code="def find_max(xs):\n    best = xs[0]\n    for x in xs:\n        if x < best:\n            best = x\n    return best\n",
        reference_code="def find_max(xs):\n    best = xs[0]\n    for x in xs:\n        if x > best:\n            best = x\n    return best\n",
        visible_tests=[{"id": 0, "input": [[1, 3, 2]], "output": 3}, {"id": 1, "input": [[5]], "output": 5}],
        heldout_tests=[{"id": 2, "input": [[-4, -2, -9]], "output": -2}, {"id": 3, "input": [[2, 9, 9, 1]], "output": 9}],
        source="toy",
    )
