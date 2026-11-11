"""The side and the direction of a turning block, and the merging of rapids."""

from __future__ import annotations

from enum import Enum

from ..constants import GEOMETRY_TOLERANCE_MM
from ..program_model.operations import Rapid


class TurningSide(Enum):
    OUTSIDE = "outside"
    INSIDE = "inside"


class PassDirection(Enum):
    ALONG_Z = "along Z"  # horizontal passes
    ALONG_X = "along X"  # vertical (transverse) passes


def merge_straight_rapids(operations: list) -> list:
    """Rapids that continue in a straight line become one move; a rapid to where the tool already is is dropped."""
    merged: list = []
    for operation in operations:
        if isinstance(operation, Rapid) and merged and isinstance(merged[-1], Rapid):
            here = merged[-1].end
            if operation.end.is_close(here):
                continue
            before = merged[-2].end if len(merged) > 1 and hasattr(merged[-2], "end") else None
            if before is not None:
                along = (here.x - before.x) * (operation.end.x - here.x) + (here.z - before.z) * (operation.end.z - here.z)
                across = (here.x - before.x) * (operation.end.z - here.z) - (here.z - before.z) * (operation.end.x - here.x)
                if along > 0 and abs(across) <= GEOMETRY_TOLERANCE_MM * here.distance_to(operation.end):
                    merged[-1] = operation
                    continue
        merged.append(operation)
    return merged
