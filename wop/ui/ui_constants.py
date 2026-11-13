"""Constants of the user interface layer (colours, sizes)."""

DISPLAY_UNIT_INCH = "inch"  # the value of the preference DISPLAY_UNITS that shows inches
INCH_UNITS = {"mm": "in", "mm/rev": "in/rev", "mm/min": "in/min", "m/min": "ft/min"}  # the units of a form field that are shown in inches, and how
INCHES_PER_FOOT = 12  # a cutting speed of m/min is shown in feet per minute
RPM_UNIT = "RPM"  # the unit of a spindle speed that is not a surface speed
SURFACE_SPEED_UNIT = "m/min"  # the unit of a constant surface speed in a form

PICTURE_WIDTH_PX = 1000
PICTURE_MARGIN_PX = 40
MIN_PICTURE_HEIGHT_PX = 200

STOCK_FILL = "#e8e8e8"
STOCK_STROKE = "#999999"
RESIDUAL_FILL = "#d9c9a3"
RESIDUAL_STROKE = "#7a6a45"
FAR_SIDE_FILL = "#e3e3e3"  # the far side of the round part (mirror of the material), faint, under the tools
FAR_SIDE_STROKE = "#c8c8c8"
FINISHED_OUTLINE_COLOR = "#d81b60"  # the finished shape of the block chosen in the flow list
FINISHED_OUTLINE_WIDTH_PX = 2.5
FINISHED_OUTLINE_DASH = "9 4"
AXIS_COLOR = "#bbbbbb"
RAPID_COLOR = "#e07000"
RAPID_DASH = "6 4"
# Cutting moves get one colour per block, repeating.
BLOCK_COLORS = ("#1f5fbf", "#1f9f4f", "#9f1fbf", "#bf1f5f", "#4f4f4f", "#0f9f9f")

LINE_WIDTH_PX = 1.5
OUTLINE_WIDTH_PX = 1
LABEL_FONT_PX = 13
LABEL_OFFSET_PX = 6
LEGEND_LINE_HEIGHT_PX = 18
KEY_TEXT_COLOR = "#555555"
FINDING_COLOR = "#d00000"
FINDING_MARK_PX = 6
# The tool shown while stepping through the program (requirement V2).
TOOL_CUTTER_COLOR = "#1a8f3c"
TOOL_HOLDER_COLOR = "#666666"
TOOL_FILL_OPACITY = 0.55
TOOL_OUTLINE_WIDTH_PX = 1.2
FINDING_WIDTH_PX = 2

# The legend of the picture: explanation lines, and how many block rows the window shows at most.
LEGEND_KEY_LINES = (
    "dashed = rapid moves, solid = cutting moves (colour per block)",
    "brown = material left, grey = raw part; Z to the right, chuck on the left",
    "pink dashed = the finished shape of the block chosen in the list",
)
LEGEND_MAX_ROWS = 12
MAX_PRECOMPUTED_STEPS = 3000  # most steps whose material is worked out in the background when stepping through starts

# Colours of the light set (the values above) and of the dark set. The window picks one
# from its OS theme (requirement V4); text colour comes from the window itself.
LIGHT_BACKGROUND = "#ffffff"
LIGHT_TEXT = "#222222"
DARK_BACKGROUND = "#1e1e1e"
DARK_TEXT = "#e0e0e0"
DARK_STOCK_FILL = "#3a3a3a"
DARK_STOCK_STROKE = "#8a8a8a"
DARK_RESIDUAL_FILL = "#a8946a"
DARK_RESIDUAL_STROKE = "#e0cf9f"
DARK_FAR_SIDE_FILL = "#2c2c2c"
DARK_FAR_SIDE_STROKE = "#444444"
DARK_FINISHED_OUTLINE_COLOR = "#ff80ab"
DARK_AXIS_COLOR = "#777777"
DARK_AXIS_3D_COLOR = "#8a8a8a"
DARK_RAPID_COLOR = "#ff9a3c"
DARK_KEY_TEXT_COLOR = "#b0b0b0"
DARK_FINDING_COLOR = "#ff5a5a"
DARK_BLOCK_COLORS = ("#5a9bff", "#4fd17f", "#d08bff", "#ff6fa0", "#bdbdbd", "#3fd6d6")
DARK_CUT_3D_COLOR = "#6aa8ff"
DARK_RAPID_3D_COLOR = "#ff9a3c"
DARK_TOOL_CUTTER_COLOR = "#5fd17f"
DARK_TOOL_HOLDER_COLOR = "#b0b0b0"
DARK_THEME_LUMINANCE_LIMIT = 0.5  # a window colour darker than this selects the dark set
HEX_COLOR_LENGTH = 7  # "#rrggbb"

# Untouched fields (requirement U6): their text is this share of the way from the text colour to the field colour.
UNTOUCHED_TEXT_FADE = 0.55
RESET_TO_DEFAULT_TEXT = "Reset to default"

# Workholding in the 2D picture (WH2): chuck body and jaws are drawn in the holder colour, jaws stronger.
WORKHOLDING_JAWS_OPACITY = 0.45
WORKHOLDING_CHUCK_OPACITY = 0.2
WORKHOLDING_LINE_WIDTH_PX = 1.5

# --- zoom and pan of the 2D picture ---
ZOOM_MIN = 1.0  # the whole picture fits the window
ZOOM_MAX = 40.0
LINE_SCALE_TOLERANCE = 0.01  # the picture is drawn again when the line scale it was drawn for is off by more than this share
ZOOM_PER_WHEEL_NOTCH = 1.2
WHEEL_NOTCH_UNITS = 120  # what Qt reports for one notch of the wheel
PAN_KEEP_VISIBLE_FRACTION = 0.1  # at least this part of the picture stays inside the window

# --- the post editor: the groups of the token grid, in this order (a token goes to the first group whose test is true) ---
POST_EDITOR_TOKEN_GROUPS = (
    ("Variables", lambda name: False),  # the variables of a custom concept: first in the token grid
    ("Position", lambda name: name in ("X", "Z", "X start", "Z start", "I", "K", "R")),
    ("Feed and speed", lambda name: name in ("F", "S", "S max", "dwell")),
    ("Codes and numbers", lambda name: name in ("code", "x mode code", "x values", "N", "N next")),
    ("Project and time", lambda name: name in (
        "project title", "machine name", "post name", "WOP version", "material", "part diameter", "part length",
        "program number", "date", "time", "date iso", "tool count", "estimated time", "path length",
    )),
    ("Tools", lambda name: name.startswith(("tool ", "previous tool", "next tool", "first tool", "last tool"))),
    ("Blocks", lambda name: name.startswith(("block ", "next block", "previous block"))),
    ("Thread", lambda name: name in (
        "pitch", "thread depth", "first cut", "peak offset", "degression", "compound angle", "spring passes",
        "taper distance", "taper code",
    ) or name.startswith("thread ")),
    ("Drilling", lambda name: name.startswith("drill ")),
    ("Text and lines", lambda name: name in (
        "list tools", "list notes", "comment text", "note",
    )),
)

# The pictures of the block styles are shown at about a third of the size of the picture of the window: thicker lines.
STYLE_PICTURE_LINE_FACTOR = 4
STYLE_PATH_FIRST_COLOR = "#2f80ff"  # the cutting moves of a style picture go from this colour (the first move) ...
STYLE_PATH_LAST_COLOR = "#ff5a1f"  # ... to this one (the last)
