"""The sketch editor without a toolkit: the tools, snapping, selection and undo.

The window (wop/ui/qt/sketch_dialog.py) sends mouse positions in sketch coordinates (x = radius, z = axial) and a
tolerance in millimetres (the snap distance on the screen turned into mm); it draws what `preview_segments`, the
sketch and the selection say.
"""

from __future__ import annotations

import copy
import math
from typing import Callable

from ..core.constants import GEOMETRY_TOLERANCE_MM
from ..core.sketch.constants import ORIGIN
from ..core.geometry import ArcDirection, ArcSegment, LineSegment, Point, Segment
from ..core.contour import Contour
from ..core.sketch.locked import locked_changed, sync_locked
from ..core.sketch.model import Sketch, SketchError, arc_from_three_points
from ..core.sketch.modes import SketchMode, contour_from_sketch, problems as mode_problems, sketch_from_contour
from ..core.sketch.pick import nearest_point, piece_id, piece_points
from ..core.sketch.solver import Analysis, analyse, solve
from .sketch_action_tool import SketchActionToolMixin
from .sketch_dimension_tool import SketchDimensionToolMixin
from .sketch_modify import SketchModifyMixin
from .sketch_target import FREE_TARGET, SketchTarget
from .sketch_relations import SketchRelationsMixin
from .sketch_stepping import SketchSteppingMixin
from .sketch_constants import (
    ORTHO_SNAP_ANGLE_DEG,
    PROMPTS,
    TOOL_ACTION,
    TOOL_ARC_CENTRE,
    TOOL_ARC_THREE,
    TOOL_CIRCLE,
    TOOL_DIMENSION,
    TOOL_LINE,
    TOOL_MIRROR,
    TOOL_POINT,
    TOOL_SELECT,
    TOOL_TRIM,
    DRAG_BACKOFF,
    DRAW_TOOLS,
    LOCKED_MESSAGE,
    UNDO_LIMIT,
)


class SketchSession(SketchSteppingMixin, SketchRelationsMixin, SketchModifyMixin, SketchDimensionToolMixin, SketchActionToolMixin):
    def __init__(self, sketch: Sketch | None = None, target: SketchTarget | None = None) -> None:
        """A session on `sketch`, or on the sketch of the target's contour (raises SketchError if that cannot be read)."""
        self.target = target or FREE_TARGET
        if sketch is None and self.target.start_sketch is not None:
            sketch = copy.deepcopy(self.target.start_sketch)
        if sketch is None and self.target.contour is not None:
            sketch = sketch_from_contour(self.target.contour)
        self.sketch = sketch or Sketch()
        self.notes: list[str] = []  # what was lost when the locked things moved (dimensions removed): shown to the user as a warning
        if self.target.locked_points or self.sketch.locked_points:
            self.notes = sync_locked(self.sketch, self.target.locked_points, self.target.locked_lines, self.target.locked_arcs)
        self.step: int | None = None  # stepping through a path: the current piece (index in the walk), None: everything is shown
        self._walk_cache: tuple[tuple, list[int], str, dict[int, bool]] | None = None
        self.tool = TOOL_SELECT
        self.pending: list[tuple[Point, int | None]] = []  # clicks of the piece being drawn (position, point id if snapped)
        self.hover: Point | None = None
        self.hover_point: int | None = None  # the point the mouse would snap to
        self.selected_points: set[int] = set()
        self.selected_pieces: set[int] = set()
        self.band: tuple[Point, Point] | None = None  # the selection box being dragged
        self.snapping = True
        self.show_relations = True  # the tags of the relations and the dimensions can be hidden; both are shown when the window opens
        self.show_dimensions = True
        self.message = ""
        self._undo: list[Sketch] = []
        self._redo: list[Sketch] = []
        self._listeners: list[Callable[[], None]] = []
        self._drag_mode = ""  # "move" (the selection follows the mouse), "band" (a selection box) or ""
        self._drag_start: Point | None = None
        self._drag_base: dict[int, Point] = {}  # where the points that follow the mouse were when it was pressed
        self._drag_undo: Sketch | None = None  # the sketch at the press, put on the undo list at the first movement
        self.selected_constraint: int | None = None
        self._analysis_cache: tuple[tuple, Analysis] | None = None
        self._problems_cache: tuple[tuple, list[str]] | None = None
        self.trail: list[Point] = []  # the path of the mouse while swiping with the Trim tool (drawn, not part of the sketch)
        self._swipe_before: Sketch | None = None  # the sketch when the swipe began: one Undo entry for the whole swipe
        self._swipe_changed = False
        self._dim_drag: tuple[int, Point, tuple[float, float]] | None = None  # the dimension being moved: id, where, its offset
        self.hover_axis: str | int | None = None  # the line the Mirror tool would mirror about now (a line id, or "z" for the axis)
        self.dim_picks: list[tuple[str, int]] = []  # what the Dimension tool has picked: ("point" | "line" | "arc", id)
        self.action = ""  # the relation or change that is on as a tool (see `armed`), and the value it uses (fillet radius)
        self.action_value = 0.0
        self.mouse: Point | None = None  # the mouse as it is (not snapped), and the snap distance there, for the dimension in hand
        self.mouse_tolerance = 1.0

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    @property
    def mode(self) -> SketchMode:
        return self.target.mode

    @property
    def problems(self) -> list[str]:
        """What stops the sketch from being used for the target (empty: it can be used)."""
        key = self.sketch.signature()
        if self._problems_cache is None or self._problems_cache[0] != key:
            self._problems_cache = (key, mode_problems(self.sketch, self.mode))
        return self._problems_cache[1]

    def result(self) -> Contour:
        """The contour the sketch draws (with the sketch kept inside). Raises SketchError with the reasons."""
        start = self.target.contour
        return contour_from_sketch(
            self.sketch, self.mode, start.contour_id if start else "sketch", start.name if start else "Sketch"
        )

    def hidden_points(self) -> set[int]:
        """The edge points of circles. A circle is its centre and its size; the point on its edge is only a handle to
        drag the size, shown while the circle is selected. (A point that has a name or belongs to another piece stays.)"""
        named = set(self.sketch.labels.values())
        pieces = self.sketch.pieces()
        hidden = set(self.sketch.helpers) | self.stepped_hidden_points()  # the mirror points of diameter dimensions are never shown
        for arc in self.sketch.arcs.values():
            edge = arc.start
            if arc.start != arc.end or arc.arc_id in self.selected_pieces or edge in self.selected_points or edge in named:
                continue
            if not any(edge in piece_points(p) for p in pieces if piece_id(p) != arc.arc_id):
                hidden.add(edge)
        return hidden

    def pickable_point(self, position: Point, tolerance: float, skip: tuple[int, ...] = ()) -> int | None:
        """The point of the sketch near the position, not counting the hidden handles of circles."""
        return nearest_point(self.sketch, position, tolerance, skip=(*skip, *self.hidden_points()))

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def prompt(self) -> str:
        return self.action_prompt if self.tool == TOOL_ACTION else dict(PROMPTS)[self.tool]

    def refresh(self) -> None:
        """Tell the window to draw again (after the message changed, for example)."""
        self._notify()

    def select_constraint(self, constraint_id: int | None) -> None:
        self.selected_constraint = constraint_id
        self._notify()

    def available_tool(self, tool: str) -> bool:
        """Can this tool be turned on now? (Mirror needs something selected to mirror; the others always.)"""
        return tool != TOOL_MIRROR or self.tool == TOOL_MIRROR or bool(self.selected_pieces)

    def set_tool(self, tool: str) -> None:
        if not self.available_tool(tool):
            self.message = "Select what to mirror first, then click the Mirror button"
            self._notify()
            return
        if tool in DRAW_TOOLS and self.step is not None:  # a new piece goes to the end of the path: show it all
            self.step = None
        self.hover_axis = None
        self.pending = []
        if not (tool == TOOL_MIRROR and self.tool != TOOL_MIRROR):  # Mirror is the one tool that acts on the selection made before
            self.selected_points, self.selected_pieces = set(), set()  # a new mode (and Esc) drops every selection
            self.selected_constraint = None
        self.dim_picks = []
        self.tool = tool
        self.message = ""
        self._notify()

    # --- undo ---------------------------------------------------------------------------------------------------------

    def _push_undo(self) -> None:
        self._undo.append(copy.deepcopy(self.sketch))
        del self._undo[:-UNDO_LIMIT]
        self._redo = []

    def undo(self) -> None:
        if self._undo:
            self._redo.append(self.sketch)
            self.sketch = self._undo.pop()
            self._after_history()

    def redo(self) -> None:
        if self._redo:
            self._undo.append(self.sketch)
            self.sketch = self._redo.pop()
            self._after_history()

    def _edit(self, change: Callable[[], None], record: bool = True) -> bool:
        """Make a change, solve, and keep it only if the relations still hold; otherwise everything stays as it was.
        `record` False leaves the Undo list alone (the caller puts one entry for a whole series of changes)."""
        before = copy.deepcopy(self.sketch)
        self.message = ""
        try:
            change()
            result = solve(self.sketch)
        except SketchError as error:
            self.sketch = before
            self.message = str(error)
            return False
        if not result.converged:
            self.sketch = before
            self.message = "That does not fit the relations and dimensions that are there"
            return False
        if self._collapsed(self.sketch) - self._collapsed(before):
            self.sketch = before
            self.message = "That would shrink a line or an arc to nothing"
            return False
        if locked_changed(before, self.sketch):
            self.sketch = before
            self.message = LOCKED_MESSAGE
            return False
        if record:
            self._push_snapshot(before)
        return True

    def _push_snapshot(self, before: Sketch) -> None:
        self._undo.append(before)
        del self._undo[:-UNDO_LIMIT]
        self._redo = []

    @staticmethod
    def _collapsed(sketch: Sketch) -> set[int]:
        """Ids of the lines and arcs that have no length or radius."""
        return {
            piece_id(piece)
            for piece in sketch.pieces()
            if sketch.points[piece.start].position.distance_to(
                sketch.points[piece.centre if hasattr(piece, "centre") else piece.end].position
            )
            <= GEOMETRY_TOLERANCE_MM
        }

    @property
    def analysis(self) -> Analysis:
        """How far the sketch is defined (worked out again only when the sketch changed)."""
        key = self.sketch.signature()
        if self._analysis_cache is None or self._analysis_cache[0] != key:
            self._analysis_cache = (key, analyse(self.sketch))
        return self._analysis_cache[1]

    def _after_history(self) -> None:
        self.selected_constraint = None
        self.pending = []
        self.selected_points = set()
        self.selected_pieces = set()
        self._notify()

    # --- snapping -----------------------------------------------------------------------------------------------------

    def snap(self, position: Point, tolerance: float) -> tuple[Point, int | None]:
        """A point of the sketch close to `position`, else the position made horizontal/vertical to the last click."""
        if not self.snapping:
            return position, None
        found = self.pickable_point(position, tolerance)
        if found is not None:
            return self.sketch.point(found).position, found
        if self.pending:
            origin = self.pending[-1][0]
            dx, dz = position.x - origin.x, position.z - origin.z
            length = math.hypot(dx, dz)
            if length > 0:
                limit = math.sin(math.radians(ORTHO_SNAP_ANGLE_DEG))
                if abs(dx) / length <= limit:
                    position = Point(origin.x, position.z)
                elif abs(dz) / length <= limit:
                    position = Point(position.x, origin.z)
        return position, None

    def move_hover(self, position: Point, tolerance: float) -> None:
        if self._drag_mode:
            return
        self.hover, self.hover_point = self.snap(position, tolerance)
        self.mouse, self.mouse_tolerance = position, tolerance
        self.hover_axis = self.mirror_axis_at(position, tolerance) if self.tool == TOOL_MIRROR else None
        self._notify()

    # --- mouse --------------------------------------------------------------------------------------------------------

    def press(self, position: Point, tolerance: float, add: bool = False) -> None:
        """Select tool: pick (`add` = Ctrl: toggle in the selection), then drag the selection or start a selection box."""
        if self.tool == TOOL_ACTION:
            self.action_click(position, tolerance)
            return
        if self.tool == TOOL_TRIM:
            self.begin_swipe(position, tolerance)
            return
        if self.tool == TOOL_DIMENSION:
            self.dimension_click(position, tolerance)
            return
        if self.tool == TOOL_MIRROR:
            self.mirror_at(position, tolerance)
            return
        if self.tool == TOOL_POINT:
            self.point_at(position, tolerance)
            return
        if self.tool != TOOL_SELECT:
            self._click(position, tolerance)
            self._notify()
            return
        hit_point = self.pickable_point(position, tolerance)
        hit_piece = None if hit_point is not None else self.pick_piece(position, tolerance)
        if hit_point is None and hit_piece is None:
            dimension = self.dimension_at(position, tolerance)
            if dimension is not None and not add:  # the line of a dimension: it can be moved
                self.selected_points, self.selected_pieces = set(), set()
                self.begin_dimension_drag(dimension, position)
                return
            if not add:
                self.selected_points, self.selected_pieces = set(), set()
            self._drag_mode, self.band = "band", (position, position)
        else:
            hit = hit_point if hit_point is not None else piece_id(hit_piece)
            locked = self.sketch.is_locked_point(hit) if hit_point is not None else self.sketch.is_locked_piece(hit)
            self.message = LOCKED_MESSAGE if locked else ""
            chosen = self.selected_points if hit_point is not None else self.selected_pieces
            if add:
                chosen.symmetric_difference_update({hit})
            elif hit not in chosen:
                self.selected_points, self.selected_pieces = set(), set()
                (self.selected_points if hit_point is not None else self.selected_pieces).add(hit)
            if self.selected_points or self.selected_pieces:
                self._drag_undo = copy.deepcopy(self.sketch)
                self._drag_mode, self._drag_start = "move", position
                self._drag_base = {i: self.sketch.point(i).position for i in self._moving_points()}
        self._notify()

    def drag(self, position: Point, tolerance: float) -> None:
        if self._drag_mode == "move" and self._drag_start is not None:
            self._move_selection(position)
        elif self._drag_mode == "band" and self.band is not None:
            self.band = (self.band[0], position)
        elif self._drag_mode == "swipe":
            self.swipe_to(position, tolerance)
        elif self._drag_mode == "dimension":
            self.move_dimension(position)
        else:
            return
        self._notify()

    def _move_selection(self, position: Point) -> None:
        """Follow the mouse; with relations (or arcs) the solver decides how far each point really goes."""
        dx, dz = position.x - self._drag_start.x, position.z - self._drag_start.z
        targets = {i: Point(base.x + dx, base.z + dz) for i, base in self._drag_base.items()}
        if self._drag_undo is not None:  # the first movement: now it is a change that can be undone
            self._undo.append(self._drag_undo)
            del self._undo[:-UNDO_LIMIT]
            self._redo = []
            self._drag_undo = None
        if not self.sketch.constraints and not self.sketch.arcs:
            for point_id, target in targets.items():
                self.sketch.move_point(point_id, target.x, target.z)
            return
        kept = {i: p.position for i, p in self.sketch.points.items()}
        for part in DRAG_BACKOFF:  # the whole pull first; if the relations cannot hold with it, a part of it
            pull = {i: Point(kept[i].x + part * (t.x - kept[i].x), kept[i].z + part * (t.z - kept[i].z)) for i, t in targets.items()}
            solve(self.sketch, pull)  # pulls softly: the relations may keep a point back
            if solve(self.sketch).converged:  # polish: the relations must hold exactly
                return
            for point_id, point in kept.items():
                self.sketch.move_point(point_id, point.x, point.z)

    def release(self, position: Point, tolerance: float, add: bool = False) -> None:
        if self._drag_mode == "swipe":
            self.end_swipe()
        elif self._drag_mode == "band" and self.band is not None:
            self._select_in_box(self.band[0], position, add)
        elif self._drag_mode == "move" and len(self.selected_points) == 1 and not self.selected_pieces:
            (moved,) = self.selected_points
            target = self.pickable_point(position, tolerance, skip=(moved,))
            if target is not None and self.snapping:  # dropped on another point: they become one
                if self._edit(lambda: self.sketch.merge_points(target, moved)):
                    self.selected_points = {target}
        self._drag_mode, self.band, self._drag_start, self._drag_undo = "", None, None, None
        self._drag_base = {}
        self._notify()

    def _moving_points(self) -> set[int]:
        """The selected points and every point of the selected pieces (a shared point moves all pieces on it), but not the
        locked ones: the pieces that end on them stretch."""
        moving = set(self.selected_points)
        for piece in self.sketch.pieces():
            if piece_id(piece) in self.selected_pieces:
                moving |= piece_points(piece)
        for arc in self.sketch.arcs.values():  # a circle follows its centre; its edge point is only a handle
            if arc.start == arc.end and arc.centre in moving and arc.start not in self.selected_points:
                moving.add(arc.start)
        return {i for i in moving if not self.sketch.is_locked_point(i)}

    def _select_in_box(self, corner: Point, other: Point, add: bool) -> None:
        low_x, high_x = sorted((corner.x, other.x))
        low_z, high_z = sorted((corner.z, other.z))
        inside = {
            point_id
            for point_id, point in self.sketch.points.items()
            if low_x <= point.x <= high_x and low_z <= point.z <= high_z and point_id not in self.sketch.helpers  # the mirror points are hidden
        }
        pieces = {piece_id(piece) for piece in self.sketch.selectable_pieces() if piece_points(piece) <= inside}
        if add:
            inside |= self.selected_points
            pieces |= self.selected_pieces
        self.selected_points, self.selected_pieces = inside, pieces

    def cancel(self) -> None:
        """End what is being drawn (right click); the tool stays on."""
        self.pending = []
        if self.tool == TOOL_DIMENSION:
            self.clear_dimension_picks()
        if self.tool == TOOL_ACTION and not self.clear_action_picks():
            self.set_tool(TOOL_SELECT)  # nothing was picked: the right click turns the tool off
            return
        self.message = ""
        self._notify()

    def escape(self) -> None:
        """Esc: end what is being drawn and go back to selecting; in selecting, end the stepping through a path."""
        if self.tool == TOOL_SELECT and self.step is not None:
            self.stop_stepping()
            return
        self.set_tool(TOOL_SELECT)

    def delete_selected(self) -> None:
        """Delete the selected pieces and every piece that uses a selected point."""
        kept = {i for i in self.selected_points if self.sketch.is_locked_point(i)}
        kept_pieces = {i for i in self.selected_pieces if self.sketch.is_locked_piece(i)}
        self.selected_points, self.selected_pieces = self.selected_points - kept, self.selected_pieces - kept_pieces
        doomed = set(self.selected_pieces)
        for piece in self.sketch.pieces():
            if piece_points(piece) & self.selected_points:
                doomed.add(piece_id(piece))
        used = {p for piece in self.sketch.pieces() for p in piece_points(piece)}
        alone = self.selected_points - used - {ORIGIN}  # points of their own (named points); the origin is no point of the sketch
        if doomed or alone:
            self._push_undo()
            for one in sorted(doomed):
                if one in self.sketch.lines or one in self.sketch.arcs:  # the pieces of a fillet or chamfer go together: one may be gone already
                    self.sketch.delete_piece(one)
            for one in alone:
                if one in self.sketch.points:  # deleting the pieces may have taken it already (a mirror point of a diameter)
                    self.sketch.delete_point(one)
        self.selected_points, self.selected_pieces = set(), set()
        self.message = LOCKED_MESSAGE if kept or kept_pieces else ""
        self._notify()

    # --- draw ---------------------------------------------------------------------------------------------------------

    def _click(self, position: Point, tolerance: float) -> None:
        snapped, point_id = self.snap(position, tolerance)
        self.pending.append((snapped, point_id))
        self.message = ""
        try:
            if self.tool == TOOL_LINE and len(self.pending) == 2:
                self._finish_line()
            elif self.tool == TOOL_CIRCLE and len(self.pending) == 2:
                self._finish_circle()
            elif self.tool == TOOL_ARC_CENTRE and len(self.pending) == 3:
                self._finish_arc_by_centre()
            elif self.tool == TOOL_ARC_THREE and len(self.pending) == 3:
                self._finish_arc_by_three()
        except SketchError as error:
            self.message = str(error)  # the finishing step already took the bad click back

    def _point_id(self, entry: tuple[Point, int | None]) -> int:
        position, point_id = entry
        return point_id if point_id is not None else self.sketch.add_point(position.x, position.z)

    def _finish_line(self) -> None:
        (start, start_id), (end, end_id) = self.pending
        if start_id is not None and start_id == end_id or start.is_close(end):
            self.pending = self.pending[:1]
            raise SketchError("a line needs two different points")
        self._push_undo()
        first = self._point_id(self.pending[0])
        last = self._point_id(self.pending[1])
        self.sketch.add_line(first, last)
        self.pending = [(self.sketch.point(last).position, last)]  # the next line continues from here

    def _finish_circle(self) -> None:
        (centre, _), (edge, _) = self.pending
        if centre.is_close(edge):
            self.pending = self.pending[:1]
            raise SketchError("the circle has no radius")
        self._push_undo()
        centre_id, edge_id = self._point_id(self.pending[0]), self._point_id(self.pending[1])
        self.sketch.add_arc(centre_id, edge_id, edge_id)  # start and end are one point: a full circle
        self.pending = []

    def _finish_arc_by_centre(self) -> None:
        (centre, _), (start, _), (end, _) = self.pending
        radius = centre.distance_to(start)
        if radius == 0 or centre.distance_to(end) == 0:
            self.pending = self.pending[:2]
            raise SketchError("the arc has no radius")
        end = Point(centre.x + (end.x - centre.x) * radius / centre.distance_to(end), centre.z + (end.z - centre.z) * radius / centre.distance_to(end))
        cross = (start.x - centre.x) * (end.z - centre.z) - (start.z - centre.z) * (end.x - centre.x)
        self._push_undo()
        ids = [self._point_id(self.pending[0]), self._point_id(self.pending[1]), self.sketch.add_point(end.x, end.z)]
        self.sketch.add_arc(ids[0], ids[1], ids[2], ArcDirection.CCW if cross >= 0 else ArcDirection.CW)
        self.pending = []

    def _finish_arc_by_three(self) -> None:
        (start, _), (end, _), (through, _) = self.pending
        try:
            centre, direction = arc_from_three_points(start, through, end)
        except SketchError:
            self.pending = self.pending[:2]
            raise
        self._push_undo()
        start_id, end_id = self._point_id(self.pending[0]), self._point_id(self.pending[1])
        centre_id = self.sketch.add_point(centre.x, centre.z)
        self.sketch.add_arc(centre_id, start_id, end_id, direction)
        self.pending = []

    # --- picture ------------------------------------------------------------------------------------------------------

    def preview_segments(self) -> list[Segment]:
        """The piece being drawn, up to the mouse position (empty when nothing is being drawn)."""
        if self.hover is None or not self.pending:
            return []
        hover = self.hover
        points = [entry[0] for entry in self.pending]
        try:
            if self.tool == TOOL_LINE and not points[0].is_close(hover):
                return [LineSegment(points[0], hover)]
            if self.tool == TOOL_CIRCLE and not points[0].is_close(hover):
                return [ArcSegment(hover, hover, points[0], ArcDirection.CCW)]
            if self.tool == TOOL_ARC_CENTRE:
                return self._preview_centre_arc(points, hover)
            if self.tool == TOOL_ARC_THREE:
                return self._preview_three_arc(points, hover)
        except (SketchError, ValueError):
            return []
        return []

    def _preview_centre_arc(self, points: list[Point], hover: Point) -> list[Segment]:
        if len(points) == 1:
            return [LineSegment(points[0], hover)] if not points[0].is_close(hover) else []
        centre, start = points
        reach = centre.distance_to(hover)
        radius = centre.distance_to(start)
        if reach == 0 or radius == 0:
            return []
        end = Point(centre.x + (hover.x - centre.x) * radius / reach, centre.z + (hover.z - centre.z) * radius / reach)
        cross = (start.x - centre.x) * (end.z - centre.z) - (start.z - centre.z) * (end.x - centre.x)
        return [ArcSegment(start, end, centre, ArcDirection.CCW if cross >= 0 else ArcDirection.CW)]

    def _preview_three_arc(self, points: list[Point], hover: Point) -> list[Segment]:
        if len(points) == 1:
            return [LineSegment(points[0], hover)] if not points[0].is_close(hover) else []
        start, end = points
        centre, direction = arc_from_three_points(start, hover, end)
        return [ArcSegment(start, end, centre, direction)]
