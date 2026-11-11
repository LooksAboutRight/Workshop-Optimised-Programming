"""The styles of the grooving block: how the blade is moved to cut a groove.

A style decides ONLY the order and the depth of the plunges. It does not decide what is cut (that comes from the form of the block),
it does not know the tool body, the holder or the material, and it writes no G-code. The block turns every step of the style into
moves, skips the air above the material, retracts between the plunges, checks the tool at every position and reports what stays uncut.

A style is a function `plan(groove) -> list of Plunge`:
- `groove` is a `GrooveInput`: plain numbers (see its fields), all in mm.
- every `Plunge` says where the blade goes down: its tip Z, how deep (a radius) and, when wanted, a pass along the bottom.

The blade covers Z from the tip Z to the tip Z plus the blade width (`groove.blade_mm`).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import GEOMETRY_TOLERANCE_MM, MAX_STYLE_PLUNGES
from ..passes import pass_levels
from .groove_plan import finish_steps, rough_plunges
from .styles import STYLES, StyleInfo

GROOVING = "grooving"  # the block type these styles belong to


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
    rough_low_z: float  # the same walls for roughing: moved in by the finishing allowance
    rough_high_z: float
    surface_radius: float  # the surface the blade enters (the plunge starts above it)
    rough_bottom_radius: float  # the depth of the roughing plunges (the final radius plus the finishing allowance)
    final_radius: float  # the depth of the finished groove
    one_sided_mm: float  # the most the blade may cut wide with air on one side (a wider cut bends the blade)
    peck_depth_mm: float | None  # the form's peck depth for roughing plunges; None: straight down. The block does the pecking itself
    finishing: bool  # True: the form asks for finishing plunges (a finishing allowance and the finishing pass are set)
    finish_stop_early_mm: float  # a finishing pass along the bottom stops this far before the other wall


@dataclass(frozen=True)
class Plunge:
    """One plunge of the blade.

    `z` is the tip Z of the blade (between `rough_low_z` and `rough_high_z - blade_mm`, or the walls for a finishing plunge).
    `radius` is how deep it goes (between the final radius and the surface). `finishing` marks a finishing plunge: it uses the
    finishing feed and speed and is not pecked. `sweep_to` (a tip Z, or None) makes the blade, at the bottom of this plunge, move
    along the bottom to that Z before it comes out.
    """

    z: float
    radius: float
    finishing: bool = False
    sweep_to: float | None = None


class GrooveStyleError(ValueError):
    pass


def check_plunges(groove: GrooveInput, plunges: list[Plunge], style: str) -> None:
    """The contract of a grooving style: every plunge stays inside the groove. Raises GrooveStyleError with the reason."""
    low = min(groove.wall_low_z, groove.rough_low_z) - GEOMETRY_TOLERANCE_MM
    high = max(groove.wall_high_z, groove.rough_high_z) - groove.blade_mm + GEOMETRY_TOLERANCE_MM
    deep_low, deep_high = sorted((groove.final_radius, groove.surface_radius))
    deep_low, deep_high = deep_low - GEOMETRY_TOLERANCE_MM, deep_high + GEOMETRY_TOLERANCE_MM
    if not plunges:
        raise GrooveStyleError(f"style {style!r} made no plunge")
    if len(plunges) > MAX_STYLE_PLUNGES:
        raise GrooveStyleError(f"style {style!r} made {len(plunges)} plunges, the most for one block is {MAX_STYLE_PLUNGES}")
    for number, plunge in enumerate(plunges, start=1):
        where = f"style {style!r}, plunge {number}"
        if not low <= plunge.z <= max(high, low + groove.blade_mm):
            raise GrooveStyleError(f"{where}: Z {plunge.z:g} is outside the groove")
        if not deep_low <= plunge.radius <= deep_high:
            raise GrooveStyleError(f"{where}: radius {plunge.radius:g} is not between the final radius and the surface")
        if plunge.sweep_to is not None and not low <= plunge.sweep_to <= max(high, low + groove.blade_mm):
            raise GrooveStyleError(f"{where}: the pass along the bottom ends at Z {plunge.sweep_to:g}, outside the groove")


def finishing_plunges(groove: GrooveInput) -> list[Plunge]:
    """The finishing plunges the standard style makes (none when the form asks for none): at the front wall, then at the other wall,
    with a pass along the bottom when the groove is wider than two blades. A style may use them as they are after its own roughing."""
    if not groove.finishing:
        return []
    return [
        Plunge(z, groove.final_radius, finishing=True, sweep_to=sweep_to)
        for z, sweep_to in finish_steps(groove.wall_low_z, groove.wall_high_z, groove.blade_mm, groove.finish_stop_early_mm)
    ]


def standard_plan(groove: GrooveInput) -> list[Plunge]:
    """The standard style: roughing plunges from the front wall towards the chuck, each at most one one-sided cut wider than
    the one before, then (when the form asks for it) the finishing plunges at the walls with a pass along the bottom."""
    positions = rough_plunges(groove.rough_low_z, groove.rough_high_z, groove.blade_mm, groove.one_sided_mm)
    return [Plunge(z, groove.rough_bottom_radius) for z in positions] + finishing_plunges(groove)


STYLES.register(GROOVING, StyleInfo("standard", "Standard", "Plunges from the front wall towards the chuck, each one at most one one-sided cut wider than the one before. Finishing plunges at the walls with a pass along the bottom.", standard_plan))


def layers_plan(groove: GrooveInput) -> list[Plunge]:
    """The groove opened layer by layer: every layer at all the plunge positions of the standard style, from the front wall towards the chuck,
    before the next layer goes deeper (the layer depth: the peck depth of the form, without one half the groove depth); then the finishing
    plunges of the form."""
    positions = rough_plunges(groove.rough_low_z, groove.rough_high_z, groove.blade_mm, groove.one_sided_mm)
    depth = abs(groove.rough_bottom_radius - groove.surface_radius)
    layer = groove.peck_depth_mm or depth / 2
    levels = pass_levels(groove.surface_radius, groove.rough_bottom_radius, layer) or [groove.rough_bottom_radius]
    return [Plunge(z, level) for level in levels for z in positions] + finishing_plunges(groove)


STYLES.register(GROOVING, StyleInfo(
    "layers", "Layers",
    "Opens the groove layer by layer: every layer at all plunge positions before the next one goes deeper. The layer depth is the peck depth of "
    "the form (without one, half the groove depth).", layers_plan,
))
