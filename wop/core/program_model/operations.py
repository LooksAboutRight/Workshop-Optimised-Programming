"""Neutral operations: what the machine is told to do, without any dialect.

Blocks produce these; postprocessors (stage S5c) turn them into the G-code of
one controller. Coordinates are x = radius and z = axial position in mm; feeds
are millimetres per revolution. Nothing in this module knows about G-code.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from ..constants import DRILL_REAPPROACH_MM, GEOMETRY_TOLERANCE_MM, MAX_THREAD_PASSES
from ..geometry import ArcDirection, Point


class SpindleMode(Enum):
    CONSTANT_SURFACE_SPEED = "css"  # value in m/min
    CONSTANT_RPM = "rpm"  # value in revolutions per minute


class SpindleDirection(Enum):
    """Which way the spindle turns. The blocks do not say M3 or M4: the postprocessor writes the code of its controller."""

    CLOCKWISE = "clockwise"
    COUNTER_CLOCKWISE = "counter-clockwise"


class CoolantMode(Enum):
    NONE = "none"
    FLOOD = "flood"
    MIST = "mist"


@dataclass(frozen=True)
class SpindleSetting:
    # first in the form (the user sees the direction above the mode), last in the call: a keyword only
    direction: SpindleDirection = field(default=SpindleDirection.CLOCKWISE, kw_only=True)
    mode: SpindleMode
    value: float  # m/min for CSS, RPM for constant RPM
    rpm_limit: float | None = None  # upper RPM limit, used with CSS

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError("spindle speed must be greater than zero")
        if self.rpm_limit is not None and self.rpm_limit <= 0:
            raise ValueError("RPM limit must be greater than zero")


def finishing_spindle(spindle: SpindleSetting, value: float | None) -> SpindleSetting | None:
    """The spindle for a finishing pass: the same mode and limit with another speed; None when it is the same as before."""
    if value is None or value == spindle.value:
        return None
    return replace(spindle, value=value)


@dataclass(frozen=True)
class Rapid:
    end: Point
    at_change: bool = field(default=False, compare=False)  # the move to the tool change position (a post may write it in machine coordinates)


@dataclass(frozen=True)
class RapidAxes:
    """Rapid move of one axis only (None = that axis stays). Used when a position is unknown."""

    x: float | None = None
    z: float | None = None


class MoveRole(Enum):
    """What a finishing move does for a controller with cutter compensation (G41 / G42). A normal move has no role."""

    NORMAL = "normal"
    LEAD_IN = "lead in"  # the move on which the compensation starts; it ends at the first point of the contour
    LEAD_OUT = "lead out"  # the move on which the compensation ends; it starts at the last point of the contour
    JOIN = "join"  # an arc WOP adds at an outer corner of the tool path; a controller with compensation makes it itself


class CompensationSide(Enum):
    """On which side of the contour the tool is, looking in the direction of travel with X up and Z to the right in the
    picture. Outside turning towards the chuck: RIGHT. A post maps it to G41 (left) or G42 (right) in its code table."""

    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True)
class LinearMove:
    """A straight feed move. `end` is where the tool reference point goes. A move of a compensated finishing pass also
    knows the point of the nominal contour it follows (`contour_end`), which a post with cutter compensation writes
    instead; the lead-in has the first contour point and the side of the tool, the lead-out writes its `end`."""

    end: Point
    feed_mm_per_rev: float
    contour_end: Point | None = None
    role: MoveRole = MoveRole.NORMAL
    side: CompensationSide | None = None  # the lead-in: the side of the tool


@dataclass(frozen=True)
class ArcMove:
    """An arc feed move; the contour fields are as in `LinearMove` (the contour arc has its own centre)."""

    end: Point
    center: Point
    direction: ArcDirection
    feed_mm_per_rev: float
    contour_end: Point | None = None
    contour_center: Point | None = None
    role: MoveRole = MoveRole.NORMAL


class DrillMode(Enum):
    """How a hole is drilled. Value: the name shown to the user."""

    DRILL = "drilling"  # one stroke to the depth
    PECK = "peck drilling"  # pecks; after each one the drill goes back only to where that peck began
    PECK_FULL_RETRACT = "peck drilling, full retract"  # pecks; after each one the drill goes back to the start


@dataclass(frozen=True)
class DrillOperation:
    """Drill on the spindle axis (requirement X4). The tool stands on the axis at retract_z.

    It feeds from retract_z (the clearance in front of the material) down to end_z, stays there for
    dwell_s and rapids out to exit_z (the safe Z; None: back to retract_z). Pecks are measured from
    entry_z, the surface of the material (None: from retract_z), and are at most peck_depth_mm. After a
    peck the drill rapids out, to where the peck began (PECK; the first one to retract_z) or to retract_z
    (PECK_FULL_RETRACT), then in to DRILL_REAPPROACH_MM above the last depth and feeds on. With air_z (a hole
    from an earlier drill) the tool rapids in to there first and the pecks are measured from it. Without a mode,
    a peck depth means PECK_FULL_RETRACT. A postprocessor may map it to a canned cycle; `explicit_moves` is
    the plain version for controllers without one.
    """

    retract_z: float
    end_z: float
    feed_mm_per_rev: float
    peck_depth_mm: float | None = None
    mode: DrillMode | None = None
    dwell_s: float = 0
    exit_z: float | None = None
    entry_z: float | None = None
    air_z: float | None = None  # a hole is there already: rapid in to here first, the first peck is measured from here

    @property
    def end(self) -> Point:
        return Point(0, self.retract_z if self.exit_z is None else self.exit_z)

    @property
    def skips_air(self) -> bool:
        return self.air_z is not None and self.air_z < self.retract_z - GEOMETRY_TOLERANCE_MM

    @property
    def effective_mode(self) -> DrillMode:
        if self.mode is not None:
            return self.mode
        return DrillMode.DRILL if self.peck_depth_mm is None else DrillMode.PECK_FULL_RETRACT

    def stops(self) -> list[float]:
        """The depth reached by every stroke; the last one is end_z."""
        if self.effective_mode is DrillMode.DRILL or self.peck_depth_mm is None:
            return [self.end_z]
        origin = self.air_z if self.skips_air else self.retract_z if self.entry_z is None else self.entry_z
        levels = []
        level = origin - self.peck_depth_mm
        while level > self.end_z + GEOMETRY_TOLERANCE_MM:
            levels.append(level)
            level -= self.peck_depth_mm
        return [*levels, self.end_z]

    def explicit_moves(self) -> tuple["Rapid | LinearMove | MachineFunction", ...]:
        if self.retract_z - self.end_z <= GEOMETRY_TOLERANCE_MM:
            return ()
        full = self.effective_mode is DrillMode.PECK_FULL_RETRACT
        moves: list[Rapid | LinearMove | MachineFunction] = []
        began = self.retract_z  # where the stroke that is running began
        if self.skips_air:
            began = self.air_z
            moves.append(Rapid(Point(0, began)))
        stops = self.stops()
        for index, level in enumerate(stops):
            moves.append(LinearMove(Point(0, level), self.feed_mm_per_rev))
            if index == len(stops) - 1:
                break
            moves.append(Rapid(Point(0, self.retract_z if full else began)))
            began = level + DRILL_REAPPROACH_MM
            moves.append(Rapid(Point(0, began)))
        if self.dwell_s > 0:
            moves.append(MachineFunction(MachineFunctionKind.DWELL, self.dwell_s))
        moves.append(Rapid(self.end))
        return tuple(moves)


class ThreadTaper(Enum):
    """Which ends of a thread run out tapered (G76 L); the taper length is `ThreadOperation.taper_distance_mm`."""

    NONE = "none"
    ENTRY = "entry"
    EXIT = "exit"
    BOTH = "entry and exit"


@dataclass(frozen=True)
class ThreadOperation:
    """Thread cutting along Z (requirement X4). The tool stands at start_x, start_z.

    Every pass is synchronised with the spindle (feed = pitch per revolution). Radii:
    `start_x` is where the cycle starts, `peak_offset_mm` the signed distance from there to
    the thread crest (negative: crest is nearer the axis, an outside thread), `first_cut_mm`
    the depth of the first pass below the crest and `depth_mm` the full thread depth.
    The tool returns to the start point. `explicit_moves` is an approximation of the passes
    (straight in-feed) for the collision check and the picture only.
    """

    start_x: float
    start_z: float
    end_z: float
    pitch_mm: float
    peak_offset_mm: float
    first_cut_mm: float
    depth_mm: float
    degression: float
    compound_angle_deg: float
    spring_passes: int
    taper_distance_mm: float = 0  # length of the tapered entry or exit along the thread (G76 E)
    taper: ThreadTaper = ThreadTaper.NONE  # which ends are tapered (G76 L)

    @property
    def end(self) -> Point:
        return Point(self.start_x, self.start_z)

    @property
    def outside(self) -> bool:
        return self.peak_offset_mm < 0

    def pass_depths(self) -> list[float]:
        """Depth below the crest of each pass (constant area when degression is 2)."""
        depths: list[float] = []
        count = 1
        while True:
            depth = self.first_cut_mm * count ** (1 / self.degression)
            if depth >= self.depth_mm - GEOMETRY_TOLERANCE_MM:
                break
            depths.append(depth)
            count += 1
            if count > MAX_THREAD_PASSES:
                raise ValueError(
                    f"the thread would need more than {MAX_THREAD_PASSES} passes (first cut {self.first_cut_mm:g} mm, "
                    f"degression {self.degression:g}, depth {self.depth_mm:g} mm): check the first cut and the degression"
                )
        depths.append(self.depth_mm)
        if len(depths) + self.spring_passes > MAX_THREAD_PASSES:
            raise ValueError(f"the thread would need more than {MAX_THREAD_PASSES} passes with {self.spring_passes} spring passes: check the spring passes")
        depths += [self.depth_mm] * self.spring_passes
        return depths

    def explicit_moves(self) -> tuple["Rapid | LinearMove", ...]:
        crest = self.start_x + self.peak_offset_mm
        sign = 1 if self.outside else -1
        moves: list[Rapid | LinearMove] = []
        for depth in self.pass_depths():
            x = crest - sign * depth
            moves += [
                Rapid(Point(x, self.start_z)),
                LinearMove(Point(x, self.end_z), self.pitch_mm),
                Rapid(Point(self.start_x, self.end_z)),
                Rapid(Point(self.start_x, self.start_z)),
            ]
        return tuple(moves)


def plain_moves(operation: "Operation") -> tuple["Operation", ...]:
    """The operation as explicit moves (a drill operation is expanded, others stay)."""
    if isinstance(operation, DrillOperation):
        return tuple(move for move in operation.explicit_moves() if isinstance(move, (Rapid, LinearMove)))  # no dwell
    if isinstance(operation, ThreadOperation):
        return operation.explicit_moves()
    return (operation,)


@dataclass(frozen=True)
class ToolChange:
    tool_number: int


@dataclass(frozen=True)
class SetSpindle:
    setting: SpindleSetting


@dataclass(frozen=True)
class StopSpindle:
    pass


def spindle_after(state: "SpindleSetting | None", operation: "Operation") -> "SpindleSetting | None":
    """The spindle (None = stopped) after an operation: only `SetSpindle` and `StopSpindle` change it (WH0)."""
    if isinstance(operation, SetSpindle):
        return operation.setting
    if isinstance(operation, StopSpindle):
        return None
    return state


def spindle_text(setting: "SpindleSetting | None") -> str:
    """Short text for the spindle state, for the stepper: "off", "1200 rpm", "CSS 180 m/min (max 3000 rpm)"."""
    if setting is None:
        return "off"
    if setting.mode is SpindleMode.CONSTANT_RPM:
        return f"{setting.value:g} rpm"
    limit = "" if setting.rpm_limit is None else f" (max {setting.rpm_limit:g} rpm)"
    return f"CSS {setting.value:g} m/min{limit}"


@dataclass(frozen=True)
class SetCoolant:
    mode: CoolantMode


class MachineFunctionKind(Enum):
    """What a machine function block does (requirement B13). Value: the name shown to the user."""

    PROGRAM_STOP = "program stop"
    OPTIONAL_STOP = "optional stop"
    DWELL = "dwell"
    SPINDLE_STOP = "spindle stop"


@dataclass(frozen=True)
class MachineFunction:
    """A function outside the motion that every post knows: a stop or a dwell."""

    kind: MachineFunctionKind
    seconds: float = 0  # for a dwell


@dataclass(frozen=True)
class FunctionCall:
    """A function of the post that WOP does not know (a custom concept of the post file): its name and the values of its variables.
    WOP assumes it changes nothing it keeps track of (position, spindle, coolant)."""

    name: str
    values: tuple[tuple[str, "float | bool | str"], ...] = ()


@dataclass(frozen=True)
class BlockBegin:
    """Marks where a block starts; postprocessors use it for comments and modal state."""

    index: int
    block_id: str
    type_name: str
    name: str


@dataclass(frozen=True)
class BlockEnd:
    block_id: str


@dataclass(frozen=True)
class Comment:
    text: str


Operation = (
    Rapid
    | RapidAxes
    | LinearMove
    | ArcMove
    | DrillOperation
    | ThreadOperation
    | ToolChange
    | SetSpindle
    | StopSpindle
    | SetCoolant
    | BlockBegin
    | BlockEnd
    | Comment
    | MachineFunction
    | FunctionCall
)

