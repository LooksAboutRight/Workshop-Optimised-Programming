"""Run the tests in several processes at once (the whole suite in about a minute instead of five).

Usage (project root):
    python tools/run_tests.py                     every test, on 8 processes
    python tools/run_tests.py -j 4                on 4 processes
    python tools/run_tests.py tests.test_verify   only these test modules
    python tools/run_tests.py --fresh             every module in a new process (slower: finds a module that only passes
                                                  because another one loaded something first)

First every example and test project is planned, each in a process of its own; then every process takes one test module after the
other. A plan made through `tests.helpers.planned` is shared by all processes of the run (files in a temporary folder), so a project
is planned once per run, as in one process. The modules that took longest in the last run start first (their times are kept in
`.test_times.json`, which git ignores); a new module counts as long. The output of a module is shown only when it fails. Standard
library only. `python -m unittest discover -s tests -t .` still runs everything in one process.
"""

from __future__ import annotations

import argparse
import io
import json
import multiprocessing
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.helpers import SHARED_PLANS_VARIABLE  # noqa: E402

TIMES_FILE = ROOT / ".test_times.json"  # seconds per test module in the last run: the longest start first
DEFAULT_PROCESSES = 8  # GUESS: more than this hardly helps (the longest module sets the end) and the PC stays usable
UNKNOWN_MODULE_SECONDS = 1e6  # a module with no time yet starts early (it may be long)
PROJECT_PATTERNS = ("examples/**/*.wop.json", "tests/data/projects/*.json")  # planned first, one per process
HASH_SEED = "0"  # the same in every process: a program pickles to the same bytes, which name its shared plan


def test_modules() -> list[str]:
    """The names of all test modules, `tests.test_*`."""
    return sorted(f"tests.{path.stem}" for path in (ROOT / "tests").glob("test_*.py"))


def project_files() -> list[Path]:
    return sorted({path for pattern in PROJECT_PATTERNS for path in ROOT.glob(pattern)})


def plan_project(path: Path) -> None:
    """Plan one project through `tests.helpers.planned`, so the test modules find the plan made."""
    from tests.helpers import planned
    from wop.adapters.project_files import load_project

    try:
        planned(load_project(path).program)
    except Exception:  # a project that does not plan: the tests that use it say so
        pass


def _start_worker() -> None:
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def run_module(name: str) -> dict:
    """Run one test module in this process; what happened, as plain data for the parent."""
    stream = io.StringIO()
    started = time.perf_counter()
    try:
        suite = unittest.defaultTestLoader.loadTestsFromName(name)
        result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
        problems = [(str(test), text) for test, text in result.failures + result.errors]
        counts = (result.testsRun, len(result.skipped), len(result.failures), len(result.errors))
    except Exception as error:  # the module does not even load
        problems, counts = [(name, f"{type(error).__name__}: {error}")], (0, 0, 0, 1)
    return {"name": name, "seconds": time.perf_counter() - started, "counts": counts, "problems": problems}


def _read_times() -> dict[str, float]:
    try:
        return json.loads(TIMES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_times(times: dict[str, float]) -> None:
    TIMES_FILE.write_text(json.dumps(times, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run the tests of WOP in several processes.")
    parser.add_argument("modules", nargs="*", help="test modules to run (default: all), for example tests.test_verify")
    parser.add_argument("-j", "--jobs", type=int, default=DEFAULT_PROCESSES, help=f"processes (default {DEFAULT_PROCESSES})")
    parser.add_argument("--fresh", action="store_true", help="every module in a new process (nothing is shared between modules)")
    arguments = parser.parse_args(argv)

    modules = arguments.modules or test_modules()
    times = _read_times()
    modules.sort(key=lambda name: -times.get(name, UNKNOWN_MODULE_SECONDS))
    processes = max(1, min(arguments.jobs, len(modules)))
    print(f"{len(modules)} test modules on {processes} processes", flush=True)

    started = time.perf_counter()
    results = []
    with tempfile.TemporaryDirectory(prefix="wop_test_plans_") as shared:
        os.environ[SHARED_PLANS_VARIABLE] = shared  # the processes are started with these
        os.environ["PYTHONHASHSEED"] = HASH_SEED
        with multiprocessing.Pool(processes, initializer=_start_worker, maxtasksperchild=1 if arguments.fresh else None) as pool:
            if not arguments.modules:
                pool.map(plan_project, project_files(), chunksize=1)
                print(f"projects planned in {time.perf_counter() - started:.0f} s", flush=True)
            for done in pool.imap_unordered(run_module, modules):
                results.append(done)
                tests, skipped, failures, errors = done["counts"]
                mark = "FAIL" if failures or errors else "ok  "
                print(f"{mark} {done['seconds']:6.1f} s  {done['name']} ({tests} tests)", flush=True)
    elapsed = time.perf_counter() - started

    for done in results:
        for test, text in done["problems"]:
            print(f"\n{'=' * 70}\n{test}\n{'-' * 70}\n{text}")
    totals = [sum(done["counts"][i] for done in results) for i in range(4)]
    times.update({done["name"]: round(done["seconds"], 2) for done in results})
    _write_times(times)
    slowest = sorted(results, key=lambda done: -done["seconds"])[:5]
    print("\nslowest: " + ", ".join(f"{done['name']} {done['seconds']:.0f} s" for done in slowest))
    print(f"ran {totals[0]} tests in {elapsed:.0f} s: {totals[2]} failures, {totals[3]} errors, {totals[1]} skipped")
    print("OK" if totals[2] == totals[3] == 0 else "FAILED")
    return 0 if totals[2] == totals[3] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
