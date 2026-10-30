"""Team coding style (BUILD_BRIEF §0.5): no comprehensions, generator expressions, zip or enumerate."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "aimargin"
BANNED_NODES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
BANNED_CALLS = {"zip", "enumerate"}


def test_no_banned_constructs():
    problems = []
    files = sorted(SRC.rglob("*.py"))
    for i in range(len(files)):
        tree = ast.parse(files[i].read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, BANNED_NODES):
                problems.append(f"{files[i].relative_to(SRC)}:{node.lineno} {type(node).__name__}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
                problems.append(f"{files[i].relative_to(SRC)}:{node.lineno} {node.func.id}()")
    assert problems == [], "style violations:\n" + "\n".join(problems)
