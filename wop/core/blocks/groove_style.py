"""The styles of the grooving block: how the blade is moved to cut a groove.

A style decides ONLY the order and the depth of the plunges. It does not decide what is cut (that comes from the form of the block),
it does not know the tool body, the holder or the material, and it writes no G-code. The block turns every step of the style into
moves, skips the air above the material, retracts between the plunges, checks the tool at every position and reports what stays uncut.

A style is a function `plan(groove) -> list of steps`:
- `groove` is a `GrooveInput`: plain numbers (see its fields), all in mm.
- every `Plunge` says where the blade goes down: its tip Z, how deep (a radius) and, when wanted, a pass along the bottom. A plunge at
  a wall with an edge (chamfer or fillet) can cut the edge in the same move (`Plunge.edge`): the corner of the blade comes down along
  the edge and goes on straight down the wall, so the edge and the wall are one cut.
- an `EdgeCut` cuts the edge of a wall with the corner only, as far as `size_mm` (a large edge is cut in several steps).

The blade covers Z from the tip Z to the tip Z plus the blade width (`groove.blade_mm`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..constants import GEOMETRY_TOLERANCE_MM, MAX_STYLE_PLUNGES
from ..passes import pass_levels
from .groove_plan import finish_steps, rough_plunges
from .styles import STYLES, StyleInfo

GROOVING = "grooving"  # the block type these styles belong to
EDGE_HIGH = "high"  # the wall nearer the face (the higher Z, the right edge)
EDGE_LOW = "low"  # the wall nearer the chuck


@dataclass(frozen=True)
class GrooveInput:
    """What a grooving style gets. All lengths in mm. Z is absolute (behind the front face it is negative); X is a radius.

    Outside the groove is cut into the surface from above (the radius gets smaller while plunging), inside into the wall of a bore
    (the radius gets bigger). `surface_radius` and the radii of the bottom tell which: `bottom` is deeper than `surface` in the direction
    of the plunge.
    """

    blade_mm: float  # width of the cutting edge across Z
    wall_low_z: float  # the groove walls, as drawn: the lower Z (nearer the chuck) ...
    wall_high_z: float  # ... and the higher Z (nearer the face)
    rough_low_z: float  # the same walls for roughing: moved in by the finishing allowance (and by the skin a wall with an edge keeps)
    rough_high_z: float
    surface_radius: float  # the surface the blade enters (the plunge starts above it)
    rough_bottom_radius: float  # the depth of the roughing plunges (the final radius plus the finishing allowance)
    final_radius: float  # the depth of the finished groove
    one_sided_mm: float  # the most the blade may cut wide with air on one side (a wider cut bends the blade)
    peck_depth_mm: float | None  # the form's peck depth for roughing plunges; None: straight down. The block does the pecking itself
    finishing: bool  # True: the form asks for finishing plunges (a finishing allowance and the finishing pass are set)
    finish_stop_early_mm: float  # a finishing pass along the bottom stops this far before the other wall
    edge_high_mm: float = 0  # the size of the edge (chamfer or fillet) of the wall nearer the face; 0: none
    edge_low_mm: float = 0  # the same for the wall nearer the chuck
    relief_radius: float | None = None  # how deep the groove must be open when an edge is cut (None: no edge, or the groove is not deeper than that)
    relief_low_z: float | None = None  # the walls for the plunges that only open the groove for an edge (None: the roughing walls); they may reach
    relief_high_z: float | None = None  # past the wall nearer the chuck, so that the wall with the edge keeps its skin in a groove as wide as the blade
    through: bool = False  # the groove goes to the axis: it cuts the part off, so its first full-depth plunge must be at the wall of the part


@dataclass(frozen=True)
class Plunge:
    """One plunge of the blade.

    `z` is the tip Z of the blade (between `rough_low_z` and `rough_high_z - blade_mm`, or the walls for a finishing plunge).
    `radius` is how deep it goes (between the final radius and the surface). `finishing` marks a finishing plunge: it uses the
    finishing feed and speed and is not pecked. `sweep_to` (a tip Z, or None) makes the blade, at the bottom of this plunge, move
    along the bottom to that Z before it comes out. `edge` (EDGE_HIGH, EDGE_LOW or None): the plunge is at that wall and starts with the
    cut of its edge, in the same move.
    """

    z: float
    radius: float
    finishing: bool = False
    sweep_to: float | None = None
    edge: str | None = None


@dataclass(frozen=True)
class EdgeCut:
    """The blade corner cuts the edge of one wall alone: `side` is EDGE_HIGH or EDGE_LOW, `size_mm` how large (None: the whole edge of the
    form; a smaller size is one of the first passes of a large edge). The groove must be open at least as deep as the edge is large
    (`GrooveInput.relief_radius`) at that moment: the body of the blade stands in it."""

    side: str
    size_mm: float | None = None


class GrooveStyleError(ValueError):
    pass


def check_plunges(groove: GrooveInput, plunges: list[Plunge | EdgeCut], style: str) -> None:
    """The contract of a grooving style: every plunge stays inside the groove. Raises GrooveStyleError with the reason."""
    walls = [groove.wall_low_z, groove.rough_low_z] + ([] if groove.relief_low_z is None else [groove.relief_low_z])
    low = min(walls) - GEOMETRY_TOLERANCE_MM
    high = max(groove.wall_high_z, groove.rough_high_z) - groove.blade_mm + GEOMETRY_TOLERANCE_MM
    deep_low, deep_high = sorted((groove.final_radius, groove.surface_radius))
    deep_low, deep_high = deep_low - GEOMETRY_TOLERANCE_MM, deep_high + GEOMETRY_TOLERANCE_MM
    if not plunges:
        raise GrooveStyleError(f"style {style!r} made no plunge")
    if len(plunges) > MAX_STYLE_PLUNGES:
        raise GrooveStyleError(f"style {style!r} made {len(plunges)} plunges, the most for one block is {MAX_STYLE_PLUNGES}")
    for number, plunge in enumerate(plunges, start=1):
        where = f"style {style!r}, plunge {number}"
        if isinstance(plunge, EdgeCut):
            _check_edge(groove, plunge.side, plunge.size_mm, where)
            continue
        if not low <= plunge.z <= max(high, low + groove.blade_mm):
            raise GrooveStyleError(f"{where}: Z {plunge.z:g} is outside the groove")
        if not deep_low <= plunge.radius <= deep_high:
            raise GrooveStyleError(f"{where}: radius {plunge.radius:g} is not between the final radius and the surface")
        if plunge.sweep_to is not None and not low <= plunge.sweep_to <= max(high, low + groove.blade_mm):
            raise GrooveStyleError(f"{where}: the pass along the bottom ends at Z {plunge.sweep_to:g}, outside the groove")
        if plunge.edge is not None:
            _check_edge(groove, plunge.edge, None, where)
            if abs(plunge.z - _wall_tip(groove, plunge.edge)) > GEOMETRY_TOLERANCE_MM:
                raise GrooveStyleError(f"{where}: a plunge that cuts an edge must be at the wall of that edge")


def _edge_size(groove: GrooveInput, side: str) -> float | None:
    return groove.edge_high_mm if side == EDGE_HIGH else groove.edge_low_mm if side == EDGE_LOW else None


def _check_edge(groove: GrooveInput, side: str, size_mm: float | None, where: str) -> None:
    size = _edge_size(groove, side)
    if size is None or size <= 0:
        raise GrooveStyleError(f"{where}: an edge cut for a wall without an edge ({side!r})")
    if size_mm is not None and not 0 < size_mm <= size + GEOMETRY_TOLERANCE_MM:
        raise GrooveStyleError(f"{where}: an edge cut of {size_mm:g} for an edge of {size:g}")


def _wall_tip(groove: GrooveInput, side: str) -> float:
    """The tip Z of a blade that stands at the wall of the edge: the corner that cuts the edge is at the wall."""
    return groove.wall_high_z - groove.blade_mm if side == EDGE_HIGH else groove.wall_low_z


def finishing_plunges(groove: GrooveInput) -> list[Plunge]:
    """The finishing plunges the standard style makes (none when the form asks for none): at the front wall, then at the other wall,
    with a pass along the bottom when the groove is wider than two blades. A style may use them as they are after its own roughing."""
    if not groove.finishing:
        return []
    return [
        Plunge(z, groove.final_radius, finishing=True, sweep_to=sweep_to)
        for z, sweep_to in finish_steps(groove.wall_low_z, groove.wall_high_z, groove.blade_mm, groove.finish_stop_early_mm)
    ]


def edge_sizes(size_mm: float, one_sided_mm: float) -> list[float]:
    """The sizes the corner cuts a large edge in, smallest first, the last is the whole edge: no step takes more than the one-sided cut."""
    count = max(1, math.ceil(size_mm / one_sided_mm - GEOMETRY_TOLERANCE_MM))
    return [size_mm * step / count for step in range(1, count + 1)]


def wall_steps(groove: GrooveInput) -> list[Plunge | EdgeCut]:
    """The steps that make the walls final: the finishing plunges of the form and, for a wall with an edge, the cut of the edge in
    the same move as the wall (the smaller passes of a large edge before it). The wall nearer the face first."""
    steps: list[Plunge | EdgeCut] = list(finishing_plunges(groove))
    for side in (EDGE_HIGH, EDGE_LOW):
        size = _edge_size(groove, side)
        if not size or size <= 0:
            continue
        tip = _wall_tip(groove, side)
        at = next((i for i, step in enumerate(steps) if isinstance(step, Plunge) and step.edge is None and abs(step.z - tip) <= GEOMETRY_TOLERANCE_MM), None)
        if at is None:  # no finishing plunge at this wall: the edge brings its own plunge down the wall
            at = 0 if side == EDGE_HIGH else len(steps)
            steps.insert(at, Plunge(tip, groove.final_radius, finishing=True, edge=side))
        else:
            steps[at] = replace(steps[at], edge=side)
        first_passes = [EdgeCut(side, part) for part in edge_sizes(size, groove.one_sided_mm)[:-1]]
        steps[at:at] = first_passes
    return steps


def _positions(groove: GrooveInput, low: float, high: float) -> list[float]:
    """Where the blade plunges to roughen the groove between the walls `low` and `high`. A groove that goes to the axis cuts the part off,
    so its first plunge is at the wall of the part, or the part comes off too long."""
    return rough_plunges(low, high, groove.blade_mm, groove.one_sided_mm, wall_first=groove.through)


def standard_plan(groove: GrooveInput) -> list[Plunge | EdgeCut]:
    """The standard style: roughing plunges from the front wall towards the chuck, each at most one one-sided cut wider than
    the one before, then (when the form asks for it) the finishing plunges at the walls with a pass along the bottom. A wall with an edge
    is cut in one move with its edge."""
    positions = _positions(groove, groove.rough_low_z, groove.rough_high_z)
    return [Plunge(z, groove.rough_bottom_radius) for z in positions] + wall_steps(groove)


STYLES.register(GROOVING, StyleInfo("standard", "Standard", "Plunges from the front wall towards the chuck, each one at most one one-sided cut wider than the one before. Finishing plunges at the walls with a pass along the bottom.", standard_plan))


def layers_plan(groove: GrooveInput) -> list[Plunge | EdgeCut]:
    """The groove opened layer by layer: every layer at all the plunge positions of the standard style, from the front wall towards the chuck,
    before the next layer goes deeper (the layer depth: the peck depth of the form, without one half the groove depth); then the finishing
    plunges of the form."""
    positions = _positions(groove, groove.rough_low_z, groove.rough_high_z)
    depth = abs(groove.rough_bottom_radius - groove.surface_radius)
    layer = groove.peck_depth_mm or depth / 2
    levels = pass_levels(groove.surface_radius, groove.rough_bottom_radius, layer) or [groove.rough_bottom_radius]
    return [Plunge(z, level) for level in levels for z in positions] + wall_steps(groove)


def edges_first_plan(groove: GrooveInput) -> list[Plunge | EdgeCut]:
    """Opens the groove only as deep as the edges need (their size plus the relief of the preferences), leaving a thin skin on the wall of
    an edge, then cuts every edge in one move with its wall: the corner comes down the chamfer or the fillet and goes on down the wall.
    A groove that goes to the axis cuts the part off with the wall of the part first, so the part is still held when its edge is cut and
    comes off at its length. The rest of the groove follows. Without an edge (or with an edge as deep as the groove) it is the standard style."""
    relief = groove.relief_radius
    if relief is None or not (groove.edge_high_mm > 0 or groove.edge_low_mm > 0):
        return standard_plan(groove)
    low = groove.rough_low_z if groove.relief_low_z is None else groove.relief_low_z
    high = groove.rough_high_z if groove.relief_high_z is None else groove.relief_high_z
    steps: list[Plunge | EdgeCut] = [Plunge(z, relief) for z in _positions(groove, low, high)]
    walls = wall_steps(groove)
    part_wall = next((i for i, step in enumerate(walls) if isinstance(step, Plunge) and step.edge == EDGE_HIGH), None)
    if groove.through and part_wall is not None:  # the wall of the part first: its edge and the cut-off in one move
        steps += walls[: part_wall + 1]
        walls = walls[part_wall + 1:]
    steps += [Plunge(z, groove.rough_bottom_radius) for z in _positions(groove, groove.rough_low_z, groove.rough_high_z)]
    return steps + walls


STYLES.register(GROOVING, StyleInfo(
    "layers", "Layers",
    "Opens the groove layer by layer: every layer at all plunge positions before the next one goes deeper. The layer depth is the peck depth of "
    "the form (without one, half the groove depth).", layers_plan,
))

STYLES.register(GROOVING, StyleInfo(
    "edges_first", "Edges before full depth",
    "Opens the groove only as deep as the chamfer or fillet of an edge needs, then cuts the edge and its wall in one move: for a cut-off with a "
    "chamfer or a fillet on the part (the wall of the part goes first, so the part is held while its edge is cut and comes off at its length). "
    "Without an edge it is the standard style.", edges_first_plan,
))
