"""Make a video (or GIF, or PNG folder) of the machining of a project (round B).

Usage (project root):
    python tools/make_animation.py examples/reference.wop.json
    python tools/make_animation.py file.wop.json --out movie.mp4 --step 0.5 --fps 25 --width 1280
    python tools/make_animation.py file.wop.json --realtime 20      (20 times faster than the machine)
    python tools/make_animation.py file.wop.json --blocks 2-3 --png-folder frames

Every frame is the window's side view (tools/animation_frames.py) with a caption. The SVG is made
into a PNG with Qt (PySide6, same look as the window) or, when Qt is missing, with Chromium (playwright) or
ImageMagick ('convert', needs its SVG support); ffmpeg makes the mp4. Without ffmpeg an animated GIF is written (Pillow) or, with
--png-folder, just the PNG files. Big projects have thousands of frames: try --max-frames 200 first.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_OUTPUT = "animation.mp4"
DEFAULT_FPS = 25
DEFAULT_WIDTH_PX = 1280
DEFAULT_HEIGHT_PX = 720
CAPTION_FONT_PX = 14
CAPTION_MARGIN_PX = 8
WHITE = "#ffffff"
PROGRESS_EVERY = 100

Rasterizer = Callable[[str], bytes]  # SVG text -> PNG bytes


def add_caption(svg: str, text: str) -> str:
    """The SVG with a one-line caption in its top left corner (inside the viewBox)."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    element = (
        f'<text x="{CAPTION_MARGIN_PX}" y="{CAPTION_MARGIN_PX + CAPTION_FONT_PX}" '
        f'font-family="Arial, Helvetica, sans-serif" font-size="{CAPTION_FONT_PX}" fill="#222222">{escaped}</text>\n'
    )
    end = svg.rfind("</svg>")
    return svg if end < 0 else svg[:end] + element + svg[end:]


def select_frames_by_time(seconds: list[float], fps: int, speedup: float) -> list[int]:
    """Real-time mode: which frames to show. Output frame k shows the machine at time k * speedup / fps."""
    if speedup <= 0 or fps <= 0:
        raise ValueError("speed-up and fps must be greater than zero")
    chosen: list[int] = []
    total = sum(seconds)
    cumulative, index, k = 0.0, 0, 0
    ends = []
    for value in seconds:
        cumulative += value
        ends.append(cumulative)
    while ends:
        target = k * speedup / fps
        while index < len(ends) - 1 and ends[index] < target:
            index += 1
        chosen.append(index)
        k += 1
        if target >= total:
            break
    return chosen


# --- rasterizers -------------------------------------------------------------------------------

def imagemagick_rasterizer(width: int, height: int) -> Rasterizer:
    program = shutil.which("magick") or shutil.which("convert")
    if program is None:
        raise RuntimeError("ImageMagick is not installed")
    command = [program] + [
        "-background", WHITE, "-density", "96", "svg:-", "-resize", f"{width}x{height}",
        "-gravity", "center", "-extent", f"{width}x{height}", "png:-",
    ]

    def rasterize(svg: str) -> bytes:
        result = subprocess.run(command, input=svg.encode("utf-8"), capture_output=True, check=True)
        return result.stdout

    return rasterize


FONT_FILES = ("arial.ttf", "segoeui.ttf", "tahoma.ttf", "DejaVuSans.ttf")
FONT_FOLDERS = ("C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu", "/Library/Fonts")


def _load_fonts_if_none() -> None:  # unproven: only needed when Qt finds no system fonts
    from PySide6.QtGui import QFontDatabase

    if QFontDatabase.families():
        return
    for folder in FONT_FOLDERS:
        for name in FONT_FILES:
            if (Path(folder) / name).exists():
                QFontDatabase.addApplicationFont(str(Path(folder) / name))


def qt_rasterizer(width: int, height: int) -> Rasterizer:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
    from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    # Windows: the normal "windows" platform is used (nothing is shown); "offscreen" has no system fonts there,
    # so the captions came out without text. Elsewhere "offscreen" works (it uses fontconfig).
    platform = [] if sys.platform == "win32" else ["-platform", "offscreen"]
    app = QGuiApplication.instance() or QGuiApplication(["make_animation", *platform])
    app.setProperty("keep", True)
    _load_fonts_if_none()

    def rasterize(svg: str) -> bytes:
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(QColor(WHITE))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        size = renderer.defaultSize()
        scale = min(width / max(size.width(), 1), height / max(size.height(), 1))
        w, h = size.width() * scale, size.height() * scale
        renderer.render(painter, QRectF((width - w) / 2, (height - h) / 2, w, h))
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(data)

    return rasterize


def chromium_rasterizer(width: int, height: int) -> Rasterizer:
    """Needs the Python package playwright with its Chromium (used where Qt is not installed)."""
    from playwright.sync_api import sync_playwright

    manager = sync_playwright().start()
    browser = manager.chromium.launch()
    page = browser.new_page(viewport={"width": width, "height": height})

    def rasterize(svg: str) -> bytes:
        body = svg[svg.index("<svg"):]
        page.set_content(
            f'<html><body style="margin:0;background:{WHITE}">'
            f'<div style="width:{width}px;height:{height}px;display:flex">{_fit(body)}</div></body></html>'
        )
        return page.screenshot(type="png")

    return rasterize


def _fit(svg: str) -> str:
    """The svg tag scaled to the picture: width and height 100 % (the viewBox keeps the proportions)."""
    return re.sub(r'(<svg[^>]*?) width="[^"]*" height="[^"]*"', r'\1 width="100%" height="100%"', svg, count=1)


def make_rasterizer(kind: str, width: int, height: int) -> Rasterizer:
    builders = {"qt": qt_rasterizer, "chromium": chromium_rasterizer, "imagemagick": imagemagick_rasterizer}
    for name in ([kind] if kind != "auto" else list(builders)):
        try:
            return builders[name](width, height)
        except (ImportError, RuntimeError):
            if kind != "auto":
                raise
    raise RuntimeError("no way to draw SVG found: install PySide6 (pip install PySide6)")


# --- writers -----------------------------------------------------------------------------------

def write_mp4(pngs: Iterable[bytes], path: Path, fps: int) -> None:
    command = [
        "ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png",
        "-i", "-", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for png in pngs:
            process.stdin.write(png)
    finally:
        process.stdin.close()
        code = process.wait()
    if code:
        raise RuntimeError(f"ffmpeg failed (exit code {code})")


def write_gif(pngs: Iterable[bytes], path: Path, fps: int) -> None:
    import io

    from PIL import Image

    images = [Image.open(io.BytesIO(png)).convert("P", palette=Image.ADAPTIVE) for png in pngs]
    if not images:
        raise RuntimeError("no frames")
    images[0].save(path, save_all=True, append_images=images[1:], duration=int(1000 / fps), loop=0)


def write_png_folder(pngs: Iterable[bytes], folder: Path) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    count = 0
    for count, png in enumerate(pngs, 1):
        (folder / f"frame_{count:06d}.png").write_bytes(png)
    return count


# --- main --------------------------------------------------------------------------------------

def parse_blocks(text: str | None) -> range | None:
    """'3' or '2-4' (1-based, as shown) -> positions in plan.blocks."""
    if text is None:
        return None
    match = re.fullmatch(r"(\d+)(?:-(\d+))?", text.strip())
    if not match:
        raise ValueError("--blocks looks like 3 or 2-4")
    first = int(match.group(1))
    last = int(match.group(2) or first)
    if first < 1 or last < first:
        raise ValueError("--blocks looks like 3 or 2-4")
    return range(first - 1, last)


class Context:
    """Everything one process needs to turn frames into PNG bytes (each worker process makes its own)."""

    def __init__(self, project_path: Path, options: dict) -> None:
        from wop.adapters.project_files import load_project
        from wop.core.geometry import Point, segments_to_polyline
        from wop.core.program_model.program import plan_program
        from wop.core.verify import verify_plan
        from wop.core.lathe.workholding import WorkholdingError, place_workholding

        self.options = options
        self.program = load_project(project_path).program
        self.plan = plan_program(self.program)
        self.findings = verify_plan(self.program, self.plan)
        try:
            self.placed = place_workholding(self.program.raw_part, self.program.workholding)
        except WorkholdingError:
            self.placed = None
        safety = self.program.safety
        self.extra = (Point(safety.safe_radius_mm, safety.safe_z_mm), Point(safety.change_point_x, safety.change_point_z))
        if self.placed is not None:  # the picture always holds the jaws, as in the window
            self.extra += tuple(segments_to_polyline(list(self.placed.jaws)))
        self.rasterize = make_rasterizer(options["rasterizer"], options["width"], options["height"])

    def png(self, frame) -> bytes:
        from animation_frames import draw_frame

        extra = {"steps_per_turn": self.options["steps_per_turn"]} if self.options["view"] == "3d" else {}
        svg = draw_frame(self.plan, frame, self.findings, view=self.options["view"], workholding=self.placed,
                         extra_points=self.extra if self.options["view"] == "side" else (), **extra)
        return self.rasterize(add_caption(svg, frame.caption))

    def frames(self, blocks, first_number, wanted):
        from animation_frames import iter_frames

        o = self.options
        return iter_frames(self.program, self.plan, o["step"], o["rapid_frames"], blocks, first_number, wanted)


_worker: Context | None = None


def _start_worker(project_path: Path, options: dict) -> None:
    global _worker
    _worker = Context(project_path, options)


def _render_block(task: tuple[int, int, list[int], str]) -> list[str]:
    """In a worker: the PNG files of the wanted frames of one block; returns their paths in order."""
    block_index, first_number, numbers, folder = task
    paths = []
    for frame in _worker.frames(range(block_index, block_index + 1), first_number, set(numbers)):
        path = Path(folder) / f"f{frame.number:08d}.png"
        path.write_bytes(_worker.png(frame))
        paths.append(str(path))
    return paths


def choose_numbers(seconds: list[float], realtime: float | None, fps: int, limit: int | None) -> list[int]:
    chosen = select_frames_by_time(seconds, fps, realtime) if realtime else list(range(len(seconds)))
    return chosen[: limit or None]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Make a video of the machining of a WOP project.")
    parser.add_argument("project", type=Path)
    parser.add_argument("--out", type=Path, default=Path(DEFAULT_OUTPUT), help=".mp4 or .gif")
    parser.add_argument("--step", type=float, default=1.0, help="mm of path per frame while cutting")
    parser.add_argument("--rapid-frames", type=int, default=6)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH_PX)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT_PX)
    parser.add_argument("--view", choices=["side", "3d"], default="side", help="the 2D side view or the 3D view")
    parser.add_argument("--steps-per-turn", type=int, default=24, help="3D: how smooth the round surfaces are")
    parser.add_argument("--blocks", help="only these blocks, for example 2-3 (1 = first)")
    parser.add_argument("--max-frames", type=int, help="stop after this many frames (a test run)")
    parser.add_argument("--realtime", type=float, help="time-true: this many times faster than the machine")
    parser.add_argument("--jobs", type=int, default=1, help="processes (one block per process); 0 = all processors")
    parser.add_argument("--rasterizer", choices=["auto", "qt", "chromium", "imagemagick"], default="auto")
    parser.add_argument("--png-folder", type=Path, help="write PNG files here instead of a video")
    args = parser.parse_args(argv[1:])

    from animation_frames import timeline
    from wop.adapters.project_files import load_project
    from wop.core.program_model.program import plan_program
    from wop.core.files.project_io import ProjectError

    try:
        program = load_project(args.project).program
        blocks = parse_blocks(args.blocks)
    except (ProjectError, ValueError) as error:
        print(f"cannot start: {error}")
        return 1
    plan = plan_program(program)
    entries = [e for e in timeline(program, plan, args.step, args.rapid_frames) if blocks is None or e[0] in blocks]
    if not entries:
        print("the program has no moves to show")
        return 1
    chosen = choose_numbers([t for _, t in entries], args.realtime, args.fps, args.max_frames)
    print(f"{len(entries)} positions, {len(chosen)} frames, {len(chosen) / args.fps:.1f} s of video")
    options = {
        "step": args.step, "rapid_frames": args.rapid_frames, "width": args.width, "height": args.height,
        "view": args.view, "steps_per_turn": args.steps_per_turn, "rasterizer": args.rasterizer,
    }
    jobs = (os.cpu_count() or 1) if args.jobs == 0 else max(args.jobs, 1)

    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        if jobs == 1:
            context = Context(args.project, options)
            first = 0

            def pngs() -> Iterable[bytes]:
                for n, frame in enumerate(context.frames(blocks, first, set(chosen)), 1):
                    yield context.png(frame)
                    if n % PROGRESS_EVERY == 0:
                        print(f"  {n} frames")
        else:
            tasks = parallel_tasks(entries, chosen, scratch)

            def pngs() -> Iterable[bytes]:
                import multiprocessing

                with multiprocessing.Pool(jobs, _start_worker, (args.project, options)) as pool:
                    done = 0
                    for paths in pool.imap(_render_block, tasks):  # in block order
                        for path in paths:
                            yield Path(path).read_bytes()
                            Path(path).unlink()
                            done += 1
                            if done % PROGRESS_EVERY == 0:
                                print(f"  {done} frames")

        if args.png_folder:
            print(f"{write_png_folder(pngs(), args.png_folder)} PNG files in {args.png_folder}")
            return 0
        if args.out.suffix.lower() == ".gif" or shutil.which("ffmpeg") is None:
            out = args.out.with_suffix(".gif")
            if args.out.suffix.lower() != ".gif":
                print("ffmpeg not found: writing a GIF instead")
            write_gif(pngs(), out, args.fps)
        else:
            out = args.out
            write_mp4(pngs(), out, args.fps)
    print(f"written {out}")
    return 0


def parallel_tasks(entries: list[tuple[int, float]], chosen: list[int], folder: str) -> list[tuple[int, int, list[int], str]]:
    """One task per block that has chosen frames: (block, number of its first position, chosen numbers in it, folder)."""
    first_of: dict[int, int] = {}
    for number, (block, _seconds) in enumerate(entries):
        first_of.setdefault(block, number)
    wanted: dict[int, list[int]] = {}
    for number in chosen:
        wanted.setdefault(entries[number][0], []).append(number)
    return [(block, first_of[block], wanted[block], folder) for block in sorted(wanted)]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
