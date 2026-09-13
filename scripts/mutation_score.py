"""Report the mutation score and fail below a floor.

`mutmut run` exits zero whether or not mutants survived, so on its own it
reports rather than gates. This turns it into a gate, reading the stats file
mutmut writes for exactly this purpose.

The floor is deliberately below 100%: a residue of mutants is *equivalent* --
`"utf-8"` to `"UTF-8"`, an explicit `int.from_bytes(..., "big")` to the default
that already means big-endian, `range(lo, hi + 1, 3)` to `hi + 2` when the step
makes them the same sequence. No test can kill those, and writing one that
appeared to would be testing the mutation tool rather than the code.
"""

import json
import subprocess
import sys
from pathlib import Path

FLOOR = 0.80
STATS = Path("mutants/mutmut-cicd-stats.json")


def main() -> int:
    subprocess.run(
        [sys.executable, "-m", "mutmut", "export-cicd-stats"],
        capture_output=True,
        text=True,
        check=False,
    )
    if not STATS.exists():
        print("no mutation stats; run `mutmut run` first", file=sys.stderr)
        return 2

    stats = json.loads(STATS.read_text())
    killed = stats["killed"] + stats["timeout"]
    survived = stats["survived"]
    total = killed + survived
    if total == 0:
        print("no mutants were run", file=sys.stderr)
        return 2

    score = killed / total
    print(f"mutation score: {score:.1%}  ({killed} killed, {survived} survived)")
    if score < FLOOR:
        print(f"FAIL: below the {FLOOR:.0%} floor", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
