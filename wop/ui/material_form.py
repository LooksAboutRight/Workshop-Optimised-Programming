"""The input of the "New..." entry of the material list (requirement U3, M5), without any GUI toolkit.

The fields of this dataclass become the form of the dialog (see block_forms.py).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NewMaterial:
    name: str = ""
    specific_cutting_force_n_mm2: float | None = None  # empty: no cutting data, so no power check
