"""Turn a model reply into a candidate program and describe what it changed."""
from __future__ import annotations

import ast
import re

_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(reply: str) -> str:
    """Return the last fenced code block, or the whole reply if there is none."""
    blocks = _FENCE.findall(reply or "")
    code = blocks[-1] if blocks else (reply or "")
    return code.strip("\n") + "\n"


def parses(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def normalise(code: str) -> str:
    """Code with comments/formatting removed, for 'unchanged patch' detection."""
    try:
        return ast.dump(ast.parse(code))
    except SyntaxError:
        return re.sub(r"\s+", " ", code).strip()


def defined_functions(code: str) -> dict[str, list[str]]:
    """Top-level function name -> argument names."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    return {
        n.name: [a.arg for a in n.args.args]
        for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def imported_modules(code: str) -> set[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    return mods
