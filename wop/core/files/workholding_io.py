"""Save and load workholding items and the program's workholding as plain data (WH1)."""

from __future__ import annotations

from ..constants import WORKHOLDING_FORMAT_VERSION
from ..contour import ContourError
from .contour_io import contour_from_dict, contour_to_dict
from ..lathe.workholding import GripMode, JAWS_KIND, Workholding, WorkholdingError, WorkholdingItem


def item_to_dict(item: WorkholdingItem) -> dict:
    data = {
        "format": WORKHOLDING_FORMAT_VERSION,
        "name": item.name,
        "kind": item.kind,
        "outline": contour_to_dict(item.outline),
    }
    if item.kind == JAWS_KIND:
        data["jaw_count"] = item.jaw_count
        data["jaw_width_deg"] = item.jaw_width_deg
        if item.chuck:
            data["chuck"] = item.chuck
    return data


def item_from_dict(data: dict) -> WorkholdingItem:
    """Rebuild an item. Raises WorkholdingError if the data is incomplete or wrong."""
    try:
        if data["format"] != WORKHOLDING_FORMAT_VERSION:
            raise WorkholdingError(f"unsupported workholding format {data['format']!r}")
        settings = {}
        if data["kind"] == JAWS_KIND:
            settings = {"jaw_count": data["jaw_count"], "jaw_width_deg": data["jaw_width_deg"], "chuck": str(data.get("chuck", ""))}
        return WorkholdingItem(data["name"], data["kind"], contour_from_dict(data["outline"]), **settings)
    except WorkholdingError:
        raise
    except ContourError as error:
        raise WorkholdingError(str(error)) from error
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise WorkholdingError(f"invalid workholding data: {error!r}") from error


def workholding_to_dict(workholding: Workholding) -> dict:
    data: dict = {"grip": workholding.grip.value, "anchor": workholding.anchor}
    if workholding.jaws is not None:
        data["jaws"] = item_to_dict(workholding.jaws)
    if workholding.chuck is not None:
        data["chuck"] = item_to_dict(workholding.chuck)
    return data


def workholding_from_dict(data: dict) -> Workholding:
    try:
        jaws = item_from_dict(data["jaws"]) if data.get("jaws") is not None else None
        chuck = item_from_dict(data["chuck"]) if data.get("chuck") is not None else None
        return Workholding(jaws, chuck, str(data.get("anchor", "")), GripMode(data.get("grip", GripMode.OUTSIDE.value)))
    except WorkholdingError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise WorkholdingError(f"invalid workholding data: {error!r}") from error
