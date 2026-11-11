"""Changes to existing sketch pieces in the sketch editor: construction on/off, fillet, chamfer, mirror, trim.

A part of `SketchSession` (a mixin: it uses the attributes and `_edit` of the session).
"""

from __future__ import annotations

import copy
import re
from dataclasses import replace
from pathlib import Path

from ..adapters.dxf_files import read_dxf
from ..core.contour import ContourError
from ..core.contour_solver import build_contour
from ..core.dxf_contour import DxfAxes, contour_from_drawing, shape_from_drawing
from ..core.geometry import LineSegment, Point
from ..core.sketch.corners import chamfer_corner, fillet_corner, is_corner
from ..core.geometry.intersect import intersections
from ..core.sketch.modes import TURNING, sketch_from_contour
from ..core.sketch.mirror import AXIS_Z, mirror_pieces
from ..core.sketch.model import SketchError
from ..core.geometry.distance import distance_to_segment
from ..core.sketch.pick import piece_id
from ..core.sketch.trim import trim_piece
from .sketch_constants import SWIPE_TRIM_LIMIT, TOOL_SELECT



class SketchModifyMixin:
    # --- construction -------------------------------------------------------------------------------------------------

    def toggle_construction(self) -> bool:
        """Turn the selected pieces into helper (construction) pieces, or back into real ones."""
        chosen = sorted(self.selected_pieces)
        if not chosen:
            self.message = "Select the pieces first"
            self._notify()
            return False

        def flip() -> None:
            for one in chosen:
                current = self.sketch.lines[one] if one in self.sketch.lines else self.sketch.arcs[one]
                changes = {"construction": not current.construction}
                if current.construction and one in self.sketch.lines:  # a real line again: no longer a corner reference
                    changes["reference"] = False
                    changes["centre_line"] = False
                self.sketch.update_piece(one, **changes)

        ok = self._edit(flip)
        self._notify()
        return ok

    def toggle_centre(self) -> bool:
        """Make the selected lines centre lines (helper lines that dimensions are measured across, as diameters), or normal
        lines again when they all are centre lines already."""
        chosen = [i for i in sorted(self.selected_pieces) if i in self.sketch.lines]
        if not chosen:
            self.message = "Select the lines first"
            self._notify()
            return False
        make = not all(self.sketch.lines[i].centre_line for i in chosen)

        def flip() -> None:
            for one in chosen:
                self.sketch.update_piece(one, centre_line=make, construction=make)

        ok = self._edit(flip)
        self._notify()
        return ok

    def toggle_cutting(self) -> bool:
        """Mark the selected pieces as cutting edges of the tool, or take the mark off."""
        chosen = sorted(self.selected_pieces)
        if not chosen:
            self.message = "Select the pieces first"
            self._notify()
            return False

        def flip() -> None:
            for one in chosen:
                current = self.sketch.lines[one] if one in self.sketch.lines else self.sketch.arcs[one]
                self.sketch.update_piece(one, cutting=not current.cutting)

        ok = self._edit(flip)
        self._notify()
        return ok

    def toggle_rapid(self) -> bool:
        """Make the selected lines rapid moves of the path, or feed moves again when they all are rapid already."""
        chosen = [i for i in sorted(self.selected_pieces) if i in self.sketch.lines]
        if not chosen:
            self.message = "Select lines first: an arc is always a feed move"
            self._notify()
            return False
        make = not all(i in self.sketch.rapid_pieces for i in chosen)

        def flip() -> None:
            for one in chosen:
                (self.sketch.rapid_pieces.add if make else self.sketch.rapid_pieces.discard)(one)
                if make:
                    self.sketch.piece_feeds.pop(one, None)  # a rapid has no feed: the control sets its speed

        ok = self._edit(flip)
        self._notify()
        return ok

    def set_piece_feed(self, feed_mm_per_rev: float | None) -> bool:
        """Give the selected pieces a feed of their own (mm per revolution), or take it away (None: the feed of the block)."""
        chosen = [i for i in sorted(self.selected_pieces) if i not in self.sketch.rapid_pieces]
        if not chosen:
            self.message = "Select the pieces first" if not self.selected_pieces else "A rapid move has no feed: the control sets its speed"
            self._notify()
            return False

        def put() -> None:
            for one in chosen:
                if feed_mm_per_rev is None:
                    self.sketch.piece_feeds.pop(one, None)
                else:
                    self.sketch.piece_feeds[one] = feed_mm_per_rev

        ok = self._edit(put)
        self._notify()
        return ok

    # --- points -------------------------------------------------------------------------------------------------------

    def point_at(self, position: Point, tolerance: float) -> None:
        """The Point tool: select the point that is there, else put a new one (it is only a point until it gets a name)."""
        found = self.pickable_point(position, tolerance)
        if found is None:
            made: list[int] = []
            if self._edit(lambda: made.append(self.sketch.add_point(position.x, position.z))):
                found = made[0]
        self.selected_points, self.selected_pieces = (set(), set()) if found is None else ({found}, set())
        self._notify()

    def name_point(self, name: str) -> bool:
        """Give the selected point a name (an empty name takes the name away)."""
        if len(self.selected_points) != 1:
            self.message = "Select one point first"
            self._notify()
            return False
        (point_id,) = self.selected_points
        ok = self._edit(lambda: self.sketch.label_point(point_id, name) if name else self.sketch.unlabel_point(point_id))
        self._notify()
        return ok

    def toggle_point_name(self, kind_name: str) -> bool:
        """Give the selected point the name of this kind of point, or take it away when it has that name already. The name of a
        kind there can be several of (steps of jaws) is numbered: step 1, step 2 ..."""
        if len(self.selected_points) != 1:
            self.message = "Select one point first"
            self._notify()
            return False
        (point_id,) = self.selected_points
        kind = next(k for k in self.target.point_kinds if k.name == kind_name)
        label = self.sketch.label_of(point_id)
        if label and (label == kind.name or (kind.numbered and re.fullmatch(re.escape(kind.name) + r" \d+", label))):
            name = ""  # the same button again takes the name away
        elif kind.numbered:
            name = next(f"{kind.name} {n}" for n in range(1, len(self.sketch.labels) + 2) if f"{kind.name} {n}" not in self.sketch.labels)
        else:
            name = kind.name
        ok = self.name_point(name)
        self.selected_points &= set(self.sketch.points)  # a point on its own that lost its name is gone
        return ok

    # --- corners ------------------------------------------------------------------------------------------------------

    def corner_points(self) -> list[int]:
        """The selected points where exactly two real pieces (lines or arcs) meet and nothing else."""
        return [point_id for point_id in sorted(self.selected_points) if is_corner(self.sketch, point_id)]

    def apply_corner(self, kind: str, value: float) -> bool:
        corners = self.corner_points()
        if not corners:
            self.message = "Select a point where two lines or arcs meet"
            self._notify()
            return False
        make = fillet_corner if kind == "fillet" else chamfer_corner

        def change() -> None:
            for point_id in corners:
                make(self.sketch, point_id, value)

        ok = self._edit(change)
        if ok:
            self.selected_points = set()
        self._notify()
        return ok

    # --- mirror -------------------------------------------------------------------------------------------------------

    def mirror_axis_at(self, position: Point, tolerance: float) -> str | int | None:
        """The line under the mouse that can be the mirror line: any line (a construction or centre line too), else the spindle
        axis of a turning contour. An arc cannot. None: no line there."""
        found = [
            (distance_to_segment(position, self.sketch.segment(line)), line.line_id) for line in self.sketch.lines.values()
        ]
        near = [item for item in found if item[0] <= tolerance]
        if near:
            return min(near)[1]
        if self.mode.centre_line and abs(position.x) <= tolerance:
            return AXIS_Z
        return None

    def mirror_at(self, position: Point, tolerance: float) -> bool:
        """The Mirror tool was clicked on a line: the selected pieces are mirrored about it (the line itself is left out), the
        copies are selected and the tool is off."""
        axis = self.mirror_axis_at(position, tolerance)
        if axis is None:
            self.message = "Click a line to mirror about (Esc stops)"
            self._notify()
            return False
        pieces = sorted(i for i in self.selected_pieces if i != axis)
        if not pieces:
            self.message = "There is nothing to mirror: the selection is only that line"
            self._notify()
            return False
        created: list[int] = []
        ok = self._edit(lambda: created.extend(mirror_pieces(self.sketch, pieces, axis)))
        if ok:
            self.set_tool(TOOL_SELECT)
            self.selected_points, self.selected_pieces = set(), set(created)  # the copies stay selected
        self._notify()
        return ok

    def available_modify(self, name: str) -> bool:
        if name in ("construction", "cutting"):
            return bool(self.selected_pieces)
        if name == "rapid":
            return any(i in self.sketch.lines for i in self.selected_pieces)
        if name == "centre":
            return any(i in self.sketch.lines for i in self.selected_pieces)
        if name in ("fillet", "chamfer"):
            return bool(self.corner_points())
        return False

    # --- drawing --------------------------------------------------------------------------------------------------------

    def load_drawing(self, path: Path, axes: DxfAxes) -> list[str]:
        """Replace the sketch with a DXF drawing (one Undo step). Returns the messages of the import; a problem goes to `message`.

        A turning contour reads the drawing as a part (`axes` says how it lies); other shapes are read as drawn."""
        try:
            drawing = read_dxf(path)
            if self.mode is TURNING:
                imported = contour_from_drawing(drawing, axes)
                definition = imported.definition
            else:
                imported = shape_from_drawing(drawing)
                definition = replace(imported.definition, points=imported.points)
            drawn = sketch_from_contour(build_contour("import", "import", definition))
        except (ContourError, SketchError, ValueError) as error:
            self.message = str(error)
            self._notify()
            return []
        ok = self._edit(lambda: setattr(self, "sketch", drawn))
        self.selected_points, self.selected_pieces = set(), set()
        self._notify()
        return list(imported.messages) if ok else []

    # --- trim ---------------------------------------------------------------------------------------------------------

    def trim_at(self, position: Point, tolerance: float, record: bool = True) -> bool:
        piece = self.pick_piece(position, tolerance)
        if piece is None:
            self.message = "Click on a line or an arc to trim it"
            self._notify()
            return False
        ok = self._edit(lambda: trim_piece(self.sketch, piece_id(piece), position), record)
        if ok:
            self.selected_points, self.selected_pieces = set(), set()
        self._notify()
        return ok

    # --- swiping with the trim tool -----------------------------------------------------------------------------------

    def begin_swipe(self, position: Point, tolerance: float) -> None:
        """The button went down with the Trim tool: trim what is under the mouse, then keep trimming what the mouse crosses."""
        self._swipe_before = copy.deepcopy(self.sketch)
        self._swipe_changed = False
        self._drag_mode = "swipe"
        self._swipe_used: list[Point] = []  # where the swipe has trimmed already
        self.trail = [position]
        if self.trim_at(position, tolerance, record=False):
            self._swipe_changed = True
            self._swipe_used.append(position)
        self._notify()

    def swipe_to(self, position: Point, tolerance: float) -> None:
        """The mouse moved on: every piece the step from the last place crosses is trimmed there, at once, in the order
        the step meets them. Ends of pieces do not count (a corner is not a crossing)."""
        start = self.trail[-1]
        self.trail.append(position)
        if start == position:
            return
        step = LineSegment(start, position)
        failed: set[int] = set()
        for _ in range(SWIPE_TRIM_LIMIT):
            hits = []
            for piece in self.sketch.selectable_pieces():  # the reference pieces of a corner are not trimmed
                one = piece_id(piece)
                if one in failed:
                    continue
                segment = self.sketch.segment(piece)
                for point in intersections(step, segment):
                    at_end = point.distance_to(segment.start) <= tolerance / 10 or point.distance_to(segment.end) <= tolerance / 10
                    done = any(point.distance_to(used) <= tolerance / 10 for used in self._swipe_used)
                    if not at_end and not done:
                        hits.append((start.distance_to(point), one, point))
            if not hits:
                return
            _distance, one, point = min(hits, key=lambda hit: hit[:2])
            if self._edit(lambda: trim_piece(self.sketch, one, point), record=False):
                self._swipe_changed = True
                self._swipe_used.append(point)
            else:
                failed.add(one)  # for example a circle with one crossing; the message says why

    def end_swipe(self) -> None:
        """The button came up: all the trims of the swipe are one step for Undo."""
        if self._swipe_changed and self._swipe_before is not None:
            self._push_snapshot(self._swipe_before)
            self.selected_points, self.selected_pieces = set(), set()
        self._swipe_before, self._swipe_changed, self.trail = None, False, []
