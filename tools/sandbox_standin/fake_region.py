"""Raster stand-in for wop.core.region (sandbox only: no shapely here)."""
from __future__ import annotations
import math
from dataclasses import dataclass
import numpy as np
from matplotlib.path import Path
import contourpy
from scipy import ndimage

from wop.core.geometry import Point, segments_to_polyline

CELL = 0.1
X0, X1 = -14.0, 46.0
Z0, Z1 = -70.0, 32.0
import os  # WOP_STANDIN_DOMAIN="x0,x1,z0,z1" makes the raster bigger for the tests that need a big bar (slow)
if os.environ.get("WOP_STANDIN_DOMAIN"):
    X0, X1, Z0, Z1 = (float(v) for v in os.environ["WOP_STANDIN_DOMAIN"].split(","))
NX = int(round((X1 - X0) / CELL))
NZ = int(round((Z1 - Z0) / CELL))
# cell centres
XC = X0 + (np.arange(NX) + 0.5) * CELL
ZC = Z0 + (np.arange(NZ) + 0.5) * CELL


class RegionError(ValueError):
    pass


@dataclass(frozen=True)
class Bounds:
    min_x: float
    min_z: float
    max_x: float
    max_z: float


@dataclass(frozen=True)
class PolygonRings:
    exterior: tuple
    holes: tuple


class Region:
    def __init__(self, mask=None):
        self.m = np.zeros((NX, NZ), bool) if mask is None else mask

    @classmethod
    def empty(cls): return cls()

    @classmethod
    def from_points(cls, points):
        if len(points) < 3:
            raise RegionError("needs 3 points")
        path = Path([(p.x, p.z) for p in points])
        xx, zz = np.meshgrid(XC, ZC, indexing="ij")
        m = path.contains_points(np.column_stack([xx.ravel(), zz.ravel()])).reshape(NX, NZ)
        return cls(m)

    @classmethod
    def from_segments(cls, segments, max_deviation_mm=0.001):
        return cls.from_points(segments_to_polyline(list(segments), max_deviation_mm))

    @classmethod
    def rectangle(cls, min_x, min_z, max_x, max_z):
        if max_x <= min_x or max_z <= min_z:
            raise RegionError("bad rectangle")
        m = ((XC >= min_x) & (XC <= max_x))[:, None] & ((ZC >= min_z) & (ZC <= max_z))[None, :]
        return cls(m)

    @property
    def area(self): return float(self.m.sum()) * CELL * CELL
    @property
    def is_empty(self): return not self.m.any()

    @property
    def bounds(self):
        if self.is_empty: return None
        xs = np.where(self.m.any(axis=1))[0]; zs = np.where(self.m.any(axis=0))[0]
        return Bounds(X0 + xs[0] * CELL, Z0 + zs[0] * CELL, X0 + (xs[-1] + 1) * CELL, Z0 + (zs[-1] + 1) * CELL)

    def contains_point(self, p):
        i = int((p.x - X0) / CELL); j = int((p.z - Z0) / CELL)
        if not (0 <= i < NX and 0 <= j < NZ): return False
        return bool(self.m[i, j])

    def union(self, o): return Region(self.m | o.m)
    def difference(self, o): return Region(self.m & ~o.m)
    def intersection(self, o): return Region(self.m & o.m)
    def overlap_area(self, o): return float((self.m & o.m).sum()) * CELL * CELL

    def polygons(self):
        gen = contourpy.contour_generator(ZC, XC, self.m.astype(float), fill_type=contourpy.FillType.OuterCode)
        filled = gen.filled(0.5, 1.5)
        rings = []
        for pts, codes in zip(*filled):
            starts = [i for i, c in enumerate(codes) if c == 1] + [len(codes)]
            ring_list = [pts[a:b] for a, b in zip(starts, starts[1:])]
            ext = tuple(Point(float(x), float(z)) for z, x in ring_list[0])
            holes = tuple(tuple(Point(float(x), float(z)) for z, x in r) for r in ring_list[1:])
            rings.append(PolygonRings(ext, holes))
        return tuple(rings)

def _strict(self, p):
    # boundary counts as outside: all four neighbours (half a cell away) must be inside
    d = CELL
    return all(self.contains_point(Point(p.x + a, p.z + b)) for a in (-d, d) for b in (-d, d))
Region.strictly_contains_point = _strict


def _offset(self, d):
    if d == 0 or self.is_empty: return self
    if d > 0:
        dist = ndimage.distance_transform_edt(~self.m) * CELL
        return Region(dist <= d)
    dist = ndimage.distance_transform_edt(self.m) * CELL
    return Region(dist > -d)
Region.offset = _offset

def _translated(self, dx, dz):
    i = int(round(dx / CELL)); j = int(round(dz / CELL))
    out = np.zeros_like(self.m)
    src_i = slice(max(0, -i), NX - max(0, i)); dst_i = slice(max(0, i), NX - max(0, -i))
    src_j = slice(max(0, -j), NZ - max(0, j)); dst_j = slice(max(0, j), NZ - max(0, -j))
    out[dst_i, dst_j] = self.m[src_i, src_j]
    return Region(out)
Region.translated = _translated

def _penetrates(self, other, tolerance_mm=0.005):
    if self.is_empty or other.is_empty: return False
    # raster: shrink both by one cell so touching edges do not count
    a = ndimage.binary_erosion(self.m); b = ndimage.binary_erosion(other.m)
    return bool((a & b).any())
Region.penetrates = _penetrates

def _shrunk(self, tolerance_mm=0.005):
    return Region(ndimage.binary_erosion(self.m))
Region.shrunk_for_collision = _shrunk
Region.overlaps = lambda self, other: bool((self.m & other.m).any())

def _length_inside(self, points, tolerance_mm=0.005):
    if self.is_empty or len(points) < 2: return 0.0
    er = ndimage.binary_erosion(self.m)
    total = 0.0
    for a, b in zip(points, points[1:]):
        n = max(1, int(math.hypot(b.x - a.x, b.z - a.z) / (CELL / 2)))
        seg = math.hypot(b.x - a.x, b.z - a.z) / n
        for k in range(n):
            t = (k + 0.5) / n
            x = a.x + (b.x - a.x) * t; z = a.z + (b.z - a.z) * t
            i = int((x - X0) / CELL); j = int((z - Z0) / CELL)
            if 0 <= i < NX and 0 <= j < NZ and er[i, j]: total += seg
    return total
Region.length_inside = _length_inside

def _distance_to(self, other):
    if self.is_empty or other.is_empty: return float("inf")
    return float(ndimage.distance_transform_edt(~other.m)[self.m].min()) * CELL
Region.distance_to = _distance_to


def _pieces(self):
    if self.is_empty: return ()
    labels, count = ndimage.label(self.m)
    return tuple(Region(labels == k) for k in range(1, count + 1))
Region.pieces = _pieces
