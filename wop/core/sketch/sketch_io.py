"""Save and load a sketch as plain data (numbers, strings, booleans, lists), so it goes into a project or tool file."""

from __future__ import annotations

from ..geometry import ArcDirection
from .model import CornerLink, Sketch, SketchArc, SketchError, SketchLine, SketchPoint
from .relations import Constraint, relation_for

SKETCH_FORMAT_VERSION = 1


def sketch_to_dict(sketch: Sketch) -> dict:
    return {
        "format": SKETCH_FORMAT_VERSION,
        "next_id": sketch.next_id,
        "points": [[p.point_id, p.x, p.z] for p in sketch.points.values()],
        "lines": [[l.line_id, l.start, l.end, l.construction, l.cutting, l.centre_line, l.reference] for l in sketch.lines.values()],
        "arcs": [
            [a.arc_id, a.centre, a.start, a.end, a.direction.name.lower(), a.construction, a.cutting, a.reference]
            for a in sketch.arcs.values()
        ],
        "constraints": [
            [c.constraint_id, c.kind, list(c.refs), list(c.values), None if c.offset is None else list(c.offset)]
            for c in sketch.constraints.values()
        ],
        "labels": [[name, point_id] for name, point_id in sketch.labels.items()],
        "helpers": sorted(sketch.helpers),
        "path": {"rapid": sorted(sketch.rapid_pieces), "feeds": [[i, f] for i, f in sketch.piece_feeds.items()]},
        "locked": {"points": [[key, i] for key, i in sketch.locked_points.items()], "lines": [[key, i] for key, i in sketch.locked_lines.items()],
   "arcs": [[key, i] for key, i in sketch.locked_arcs.items()],
   "groups": [[group, [list(piece) for piece in pieces]] for group, pieces in sketch.locked_groups.items()]},
        "corners": [
            [bevel, c.point, list(c.kept), list(c.ends), list(c.references)] for bevel, c in sketch.corners.items()
        ],
    }


def sketch_from_dict(data: dict) -> Sketch:
    """Rebuild a sketch. Raises SketchError if the data is not a sketch."""
    try:
        if data["format"] != SKETCH_FORMAT_VERSION:
            raise SketchError(f"unsupported sketch format {data['format']!r}")
        sketch = Sketch()
        for point_id, x, z in data["points"]:
            sketch.points[point_id] = SketchPoint(point_id, float(x), float(z))
        for line_id, start, end, construction, cutting, centre, reference in data["lines"]:
            sketch.lines[line_id] = SketchLine(line_id, start, end, bool(construction), bool(cutting), bool(centre), bool(reference))
        for arc_id, centre, start, end, direction, construction, cutting, *more in data["arcs"]:
            sketch.arcs[arc_id] = SketchArc(
                arc_id, centre, start, end, ArcDirection[direction.upper()], bool(construction), bool(cutting), bool(more[0]) if more else False,
            )
        for constraint_id, kind, refs, values, offset in data["constraints"]:
            relation_for(kind)  # an unknown kind raises KeyError
            placed = None if offset is None else (float(offset[0]), float(offset[1]))
            sketch.constraints[constraint_id] = Constraint(constraint_id, kind, tuple(refs), tuple(float(v) for v in values), placed)
        sketch.labels = {str(name): point_id for name, point_id in data["labels"]}
        sketch.helpers = {int(point_id) for point_id in data["helpers"]}
        path = data.get("path", {"rapid": [], "feeds": []})
        sketch.rapid_pieces = {int(i) for i in path["rapid"]}
        sketch.piece_feeds = {int(i): float(f) for i, f in path["feeds"]}
        locked = data.get("locked", {"points": [], "lines": []})
        sketch.locked_points = {str(key): int(i) for key, i in locked["points"]}
        sketch.locked_lines = {str(key): int(i) for key, i in locked["lines"]}
        sketch.locked_arcs = {str(key): int(i) for key, i in locked.get("arcs", [])}
        sketch.locked_groups = {str(group): tuple((str(kind), str(key)) for kind, key in pieces) for group, pieces in locked.get("groups", [])}
        for bevel, point, kept, ends, references in data.get("corners", ()):
            sketch.corners[int(bevel)] = CornerLink(int(point), (int(kept[0]), int(kept[1])), (int(ends[0]), int(ends[1])),
                                                    (int(references[0]), int(references[1])), int(bevel))
        sketch.next_id = int(data["next_id"])
        _check(sketch)
        return sketch
    except SketchError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise SketchError(f"invalid sketch data: {error!r}") from error


def _check(sketch: Sketch) -> None:
    for line in sketch.lines.values():
        sketch.point(line.start), sketch.point(line.end)
    for arc in sketch.arcs.values():
        sketch.point(arc.centre), sketch.point(arc.start), sketch.point(arc.end)
    for point_id in sketch.labels.values():
        sketch.point(point_id)
    for point_id in sketch.locked_points.values():
        sketch.point(point_id)
    for line_id in sketch.locked_lines.values():
        if line_id not in sketch.lines:
            raise SketchError(f"unknown locked line {line_id}")
    for arc_id in sketch.locked_arcs.values():
        if arc_id not in sketch.arcs:
            raise SketchError(f"unknown locked arc {arc_id}")
