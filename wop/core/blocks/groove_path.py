"""The moves of a grooving block: where the blade goes in, how it comes out and how it leaves (requirement B3).

`GroovePath` holds what the moves have in common (the clear radius, the safe point, whether the first plunge was made) and is
asked for one plunge, one pass along the bottom and the way out at the end. The block (`grooving.py`) decides what to cut; this
class only moves, with the `Sweeper` so that the blade stops before a collision.
"""

from __future__ import annotations

from ..constants import DRILL_REAPPROACH_MM, GROOVE_AIR_SKIP_MIN_MM, PECK_RETRACT_MM
from ..geometry import Point
from ..passes import pass_levels
from ..program_model.operations import LinearMove, Rapid
from .groove_style import Plunge
from .sweep import Sweeper


class GroovePath:
    """The operations of one grooving block, made plunge by plunge.

    sign: 1 for a groove in the outer surface, -1 for one in a bore. shift: from the tip of the left side of the blade to the
    reference point of the tool. clear_x: the radius where the blade is clear of the part at the groove, whole_clear_x: clear
    of the whole part (the way along a bore). surface: where the blade starts to cut. z_front: the Z in front of the part.
    """

    def __init__(
        self, sweeper: Sweeper, first: list, *, sign: int, shift: float, surface: float, clearance: float, clear_x: float,
        whole_clear_x: float, z_front: float, safe_radius: float, safe_point: Point, start_z: float, full_retract: bool,
    ) -> None:
        self.sweeper = sweeper
        self.operations: list = first
        self.started = False  # the first plunge was made (the way to it is in the operations)
        self.last_z = start_z + shift
        self.collisions: list[Point | None] = []  # where the blade collides while cutting (None: nowhere), for the note
        self.sign = sign
        self.shift = shift
        self.surface = surface
        self.clearance = clearance
        self.clear_x = clear_x
        self.whole_clear_x = whole_clear_x
        self.z_front = z_front
        self.safe_radius = safe_radius
        self.safe_point = safe_point
        self.full_retract = full_retract  # a peck goes all the way out (else a little: chip breaking)

    def _way_to_first_plunge(self, z: float) -> list:
        """Outside a Z move at the safe radius; inside X to the clear radius at the safe Z, then straight down (when that line is
        free), otherwise along the whole bore."""
        if self.sign > 0:
            return [Rapid(Point(self.safe_radius, z))]
        if self.sweeper.line_is_free(Point(self.clear_x, self.safe_point.z), Point(self.clear_x, z)):
            return [Rapid(Point(self.clear_x, self.safe_point.z))]
        return [Rapid(Point(self.safe_radius, self.z_front)), Rapid(Point(self.whole_clear_x, self.z_front)), Rapid(Point(self.whole_clear_x, z))]

    def plunge(self, z: float, depth_x: float, plunge_feed: float, peck: float | None) -> None:
        """Plunge at tip position z down to depth_x, always all the way: the checks report a collision."""
        sweeper, sign, clear_x = self.sweeper, self.sign, self.clear_x
        z += self.shift  # from here on z is the position of the reference point
        start = Point(clear_x, z)
        contact = sweeper.air_line(start, Point(depth_x, z))  # where an earlier cut ends: nothing to feed through
        gap = sign * (clear_x - contact.x) - self.clearance
        air_x = clear_x - sign * gap if gap >= GROOVE_AIR_SKIP_MIN_MM else None
        feed_from = start if air_x is None else Point(air_x, z)
        levels = pass_levels(self.surface if air_x is None else air_x, depth_x, peck) if peck is not None else []
        levels = levels or [depth_x]
        reached, collision = sweeper.follow_line(feed_from, Point(levels[0], z))  # as asked: always to the depth
        self.collisions.append(collision)
        moves: list = [] if self.started else self._way_to_first_plunge(z)
        moves.append(Rapid(start))
        if air_x is not None:
            moves.append(Rapid(feed_from))
        for index, level in enumerate(levels):
            target, collision = sweeper.follow_line(Point(reached[-1].x, z), Point(level, z))
            self.collisions.append(collision)
            end_x = target[-1].x if target else reached[-1].x
            moves.append(LinearMove(Point(end_x, z), plunge_feed))
            if index < len(levels) - 1:
                if self.full_retract:  # all the way out, then in to just above the last depth
                    moves += [Rapid(start), Rapid(Point(end_x + sign * DRILL_REAPPROACH_MM, z))]
                else:  # chip breaking: out a little and back
                    moves += [Rapid(Point(end_x + sign * PECK_RETRACT_MM, z)), Rapid(Point(end_x, z))]
            reached = [Point(end_x, z)]
        moves.append(Rapid(start))
        self.operations.extend(moves)
        self.started = True
        self.last_z = z

    def pass_along(self, step: Plunge, finish_feed: float) -> None:
        """After the plunge of `step`: the pass along the bottom to `step.sweep_to`, in place of the retract of the plunge."""
        shift = self.shift
        along, collision = self.sweeper.follow_line(Point(step.radius, step.z + shift), Point(step.radius, step.sweep_to + shift))
        self.collisions.append(collision)
        if len(along) > 1:
            # the allowance on the other wall is still there, so the way across is above the surface
            self.operations.pop()
            self.operations.append(LinearMove(Point(step.radius, along[-1].z), finish_feed))
            self.operations.append(Rapid(Point(self.clear_x, along[-1].z)))
            self.last_z = along[-1].z

    def leave(self) -> None:
        """One rapid to the safe point when that line is free, otherwise out to the safe radius or along the whole bore first."""
        if not self.started:
            return
        here = Point(self.clear_x, self.last_z)
        if self.sweeper.line_is_free(here, self.safe_point):
            self.operations.append(Rapid(self.safe_point))
        elif self.sign > 0:
            self.operations += [Rapid(Point(self.safe_radius, self.last_z)), Rapid(self.safe_point)]
        else:
            up = Point(self.clear_x, self.z_front)
            if self.sweeper.line_is_free(here, up) and self.sweeper.line_is_free(up, self.safe_point):
                self.operations += [Rapid(up), Rapid(self.safe_point)]
            else:  # out along the whole bore
                self.operations += [Rapid(Point(self.whole_clear_x, self.last_z)), Rapid(Point(self.whole_clear_x, self.z_front)), Rapid(self.safe_point)]
