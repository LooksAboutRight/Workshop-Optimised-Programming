"""Read a DXF file into lines and arcs (requirement C6), with the ezdxf library.

Lines and arcs are used directly; polylines are exploded into lines and arcs. POINT entities are named
by the TEXT or MTEXT next to them (named points of a shape). Circles, splines, ellipses, dimensions and everything
else are counted and named in the notes of the drawing, never dropped silently. The result is in mm.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..core.constants import DXF_INCH_TO_MM, DXF_UNITS_INCH_CODE
from ..core.contour import ContourError
from ..core.dxf_contour import DxfArc, DxfDrawing, DxfLine, name_markers

MIRRORED_EXTRUSION_Z = 0  # an arc whose extrusion points to -Z is drawn mirrored
FLAT_DEGREES = 180


def read_dxf(path: Path) -> DxfDrawing:
    """Lines and arcs of the model space. Raises ContourError with a readable message."""
    try:
        import ezdxf
    except ModuleNotFoundError as error:
        raise ContourError("DXF import needs the ezdxf package: pip install ezdxf") from error
    try:
        document = ezdxf.readfile(str(path))
    except (OSError, ezdxf.DXFError) as error:
        raise ContourError(f"cannot read {path.name}: {error}") from error
    scale = DXF_INCH_TO_MM if document.units == DXF_UNITS_INCH_CODE else 1.0
    entities: list[DxfLine | DxfArc] = []
    ignored: Counter[str] = Counter()
    markers: list[tuple[float, float]] = []
    labels: list[tuple[str, tuple[float, float]]] = []

    def add(entity) -> None:
        kind = entity.dxftype()
        if kind == "LINE":
            start, end = entity.dxf.start, entity.dxf.end
            entities.append(DxfLine((start.x * scale, start.y * scale), (end.x * scale, end.y * scale)))
        elif kind == "ARC":
            center, radius = entity.dxf.center, entity.dxf.radius
            start_deg, end_deg = entity.dxf.start_angle, entity.dxf.end_angle
            x = center.x
            if entity.dxf.extrusion.z < MIRRORED_EXTRUSION_Z:
                x = -x
                start_deg, end_deg = FLAT_DEGREES - end_deg, FLAT_DEGREES - start_deg
            entities.append(DxfArc((x * scale, center.y * scale), radius * scale, start_deg, end_deg))
        elif kind in ("LWPOLYLINE", "POLYLINE"):
            for part in entity.virtual_entities():
                add(part)
        elif kind == "POINT":
            location = entity.dxf.location
            markers.append((location.x * scale, location.y * scale))
        elif kind in ("TEXT", "MTEXT"):
            insert = entity.dxf.insert
            text = entity.dxf.text if kind == "TEXT" else entity.plain_text()
            labels.append((text, (insert.x * scale, insert.y * scale)))
        else:
            ignored[kind] += 1

    for entity in document.modelspace():
        add(entity)
    points = name_markers(markers, labels)
    if not markers and labels:
        ignored["TEXT"] += len(labels)  # text with no point beside it is not used
    notes = [f"ignored in the drawing: {count} {kind}" for kind, count in sorted(ignored.items())]
    if scale != 1.0:
        notes.append("the drawing is in inches: converted to mm")
    return DxfDrawing(tuple(entities), tuple(notes), points)
