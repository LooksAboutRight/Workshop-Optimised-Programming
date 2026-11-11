"""Constants of the LinuxCNC adapters (file formats and ini names)."""

# --- tool.tbl ---------------------------------------------------------------
TOOL_TABLE_DECIMALS = 6
TOOL_TABLE_COMMENT_MARK = ";"
BACKUP_SUFFIX = ".wop-backup-"
BACKUP_TIME_FORMAT = "%Y%m%d-%H%M%S-%f"

# --- ini file ---------------------------------------------------------------
INI_SECTION_TRAJ = "TRAJ"
INI_SECTION_RS274NGC = "RS274NGC"
INI_SECTION_SPINDLE = "SPINDLE_0"
INI_AXIS_SECTION_PREFIX = "AXIS_"
INI_KEY_COORDINATES = "coordinates"
INI_KEY_LINEAR_UNITS = "linear_units"
INI_KEY_MIN_LIMIT = "min_limit"
INI_KEY_MAX_LIMIT = "max_limit"
INI_KEY_MAX_VELOCITY = "max_velocity"  # of an axis, in units per second
INI_SECONDS_PER_MINUTE = 60
INI_KEY_STARTUP_CODE = "rs274ngc_startup_code"
INI_KEY_MIN_RPM = "min_forward_velocity"
INI_KEY_MAX_RPM = "max_forward_velocity"
INI_METRIC_NAMES = ("mm", "metric", "millimeter", "millimeters")
INI_IMPERIAL_NAMES = ("in", "inch", "inches", "imperial")
INI_DIAMETER_CODE = "G7"
INI_RADIUS_CODE = "G8"
INI_DEFAULT_COORDINATES = "X Z"
