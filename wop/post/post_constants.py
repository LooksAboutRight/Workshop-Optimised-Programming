"""Constants shared by the postprocessors."""

COORDINATE_DECIMALS = 3
FEED_DECIMALS = 3
SPEED_DECIMALS = 1
COORDINATE_DECIMALS_INCH = 4  # decimals of coordinates in an inch program
FEED_DECIMALS_INCH = 4  # decimals of feeds in an inch program
SPINDLE_RAMP_DWELL_S = 1.0  # the wait after every step of the speed ramp before a spindle stop (post setting spindle_ramp_dwell)
MAX_SPINDLE_RAMP_STEPS = 100  # a ramp of more steps than this is refused: the step is too small for the speed
INCHES_PER_FOOT = 12  # a constant surface speed in an inch program is in feet per minute
# Used by the fixed-RPM remedy: RPM = surface speed (m/min) * this / (pi * diameter in mm).
M_PER_MIN_TO_MM_PER_MIN = 1000
# Chord deviation allowed when arcs are replaced by short lines (remedy).
ARC_AS_LINES_DEVIATION_MM = 0.005

# The template engine (post files, `*.post.ini`).
POST_FILE_FORMAT_VERSION = 1
POST_FILE_SUFFIX = ".post.ini"
WOP_VERSION_TEXT = "0.1.0"  # the version of WOP, the same as `version` in pyproject.toml (`tests/test_version.py` checks it); the token <WOP version>
DEFAULT_LINE_NUMBER_PREFIX = "N"
DEFAULT_LINE_NUMBER_START = 10
DEFAULT_LINE_NUMBER_STEP = 10
SEPARATOR_PLACEHOLDER = "\ue000"  # stands for a space inside <text>...</text> while a line is tidied up
ESTIMATED_RAPID_MM_PER_MIN = 5000  # GUESS: for the estimated time when the machine has no maximum speeds: rapids at this speed
EXAMPLE_DATE_FORMAT = "%d.%m.%Y"
EXAMPLE_TIME_FORMAT = "%H:%M"

# The modal groups every post file knows (`[modal_groups]`): (name, meaning, modal). The names cannot be changed; the user types the
# codes of each group, and may add groups of their own. Codes of one modal group cancel each other; `changed` compares inside the group.
# A group that is not modal is never suppressed by `changed`.
FIXED_MODAL_GROUPS = (
    ("motion", "straight moves, arcs, threading and the cycles (LinuxCNC group 1)", True),
    ("plane", "working plane: G17 G18 G19", True),
    ("distance_mode", "absolute or incremental coordinates: G90 G91", True),
    ("arc_distance_mode", "absolute or incremental arc centres: G90.1 G91.1", True),
    ("feed_mode", "what the feed means: G93 G94 G95", True),
    ("units", "millimetres or inches: G20 G21", True),
    ("cutter_compensation", "tool nose radius compensation: G40 G41 G42", True),
    ("tool_length_compensation", "tool length offset: G43 G49", True),
    ("retract_mode", "return level of the cycles: G98 G99", True),
    ("coordinate_system", "work offset: G54 to G59", True),
    ("path_control", "exact stop or blending: G61 G64", True),
    ("spindle_mode", "constant surface speed or fixed rpm: G96 G97", True),
    ("diameter_mode", "X as diameter or radius on a lathe: G7 G8", True),
    ("spindle", "spindle on or off: M3 M4 M5", True),
    ("coolant", "coolant: M7 M8 M9", True),
    ("tool_change", "tool change: M6", True),
    ("program_stop", "stops: M0 M1 M2 M30", True),
    ("non_modal", "codes that work in one line only: G4 G28 G53 G92 ...", False),
)

# The codes every post file knows by name (`[codes]`): (name, meaning, heading). A template says `<code name>`; the post file types the code
# of each (an empty code: the controller has no such function). The names cannot be changed; the user may add codes of their own.
CODE_HEADING_MAIN = "Main functions (G codes)"
CODE_HEADING_MISC = "Miscellaneous functions (M codes)"
FIXED_CODES = (
    ("rapid", "rapid move", CODE_HEADING_MAIN),
    ("feed", "straight feed move", CODE_HEADING_MAIN),
    ("arc_ccw", "arc, counter-clockwise (in X towards Z)", CODE_HEADING_MAIN),
    ("arc_cw", "arc, clockwise", CODE_HEADING_MAIN),
    ("machine_coordinates", "the next move uses machine coordinates", CODE_HEADING_MAIN),
    ("dwell", "dwell (wait for some seconds)", CODE_HEADING_MAIN),
    ("thread_cycle", "thread cycle", CODE_HEADING_MAIN),
    ("drill_cycle", "canned drilling cycle", CODE_HEADING_MAIN),
    ("dwell_drill_cycle", "canned drilling cycle with a dwell at the bottom", CODE_HEADING_MAIN),
    ("chip_break_cycle", "canned peck drilling cycle that backs out only a little (chip breaking)", CODE_HEADING_MAIN),
    ("peck_dwell_drill_cycle", "canned peck drilling cycle with a dwell at the bottom", CODE_HEADING_MAIN),
    ("peck_drill_cycle", "canned peck drilling cycle", CODE_HEADING_MAIN),
    ("cycle_cancel", "cancel a canned cycle", CODE_HEADING_MAIN),
    ("css", "constant surface speed", CODE_HEADING_MAIN),
    ("rpm", "fixed spindle speed", CODE_HEADING_MAIN),
    ("spindle_limit", "highest spindle speed with constant surface speed", CODE_HEADING_MAIN),
    ("feed_per_rev", "feed per revolution", CODE_HEADING_MAIN),
    ("feed_per_minute", "feed per minute", CODE_HEADING_MAIN),
    ("units_mm", "units are millimetres", CODE_HEADING_MAIN),
    ("units_inch", "units are inches", CODE_HEADING_MAIN),
    ("absolute", "absolute coordinates", CODE_HEADING_MAIN),
    ("plane_zx", "the plane of a lathe (Z and X)", CODE_HEADING_MAIN),
    ("plane_xy", "the plane in which a cycle drills along Z", CODE_HEADING_MAIN),
    ("comp_left", "tool nose radius compensation, left of the contour", CODE_HEADING_MAIN),
    ("comp_right", "tool nose radius compensation, right of the contour", CODE_HEADING_MAIN),
    ("comp_off", "tool nose radius compensation off", CODE_HEADING_MAIN),
    ("diameter_mode", "X values are diameters", CODE_HEADING_MAIN),
    ("radius_mode", "X values are radii", CODE_HEADING_MAIN),
    ("tool_length_comp", "tool length offset on", CODE_HEADING_MAIN),
    ("exact_path", "path control: follow the programmed path exactly (LinuxCNC G61)", CODE_HEADING_MAIN),
    ("exact_stop", "path control: stop exactly at the end of every move (LinuxCNC G61.1)", CODE_HEADING_MAIN),
    ("path_blend", "path control: blend the moves for a smooth path (LinuxCNC G64)", CODE_HEADING_MAIN),
    ("program_stop", "program stop", CODE_HEADING_MISC),
    ("optional_stop", "optional stop", CODE_HEADING_MISC),
    ("program_end", "end of the program", CODE_HEADING_MISC),
    ("tool_change", "tool change", CODE_HEADING_MISC),
    ("spindle_cw", "spindle on, clockwise", CODE_HEADING_MISC),
    ("spindle_ccw", "spindle on, counter-clockwise", CODE_HEADING_MISC),
    ("spindle_stop", "spindle off", CODE_HEADING_MISC),
    ("coolant_mist", "mist coolant on", CODE_HEADING_MISC),
    ("coolant_flood", "flood coolant on", CODE_HEADING_MISC),
    ("coolant_off", "coolant off", CODE_HEADING_MISC),
)
CODE_CUSTOM_HEADING = "Custom codes"
CODE_WORK_OFFSET_HEADING = "Work offsets"
WORK_OFFSET_CODE_PREFIX = "work_offset_"  # the work offsets of a controller are the codes work_offset_1, work_offset_2 ... of the code table
