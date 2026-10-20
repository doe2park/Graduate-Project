#!/usr/bin/env python3
"""Run every unit test (no browsers, no GPU, no network) and print one summary.

    python3 scripts/run_all_tests.py

Runs each tests/*.test.cjs and tests/*.test.mjs with node, then the Python unittest suite
(tests/test_*.py) with the interpreter running this script. THREE_MODULE defaults to
tools/node_modules/three when present (needed by the two render-tier .mjs tests).
Headless browser smokes (tests/*-smoke.cjs) are NOT run here. Exit code 1 if anything fails.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"


def python_exe():
    """First interpreter that has numpy + requests (the Gaussian venv has no requests; a bare Homebrew python3,
    which VS Code's login shell may pick, has neither). Falls back to the one running this script."""
    import shutil
    candidates = [sys.executable, str(Path.home() / "miniforge3/bin/python3"), shutil.which("python3.11"),
                  "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3", shutil.which("python3")]
    for exe in candidates:
        if exe and Path(exe).exists() and subprocess.run(
                [exe, "-c", "import numpy, requests"], capture_output=True).returncode == 0:
            return exe
    return sys.executable


def run(label, cmd, env=None):
    t = time.time()
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    dt = time.time() - t
    ok = r.returncode == 0
    print(f"{'PASS' if ok else 'FAIL'}  {label}  ({dt:.1f}s)", flush=True)
    if not ok:
        tail = (r.stdout + r.stderr).strip().splitlines()[-25:]
        print("\n".join("      " + line for line in tail), flush=True)
    return ok


def main():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    three = ROOT / "tools" / "node_modules" / "three" / "build" / "three.module.js"
    if "THREE_MODULE" not in env and three.exists():
        env["THREE_MODULE"] = str(three)
    results = []
    for f in sorted(list(TESTS.glob("*.test.cjs")) + list(TESTS.glob("*.test.mjs"))):
        results.append(run(f"node {f.relative_to(ROOT)}", ["node", str(f)], env))
    results.append(run("python unittest tests/test_*.py", [python_exe(), "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], env))
    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} test groups passed" + ("" if not failed else f", {failed} FAILED"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
