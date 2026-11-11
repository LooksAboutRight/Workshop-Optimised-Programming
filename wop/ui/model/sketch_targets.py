"""What the sketch editor can be opened for: a contour of the part, a tool shape, a workholding outline."""

from __future__ import annotations

from dataclasses import replace

from ...core.blocks.custom_path import CustomPathBlock
from ...core.blocks.path_locked import path_locked_items
from ...core.contour_solver import build_contour
from ...core.geometry import Point
from ...core.program_model.raw_outline import starting_sketch
from ...core.program_model.stock import stock_region
from ...core.sketch.model import Sketch
from ...core.sketch.modes import PATH, RAW_PART, TOOL, TURNING, WORKHOLDING, contour_from_sketch
from ...core.sketch.sketch_io import sketch_from_dict
from ...core.tooling.tool_shape import shape_to_definition
from ...core.program_model.units import XInputMode
from ...core.lathe.workholding import library_find
from ..app_constants import DEFAULT_STOCK_INSIDE_MM
from ..point_kinds import RAW_PART_POINT_KINDS, TOOL_POINT_KINDS, WORKHOLDING_POINT_KINDS
from ..sketch_target import SketchTarget
from .helpers import ModelError

TOOL_SKETCH_ID = "tool_shape"


class SketchTargetsMixin:
    """Targets of the sketch editor. (A part of AppModel: it uses the attributes that AppModel.__init__ sets.)"""

    def contour_sketch_target(self, contour_id: str) -> SketchTarget:
        stored = next((c for c in self.program.contours if c.contour_id == contour_id), None)
        if stored is None:
            raise ModelError(f"there is no contour {contour_id!r}")
        scale = 2 if self.x_mode() is XInputMode.DIAMETER else 1

        def commit(contour) -> None:
            self.set_contour(replace(contour, contour_id=stored.contour_id, name=stored.name))

        return SketchTarget(TURNING, f"Sketch of {stored.name}", stored, (), scale, commit)

    def raw_part_sketch_target(self) -> SketchTarget:
        """The raw part of the Setup: the drawing it has, else its bar or tube as a first drawing to change."""
        raw = self.program.raw_part
        outline = raw.outline
        if outline is None:
            inside = raw.length_inside_mm
            behind = DEFAULT_STOCK_INSIDE_MM if not inside else inside  # a bar through the spindle (or one that ends at the jaws): some length behind them
            outline = contour_from_sketch(starting_sketch(raw, raw.clamp_z_mm - behind), RAW_PART, "raw_part", "Raw part")
        scale = 2 if self.x_mode() is XInputMode.DIAMETER else 1
        return SketchTarget(RAW_PART, "Raw part", outline, RAW_PART_POINT_KINDS, scale, self.draw_raw_part)

    def path_sketch_target(self, index: int) -> SketchTarget:
        """The drawing of the custom path block `index`, with the safe point and the part before the block as locked things."""
        block = self.blocks[index]
        if not isinstance(block, CustomPathBlock):
            raise ModelError("this block is not a custom path")
        sketch = Sketch() if block.sketch is None else sketch_from_dict(block.sketch)
        safety = self.program.safety
        plan = self.analysis.plan
        block_plan = None if plan is None else next((b for b in plan.blocks if b.program_index == index), None)
        residual = stock_region(self.program.raw_part) if block_plan is None else block_plan.residual_before
        points, lines, arcs = path_locked_items(Point(safety.safe_radius_mm, safety.safe_z_mm), residual)
        scale = 2 if self.x_mode() is XInputMode.DIAMETER else 1

        def commit(contour) -> None:
            self.replace_block(index, replace(block, sketch=contour.sketch))

        return SketchTarget(
            PATH, f"Path of {block.title}", None, (), scale, commit, sketch, points, lines, arcs,
        )

    def tool_sketch_target(self, number: int) -> SketchTarget:
        try:
            tool = self.program.tool(number)
        except ValueError as error:
            raise ModelError(str(error)) from error
        contour = build_contour(TOOL_SKETCH_ID, tool.name, shape_to_definition(tool.shape, tool.points))
        contour = replace(contour, sketch=tool.sketch)
        return SketchTarget(TOOL, f"Shape of T{number} {tool.name}", contour, TOOL_POINT_KINDS, 1, lambda c: self.set_tool_shape(number, c))

    def workholding_sketch_target(self, name: str) -> SketchTarget:
        item = library_find(self.workholding_library, name)
        if item is None:
            raise ModelError(f"there is no workholding item {name!r}")
        kinds = WORKHOLDING_POINT_KINDS.get(item.kind, ())
        return SketchTarget(WORKHOLDING, f"Shape of {name}", item.outline, kinds, 1, lambda c: self.set_workholding_shape(name, c))
