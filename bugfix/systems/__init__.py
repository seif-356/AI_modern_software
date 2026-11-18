from .base import RepairResult
from .multi import run_s2, run_s2r
from .single import run_s0, run_s1

SYSTEMS = {"s0": run_s0, "s1": run_s1, "s2": run_s2, "s2r": run_s2r}

__all__ = ["SYSTEMS", "RepairResult", "run_s0", "run_s1", "run_s2", "run_s2r"]
