"""Turn plain dataclasses into JSON-ready data and back, using their type hints.

Supported field types: bool, int, float, str, None, enums (stored by name),
dataclasses, tuples of those, and `X | None`. Numbers keep the kind they had
(an int stays an int), so saving a loaded file gives the same text again.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from enum import Enum
from typing import Any


class CodecError(ValueError):
    """The data does not fit the dataclass."""


def plain_number(value: float) -> float | int:
    """A whole number as an int (30, not 30.0): the files read the same whether a value was given as 30 or worked out as 30.0 (a compiled
    `geometry.Point` always holds floats, `tools/build_compiled.py`)."""
    return int(value) if float(value).is_integer() else value


def to_data(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.name
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_data(getattr(value, f.name)) for f in dataclasses.fields(value) if f.init}  # a field not given when made is worked out
    if isinstance(value, (tuple, list)):
        return [to_data(item) for item in value]
    if isinstance(value, dict):  # plain data kept as it is (the sketch of a custom path)
        return {str(key): to_data(item) for key, item in value.items()}
    if isinstance(value, float):
        return plain_number(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise CodecError(f"cannot store a value of type {type(value).__name__}")


def from_data(cls: type, data: Any) -> Any:
    """Build a `cls` from data made by to_data. Missing fields use their default."""
    if not isinstance(data, dict):
        raise CodecError(f"expected an object for {cls.__name__}")
    hints = typing.get_type_hints(cls)
    values = {}
    for field in dataclasses.fields(cls):
        if not field.init:
            continue
        if field.name in data:
            values[field.name] = _decode(hints[field.name], data[field.name], field.name)
        elif field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
            raise CodecError(f"{cls.__name__}: field {field.name!r} is missing")
    extra = set(data) - {f.name for f in dataclasses.fields(cls) if f.init}
    if extra:
        raise CodecError(f"{cls.__name__}: unknown fields {sorted(extra)}")
    try:
        return cls(**values)
    except ValueError as error:
        raise CodecError(f"{cls.__name__}: {error}") from error


def _decode(hint: Any, value: Any, name: str) -> Any:
    """`value` from the file as the type `hint`; `name` is the field, for the error message."""
    origin = typing.get_origin(hint)
    if origin is typing.Union or origin is types.UnionType:
        options = [a for a in typing.get_args(hint) if a is not type(None)]
        if value is None:
            if len(options) == len(typing.get_args(hint)):
                raise CodecError(f"{name}: a value is needed")
            return None
        if len(options) != 1:
            raise CodecError(f"{name}: unsupported field type")
        return _decode(options[0], value, name)
    if origin is tuple:
        if not isinstance(value, list):
            raise CodecError(f"{name}: expected a list")
        item_type = typing.get_args(hint)[0]
        return tuple(_decode(item_type, item, name) for item in value)
    if isinstance(hint, type) and issubclass(hint, Enum):
        try:
            return hint[value]
        except (KeyError, TypeError):
            raise CodecError(f"{name}: {value!r} is not one of {[m.name for m in hint]}") from None
    if isinstance(hint, type) and dataclasses.is_dataclass(hint):
        return from_data(hint, value)
    if hint is dict:
        if not isinstance(value, dict):
            raise CodecError(f"{name}: expected an object")
        return value
    if hint is bool:
        if not isinstance(value, bool):
            raise CodecError(f"{name}: expected true or false")
        return value
    if hint in (int, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CodecError(f"{name}: expected a number, got {value!r}")
        return value
    if hint is str:
        if not isinstance(value, str):
            raise CodecError(f"{name}: expected text")
        return value
    raise CodecError(f"{name}: unsupported field type {hint!r}")
