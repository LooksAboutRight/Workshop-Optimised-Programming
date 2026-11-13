"""Central constants (requirement A5).

Every tolerance, default and conversion factor of the core lives here.
Other core modules may only use the literals 0, 1, -1 and 2 directly.
All lengths are in millimetres.
"""

import math

# === Values the user may change (File > Preferences, file conventions.json) ===========================
# Every number or text here must have an entry in core/conventions.py (name, meaning, topic, rule): a test fails
# otherwise. A new constant goes here only if the user wants it editable (ask him); everything below the marker
# is fixed. Changes apply after a restart of WOP.
# Overlap deeper than this counts as a collision; touching or grazing does not.
COLLISION_PENETRATION_TOLERANCE_MM = 0.005
# Distance between the positions tested along a tool path or a contour.
# Thin obstacles smaller than this can be missed; 0.5 mm is a first guess.
PATH_CHECK_STEP_MM = 0.5
CUT_OFF_MIN_AREA_MM2 = 1e-3  # a piece smaller than this is a numerical sliver: never the held part, dropped without a word
# Axial position of the end face of the raw part unless the user sets another.
DEFAULT_FRONT_Z_MM = 0
# Material left uncut inside a block's outline that is smaller than this area is not
# reported (slivers at corners and arcs); larger pieces are reported as unreachable.
UNREACHED_MIN_AREA_MM2 = 0.25
EXAMPLE_FEED_MM_PER_REV = 0.2
EXAMPLE_FINISH_FEED_MM_PER_REV = 0.1
EXAMPLE_DEPTH_OF_CUT_MM = 1
EXAMPLE_FINISH_ALLOWANCE_MM = 0.2
TURNING_TAPER_DEG = 0  # the taper of a new turning block: its included angle (0: straight, positive: larger towards the chuck)
# Next plunge is at most this fraction of the blade width further along the groove.
GROOVE_ONE_SIDED_MODE = "mm"  # how a new grooving block gives it: "mm" or "percent" (of the blade width)
GROOVE_ONE_SIDED_CUT_MM = 1.0  # most a blade may cut wide with air on its other side (next to a wall), in mm
GROOVE_ONE_SIDED_CUT_PERCENT = 50  # the same, as a percentage of the blade width
GROOVE_FINISH_STOP_MIN_MM = 0.2  # the finishing pass along the bottom ends this early before the wall ...
GROOVE_FINISH_STOP_BLADE_FRACTION = 0.5  # ... or this part of the blade width, whichever is more
GROOVE_EDGE_SIZE_MM = 0.5  # size of a chamfer or a fillet on the edge of a groove wall when the block is given one
GROOVE_EDGE_SKIN_MM = 0.2  # the roughing leaves this much on a wall with a chamfer or a fillet: the edge and the wall are cut in one move
GROOVE_EDGE_RELIEF_MM = 0.5  # before an edge is cut the groove is opened this much deeper than the edge is large (style Edges before full depth)
# What a new drilling block opens with (the order is the order in Preferences).
EXAMPLE_DRILL_MODE = "peck drilling"  # "drilling", "peck drilling" or "peck drilling, full retract" (the names of the Drill mode dropdown)
EXAMPLE_DRILL_DEPTH_MM = 15  # the depth, positive: the hole goes this far behind the front face
EXAMPLE_DRILL_TO_FULL_DIAMETER = "yes"  # "yes": the depth is where the hole has its full diameter; "no": the tip of the drill reaches it
EXAMPLE_DRILL_FEED_MM_PER_REV = 0.1
EXAMPLE_DRILL_PECK_MM = 5  # used by the two peck modes
EXAMPLE_DRILL_DWELL_S = 0  # at the bottom of the hole
# After each peck the tool backs out this far to break the chip.
PECK_RETRACT_MM = 0.5
GROOVE_AIR_SKIP_MIN_MM = 0.5  # air above an existing groove must be at least this deep to be rapided through
DRILL_AIR_SKIP_MIN_MM = 0.5  # an existing hole must save at least this much feed travel to be rapided through
DRILL_REAPPROACH_MM = 0.25  # a peck drill comes back this far above the last depth, then feeds
THREAD_COMPOUND_ANGLE_DEG = 29.5  # in-feed along the flank (G76 Q)
THREAD_LEAD_IN_PITCHES = 3  # run-in before the thread so the feed is synchronised
THREAD_FIRST_CUT_MM = 0.3
THREAD_DEGRESSION_CONSTANT_AREA = 2.0  # G76 R: 1 constant depth, 2 constant area
THREAD_SPRING_PASSES = 1
THREAD_EXTERNAL_CREST_ALLOWANCE_MM = 0  # diameter taken off the major diameter of an outside thread (fit allowance)
THREAD_INTERNAL_BORE_ALLOWANCE_MM = 0  # diameter added to the basic minor diameter of an inside thread
POWER_EFFICIENCY = 0.8  # share of the spindle power that reaches the cutting edge
DXF_MIN_LINE_LENGTH_MM = 0.01  # shorter lines are ignored
# Facing runs past the centre (or the bore of a tube) by this many nose radii, so no pip is left.
FACING_OVERTRAVEL_NOSE_FACTOR = 2
# The finishing allowance of a turning block follows the nose radius of the tool until the user types a value (GUESSED, to review).
TURNING_FINISH_ALLOWANCE_NOSE_FACTOR = 0.5
COMPENSATION_LEAD_MARGIN_MM = 1  # lead-in and lead-out of a compensated finishing pass: the nose radius plus this

NOT_EDITABLE_BELOW = True  # marker: the constants below this line are fixed (shown read only in Preferences)

# --- Units -----------------------------------------------------------------
MM_PER_INCH = 25.4
PERCENT_OF_WHOLE = 100

# --- Geometry --------------------------------------------------------------
# Two coordinates closer than this are treated as the same point.
GEOMETRY_TOLERANCE_MM = 1e-6
WORKHOLDING_NOTE_TOLERANCE_MM = 0.01  # a jaw front face this close to the clamping plane counts as at it (WH3)


# Largest allowed distance between an arc and the polyline that replaces it.
ARC_MAX_DEVIATION_MM = 0.001

# An arc is never replaced by chords that span more than this angle.
MAX_ARC_SEGMENT_ANGLE_RAD = math.pi / 2

# Two directions with a cross product below this are treated as parallel.
ANGLE_TOLERANCE_RAD = 1e-9

# Coarser arc approximation used only for the crossing check (speed).
CROSSING_CHECK_ARC_DEVIATION_MM = 0.01

# With fewer segments every pair is adjacent, so no crossing check is made.
MIN_SEGMENTS_FOR_CROSSING_CHECK = 3

OFFSET_CACHE_SIZE = 8  # offsets kept per area (Region); few distances are used on the same area

# A polygon needs at least this many corners.
MIN_POLYGON_POINTS = 3

CONTACT_SEARCH_STEPS = 20  # halvings that find where a tool first touches material (about a millionth of a step)
# A rapid move far from everything skips the positions it cannot touch anything at; this much distance is kept as a reserve.
RAPID_SKIP_MARGIN_MM = 0.5
RAPID_SKIP_UNLIMITED = 1_000_000_000  # nothing to touch at all: the rest of the move is free
STRAIGHT_WAY_STEP_MM = 0.5  # spacing of the points tested on a straight rapid for material in the way

# Size of the default jaws: a flat plane at the clamping position, this deep and wide.
DEFAULT_JAWS_EXTENT_MM = 1000

# --- Workholding (chuck body and jaws, WH1) --------------------------------------
WORKHOLDING_FORMAT_VERSION = 1
FULL_TURN_DEG = 360
MIN_JAW_COUNT = 2
DEFAULT_JAW_COUNT = 3
DEFAULT_JAW_WIDTH_DEG = 60  # angle of one jaw around the spindle axis (3D picture only; collision treats jaws as a ring)
# Named points that the placement uses (the user can add more points for the steps of a jaw).
JAWS_MOUNT_POINT = "mount"  # on the jaws: where the chuck face meets the jaws (only its Z counts)
CHUCK_FACE_POINT = "face"  # on the chuck body: its front face (only its Z counts)
# PLACEHOLDER example shapes offered by Add (x = radius, z = axial, front of the jaws at z = 0, body towards -z).
# Typical sizes, not from a catalogue: the user draws the real ones in the Sketch editor.
EXAMPLE_JAWS_OUTLINE = ((25, 0), (45, 0), (45, -24), (15, -24), (15, -12), (25, -12))
EXAMPLE_JAWS_POINTS = (("step 1", 25, -12), ("step 2", 15, -24), (JAWS_MOUNT_POINT, 45, -24))
EXAMPLE_CHUCK_OUTLINE = ((20, 0), (100, 0), (100, -70), (20, -70))
EXAMPLE_CHUCK_POINTS = ((CHUCK_FACE_POINT, 20, 0),)

# --- Toolpaths ------------------------------------------------------------

# --- Raw part --------------------------------------------------------------

# --- Tool table -----------------------------------------------------------
# Tool tip orientation numbers (as in the LinuxCNC tool table): 0 to 9.
MAX_TOOL_ORIENTATION = 9

# --- Materials -------------------------------------------------------------
# Built-in materials: (name, specific cutting force in N/mm2).
# Rough textbook values for a first power estimate; to be reviewed (design notes, GUESS).
BUILTIN_MATERIALS = (
    ("Mild steel", 1800),
    ("Stainless steel", 2400),
    ("Aluminium", 700),
    ("Brass", 800),
    ("Cast iron", 1100),
)

# --- Files -----------------------------------------------------------------
# Version of the saved contour data; increase it when the layout changes.
CONTOUR_FORMAT_VERSION = 1
MACHINE_FORMAT_VERSION = 1
PROJECT_FORMAT_VERSION = 1
TOOL_FORMAT_VERSION = 1
MATERIAL_FORMAT_VERSION = 1
APP_SETTINGS_FORMAT_VERSION = 1
LIBRARY_FORMAT_VERSION = 1

# Libraries (LIB1): one file per library in the app folder, one folder per kind.
LIBRARIES_FOLDER_NAME = "libraries"
LIBRARY_FILE_SUFFIX = ".json"
EXAMPLE_LIBRARY_NAME = "Example"  # always there, built in, read only: the first change forks it
USER_LIBRARY_NAME = "My library"  # the name a forked or migrated library gets
LIBRARY_KIND_MATERIALS = "materials"
LIBRARY_KIND_WORKHOLDING = "workholding"
LIBRARY_KIND_TOOLS = "tools"
MACHINES_FOLDER_NAME = "machines"  # one file per machine, next to the settings file (LIB3)
EXAMPLE_TOOL_NAME_PREFIX = "Example"
LIBRARY_NAME_FORBIDDEN_CHARS = '\\/:*?"<>|'
EXAMPLE_JAWS_NAME = "Example jaws"
EXAMPLE_CHUCK_NAME = "Example chuck"

# --- Starter tool (a plain rectangular tool until the tool editor exists) --------
STARTER_TOOL_WIDTH_MM = 8
STARTER_TOOL_HEIGHT_MM = 12

# --- Values of a newly added block (the user changes them afterwards) -----------
EXAMPLE_TARGET_RADIUS_MM = 10
EXAMPLE_TURNING_LENGTH_MM = 20

# --- Grooving ---------------------------------------------------------------------
EXAMPLE_GROOVE_WIDTH_MM = 4
DRILL_TOOL_DIAMETER_MM = 6
DRILL_TOOL_FLUTE_LENGTH_MM = 30
DRILL_TOOL_SHANK_LENGTH_MM = 30
DRILL_TIP_ANGLE_DEG = 118
HALF = 0.5
EXAMPLE_GROOVE_START_Z_MM = -10
EXAMPLE_GROOVE_BOTTOM_RADIUS_MM = 8
# Plain grooving tool made by the preset: blade, then a wider holder.
GROOVE_TOOL_BLADE_WIDTH_MM = 3
GROOVE_TOOL_BLADE_REACH_MM = 10
GROOVE_TOOL_HOLDER_WIDTH_MM = 12
GROOVE_TOOL_HOLDER_LENGTH_MM = 20

# --- threading (ISO metric 60 degree thread) ---
# ISO 68-1 basic profile of the metric 60 degree thread: depth = factor * pitch (outside 17/24 of the sharp V, inside 5/8). Fixed: they follow from the geometry.
THREAD_DEPTH_FACTOR_EXTERNAL = 0.6134
THREAD_DEPTH_FACTOR_INTERNAL = 0.5413
THREAD_FLANK_HALF_ANGLE_DEG = 30
THREAD_COMPOUND_ANGLE_LIMIT_DEG = 90  # the angle must be below this
THREAD_CREST_TOLERANCE_MM = 0.01  # material this far above the crest means "turn it first"
# --- thread designations (core/thread_designation.py) ---
THREAD_PITCH_DIAMETER_FACTOR = 0.6495  # pitch diameter = major diameter - factor * pitch (60 degree profile)
THREAD_TRAPEZOID_FLANK_HALF_ANGLE_DEG = 15  # ISO 2904: 30 degrees between the flanks
THREAD_TRAPEZOID_HEIGHT_FACTOR = 0.5  # basic flank height H1 = factor * pitch
THREAD_TRAPEZOID_CLEARANCES = ((1.5, 0.15), (5, 0.25), (12, 0.5), (44, 1))  # (pitch up to this, clearance ac in mm)
THREAD_COMPOUND_MARGIN_DEG = 0.5  # compound angle of a designation = flank half angle minus this
THREAD_FLANK_MISMATCH_DEG = 1  # the block tells when the tool flank and the thread flank differ by more than this
NUMBERED_SCREW_BASE_IN = 0.06  # machine screw size N: diameter = base + step * N inches
NUMBERED_SCREW_STEP_IN = 0.013
THREAD_SIZE_MATCH_TOLERANCE_IN = 0.0005  # a size matches a table entry within this
# ISO 261 coarse pitches (major diameter mm, pitch mm)
METRIC_COARSE_PITCHES = (
    (1, 0.25), (1.2, 0.25), (1.4, 0.3), (1.6, 0.35), (1.8, 0.35), (2, 0.4), (2.5, 0.45), (3, 0.5), (3.5, 0.6),
    (4, 0.7), (5, 0.8), (6, 1), (7, 1), (8, 1.25), (10, 1.5), (12, 1.75), (14, 2), (16, 2), (18, 2.5), (20, 2.5),
    (22, 2.5), (24, 3), (27, 3), (30, 3.5), (33, 3.5), (36, 4), (39, 4), (42, 4.5), (45, 4.5), (48, 5), (52, 5),
    (56, 5.5), (60, 5.5), (64, 6),
)
# Unified threads (size, threads per inch)
UNC_THREADS = (
    ("#1", 64), ("#2", 56), ("#3", 48), ("#4", 40), ("#5", 40), ("#6", 32), ("#8", 32), ("#10", 24), ("#12", 24),
    ("1/4", 20), ("5/16", 18), ("3/8", 16), ("7/16", 14), ("1/2", 13), ("9/16", 12), ("5/8", 11), ("3/4", 10),
    ("7/8", 9), ("1", 8), ("1 1/8", 7), ("1 1/4", 7), ("1 3/8", 6), ("1 1/2", 6), ("1 3/4", 5), ("2", 4.5),
)
UNF_THREADS = (
    ("#0", 80), ("#1", 72), ("#2", 64), ("#3", 56), ("#4", 48), ("#5", 44), ("#6", 40), ("#8", 36), ("#10", 32),
    ("#12", 28), ("1/4", 28), ("5/16", 24), ("3/8", 24), ("7/16", 20), ("1/2", 20), ("9/16", 18), ("5/8", 18),
    ("3/4", 16), ("7/8", 14), ("1", 12), ("1 1/8", 12), ("1 1/4", 12), ("1 3/8", 12), ("1 1/2", 12),
)
THREAD_TOOL_TIP_HEIGHT_MM = 3  # the 60 degree point of the preset tool, tip to the holder
THREAD_TOOL_HOLDER_LENGTH_MM = 25
EXAMPLE_THREAD_CREST_RADIUS_MM = 15
EXAMPLE_THREAD_PITCH_MM = 1.5
EXAMPLE_THREAD_START_Z_MM = 0
EXAMPLE_THREAD_LENGTH_MM = 15

# --- spindle power estimate (requirement M4); everything here is a rough model ---
SPINDLE_MIN_RADIUS_MM = 0.5  # radius used for cutting speed near the axis
MM_PER_M = 1000
POWER_FORMULA_DIVISOR = 60000  # kW = kc [N/mm2] * ap [mm] * f [mm/rev] * vc [m/min] / this
POWER_LABEL = "estimate"

# --- DXF import (requirement C6) ---
DXF_JOIN_TOLERANCE_MM = 0.1  # ends this close count as one point
DXF_EXACT_START_TOLERANCE_MM = 1e-7  # an arc start this close to the previous end keeps its centre
DXF_AXIS_TOLERANCE_MM = 1e-3  # lines lying on the spindle axis (radius 0) are dropped
DXF_INCH_TO_MM = 25.4
DXF_UNITS_INCH_CODE = 1  # value of the DXF $INSUNITS header for inches
DXF_LABEL_DISTANCE_MM = 15.0  # a POINT takes the name of the nearest TEXT this close (named points from CAD, TH1)
DEGREES_PER_TURN = 360
FLAT_ANGLE_DEG = 180

# --- ISO insert designation (requirement T9, ISO 1832) ---
# The tables are written from memory of the standard and have to be checked against it.
# Shape letter, name, tip angle of the acute corner in degrees, edge length divided by the inscribed circle.
INSERT_SHAPES_SUPPORTED = (
    ("S", "square", 90, 1.0),
    ("T", "triangle", 60, 1.732051),
    ("C", "rhombic 80", 80, 1.015427),
    ("D", "rhombic 55", 55, 1.220775),
    ("E", "rhombic 75", 75, 1.035276),
    ("M", "rhombic 86", 86, 1.002442),
    ("V", "rhombic 35", 35, 1.743447),
)
INSERT_SHAPES_UNSUPPORTED = (
    ("H", "hexagon"), ("O", "octagon"), ("P", "pentagon"), ("L", "rectangle"), ("R", "round"),
    ("W", "trigon 80"), ("A", "parallelogram 85"), ("B", "parallelogram 82"), ("K", "parallelogram 55"),
)
INSERT_SQUARE_LETTER = "S"
INSERT_TRIANGLE_LETTER = "T"
# Clearance (relief) angle in degrees; None: other, as given in the catalogue.
INSERT_CLEARANCES = (
    ("A", 3), ("B", 5), ("C", 7), ("D", 15), ("E", 20), ("F", 25), ("G", 30), ("N", 0), ("P", 11), ("O", None),
)
# Tolerance class: letters and a short description (the values themselves are not used).
INSERT_TOLERANCES = (
    ("A", "ground, close"), ("C", "ground, close"), ("E", "ground, close"), ("F", "ground, close"),
    ("G", "ground"), ("H", "ground, close"), ("J", "ground, close"), ("K", "ground, close"),
    ("L", "ground, close"), ("M", "pressed or ground"), ("N", "pressed or ground"), ("U", "pressed, wide"),
)
# Type: hole and chipbreaker (not used for the 2D shape).
INSERT_TYPES = (
    ("A", "cylindrical hole"), ("B", "hole, countersunk 70-90 degrees on one side"),
    ("C", "hole, countersunk 70-90 degrees on both sides"), ("F", "no hole, chipbreaker on both sides"),
    ("G", "cylindrical hole, chipbreaker on both sides"),
    ("H", "hole, countersunk 70-90 degrees on one side, chipbreaker on one side"),
    ("J", "hole, countersunk 70-90 degrees on both sides, chipbreaker on both sides"),
    ("M", "cylindrical hole, chipbreaker on one side"), ("N", "no hole"),
    ("Q", "hole, countersunk 40-60 degrees on both sides"),
    ("R", "no hole, chipbreaker on one side"),
    ("T", "hole, countersunk 40-60 degrees on one side, chipbreaker on one side"),
    ("U", "hole, countersunk 40-60 degrees on both sides, chipbreaker on both sides"),
    ("W", "hole, countersunk 40-60 degrees on one side"), ("X", "special design"),
)
# Inscribed circle diameters in mm (inch series first, then metric); the size code is the edge length
# rounded down after adding INSERT_SIZE_ROUNDING_MM.
INSERT_INSCRIBED_CIRCLES_MM = (
    3.97, 5.56, 6.35, 7.94, 9.525, 12.7, 15.875, 19.05, 25.4, 31.75, 6, 8, 10, 12, 16, 20, 25, 32,
)
INSERT_SIZE_ROUNDING_MM = 0.05
INSERT_THICKNESSES_MM = (
    ("01", 1.59), ("T1", 1.98), ("02", 2.38), ("T2", 2.78), ("03", 3.18), ("T3", 3.97),
    ("04", 4.76), ("05", 5.56), ("06", 6.35), ("07", 7.94), ("09", 9.52),
)
INSERT_CORNER_RADII_MM = (
    ("00", 0), ("02", 0.2), ("04", 0.4), ("08", 0.8), ("12", 1.2), ("16", 1.6),
    ("20", 2.0), ("24", 2.4), ("28", 2.8), ("32", 3.2),
)
INSERT_EDGE_PREPARATIONS = (("F", "sharp edge"), ("E", "rounded edge"), ("T", "chamfered edge"), ("S", "chamfered and rounded edge"))
INSERT_HANDS = (("R", "right hand"), ("L", "left hand"), ("N", "neutral"))
INSERT_LETTER_POSITIONS = 4  # shape, clearance, tolerance, type
INSERT_CODE_WIDTH = 2  # size, thickness and corner radius have two characters each
INSERT_POSITIONS = 7
INSERT_POSITION_NAMES = ("shape", "clearance", "tolerance", "type", "size", "thickness", "corner radius")
INSERT_DEFAULT_DESIGNATION = "CNMG 120408"
INSERT_POSITION_SHAPE, INSERT_POSITION_CLEARANCE, INSERT_POSITION_TOLERANCE, INSERT_POSITION_TYPE = 1, 2, 3, 4
INSERT_POSITION_SIZE, INSERT_POSITION_THICKNESS, INSERT_POSITION_RADIUS = 5, 6, 7
EXAMPLE_DWELL_S = 1
# --- Custom path block (requirement B12) ---
EXAMPLE_PATH_START_X_MM = 16
EXAMPLE_PATH_START_Z_MM = 2
EXAMPLE_PATH_END_Z_MM = -10
EXAMPLE_PATH_INNER_X_MM = 12
EXAMPLE_PATH_CHAMFER_MM = 1
EXAMPLE_PATH_FEED_MM_PER_REV = 0.1
DEFAULT_PATH_ARC_RADIUS_MM = 5

# --- ISO tool holders (ISO 5608 rectangular holders, ISO 5609 / 6261 boring bars) ---
# VALUES MARKED "guessed" ARE NOT FROM A STANDARD YOU HAVE READ and must be checked against ISO 5610-2..15 and ISO 6261 (design notes, GUESS).
HOLDER_CLAMPING = (
    ("C", "top clamping (insert without hole)"), ("M", "top and hole clamping"),
    ("P", "hole clamping"), ("S", "screw clamping through hole"),
)
# Style letter, cutting edge angle kappa in degrees (the main edge, towards the chuck), offset shank, cutting direction.
# ISO 5608 table 3. The head shape itself is not standardised: it is drawn as a plain wedge (guessed).
HOLDER_STYLES = (
    ("A", 90, False, "side cutting"), ("B", 75, False, "side cutting"), ("C", 90, False, "end cutting"),
    ("D", 45, False, "side cutting"), ("E", 60, False, "side cutting"), ("F", 90, True, "end cutting"),
    ("G", 90, True, "side cutting"), ("H", 107.5, True, "side cutting"), ("J", 93, True, "side cutting"),
    ("K", 75, True, "end cutting"), ("L", 95, True, "side and end cutting"), ("M", 50, False, "side cutting"),
    ("N", 63, False, "side cutting"), ("P", 117.5, True, "side cutting"), ("R", 75, True, "side cutting"),
    ("S", 45, True, "side cutting"), ("T", 60, True, "side cutting"), ("U", 93, True, "end cutting"),
    ("V", 72.5, False, "side cutting"), ("W", 60, True, "end cutting"), ("Y", 85, True, "end cutting"),
)
HOLDER_HANDS = (("R", "right hand"), ("L", "left hand"), ("N", "either hand (drawn as right hand)"))
HOLDER_SECTIONS = ("0808", "1010", "1212", "1616", "2020", "2525", "3225", "3232", "4032", "4040", "5050")
# Standard shank sizes per style (ISO 5610-1 table 1, read from the pictures; some dots unclear). Styles that are not
# listed have no standard shank sizes: every size is offered.
HOLDER_STYLE_SECTIONS = (
    ("A", ("1010", "1212", "1616", "2020", "2525", "3225", "3232", "4040")),
    ("B", ("0808", "1010", "1212", "1616", "2020", "2525", "3225", "4040", "5050")),
    ("D", ("0808", "1010", "1212", "1616", "2020", "2525", "3225", "3232", "4040")),
    ("F", ("0808", "1010", "1212", "1616", "2020", "2525", "3225", "3232", "4040")),
    ("G", ("0808", "1010", "1212", "1616", "2020", "2525", "3225", "3232", "4040", "5050")),
    ("H", ("1212", "1616", "2020", "2525", "3225")),
    ("J", ("0808", "1010", "1212", "1616", "2020", "2525", "3225", "4032")),
    ("K", ("0808", "1010", "1212", "1616", "2020", "2525", "3225", "3232", "4040")),
    ("L", ("0808", "1010", "1212", "1616", "2020", "2525", "3225", "3232", "4040")),
    ("N", ("0808", "1010", "1212", "1616", "2020", "2525", "3225", "4032")),
    ("R", ("1212", "1616", "2020", "2525", "3225", "3232", "4040", "5050")),
    ("S", ("0808", "1010", "1212", "1616", "2020", "2525", "3225", "3232", "4040", "5050")),
    ("T", ("1212", "1616", "2020", "2525", "3225", "3232", "4040")),
    ("V", ("1212", "1616", "2020", "2525", "3225")),
)
# Dimension f (tip to the far side of the shank) of OFFSET shanks by the width b of the shank: guessed (about 1.25 b).
HOLDER_OFFSET_F_MM = (
    (8, 10), (10, 12), (12, 16), (16, 20), (20, 25), (25, 32), (32, 40), (40, 50), (50, 63),
)
HOLDER_STRAIGHT_F_FACTOR = 1  # straight shank (guessed): the tip is in line with the front face, f = b
HOLDER_HEAD_NECK_SLOPE = 1  # the head narrows to the shank at 45 degrees (guessed)
# Tool length letters l1 in mm (ISO 5608 / 6261 table 2).
HOLDER_LENGTHS_MM = (
    ("A", 32), ("B", 40), ("C", 50), ("D", 60), ("E", 70), ("F", 80), ("G", 90), ("H", 100), ("J", 110), ("K", 125),
    ("M", 150), ("N", 160), ("P", 170), ("Q", 180), ("R", 200), ("S", 250), ("T", 300), ("U", 350), ("V", 400),
    ("W", 450), ("Y", 500),
)
HOLDER_SECTION_DIGITS = 2  # height and width are two digits each
HOLDER_DEFAULT_CODE = "PCLNR 2525 M12"
HOLDER_MIN_SECONDARY_ANGLE_DEG = 0  # the end cutting edge angle must not turn into the work
# Boring bars: shank diameter, f (point K to the axis), smallest bore (ISO 5609 table 1).
BORING_BARS = (
    (8, 6, 11), (10, 7, 13), (12, 9, 16), (16, 11, 20), (20, 13, 25), (25, 17, 32), (32, 22, 40), (40, 27, 50),
    (50, 35, 63), (60, 43, 80),
)
BORING_TYPES = (
    ("S", "solid steel"), ("A", "solid steel, coolant hole"), ("B", "solid steel, anti-vibration"),
    ("D", "solid steel, anti-vibration, coolant hole"), ("C", "carbide, steel head"),
    ("E", "carbide, steel head, coolant hole"), ("F", "carbide, steel head, anti-vibration"),
    ("G", "carbide, steel head, anti-vibration, coolant hole"), ("H", "heavy metal"),
    ("J", "heavy metal, coolant hole"), ("K", "heavy metal, steel head"), ("L", "heavy metal, steel head, coolant hole"),
)
# Boring bar styles (ISO 6261 table 5 is not in the preview): guessed from the common catalogue codes.
BORING_STYLES = (
    ("F", 90, "end cutting"), ("K", 75, "end cutting"), ("L", 95, "side and end cutting"),
    ("Q", 107.5, "side cutting"), ("S", 45, "side cutting"), ("U", 93, "end cutting"),
)
BORING_DEFAULT_CODE = "S25S-PCLNR 12"
HOLDER_LEFT_HAND = "L"
HOLDER_GUESS_NOTES = (
    "Approximate: the head of the holder is drawn as a plain envelope (not standardised).",
    "Guessed values (to check against ISO 5610-2..15): dimension f of offset shanks, length l1 of the holder.",
)
BORING_GUESS_NOTES = (
    "Approximate: the head of the bar is drawn as a plain envelope (not standardised).",
    "Guessed values (to check against ISO 6261): the style letters of boring bars and the length l1.",
)

# The order of the block types in the Add block menu: the common ones first, the special cases last.
# A type that is not listed comes after these, in alphabetical order.
BLOCK_MENU_ORDER = (
    "facing", "turning", "drilling", "threading", "grooving", "turning_contour",
    "machine_function", "custom_path",
)



# Two styles of one block may differ by a sliver at corners and arcs, not more (see core/blocks/styles.py).
STYLE_REMOVED_AREA_TOLERANCE_MM2 = 0.05
MAX_STYLE_PLUNGES = 2000  # plunges one grooving style may return for one block (a style that returns more is refused)

# --- The user's own values (conventions.json, see conventions.py) replace the defaults above ---
from .files.convention_overrides import apply_overrides  # noqa: E402  (must come last: it changes the values above)

DEFAULT_POSTPROCESSOR_ID = "linuxcnc"  # the postprocessor of a project without a machine

# --- tool reference point (the touch-off point) -----------------------------------------------------------
TIP_POINT = "tip"  # named point of a tool: where the tool is touched off; the tool path is the path of this point
TIP_DIRECTION_TOLERANCE_MM = 0.01  # a tool whose outline is this symmetric in Z (a threading tool) is touched off at its lowest-X point

# --- roughing: follow the contour, plunge into pockets ------------------------------------------------------
RIGHT_ANGLE_DEG = 90
STRAIGHT_ANGLE_DEG = 180
FOLLOW_SNAP_MM = 0.05  # how far the end of a roughing line may be from the contour plus allowance to follow it
EXAMPLE_MIN_FREE_ANGLE_DEG = 5  # the angle that must stay free between the back of the tool and the wall behind a pocket

# --- checking a move as a whole (core/verify.py: the swept area of the tool) ---------------------------------------
SWEEP_MIN_LENGTH_MM = 1  # a shorter move is simply followed in steps
SWEEP_CONTACT_SEARCH_STEPS = 14  # halvings that find where on a move the tool first touches something
HOLDER_BAND_MM = 0.0005  # half the thickness of the thin area that stands for a holder edge when it is swept
HOLDER_NORMAL_PROBE_MM = 0.005  # how far from an edge the side of the tool is looked for

# --- limits against runaway planning (fixed: a typo such as 0.0001 for 0.1 must not freeze the program) ---------
MAX_PASS_LEVELS = 3000  # cuts of one roughing, facing or peck sequence
MAX_SAMPLES_PER_SEGMENT = 20000  # positions tested along one straight or curved piece of a tool path
MAX_GROOVE_PLUNGES = 1000  # plunges of one grooving block
MAX_THREAD_PASSES = 500  # passes of one thread

# --- Tool types: the order in the Add menu and the standard turning tool (fixed; the numbers are GUESSED from the user's drawing "right rand cutter.DXF") ---
TOOL_TYPE_ORDER = ("turning", "holder", "boring", "boring_bar", "groove", "thread", "drill")  # type names; a type not listed comes last
TURNING_TOOL_SIDE_ANGLE_DEG = 96  # side edge to the feed direction (towards the chuck): 90 plus the 6 degrees the edge leans back
TURNING_TOOL_FRONT_ANGLE_DEG = 96  # front edge to the facing direction (towards the axis)
TURNING_TOOL_ANGLE_MIN_DEG = 45
TURNING_TOOL_ANGLE_MAX_DEG = 135
TURNING_TOOL_MIN_TIP_DEG = 10  # the angle between the two edges must stay above this
TURNING_TOOL_NOSE_RADIUS_MM = 0.3
TURNING_TOOL_EDGE_LENGTH_MM = 20  # side edge, from the sharp corner
TURNING_TOOL_WIDTH_MM = 20
TURNING_TOOL_LENGTH_MM = 100
TOOL_SHAPE_DECIMALS = 9  # the corners of a drawn turning tool are rounded to this many decimals (no 1e-16 noise in the files)
BORING_TOOL_NOSE_RADIUS_MM = 0.3  # the standard boring bar (the user's drawing "Boring bar.DXF"; GUESSED numbers)
BORING_TOOL_END_ANGLE_DEG = 96  # end edge (faces the chuck) to the feed direction
BORING_TOOL_WALL_ANGLE_DEG = 100  # wall edge (faces the bore wall) to the facing direction: it leans away from the wall by 10 degrees
BORING_TOOL_WALL_EDGE_LENGTH_MM = 25  # at most: the edge ends where it meets the bar (about 20 with the other defaults)
BORING_TOOL_FRONT_WIDTH_MM = 19.5  # the whole front of the head from the tip: the bar width plus the head that stands out
BORING_TOOL_BAR_WIDTH_MM = 16  # the full profile of the bar seen from above
BORING_TOOL_LENGTH_MM = 100
GROOVE_TOOL_CORNER_RADIUS_MM = 0.2  # the standard grooving tool (GUESSED numbers)
GROOVE_TOOL_FRONT_ANGLE_DEG = 90
GROOVE_TOOL_FRONT_ANGLE_MIN_DEG = 45
GROOVE_TOOL_FRONT_ANGLE_MAX_DEG = 135
GROOVE_TOOL_TYPE_HOLDER_LENGTH_MM = 100  # a tool of the grooving type; the old preset above has its own, shorter holder
THREAD_TOOL_INCLUDED_ANGLE_DEG = 60  # the standard threading tool (GUESSED numbers)
THREAD_TOOL_INCLUDED_MIN_DEG = 10
THREAD_TOOL_INCLUDED_MAX_DEG = 120
THREAD_TOOL_FLANK_MAX_DEG = 85  # each flank, from the radial direction: a flank that leans further would cut under
THREAD_TOOL_NOSE_RADIUS_MM = 0.1
THREAD_TOOL_FLAT_MM = 0  # no flat: a pointed tip
THREAD_TOOL_TIP_DISTANCE_MM = 6  # from the point to the side face on the cutting side: the point is in the middle of a 12 mm tool
THREAD_TOOL_WIDTH_MM = 12
THREAD_TOOL_LENGTH_MM = 100
THREAD_TOOL_CUTTING_HEIGHT_MM = 5
FIXED_FUNCTION_NAMES = ("program_stop", "optional_stop", "dwell", "spindle_stop")  # the functions of the machine function block that every post knows
REMOVED_CAPABILITIES = ("flood coolant", "mist coolant")  # names in older machine files that are ignored (a coolant is only a code now)
TURNING_TOOL_STEP_EPSILON_MM = 0.0005  # a step shorter than this is not drawn

TRIANGLE_CORNERS = 3  # a triangle has three corners
NEUTRAL_NOSE_TOLERANCE_DEG = 2.0  # the two back edges of a tool nose differ by no more than this: the tool has no hand (a symmetric V insert)
DEFAULT_WORK_OFFSET = "G54"  # the work offset a new project calls in the header of the program
CHAIN_SNAP_MM = 2 * ARC_MAX_DEVIATION_MM  # chains that came from polygons (arcs as chords) lie on each other when they are this close
WANTED_LEVEL_SHIFT_MM = 1e-5  # a line that lies exactly on a wall of the region (the deepest level) is tested this far on the free side of it, so it counts as inside
CHAIN_TOLERANCE_RETRIES = (4, 16)  # GUESS: when two chains cannot be joined (edges that nearly lie on each other), the boolean is tried again with the tolerance times these factors
CUT_JITTER_MM = ((0.0041, 0.0013), (-0.0037, 0.0029), (0.0023, -0.0047), (-0.0031, -0.0019))  # GUESS: when the strips of a cut cannot be joined to the material (a corner within a few thousandths of an edge), the whole cut is repeated with every strip moved by one of these shifts: the user's roughing accuracy is 0.01
CONTACT_POINT_SLACK_MM = 1e-5  # a contact point found by solving an equation must lie on both pieces within this (the arithmetic of the roots)
CUT_END_SNAP_MM = 0.01  # GUESS: the end of a cut that lies this close to the end of its wanted stretch is put on it (the user's roughing accuracy): it keeps steps of a thousandth of a millimetre out of the material border
MIDPOINT_FRACTION = 0.5  # the middle of a piece of a chain: where it is tested against another chain
WANTED_SPAN_MIN_MM = 0.01  # GUESS: a stretch of a roughing line shorter than this is not a line (the sliver limit of the analytic planner; the user's roughing accuracy is 0.01)
TIP_WALK_MAX_PIECES = 200  # a walk of the tool tip along the part is cut off after this many pieces (a safeguard against a walk that goes round)
CUT_TOLERANCE_FACTORS = (0.05, 0.005)  # GUESS: when a cut cannot be worked out with the snap distance (a sliver of the material thinner than it, between two arcs that nearly lie on each other), it is tried again with the tolerance times these factors
MIN_LOOP_PIECES = 3  # a loop with fewer pieces than this is not tidied (a circle of two arcs stays)
DIP_MIN_AREA_MM2 = 0.01  # GUESS: a line, or a pass along the contour under a line, that takes less material than this is dropped (the user's roughing accuracy is 0.01 mm)
RAPID_CLEARANCE_TOLERANCE_MM = 0.05  # the user's rule X12 (2026-10-22): a rapid may come this much closer to the material than the clearance (the test of the replay)
OFFSET_KEEP_TOLERANCE_MM = 1e-6  # exact offset (geometry/region_offset.py): a piece this much nearer than the distance to the old border still counts as on the offset
OFFSET_JOIN_TOLERANCE_MM = 1e-5  # exact offset: ends of kept pieces this close are one point
OFFSET_SIDE_FRACTION = 1e-3  # exact offset: two moved ends at a corner that point less apart than this part of the distance are a spike (the loop turns back on itself)
SHRUNK_NEAR_MARGIN_FACTOR = 4  # the checker shrinks the material only in the box of the swept tool grown by this many collision tolerances
BLOCK_CACHE_SIZE = 200  # GUESS: blocks whose results the window keeps for the next plan (`plan_cache.py`): a few programs of 50 blocks
BLOCK_CACHE_MATERIALS = 2  # results kept per block for different material before it: the whole plan and a plan of a selection
POWER_PEAK_TO_MEAN = 2.0  # GUESS: the power estimate of a custom path takes its biggest cut as this times its mean thickness
THREAD_HALF_ANGLE_DEG = 30.0  # the power estimate of a thread with radial infeed (compound angle 0): half the angle of a metric thread
NOSE_FOLLOW_TOLERANCE_MM = 0.002  # GUESS: the finishing pass follows the contour when the nose touches every point of it and cuts into the part nowhere, to this much
NOSE_FOLLOW_SAMPLE_MM = 0.1  # GUESS: the points of that test lie this far apart along the contour and the path of the nose centre
NOSE_RADIUS_SEARCH_STEPS = 12  # halvings that find the largest nose radius that follows the contour (the note: "needs N mm or smaller")
RIDE_END_FRACTION = 0.95  # a ride piece across X that still cuts beyond this fraction of its length is kept whole
RIDE_TRIM_STEPS = 8  # halvings that find where a ride across X stops cutting (to 1/500 of the piece)
NO_TOOL_NUMBER = 0  # the tool number of a block that has no tool chosen (T18); real tools are numbered from 1
RAW_OUTLINE_MARGIN_MM = 1.0  # a drawn raw part is cut off at the jaws by a box this much bigger than the piece, so no edge lies on an edge
EXAMPLE_PATH_SAFE_X_MM = 25  # the safe point that the sketch of an example path starts from (the block puts the real one in when it is planned)
EXAMPLE_PATH_SAFE_Z_MM = 5
PATH_OUTLINE_MAX_PIECES = 400  # GUESS: a part before a custom path block with more pieces than this is not drawn into the sketch of the path
SAFE_POINT_KEY = "safe point"  # the locked point of a path sketch: where every block starts and the path begins
CLAMP_PLANE_POINT = "clamping plane"  # the named point of a drawn raw part: where the jaws begin (only its Z counts)
ATTACH_MM = 0.01  # the material a finishing pass leaves standing in a corner is grown by this to meet the part again (the cut leaves a gap of the snap distance)
REPLACED_DEFAULTS = apply_overrides(globals(), "wop.core.constants")
