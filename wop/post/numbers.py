"""Options of a token and the way a number is written.

The same options are valid on every numeric token (the ones it lists): any value the engine knows can be written in any form.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Flags and key=value options. A token lists the ones it accepts.
FLAG_OPTIONS = {
    "incremental": "relative to the last position",
    "absolute": "the position itself",
    "diameter": "write X as a diameter",
    "radius": "write X as a radius",
    "by_mode": "write a radial value (a depth) as a diameter value when the program is in diameter mode",
    "changed": "leave it out (empty) when it is the same as last time",
    "zeros": "keep trailing zeros (10.500)",
    "point": "always a decimal point (10.)",
    "plus": "always a sign (+10)",
    "abs": "no sign",
    "scaled": "an integer scaled by the decimals (10.5 with 3 decimals is 10500)",
    "upper": "capital letters",
    "safe": "only characters the comment of this post may hold",
    "per_minute": "feed per minute instead of per revolution",
    "contour": "the point of the nominal contour (the tool path point where the move has none)",
    "path": "the point of the tool path (where the tool reference point goes)",
}
VALUE_OPTIONS = {
    "decimals": "number of decimals",
    "scale": "multiply the value (1000 for micrometres)",
    "width": "at least this many digits, filled with zeros in front",
    "prefix": "text in front of the value (left out when the value is empty)",
    "suffix": "text behind the value (left out when the value is empty)",
    "yes": "(a bool) the text written when it is true, instead of 1",
    "no": "(a bool) the text written when it is false, instead of nothing",
}
NUMBER_OPTIONS = frozenset({"zeros", "point", "plus", "abs", "scaled", "decimals", "scale", "width", "prefix", "suffix"})
TEXT_OPTIONS = frozenset({"upper", "safe", "prefix", "suffix"})


class OptionError(ValueError):
    pass


@dataclass(frozen=True)
class Options:
    flags: frozenset[str] = frozenset()
    values: dict[str, str] = field(default_factory=dict, hash=False)

    def has(self, name: str) -> bool:
        return name in self.flags

    def get(self, name: str, default: str = "") -> str:
        return self.values.get(name, default)


def parse_options(words: tuple[str, ...], allowed: frozenset[str]) -> Options:
    flags: set[str] = set()
    values: dict[str, str] = {}
    for word in words:
        name, equals, value = word.partition("=")
        if name not in allowed:
            known = ", ".join(sorted(allowed)) or "none"
            raise OptionError(f"unknown option {word!r}; this token has: {known}")
        if equals:
            if name not in VALUE_OPTIONS:
                raise OptionError(f"option {name!r} takes no value")
            values[name] = value
        else:
            if name in VALUE_OPTIONS and name not in ("prefix", "suffix"):
                raise OptionError(f"option {name!r} needs a value ({name}=...)")
            flags.add(name)
    for name in ("decimals", "width"):
        if name in values and not values[name].isdigit():
            raise OptionError(f"{name} must be a whole number")
    if "scale" in values:
        try:
            float(values["scale"])
        except ValueError:
            raise OptionError("scale must be a number") from None
    if {"incremental", "absolute"} <= flags:
        raise OptionError("incremental and absolute together")
    if {"diameter", "radius"} <= flags:
        raise OptionError("diameter and radius together")
    if {"contour", "path"} <= flags:
        raise OptionError("contour and path together")
    return Options(frozenset(flags), values)


@dataclass(frozen=True)
class NumberFormat:
    """The defaults of the post for a kind of number (coordinates, feeds, speeds); the options of a token change them."""

    decimals: int
    zeros: bool = False
    point: bool = False


def format_number(value: float, base: NumberFormat, options: Options) -> str:
    decimals = int(options.get("decimals", str(base.decimals)))
    zeros = base.zeros or options.has("zeros")
    number = value * float(options.get("scale", "1"))
    if options.has("abs"):
        number = abs(number)
    if options.has("scaled"):
        number *= 10 ** decimals
        decimals = 0
    point = options.has("point") or (base.point and decimals > 0)  # a whole number the post asks for (micrometres) has no point
    text = f"{number:.{decimals}f}"
    if decimals > 0 and not zeros:
        text = text.rstrip("0")
        if text.endswith("."):
            text = text[:-1]
    sign = ""
    if text.startswith("-"):
        sign, text = "-", text[1:]
    if not text.strip("0."):  # -0.0004 with three decimals: no minus sign in front of a zero
        sign = ""
    whole, dot, rest = text.partition(".")
    if "width" in options.values:
        whole = whole.rjust(int(options.values["width"]), "0")
    text = whole + dot + rest
    if point and "." not in text:
        text += "."
    if not sign and options.has("plus") and text.strip("0."):
        sign = "+"
    return sign + text
