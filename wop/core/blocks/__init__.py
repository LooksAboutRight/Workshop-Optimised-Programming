"""Block types. Importing this package registers the built-in ones."""

from . import custom_path, drilling, facing, grooving, machine_function, threading, turning, turning_contour  # noqa: F401  (registers the block types)
from .base import BLOCK_TYPES  # noqa: F401
