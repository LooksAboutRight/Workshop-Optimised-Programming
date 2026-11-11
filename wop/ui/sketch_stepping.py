"""Stepping through a path in the sketch editor (a part of `SketchSession`: it uses the attributes the session sets).

The pieces of a path run in the order the tool moves (`core/sketch/path_walk.py`). Stepping shows them one after the other: the pieces
after the current one are hidden, the older ones are drawn thin, the current one is the selected piece (so it is the one an edit
reaches where several pieces lie on one place), and the dimensions of older pieces are not drawn. If the chain is broken, stepping
stops there and says why.
"""

from __future__ import annotations

from ..core.sketch.model import SketchArc
from ..core.sketch.path_walk import walk_path
from ..core.sketch.pick import nearest_piece, piece_id, piece_points

HIDDEN, OLD, CURRENT, NORMAL = "hidden", "old", "current", "normal"


class SketchSteppingMixin:
    @property
    def can_step(self) -> bool:
        return self.mode.walk is not None

    def _walked(self) -> tuple[list[int], str]:
        """The ids of the pieces of the path in travel order, and what is wrong with the chain (text, empty: nothing)."""
        key = self.sketch.signature()
        if self._walk_cache is None or self._walk_cache[0] != key:
            walked, problems = walk_path(self.sketch)
            self._walk_cache = (key, [piece_id(piece) for piece, _forward in walked], "; ".join(problems), {piece_id(piece): forward for piece, forward in walked})
        return self._walk_cache[1], self._walk_cache[2]

    def walked_forward(self, one: int) -> bool:
        """Is the piece walked from its start to its end (it was drawn the way the tool moves)?"""
        self._walked()
        return self._walk_cache[3].get(one, True)

    @property
    def step_ids(self) -> list[int]:
        """The pieces of the path in travel order; the step is kept inside them (an edit may have made the path shorter)."""
        ids, _problem = self._walked()
        if self.step is not None and self.step >= len(ids):
            self.step = len(ids) - 1 if ids else None
        return ids

    def step_forward(self) -> None:
        """Show one more piece of the path (the first one if stepping was off). At the end of a broken chain it says why it stops."""
        ids = self.step_ids
        if not ids:
            self.message = self._walked()[1] or "There is no path to step through"
        elif self.step is None:
            self._go_to(0)
        elif self.step + 1 < len(ids):
            self._go_to(self.step + 1)
        else:
            self.message = self._walked()[1] or "That is the last piece of the path"
        self._notify()

    def step_back(self) -> None:
        """Show one piece less; before the first one stepping is off and everything is shown."""
        self.step_ids
        if self.step is None:
            return
        if self.step == 0:
            self.stop_stepping()
            return
        self._go_to(self.step - 1)
        self._notify()

    def stop_stepping(self) -> None:
        if self.step is not None:
            self.step = None
            self.selected_pieces = set()
            self.message = ""
            self._notify()

    def _go_to(self, index: int) -> None:
        self.step = index
        self.selected_points, self.selected_pieces = set(), {self.step_ids[index]}
        self.selected_constraint = None
        self.message = ""

    def piece_state(self, one: int) -> str:
        """How the picture shows a piece while stepping: hidden (after the current one), old, current, or normal (not part of the walk)."""
        ids = self.step_ids
        if self.step is None or one not in ids:
            return NORMAL
        index = ids.index(one)
        return HIDDEN if index > self.step else (CURRENT if index == self.step else OLD)

    def stepped_hidden_points(self) -> set[int]:
        """Points that only hidden pieces use."""
        if self.step is None:
            return set()
        hidden: set[int] = set()
        shown: set[int] = set()
        for piece in self.sketch.pieces():
            (hidden if self.piece_state(piece_id(piece)) == HIDDEN else shown).update(piece_points(piece))
        return hidden - shown - set(self.sketch.labels.values()) - set(self.sketch.locked_points.values())

    def constraint_visible(self, constraint) -> bool:
        """While stepping a dimension or relation is drawn at the piece it belongs to: the piece that has all its points, else the
        piece that has the points that are not locked. One that belongs to no piece of the path is always drawn."""
        if self.step is None:
            return True
        ids = self.step_ids
        points = set(self.sketch.constraint_points(constraint))
        by_id = {piece_id(p): piece_points(p) for p in self.sketch.pieces() if piece_id(p) in ids}
        for wanted in (points, points - set(self.sketch.locked_points.values())):
            owners = [i for i, own in by_id.items() if wanted and wanted <= own]
            if owners:
                return ids[self.step] in owners
        return True

    def pick_piece(self, position, tolerance):
        """The piece near the position, not counting hidden ones; where pieces lie on one place the current one wins."""
        skip = {i for i in self.step_ids if self.piece_state(i) == HIDDEN} if self.step is not None else set()
        current = self.step_ids[self.step] if self.step is not None and self.step_ids else None
        return nearest_piece(self.sketch, position, tolerance, skip=skip, prefer=current)

    @property
    def step_text(self) -> str:
        """Where stepping is ('' when it is off), for the label next to the buttons."""
        ids = self.step_ids
        if self.step is None or not ids:
            return ""
        piece = next(p for p in self.sketch.pieces() if piece_id(p) == ids[self.step])
        kind = "arc" if isinstance(piece, SketchArc) else ("rapid line" if piece.line_id in self.sketch.rapid_pieces else "feed line")
        return f"Step {self.step + 1} of {len(ids)}: {kind}" + ("" if self.step + 1 < len(ids) or not self._walked()[1] else "; the path stops here: " + self._walked()[1])
