"""Constants of the 3D view (requirement Z1)."""

VIEW_WIDTH_PX = 900
VIEW_HEIGHT_PX = 600
VIEW_MARGIN_PX = 30

DEFAULT_AZIMUTH_DEG = -30.0
DEFAULT_ELEVATION_DEG = -30.0
MIN_ELEVATION_DEG = -89.0
MAX_ELEVATION_DEG = 89.0
MIN_ZOOM = 0.2
MAX_ZOOM = 20.0

# The part is drawn as a revolve with a quarter cut away, so the inside shows.
SWEEP_DEG = 270.0
# The removed quarter is the one between 0 and 90 degrees (flipped in W15). The tool path is drawn on the cut face
# at 90 degrees, and the default camera looks at that face, so the path side faces the user (requirement V5).
SWEEP_START_DEG = 180.0
# The tool path and the tool are drawn on the other cut face, the one at the end of the sweep.
PATH_PLANE_DEG = SWEEP_START_DEG + SWEEP_DEG
STEPS_PER_TURN = 48  # the normals are smooth round the axis, so fewer steps than with flat faces look the same
AXIS_EPSILON_MM = 1e-6  # a ring piece on the spindle axis has no surface

SURFACE_RGB = (176, 182, 192)
CHUCK_RGB = (120, 132, 150)  # the chuck body: opaque, like the part
JAWS_RGB = (96, 112, 138)
JAWS_SPINDLE_OPACITY = 0.4  # the jaws as a full revolve while the spindle runs (the part and the chuck stay opaque)
CUT_FACE_RGB = (222, 196, 140)
AMBIENT_LIGHT = 0.35
LIGHT_DIRECTION = (-0.4, -0.5, 0.75)  # towards the light, in screen space (right, up, towards viewer)
CUT_FACE_EDGE = "#7a6a45"  # the edge of the cross-section of the part
CHUCK_EDGE = "#44505f"  # and of the chuck body
CUT_FACE_EDGE_WIDTH_PX = 0.6
FINISHED_OUTLINE_DASH_PX = (9.0, 4.0)
DEPTH_RANGE_FACTOR = 1.5  # the depth buffer covers this many radii of the scene on each side of its centre

PATH_CUT_COLOR = "#1f5fbf"
PATH_RAPID_COLOR = "#e07000"
PATH_RAPID_DASH = (5.0, 4.0)  # pixels on, pixels off
PATH_WIDTH_PX = 1.6
AXIS_COLOR = "#999999"
AXIS_DASH_ON_FACTOR = 0.03  # of the radius of the scene: the dashes of the axis line are model lengths (it has the depth test)
AXIS_DASH_OFF_FACTOR = 0.015
AXIS_OVERSHOOT_MM = 6.0
