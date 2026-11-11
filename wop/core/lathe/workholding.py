"""Workholding: chuck body and jaws (requirement R6, work package WH1).

A workholding item is a closed outline (a contour with named points) drawn in machine orientation, like a tool
shape: x = radius, z = axial position. Two kinds exist: the chuck body and a set of jaws (`workholding_types`).
The program uses at most one of each (`Workholding`); no workholding at all is the normal case, then the flat
clamping plane of the raw part is the surface the checks use.

Placement of the jaws: one named point of the jaws (the anchor, a step of a stepped jaw) is moved onto the part:
to the outer radius of the raw part for an outside grip, to the inner radius for an inside grip (a tube held from
the bore). Axially it goes to the clamping plane, or, when the stock ends inside the jaws, to the back end of the
stock (clamping plane minus the length inside), where the shoulder of a step meets the stock. The chuck body is
then moved in Z only, so its face point meets the mount point of the jaws.

The checks treat the jaws as a ring around the axis (they turn with the spindle). The angular width and the
count of the jaws are for the 3D picture.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from ..constants import WORKHOLDING_NOTE_TOLERANCE_MM, DEFAULT_JAW_COUNT, DEFAULT_JAW_WIDTH_DEG, FULL_TURN_DEG, JAWS_MOUNT_POINT, MIN_JAW_COUNT, CHUCK_FACE_POINT
from ..contour import Contour, NamedPoint
from ..geometry import ArcSegment, LineSegment, Point, Segment, segments_to_polyline
from ..program_model.raw_part import RawPart


class WorkholdingError(ValueError):
    """A workholding item or its placement is not usable."""


class GripMode(Enum):
    OUTSIDE = "outside"  # jaws close on the outer diameter
    INSIDE = "inside"  # jaws expand in the bore of a tube


JAWS_KIND = "jaws"
CHUCK_KIND = "chuck"


@dataclass(frozen=True)
class WorkholdingItem:
    """A saved chuck body or set of jaws. `kind` is the type name (`workholding_types`)."""

    name: str
    kind: str
    outline: Contour  # closed, valid; its named points are the points the placement uses
    jaw_count: int = DEFAULT_JAW_COUNT  # jaws only
    jaw_width_deg: float = DEFAULT_JAW_WIDTH_DEG  # jaws only: angle of one jaw
    chuck: str = ""  # jaws only: name of the chuck body they sit on (empty: none)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise WorkholdingError("a workholding item needs a name")
        if not self.outline.is_valid:
            raise WorkholdingError(f"{self.name}: {self.outline.error or 'the shape has no outline'}")
        if not self.outline.is_closed:
            raise WorkholdingError(f"{self.name}: the shape is not closed")
        if self.kind == JAWS_KIND:
            if self.jaw_count < MIN_JAW_COUNT:
                raise WorkholdingError(f"{self.name}: a chuck has at least {MIN_JAW_COUNT} jaws")
            if self.jaw_width_deg <= 0:
                raise WorkholdingError(f"{self.name}: the jaw width must be greater than zero")
            if self.jaw_count * self.jaw_width_deg > FULL_TURN_DEG:
                raise WorkholdingError(f"{self.name}: the jaws are wider together than a full turn")

    @property
    def points(self) -> tuple[NamedPoint, ...]:
        return self.outline.points

    def point(self, name: str) -> NamedPoint | None:
        for point in self.outline.points:
            if point.name == name:
                return point
        return None


@dataclass(frozen=True)
class Workholding:
    """What the program uses: jaws and/or chuck body (both optional), where the jaws sit on the part."""

    jaws: WorkholdingItem | None = None
    chuck: WorkholdingItem | None = None
    anchor: str = ""  # name of the jaw point that sits on the part; empty: the jaws stay where they are drawn
    grip: GripMode = GripMode.OUTSIDE

    @property
    def is_none(self) -> bool:
        return self.jaws is None and self.chuck is None


@dataclass(frozen=True)
class PlacedWorkholding:
    """The outlines on the machine, in the machine's X/Z (no longer the drawing's own position)."""

    jaws: tuple[Segment, ...] = ()
    chuck: tuple[Segment, ...] = ()
    jaws_points: tuple[NamedPoint, ...] = ()
    chuck_points: tuple[NamedPoint, ...] = ()
    anchor_target: Point | None = None  # where the anchor point sits on the part
    jaw_count: int = DEFAULT_JAW_COUNT  # for the 3D picture
    jaw_width_deg: float = DEFAULT_JAW_WIDTH_DEG

    @property
    def is_empty(self) -> bool:
        return not self.jaws and not self.chuck


# --- moving outlines ---------------------------------------------------------------


def _shifted(point: Point, dx: float, dz: float) -> Point:
    return Point(point.x + dx, point.z + dz)


def translate_segments(segments: tuple[Segment, ...], dx: float, dz: float) -> tuple[Segment, ...]:
    moved: list[Segment] = []
    for segment in segments:
        if isinstance(segment, ArcSegment):
            moved.append(
                ArcSegment(
                    _shifted(segment.start, dx, dz),
                    _shifted(segment.end, dx, dz),
                    _shifted(segment.center, dx, dz),
                    segment.direction,
                )
            )
        else:
            moved.append(LineSegment(_shifted(segment.start, dx, dz), _shifted(segment.end, dx, dz)))
    return tuple(moved)


def _translate_points(points: tuple[NamedPoint, ...], dx: float, dz: float) -> tuple[NamedPoint, ...]:
    return tuple(replace(point, x=point.x + dx, z=point.z + dz) for point in points)


def _z_range(segments: tuple[Segment, ...]) -> tuple[float, float]:
    zs = [point.z for point in segments_to_polyline(list(segments))]
    return min(zs), max(zs)


# --- placement ---------------------------------------------------------------------


def placement_target(raw_part: RawPart, grip: GripMode) -> Point:
    """Where the anchor point of the jaws sits on the raw part (x = radius, z = axial)."""
    if grip is GripMode.INSIDE:
        if raw_part.inner_diameter_mm <= 0:
            raise WorkholdingError("an inside grip needs a tube: the raw part has no bore")
        radius = raw_part.inner_radius_mm
    else:
        radius = raw_part.outer_radius_mm
    z = raw_part.clamp_z_mm
    if raw_part.length_inside_mm is not None:  # the stock ends inside the jaws: a step shoulder meets its back end
        z -= raw_part.length_inside_mm
    return Point(radius, z)


def workholding_problem(raw_part: RawPart, workholding: Workholding | None) -> str:
    """Why the workholding cannot be placed on this raw part; empty text if it can."""
    try:
        place_workholding(raw_part, workholding)
    except WorkholdingError as error:
        return str(error)
    return ""


def place_workholding(raw_part: RawPart, workholding: Workholding | None) -> PlacedWorkholding:
    """The jaws and the chuck body on the machine. Raises WorkholdingError if they cannot be placed."""
    if workholding is None or workholding.is_none:
        return PlacedWorkholding()
    jaws_segments: tuple[Segment, ...] = ()
    jaws_points: tuple[NamedPoint, ...] = ()
    target: Point | None = None
    mount_z: float = raw_part.clamp_z_mm  # without jaws the chuck face sits at the clamping plane
    if workholding.jaws is not None:
        jaws = workholding.jaws
        dx = dz = 0.0
        if workholding.anchor:
            anchor = jaws.point(workholding.anchor)
            if anchor is None:
                raise WorkholdingError(f"the jaws {jaws.name} have no point called {workholding.anchor!r}")
            target = placement_target(raw_part, workholding.grip)
            dx, dz = target.x - anchor.x, target.z - anchor.z
        jaws_segments = translate_segments(jaws.outline.segments, dx, dz)
        jaws_points = _translate_points(jaws.points, dx, dz)
        mount = jaws.point(JAWS_MOUNT_POINT)
        mount_z = mount.z + dz if mount is not None else _z_range(jaws_segments)[0]
    chuck_segments: tuple[Segment, ...] = ()
    chuck_points: tuple[NamedPoint, ...] = ()
    if workholding.chuck is not None:
        chuck = workholding.chuck
        face = chuck.point(CHUCK_FACE_POINT)
        face_z = face.z if face is not None else _z_range(chuck.outline.segments)[1]
        chuck_segments = translate_segments(chuck.outline.segments, 0, mount_z - face_z)
        chuck_points = _translate_points(chuck.points, 0, mount_z - face_z)
    count = workholding.jaws.jaw_count if workholding.jaws is not None else DEFAULT_JAW_COUNT
    width = workholding.jaws.jaw_width_deg if workholding.jaws is not None else DEFAULT_JAW_WIDTH_DEG
    return PlacedWorkholding(jaws_segments, chuck_segments, jaws_points, chuck_points, target, count, width)


def workholding_notes(raw_part: RawPart, workholding: Workholding | None) -> tuple[str, ...]:
    """Hints where the placed jaws and the Setup disagree (WH3). Empty if all fits or nothing can be placed.

    The checks use the jaws as placed; the clamping plane of the Setup (stick-out) is what the user typed. If the front
    face of the jaws is not at that plane, one of them is probably not what the user means.
    """
    if workholding is None or workholding.jaws is None:
        return ()
    try:
        placed = place_workholding(raw_part, workholding)
    except WorkholdingError:
        return ()  # `workholding_problem` says why
    notes: list[str] = []
    front = _z_range(placed.jaws)[1]
    gap = front - raw_part.clamp_z_mm
    if gap > WORKHOLDING_NOTE_TOLERANCE_MM:
        notes.append(
            f"the front face of the jaws is {gap:g} mm in front of the clamping plane of the Setup (Z {raw_part.clamp_z_mm:g}): "
            "the jaws cover that much of the free length; the checks use the jaws as placed"
        )
    elif -gap > WORKHOLDING_NOTE_TOLERANCE_MM:
        notes.append(
            f"the front face of the jaws is {-gap:g} mm behind the clamping plane of the Setup (Z {raw_part.clamp_z_mm:g}): "
            "that much of the part is clamped by nothing; the checks use the jaws as placed"
        )
    if workholding.grip is GripMode.INSIDE:
        notes += _inside_grip_notes(raw_part, placed)
    return tuple(notes)


def _inside_grip_notes(raw_part: RawPart, placed: PlacedWorkholding) -> list[str]:
    """Jaws that expand in the bore of a tube must stay inside the bore where they hold the tube."""
    held = [
        point
        for point in segments_to_polyline(list(placed.jaws))
        if point.z <= raw_part.clamp_z_mm + WORKHOLDING_NOTE_TOLERANCE_MM
    ]
    if not held:
        return []
    reach = max(point.x for point in held)
    excess = reach - raw_part.inner_radius_mm
    if excess <= WORKHOLDING_NOTE_TOLERANCE_MM:
        return []
    return [
        f"the jaws reach {excess:g} mm into the wall of the tube (bore radius {raw_part.inner_radius_mm:g}, jaws up to "
        f"radius {reach:g}) where they hold it: check the point of the jaws that sits on the part"
    ]


def raw_part_notes(raw_part: RawPart, workholding: Workholding | None) -> tuple[str, ...]:
    """Findings about the raw part that do not change the G-code: a stick-out longer than the part, bar stock too thick for the chuck."""
    notes: list[str] = []
    if raw_part.length_mm is not None and raw_part.length_outside_mm > raw_part.length_mm:
        notes.append(
            f"the stick-out ({raw_part.length_outside_mm:g} mm) is more than the length of the part ({raw_part.length_mm:g} mm): "
            "the part does not reach the chuck"
        )
    chuck = None if workholding is None else workholding.chuck
    if raw_part.length_mm is None and chuck is not None:
        bore = min(point.x for point in segments_to_polyline(list(chuck.outline.segments)))
        if raw_part.outer_radius_mm > bore:
            notes.append(
                f"the bar stock (diameter {raw_part.outer_diameter_mm:g}) does not fit through the chuck body "
                f"{chuck.name!r} (bore diameter {bore * 2:g})"
            )
    return tuple(notes)


# --- the library (a plain tuple of items with unique names) ----------------------------


def library_with(items: tuple[WorkholdingItem, ...], item: WorkholdingItem) -> tuple[WorkholdingItem, ...]:
    """The list with the item added, or replacing the one of the same name (not case sensitive)."""
    key = item.name.casefold()
    for index, existing in enumerate(items):
        if existing.name.casefold() == key:
            return items[:index] + (item,) + items[index + 1 :]
    return items + (item,)


def library_without(items: tuple[WorkholdingItem, ...], name: str) -> tuple[WorkholdingItem, ...]:
    key = name.casefold()
    return tuple(item for item in items if item.name.casefold() != key)


def library_find(items: tuple[WorkholdingItem, ...], name: str) -> WorkholdingItem | None:
    key = name.casefold()
    for item in items:
        if item.name.casefold() == key:
            return item
    return None
