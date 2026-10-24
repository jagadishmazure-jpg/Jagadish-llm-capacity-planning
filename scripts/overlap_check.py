"""8-word overlap check: fail if any run of 8 consecutive words in the repo's text also appears in a
source text (for example a talk transcript). The source itself is never committed.

python scripts/overlap_check.py /path/to/source.txt
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

N = 8
WORD = re.compile(r"[a-z0-9']+")


def grams(text: str, n: int = N) -> set[tuple[str, ...]]:
    w = WORD.findall(text.lower())
    return {tuple(w[i : i + n]) for i in range(len(w) - n + 1)}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    src = grams(Path(argv[1]).read_text(errors="ignore"))
    root = Path(__file__).resolve().parents[1]
    files = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard"], capture_output=True, text=True, check=True
    ).stdout.split()
    hits = 0
    for f in files:
        if not re.search(r"\.(md|py|txt|json|toml|ya?ml)$", f):
            continue
        for g in grams((root / f).read_text(errors="ignore")) & src:
            hits += 1
            print(f"{f}: {' '.join(g)}")
    print(f"8-word overlaps with source: {hits}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
