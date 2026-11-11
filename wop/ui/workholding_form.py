"""The form of a workholding item (WH2): name, and for jaws the count and the width of one jaw.

The outline itself is edited in the contour editor (`workholding_shape_session.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..core.constants import DEFAULT_JAW_COUNT, DEFAULT_JAW_WIDTH_DEG
from ..core.lathe.workholding import JAWS_KIND, WorkholdingItem
from .block_forms import NO_WORKHOLDING_LABEL


@dataclass(frozen=True)
class WorkholdingForm:
    name: str = ""
    jaw_count: int = DEFAULT_JAW_COUNT
    jaw_width_deg: float = DEFAULT_JAW_WIDTH_DEG
    chuck: str = ""  # jaws only: the chuck body they sit on
    is_jaws: bool = True  # not shown: decides which fields are
    chuck_names: tuple[str, ...] = ()  # not shown: what the chuck dropdown offers


def _form_fields(self: WorkholdingForm) -> tuple[str, ...]:
    """A chuck body has only a name; jaws also have their count and width (used by the 3D picture)."""
    return ("name", "jaw_count", "jaw_width_deg", "chuck") if self.is_jaws else ("name",)


def _field_choices(self: WorkholdingForm) -> dict[str, list[tuple[str, str]]]:
    """The chuck of a set of jaws is one of the chuck bodies in the list, or none."""
    return {"chuck": [("", NO_WORKHOLDING_LABEL)] + [(name, name) for name in self.chuck_names]}


WorkholdingForm.form_fields = _form_fields  # type: ignore[attr-defined]
WorkholdingForm.field_choices = _field_choices  # type: ignore[attr-defined]


def form_of_item(item: WorkholdingItem, chuck_names: tuple[str, ...] = ()) -> WorkholdingForm:
    return WorkholdingForm(item.name, item.jaw_count, item.jaw_width_deg, item.chuck, item.kind == JAWS_KIND, chuck_names)


def item_from_form(item: WorkholdingItem, form: WorkholdingForm) -> WorkholdingItem:
    """The item with the values of the form. Raises WorkholdingError (a ValueError) for impossible values."""
    return replace(item, name=form.name.strip(), jaw_count=form.jaw_count, jaw_width_deg=form.jaw_width_deg, chuck=form.chuck if item.kind == JAWS_KIND else "")
