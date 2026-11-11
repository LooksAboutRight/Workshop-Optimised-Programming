"""Move, mirror and turn a contour definition (open contours of the part and closed shapes of tools and holding).

Pictures are drawn with Z to the right and X up. `mirrored_x` swaps the sign of X (up/down), `mirrored_z` the sign of
Z (left/right), `rotated_90` turns the shape a quarter turn counter-clockwise (a point at the right goes to the top).
`shifted` adds a constant to X and Z and changes nothing else: the shape stays as it is and only its coordinate system
moves (a drawing whose zero is in the wrong place).

Mirroring and turning give every line its end point and every arc its radius, centre and end point: the values the user
had typed (an angle, a centre) are not kept, the shape is. Mirroring an open contour in Z also runs the chain the other
way round, so that it still starts at its highest Z.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from .contour import (
    ArcCenterStep,
    ArcRadiusStep,
    ContourDefinition,
    Corner,
    LineStep,
    NamedPoint,
    SHARP_CORNER,
    Step,
)
from .geometry import ArcDirection, Point

PointMap = Callable[[Point], Point]


def _flipped(direction: ArcDirection) -> ArcDirection:
    return ArcDirection.CW if direction is ArcDirection.CCW else ArcDirection.CCW


def _named(points: tuple[NamedPoint, ...], where: PointMap) -> tuple[NamedPoint, ...]:
    return tuple(replace(p, x=where(p.position).x, z=where(p.position).z) for p in points)


def shifted(definition: ContourDefinition, dx: float, dz: float) -> ContourDefinition:
    """Every coordinate moved by (dx, dz); lengths, angles and what the user typed stay."""

    def where(point: Point) -> Point:
        return Point(point.x + dx, point.z + dz)

    steps: list[Step] = []
    for step in definition.steps:
        if isinstance(step, (LineStep, ArcRadiusStep)):
            steps.append(replace(step, end=where(step.end)))
        else:
            steps.append(replace(step, end=where(step.end), center=where(step.center)))
    return replace(definition, start=where(definition.start), steps=tuple(steps), points=_named(definition.points, where))


def _mapped(definition: ContourDefinition, where: PointMap, flips: bool) -> ContourDefinition:
    """The definition seen through `where`. `flips`: the map reverses the orientation."""
    steps: list[Step] = []
    for step in definition.steps:
        end = where(step.end)
        direction = getattr(step, "direction", None)
        if direction is not None and flips:
            direction = _flipped(direction)
        if isinstance(step, LineStep):
            steps.append(LineStep(end, step.corner, step.cutting))
        elif isinstance(step, ArcRadiusStep):
            steps.append(ArcRadiusStep(end, step.radius_mm, direction, step.large_arc, step.cutting))
        else:
            steps.append(ArcCenterStep(end, where(step.center), direction, step.cutting))
    return replace(definition, start=where(definition.start), steps=tuple(steps), points=_named(definition.points, where))


def _reversed(definition: ContourDefinition) -> ContourDefinition:
    """The open chain run from its end to its start (the same shape)."""
    steps = definition.steps
    if not steps:
        return definition
    ends = [definition.start] + [step.end for step in steps]  # ends[i] is where step i-1 ends
    result: list[Step] = []
    for index in range(len(steps) - 1, -1, -1):
        step, target = steps[index], ends[index]
        before = steps[index - 1] if index > 0 else None
        corner: Corner = before.corner if isinstance(before, LineStep) and isinstance(step, LineStep) else SHARP_CORNER
        if isinstance(step, LineStep):
            result.append(LineStep(target, corner, step.cutting))
        elif isinstance(step, ArcRadiusStep):
            result.append(ArcRadiusStep(target, step.radius_mm, _flipped(step.direction), step.large_arc, step.cutting))
        else:
            result.append(ArcCenterStep(target, step.center, _flipped(step.direction), step.cutting))
    return replace(definition, start=steps[-1].end, steps=tuple(result))


def mirrored_x(definition: ContourDefinition) -> ContourDefinition:
    return _mapped(definition, lambda p: Point(-p.x, p.z), flips=True)


def mirrored_z(definition: ContourDefinition) -> ContourDefinition:
    mirrored = _mapped(definition, lambda p: Point(p.x, -p.z), flips=True)
    return mirrored if definition.closed else _reversed(mirrored)


def rotated_90(definition: ContourDefinition) -> ContourDefinition:
    """A quarter turn counter-clockwise in the picture (Z to the right, X up): (x, z) becomes (z, -x)."""
    return _mapped(definition, lambda p: Point(p.z, -p.x), flips=False)
