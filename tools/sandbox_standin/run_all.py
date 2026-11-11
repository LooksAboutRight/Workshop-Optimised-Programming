"""Run every test module under the raster stand-in, several at a time (ONLY for a sandbox without shapely).

Usage (project root):  python tools/sandbox_standin/run_all.py [jobs] [module ...]
Each module runs in its own process; the last line of its output is collected into logs/standin/summary.txt (the
logs are in the same folder). Modules that need big bars (test_user_projects) are left out unless named. A development aid, not part of the product.
"""

from __future__ import annotations

import concurrent.futures
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RUNNER = ROOT / "tools" / "sandbox_standin" / "run_tests.py"
LOGS = ROOT / "logs" / "standin"
LEFT_OUT = {"test_user_projects"}
TIME_LIMIT_S = 3000


def run(module: str) -> str:
    log = LOGS / f"{module}.log"
    try:
        done = subprocess.run([sys.executable, str(RUNNER), f"tests.{module}"], cwd=ROOT, capture_output=True, text=True, timeout=TIME_LIMIT_S)
        text = done.stdout + done.stderr
    except subprocess.TimeoutExpired:
        text = "TIMEOUT"
    log.write_text(text, encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    return f"{module}: {lines[-1] if lines else 'no output'}"


def main(argv: list[str]) -> None:
    jobs = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 2
    names = [a for a in argv[1:] if not a.isdigit()]
    modules = names or sorted(p.stem for p in (ROOT / "tests").glob("test_*.py") if p.stem not in LEFT_OUT)
    LOGS.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        results = list(pool.map(run, modules))
    (LOGS / "summary.txt").write_text("\n".join(results) + "\n", encoding="utf-8")
    print("\n".join(line for line in results if not line.endswith("OK") and "OK (" not in line) or "all OK")


if __name__ == "__main__":
    main(sys.argv)
