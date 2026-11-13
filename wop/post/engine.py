"""The interpreter: one postprocessor that writes G-code from the templates of a post file.

It has the same methods as every postprocessor (`Postprocessor`), so the generator, the checks and the remedies work with it
as they are. Each method picks the concept of the operation, hands the values of the operation to the tokens and tidies the
lines. The engine keeps what "if changed" needs: the last position, the last value of a token, the last code of every modal
group, the line number, the spindle speed, the tool and the block.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ..core.constants import GEOMETRY_TOLERANCE_MM, MM_PER_INCH
from ..core.geometry import ArcDirection, Point
from ..core.program_model.operations import (
    ArcMove,
    BlockBegin,
    CompensationSide,
    CoolantMode,
    DrillMode,
    DrillOperation,
    LinearMove,
    MachineFunction,
    FunctionCall,
    MachineFunctionKind,
    MoveRole,
    Rapid,
    RapidAxes,
    SpindleMode,
    SpindleSetting,
    ThreadOperation,
)
from ..core.program_model.operations import SpindleDirection
from ..core.program_model.units import UnitSystem, XInputMode
from .base import PostError, PostInfo, Postprocessor, PostSettings
from .concepts import CONCEPTS
from .context import BlockInfo, PostContext
from .numbers import NumberFormat, format_number
from .post_constants import INCHES_PER_FOOT, M_PER_MIN_TO_MM_PER_MIN, MAX_SPINDLE_RAMP_STEPS, SEPARATOR_PLACEHOLDER
from .post_definition import BoundOptional, Line, PostDefinition, replace_pairs
from .template import Literal
from .tokens import DIMENSION_LENGTH, DIMENSION_SURFACE_SPEED, BoundToken, dimension_of
from .variables import VariableError, check_values

FUNCTION_CONCEPTS = {
    MachineFunctionKind.PROGRAM_STOP: "program_stop",
    MachineFunctionKind.OPTIONAL_STOP: "optional_stop",
    MachineFunctionKind.DWELL: "dwell",
}
ARC_CONCEPTS = {ArcDirection.CCW: "arc_ccw", ArcDirection.CW: "arc_cw"}
COORDINATE_FORMATS = ("coordinate", "feed")  # the formats that follow the zeros/point settings of the post (a speed or an angle does not)
ONE_DECIMAL = 1
CODE_TOKEN = "code"  # the token of the code table
SPACES = re.compile(r" {2,}")
UNNUMBERED_LINE_STARTS = ("(", ";", "%")  # comment lines and the % of a program start carry no line number


@dataclass
class EngineState:
    x: float | None = None  # the last position of the tool path
    z: float | None = None
    cx: float | None = None  # the last point of the contour (the same as x, z where the move had no contour point)
    cz: float | None = None
    written: dict[str, str] = field(default_factory=dict)  # the last text of every token with memory
    groups: dict[str, str] = field(default_factory=dict)  # the last code of every modal group
    line_number: int | None = None
    rpm: float | None = None  # the fixed spindle speed, None when unknown (off, or constant surface speed)
    css: tuple[float, float | None] | None = None  # constant surface speed running: (m/min, rpm limit); None otherwise
    direction: SpindleDirection = SpindleDirection.CLOCKWISE  # the direction of the last start
    cut_x: float | None = None  # the radius of the last feed move (the speed of a constant surface speed follows it)
    tool_cursor: int = 0  # tool changes done
    tool_index: int | None = None  # place of the current tool in the tool sequence of the program
    tool_number: int | None = None
    block: BlockInfo | None = None


@dataclass
class Render:
    """What a token may look at while a line is written."""

    engine: "TemplatePost"
    concept: str
    scope: dict

    @property
    def state(self) -> EngineState:
        return self.engine.state

    @property
    def context(self) -> PostContext:
        return self.engine.context


@dataclass
class Piece:
    text: str = ""
    filled: bool = False  # a token other than a code gave a value
    code_filled: bool = False  # a `<code ...>` gave a value
    has_token: bool = False
    has_value_token: bool = False  # there is a token that is not a code
    literal: bool = False  # text of its own stands in it (an explicit blank line has one)


def cycle_concept(operation: DrillOperation) -> str | None:
    """The concept of the canned cycle that writes this hole, by what the hole needs; None for a hole inside a hole that is there (no
    cycle starts there): plain moves."""
    if operation.skips_air:
        return None
    if operation.effective_mode is DrillMode.DRILL or operation.peck_depth_mm is None:
        return "dwell_drill_cycle" if operation.dwell_s > 0 else "drill_cycle"
    if operation.dwell_s > 0:
        return "peck_dwell_drill_cycle"
    return "peck_drill_cycle" if operation.effective_mode is DrillMode.PECK_FULL_RETRACT else "chip_break_cycle"


class TemplatePost(Postprocessor):
    def __init__(self, definition: PostDefinition, context: PostContext | None = None) -> None:
        self.definition = definition
        self.context = context or PostContext()
        self.settings = PostSettings(XInputMode.RADIUS)
        self.state = EngineState()
        self.exit_written = False  # the drilling cycle just written took the drill out itself (<drill exit Z>)
        self.preview: bool | None = None  # None: normal. True / False: every `changed` counts as changed / unchanged (the sample output of the editor)

    @property
    def info(self) -> PostInfo:
        return self.definition.info

    @property
    def line_ending(self) -> str:
        return self.definition.settings.newline

    def fresh(self) -> "TemplatePost":
        return TemplatePost(self.definition, self.context)

    def start(self, context: PostContext) -> None:
        self.context = context

    # --- writing a concept ---------------------------------------------------------------

    def render_concept(self, concept: str, scope: dict | None = None) -> list[str]:
        lines = self.definition.lines_for(concept)
        if lines is None:
            known = CONCEPTS.get(concept)
            if known is None or known.needed:
                raise PostError(f"{self._where(concept)}: the post has no [{concept}] and there is no default post to take it from")
            return []
        render = Render(self, concept, scope or {})
        output: list[str] = []
        for line in lines:
            try:
                output += self._line(line, render)
            except PostError as error:
                raise PostError(f"{self._where(concept)}: {error}") from None
        return output

    def _where(self, concept: str) -> str:
        block = self.state.block
        return f"[{concept}]" if block is None else f"block {block.number} ({block.type_name}) [{concept}]"

    def _line(self, line: Line, render: Render) -> list[str]:
        significant = [n for n in line if not (isinstance(n, Literal) and not n.protected and not n.text.strip())]
        if len(significant) == 1 and isinstance(significant[0], BoundToken) and significant[0].token.kind == "lines":
            token = significant[0]
            return list(token.token.evaluate(render, token.args, token.options) or [])
        piece = self._nodes(line, render)
        text = SPACES.sub(" ", piece.text).strip(" ").replace(SEPARATOR_PLACEHOLDER, " ")
        if not text and not piece.literal:
            return []  # nothing but empty tokens: no blank line
        return [text]

    def _nodes(self, nodes, render: Render) -> Piece:
        piece = Piece()
        parts: list[str] = []
        for node in nodes:
            if isinstance(node, Literal):
                parts.append(node.text.replace(" ", SEPARATOR_PLACEHOLDER) if node.protected else node.text)
                piece.literal = piece.literal or node.protected or bool(node.text.strip())
            elif isinstance(node, BoundToken):
                text = self._token(node, render)
                piece.has_token = True
                if node.token.name == CODE_TOKEN:  # a code keeps an optional part alive only when nothing else is in it
                    piece.code_filled = piece.code_filled or bool(text)
                else:
                    piece.has_value_token = True
                    piece.filled = piece.filled or bool(text)
                parts.append(text)
            else:
                assert isinstance(node, BoundOptional)
                inner = self._nodes(node.parts, render)
                piece.has_value_token = piece.has_value_token or inner.has_value_token
                if inner.has_token and not (inner.filled or (inner.code_filled and not inner.has_value_token)):
                    continue  # every token inside is empty (a code does not count when the part has a value too): the part disappears
                piece.filled = piece.filled or inner.filled
                piece.code_filled = piece.code_filled or inner.code_filled
                parts.append(inner.text)
        piece.text = "".join(parts)
        return piece

    # --- one token -----------------------------------------------------------------------

    def _unit_factor(self, token, render: Render) -> float:
        """The factor from the millimetres of the program to the unit of the G-code (1 for millimetres)."""
        if self.settings.unit is not UnitSystem.IMPERIAL:
            return 1
        dimension = dimension_of(token)
        if dimension == DIMENSION_LENGTH:
            return 1 / MM_PER_INCH
        if dimension == DIMENSION_SURFACE_SPEED and render.concept == "spindle_css":  # m/min to feet per minute
            return M_PER_MIN_TO_MM_PER_MIN / MM_PER_INCH / INCHES_PER_FOOT
        return 1

    def _number_format(self, token) -> NumberFormat:
        settings = self.definition.settings
        imperial = self.settings.unit is UnitSystem.IMPERIAL and dimension_of(token) == DIMENSION_LENGTH
        decimals = {"coordinate": settings.decimals_inch if imperial else settings.decimals,
                    "feed": settings.feed_decimals_inch if imperial else settings.feed_decimals, "speed": settings.speed_decimals,
                    "one": ONE_DECIMAL, "count": 0}[token.number_format]
        if token.number_format in COORDINATE_FORMATS:
            return NumberFormat(decimals, settings.zeros, settings.point)
        return NumberFormat(decimals)

    def _token(self, node: BoundToken, render: Render) -> str:
        token, options = node.token, node.options
        value = token.evaluate(render, node.args, options)
        if value is None:
            return ""
        if token.kind == "number":
            text = format_number(float(value) * self._unit_factor(token, render), self._number_format(token), options)
        else:
            text = str(value)
            if options.has("safe"):
                text = self._safe(text)
            if options.has("upper"):
                text = text.upper()
        if token.memory and options.has("changed"):
            key = f"{token.name}{' per minute' if options.has('per_minute') else ''}"
            if self.preview is False or (self.preview is None and self.state.written.get(key) == text):
                return ""
            self.state.written[key] = text
        if text:
            text = options.get("prefix") + text + options.get("suffix")
        return text

    def _safe(self, text: str) -> str:
        """Only what a comment of this post may hold."""
        settings = self.definition.settings
        for old, new in replace_pairs(settings.comment_replace):
            text = text.replace(old, new)
        if settings.comment_upper:
            text = text.upper()
        if settings.comment_allowed:
            text = " ".join("".join(c if c in settings.comment_allowed else " " for c in text).split())
        return text

    # --- the operations ------------------------------------------------------------------

    def header(self, settings: PostSettings, notes: list[str]) -> list[str]:
        self.settings = settings
        return self.render_concept("header", {"notes": notes}) + self.render_concept("setup")

    def footer(self) -> list[str]:
        return self.render_concept("footer")

    def number_lines(self, lines: list[str]) -> list[str]:
        """A line number in front of every line that is not a comment (the numbers of the whole program count on)."""
        settings = self.definition.settings
        if not settings.line_numbers:
            return lines
        state, numbered = self.state, []
        for line in lines:
            if not line.strip() or line.lstrip().startswith(UNNUMBERED_LINE_STARTS):
                numbered.append(line)
                continue
            state.line_number = settings.line_number_start if state.line_number is None else state.line_number + settings.line_number_step
            numbered.append(f"{settings.line_number_prefix}{state.line_number} {line}")
        return numbered

    def comment(self, text: str) -> list[str]:
        return self.render_concept("comment", {"text": text})

    def block_begin(self, operation: BlockBegin) -> list[str]:
        number = operation.index + 1
        known = next((b for b in self.context.blocks if b.number == number), None)
        self.state.block = known or BlockInfo(number, operation.name, operation.type_name)
        return self.render_concept("block_start")

    def _moved(self, x: float | None, z: float | None, contour: Point | None = None) -> None:
        if x is not None:
            self.state.x = self.state.cx = x
        if z is not None:
            self.state.z = self.state.cz = z
        if contour is not None:
            self.state.cx, self.state.cz = contour.x, contour.z

    def _check_compensation_code(self, move: LinearMove, lines: list[str]) -> None:
        """A post that writes the contour (cutter_compensation = yes) must start and end the compensation: the contour without
        G41 / G42 would be cut with the tool tip on it, a nose radius off. A post that cannot is an error, not a silent wrong path."""
        if not self.compensating or move.role not in (MoveRole.LEAD_IN, MoveRole.LEAD_OUT):
            return
        if move.role is MoveRole.LEAD_OUT:
            name = "comp_off"
        else:
            name = "comp_left" if move.side is CompensationSide.LEFT else "comp_right"
        code = self.definition.codes.get(name)
        if code is None:
            raise PostError(
                f"{self._where('feed')}: the post has cutter_compensation = yes but its code table has no {name}; "
                f"add it (for example {name} = G4{'0' if name == 'comp_off' else ('1' if name == 'comp_left' else '2')})"
            )
        if not any(code.text in line for line in lines):
            raise PostError(
                f"{self._where('feed')}: the post has cutter_compensation = yes but its [feed] does not write the code {name}: "
                f"put <comp code> into the template"
            )

    @property
    def compensating(self) -> bool:
        """The post writes the contour and the codes of cutter compensation for the moves that have a contour point."""
        return self.definition.settings.cutter_compensation

    def _compensated(self, move) -> dict:
        """What a move adds to its scope: the contour point, whether the contour is the default, the role and the side."""
        contour = move.contour_end
        scope = {
            "cx": None if contour is None else contour.x, "cz": None if contour is None else contour.z,
            "csx": self.state.cx, "csz": self.state.cz,
            "comp": self.compensating and contour is not None,
            "compensating": self.compensating, "role": move.role, "side": getattr(move, "side", None),
        }
        centre = getattr(move, "contour_center", None)
        if centre is not None:
            scope["ccx"], scope["ccz"] = centre.x, centre.z
        return scope

    @property
    def has_change_position(self) -> bool:
        """The post has a [change_position]: it writes the move to the tool change position itself."""
        return self.definition.lines_for("change_position") is not None

    def rapid(self, move: Rapid) -> list[str]:
        if move.at_change:
            if self.has_change_position:
                return self._change_position_move(move)
            lines = self._machine_change_move()
            if lines:
                return lines
        lines = self.render_concept("rapid", {"x": move.end.x, "z": move.end.z})
        self._moved(move.end.x, move.end.z)
        return lines

    def rapid_axes(self, move: RapidAxes) -> list[str]:
        lines = self.render_concept("rapid", {"x": move.x, "z": move.z})
        self._moved(move.x, move.z)
        return lines

    def linear(self, move: LinearMove) -> list[str]:
        if self.compensating and move.role is MoveRole.JOIN:  # the controller makes the corner itself
            self.state.x, self.state.z = move.end.x, move.end.z
            return []
        scope = {"x": move.end.x, "z": move.end.z, "feed": move.feed_mm_per_rev, **self._compensated(move)}
        lines = self.render_concept("feed", scope)
        self._check_compensation_code(move, lines)
        self._moved(move.end.x, move.end.z, move.contour_end)
        self.state.cut_x = move.end.x
        return lines

    def arc(self, move: ArcMove, start_x: float, start_z: float) -> list[str]:
        if self.compensating and move.role is MoveRole.JOIN:
            self.state.x, self.state.z = move.end.x, move.end.z
            return []
        scope = {
            **self._compensated(move),
            "x": move.end.x, "z": move.end.z, "feed": move.feed_mm_per_rev, "start_x": start_x, "start_z": start_z,
            "center_x": move.center.x, "center_z": move.center.z, "start": Point(start_x, start_z), "end": move.end,
            "center": move.center, "direction": move.direction,
        }
        lines = self.render_concept(ARC_CONCEPTS[move.direction], scope)
        self._moved(move.end.x, move.end.z, move.contour_end)
        self.state.cut_x = move.end.x
        return lines

    def thread(self, operation: ThreadOperation) -> list[str]:
        scope = {"op": operation, "start_x": operation.start_x, "start_z": operation.start_z}
        style = self.definition.settings.threading_style
        if style == "cycle":
            lines = self.render_concept("thread_cycle", scope)
        elif style == "two_block":
            lines = self.render_concept("thread_two_block", scope)
        else:  # plain passes: the moves of the passes are written as ordinary moves
            lines = self.render_concept("thread_passes", scope)
            for move in operation.explicit_moves():
                lines += self.rapid(move) if isinstance(move, Rapid) else self.linear(move)
        self._moved(operation.start_x, operation.start_z)
        return lines

    def drill(self, operation: DrillOperation, settings: PostSettings) -> list[str]:
        """A hole as a canned cycle (`drilling_style = cycle`) when the post has the concept of its kind (`cycle_concept`), else as plain moves.
        A cycle starts at the start of the hole and pecks from there (WOP measures the pecks from the surface, so a cycle's pecks end up to
        one clearance higher than the plain moves; the same material is removed) and ends there: a rapid takes the drill on to the safe Z,
        unless the template writes the exit itself (`<drill exit Z>`)."""
        self.settings = settings
        concept = cycle_concept(operation)
        if self.definition.settings.drilling_style != "cycle" or concept is None or self.definition.lines_for(concept) is None:
            return super().drill(operation, settings)
        self.exit_written = False
        lines = self.render_concept(concept, {"op": operation, "feed": operation.feed_mm_per_rev})
        if not self.exit_written and abs(operation.end.z - operation.retract_z) > GEOMETRY_TOLERANCE_MM:
            self._moved(0, operation.retract_z)
            return lines + self.rapid(Rapid(operation.end))
        self._moved(operation.end.x, operation.end.z)
        return lines

    def machine_function(self, operation: MachineFunction, settings: PostSettings) -> list[str]:
        self.settings = settings
        concept = FUNCTION_CONCEPTS.get(operation.kind)
        if concept is None:
            raise PostError(f"this postprocessor cannot write {operation.kind.value}")
        return self.render_concept(concept, {"seconds": operation.seconds, "kind": operation.kind.value})

    def function_call(self, operation: FunctionCall) -> list[str]:
        return self.function(operation.name, dict(operation.values))

    def tool_change(self, tool_number: int) -> list[str]:
        sequence, state = self.context.tool_sequence, self.state
        index = state.tool_cursor
        state.tool_index = index if index < len(sequence) and sequence[index] == tool_number else None
        state.tool_number = tool_number
        state.tool_cursor += 1
        return self.render_concept("tool_change")

    def _change_position_move(self, move: Rapid) -> list[str]:
        """The move to the tool change position written with the template [change_position] (the code of the controller for it). X and Z are
        the machine's tool change position in machine coordinates when it has one, else the position of the move in work coordinates. The work
        position is not known afterwards (the controller may have moved anywhere), so the next move writes both axes."""
        context = self.context
        known = context.change_radius_mm is not None and context.change_z_mm is not None
        scope = {"x": context.change_radius_mm, "z": context.change_z_mm} if known else {"x": move.end.x, "z": move.end.z}
        lines = self.render_concept("change_position", scope)
        state = self.state
        state.x = state.z = state.cx = state.cz = None
        return lines

    def _machine_change_move(self) -> list[str]:
        """The move to the tool change position (the planner's move to it, `Rapid.at_change`) in machine coordinates, G53, when the
        machine has such a position (nothing then: the move is written in work coordinates). The position in the work coordinates is
        not known afterwards, so the next move writes both axes."""
        context = self.context
        if context.change_radius_mm is None or context.change_z_mm is None:
            return []
        lines = self.render_concept("machine_rapid", {"x": context.change_radius_mm, "z": context.change_z_mm})
        if lines:
            state = self.state
            state.x = state.z = state.cx = state.cz = None
        return lines

    def set_spindle(self, setting: SpindleSetting) -> list[str]:
        css = setting.mode is SpindleMode.CONSTANT_SURFACE_SPEED
        self.state.rpm = None if css else setting.value
        self.state.css = (setting.value, setting.rpm_limit) if css else None
        self.state.direction = setting.direction
        return self.render_concept(
            "spindle_css" if css else "spindle_rpm", {"value": setting.value, "rpm_limit": setting.rpm_limit, "direction": setting.direction},
        )

    def stop_spindle(self) -> list[str]:
        lines = self.render_concept("spindle_stop")
        self.state.rpm = None
        self.state.css = None
        return lines

    def _spindle_speed(self) -> float | None:
        """The speed of the spindle now (rpm), None when it is off. With constant surface speed: from the radius of the last cut, not above the
        rpm limit of the block or the highest speed of the machine; without a radius (or any limit) the limit stands for it."""
        if self.state.rpm is not None:
            return self.state.rpm
        if self.state.css is None:
            return None
        surface_speed, limit = self.state.css
        caps = [value for value in (limit, self.context.max_rpm) if value]
        radius = self.state.cut_x
        if radius is not None and radius > GEOMETRY_TOLERANCE_MM:
            speed = surface_speed * M_PER_MIN_TO_MM_PER_MIN / (2 * math.pi * radius)
            return min([math.floor(speed), *caps])  # whole rpm: the steps of the ramp are round numbers
        if caps:
            return min(caps)
        raise PostError(
            "the speed of the spindle before the stop is not known (constant surface speed, no cut yet, no rpm limit in the block and no highest speed in the "
            "machine): give the block an rpm limit or the machine a highest speed, or turn the ramp off (spindle_ramp_step = 0)"
        )

    def spindle_ramp(self) -> list[str]:
        """The steps that slow the spindle down before a stop: from the speed now down in steps of `spindle_ramp_step` rpm, each with a wait,
        not below `spindle_ramp_min`. The spindle counts as stopped afterwards (the stop code follows). Nothing when the ramp is off."""
        settings = self.definition.settings
        step = settings.spindle_ramp_step
        if step <= 0:
            return []
        speed = self._spindle_speed()
        if speed is None:
            return []
        speeds = []
        level = speed - step
        while level > 0 and level >= settings.spindle_ramp_min:
            speeds.append(level)
            level -= step
            if len(speeds) > MAX_SPINDLE_RAMP_STEPS:
                raise PostError(f"the speed ramp from {speed:.0f} rpm in steps of {step:g} rpm would have more than {MAX_SPINDLE_RAMP_STEPS} steps: raise spindle_ramp_step")
        if speeds and self.definition.lines_for("spindle_ramp_step") is None:
            raise PostError("the post has a speed ramp (spindle_ramp_step) but no [spindle_ramp_step] template that writes one step")
        lines: list[str] = []
        for level in speeds:
            lines += self.render_concept(
                "spindle_ramp_step", {"value": level, "seconds": settings.spindle_ramp_dwell, "rpm_limit": None, "direction": self.state.direction},
            )
        self.state.rpm = None
        self.state.css = None
        return lines

    def set_coolant(self, mode: CoolantMode) -> list[str]:
        concept = {CoolantMode.NONE: "coolant_off", CoolantMode.FLOOD: "coolant_flood", CoolantMode.MIST: "coolant_mist"}[mode]
        return self.render_concept(concept)

    def function(self, name: str, values: dict | None = None) -> list[str]:
        """The lines of a custom concept of the post. `values` are the variables by name; the others have their default.
        Raises PostError for a function the post does not have, or a value outside min and max."""
        function = self.definition.functions.get(name)
        if function is None:
            raise PostError(f"the post has no function {name!r}")
        try:
            checked = check_values(function.variables, values or {})
        except VariableError as error:
            raise PostError(f"function {name}: {error.message}") from None
        return self.render_concept(name, {"variables": checked})
