"""Report the CRAP score of every function.

CRAP = complexity^2 * (1 - coverage)^3 + complexity

It punishes code that is both convoluted and untested, and forgives code that
is one or the other: a simple function needs little testing to score well, and
a complex one can still pass if it is thoroughly covered.

Per-function coverage is derived by intersecting each function's line range
(from radon) with the lines coverage.py recorded as executed.
"""

import json
import subprocess
import sys
from pathlib import Path

THRESHOLD = 6.0


def crap(complexity: int, coverage: float) -> float:
    return complexity**2 * (1.0 - coverage) ** 3 + complexity


def blocks(target: str) -> list[dict]:
    raw = subprocess.run(
        [sys.executable, "-m", "radon", "cc", "-j", target],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    found = []
    for path, items in json.loads(raw).items():
        if isinstance(items, dict) and items.get("error"):
            continue
        for item in items:
            found.append({**item, "path": path})
    return found


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "src"
    coverage_path = Path("coverage.json")
    if not coverage_path.exists():
        print("run: pytest --cov --cov-report=json", file=sys.stderr)
        return 2
    data = json.loads(coverage_path.read_text())["files"]

    rows = []
    for block in blocks(target):
        file_data = data.get(block["path"])
        if file_data is None:
            continue
        executed = set(file_data["executed_lines"])
        missing = set(file_data["missing_lines"])
        span = set(range(block["lineno"], block["endline"] + 1))
        run, gone = len(span & executed), len(span & missing)
        if run + gone == 0:
            continue
        coverage = run / (run + gone)
        score = crap(block["complexity"], coverage)
        rows.append((score, block["path"], block["name"], block["complexity"], coverage))

    rows.sort(reverse=True)
    over = [r for r in rows if r[0] >= THRESHOLD]
    print(f"{'CRAP':>7}  {'cplx':>4}  {'cov':>6}  location")
    for score, path, name, complexity, coverage in rows[:15]:
        flag = "!!" if score >= THRESHOLD else "  "
        print(f"{score:7.2f}  {complexity:4d}  {coverage:6.1%}  {flag} {path}:{name}")
    print(f"\n{len(rows)} blocks, {len(over)} at or above CRAP {THRESHOLD}")
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
