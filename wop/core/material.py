"""Materials and the built-in material table (requirement M5).

The built-in values live in constants.py. The user can change a built-in
material or add new ones; those entries are kept in the user part of the
library (saved by material_io.py). A user entry with the name of a built-in
material replaces it; removing the user entry brings the built-in back.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import BUILTIN_MATERIALS


class MaterialError(ValueError):
    """The material data is not usable."""


@dataclass(frozen=True)
class Material:
    name: str
    specific_cutting_force_n_mm2: float | None = None  # None = no cutting data

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise MaterialError("a material needs a name")
        force = self.specific_cutting_force_n_mm2
        if force is not None and force <= 0:
            raise MaterialError("specific cutting force must be greater than zero")

    @property
    def has_cutting_data(self) -> bool:
        return self.specific_cutting_force_n_mm2 is not None

    def power_check_warning(self) -> str | None:
        """Text for the user if no power check is possible, else None."""
        if self.has_cutting_data:
            return None
        return f"material {self.name!r} has no cutting data: no power check"


def builtin_materials() -> tuple[Material, ...]:
    return tuple(Material(name, force) for name, force in BUILTIN_MATERIALS)


def _key(name: str) -> str:
    return name.strip().casefold()


@dataclass(frozen=True)
class MaterialLibrary:
    user: tuple[Material, ...] = ()

    def __post_init__(self) -> None:
        keys = [_key(material.name) for material in self.user]
        if len(set(keys)) != len(keys):
            raise MaterialError("a material is listed twice")

    def all(self) -> list[Material]:
        """Built-in materials (replaced by user versions) followed by new user materials."""
        user_by_key = {_key(material.name): material for material in self.user}
        result = []
        for builtin in builtin_materials():
            result.append(user_by_key.pop(_key(builtin.name), builtin))
        result.extend(user_by_key.values())
        return result

    def find(self, name: str) -> Material | None:
        for material in self.all():
            if _key(material.name) == _key(name):
                return material
        return None

    def is_user_defined(self, name: str) -> bool:
        return any(_key(material.name) == _key(name) for material in self.user)

    def with_material(self, material: Material) -> MaterialLibrary:
        """Add a material or replace the one with the same name."""
        kept = tuple(m for m in self.user if _key(m.name) != _key(material.name))
        return MaterialLibrary(kept + (material,))

    def without(self, name: str) -> MaterialLibrary:
        """Remove the user entry (a built-in material returns to its default)."""
        return MaterialLibrary(tuple(m for m in self.user if _key(m.name) != _key(name)))
