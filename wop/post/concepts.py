"""The concepts: the things a post writes. A post file has one section per concept; each line of a section is a template.

A concept that a post does not have falls back on the default post ("generic"). What happens when nobody has it depends on
`needed`: a needed concept is an error when the program uses it (a missing stop, tool change or move must never be left out
silently); a concept that is not needed writes nothing (header, block start, the notes before a thread ... are decoration).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Concept:
    name: str
    description: str
    needed: bool = True


_LIST = (
    Concept("header", "start of the file, before everything", needed=False),
    Concept("setup", "units, plane, absolute mode, cancel compensation, feed mode", needed=False),
    Concept("footer", "spindle off, coolant off, end of the program"),
    Concept("comment", "one comment line (the text is <comment text>)"),
    Concept("block_start", "start of a block of the program", needed=False),
    Concept("rapid", "rapid move (X or Z can be empty for a move of one axis)"),
    Concept("feed", "straight feed move"),
    Concept("arc_ccw", "arc, counter-clockwise (in X towards Z)"),
    Concept("arc_cw", "arc, clockwise"),
    Concept("dwell", "wait for some seconds"),
    Concept("program_stop", "program stop"),
    Concept("optional_stop", "optional stop"),
    Concept("spindle_css", "start the spindle with constant surface speed"),
    Concept("spindle_rpm", "start the spindle with a fixed speed"),
    Concept("spindle_stop", "stop the spindle"),
    Concept("spindle_ramp_step", "one step of the speed ramp before the spindle stops: the speed is <S>, the wait <dwell> (setting spindle_ramp_step; used by <spindle ramp>)", needed=False),
    Concept("coolant_flood", "flood coolant on"),
    Concept("coolant_mist", "mist coolant on"),
    Concept("coolant_off", "coolant off"),
    Concept("change_position", "go to the tool change position with the code of the controller for it (G28 U0 W0 ...); X and Z are the position in machine coordinates when the machine has one, else in work coordinates. Wins over machine_rapid and the plain rapid move", needed=False),
    Concept("machine_rapid", "rapid move in machine coordinates before a tool change (the machine has a tool change position)", needed=False),
    Concept("tool_change", "change the tool (with the offset)"),
    Concept("thread_cycle", "thread in one block (threading_style = cycle)"),
    Concept("thread_two_block", "thread in two blocks (threading_style = two_block)"),
    Concept("thread_passes", "lines before a thread written as plain passes (threading_style = passes)", needed=False),
    Concept("drill_cycle", "canned cycle for a hole with a depth only (drilling_style = cycle; without it the hole is written as plain moves)", needed=False),
    Concept("dwell_drill_cycle", "canned cycle for a hole with a depth and a dwell at the bottom", needed=False),
    Concept("peck_drill_cycle", "canned peck cycle that backs out to the start after every peck", needed=False),
    Concept("chip_break_cycle", "canned peck cycle that backs out only a little after every peck (chip breaking)", needed=False),
    Concept("peck_dwell_drill_cycle", "canned peck cycle with a dwell at the bottom", needed=False),
    Concept("tool_entry", "one line per tool of <list tools>", needed=False),
    Concept("note_entry", "one line per note of <list notes>", needed=False),
)
CONCEPTS = {concept.name: concept for concept in _LIST}

DRILL_CYCLES = frozenset({"drill_cycle", "dwell_drill_cycle", "peck_drill_cycle", "chip_break_cycle", "peck_dwell_drill_cycle"})
MOVES = frozenset({"rapid", "feed", "arc_ccw", "arc_cw", "machine_rapid", "change_position"})
ARCS = frozenset({"arc_ccw", "arc_cw"})
THREADS = frozenset({"thread_cycle", "thread_two_block", "thread_passes"})
SPINDLE = frozenset({"spindle_css", "spindle_rpm", "spindle_ramp_step"})
