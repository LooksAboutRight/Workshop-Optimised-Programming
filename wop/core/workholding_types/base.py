"""Workholding types (WH1): what the Add menu of the workholding view offers.

A type has a `type_name` (stored in the item), a `label` and `example(name)`, which makes an item with
placeholder values that the user then reshapes with the contour editor. Registered with WORKHOLDING_TYPES.register.
"""

from __future__ import annotations

from ..contour import ContourDefinition, LineStep, NamedPoint
from ..contour_solver import build_contour
from ..geometry import Point
from ..lathe.workholding import WorkholdingError, WorkholdingItem


def outline_definition(
    vertices: tuple[tuple[float, float], ...], points: tuple[tuple[str, float, float], ...]
) -> ContourDefinition:
    """A closed outline through the vertices (x, z), with named points."""
    start, rest = vertices[0], vertices[1:]
    steps = tuple(LineStep(Point(x, z)) for x, z in rest)
    return ContourDefinition(Point(*start), steps, True, tuple(NamedPoint(n, x, z) for n, x, z in points))


def item_from_vertices(
    name: str,
    kind: str,
    vertices: tuple[tuple[float, float], ...],
    points: tuple[tuple[str, float, float], ...],
    **settings,
) -> WorkholdingItem:
    """An item whose outline is a closed polygon through the vertices (the shape can be edited later)."""
    outline = build_contour(name, name, outline_definition(vertices, points))
    return WorkholdingItem(name, kind, outline, **settings)


class WorkholdingType:
    """Base of a workholding type. Set the class attributes and write `example`."""

    type_name: str = ""
    label: str = ""  # shown in the Add menu
    uses_jaw_settings = False  # the item has a jaw count and width

    def example(self, name: str) -> WorkholdingItem:
        raise NotImplementedError


class WorkholdingTypeRegistry:
    def __init__(self) -> None:
        self._types: dict[str, WorkholdingType] = {}

    def register(self, type_class: type[WorkholdingType]) -> type[WorkholdingType]:
        instance = type_class()
        if not instance.type_name or not instance.label:
            raise WorkholdingError(f"{type_class.__name__} has no type_name or label")
        if instance.type_name in self._types:
            raise WorkholdingError(f"workholding type {instance.type_name!r} is already registered")
        self._types[instance.type_name] = instance
        return type_class

    def get(self, type_name: str) -> WorkholdingType:
        if type_name not in self._types:
            raise WorkholdingError(f"unknown workholding type {type_name!r}")
        return self._types[type_name]

    def types(self) -> list[WorkholdingType]:
        return sorted(self._types.values(), key=lambda t: t.label)


WORKHOLDING_TYPES = WorkholdingTypeRegistry()


def example_item(type_name: str, name: str) -> WorkholdingItem:
    """A new item of the type with placeholder values."""
    return WORKHOLDING_TYPES.get(type_name).example(name)
