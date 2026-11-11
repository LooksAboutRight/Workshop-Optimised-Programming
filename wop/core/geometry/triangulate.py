"""Triangles that cover a polygon with holes exactly (the faces of the 3D view), without shapely: every hole is joined to the outer ring by
a bridge to a corner it can see, then ears are cut off the ring one by one."""

from __future__ import annotations

import numpy as np

from ..constants import GEOMETRY_TOLERANCE_MM, TRIANGLE_CORNERS
from .region_types import PolygonRings

Corner = tuple[float, float]


def _signed_area(ring: list[Corner]) -> float:
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1])) / 2


def _open(ring) -> list[Corner]:
    """The ring as corners without the repeated first one, and without corners that repeat the one before."""
    corners: list[Corner] = []
    for point in ring:
        corner = (point.x, point.z)
        if not corners or abs(corner[0] - corners[-1][0]) > GEOMETRY_TOLERANCE_MM or abs(corner[1] - corners[-1][1]) > GEOMETRY_TOLERANCE_MM:
            corners.append(corner)
    if len(corners) > 1 and abs(corners[0][0] - corners[-1][0]) <= GEOMETRY_TOLERANCE_MM and abs(corners[0][1] - corners[-1][1]) <= GEOMETRY_TOLERANCE_MM:
        corners.pop()
    return corners


def _cross(o: Corner, a: Corner, b: Corner) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(p1: Corner, p2: Corner, q1: Corner, q2: Corner) -> bool:
    """True when the two segments cross in their insides (touching at an end does not count)."""
    d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    return ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4))


def _bridged(outer: list[Corner], holes: list[list[Corner]]) -> list[Corner]:
    """One ring: every hole (clockwise) cut into the outer ring (counter-clockwise) along a bridge from its corner of the largest X to the
    nearest corner of the ring that the bridge reaches without crossing an edge; the bridge is walked there and back."""
    ring = list(outer)
    for hole in sorted(holes, key=lambda h: -max(c[0] for c in h)):
        start = max(range(len(hole)), key=lambda i: hole[i][0])
        m = hole[start]
        edges = [(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]
        for other in holes:
            edges += [(other[i], other[(i + 1) % len(other)]) for i in range(len(other))]
        candidates = sorted(range(len(ring)), key=lambda i: (ring[i][0] - m[0]) ** 2 + (ring[i][1] - m[1]) ** 2)
        target = next(
            (i for i in candidates if not any(_segments_cross(m, ring[i], a, b) for a, b in edges if ring[i] not in (a, b) and m not in (a, b))),
            candidates[0],
        )
        loop = hole[start:] + hole[:start]
        ring = ring[: target + 1] + loop + [m] + ring[target:]
    return ring


def _ears(ring: list[Corner]) -> list[tuple[Corner, Corner, Corner]]:
    """Ear clipping of one counter-clockwise ring (it may touch itself along a bridge)."""
    corners = list(ring)
    found: list[tuple[Corner, Corner, Corner]] = []
    for _step in range(2 * len(corners)):  # one ear or one flat corner per step: at most as many steps as corners
        if len(corners) <= TRIANGLE_CORNERS:
            break
        count = len(corners)
        for i in range(count):
            a, b, c = corners[i - 1], corners[i], corners[(i + 1) % count]
            if _cross(a, b, c) <= 0:
                continue  # not convex (or flat): no ear here
            if any(_cross(a, b, p) > 0 and _cross(b, c, p) > 0 and _cross(c, a, p) > 0 for p in corners if p not in (a, b, c)):
                continue  # another corner lies in the triangle
            found.append((a, b, c))
            del corners[i]
            break
        else:
            flat = next((i for i in range(len(corners)) if abs(_cross(corners[i - 1], corners[i], corners[(i + 1) % len(corners)])) <= GEOMETRY_TOLERANCE_MM ** 2), None)
            if flat is None:
                break  # a ring the clipping cannot take apart (it crosses itself): what is found so far
            del corners[flat]  # a corner on a straight edge: it makes no triangle
    if len(corners) == TRIANGLE_CORNERS and _cross(*corners) > 0:
        found.append(tuple(corners))
    return found


def triangles_of(polygons: tuple[PolygonRings, ...]) -> np.ndarray:
    """The triangles (shape (n, 3, 2), the x and z of the corners) that cover the polygons; holes stay open."""
    found: list[tuple[Corner, Corner, Corner]] = []
    for polygon in polygons:
        outer = _open(polygon.exterior)
        if len(outer) < TRIANGLE_CORNERS:
            continue
        if _signed_area(outer) < 0:
            outer.reverse()
        holes = []
        for ring in polygon.holes:
            hole = _open(ring)
            if len(hole) >= TRIANGLE_CORNERS:
                holes.append(hole[::-1] if _signed_area(hole) > 0 else hole)
        found += _ears(_bridged(outer, holes))
    return np.array(found, dtype=float).reshape(-1, TRIANGLE_CORNERS, 2) if found else np.empty((0, TRIANGLE_CORNERS, 2))
