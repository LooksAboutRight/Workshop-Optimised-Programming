"""A 3D scene (wop/ui/view3d.py) as SVG text, for the animation tool (tools/make_animation.py).

The program shows the 3D view with OpenGL. A video is made from pictures that are made one after the other in several
processes, with ImageMagick or rsvg or Qt turning SVG into pictures, so the animation keeps SVG for its 3D view: the
triangles are sorted by depth (painter's algorithm) and shaded flat, the lines and fills are drawn over them. It looks like
the old SVG view of the program and needs no graphics card.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wop.ui import view3d_constants as v  # noqa: E402
from wop.ui.theme import LIGHT_COLORS, ColorSet  # noqa: E402
from wop.ui.view3d import Camera, Scene, Stroke, _Projection  # noqa: E402

RGB_MAX = 255


def _hex(rgb: np.ndarray) -> list[str]:
    values = np.clip(np.round(rgb * RGB_MAX), 0, RGB_MAX).astype(int)
    return [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in values]


def _polyline(pixels: np.ndarray) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pixels)


def _stroke_element(stroke: Stroke, projection: _Projection) -> str:
    pixels = projection.pixels_of(stroke.points)
    dash = f' stroke-dasharray="{" ".join(f"{d:g}" for d in stroke.dash)}"' if stroke.dash else ""
    tag = "polygon" if stroke.closed else "polyline"
    return f'<{tag} points="{_polyline(pixels)}" fill="none" stroke="{stroke.color}" stroke-width="{stroke.width}"{dash}/>'


def scene_to_svg(
    scene: Scene, camera: Camera | None = None, width: int = v.VIEW_WIDTH_PX, height: int = v.VIEW_HEIGHT_PX,
    colors: ColorSet = LIGHT_COLORS,
) -> str:
    projection = _Projection(camera or Camera(), scene.centre, scene.radius, width, height)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    if colors.background:
        parts.append(f'<rect width="{width}" height="{height}" fill="{colors.background}"/>')
    rotation = projection.rotation
    light = np.array(v.LIGHT_DIRECTION, dtype=float)
    light /= np.linalg.norm(light)
    towards = rotation.copy()
    towards[2] *= -1
    faces: list[tuple[float, str, str, float]] = []
    for mesh, opacity in ((scene.solid, 1.0), (scene.glass, scene.glass_opacity)):
        if not mesh.count:
            continue
        positions = mesh.positions.astype(float).reshape(-1, 3, 3)
        flat = positions.reshape(-1, 3)
        u, screen_y, depth = projection.view_arrays(flat[:, 0], flat[:, 1], flat[:, 2])
        x, y = projection.pixel_arrays(u, screen_y)
        corners = np.stack([x, y], axis=1).reshape(-1, 3, 2)
        mean_depth = depth.reshape(-1, 3).mean(axis=1)
        normal = mesh.normals.astype(float).reshape(-1, 3, 3).mean(axis=1) @ towards.T
        length = np.linalg.norm(normal, axis=1)
        lit = np.abs((normal / np.where(length == 0, 1, length)[:, None]) @ light)
        shade = v.AMBIENT_LIGHT + (1 - v.AMBIENT_LIGHT) * lit
        fills = _hex(mesh.colors.reshape(-1, 3, 3)[:, 0] * shade[:, None])
        for index in range(len(corners)):
            faces.append((mean_depth[index], _polyline(corners[index]), fills[index], opacity))
    faces.sort(key=lambda item: -item[0])
    if len(scene.axis):
        pairs = projection.pixels_of(scene.axis).reshape(-1, 2, 2)
        parts += [
            f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="{scene.axis_color}"/>' for a, b in pairs
        ]
    for _depth, points, fill, opacity in faces:
        see_through = "" if opacity >= 1 else f' fill-opacity="{opacity}" stroke-opacity="{opacity}"'
        parts.append(f'<polygon points="{points}" fill="{fill}" stroke="{fill}" stroke-width="0.2"{see_through}/>')
    parts += [_stroke_element(stroke, projection) for stroke in scene.strokes]
    for fill in scene.fills:
        pixels = projection.pixels_of(fill.points)
        parts.append(
            f'<polygon points="{_polyline(pixels)}" fill="{fill.color}" fill-opacity="{fill.opacity}" '
            f'stroke="{fill.stroke_color}" stroke-width="{fill.stroke_width}"/>'
        )
    parts += [_stroke_element(stroke, projection) for stroke in scene.top_strokes]
    parts.append("</svg>")
    return "\n".join(parts)
