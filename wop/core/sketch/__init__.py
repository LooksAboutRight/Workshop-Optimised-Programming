"""Free 2D sketch (like a CAD sketch): points, lines and arcs, later relations and dimensions.

The sketch knows nothing about lathes. A "mode" (turning contour, tool shape, ...) decides what is allowed and turns the
solved sketch into the program's own data; see `wop/core/sketch/loops.py` for the chains of pieces.
"""
