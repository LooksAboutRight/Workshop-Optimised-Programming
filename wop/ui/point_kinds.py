"""The kinds of named point the contour editor offers, depending on who opened it.

A tool shape offers the touch-off point and the corners of a tool, the outline of a chuck or of jaws the points
the placement uses. A free name is always possible.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.constants import (
    CHUCK_FACE_POINT,
    CLAMP_PLANE_POINT,
    JAWS_MOUNT_POINT,
    TIP_POINT,
)
from ..core.lathe.workholding import CHUCK_KIND, JAWS_KIND

STEP_POINT = "step"  # a step of stepped jaws where a part is gripped: step 1, step 2 ...


@dataclass(frozen=True)
class PointKind:
    label: str
    name: str  # the name the point gets (a point of this name is not added twice)
    help: str = ""
    automatic: bool = False  # the position can be worked out from the shape
    icon: str = ""  # the pictogram of its button in the sketch editor
    numbered: bool = False  # a shape can have several: the points are called "step 1", "step 2" ...


TOOL_POINT_KINDS = (
    PointKind(
        "Tip (touch-off point)", TIP_POINT,
        "Where the tool is touched off: X on a turned diameter, Z on a faced end. The program describes the path of this "
        "point. Without it WOP uses the corner of the box round the cutting edges.", automatic=True,
    ),
)

RAW_PART_POINT_KINDS = (
    PointKind(
        "Clamping plane (where the jaws begin)", CLAMP_PLANE_POINT,
        "Where the jaws begin: only its Z counts. The stick-out is measured from the front of the piece to this plane.", icon="name_face",
    ),
)

WORKHOLDING_POINT_KINDS = {
    JAWS_KIND: (
        PointKind("Mount (on the chuck)", JAWS_MOUNT_POINT, "Where the jaws meet the face of the chuck: only Z counts.", icon="name_mount"),
        PointKind("Step (where a part is gripped)", STEP_POINT, "A step of stepped jaws where a part can sit; one point per step.", icon="name_step", numbered=True),
    ),
    CHUCK_KIND: (
        PointKind("Face (front of the chuck)", CHUCK_FACE_POINT, "The front face of the chuck body: only Z counts.", icon="name_face"),
    ),
}
