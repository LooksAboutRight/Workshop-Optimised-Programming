"""The value functions of the code tokens: `<code name>` (with `changed` inside its modal group) and the cutter compensation codes."""

from __future__ import annotations

from ..core.program_model.operations import CompensationSide, MoveRole, SpindleDirection
from .base import PostError
from .modal_groups import normalize_code
from .numbers import Options


def _code(render, args, options: Options):
    text, group, modal = args
    same = normalize_code(text)  # G0 and G00 are the same code
    if options.has("changed") and modal:  # a code of a group that is not modal is always written
        forced = render.engine.preview
        if forced is False or (forced is None and render.state.groups.get(group) == same):
            return None
    if modal:
        render.state.groups[group] = same
    return text


def _prepare_code(args: tuple, codes: dict) -> tuple:
    name = args[0]
    if name not in codes:
        known = ", ".join(sorted(codes)) or "none"
        raise PostError(f"the code table has no {name!r}; it has: {known}")
    return (codes[name].text, codes[name].group or name, codes[name].modal)


def _prepare_compensation(_args: tuple, codes: dict) -> tuple:
    return tuple(codes[name].text if name in codes else None for name in ("comp_left", "comp_right", "comp_off"))


def _prepare_spindle_code(_args: tuple, codes: dict) -> tuple:
    return tuple((codes[name].text, codes[name].group or name, codes[name].modal) if name in codes else None for name in ("spindle_cw", "spindle_ccw"))


def _spindle_code(render, args, options: Options):
    """The code that starts the spindle the way the block asks: `spindle_cw` or `spindle_ccw` of the code table (`changed` as for `<code ..>`)."""
    reversed_ = render.scope.get("direction") is SpindleDirection.COUNTER_CLOCKWISE
    entry = args[1 if reversed_ else 0]
    if entry is None:
        raise PostError(f"the code table has no {'spindle_ccw' if reversed_ else 'spindle_cw'}, which this spindle needs")
    return _code(render, entry, options)


def _comp_code(render, args, _options: Options):
    """G41 / G42 on the lead-in, G40 on the lead-out, when the post does cutter compensation; else empty."""
    if not render.scope.get("compensating"):
        return None
    role = render.scope.get("role")
    if role is MoveRole.LEAD_IN:
        return args[0] if render.scope.get("side") is CompensationSide.LEFT else args[1]
    if role is MoveRole.LEAD_OUT:
        return args[2]
    return None
