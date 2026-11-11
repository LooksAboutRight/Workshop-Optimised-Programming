"""A set of chuck jaws: a closed outline with named points for the steps (placed by one of them)."""

from ..constants import EXAMPLE_JAWS_OUTLINE, EXAMPLE_JAWS_POINTS
from ..lathe.workholding import JAWS_KIND, WorkholdingItem
from .base import WORKHOLDING_TYPES, WorkholdingType, item_from_vertices


@WORKHOLDING_TYPES.register
class JawsType(WorkholdingType):
    type_name = JAWS_KIND
    label = "Chuck jaws"
    uses_jaw_settings = True

    def example(self, name: str) -> WorkholdingItem:
        return item_from_vertices(name, JAWS_KIND, EXAMPLE_JAWS_OUTLINE, EXAMPLE_JAWS_POINTS)
