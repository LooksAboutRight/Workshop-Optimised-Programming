"""The raw part (bar stock or tube) clamped in the chuck (requirement R-group).

z = front_z_mm is the end face of the raw part. The part extends towards
negative z into the chuck. length_outside_mm is the stick-out (how far it sticks out of the
jaws, measured from the end face), so the clamping plane is at front_z_mm - length_outside_mm.
length_mm is the whole length of the part; None is bar stock of unlimited length.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import DEFAULT_FRONT_Z_MM
from ..contour import Contour


class RawPartError(ValueError):
    """The raw part data is not usable."""


@dataclass(frozen=True)
class RawPart:
    material: str
    outer_diameter_mm: float
    length_outside_mm: float  # required: the stick-out, how far it sticks out of the jaws
    inner_diameter_mm: float = 0  # 0 = solid bar
    length_mm: float | None = None  # the whole length; None = unlimited (long bar through the spindle)
    front_z_mm: float = DEFAULT_FRONT_Z_MM
    outline: Contour | None = None  # a drawn raw part (`raw_outline.py`): the numbers above are worked out from it, the stock is its shape

    def __post_init__(self) -> None:
        if self.outer_diameter_mm <= 0:
            raise RawPartError("outer diameter must be greater than zero")
        if self.length_outside_mm <= 0:
            raise RawPartError("length outside the chuck must be greater than zero")
        if self.inner_diameter_mm < 0:
            raise RawPartError("inner diameter must not be negative")
        if self.inner_diameter_mm >= self.outer_diameter_mm:
            raise RawPartError("inner diameter must be smaller than the outer diameter")
        if self.length_mm is not None and self.length_mm <= 0:
            raise RawPartError("the length of the part must be greater than zero")

    @property
    def length_inside_mm(self) -> float | None:
        """How much of the part is behind the clamping plane (None: bar stock). Zero if the stick-out is more than the part."""
        return None if self.length_mm is None else max(self.length_mm - self.length_outside_mm, 0)

    @property
    def outer_radius_mm(self) -> float:
        return self.outer_diameter_mm / 2

    @property
    def inner_radius_mm(self) -> float:
        return self.inner_diameter_mm / 2

    @property
    def clamp_z_mm(self) -> float:
        """Axial position of the clamping plane (where the jaws begin)."""
        return self.front_z_mm - self.length_outside_mm
