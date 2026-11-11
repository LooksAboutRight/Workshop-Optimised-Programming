"""A stand-in for PySide6 that accepts every call (ONLY for a sandbox where PySide6 cannot be installed).

`install()` puts PySide6 and its sub-modules into sys.modules. Every Q... class is a plain Python class whose methods
do nothing and answer with a value that accepts anything; signals really connect and emit, so wiring can be tested.
It finds typos, wrong names, wrong arguments to OUR code and broken wiring; it knows nothing about how Qt looks or
behaves. A development aid, not part of the product.
"""

from __future__ import annotations

import sys
import types

SUBMODULES = ("QtCore", "QtGui", "QtWidgets", "QtSvg", "QtSvgWidgets", "QtOpenGL", "QtOpenGLWidgets")


# methods whose answer must be a real string, because our code looks at it
STRING_ANSWERS = {
    '.name': '#ffffff', '.text': '', '.toPlainText': '', '.currentText': '', '.title': '',
    '.rowCount': 0, '.count': 0, '.columnCount': 0, '.currentRow': -1, '.currentIndex': -1,
}


class Value:
    """Answers every attribute, call and operator (enum values, results of Qt methods)."""

    def __init__(self, name: str = "") -> None:
        self._name = name

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        return Value(f"{self._name}.{name}")

    def __call__(self, *args, **kwargs):
        for ending, result in STRING_ANSWERS.items():
            if self._name.endswith(ending):
                return result
        return Value(f"{self._name}()")

    def __eq__(self, other) -> bool:
        return isinstance(other, Value) and other._name == self._name

    def __hash__(self) -> int:
        return hash(self._name)

    def __or__(self, other):
        return self

    __ror__ = __and__ = __rand__ = __or__
    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = __truediv__ = __rtruediv__ = __floordiv__ = __or__
    __neg__ = __invert__ = __or__

    def __lt__(self, other) -> bool:
        return False

    __le__ = __gt__ = __ge__ = __lt__

    def __bool__(self) -> bool:
        return False  # a dialog answers 'cancelled', a loop over a count ends

    def __int__(self) -> int:
        return 0

    __index__ = __int__

    def __float__(self) -> float:
        return 0.0

    def __iter__(self):
        return iter(())

    def __repr__(self) -> str:
        return f"<Qt {self._name}>"


class _Meta(type):
    def __getattr__(cls, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        return Value(f"{cls.__name__}.{name}")


class BoundSignal:
    def __init__(self) -> None:
        self._slots: list = []

    def connect(self, slot, *_args) -> None:
        self._slots.append(slot)

    def disconnect(self, *_args) -> None:
        self._slots.clear()

    def emit(self, *args) -> None:
        for slot in list(self._slots):
            slot(*args)


class Signal:
    def __init__(self, *_types) -> None:
        self._name = ""

    def __set_name__(self, owner, name) -> None:
        self._name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        return obj.__dict__.setdefault("_signal_" + self._name, BoundSignal())


def Slot(*_args, **_kwargs):  # noqa: N802  (the Qt decorator)
    return lambda function: function


class _Base(metaclass=_Meta):
    def __init__(self, *args, **kwargs) -> None:
        pass

    # methods that our code reaches through super()
    def event(self, event) -> bool:
        return True

    def changeEvent(self, event) -> None:  # noqa: N802
        pass

    def closeEvent(self, event) -> None:  # noqa: N802
        pass

    def __getattr__(self, name: str):
        if name.startswith("__") or name.startswith("_signal_"):
            raise AttributeError(name)
        return Value(f"{type(self).__name__}.{name}")


def _make(name: str) -> type:
    return _Meta(name, (_Base,), {})


class _Module(types.ModuleType):
    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        if name == "Signal":
            return Signal
        if name == "Slot":
            return Slot
        if name[:1] == "Q":
            made = _make(name)
            setattr(self, name, made)
            return made
        raise AttributeError(name)


def install() -> None:
    if "PySide6" in sys.modules and not isinstance(sys.modules["PySide6"], _Module):
        return
    root = _Module("PySide6")
    root._fake = True
    root.__path__ = []  # a package
    sys.modules["PySide6"] = root
    for name in SUBMODULES:
        module = _Module(f"PySide6.{name}")
        sys.modules[f"PySide6.{name}"] = module
        setattr(root, name, module)
