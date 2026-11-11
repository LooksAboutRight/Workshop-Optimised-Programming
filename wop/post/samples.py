"""Sample output for the post editor: what one concept writes, with fixed built-in values (not a project).

Two results per concept: "present" (every optional part there, every "if changed" token counts as changed, the neighbours of
a tool or block exist) and "absent" (nothing changed, optional parts gone, no previous or next tool or block). The values are
fixed so that the output is the same every time and can be tested.
"""

from __future__ import annotations

from datetime import datetime

from ..core.geometry import ArcDirection, Point
from ..core.program_model.operations import BlockBegin, DrillMode, DrillOperation, SpindleDirection, ThreadOperation, ThreadTaper
from ..core.program_model.units import XInputMode
from .base import PostSettings
from .concepts import DRILL_CYCLES
from .context import BlockInfo, PostContext, ToolInfo
from .engine import TemplatePost
from .post_definition import PostDefinition
from .variables import sample_values

SAMPLE_TITLE = "Sample part"
SAMPLE_CLOCK = datetime(2026, 1, 15, 9, 30)
SAMPLE_TOOLS = (
    ToolInfo(1, "Rough 80", "holder", 1, "carbide", 0.8, 3),
    ToolInfo(2, "Finish 35", "holder", 2, "carbide", 0.4, 3),
    ToolInfo(3, "Groove 3", "holder", 3, "carbide", None, None),
)
SAMPLE_BLOCKS = (BlockInfo(1, "Face", "facing", 1), BlockInfo(2, "Rough", "turning", 2), BlockInfo(3, "Finish", "turning", 1))
SAMPLE_START = Point(5.0, 2.0)  # where the tool stood before the move
SAMPLE_END = Point(12.5, -3.0)
SAMPLE_RPM = 1000
SAMPLE_FEED = 0.2
SAMPLE_NOTES = ("a note for the operator",)
SAMPLE_COMMENT = "sample comment (with brackets)"


def sample_context(present: bool) -> PostContext:
    tools = {tool.number: tool for tool in SAMPLE_TOOLS}
    if present:
        sequence, blocks = (3, 1, 2), SAMPLE_BLOCKS
    else:
        sequence, blocks = (1,), SAMPLE_BLOCKS[1:2]
    return PostContext(
        project_title=SAMPLE_TITLE, machine_name="Sample lathe", material="steel", part_diameter_mm=40, part_length_mm=60,
        tools=tools, blocks=blocks, tool_sequence=sequence, now=SAMPLE_CLOCK, path_length_mm=1234.5, estimated_time_min=12.5,
    )


def _thread(present: bool) -> ThreadOperation:
    return ThreadOperation(
        start_x=11, start_z=2, end_z=-20, pitch_mm=1.5, peak_offset_mm=-1, first_cut_mm=0.2, depth_mm=0.92, degression=1,
        compound_angle_deg=29.5, spring_passes=2,
        taper=ThreadTaper.BOTH if present else ThreadTaper.NONE, taper_distance_mm=3 if present else 0,
    )


def _drill(present: bool) -> DrillOperation:
    if present:
        return DrillOperation(retract_z=2, end_z=-10, feed_mm_per_rev=0.1, peck_depth_mm=3, mode=DrillMode.PECK, dwell_s=0.5)
    return DrillOperation(retract_z=2, end_z=-10, feed_mm_per_rev=0.1)


def _scope(concept: str, present: bool) -> dict:
    move = {"x": SAMPLE_END.x, "z": SAMPLE_END.z}
    if concept == "feed":
        return {**move, "feed": SAMPLE_FEED}
    if concept in ("arc_ccw", "arc_cw"):
        center = Point(SAMPLE_START.x, SAMPLE_END.z)
        direction = ArcDirection.CCW if concept == "arc_ccw" else ArcDirection.CW
        return {
            **move, "feed": SAMPLE_FEED, "start_x": SAMPLE_START.x, "start_z": SAMPLE_START.z, "center_x": center.x,
            "center_z": center.z, "start": SAMPLE_START, "end": SAMPLE_END, "center": center, "direction": direction,
        }
    if concept == "machine_rapid":
        return move
    if concept == "dwell":
        return {"seconds": 1.5}
    if concept == "spindle_css":
        return {"value": 120, "rpm_limit": 3000 if present else None, "direction": SpindleDirection.CLOCKWISE}
    if concept == "spindle_rpm":
        return {"value": 1200, "rpm_limit": None, "direction": SpindleDirection.CLOCKWISE}
    if concept in ("thread_cycle", "thread_two_block", "thread_passes"):
        op = _thread(present)
        return {"op": op, "start_x": op.start_x, "start_z": op.start_z}
    if concept in DRILL_CYCLES:
        return {"op": _drill(present), "feed": 0.1}
    if concept == "comment":
        return {"text": SAMPLE_COMMENT}
    if concept == "note_entry":
        return {"note": SAMPLE_NOTES[0]}
    if concept == "tool_entry":
        return {"tool": SAMPLE_TOOLS[0] if present else SAMPLE_TOOLS[2]}
    if concept == "header":
        return {"notes": list(SAMPLE_NOTES) if present else []}
    return move


def render_sample(
    definition: PostDefinition, concept: str, present: bool, x_mode: XInputMode = XInputMode.DIAMETER,
) -> list[str]:
    """The lines a concept writes for the sample values. Raises PostError when the template cannot be written."""
    engine = TemplatePost(definition, sample_context(present))
    engine.preview = present
    engine.settings = PostSettings(x_mode)
    engine.state.x, engine.state.z = SAMPLE_START.x, SAMPLE_START.z
    engine.state.rpm = SAMPLE_RPM
    blocks = engine.context.blocks
    engine.state.block = blocks[1] if present else blocks[0]
    if concept == "tool_change":
        engine.state.tool_cursor = 1 if present else 0
        return engine.tool_change(1)
    if concept == "block_start":
        return engine.block_begin(BlockBegin(1 if present else 0, "b", engine.state.block.type_name, engine.state.block.name))
    if concept in definition.functions:
        return engine.render_concept(concept, {"variables": sample_values(definition.functions[concept].variables, present)})
    return engine.render_concept(concept, _scope(concept, present))
