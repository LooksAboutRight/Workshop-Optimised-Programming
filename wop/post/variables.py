"""The variables of a custom concept (a function of the post file).

A custom concept is declared in `[functions]` (`name = description`); its template is the section `[name]` and its variables are
declared in the section `[name_variables]`, one per line:

    length = float min=0 max=500 default=10 unit=mm label="Feed distance"

The first word after the equals sign is the type (float, int, uint, bool or string); `min`, `max` (numbers only), `default`, `unit` and
`label` are optional. The template uses a variable as a token with its name, `<length>`, with the options of its type. A variable can only
be used in its own concept, and its name may not be a built-in token (nor the first word of one: `tool` would be taken for `<tool number>`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .numbers import NUMBER_OPTIONS, TEXT_OPTIONS, Options
from .template import split_words
from .tokens import TOKENS, Token

VARIABLE_TYPES = ("float", "int", "uint", "bool", "string")
NUMBER_TYPES = ("float", "int", "uint")
VARIABLE_KEYS = ("min", "max", "default", "unit", "label")
NAME = re.compile(r"^[a-z][a-z0-9_]*$")
YES = ("yes", "true", "on", "1")
NO = ("no", "false", "off", "0")
FUNCTION_NAME_END = "_variables"  # a function may not end like this: that is the section of the variables of another one


class VariableError(ValueError):
    """A variable or a function that cannot be read. `line` is the line inside its section (0: no place)."""

    def __init__(self, message: str, line: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.line = line


@dataclass(frozen=True)
class Variable:
    name: str
    type: str
    minimum: float | None
    maximum: float | None
    default: Any
    unit: str
    label: str
    token: Token  # what the template binds `<name>` to


@dataclass(frozen=True)
class Function:
    """A custom concept: what it is called, what it does, and the variables its template and its block can use."""

    name: str
    description: str
    variables: tuple[Variable, ...] = ()


def _reserved(name: str) -> str:
    """Why a name may not be a variable (empty: it may)."""
    if name in TOKENS:
        return f"{name!r} is a token of the program"
    for token_name in sorted(TOKENS):
        if token_name.split()[0] == name:
            return f"{name!r} is the start of the token <{token_name}>"
    return ""


def _number(text: str, type_name: str, what: str, line: int) -> float:
    try:
        value = float(text.replace(",", "."))  # typed in the post editor: a comma works as the decimal point
    except ValueError:
        raise VariableError(f"{what} must be a number", line) from None
    if type_name != "float":
        if value != int(value):
            raise VariableError(f"{what} must be a whole number", line)
        value = int(value)
    if type_name == "uint" and value < 0:
        raise VariableError(f"{what} must not be negative", line)
    return value


def _bool(text: str, line: int) -> bool:
    if text.lower() in YES:
        return True
    if text.lower() in NO:
        return False
    raise VariableError("a bool default is yes or no", line)


def _token(name: str, type_name: str, label: str, default: Any) -> Token:
    def evaluate(render, _args, options: Options):
        value = render.scope.get("variables", {}).get(name)
        if type_name == "bool":
            return (options.get("yes", "1") if value else options.get("no", "")) or None
        return value

    numbers = type_name in NUMBER_TYPES
    return Token(
        name, label, str(default), evaluate, kind="number" if numbers else "text",
        number_format="coordinate" if type_name == "float" else "count",
        options=NUMBER_OPTIONS if numbers else (TEXT_OPTIONS if type_name == "string" else frozenset({"yes", "no", "prefix", "suffix"})),
    )


def parse_variables(entries: list[tuple[int, str, str]]) -> tuple[Variable, ...]:
    """The variables of one concept from `name = type key=value ...` lines (line number, name, rest)."""
    found: list[Variable] = []
    for number, name, rest in entries:
        if not NAME.match(name):
            raise VariableError(f"{name!r} is not a variable name (lower case letters, digits and _, starting with a letter)", number)
        if any(variable.name == name for variable in found):
            raise VariableError(f"the variable {name!r} is declared twice in this concept", number)
        reason = _reserved(name)
        if reason:
            raise VariableError(f"{reason}: choose another name", number)
        try:
            words = split_words(rest, 0)
        except Exception as error:  # an open quote
            raise VariableError(f"{name}: {getattr(error, 'message', error)}", number) from None
        if not words or words[0] not in VARIABLE_TYPES:
            raise VariableError(f"{name}: the type comes first: {', '.join(VARIABLE_TYPES)}", number)
        type_name, given = words[0], {}
        for word in words[1:]:
            key, equals, value = word.partition("=")
            if key not in VARIABLE_KEYS or not equals:
                raise VariableError(f"{name}: {word!r} is not key=value with one of: {', '.join(VARIABLE_KEYS)}", number)
            given[key] = value
        numbers = type_name in NUMBER_TYPES
        if not numbers and ("min" in given or "max" in given):
            raise VariableError(f"{name}: min and max are for numbers (float, int, uint)", number)
        minimum = _number(given["min"], type_name, f"{name}: min", number) if "min" in given else None
        maximum = _number(given["max"], type_name, f"{name}: max", number) if "max" in given else None
        if type_name == "uint" and minimum is None:
            minimum = 0
        if minimum is not None and maximum is not None and minimum > maximum:
            raise VariableError(f"{name}: min is greater than max", number)
        if "default" in given:
            default = (
                _number(given["default"], type_name, f"{name}: default", number) if numbers
                else _bool(given["default"], number) if type_name == "bool" else given["default"]
            )
        else:
            default = (minimum if minimum is not None and minimum > 0 else 0) if numbers else (False if type_name == "bool" else "")
        if numbers and ((minimum is not None and default < minimum) or (maximum is not None and default > maximum)):
            raise VariableError(f"{name}: the default {default:g} is outside min and max", number)
        label = given.get("label") or name.replace("_", " ").capitalize()
        found.append(Variable(name, type_name, minimum, maximum, default, given.get("unit", ""), label, _token(name, type_name, label, default)))
    return tuple(found)


def read_functions(entries: list[tuple[int, str, str]], taken: frozenset[str]) -> dict[str, str]:
    """The custom concepts from `name = description` lines; `taken` are the names of the sections and concepts a function may not use."""
    functions: dict[str, str] = {}
    for number, name, description in entries:
        if not NAME.match(name):
            raise VariableError(f"{name!r} is not a function name (lower case letters, digits and _, starting with a letter)", number)
        if name in taken:
            raise VariableError(f"{name!r} is the name of a section or concept of the program: choose another name", number)
        if name.endswith(FUNCTION_NAME_END):
            raise VariableError(f"a function name may not end with {FUNCTION_NAME_END}", number)
        if name in functions:
            raise VariableError(f"the function {name!r} is declared twice", number)
        functions[name] = description
    return functions


def sample_values(variables: tuple[Variable, ...], present: bool) -> dict[str, Any]:
    """Values for the sample output: the defaults; with `present` a bool is true and a text is filled, else a bool is false and a text empty."""
    values: dict[str, Any] = {}
    for variable in variables:
        if variable.type == "bool":
            values[variable.name] = present
        elif variable.type == "string":
            values[variable.name] = (variable.default or variable.label) if present else ""
        else:
            values[variable.name] = variable.default
    return values


def check_values(variables: tuple[Variable, ...], values: dict[str, Any]) -> dict[str, Any]:
    """The values for a concept: the ones given, the default for the rest. Raises VariableError for a wrong type or a value outside min and max."""
    unknown = sorted(set(values) - {variable.name for variable in variables})
    if unknown:
        raise VariableError(f"there is no variable {unknown[0]!r}")
    checked: dict[str, Any] = {}
    for variable in variables:
        value = values.get(variable.name, variable.default)
        if variable.type in NUMBER_TYPES:
            value = _number(str(value), variable.type, variable.label, 0)
            if (variable.minimum is not None and value < variable.minimum) or (variable.maximum is not None and value > variable.maximum):
                low = "" if variable.minimum is None else f"{variable.minimum:g}"
                high = "" if variable.maximum is None else f"{variable.maximum:g}"
                raise VariableError(f"{variable.label} must be between {low or 'no limit'} and {high or 'no limit'}")
        elif variable.type == "bool":
            value = bool(value)
        else:
            value = str(value)
        checked[variable.name] = value
    return checked
