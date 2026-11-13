"""The conventions of WOP in one list: every rule of thumb, preset and limit a user may want to change.

Each entry names a constant (in `constants.py`, or in `ui/app_constants.py` for the application layer), says what it
means, puts it under a heading (`group`) and says what may be typed (`rule`). The values themselves stay where they are.
They sit above the line `NOT_EDITABLE_BELOW` of their module; everything below that line is fixed and only shown
read only in File > Preferences. The user's own values come from the file `conventions.json`
(convention_overrides.py), applied when the constants load. A test fails when a number or text above the marker has
no entry here, or an entry names a constant that is not above the marker.

A new constant: ask the user whether it should be editable. If yes: put it above the marker, add an entry here
(heading, meaning, rule). If not: put it below the marker.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

CORE = "wop.core.constants"
APP = "wop.ui.app_constants"
MARKER = "NOT_EDITABLE_BELOW"  # the name of the line in a constants module that ends the editable part

# Headings of the Preferences window, in this order.
NEW_PROJECT = "New project"
NEW_BLOCKS = "New blocks"
TOOLPATHS = "Tool paths"
GROOVING = "Grooving"
DRILLING = "Drilling"
THREADING = "Threading"
POWER = "Power estimate"
CHECKS = "Checks and tolerances (change only knowing the effect)"
DXF = "DXF import"
PROGRAM = "Program"
GROUPS = (NEW_PROJECT, NEW_BLOCKS, TOOLPATHS, GROOVING, DRILLING, THREADING, POWER, CHECKS, DXF, PROGRAM)

# What may be typed.
POSITIVE = "positive"  # a number above 0
NON_NEGATIVE = "non_negative"  # a number, 0 or more
ANY_NUMBER = "any_number"  # any number (a Z position may be negative)
WHOLE_POSITIVE = "whole_positive"  # a whole number, 1 or more
WHOLE_NON_NEGATIVE = "whole_non_negative"  # a whole number, 0 or more
SHARE = "share"  # above 0, at most 1
ANGLE = "angle"  # 0 up to below a right angle
PERCENT = "percent"  # above 0, at most 100
CHOICE = "choice"  # one of `choices` (numbers or text)
MATERIAL = "material"  # a name from the material table (the window offers the names)
RULES = (POSITIVE, NON_NEGATIVE, ANY_NUMBER, WHOLE_POSITIVE, WHOLE_NON_NEGATIVE, SHARE, ANGLE, PERCENT, CHOICE, MATERIAL)
RIGHT_ANGLE_DEG = math.degrees(math.pi / 2)


@dataclass(frozen=True)
class Convention:
    name: str  # the constant
    group: str  # the heading in Preferences
    meaning: str
    rule: str = POSITIVE
    module: str = CORE
    choices: tuple = ()  # for the rule CHOICE


def _percent_limit() -> float:
    from . import constants  # here, not at the top: constants.py imports this module while it loads

    return constants.PERCENT_OF_WHOLE


def _number_text(value: object) -> str:
    return f"{value:g}" if isinstance(value, (int, float)) else str(value)


def rule_text(convention: Convention) -> str:
    """What may be typed, in words (for the window)."""
    rule = convention.rule
    if rule == POSITIVE:
        return "a number above 0"
    if rule == NON_NEGATIVE:
        return "a number, 0 or more"
    if rule == ANY_NUMBER:
        return "any number"
    if rule == WHOLE_POSITIVE:
        return "a whole number, 1 or more"
    if rule == WHOLE_NON_NEGATIVE:
        return "a whole number, 0 or more"
    if rule == SHARE:
        return "a number above 0, at most 1"
    if rule == ANGLE:
        return f"an angle from 0 to below {_number_text(RIGHT_ANGLE_DEG)} degrees"
    if rule == PERCENT:
        return f"a number above 0, at most {_number_text(_percent_limit())}"
    if rule == CHOICE:
        return "one of " + ", ".join(_number_text(choice) for choice in convention.choices)
    return "a material name"


def check_value(convention: Convention, value: object) -> str | None:
    """Nothing when the value is allowed, otherwise what is wrong (in words)."""
    if convention.rule == MATERIAL:
        return None if isinstance(value, str) and value.strip() else "a name is needed"
    if convention.rule == CHOICE and not isinstance(value, bool) and value in convention.choices:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return f"not a number; allowed: {rule_text(convention)}"
    whole = float(value).is_integer()
    allowed = {
        POSITIVE: value > 0,
        NON_NEGATIVE: value >= 0,
        ANY_NUMBER: True,
        WHOLE_POSITIVE: whole and value >= 1,
        WHOLE_NON_NEGATIVE: whole and value >= 0,
        SHARE: 0 < value <= 1,
        ANGLE: 0 <= value < RIGHT_ANGLE_DEG,
        PERCENT: 0 < value <= _percent_limit(),
        CHOICE: False,  # a number that is not one of the choices
    }.get(convention.rule, False)
    return None if allowed else f"{_number_text(value)} is not allowed; allowed: {rule_text(convention)}"


CONVENTIONS = (
    # --- new project ---
    Convention("DEFAULT_NEW_PART_MATERIAL", NEW_PROJECT, "material of a new project (a name from the material table)", MATERIAL, APP),
    Convention("DEFAULT_NEW_PART_DIAMETER_MM", NEW_PROJECT, "diameter of the part in a new project", POSITIVE, APP),
    Convention("DEFAULT_NEW_PART_LENGTH_MM", NEW_PROJECT, "length of the part in a new project", POSITIVE, APP),
    Convention("DEFAULT_FRONT_Z_MM", NEW_PROJECT, "Z of the front face of a new part", ANY_NUMBER),
    Convention("DEFAULT_CLEARANCE_MM", NEW_PROJECT, "clearance of a new project: the gap kept between tool and material when approaching and retracting", POSITIVE, APP),
    Convention("SAFE_RADIUS_BEYOND_PART_MM", NEW_PROJECT, "the safe radius and the tool change radius follow the part: its outer radius plus this", NON_NEGATIVE, APP),
    Convention("SAFE_Z_IN_FRONT_MM", NEW_PROJECT, "the safe Z and the tool change Z follow the front face: front Z plus this", NON_NEGATIVE, APP),
    # --- new blocks ---
    Convention("DEFAULT_NEW_BLOCK_RPM", NEW_BLOCKS, "spindle speed of the first block of a project", POSITIVE, APP),
    Convention("EXAMPLE_FEED_MM_PER_REV", NEW_BLOCKS, "feed of a new block"),
    Convention("EXAMPLE_FINISH_FEED_MM_PER_REV", NEW_BLOCKS, "finishing feed of a new block"),
    Convention("EXAMPLE_DEPTH_OF_CUT_MM", NEW_BLOCKS, "depth of cut of a new block"),
    Convention("TAPER_INPUT", NEW_BLOCKS, "how the taper of a turning block is shown first (its button switches): the included angle in degrees or the rise of the diameter per 100 mm", CHOICE, APP, ("degrees", "rise per 100 mm")),
    Convention("TURNING_TAPER_DEG", NEW_BLOCKS, "taper of a new turning block, its included angle in degrees (0: straight, positive: larger towards the chuck)", ANY_NUMBER),
    Convention("EXAMPLE_FINISH_ALLOWANCE_MM", NEW_BLOCKS, "finishing allowance of a new block (a turning block with a nose radius overrides it, see the factor below)", NON_NEGATIVE),
    Convention("TURNING_FINISH_ALLOWANCE_NOSE_FACTOR", NEW_BLOCKS, "finishing allowance of a turning block = this x the nose radius, until typed", NON_NEGATIVE),
    Convention("FACING_OVERTRAVEL_NOSE_FACTOR", NEW_BLOCKS, "facing runs past the centre (or bore) by this many nose radii", NON_NEGATIVE),
    # --- tool paths ---
    Convention("COMPENSATION_LEAD_MARGIN_MM", TOOLPATHS, "lead-in and lead-out of a finishing pass with cutter compensation: the nose radius plus this", NON_NEGATIVE),
    # --- grooving ---
    Convention("GROOVE_ONE_SIDED_MODE", GROOVING, "a new grooving block gives the most the blade may cut wide with air on its other side in mm or as a percentage of the blade width", CHOICE, CORE, ("mm", "percent")),
    Convention("GROOVE_ONE_SIDED_CUT_MM", GROOVING, "that most, in mm (used when the mode above is mm)"),
    Convention("GROOVE_ONE_SIDED_CUT_PERCENT", GROOVING, "that most, in percent of the blade width (used when the mode above is percent)", PERCENT),
    Convention("GROOVE_FINISH_STOP_MIN_MM", GROOVING, "the finishing sweep along a groove bottom ends at least this early before the wall", NON_NEGATIVE),
    Convention("GROOVE_FINISH_STOP_BLADE_FRACTION", GROOVING, "... or this part of the blade width, whichever is more", SHARE),
    Convention("GROOVE_AIR_SKIP_MIN_MM", GROOVING, "air above an existing groove must be this deep to be crossed with a rapid", NON_NEGATIVE),
    # --- drilling ---
    Convention("EXAMPLE_DRILL_MODE", DRILLING, "drill mode of a new drilling block", CHOICE, CORE, ("drilling", "peck drilling", "peck drilling, full retract")),
    Convention("EXAMPLE_DRILL_DEPTH_MM", DRILLING, "depth of a new drilling block (positive, behind the front face)"),
    Convention("EXAMPLE_DRILL_TO_FULL_DIAMETER", DRILLING, "a new drilling block measures the depth to where the hole has its full diameter (yes) or to the tip of the drill (no)", CHOICE, CORE, ("yes", "no")),
    Convention("EXAMPLE_DRILL_FEED_MM_PER_REV", DRILLING, "feed of a new drilling block"),
    Convention("EXAMPLE_DRILL_PECK_MM", DRILLING, "peck depth of a new drilling block, also used when a block is switched to a peck mode with no peck depth"),
    Convention("EXAMPLE_DRILL_DWELL_S", DRILLING, "dwell at the bottom of the hole of a new drilling block, in seconds", NON_NEGATIVE),
    Convention("PECK_RETRACT_MM", DRILLING, "how far the tool backs out after a peck to break the chip", NON_NEGATIVE),
    Convention("DRILL_AIR_SKIP_MIN_MM", DRILLING, "an existing hole must save this much feed travel to be crossed with a rapid", NON_NEGATIVE),
    Convention("DRILL_REAPPROACH_MM", DRILLING, "a peck drill comes back this far above the last depth, then feeds", NON_NEGATIVE),
    # --- threading ---
    Convention("THREAD_LEAD_IN_PITCHES", THREADING, "run-in before a thread, in pitches, so the feed is synchronised"),
    Convention("THREAD_FIRST_CUT_MM", THREADING, "depth of the first thread pass (G76 J)"),
    Convention("THREAD_DEGRESSION_CONSTANT_AREA", THREADING, "G76 R: 1 = same depth every pass, 2 = same area every pass", CHOICE, CORE, (1, 2)),
    Convention("THREAD_SPRING_PASSES", THREADING, "passes without in-feed at the end of a thread (G76 H)", WHOLE_NON_NEGATIVE),
    Convention("THREAD_COMPOUND_ANGLE_DEG", THREADING, "in-feed along the flank (G76 Q)", ANGLE),
    Convention("THREAD_EXTERNAL_CREST_ALLOWANCE_MM", THREADING, "diameter an outside thread is turned under the major diameter (fit allowance)", NON_NEGATIVE),
    Convention("THREAD_INTERNAL_BORE_ALLOWANCE_MM", THREADING, "diameter added to the basic minor diameter of an inside thread", NON_NEGATIVE),
    # --- power ---
    Convention("POWER_EFFICIENCY", POWER, "share of the spindle power that reaches the cutting edge (power estimate)", SHARE),
    # --- checks and tolerances ---
    Convention("PATH_CHECK_STEP_MM", CHECKS, "distance between the positions tested along a move. A bigger step is faster but may miss a collision"),
    Convention("UNREACHED_MIN_AREA_MM2", CHECKS, "uncut pieces smaller than this are not reported", NON_NEGATIVE),
    Convention("COLLISION_PENETRATION_TOLERANCE_MM", CHECKS, "overlap deeper than this counts as a collision", NON_NEGATIVE),
    Convention("CUT_OFF_MIN_AREA_MM2", CHECKS, "a cut-off piece smaller than this is a sliver and is dropped", NON_NEGATIVE),
    # --- DXF ---
    Convention("DXF_MIN_LINE_LENGTH_MM", DXF, "DXF lines shorter than this are ignored", NON_NEGATIVE),
    # --- program ---
    Convention("DISPLAY_UNITS", PROGRAM, "the unit of lengths, feeds and sketch dimensions shown and typed in the window (the program, the files and the unit of the G-code do not change); takes effect after a restart", CHOICE, APP, ("mm", "inch")),
    Convention("UNDO_LIMIT", PROGRAM, "how many states Undo keeps", WHOLE_POSITIVE, APP),
)


def conventions_by_group() -> list[tuple[str, list[Convention]]]:
    """The conventions under their headings, in the order of GROUPS and of the table."""
    return [(group, [c for c in CONVENTIONS if c.group == group]) for group in GROUPS]
