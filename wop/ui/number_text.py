"""Read a number out of the text of a number field (toolkit-free, so it can be tested).

The text may carry the unit ("12.5 mm") and may use "," as the decimal point.
"""

from __future__ import annotations

import re

_NUMBER = re.compile(r"[-+]?(?:\d+(?:[.,]\d*)?|[.,]\d+)")


def number_from_text(text: str) -> float | None:
    """The first number in the text, or None when there is none."""
    match = _NUMBER.search(text)
    if match is None:
        return None
    return float(match.group(0).replace(",", "."))
