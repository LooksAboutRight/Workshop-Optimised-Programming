"""What a sketch is for: the modes (turning contour, tool shape, workholding outline, free) and the way to and from `Contour`.

A mode says what the finished outline must look like (one chain of pieces, open or closed, above the spindle axis ...)
and `problems` lists in plain words what is still wrong. `contour_from_sketch` turns a good sketch into the program's own
contour (segments, cutting flags, named points) and keeps the sketch inside it, so it can be edited again.
`sketch_from_contour` does the way back; a contour without a sketch (made by the old editor or a DXF file) becomes a
sketch without relations.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..constants import GEOMETRY_TOLERANCE_MM
from ..contour import Contour, NamedPoint
from ..contour_check import find_crossings
from ..geometry import ArcSegment, LineSegment, Point, Segment, segments_to_polyline
from .constants import POINT_TOLERANCE, SAME_DECIMALS
from .loops import chain_segments, find_chains, reversed_segment
from .model import Sketch, SketchError
from .path_walk import path_segments
from .raw_part_rule import raw_part_problems
from .sketch_io import sketch_from_dict, sketch_to_dict


@dataclass(frozen=True)
class SketchMode:
    key: str
    title: str
    needs_outline: bool = True  # exactly one chain of pieces
    closed: bool | None = None  # True: the outline must be closed; False: open; None: either
    above_axis: bool = False  # nothing below the spindle axis (X is a radius)
    start_high_z: bool = False  # the contour starts at its highest Z (the convention of the contours of the part)
    cutting_edges: bool = False  # pieces can be marked as cutting edges (tool shapes)
    named_points: bool = False  # points can get names (tip ...)
    centre_line: bool = False  # the spindle axis is there as a centre line that dimensions go to (they become diameters)
    rapid_lines: bool = False  # lines can be marked as rapid moves (a path)
    piece_feeds: bool = False  # a piece can have a feed of its own (a path)
    may_cross: bool = False  # the outline may cross or touch itself (a path goes back and forth)
    walk: Callable[[Sketch], tuple[list[Segment], list[str]]] | None = None  # a mode that is not one chain: its own order of the pieces and problems
    check: Callable[[Sketch, list[Segment], bool], list[str]] | None = None  # more rules of this mode: (sketch, outline in travel order, closed) -> problems


FREE = SketchMode("free", "Free sketch", needs_outline=False)
TURNING = SketchMode("turning", "Turning contour", closed=False, above_axis=True, start_high_z=True, centre_line=True)
TOOL = SketchMode("tool", "Tool shape", closed=True, cutting_edges=True, named_points=True)
WORKHOLDING = SketchMode("workholding", "Workholding outline", closed=True, named_points=True)
RAW_PART = SketchMode(
    "raw_part", "Raw part", closed=None, above_axis=True, named_points=True, centre_line=True, check=raw_part_problems,
)
PATH = SketchMode(
    "path", "Custom path", closed=False, centre_line=True, rapid_lines=True, piece_feeds=True, may_cross=True, walk=path_segments,
)


def problems(sketch: Sketch, mode: SketchMode) -> list[str]:
    """What is still wrong with the sketch for this mode, in plain words (empty: it can be used)."""
    if not mode.needs_outline:
        return []
    if mode.walk is not None:
        return mode.walk(sketch)[1]
    try:
        chains = find_chains(sketch)
    except SketchError:
        return ["Three or more pieces meet at one point: an outline is one piece after the other"]
    if not chains:
        return ["Draw the outline first"]
    if len(chains) > 1:
        return [f"The outline is in {len(chains)} separate parts: join them, or make the extra ones construction lines"]
    found = []
    chain = chains[0]
    if mode.closed is True and not chain.closed:
        found.append("The outline is not closed")
    if mode.closed is False and chain.closed:
        found.append("The contour must be open, not a closed loop")
    segments = chain_segments(sketch, chain)
    crossings = [] if mode.may_cross else find_crossings(segments, chain.closed)
    if crossings:
        first = crossings[0]
        found.append(f"The outline crosses or touches itself (piece {first.first + 1} and piece {first.second + 1} along the outline)")
    if mode.check is not None and not crossings:
        found += mode.check(sketch, segments, chain.closed)
    if mode.above_axis:
        lowest = min(point.x for point in segments_to_polyline(chain_segments(sketch, chain)))
        if lowest < -GEOMETRY_TOLERANCE_MM:
            found.append("Part of the contour is below the spindle axis (X is less than 0)")
    return found


def contour_from_sketch(sketch: Sketch, mode: SketchMode, contour_id: str, name: str) -> Contour:
    """The contour the sketch draws, with the sketch kept inside. Raises SketchError with the problems."""
    if not mode.needs_outline:
        raise SketchError("A free sketch has no outline to use")
    found = problems(sketch, mode)
    if found:
        raise SketchError("; ".join(found))
    if mode.walk is not None:
        return Contour(contour_id, name, tuple(mode.walk(sketch)[0]), None, "", (), (), sketch_to_dict(sketch))
    chain = find_chains(sketch)[0]
    segments = tuple(chain_segments(sketch, chain))
    if mode.start_high_z and segments[0].start.z < segments[-1].end.z:
        segments = tuple(reversed_segment(segment) for segment in reversed(segments))
    cutting = tuple(piece.cutting for piece in chain.pieces) if mode.cutting_edges else ()
    points = ()
    if mode.named_points:
        points = tuple(NamedPoint(label, sketch.point(point_id).x, sketch.point(point_id).z) for label, point_id in sketch.labels.items())
    return Contour(contour_id, name, segments, None, "", cutting, points, sketch_to_dict(sketch))


def sketch_from_contour(contour: Contour) -> Sketch:
    """The sketch to edit for a contour: its own, or one made from its segments (shared ends become one point)."""
    kept = _kept_sketch(contour)
    if kept is not None:
        return kept
    sketch = Sketch()

    def point_at(position: Point) -> int:
        for point_id, point in sketch.points.items():
            if point.position.distance_to(position) <= POINT_TOLERANCE:
                return point_id
        return sketch.add_point(position.x, position.z)

    for index, segment in enumerate(contour.segments):
        cutting = index < len(contour.cutting) and contour.cutting[index]
        if isinstance(segment, LineSegment):
            start, end = point_at(segment.start), point_at(segment.end)
            if start != end:
                sketch.add_line(start, end, cutting=cutting)
        elif isinstance(segment, ArcSegment):
            sketch.add_arc(point_at(segment.center), point_at(segment.start), point_at(segment.end), segment.direction, cutting=cutting)
    for named in contour.points:
        sketch.label_point(point_at(named.position), named.name)
    return sketch


def _describe(segments) -> list[tuple]:
    """The pieces as comparable numbers, in no particular order and whichever way they are walked."""
    def key(point: Point) -> tuple[float, float]:
        return round(point.x, SAME_DECIMALS), round(point.z, SAME_DECIMALS)

    return sorted(
        (type(s).__name__, tuple(sorted((key(s.start), key(s.end)))), key(s.point_at(1 / 2)))  # the middle tells which arc
        for s in segments
    )


def _kept_sketch(contour: Contour) -> Sketch | None:
    """The sketch stored in the contour, if it still draws the contour's outline (it may have been changed since)."""
    if contour.sketch is None:
        return None
    try:
        sketch = sketch_from_dict(contour.sketch)
        chains = find_chains(sketch)
    except SketchError:
        return None
    if len(chains) != 1 or _describe(chain_segments(sketch, chains[0])) != _describe(contour.segments):
        return None
    return sketch
