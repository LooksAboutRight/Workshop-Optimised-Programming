"""What the pictures show of a block that cut into the part (the user's idea, 2026-10-30).

The plan keeps the part as drawn: a block never removes more than it says, and the next block is planned on that. The check
(`verify_plan`) finds where a tool really cuts into the finished part or runs its holder into the material. `with_damage` gives the
pictures (2D, 3D, the stepper) the material with that cut away, from the block that did it to the end of the program. Planning, the files
and the export do not see it.
"""

from __future__ import annotations

from dataclasses import replace

from ..core.geometry.region import Region
from ..core.program_model.program import Program, ProgramPlan
from ..core.verify import Finding, FindingKind
from .stepper import Stepper

CUTS_INTO_THE_PART = (FindingKind.GOUGE, FindingKind.HOLDER_IN_MATERIAL)


def _damage(lost: Region) -> Region:
    """What was cut away, as whole pieces: a piece that is gone when it is shrunk by the collision tolerance is a thin tooth of the sweep, not
    damage. (The pieces are not shrunk themselves: a shrunk piece lets go of the surface it was cut from and becomes a hole in the part.)"""
    found = Region.empty()
    for piece in lost.pieces():
        if not piece.shrunk_for_collision().is_empty:
            found = found.union(piece)
    return found


def with_damage(program: Program, plan: ProgramPlan, findings: list[Finding]) -> ProgramPlan:
    """The plan with the material the pictures show: what the blocks with such findings cut away that the plan keeps is missing from
    the block on. The plan itself when there is no such finding."""
    bad = {finding.block_index for finding in findings if finding.kind in CUTS_INTO_THE_PART}
    if not bad:
        return plan
    stepper = Stepper(program, plan)
    carried = Region.empty()  # cut away by the blocks so far
    blocks = []
    for index, block_plan in enumerate(plan.blocks):
        before = block_plan.residual_before.difference(carried) if not carried.is_empty else None
        if index in bad:
            actual = stepper.swept(index, block_plan.residual_before if before is None else before)
            carried = carried.union(_damage(block_plan.residual_after.difference(actual)))
        after = block_plan.residual_after.difference(carried) if not carried.is_empty else None
        blocks.append(replace(block_plan, shown_before=before, shown_after=after))
    return replace(plan, blocks=tuple(blocks))
