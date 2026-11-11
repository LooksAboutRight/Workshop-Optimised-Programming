"""Save and load a project as text (requirements B4, B2, T5, C5).

The file is JSON with a format number. It holds everything the program needs:
raw part, safe positions, its own tool table, the contours and the blocks.
Saving a loaded project gives the same text again.
"""

from __future__ import annotations

import json
from dataclasses import replace

from ..blocks import BLOCK_TYPES
from ..blocks.base import Block, BlockError, Safety
from ..constants import NO_TOOL_NUMBER, PROJECT_FORMAT_VERSION
from ..geometry.chain_index import Loop
from .contour_io import ContourError, contour_from_dict, contour_to_dict
from ..geometry import ArcDirection, ArcSegment, LineSegment, Point, Segment
from ..lathe.machine import MachineError
from .machine_io import machine_from_dict, machine_to_dict
from .dataclass_codec import CodecError, from_data, plain_number, to_data
from ..program_model.program import Program
from ..program_model.project import Project, ProjectSettings
from ..program_model.raw_part import RawPart
from ..tooling.tool import ToolError
from .tool_io import tool_from_dict, tool_to_dict
from ..lathe.workholding import WorkholdingError
from .workholding_io import workholding_from_dict, workholding_to_dict


class ProjectError(ValueError):
    """The project file is damaged, from a newer version, or refers to something missing."""


def _block_to_data(block: Block) -> dict:
    return {"type": block.type_name, "parameters": to_data(block)}


def _block_from_data(data: dict) -> Block:
    block_class = BLOCK_TYPES.get(data["type"])
    parameters = data["parameters"]
    if data["type"] == "facing" and "finish_pass" not in parameters:  # before SETUP3 an allowance always came with a finishing pass
        parameters = dict(parameters, finish_pass=parameters.get("finish_allowance_mm", 0) > 0)
    if data["type"] == "drilling" and "depth_mm" in parameters:  # before: start Z and a depth measured from it
        parameters = {key: value for key, value in parameters.items() if key not in ("start_z_mm", "depth_mm")}
        parameters["depth_z_mm"] = data["parameters"].get("start_z_mm", 0) - data["parameters"]["depth_mm"]
        parameters["drill_mode"] = "DRILL" if parameters.get("peck_depth_mm") is None else "PECK_FULL_RETRACT"
    if data["type"] == "grooving" and "finish_pass" not in parameters:  # before, an allowance always came with a finishing pass
        parameters = dict(parameters, finish_pass=parameters.get("finish_allowance_mm", 0) > 0)
    if data["type"] == "grooving" and "min_overlap_mm" in parameters:  # a field of one earlier test version
        parameters = {key: value for key, value in parameters.items() if key != "min_overlap_mm"}
    if data["type"] == "threading" and "length_mm" in parameters:  # before: a length from the start, now an absolute end
        parameters = {key: value for key, value in parameters.items() if key != "length_mm"}
        parameters["end_z_mm"] = data["parameters"]["start_z_mm"] - data["parameters"]["length_mm"]
    if data["type"] == "turning" and "start_z_mm" in parameters:  # the cut now starts at the front face of the material
        parameters = {key: value for key, value in parameters.items() if key != "start_z_mm"}
    return from_data(block_class, parameters)


def project_to_dict(project: Project) -> dict:
    program = project.program
    data = {
        "format": PROJECT_FORMAT_VERSION,
        "settings": to_data(project.settings),
        "raw_part": _raw_part_to_data(program.raw_part),
        "safety": to_data(program.safety),
        "tools": [tool_to_dict(tool) for tool in program.tools],
        "contours": [contour_to_dict(contour) for contour in program.contours],
        "blocks": [_block_to_data(block) for block in program.blocks],
    }
    if program.workholding is not None:  # absent when there is none: files look as before
        data["workholding"] = workholding_to_dict(program.workholding)
    if program.toolbox_name:
        data["toolbox"] = {"library": program.toolbox_library, "name": program.toolbox_name}
    if project.machine is not None:
        data["machine"] = machine_to_dict(project.machine)
    if project.touched is not None:  # absent in files from before U6
        data["touched"] = list(project.touched)
    return data


def _raw_part_to_data(raw_part: RawPart) -> dict:
    data = to_data(replace(raw_part, outline=None))
    del data["outline"]  # a plain bar: files look as before
    if raw_part.outline is not None:
        data["outline"] = contour_to_dict(raw_part.outline)
    return data


def _raw_part_data(data: dict) -> dict:
    """Files from before SETUP2 store the length behind the chuck instead of the whole length."""
    if "length_inside_mm" not in data:
        return data
    data = dict(data)
    inside = data.pop("length_inside_mm")
    data["length_mm"] = None if inside is None else data["length_outside_mm"] + inside
    return data


def _raw_part_from_data(data: dict) -> RawPart:
    data = dict(_raw_part_data(data))
    outline = data.pop("outline", None)
    return replace(from_data(RawPart, data), outline=None if outline is None else contour_from_dict(outline))


def project_from_dict(data: dict) -> Project:
    try:
        if data["format"] != PROJECT_FORMAT_VERSION:
            raise ProjectError(f"unsupported project format {data['format']!r}")
        program = Program(
            raw_part=_raw_part_from_data(data["raw_part"]),
            tools=tuple(tool_from_dict(item) for item in data["tools"]),
            safety=from_data(Safety, data["safety"]),
            blocks=tuple(_block_from_data(item) for item in data["blocks"]),
            contours=tuple(contour_from_dict(item) for item in data["contours"]),
            workholding=workholding_from_dict(data["workholding"]) if data.get("workholding") is not None else None,
            toolbox_library=data.get("toolbox", {}).get("library", ""), toolbox_name=data.get("toolbox", {}).get("name", ""),
        )
        touched = data.get("touched")
        if touched is not None and not (isinstance(touched, list) and all(isinstance(k, str) for k in touched)):
            raise ProjectError("the list of touched fields is not a list of text")
        project = Project(
            program,
            from_data(ProjectSettings, data["settings"]),
            machine_from_dict(data["machine"]) if data.get("machine") is not None else None,
            None if touched is None else tuple(sorted(set(touched))),
        )
    except ProjectError:
        raise
    except (CodecError, ContourError, ToolError, BlockError, MachineError, WorkholdingError) as error:
        raise ProjectError(str(error)) from error
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ProjectError(f"invalid project data: {error!r}") from error
    problems = program_problems(program)
    if problems:
        raise ProjectError("; ".join(problems))
    return project


def program_problems(program: Program) -> list[str]:
    """Things a block refers to that do not exist."""
    tool_numbers = {tool.number for tool in program.tools}
    contour_ids = {contour.contour_id for contour in program.contours}
    problems = []
    for position, block in enumerate(program.blocks, start=1):
        if block.tool_number != NO_TOOL_NUMBER and block.tool_number not in tool_numbers:
            problems.append(f"block {position}: tool T{block.tool_number} is not in the program")
        for contour_id in block.contour_ids:
            if contour_id not in contour_ids:
                problems.append(f"block {position}: contour {contour_id!r} is not in the program")
    return problems


def project_to_json(project: Project, preview: list[Loop] | None = None) -> str:
    """The file text. `preview`: the loops of the finished part as the last plan made it (V9): written as `"preview"`, so that opening the
    file can show the part at once, before the plan is made again."""
    data = project_to_dict(project)
    if preview:
        data["preview"] = [[_piece_text(piece) for piece in loop] for loop in preview]
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def project_from_json(text: str) -> Project:
    return project_and_preview_from_json(text)[0]


def project_and_preview_from_json(text: str) -> tuple[Project, list[Loop] | None]:
    """The project and the loops of the finished part saved with it (None when the file has none, or they do not read: the picture then
    waits for the plan, nothing else depends on them)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProjectError(f"the file is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise ProjectError("the file does not hold a project")
    project = project_from_dict(data)
    try:
        preview = [tuple(_piece_from_text(piece) for piece in loop) for loop in data.get("preview") or ()] or None
    except (KeyError, TypeError, ValueError):
        preview = None
    return project, preview


def _piece_text(piece: Segment) -> str:
    """One piece of the saved part as a short line of text (the file stays small): `L x z x z` or `A x z x z cx cz CCW|CW`, the numbers
    exact (the shortest text that reads back as the same number)."""
    numbers = [piece.start.x, piece.start.z, piece.end.x, piece.end.z]
    if isinstance(piece, ArcSegment):
        return " ".join(["A", *(repr(plain_number(n)) for n in [*numbers, piece.center.x, piece.center.z]), piece.direction.name])
    return " ".join(["L", *(repr(plain_number(n)) for n in numbers)])


def _piece_from_text(text: str) -> Segment:
    kind, *rest = text.split()
    if kind == "L" and len(rest) == 4:
        x0, z0, x1, z1 = (float(n) for n in rest)
        return LineSegment(Point(x0, z0), Point(x1, z1))
    if kind == "A" and len(rest) == 7:
        x0, z0, x1, z1, cx, cz = (float(n) for n in rest[:6])
        return ArcSegment(Point(x0, z0), Point(x1, z1), Point(cx, cz), ArcDirection[rest[6]])
    raise ValueError(f"not a piece: {text!r}")
