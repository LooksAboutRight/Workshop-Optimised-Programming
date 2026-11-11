"""Relations and changes as a tool of the sketch editor: press the button first, then click what it acts on.

The button stays on after the work is done, so the next clicks do the same again. A click that does not fit is ignored
(the tool stays on). Things that need several picks (two lines for Parallel) show what is picked as a selection until the
last one is clicked; a second click on a picked thing takes it back. Esc or the button itself turns the tool off; a right
click first forgets the picks, then turns it off. Selecting first and then pressing the button works as before: it acts on
the selection at once.

A part of `SketchSession` (a mixin: it uses the attributes and the relation and change functions of the session).
"""

from __future__ import annotations

from ..core.geometry import Point
from ..core.sketch.constants import ORIGIN
from ..core.sketch.model import SketchArc, SketchError
from ..core.sketch.pick import piece_id, piece_points
from .sketch_constants import ACTION_PROMPTS, CORNER_ACTIONS, NAME_PREFIX, SINGLE_CLICK_ACTIONS, STOP_HINT, TOOL_ACTION, TOOL_SELECT

LEVEL_ACTIONS = ("horizontal", "vertical")  # the only ones where the origin can be picked


class SketchActionToolMixin:
    @property
    def armed(self) -> str:
        """The relation or change that is on as a tool ("" when none is)."""
        return self.action if self.tool == TOOL_ACTION else ""

    @property
    def action_prompt(self) -> str:
        if self.action.startswith(NAME_PREFIX):
            kind = next(k for k in self.target.point_kinds if k.name == self.action[len(NAME_PREFIX):])
            return f"Click a point to make it: {kind.label}. Click it again to take the name away." + STOP_HINT
        return dict(ACTION_PROMPTS)[self.action]

    def use_relation(self, name: str) -> None:
        """A relation button was pressed: turn its tool off if it is on, else act on the selection if that fits, else turn it on."""
        if self.armed or not self.available_relation(name):
            keep = name in LEVEL_ACTIONS and len(self.selected_points) == 1 and not self.selected_pieces and not self.armed
            self._toggle_action(name, keep_picks=keep)  # one point selected: it is the first pick, the second click completes
        else:
            self.apply_relation(name)

    def use_modify(self, name: str, value: float = 0.0) -> None:
        """A change button was pressed (`value`: the radius or distance of a fillet or chamfer, asked for by the window)."""
        if self.armed or not self.available_modify(name):
            self._toggle_action(name, value)
        elif name in CORNER_ACTIONS:
            self.apply_corner(name, value)
        else:
            getattr(self, {"construction": "toggle_construction", "centre": "toggle_centre", "cutting": "toggle_cutting", "rapid": "toggle_rapid"}[name])()

    def use_name(self, kind_name: str) -> None:
        """A named-point button was pressed: name the selected point (the same name again takes it away), else turn the tool on."""
        if self.armed or len(self.selected_points) != 1 or self.selected_pieces:
            self._toggle_action(NAME_PREFIX + kind_name)
        else:
            self.toggle_point_name(kind_name)

    def _toggle_action(self, name: str, value: float = 0.0, keep_picks: bool = False) -> None:
        if self.armed == name:
            self.set_tool(TOOL_SELECT)
            return
        kept = (self.selected_points, self.selected_pieces) if keep_picks else (set(), set())  # a selection that does not fit would never be completed
        self.action, self.action_value = name, value
        self.set_tool(TOOL_ACTION)
        self.selected_points, self.selected_pieces = kept
        if keep_picks:
            self.message = "Now click a second point, or the origin (Esc stops)"
            self._notify()

    def clear_action_picks(self) -> bool:
        """Forget what has been picked; False when nothing was."""
        had = bool(self.selected_points or self.selected_pieces)
        self.selected_points, self.selected_pieces = set(), set()
        return had

    # --- the clicks ---------------------------------------------------------------------------------------------------

    def _action_hit(self, position: Point, tolerance: float) -> tuple[bool, int] | None:
        """(is a point, id) of what is under the mouse: a point of the sketch, the origin (for level and plumb), a line or an arc."""
        point = self.pickable_point(position, tolerance)
        if point is not None:
            return True, point
        if self.action in LEVEL_ACTIONS and position.distance_to(Point(0, 0)) <= tolerance:
            return True, ORIGIN
        piece = self.pick_piece(position, tolerance)
        return None if piece is None else (False, piece_id(piece))

    def action_click(self, position: Point, tolerance: float) -> None:
        self.message = ""
        hit = self._action_hit(position, tolerance)
        if hit is not None:
            if self.action in SINGLE_CLICK_ACTIONS or self.action.startswith(NAME_PREFIX):
                self._single_click(*hit)
            else:
                self._pick(*hit)
        self._notify()

    def _counts(self) -> tuple[int, int, int]:
        lines = sum(1 for i in self.selected_pieces if i in self.sketch.lines)
        return len(self.selected_points), lines, len(self.selected_pieces) - lines

    def _pick(self, is_point: bool, ident: int) -> None:
        chosen = self.selected_points if is_point else self.selected_pieces
        if ident in chosen:
            chosen.discard(ident)
            return
        chosen.add(ident)
        if not self._fits(*self._counts()):
            chosen.discard(ident)  # does not fit this relation: ignored
            return
        if self._complete(*self._counts()):
            self._finish_pick()

    def _fits(self, points: int, lines: int, arcs: int) -> bool:
        """Could the picks still grow into what the relation needs?"""
        return {
            "horizontal": (points <= 2 and not lines and not arcs) or (lines <= 1 and not points and not arcs),
            "parallel": not points and not arcs and lines <= 2,
            "equal": not points and ((not arcs and lines <= 2) or (not lines and arcs <= 2)),
            "tangent": not points and lines <= 1 and arcs <= 2 and lines + arcs <= 2,
            "point_on": points <= 1 and lines + arcs <= 1,
            "midpoint": points <= 1 and lines <= 1 and not arcs,
            "join": points <= 2 and not lines and not arcs,
        }[self._shape()]

    def _complete(self, points: int, lines: int, arcs: int) -> bool:
        return {
            "horizontal": (points == 2 and not lines and not arcs) or (lines == 1 and not points and not arcs),
            "parallel": lines == 2,
            "equal": lines == 2 or arcs == 2,
            "tangent": (lines == 1 and arcs == 1) or arcs == 2,
            "point_on": points == 1 and lines + arcs == 1,
            "midpoint": points == 1 and lines == 1,
            "join": points == 2,
        }[self._shape()]

    def _shape(self) -> str:
        """The relations that are picked the same way share a shape."""
        return {"vertical": "horizontal", "perpendicular": "parallel"}.get(self.action, self.action)

    def _finish_pick(self) -> None:
        """All picks are there: make the relation and start again. A relation that cannot be made says why."""
        problem = self._own_point_problem()
        if problem:
            self.message = problem
        else:
            self.apply_relation(self.action)
        message = self.message
        self.clear_action_picks()
        self.message = message

    def _own_point_problem(self) -> str:
        """A point picked together with a piece that it belongs to already."""
        if self.action not in ("point_on", "midpoint") or len(self.selected_pieces) != 1 or len(self.selected_points) != 1:
            return ""
        (piece_number,) = self.selected_pieces
        (point,) = self.selected_points
        piece = self.sketch.lines.get(piece_number) or self.sketch.arcs[piece_number]
        if point in piece_points(piece):
            return "The point belongs to that " + ("arc" if isinstance(piece, SketchArc) else "line") + " already"
        return ""

    def _single_click(self, is_point: bool, ident: int) -> None:
        """Relations and changes that need one click: act on what was clicked and forget it."""
        if ident == ORIGIN:
            return
        if self.action.startswith(NAME_PREFIX):
            if is_point:
                self.selected_points, self.selected_pieces = {ident}, set()
                self.toggle_point_name(self.action[len(NAME_PREFIX):])
            message = self.message
            self.clear_action_picks()
            self.message = message
            return
        corner = self.action in CORNER_ACTIONS
        if corner != is_point and (corner or self.action != "fixed"):
            return  # a corner is a point; the marks are for pieces; "fixed" takes both
        self.selected_points, self.selected_pieces = ({ident}, set()) if is_point else (set(), {ident})
        try:
            if self.action == "fixed":
                self.apply_relation("fixed")
            elif corner:
                self.apply_corner(self.action, self.action_value)
            elif self.available_modify(self.action):
                getattr(self, "toggle_" + self.action)()
        except SketchError as error:
            self.message = str(error)
        message = self.message
        self.clear_action_picks()
        self.message = message
