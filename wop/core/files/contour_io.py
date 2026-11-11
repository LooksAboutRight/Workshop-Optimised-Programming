"""Save and load contours as plain data (requirement C1).

contour_to_dict returns only numbers, strings, booleans, lists and dicts, so
the result can go straight into a JSON file (the project file, stage S6).
Floats survive JSON unchanged, so a contour loads exactly as it was saved.
"""

from __future__ import annotations

from ..constants import CONTOUR_FORMAT_VERSION
from ..contour import (
    ArcCenterStep,
    ArcRadiusStep,
    Contour,
    ContourDefinition,
    ContourError,
    Corner,
    CornerKind,
    LineStep,
    NamedPoint,
    Step,
)
from .dataclass_codec import plain_number
from ..geometry import ArcDirection, ArcSegment, LineSegment, Point, Segment

_LINE = "line"
_ARC = "arc"
_ARC_RADIUS = "arc_radius"
_ARC_CENTER = "arc_center"


def contour_to_dict(contour: Contour) -> dict:
    definition = None
    if contour.definition is not None:
        definition = {
            "start": point_to_data(contour.definition.start),
            "steps": [_step_to_data(step) for step in contour.definition.steps],
        }
        if contour.definition.closed:
            definition["closed"] = True
        if contour.definition.points:
            definition["points"] = [point_to_named_data(p) for p in contour.definition.points]
    data = {
        "format": CONTOUR_FORMAT_VERSION,
        "id": contour.contour_id,
        "name": contour.name,
        "segments": [segment_to_data(segment) for segment in contour.segments],
        "definition": definition,
    }
    if any(contour.cutting):
        data["cutting"] = list(contour.cutting)
    if contour.points:
        data["points"] = [point_to_named_data(p) for p in contour.points]
    if contour.sketch is not None:
        data["sketch"] = contour.sketch
    return data


def contour_from_dict(data: dict) -> Contour:
    """Rebuild a contour. Raises ContourError if the data is incomplete or wrong."""
    try:
        if data["format"] != CONTOUR_FORMAT_VERSION:
            raise ContourError(f"unsupported contour format {data['format']!r}")
        definition_data = data["definition"]
        definition = None if definition_data is None else _definition_from_data(definition_data)
        segments = tuple(segment_from_data(item) for item in data["segments"])
        cutting = tuple(bool(flag) for flag in data.get("cutting", ()))
        points = tuple(named_point_from_data(item) for item in data.get("points", ()))
        return Contour(data["id"], data["name"], segments, definition, "", cutting, points, data.get("sketch"))
    except ContourError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ContourError(f"invalid contour data: {error!r}") from error


# --- points and directions -------------------------------------------------


def point_to_data(point: Point) -> list[float]:
    return [plain_number(point.x), plain_number(point.z)]


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContourError(f"expected a number, got {value!r}")
    return value


def point_from_data(data: list) -> Point:
    x, z = data
    return Point(_number(x), _number(z))


def point_to_named_data(point: NamedPoint) -> dict:
    return {"name": point.name, "x": plain_number(point.x), "z": plain_number(point.z)}


def named_point_from_data(data: dict) -> NamedPoint:
    return NamedPoint(str(data["name"]), _number(data["x"]), _number(data["z"]))


def _direction_to_data(direction: ArcDirection) -> str:
    return direction.name.lower()


def _direction_from_data(value: str) -> ArcDirection:
    return ArcDirection[value.upper()]


# --- solved segments -------------------------------------------------------


def segment_to_data(segment: Segment) -> dict:
    if isinstance(segment, LineSegment):
        return {
            "type": _LINE,
            "start": point_to_data(segment.start),
            "end": point_to_data(segment.end),
        }
    return {
        "type": _ARC,
        "start": point_to_data(segment.start),
        "end": point_to_data(segment.end),
        "center": point_to_data(segment.center),
        "direction": _direction_to_data(segment.direction),
    }


def segment_from_data(data: dict) -> Segment:
    kind = data["type"]
    start = point_from_data(data["start"])
    end = point_from_data(data["end"])
    if kind == _LINE:
        return LineSegment(start, end)
    if kind == _ARC:
        center = point_from_data(data["center"])
        return ArcSegment(start, end, center, _direction_from_data(data["direction"]))
    raise ContourError(f"unknown segment type {kind!r}")


# --- definition (what the user entered) ------------------------------------


def _step_to_data(step: Step) -> dict:
    if isinstance(step, LineStep):
        data = {
            "type": _LINE,
            "end": point_to_data(step.end),
            "corner": {"kind": step.corner.kind.value, "size_mm": step.corner.size_mm},
        }
        return _with_cutting(data, step)
    if isinstance(step, ArcRadiusStep):
        return _with_cutting({
            "type": _ARC_RADIUS,
            "end": point_to_data(step.end),
            "radius_mm": step.radius_mm,
            "direction": _direction_to_data(step.direction),
            "large_arc": step.large_arc,
        }, step)
    return _with_cutting({
        "type": _ARC_CENTER,
        "end": point_to_data(step.end),
        "center": point_to_data(step.center),
        "direction": _direction_to_data(step.direction),
    }, step)


def _with_cutting(data: dict, step: Step) -> dict:
    if step.cutting:  # written only when set, so contours of parts look as before
        data["cutting"] = True
    return data


def _step_from_data(data: dict) -> Step:
    kind = data["type"]
    end = point_from_data(data["end"])
    if kind == _LINE:
        corner = data["corner"]
        made = Corner(CornerKind(corner["kind"]), _number(corner["size_mm"]))
        cutting = bool(data.get("cutting", False))
        return LineStep(end, made, cutting=cutting)
    direction = _direction_from_data(data["direction"])
    cutting = bool(data.get("cutting", False))
    if kind == _ARC_RADIUS:
        return ArcRadiusStep(end, _number(data["radius_mm"]), direction, bool(data["large_arc"]), cutting)
    if kind == _ARC_CENTER:
        return ArcCenterStep(end, point_from_data(data["center"]), direction, cutting)
    raise ContourError(f"unknown step type {kind!r}")


def _definition_from_data(data: dict) -> ContourDefinition:
    start = point_from_data(data["start"])
    points = tuple(named_point_from_data(item) for item in data.get("points", ()))
    return ContourDefinition(
        start, tuple(_step_from_data(item) for item in data["steps"]), bool(data.get("closed", False)), points
    )
