"""Defaults of the application layer (a new project, a new contour).

Above NOT_EDITABLE_BELOW: the values the user may change in File > Preferences (each needs an entry in core/conventions.py).
"""

DEFAULT_NEW_PART_DIAMETER_MM = 30
DEFAULT_NEW_PART_LENGTH_MM = 60
DEFAULT_NEW_PART_MATERIAL = "Mild steel"  # a name from the built-in material table
SAFE_RADIUS_BEYOND_PART_MM = 10  # the safe radius (and the tool change position) follows the part: its outer radius plus this
SAFE_Z_IN_FRONT_MM = 10  # the safe Z follows the front face: front Z plus this
DEFAULT_CLEARANCE_MM = 1
DEFAULT_NEW_BLOCK_RPM = 1000
UNDO_LIMIT = 200  # states kept for Undo
DISPLAY_UNITS = "mm"  # the unit of lengths in the window: "mm" or "inch" (the program, the files and the G-code unit do not change)
TAPER_INPUT = "degrees"  # how a taper is shown first: "degrees" (the included angle) or "rise per 100 mm" (of the diameter)

NOT_EDITABLE_BELOW = True  # marker: the constants below this line are fixed (shown read only in Preferences)
DEFAULT_STOCK_INSIDE_MM = 30  # the length inside the chuck that is offered when the stock ends in the jaws
# Length of the shaft in the first contour that a new contour block gets.
DEFAULT_CONTOUR_LENGTH_MM = 20
PLAN_CACHE_SIZE = 8  # plans kept for the same program (the whole program and a few selections)
WORKING_PLANNING = "planning"  # `Analysis.working`: the plan of a newer program is being made in the background
WORKING_CHECKING = "checking"  # `Analysis.working`: the plan is there, its check is being made in the background

from ..core.files.convention_overrides import apply_overrides  # noqa: E402  (last: it replaces the values above with the user's)

REPLACED_DEFAULTS = apply_overrides(globals(), __name__)
