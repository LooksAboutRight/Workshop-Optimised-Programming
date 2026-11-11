"""The sketch solver: moves the points until every relation holds, and says how much is still free.

Every relation (and, for an arc, "the end is as far from the centre as the start") is a few residuals that are zero
when it holds. The solver minimises them with damped Newton steps (Levenberg-Marquardt), so the points move as little as
possible from where they are: a half-dimensioned sketch changes only what the new relation needs. The Jacobian is
worked out by central differences, block by block, because a relation touches only a few points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from ..geometry import Point
from .constants import (
    DAMPING_MAX,
    DAMPING_MIN,
    DAMPING_START,
    DAMPING_STEP,
    DIFFERENCE_STEP,
    DRAG_STAY_WEIGHT,
    DRAG_WEIGHT,
    FIXED_TOLERANCE,
    MAX_ITERATIONS,
    ORIGIN,
    RANK_TOLERANCE,
    SOLVE_TOLERANCE,
    STEP_STOP,
)
from .model import Sketch
from .relations import relation_for

Coords = dict[int, tuple[float, float]]


@dataclass(frozen=True)
class SolveResult:
    converged: bool
    error: float  # largest residual of the relations (not of a drag target)
    iterations: int


@dataclass(frozen=True)
class Analysis:
    """`free_directions` is the number of ways the sketch can still move (0 = fully defined).

    `fixed_points` are the points that cannot move at all. `dependent` is true when some relations repeat each other.
    """

    free_directions: int
    fixed_points: frozenset[int]
    dependent: bool

    @property
    def fully_defined(self) -> bool:
        return self.free_directions == 0


@dataclass
class _Block:
    point_ids: list[int]
    residuals: Callable[[Coords], list[float]]
    hard: bool = True


def _blocks(sketch: Sketch, targets: dict[int, Point] | None) -> list[_Block]:
    blocks: list[_Block] = []
    for constraint in sketch.constraints.values():
        relation = relation_for(constraint.kind)

        def residuals(coords, constraint=constraint, relation=relation):
            return relation.equations(sketch.constraint_args(constraint, coords), constraint.values)

        blocks.append(_Block(sketch.constraint_points(constraint), residuals))
    for arc in sketch.arcs.values():
        if arc.start != arc.end:
            def residuals(coords, arc=arc):
                centre = coords[arc.centre]
                return [_distance(centre, coords[arc.end]) - _distance(centre, coords[arc.start])]

            blocks.append(_Block([arc.centre, arc.start, arc.end], residuals))
    for point_id in sketch.locked_points.values():  # a locked point stays where the program put it
        def pinned(coords, point_id=point_id, here=sketch.points[point_id]):
            return [coords[point_id][0] - here.x, coords[point_id][1] - here.z]

        blocks.append(_Block([point_id], pinned))
    for point_id, target in (targets or {}).items():
        def residuals(coords, point_id=point_id, target=target):
            return [DRAG_WEIGHT * (coords[point_id][0] - target.x), DRAG_WEIGHT * (coords[point_id][1] - target.z)]

        blocks.append(_Block([point_id], residuals, hard=False))
    if targets:  # a drag: the points that are not pulled stay where they are, softly (see DRAG_STAY_WEIGHT)
        for point_id, point in sketch.points.items():
            if point_id not in targets:
                def stay(coords, point_id=point_id, here=point):
                    return [DRAG_STAY_WEIGHT * (coords[point_id][0] - here.x), DRAG_STAY_WEIGHT * (coords[point_id][1] - here.z)]

                blocks.append(_Block([point_id], stay, hard=False))
    return blocks


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


class _System:
    def __init__(self, sketch: Sketch, targets: dict[int, Point] | None = None) -> None:
        self.sketch = sketch
        self.ids = list(sketch.points)
        self.column = {point_id: 2 * index for index, point_id in enumerate(self.ids)}
        self.blocks = _blocks(sketch, targets)

    def start_vector(self) -> np.ndarray:
        return np.array([value for i in self.ids for value in (self.sketch.points[i].x, self.sketch.points[i].z)])

    def coords(self, vector: np.ndarray) -> Coords:
        found: Coords = {i: (float(vector[self.column[i]]), float(vector[self.column[i] + 1])) for i in self.ids}
        found[ORIGIN] = (0.0, 0.0)
        return found

    def residuals(self, vector: np.ndarray) -> tuple[np.ndarray, float]:
        """All residuals, and the largest one of the hard blocks."""
        coords = self.coords(vector)
        values: list[float] = []
        worst = 0.0
        for block in self.blocks:
            part = block.residuals(coords)
            values += part
            if block.hard and part:
                worst = max(worst, max(abs(v) for v in part))
        return np.array(values), worst

    def jacobian(self, vector: np.ndarray, hard_only: bool = False) -> np.ndarray:
        coords = self.coords(vector)
        blocks = [b for b in self.blocks if b.hard or not hard_only]
        sizes = [len(b.residuals(coords)) for b in blocks]
        jacobian = np.zeros((sum(sizes), len(vector)))
        row = 0
        for block, size in zip(blocks, sizes):
            for point_id in block.point_ids:
                for axis in (0, 1):
                    plus, minus = dict(coords), dict(coords)
                    x, z = coords[point_id]
                    plus[point_id] = (x + DIFFERENCE_STEP, z) if axis == 0 else (x, z + DIFFERENCE_STEP)
                    minus[point_id] = (x - DIFFERENCE_STEP, z) if axis == 0 else (x, z - DIFFERENCE_STEP)
                    delta = (np.array(block.residuals(plus)) - np.array(block.residuals(minus))) / (2 * DIFFERENCE_STEP)
                    jacobian[row:row + size, self.column[point_id] + axis] = delta
            row += size
        return jacobian


def solve(sketch: Sketch, targets: dict[int, Point] | None = None) -> SolveResult:
    """Move the points of `sketch` so that its relations hold; `targets` pull points softly (used while dragging).

    The sketch is changed only when the result is good (hard residuals below the tolerance); otherwise it stays as it was.
    """
    system = _System(sketch, targets)
    vector = system.start_vector()
    if not system.blocks or not len(vector):
        return SolveResult(True, 0.0, 0)
    values, worst = system.residuals(vector)
    damping = DAMPING_START
    iterations = 0
    while iterations < MAX_ITERATIONS and (worst > SOLVE_TOLERANCE or targets):
        iterations += 1
        jacobian = system.jacobian(vector)
        normal = jacobian.T @ jacobian
        gradient = jacobian.T @ values
        moved = False
        while damping <= DAMPING_MAX:
            try:
                step = np.linalg.solve(normal + damping * np.eye(len(vector)), -gradient)
            except np.linalg.LinAlgError:
                damping *= DAMPING_STEP
                continue
            trial_values, trial_worst = system.residuals(vector + step)
            if float(trial_values @ trial_values) < float(values @ values):
                vector, values, worst = vector + step, trial_values, trial_worst
                damping = max(damping / DAMPING_STEP, DAMPING_MIN)
                moved = float(np.max(np.abs(step))) > STEP_STOP
                break
            damping *= DAMPING_STEP
        if not moved:
            break
    converged = worst <= SOLVE_TOLERANCE
    if converged or targets:  # a pull that the relations hold back is still a result
        for point_id in system.ids:
            if sketch.is_locked_point(point_id):  # exactly where the program put it, not within the tolerance
                continue
            sketch.move_point(point_id, float(vector[system.column[point_id]]), float(vector[system.column[point_id] + 1]))
    return SolveResult(converged, worst, iterations)


def _circle_edge_rows(system: _System, vector: np.ndarray) -> list[np.ndarray]:
    """One row per circle: the turning of its edge point round its centre. Where on the circle that point sits does not
    matter, so the analysis takes that freedom away instead of asking the user to dimension the point."""
    rows = []
    for arc in system.sketch.arcs.values():
        if arc.start != arc.end:
            continue
        centre, edge = system.column[arc.centre], system.column[arc.start]
        radial = vector[edge:edge + 2] - vector[centre:centre + 2]
        row = np.zeros(len(vector))
        row[edge], row[edge + 1] = -radial[1], radial[0]
        row[centre], row[centre + 1] = radial[1], -radial[0]
        rows.append(row)
    return rows


def analyse(sketch: Sketch) -> Analysis:
    """How many ways the solved sketch can still move, which points are pinned down, whether relations repeat."""
    system = _System(sketch)
    vector = system.start_vector()
    count = len(vector)
    jacobian = system.jacobian(vector, hard_only=True) if system.blocks else np.zeros((0, count))
    if not count:
        return Analysis(0, frozenset(), False)
    relations_repeat = bool(jacobian.shape[0]) and jacobian.shape[0] > int(np.linalg.matrix_rank(jacobian, tol=RANK_TOLERANCE))
    pins = _circle_edge_rows(system, vector)
    if not jacobian.shape[0] and not pins:
        return Analysis(count, frozenset(), False)
    jacobian = np.vstack([jacobian, *pins])
    _u, singular, vt = np.linalg.svd(jacobian, full_matrices=True)
    rank = int(np.sum(singular > RANK_TOLERANCE * max(1.0, float(singular.max()))))
    null_space = vt[rank:].T  # columns: the directions in which the points can still move
    fixed = frozenset(
        point_id
        for point_id in system.ids
        if not null_space.size or float(np.linalg.norm(null_space[system.column[point_id]:system.column[point_id] + 2])) < FIXED_TOLERANCE
    )
    return Analysis(count - rank, fixed, relations_repeat)
