"""Run a tool script with a raster stand-in for shapely (ONLY for a sandbox where shapely cannot be installed).

Usage (from the project root):  python tools/sandbox_standin/run_script.py tools/make_block_examples.py [arguments]
The stand-in needs numpy, scipy, matplotlib and contourpy. Its cells are 0.1 mm, so areas and
positions are coarse (a few older turning tests and the golden-file test differ by 0.05-0.1 mm
there and fail only because of that). It is a development aid, not part of the product; on a
machine with shapely use `python -m unittest` instead.
"""

import sys
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE))

import fake_region  # noqa: E402

sys.modules["wop.core.region"] = fake_region
sys.modules["shapely"] = types.ModuleType("shapely")
import wop.core  # noqa: E402

wop.core.region = fake_region
import wop.core.constants as constants  # noqa: E402

constants.ROUGH_LINE_HALF_WIDTH_MM = 0.1  # the cells are 0.1 mm: thinner lines would vanish

import runpy  # noqa: E402

script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name="__main__")
