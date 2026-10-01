"""Stdlib-only line coverage for dagp_ref (no third-party coverage.py needed).
Usage: python3 coverage_check.py [--min 95]"""
import ast
import os
import sys
import threading
import types
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dagp_ref")
hit: dict[str, set] = {}


def tracer(frame, event, arg):
    fn = frame.f_code.co_filename
    if not fn.startswith(ROOT):
        return None
    hit.setdefault(fn, set()).add(frame.f_lineno)

    def local(frame, event, arg):
        if event == "line":
            hit[fn].add(frame.f_lineno)
        return local
    return local


def executable_lines(tree: ast.AST) -> set:
    """Statement start lines (AST based, so multi-line signatures/expressions count once;
    bare docstrings are excluded)."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.stmt):
            if isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant) \
                    and isinstance(n.value.value, str):
                continue
            out.add(n.lineno)
    return out


def main() -> int:
    floor = 0
    if "--min" in sys.argv:
        floor = int(sys.argv[sys.argv.index("--min") + 1])
    sys.path.insert(0, os.path.dirname(ROOT))
    sys.settrace(tracer)
    threading.settrace(tracer)
    suite = unittest.defaultTestLoader.discover(os.path.join(os.path.dirname(ROOT), "tests"),
                                                top_level_dir=os.path.dirname(ROOT))
    res = unittest.TextTestRunner(stream=open(os.devnull, "w")).run(suite)
    sys.settrace(None)
    total = covered = 0
    print(f"tests run: {res.testsRun}, failures: {len(res.failures)}, errors: {len(res.errors)}")
    for f in sorted(os.listdir(ROOT)):
        if not f.endswith(".py") or f == "__init__.py":
            continue
        path = os.path.join(ROOT, f)
        ex = executable_lines(ast.parse(open(path).read()))
        miss = sorted(ex - hit.get(path, set()))
        total += len(ex)
        covered += len(ex) - len(miss)
        pct = 100 * (len(ex) - len(miss)) // max(1, len(ex))
        print(f"{f:18s} {pct:3d}%  missing: {miss if miss else '-'}")
    pct = 100 * covered // total
    print(f"TOTAL {pct}% ({covered}/{total} lines)")
    return 0 if res.wasSuccessful() and pct >= floor else 1


if __name__ == "__main__":
    sys.exit(main())
