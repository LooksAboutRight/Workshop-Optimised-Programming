"""The 3D scene of the part after a block (requirement Z1), as numbers: triangles, lines and polygons. No toolkit.

The 2D outline of the material left is revolved around the spindle axis (Z), with a quarter cut away so the inside can
be seen. The cutting moves and rapid moves of the chosen block, the finished outline and the tool are drawn in the cut
plane. `build_scene` makes the scene; the OpenGL widget (`wop/ui/qt/gl_view.py`) draws the triangles with a depth buffer
and the strokes and fills over them, using `view_matrix` for the camera.

Model space: first axis = the spindle axis (Z), the other two span the turning plane (`_model_point`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import numpy as np

from ..core.geometry import ArcSegment, Point, Segment
from ..core.geometry import segments_to_polyline
from ..core.program_model.operations import ArcMove, LinearMove, Rapid, plain_moves
from ..core.geometry.region import Region
from . import ui_constants as ui
from . import view3d_constants as v
from .svg_preview import StepView
from .theme import LIGHT_COLORS, ColorSet

if TYPE_CHECKING:  # the scene code needs these only for annotations
    from ..core.program_model.program import ProgramPlan
    from ..core.lathe.workholding import PlacedWorkholding

Vec = tuple[float, float, float]
RGB_MAX = 255
ARC_DEVIATION_MM = 0.05
CAP_CORNERS = 3  # the corners of a triangle


@dataclass(frozen=True)
class Camera:
    azimuth_deg: float = v.DEFAULT_AZIMUTH_DEG
    elevation_deg: float = v.DEFAULT_ELEVATION_DEG
    zoom: float = 1.0
    pan_x_px: float = 0.0  # the picture is moved on the screen (the view direction is fixed in the window)
    pan_y_px: float = 0.0

    def turned(self, d_azimuth: float, d_elevation: float) -> "Camera":
        elevation = min(v.MAX_ELEVATION_DEG, max(v.MIN_ELEVATION_DEG, self.elevation_deg + d_elevation))
        return replace(self, azimuth_deg=self.azimuth_deg + d_azimuth, elevation_deg=elevation)

    def panned(self, dx_px: float, dy_px: float) -> "Camera":
        return replace(self, pan_x_px=self.pan_x_px + dx_px, pan_y_px=self.pan_y_px + dy_px)

    def zoomed(self, factor: float) -> "Camera":
        return replace(self, zoom=min(v.MAX_ZOOM, max(v.MIN_ZOOM, self.zoom * factor)))


def _model_point(x: float, z: float, angle: float) -> Vec:
    """Model space: first axis = the spindle axis (Z), the other two span the turning plane."""
    return (z, x * math.cos(angle), x * math.sin(angle))


class _Projection:
    """Orthographic view: screen x to the right, screen y up, depth growing away from the viewer."""

    def __init__(self, camera: Camera, centre: Vec, radius: float, width: float, height: float) -> None:
        self._az = math.radians(camera.azimuth_deg)
        self._el = math.radians(camera.elevation_deg)
        self._cos_az, self._sin_az = math.cos(self._az), math.sin(self._az)
        self._cos_el, self._sin_el = math.cos(self._el), math.sin(self._el)
        self._centre = centre
        self._scale = camera.zoom * (min(width, height) / 2 - v.VIEW_MARGIN_PX) / radius
        self._half = (width / 2 + camera.pan_x_px, height / 2 + camera.pan_y_px)

    @property
    def scale(self) -> float:
        return self._scale

    @property
    def half(self) -> tuple[float, float]:
        return self._half

    @property
    def rotation(self) -> np.ndarray:
        """The 3 x 3 turn from model space (minus the centre) to (screen x, screen y, depth)."""
        return np.array(
            [
                [self._cos_az, -self._sin_az, 0.0],
                [-self._sin_el * self._sin_az, -self._sin_el * self._cos_az, self._cos_el],
                [self._cos_el * self._sin_az, self._cos_el * self._cos_az, self._sin_el],
            ]
        )

    @property
    def centre(self) -> Vec:
        return self._centre

    def view(self, point: Vec) -> Vec:
        a, b, h = (point[i] - self._centre[i] for i in range(3))
        return self.rotate(a, b, h)

    def rotate(self, a, b, h):
        """The turn into screen space; works on numbers and on numpy arrays alike."""
        u = a * self._cos_az - b * self._sin_az
        d = a * self._sin_az + b * self._cos_az
        screen_y = h * self._cos_el - d * self._sin_el
        depth = d * self._cos_el + h * self._sin_el
        return (u, screen_y, depth)

    def view_arrays(self, a, b, h):
        """`view` for model coordinates given as arrays."""
        return self.rotate(a - self._centre[0], b - self._centre[1], h - self._centre[2])

    def pixel_arrays(self, u, screen_y):
        return (self._half[0] + u * self._scale, self._half[1] - screen_y * self._scale)

    def pixel(self, view_point: Vec) -> tuple[float, float]:
        return (self._half[0] + view_point[0] * self._scale, self._half[1] - view_point[1] * self._scale)

    def pixels_of(self, points: np.ndarray) -> np.ndarray:
        """Model points (n, 3) to screen pixels (n, 2)."""
        u, screen_y, _depth = self.view_arrays(points[:, 0], points[:, 1], points[:, 2])
        x, y = self.pixel_arrays(u, screen_y)
        return np.stack([x, y], axis=1)


def view_matrix(projection: _Projection, width: float, height: float, radius: float) -> tuple[np.ndarray, np.ndarray]:
    """(mvp, normal matrix) for OpenGL: the same picture as `_Projection` (orthographic, pan in pixels, zoom).

    mvp is 4 x 4 and takes model points to clip space (depth smaller = nearer); the normal matrix is 3 x 3 and takes a
    model normal to (screen x, screen y, towards the viewer), the space the light is given in."""
    rotation = projection.rotation
    scale = projection.scale
    pan_x, pan_y = projection.half[0] - width / 2, projection.half[1] - height / 2
    mvp = np.zeros((4, 4))
    mvp[0, :3] = rotation[0] * scale / (width / 2)
    mvp[1, :3] = rotation[1] * scale / (height / 2)
    mvp[2, :3] = rotation[2] / (v.DEPTH_RANGE_FACTOR * radius)
    mvp[3, 3] = 1.0
    centre = np.array(projection.centre)
    mvp[:3, 3] = -mvp[:3, :3] @ centre
    mvp[0, 3] += pan_x / (width / 2)
    mvp[1, 3] += -pan_y / (height / 2)
    towards_viewer = rotation.copy()
    towards_viewer[2] *= -1
    return mvp, towards_viewer


# --- the scene -----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Mesh:
    """Triangles in model space: positions and normals (n, 3), colours (n, 3) in 0..1. n is a multiple of 3."""

    positions: np.ndarray
    normals: np.ndarray
    colors: np.ndarray

    @property
    def count(self) -> int:
        return len(self.positions)


EMPTY_MESH = Mesh(np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32))


def join_meshes(meshes: list[Mesh]) -> Mesh:
    meshes = [mesh for mesh in meshes if mesh.count]
    if not meshes:
        return EMPTY_MESH
    return Mesh(
        np.concatenate([m.positions for m in meshes]).astype(np.float32),
        np.concatenate([m.normals for m in meshes]).astype(np.float32),
        np.concatenate([m.colors for m in meshes]).astype(np.float32),
    )


@dataclass(frozen=True)
class Stroke:
    """A line in model space, drawn over the solids. `dash` in pixels (on, off); empty = solid."""

    points: np.ndarray  # (n, 3)
    color: str
    width: float
    dash: tuple[float, ...] = ()
    closed: bool = False


@dataclass(frozen=True)
class Fill:
    """A flat polygon in model space, drawn over the solids."""

    points: np.ndarray  # (n, 3)
    color: str
    opacity: float
    stroke_color: str
    stroke_width: float


@dataclass(frozen=True)
class Scene:
    solid: Mesh  # opaque triangles, depth tested
    glass: Mesh  # see-through triangles (jaws while the spindle runs), drawn after the solids
    glass_opacity: float
    axis: np.ndarray  # (2n, 3) end points of the short dashes of the spindle axis, drawn with the depth test
    axis_color: str
    strokes: tuple[Stroke, ...]
    fills: tuple[Fill, ...]
    top_strokes: tuple[Stroke, ...]  # drawn after the fills (the outline of the tool holder)
    centre: Vec  # what the camera looks at
    radius: float  # of a sphere round the whole scene


def _shown_block(plan: ProgramPlan, upto_block: int | None) -> int:
    last = len(plan.blocks) - 1 if upto_block is None else upto_block
    if upto_block is not None and not 0 <= last < len(plan.blocks):
        raise ValueError("there is no such block")
    return last


def _path_points(plan: ProgramPlan, block_index: int, max_moves: int | None = None) -> list[tuple[bool, list[Point]]]:
    """(is_cutting, points) for every move of the block (only the first `max_moves` of them if given)."""
    moves: list[tuple[bool, list[Point]]] = []
    position: Point | None = None
    counted = 0
    for block_number, block_plan in enumerate(plan.blocks[: block_index + 1]):
        for original in block_plan.operations:
            for move in plain_moves(original):
                if not isinstance(move, (Rapid, LinearMove, ArcMove)):
                    continue
                if block_number == block_index:
                    if max_moves is not None and counted >= max_moves:
                        return moves
                    counted += 1
                if block_number == block_index and position is not None:
                    if isinstance(move, ArcMove):
                        arc = ArcSegment(position, move.end, move.center, move.direction)
                        points = arc.to_polyline(ARC_DEVIATION_MM)
                    else:
                        points = [position, move.end]
                    moves.append((not isinstance(move, Rapid), points))
                position = move.end
    return moves


def _bounds(region: Region) -> tuple[float, float, float]:
    box = region.bounds
    if box is None:
        return (0.0, 1.0, 1.0)
    return (box.min_z, box.max_z, box.max_x)


def _rgb(rgb: tuple[int, int, int]) -> np.ndarray:
    return np.array(rgb, dtype=np.float32) / RGB_MAX


def _plane_points(points, angle: float) -> np.ndarray:
    """(x, z) points as model points in the plane at `angle`."""
    x = np.array([p.x for p in points])
    z = np.array([p.z for p in points])
    return np.stack([z, x * math.cos(angle), x * math.sin(angle)], axis=1)


def _open_ring(ring) -> list[Point]:
    ring = list(ring)
    return ring[:-1] if len(ring) > 1 and ring[0].is_close(ring[-1]) else ring


def revolve_ring(ring, angles: list[float], rgb: tuple[int, int, int]) -> Mesh:
    """The surface of a closed (x, z) outline turned through the given angles: two triangles for every edge and angle
    step, with the normals of the surface (smooth round the axis). An edge that lies on the axis has no surface."""
    ring = _open_ring(ring)
    edges = [(p, q) for p, q in zip(ring, ring[1:] + ring[:1]) if not (p.x <= v.AXIS_EPSILON_MM and q.x <= v.AXIS_EPSILON_MM)]
    if not edges or len(angles) < 2:
        return EMPTY_MESH
    px = np.array([e[0].x for e in edges])[:, None]
    pz = np.array([e[0].z for e in edges])[:, None]
    qx = np.array([e[1].x for e in edges])[:, None]
    qz = np.array([e[1].z for e in edges])[:, None]
    angle = np.asarray(angles, dtype=float)
    first, second = angle[None, :-1], angle[None, 1:]
    count, steps = len(edges), len(angle) - 1

    def corner(x, z, a):  # (edges, steps, 3)
        return np.stack(np.broadcast_arrays(z + 0 * a, x * np.cos(a), x * np.sin(a)), axis=-1)

    a, b, c, d = corner(px, pz, first), corner(qx, qz, first), corner(qx, qz, second), corner(px, pz, second)
    length = np.hypot(qx - px, qz - pz)
    length = np.where(length == 0, 1.0, length)
    n_x, n_z = (qz - pz) / length, -(qx - px) / length  # the normal of the edge in the (x, z) plane

    def normal(a_):  # (edges, steps, 3): the same normal turned with the angle
        return np.stack(np.broadcast_arrays(n_z + 0 * a_, n_x * np.cos(a_), n_x * np.sin(a_)), axis=-1)

    n_first, n_second = normal(first), normal(second)
    positions = np.stack([a, b, c, a, c, d], axis=2).reshape(-1, 3)
    normals = np.stack([n_first, n_first, n_second, n_first, n_second, n_second], axis=2).reshape(-1, 3)
    colors = np.broadcast_to(_rgb(rgb), (count * steps * 2 * CAP_CORNERS, 3))
    return Mesh(positions.astype(np.float32), normals.astype(np.float32), colors.astype(np.float32))


def flat_face(triangles: np.ndarray, angle: float, rgb: tuple[int, int, int]) -> Mesh:
    """Triangles in the (x, z) plane (n, 3, 2) put into the plane at `angle` as a flat face."""
    if not len(triangles):
        return EMPTY_MESH
    flat = triangles.reshape(-1, 2)
    positions = np.stack([flat[:, 1], flat[:, 0] * math.cos(angle), flat[:, 0] * math.sin(angle)], axis=1)
    normals = np.broadcast_to(np.array([0.0, -math.sin(angle), math.cos(angle)]), positions.shape)
    colors = np.broadcast_to(_rgb(rgb), positions.shape)
    return Mesh(positions.astype(np.float32), normals.astype(np.float32), colors.astype(np.float32))


def _ring_triangles(ring) -> np.ndarray:
    ring = _open_ring(ring)
    try:
        return Region.from_points(ring).triangles()
    except ValueError:  # an outline that crosses itself or has no area has no flat face
        return np.zeros((0, CAP_CORNERS, 2))


def _jaw_intervals(count: int, width_deg: float) -> list[tuple[float, float]]:
    """The angles (degrees, inside the swept range) each jaw covers. Jaw 0 is centred in the plane of the path."""
    low, high = v.SWEEP_START_DEG, v.SWEEP_START_DEG + v.SWEEP_DEG
    found = []
    for k in range(count):
        centre = v.PATH_PLANE_DEG + k * 360.0 / count
        for turn in (-360.0, 0.0, 360.0):
            start, end = centre + turn - width_deg / 2, centre + turn + width_deg / 2
            start, end = max(start, low), min(end, high)
            if end - start > v.AXIS_EPSILON_MM:
                found.append((start, end))
    return found


def _dashes(start: np.ndarray, end: np.ndarray, on: float, off: float) -> np.ndarray:
    """End points of the short dashes on a straight line (pairs, n x 2 x 3)."""
    length = float(np.linalg.norm(end - start))
    if length == 0:
        return np.zeros((0, 3))
    direction = (end - start) / length
    found = []
    at = 0.0
    while at < length:
        found += [start + direction * at, start + direction * min(at + on, length)]
        at += on + off
    return np.array(found)


def _part_meshes(region: Region, angles: list[float]) -> tuple[list[Mesh], list[Stroke]]:
    """The part revolved, and the cross-section at both ends of the cut-away part with its edge."""
    rings = [ring for polygon in region.polygons() for ring in (polygon.exterior, *polygon.holes)]
    solids = [revolve_ring(ring, angles, v.SURFACE_RGB) for ring in rings]
    strokes: list[Stroke] = []
    section = region.triangles()
    for angle in (angles[0], angles[-1]):
        solids.append(flat_face(section, angle, v.CUT_FACE_RGB))
        strokes += [Stroke(_plane_points(_open_ring(ring), angle), v.CUT_FACE_EDGE, v.CUT_FACE_EDGE_WIDTH_PX, closed=True) for ring in rings]
    return solids, strokes


def _chuck_meshes(workholding: PlacedWorkholding, angles: list[float]) -> tuple[list[Mesh], list[Stroke]]:
    """The chuck body revolved like the part, with its faces and edges at both ends."""
    chuck = segments_to_polyline(list(workholding.chuck))
    solids = [revolve_ring(chuck, angles, v.CHUCK_RGB)]
    strokes: list[Stroke] = []
    chuck_faces = _ring_triangles(chuck)
    for angle in (angles[0], angles[-1]):
        solids.append(flat_face(chuck_faces, angle, v.CHUCK_RGB))
        strokes.append(Stroke(_plane_points(_open_ring(chuck), angle), v.CHUCK_EDGE, v.CUT_FACE_EDGE_WIDTH_PX, closed=True))
    return solids, strokes


def _jaw_meshes(workholding: PlacedWorkholding, angles: list[float], steps_per_turn: int, spindle_on: bool) -> tuple[list[Mesh], list[Mesh]]:
    """The jaws: (solids, glass). Separate solids, or with `spindle_on` one full, slightly transparent revolve (glass)."""
    ring = segments_to_polyline(list(workholding.jaws))
    if spindle_on:
        turns = max(3, steps_per_turn)
        full = [math.radians(360.0 * k / turns) for k in range(turns + 1)]
        return [], [revolve_ring(ring, full, v.JAWS_RGB)]
    solids: list[Mesh] = []
    per_step = math.radians(v.SWEEP_DEG) / max(1, len(angles) - 1)
    jaw_faces = _ring_triangles(ring)
    for start_deg, end_deg in _jaw_intervals(workholding.jaw_count, workholding.jaw_width_deg):
        a0, a1 = math.radians(start_deg), math.radians(end_deg)
        pieces = max(1, math.ceil((a1 - a0) / per_step))
        solids.append(revolve_ring(ring, [a0 + (a1 - a0) * k / pieces for k in range(pieces + 1)], v.JAWS_RGB))
        solids += [flat_face(jaw_faces, a0, v.JAWS_RGB), flat_face(jaw_faces, a1, v.JAWS_RGB)]
    return solids, []


def _path_strokes(plan: ProgramPlan, last: int, step: StepView | None, colors: ColorSet, path_angle: float) -> list[Stroke]:
    """The tool path in the plane where it is drawn: cutting moves solid, rapids dashed."""
    strokes = []
    for cutting, points in _path_points(plan, last, step.moves_done if step else None):
        line = _plane_points(points, path_angle)
        if cutting:
            strokes.append(Stroke(line, colors.cut_3d, v.PATH_WIDTH_PX))
        else:
            strokes.append(Stroke(line, colors.rapid_3d, v.PATH_WIDTH_PX, v.PATH_RAPID_DASH))
    return strokes


def _tool_parts(step: StepView, colors: ColorSet, path_angle: float) -> tuple[list[Fill], list[Stroke]]:
    """The tool of a step: the cutter filled, the holder outlined (on top of everything)."""
    fills = [
        Fill(_plane_points(_open_ring(polygon.exterior), path_angle), colors.tool_cutter, ui.TOOL_FILL_OPACITY, colors.tool_cutter, ui.TOOL_OUTLINE_WIDTH_PX)
        for polygon in step.tool_body.polygons()
    ]
    top_strokes = [Stroke(_plane_points(holder, path_angle), colors.tool_holder, ui.TOOL_OUTLINE_WIDTH_PX) for holder in step.holder_outlines]
    return fills, top_strokes


def build_scene(
    plan: ProgramPlan,
    upto_block: int | None = None,
    steps_per_turn: int = v.STEPS_PER_TURN,
    show_path: bool = True,
    colors: ColorSet = LIGHT_COLORS,
    step: StepView | None = None,
    workholding: PlacedWorkholding | None = None,
    spindle_on: bool = False,
    outline: tuple[Segment, ...] = (),
) -> Scene:
    """The part after block `upto_block` (None: the last one) as a scene.

    step: show the material and the tool of one step of that block instead (V2).

    workholding: the placed chuck body and jaws (WH4). The chuck is revolved like the part. The jaws are three (or
    more) separate solids, one centred in the plane where the path is drawn; with `spindle_on` they are drawn as a full,
    slightly transparent revolve instead. The part and the chuck never turn transparent.

    outline: the finished shape of the block chosen in the flow list, dashed in the plane where the path is drawn.
    """
    last = _shown_block(plan, upto_block)
    region = step.material if step else plan.blocks[last].material_after if plan.blocks else plan.stock
    min_z, max_z, max_x = _bounds(plan.stock)
    if workholding is not None and workholding.jaws:  # the jaws are always inside the picture (the chuck is cut off)
        jaw_points = segments_to_polyline(list(workholding.jaws))
        min_z = min(min_z, *(p.z for p in jaw_points))
        max_z = max(max_z, *(p.z for p in jaw_points))
        max_x = max(max_x, *(p.x for p in jaw_points))
    centre = ((min_z + max_z) / 2, 0.0, 0.0)
    radius = math.sqrt(((max_z - min_z) / 2) ** 2 + max_x**2) or 1.0

    start = math.radians(v.SWEEP_START_DEG)
    sweep = math.radians(v.SWEEP_DEG)
    steps = max(3, round(steps_per_turn * v.SWEEP_DEG / 360))
    angles = [start + sweep * k / steps for k in range(steps + 1)]
    path_angle = math.radians(v.PATH_PLANE_DEG)

    solids, strokes = _part_meshes(region, angles)
    glass: list[Mesh] = []
    fills: list[Fill] = []
    top_strokes: list[Stroke] = []
    if workholding is not None and workholding.chuck:
        chuck_solids, chuck_strokes = _chuck_meshes(workholding, angles)
        solids += chuck_solids
        strokes += chuck_strokes
    if workholding is not None and workholding.jaws:
        jaw_solids, glass = _jaw_meshes(workholding, angles, steps_per_turn, spindle_on)
        solids += jaw_solids
    if show_path and plan.blocks:
        strokes += _path_strokes(plan, last, step, colors, path_angle)
    if outline:
        strokes.append(Stroke(
            _plane_points(segments_to_polyline(list(outline)), path_angle), colors.finished_outline,
            ui.FINISHED_OUTLINE_WIDTH_PX, v.FINISHED_OUTLINE_DASH_PX,
        ))
    if step:
        fills, top_strokes = _tool_parts(step, colors, path_angle)

    ends = (np.array(_model_point(0, min_z - v.AXIS_OVERSHOOT_MM, 0)), np.array(_model_point(0, max_z + v.AXIS_OVERSHOOT_MM, 0)))
    axis = _dashes(ends[0], ends[1], radius * v.AXIS_DASH_ON_FACTOR, radius * v.AXIS_DASH_OFF_FACTOR)
    return Scene(
        join_meshes(solids), join_meshes(glass), v.JAWS_SPINDLE_OPACITY, axis, colors.axis_3d,
        tuple(strokes), tuple(fills), tuple(top_strokes), centre, radius,
    )
