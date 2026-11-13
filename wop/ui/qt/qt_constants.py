"""Sizes, timings and fixed texts of the window."""

WINDOW_WIDTH_PX = 1400
WINDOW_HEIGHT_PX = 800
FLOW_PANEL_WIDTH_PX = 240  # the width the side panels open with
FORM_PANEL_WIDTH_PX = 360
FLOW_PANEL_MIN_WIDTH_PX = 210  # the smallest an open side panel can be made: with both open the window still fits a screen 1024 wide
FORM_PANEL_MIN_WIDTH_PX = 330
RIGHT_PANEL = 2  # index of the right panel in the splitter (left 0, middle 1)
PANEL_HANDLE_WIDTH_PX = 16  # the splitter handles stay visible when a side panel is collapsed
HANDLE_DOT_PX = 3
HANDLE_BACKGROUND_ALPHA = 70  # 0..255
HANDLE_DOT_GAP_PX = 7
HANDLE_ARROW_PX = 5  # half size of the arrow that shows a collapsed panel
HANDLE_CLICK_SLOP_PX = 4  # a press that moves less than this is a click (open / close), not a drag
SPLITTER_PICTURE_STRETCH = 1
MESSAGE_PANEL_HEIGHT_PX = 150  # the height the message box opens with (the user can drag the border between the picture and the box)
MESSAGE_PANEL_MIN_HEIGHT_PX = 40
MESSAGE_HANDLE_HEIGHT_PX = 10
SPIN_DECIMALS = 4
SPIN_LIMIT = 1_000_000
SPIN_STEP = 0.1
SPIN_DECIMALS_INCH = 6  # an inch is 25.4 mm: a value of 0.1 mm must survive the round trip
SPIN_STEP_INCH = 0.01
TEXT_EDIT_DELAY_MS = 700  # a multi-line text is taken over this long after the last key
STATUS_MESSAGE_MS = 6000
THREAD_SWITCH_INTERVAL_S = 0.0005  # GUESS: how long Python lets the background work run before the window gets its turn (default 0.005: a repaint of the window took seconds while the plan ran)
WORK_TEXTS = {"planning": "Planning ...", "checking": "Checking collisions and power ..."}  # `Analysis.working` in the status bar
WORK_NOTES = {  # `Analysis.working` at the top of the messages box
    "planning": "WORKING: planning the changed program; the picture and the notes are those of the program before the last change.",
    "checking": "WORKING: checking collisions and power; the findings follow.",
}
WORK_NOTE_SAVED_PART = "WORKING: planning the program; the picture shows the finished part as it was saved, the moves follow."
ERROR_LOG_CHECK_MS = 1500  # how often the window looks for new entries in the error log
WARNING_MARK = "⚠"
APP_NAME = "WOP"
DIALOG_WIDTH_PX = 1000
DIALOG_HEIGHT_PX = 650
DIALOG_NOTES_HEIGHT_PX = 140
ZOOM_REDRAW_DELAY_MS = 100  # the 2D picture is drawn again with thinner lines this long after the last wheel step
OVERLAY_MARGIN_PX = 8  # distance of the legend, its checkbox and the hint from the edge of the picture
LEGEND_BACKGROUND_ALPHA = 200  # 0..255, so the drawing below can still be seen
LEGEND_MARKER = "&#9632;"  # a square in the colour of the block
VIEW3D_HINT = "Drag to move, wheel to zoom, double click to reset"
MACHINE_DIALOG_WIDTH_PX = 900
MACHINE_DIALOG_HEIGHT_PX = 640
MACHINE_LIST_WIDTH_PX = 240
DEFAULT_MACHINE_MARK = " (default)"
IN_PROJECT_MARK = " (in project)"
MATERIAL_DIALOG_WIDTH_PX = 620
MATERIAL_DIALOG_HEIGHT_PX = 380
TOOLBOX_DIALOG_WIDTH_PX = 760
TOOLBOX_DIALOG_HEIGHT_PX = 440
PREFERENCES_DIALOG_WIDTH_PX = 980
PREFERENCES_DIALOG_HEIGHT_PX = 700
PREFERENCES_FIELD_WIDTH_PX = 130
PREFERENCES_MEANING_MIN_WIDTH_PX = 420
PREFERENCES_FIXED_WIDTH_PX = 900
PREFERENCES_FIXED_HEIGHT_PX = 640
PREFERENCES_ERROR_STYLE = "QLineEdit { border: 2px solid #c0392b; }"
PREFERENCES_RESTART_TEXT = "Changes are saved, but they apply after you restart WOP. WOP does not restart by itself, so save your project first."
PREFERENCES_NAME_STYLE = "color: gray; font-size: 9pt;"
FLOW_CARD_GAP_PX = 3  # space around a card in the flow list
FLOW_CARD_MIN_HEIGHT_PX = 44
FLOW_CARD_PAD_PX = 8
FLOW_CARD_RADIUS_PX = 8
FLOW_STRIP_PX = 6  # the strip in the colour of the block
FLOW_CHECK_HIT_PX = 36  # width of the area that ticks a block (touch)
FLOW_CHECK_BOX_PX = 20
FLOW_LINE_GAP_PX = 2
FLOW_NOTE_SIZE_FACTOR = 0.85
FLOW_DIM_ALPHA = 150  # 0..255, the note line is dimmer
FLOW_SELECTED_FILL_ALPHA = 45
FLOW_SELECTED_BORDER_PX = 2
FLOW_WARNING_COLOR = "#d98300"
FLOW_COLLISION_NOTE = "Collision, see messages"
SPIN_MIN_WIDTH_PX = 90
TOOL_SHAPE_HINT = (
    "Orange: cutting edges (may touch the material). Everything else must never touch it. "
    "Named points show with their name. The shape must be closed. The tip (touch-off point) is the origin."
)

WORKHOLDING_SHAPE_HINT = (
    "Draw the item in machine orientation: X is the radius, Z runs along the axis, the front face is at Z = 0 and the "
    "body towards minus Z. The shape must be closed. Named points: on jaws the steps that can sit on the part (Step) and "
    "'mount' where the chuck body meets them; on a chuck body 'face'."
)
WORKHOLDING_VIEW_INFO = (
    "Choose the jaws and the chuck body the program uses in the Setup. With none chosen there, nothing is shown and the "
    "flat clamping plane of the Setup is what the checks use."
)
DXF_SHAPE_HINT = (
    "The drawing is taken as it is: spindle axis horizontal, drawing X = Z (to the right), drawing Y = radius (up). "
    "Nothing is moved, turned or mirrored; the origin of the drawing stays the origin. One closed outline. "
    "A POINT with a TEXT next to it makes a named point."
)

# The right-click entry of a block that shows its neutral operations as text (a helper for development; False hides it).
SHOW_NEUTRAL_CODE_MENU = True
NEUTRAL_CODE_MENU_TEXT = "Show operations (neutral code)..."
NEUTRAL_CODE_SINGLE_MOVES_MENU_TEXT = "Show operations, drilling and threading as single moves..."
NEUTRAL_CODE_WIDTH_PX = 640
NEUTRAL_CODE_HEIGHT_PX = 520
EXPORT_CHECK_TITLE = "Export G-code"
EXPORT_CHECK_NOT_RUN = "No collision and power checks have been run for this program."
EXPORT_CHECK_NOT_RUN_LEFT_OUT = " Blocks that are left out are listed below."
EXPORT_CHECK_BUSY = "Checking..."
EXPORT_CHECK_FOUND = "The check found {count} problem(s). The G-code is written as drawn, so the tool would really do this:"
EXPORT_CHECK_RUN_NOW = "Run checks now"
EXPORT_CHECK_WITHOUT = "Export without checks"
EXPORT_CHECK_ANYWAY = "Export anyway"
EXPORT_CHECK_MIN_HEIGHT_PX = 220
SCREEN_MARGIN_X_PX = 16  # a window that is larger than the screen is made this much narrower than the free part of it (the frame)
SCREEN_MARGIN_Y_PX = 56  # ... and this much lower (the title bar and the frame)
POST_CHOOSER_MIN_CHARACTERS = 20  # the post list of the post editor shows at least this many letters (it can be wider)
POST_DIALOG_WIDTH_PX = 1250
POST_DIALOG_HEIGHT_PX = 820
POST_PAGE_LIST_WIDTH_PX = 210
POST_TEMPLATE_MIN_HEIGHT_PX = 170
POST_SAMPLE_MIN_HEIGHT_PX = 110
POST_TOKEN_COLUMNS = 4  # buttons in a row of the token grid
POST_PREVIEW_DELAY_MS = 250  # the sample output follows the typing this long after the last key
POST_ERROR_COLOR = "#d9534f"
POST_HINT_COLOR = "#b8860b"  # a hint that is no problem
POST_ERROR_LINE_COLOR = "#f8d7da"
POST_ERROR_LINE_TEXT_COLOR = "#212529"  # dark text on the light red background of a line with a problem (the text colour of a dark theme is unreadable on it)
POST_PROBLEMS_MARK = " (has problems)"
POST_UNREADABLE_MARK = " (unreadable file)"
POST_NEW_ID = ""  # the id of a post that has no file yet
POST_SHIPPED_MARK = " (comes with WOP)"
POST_NEW_MARK = "(new post)"
POST_OWN_NOTE = "This post has its own section."
POST_DEFAULT_NOTE = "No section of its own: the default post writes this. Tick the box to make it this post's own (it starts as a copy)."
POST_DISCLAIMER = (
    "Every post, the shipped ones too, can crash a machine. Check what a post writes before you run it on a machine. "
    "Shipped posts are read-only: use Save as copy to change one."
)
POST_PAGES = (("post", "Post"), ("settings", "Settings"), ("codes", "Code table"), ("modal_groups", "Modal groups"))
POST_CUSTOM_GROUPS_TEXT = "Custom modal groups"
POST_CUSTOM_CONCEPTS_TEXT = "Custom concepts"
POST_VARIABLES_HEIGHT_PX = 90
POST_VARIABLES_HINT = (
    "Variables (one per line): name = type min=0 max=500 default=10 unit=mm label=\"Feed distance\". The types are float, int, uint, bool and "
    "string; min, max, default, unit and label are optional. The template uses a variable as <name>, with the options of its type."
)
POST_UNGROUPED_NOTE = "In no modal group (each is its own group): {names}. Put the code into a group on the Modal groups page."
POST_NO_TOKEN_TEXT = "(put the cursor into a token)"
POST_MODIFIER_BUTTONS = (  # (key, text on the button, tooltip) of the row under the sample output
    ("changed", "changed", "Make the selected statement optional and changed: F<F> becomes [ F<F changed>]. Without a selection the statement under the cursor. Again: takes it away."),
    ("optional", "Optional [ ]", "Put [ ] around the selected statement: it is left out when everything in it is empty."),
    ("options", "Token options \u25be", "The options of the token under the cursor (scaled, decimals, plus, upper, safe ...)."),
    ("protect", "Protect text", "Put <text> </text> around the selection: it is written as it is, also < > [ ] and spaces. Again: takes it away."),
    ("comment", "Comment out", "Put # in front of the selected lines (a line that starts with # is not read). Again: takes it away."),
    ("unwrap", "Remove brackets", "Take the [ ] around the cursor or the selection away; the tokens stay as they are."),
)
POST_TOKEN_LIST_WIDTH_PX = 1100
POST_TOKEN_LIST_HEIGHT_PX = 600

# The pictures that show the path of a style when its entry in the dropdown is hovered.
STYLE_PICTURE_WIDTH_PX = 330
STYLE_PICTURE_COLUMNS = 2
STYLE_PICTURE_GAP_PX = 8
STYLE_PICTURE_HINT = "Cutting moves only, blue = made first, red = made last"

NO_TOOLS_TEXT = "No tools yet - use Add tool or Add from library"
TOOL_OFFSET_MAX = 99999  # the largest tool offset number the Tools view accepts (the range of the tool numbers of LinuxCNC)
