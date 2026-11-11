"""Which fields of a project the user has touched (requirement U6).

A field is "touched" once the user edited it. The project keeps the touched
fields as a tuple of text keys `owner/field.path` (for example `b3/depth_of_cut_mm`
or `raw_part/outer_radius_mm`). `None` instead of a tuple means "not recorded"
(a project file from before this existed): then every field counts as touched,
so old projects do not suddenly look unset.
"""

from __future__ import annotations

OWNER_SEPARATOR = "/"
PATH_SEPARATOR = "."
SETUP_OWNER = "setup"  # raw part, material and safe positions (one form)
BLOCK_OWNER_PREFIX = "block:"

Touched = tuple[str, ...] | None


def block_owner(block_id: str) -> str:
    return BLOCK_OWNER_PREFIX + block_id


def field_key(owner: str, path: tuple[str, ...]) -> str:
    return owner + OWNER_SEPARATOR + PATH_SEPARATOR.join(path)


def is_touched(touched: Touched, owner: str, path: tuple[str, ...]) -> bool:
    return touched is None or field_key(owner, path) in touched


def mark_touched(touched: Touched, owner: str, path: tuple[str, ...]) -> Touched:
    if touched is None:
        return None
    key = field_key(owner, path)
    return touched if key in touched else tuple(sorted((*touched, key)))


def mark_untouched(touched: Touched, owner: str, path: tuple[str, ...]) -> Touched:
    """Forget one field (Reset to default). Without records there is nothing to forget."""
    if touched is None:
        return None
    key = field_key(owner, path)
    return tuple(k for k in touched if k != key)


def forget_owner(touched: Touched, owner: str) -> Touched:
    """Drop every field of an owner (a deleted block must not hand its marks to a new block with the same id)."""
    if touched is None:
        return None
    prefix = owner + OWNER_SEPARATOR
    return tuple(k for k in touched if not k.startswith(prefix))


def rename_owner(touched: Touched, old: str, new: str) -> Touched:
    """Give the fields of an owner another owner name (a renamed machine keeps its marks)."""
    if touched is None:
        return None
    old_prefix, new_prefix = old + OWNER_SEPARATOR, new + OWNER_SEPARATOR
    return tuple(sorted(new_prefix + k[len(old_prefix):] if k.startswith(old_prefix) else k for k in touched))


def copy_owner(touched: Touched, source: str, copy: str) -> Touched:
    """Give an owner (a copied block) the same marks as its source; the source keeps its own."""
    if touched is None:
        return None
    source_prefix, copy_prefix = source + OWNER_SEPARATOR, copy + OWNER_SEPARATOR
    added = tuple(copy_prefix + k[len(source_prefix):] for k in touched if k.startswith(source_prefix))
    return tuple(sorted({*touched, *added}))
