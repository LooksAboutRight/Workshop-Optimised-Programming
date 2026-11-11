"""The chuck body: a closed outline behind the jaws (revolved, the cylinder with a bore)."""

from ..constants import EXAMPLE_CHUCK_OUTLINE, EXAMPLE_CHUCK_POINTS
from ..lathe.workholding import CHUCK_KIND, WorkholdingItem
from .base import WORKHOLDING_TYPES, WorkholdingType, item_from_vertices


@WORKHOLDING_TYPES.register
class ChuckType(WorkholdingType):
    type_name = CHUCK_KIND
    label = "Chuck body"

    def example(self, name: str) -> WorkholdingItem:
        return item_from_vertices(name, CHUCK_KIND, EXAMPLE_CHUCK_OUTLINE, EXAMPLE_CHUCK_POINTS)
