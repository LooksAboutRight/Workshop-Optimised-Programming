"""Save and load the user part of the material library (requirement M5)."""

from __future__ import annotations

from ..constants import MATERIAL_FORMAT_VERSION
from ..material import Material, MaterialError, MaterialLibrary


def library_to_dict(library: MaterialLibrary) -> dict:
    return {
        "format": MATERIAL_FORMAT_VERSION,
        "materials": [
            {"name": m.name, "specific_cutting_force_n_mm2": m.specific_cutting_force_n_mm2}
            for m in library.user
        ],
    }


def library_from_dict(data: dict) -> MaterialLibrary:
    """Rebuild the library. Raises MaterialError for wrong data."""
    try:
        if data["format"] != MATERIAL_FORMAT_VERSION:
            raise MaterialError(f"unsupported material format {data['format']!r}")
        materials = []
        for item in data["materials"]:
            force = item["specific_cutting_force_n_mm2"]
            if force is not None and (isinstance(force, bool) or not isinstance(force, (int, float))):
                raise MaterialError(f"expected a number, got {force!r}")
            materials.append(Material(item["name"], force))
        return MaterialLibrary(tuple(materials))
    except MaterialError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise MaterialError(f"invalid material data: {error!r}") from error
