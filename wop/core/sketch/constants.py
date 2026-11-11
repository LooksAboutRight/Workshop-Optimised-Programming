"""Fixed numbers of the sketch solver (numerical details; none of them is a setting for the user)."""

ORIGIN = 0  # the id that stands for the point (0, 0) of the sketch in a relation; it never moves

SOLVE_TOLERANCE = 1e-8  # largest residual (mm, or a unitless angle/ratio) of a solved sketch
DIFFERENCE_STEP = 1e-6  # step of the central difference for the Jacobian
LENGTH_FLOOR = 1e-12  # lengths below this are not divided by
MAX_ITERATIONS = 100
DAMPING_START = 1e-3
DAMPING_MIN = 1e-12
DAMPING_MAX = 1e12
DAMPING_STEP = 10
STEP_STOP = 1e-13  # a step smaller than this ends the iteration
RANK_TOLERANCE = 1e-6  # singular values below this are zero when counting the degrees of freedom
FIXED_TOLERANCE = 1e-6  # a point whose null-space movement is below this is fully defined
DRAG_WEIGHT = 0.05  # how hard a drag pulls compared to the relations (the relations are exact afterwards)
DRAG_STAY_WEIGHT = 0.001  # while dragging, every other point is held where it is this softly: the directions the sketch can still move in are
# badly conditioned, and without this the solver drifts along them (a free line shrinks to nothing) and the drag is refused

AXIS_LINE = -1  # the id of the spindle axis (x = 0, along z) as a line of a relation: the centre line that is always there in a turning contour

SLOT_POINT = "point"
SLOT_LINE = "line"
SLOT_ARC = "arc"

ANGLE_EPSILON = 1e-9  # sin of an angle below this: the lines run along each other
POINT_TOLERANCE = 1e-6  # two points closer than this (mm) are the same point
SAME_DECIMALS = 6  # decimals when two outlines are compared piece by piece
MIRROR_KINDS = ("symmetric", "symmetric_axis_z", "symmetric_axis_x")  # the relations that make a mirror point
PARALLEL_SINE = 0.035  # two lines whose directions differ by less than this (sine, about 2 degrees) count as parallel
