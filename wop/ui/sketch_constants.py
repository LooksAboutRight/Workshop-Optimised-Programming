"""Fixed values of the sketch editor session (the toolkit-free part)."""

from ..core.sketch.constants import AXIS_LINE

TOOL_SELECT = "select"
TOOL_LINE = "line"
TOOL_CIRCLE = "circle"
TOOL_TRIM = "trim"
TOOL_POINT = "point"
TOOL_DIMENSION = "dimension"
TOOL_MIRROR = "mirror"
TOOL_ARC_CENTRE = "arc_centre"
TOOL_ARC_THREE = "arc_three"
TOOL_ACTION = "action"  # a relation or a change picked first (the button stays on), then the things it acts on are clicked
TOOL_NAMES = (
    (TOOL_SELECT, "Select"),
    (TOOL_LINE, "Line"),
    (TOOL_CIRCLE, "Circle"),
    (TOOL_ARC_CENTRE, "Arc (centre, start, end)"),
    (TOOL_ARC_THREE, "Arc (start, end, point on arc)"),
    (TOOL_TRIM, "Trim"),
    (TOOL_POINT, "Point"),
    (TOOL_DIMENSION, "Dimension"),
    (TOOL_MIRROR, "Mirror the selection about a line"),
)

UNDO_LIMIT = 100
DRAG_BACKOFF = (1.0, 0.5, 0.25, 0.1)  # a drag that the relations cannot follow all the way is tried again with this part of the pull
DRAW_TOOLS = (TOOL_LINE, TOOL_CIRCLE, TOOL_ARC_CENTRE, TOOL_ARC_THREE, TOOL_POINT)  # the tools that make a new piece or point
LOCKED_MESSAGE = "That is locked: it comes from the program. You can dimension to it, but not move, change or delete it"
AXIS_ID = AXIS_LINE  # the id of the spindle axis, the centre line that is always there in a turning contour
PENDING_MIRROR = -2  # in a dimension that is not placed yet: the mirror point that is made when it is
SWIPE_TRIM_LIMIT = 50  # most trims for one step of the mouse while swiping (a safety net)
DIMENSION_NEAR_FACTOR = 5  # "close to the line" for a dimension: this many snap distances
DEFAULT_DIMENSION_OFFSET = (3.0, 3.0)  # mm from what is measured, for a dimension that was not placed by hand
ORTHO_SNAP_ANGLE_DEG = 1.5  # a line drawn this close to horizontal or vertical is made exact
SNAP_RADIUS_PX = 6  # how near the mouse must be to a point or piece, on the screen

PROMPTS = (
    (TOOL_SELECT, "Click a point or piece (Ctrl adds or takes away). Drag it to move it, or drag on empty space to select with a box. Delete removes the selection."),
    (TOOL_LINE, "Click the start, then the end. The next line continues from the end. Right click ends the line, Esc ends it and goes back to selecting."),
    (TOOL_CIRCLE, "Click the centre, then a point on the circle."),
    (TOOL_ARC_CENTRE, "Click the centre, then the start, then the end of the arc (the end sets the direction)."),
    (TOOL_ARC_THREE, "Click the start, then the end, then a point the arc goes through."),
    (TOOL_TRIM, "Click the part of a line or arc to cut away (up to the next crossing or the end). Hold the button and drag to trim everything the mouse crosses."),
    (TOOL_POINT, "Click to put a point (for example for a name from the Names menu). Click a point to select it."),
    (TOOL_DIMENSION, "Click a line, an arc or circle, or two points (the origin too), then click where the dimension goes: near the line its length, to the side along X, above or below along Z. Two lines: the angle. Double click a number to change it."),
    (TOOL_MIRROR, "Click the line to mirror the selected pieces about: any line, a construction or centre line too, or the spindle axis of a turning contour. Esc stops."),
)

STOP_HINT = " Click the button again or press Esc to stop."
ACTION_PROMPTS = (
    ("horizontal", "Click a line, or two points (the origin is one too), to make them level." + STOP_HINT),
    ("vertical", "Click a line, or two points (the origin is one too), to put them one above the other." + STOP_HINT),
    ("parallel", "Click two lines." + STOP_HINT),
    ("perpendicular", "Click two lines." + STOP_HINT),
    ("equal", "Click two lines, or two arcs / circles." + STOP_HINT),
    ("tangent", "Click a line and an arc, or two arcs, that meet at a point." + STOP_HINT),
    ("fixed", "Click a point or a piece to fix it in place." + STOP_HINT),
    ("point_on", "Click a point and a line or arc (in any order)." + STOP_HINT),
    ("midpoint", "Click a point and a line (in any order)." + STOP_HINT),
    ("join", "Click two points to make them one." + STOP_HINT),
    ("construction", "Click a piece to turn it into a helper line, or back." + STOP_HINT),
    ("centre", "Click a line to make it a centre line, or a normal line again." + STOP_HINT),
    ("cutting", "Click a piece to mark it as a cutting edge, or to take the mark off." + STOP_HINT),
    ("rapid", "Click a line to make it a rapid move, or a feed move again." + STOP_HINT),
    ("fillet", "Click a corner point to round it." + STOP_HINT),
    ("chamfer", "Click a corner point to chamfer it." + STOP_HINT),
)
# Tools where one click does the whole job (the others collect picks first, then act).
SINGLE_CLICK_ACTIONS = ("fixed", "construction", "centre", "cutting", "rapid", "fillet", "chamfer")
CORNER_ACTIONS = ("fillet", "chamfer")
NAME_PREFIX = "name:"  # the action of a named-point button is NAME_PREFIX + the name of its kind of point

# Relations and dimensions in the menus: (name used by the session, text in the menu).
RELATION_ITEMS = (
    ("horizontal", "Horizontal"),
    ("vertical", "Vertical"),
    ("parallel", "Parallel"),
    ("perpendicular", "Perpendicular"),
    ("equal", "Equal (length or radius)"),
    ("tangent", "Tangent"),
    ("fixed", "Fix in place"),
    ("point_on", "Point on line / arc"),
    ("midpoint", "Midpoint"),
    ("join", "Join points (coincident)"),
)
# The short tag drawn next to a relation in the picture (dimensions show their value instead).
RELATION_TAGS = (
    ("horizontal", "H"),
    ("vertical", "V"),
    ("fixed", "F"),
    ("parallel", "||"),
    ("perpendicular", "T"),
    ("equal_length", "="),
    ("equal_radius", "="),
    ("tangent_line_arc", "tan"),
    ("tangent_arcs", "tan"),
    ("point_on_line", "on"),
    ("point_on_circle", "on"),
    ("midpoint", "mid"),
)

MODIFY_ITEMS = (
    ("construction", "Construction on / off (helper line)"),
    ("centre", "Centre line on / off (dimensions to it are diameters)"),
    ("cutting", "Cutting edge on / off"),
    ("rapid", "Rapid move on / off (a line is a feed move unless it is a rapid move)"),
    ("fillet", "Fillet corner..."),
    ("chamfer", "Chamfer corner..."),
)

# The sections of the button strip: (heading, the names of its buttons in order). A name that does not exist in a window
# (the cutting edge outside tool shapes, names outside shapes with named points) is left out there.
# Draw makes basic geometry; Edit changes geometry that is there already; Constraints starts with the dimension; Mark says
# what a line or a point is without changing the geometry; General is what belongs to the whole sketch.
SECTIONS = (
    ("Draw", ("line", "circle", "arc_centre", "arc_three", "point")),
    ("Edit", ("trim", "mirror", "fillet", "chamfer")),
    ("Constraints", ("dimension", "horizontal", "vertical", "parallel", "perpendicular", "equal", "tangent", "fixed", "point_on", "midpoint", "join")),
    ("Mark", ("construction", "centre", "cutting", "rapid", "names")),  # "names" stands for the buttons of the kinds of point
    ("General", ("import", "undo", "redo", "snap", "show_relations", "show_dimensions")),
)
