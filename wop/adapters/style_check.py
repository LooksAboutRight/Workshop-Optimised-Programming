"""The check every style passes when it is loaded: it is tried on the samples of its block type and compared with the standard style."""

from __future__ import annotations

import math

from ..core.blocks.base import BlockError
from ..core.blocks.styles import DEFAULT_STYLE_KEY, contract_problems
from ..core.geometry import Point
from ..core.program_model.program import plan_program
from ..core.verify import verify_plan
from .style_samples import samples_for


def _last_end(operations) -> Point | None:
    for operation in reversed(operations):
        end = getattr(operation, "end", None)
        if isinstance(end, Point):
            return end
    return None


def _findings(program):
    return verify_plan(program, plan_program(program))


def check_style(block_type: str, key: str) -> list[str]:
    """What is wrong with the style (empty: it passes). The style must already be registered.

    On every sample: no error, only finite numbers, the same material removed as by the standard style, the same end position (the
    safe point). A mistake inside the style function is reported, not raised."""
    problems: list[str] = []
    for sample in samples_for(block_type):
        block, context = sample.build(DEFAULT_STYLE_KEY)
        standard = block.generate(context)
        block, context = sample.build(key)
        try:
            result = block.generate(context)
        except BlockError as error:
            problems.append(f"{sample.name}: {error}")
            continue
        except Exception as error:  # noqa: BLE001 - a style file is somebody else's code
            problems.append(f"{sample.name}: the style stopped with {type(error).__name__}: {error}")
            continue
        points = [getattr(op, "end", None) for op in result.operations]
        if any(isinstance(p, Point) and not (math.isfinite(p.x) and math.isfinite(p.z)) for p in points):
            problems.append(f"{sample.name}: the style made a position that is not a number")
            continue
        problems += [f"{sample.name}: {text}" for text in contract_problems(standard.removed, _last_end(standard.operations), result.removed, _last_end(result.operations))]
        if sample.verify:  # a style may not cause a collision that the standard style does not cause
            known = {finding.kind for finding in _findings(sample.program(DEFAULT_STYLE_KEY))}
            new = sorted({finding.kind.name for finding in _findings(sample.program(key))} - {kind.name for kind in known})
            if new:
                problems.append(f"{sample.name}: the style causes what the standard style does not: {', '.join(new)}")
    return problems
