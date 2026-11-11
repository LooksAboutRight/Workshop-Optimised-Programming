"""Save and load tools as plain data (requirements T1, T5)."""

from __future__ import annotations

from ..constants import TOOL_FORMAT_VERSION
from .contour_io import named_point_from_data, point_to_named_data, segment_from_data, segment_to_data
from ..tooling.toolbox import Toolbox, ToolboxEntry, ToolboxError
from ..tooling.tool import Tool, ToolError, ToolMaterial, ToolSegment, ToolSegmentRole, ToolShape


def toolbox_to_dict(box: Toolbox) -> dict:
    return {
        "name": box.name,
        "tools": [
            {"tool": e.tool_name, "number": e.number, **({"offset_number": e.offset_number} if e.offset_number is not None else {})}
            for e in box.entries
        ],
    }


def toolbox_from_dict(data: dict) -> Toolbox:
    """Rebuild a toolbox. Raises ToolboxError if the data is wrong."""
    try:
        entries = tuple(ToolboxEntry(item["tool"], item["number"], item.get("offset_number")) for item in data["tools"])
        return Toolbox(data["name"], entries)
    except ToolboxError:
        raise
    except (AttributeError, KeyError, TypeError) as error:
        raise ToolboxError(f"invalid toolbox data: {error!r}") from error


def tool_to_dict(tool: Tool) -> dict:
    data = {
        "format": TOOL_FORMAT_VERSION,
        "number": tool.number,
        "name": tool.name,
        "pieces": [
            {"role": piece.role.name, "segment": segment_to_data(piece.segment)}
            for piece in tool.shape.pieces
        ],
        "material": tool.material.name,
    }
    if tool.kind:  # a tool made from a type keeps its definition for editing (T8)
        data["kind"] = tool.kind
        data["definition"] = tool.definition
    if tool.sketch is not None:
        data["sketch"] = tool.sketch
    if tool.offset_number is not None:
        data["offset_number"] = tool.offset_number
    if tool.origin_library:
        data["origin"] = {"library": tool.origin_library, "name": tool.origin_name}
    if tool.points:
        data["points"] = [point_to_named_data(point) for point in tool.points]
    return data


def tool_from_dict(data: dict) -> Tool:
    """Rebuild a tool. Raises ToolError if the data is incomplete or wrong."""
    try:
        if data["format"] != TOOL_FORMAT_VERSION:
            raise ToolError(f"unsupported tool format {data['format']!r}")
        pieces = tuple(
            ToolSegment(segment_from_data(item["segment"]), ToolSegmentRole[item["role"]])
            for item in data["pieces"]
        )
        material = ToolMaterial[data["material"]] if "material" in data else ToolMaterial.CARBIDE
        points = tuple(named_point_from_data(item) for item in data.get("points", ()))
        return Tool(
            data["number"], data["name"], ToolShape(pieces), material, data.get("kind", ""), data.get("definition"), points,
            offset_number=data.get("offset_number"), sketch=data.get("sketch"),
            origin_library=data.get("origin", {}).get("library", ""), origin_name=data.get("origin", {}).get("name", ""),
        )
    except ToolError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ToolError(f"invalid tool data: {error!r}") from error
