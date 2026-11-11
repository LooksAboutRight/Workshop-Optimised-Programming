"""The wanted plan of a roughing block: the region to remove and its lines (open lines at the depth of cut, pocket lines at the plunge depth of cut).

Tool-free: it needs the stock as chains (`material.py`), the contour with the wall at its end, the finishing allowance, and the
two depths of cut. There is no thin-stock rule (requirement B23, dropped): what is to be removed
is removed, and a stretch is only dropped when it is shorter than the sliver limit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..passes import levels
from ..constants import GEOMETRY_TOLERANCE_MM
from ..geometry import LineSegment, Segment
from ..geometry.chains import Loop, box_of, loops_box
from .pockets import make_lines
from .wanted_lines import LineDirection, WantedPlan, front_floor, removal_loops


@dataclass(frozen=True)
class WantedJob:
    """What the wanted plan of a block needs besides the material."""
    path: list[Segment]  # the contour, from the front to the chuck, with its last wall run on to the material
    outside: bool
    direction: LineDirection
    allowance: float  # the finishing allowance
    depth_of_cut: float
    plunge_depth: float | None  # the depth of cut of a pocket line; None: the depth of cut
    outer: float  # the radius beyond the material and the contour where the area to remove is closed
    start_z: float  # the front of the block's material
    chuck_z: float | None = None  # the clamping plane: a wall
    grid_from: tuple[float, float] | None = None  # the radius and the front (Z) of the raw bar, where the levels are laid out from; None: the material


def wanted_plan(stock: list[Loop], job: WantedJob, cleaned_stock: Callable[[], list[Loop]] | None = None) -> WantedPlan:
    """The region to remove and the lines through it, level by level from the free side of the material towards the part. The levels are
    laid out from the raw bar (`grid_from`, the user's decision 2026-10-22): the same block gets the same levels whatever earlier blocks cut;
    the levels outside the material that stands now give no line. `cleaned_stock`: the material opened and simplified, tried when the
    exact loops cannot be joined."""

    path, outside, direction, allowance, start_z, grid_from = job.path, job.outside, job.direction, job.allowance, job.start_z, job.grid_from
    depth_of_cut, plunge_depth = job.depth_of_cut, job.plunge_depth
    sign = 1 if outside else -1
    tol = GEOMETRY_TOLERANCE_MM
    loops = removal_loops(path, stock, outside, allowance, job.outer, start_z, cleaned_stock)
    if not loops:
        return WantedPlan((), ())
    x_low, z_low, x_high, _z_high = loops_box(loops)
    path_low = min(box_of(s)[0] for s in path)  # the lowest and the highest radius of the contour (an arc counts with its extreme points)
    path_high = max(box_of(s)[2] for s in path)
    if direction is LineDirection.ALONG_Z:
        axis, free_side = 0, sign
        surface = x_high if outside else x_low
        deepest = path_low if outside else path_high
        reach = max(deepest + sign * allowance, x_low) if outside else min(deepest + sign * allowance, x_high)
        critical = [s.start.x + sign * allowance for s in path if isinstance(s, LineSegment) and abs(s.start.z - s.end.z) > tol and abs(s.start.x - s.end.x) <= tol]
        floor = front_floor(path, outside, allowance, start_z)
        if floor is not None:
            critical.append(floor)  # the floor in front of the contour: a line runs on it, as on a flat of the contour
            reach = min(reach, floor) if outside else max(reach, floor)  # a face down to the axis: its allowance is in Z, the lines go down to the floor
        deeper = sign * (surface - reach) > tol
    else:
        axis, free_side = 1, 1
        surface = start_z
        end_z = min(min(s.start.z, s.end.z) for s in path)
        reach = max(end_z + allowance, z_low)
        critical = [s.start.z + allowance for s in path if isinstance(s, LineSegment) and abs(s.start.x - s.end.x) > tol and abs(s.start.z - s.end.z) <= tol]
        deeper = surface - reach > tol
    origin = surface
    if direction is LineDirection.ALONG_Z and grid_from is not None:  # the same levels for the same block, whatever earlier blocks cut:
        radius, front = grid_from
        origin = radius if sign * (radius - surface) > tol else surface  # from the raw bar ...
        reach = deepest + sign * allowance  # ... down to the deepest point of the contour, not to the bottom of the material that stands now
        critical = [level for level in critical if level != floor]
        floor = front_floor(path, outside, allowance, max(start_z, front))  # the floor in front of the face of the raw bar (not of what stands now)
        if floor is not None:
            critical.append(floor)
            reach = min(reach, floor) if outside else max(reach, floor)
        deeper = sign * (surface - reach) > tol
    if direction is LineDirection.ALONG_X and grid_from is not None:  # the same for lines across X: from the front of the raw bar ...
        origin = max(grid_from[1], surface)
        reach = end_z + allowance  # ... to the end of the contour, not to the back of the material that stands now
        deeper = surface - reach > tol
    positions = [p for p in levels(origin, reach, critical, depth_of_cut) if sign * (surface - p) > tol] if deeper else []
    lines = make_lines(loops, stock, positions, critical, surface, axis, free_side, depth_of_cut if plunge_depth is None else plunge_depth, job.chuck_z)
    return WantedPlan(tuple(loops), tuple(lines))
