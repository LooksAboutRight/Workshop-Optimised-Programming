"""The centre of the window: the program picture (2D) or the 3D view, with a toggle (requirements V3, V5).

One checkbox "Up to selected block" serves both views. In 2D the legend is an overlay
in the top-left corner of the picture and a checkbox in the top-right corner hides it; the drawing
itself never moves or changes its scale.
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..app_model import AppModel
from ..contour_picture import contour_svg
from ..ui_constants import LEGEND_MAX_ROWS
from .overlay_svg import TOP_LEFT, TOP_RIGHT, OverlaySvgWidget
from .small_screens import scrolling
from .qt_constants import LEGEND_BACKGROUND_ALPHA, LEGEND_MARKER
from .tools_view import ToolsView
from .workholding_view import WorkholdingView
from .gl_view import opengl_works
from .view3d_widget import View3DWidget

PAGE_2D, PAGE_3D, PAGE_TOOLS, PAGE_WORKHOLDING = 0, 1, 2, 3
OVERLAY_PADDING_PX = 6
OVERLAY_RADIUS_PX = 4


class _NoOpenGLPage(QLabel):
    """Stands where the 3D view would be on a computer without OpenGL (the 2D picture is used there)."""

    def __init__(self, why_not: str) -> None:
        super().__init__(f"The 3D view needs OpenGL: {why_not}")
        self.setAlignment(Qt.AlignCenter)

    def draw(self) -> None:
        pass

    def reset_view(self) -> None:
        pass


class CentreView(QWidget):
    def __init__(self, model: AppModel) -> None:
        super().__init__()
        self.model = model
        self.opengl, why_not = opengl_works()
        self._build_mode_buttons(why_not)
        self._build_stepping_controls()
        self._build_picture()
        self.view3d = View3DWidget(model, self.upto_block, self.step_number) if self.opengl else _NoOpenGLPage(why_not)
        self._build_stack()
        self._build_layout()

    def _build_mode_buttons(self, why_not: str) -> None:
        """2D and 3D, reset view, and 'show only up to the selected block'."""
        self.button_2d = QToolButton()
        self.button_2d.setText("2D")
        self.button_2d.setCheckable(True)
        self.button_3d = QToolButton()
        self.button_3d.setText("3D")
        self.button_3d.setCheckable(True)
        self.button_3d.setToolTip("Show the part in 3D (Ctrl+3)")
        modes = QButtonGroup(self)
        modes.setExclusive(True)
        modes.addButton(self.button_2d)
        modes.addButton(self.button_3d)
        self.button_3d.setChecked(self.opengl)  # the 3D view is the start view when this computer can draw it
        self.button_2d.setChecked(not self.opengl)
        if not self.opengl:
            self.button_3d.setEnabled(False)
            self.button_3d.setToolTip(f"The 3D view needs OpenGL: {why_not}")
        self.button_3d.toggled.connect(self._mode_changed)
        self.reset_button = QToolButton()
        self.reset_button.setText("Reset view")
        self.reset_button.setToolTip(
            "Back to the whole picture: the start position and zoom of the 3D view, or of the 2D picture (or double click it).\n"
            "2D: mouse wheel zooms, drag with the left or middle button moves the picture."
        )
        self.reset_button.clicked.connect(self._reset_view)
        self.upto = QCheckBox("Up to selected block")  # short: the top row decides how narrow the window can be
        self.upto.setToolTip("Show only the blocks up to the selected one: the later blocks are hidden, so you see the part as it is at that moment of the program")
        self.upto.toggled.connect(lambda _on: self.redraw())

    def _build_stepping_controls(self) -> None:
        """Step through: the check box, the four buttons, the slider and the keys."""
        self.step_check = QCheckBox("Step through")
        self.step_check.setToolTip("Walk through the program move by move (Left / Right / Home / End)")
        self.step_check.toggled.connect(self._stepping_toggled)
        self._step_buttons = {}
        for key, text, tip, handler in (
            ("start", "|<", "Start of the block (Home)", lambda: self._go_block_start()),
            ("back", "<", "One move back (Left)", lambda: self._go_later(-1)),
            ("forward", ">", "One move forward (Right)", lambda: self._go_later(1)),
            ("end", ">|", "End of the block (End)", lambda: self._go_block_end()),
        ):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tip)
            button.clicked.connect(handler)
            self._step_buttons[key] = button
        self._slider = QSlider(Qt.Horizontal)
        self._slider.valueChanged.connect(lambda value: self._go_later(0, value))
        self._step_label = QLabel()
        self.step = 0
        self._busy = False
        self._pending_step: int | None = None  # where the slider or a key has moved to, drawn when the input is handled
        self._pending_timer = QTimer(self)
        self._pending_timer.setSingleShot(True)
        self._pending_timer.setInterval(0)
        self._pending_timer.timeout.connect(self._go_pending)
        self._cached_stepper = None  # the stepper whose materials are being worked out in the background
        for sequence, handler in (
            ("Left", lambda: self._go_later(-1)),
            ("Right", lambda: self._go_later(1)),
            ("Home", lambda: self._go_block_start()),
            ("End", lambda: self._go_block_end()),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)

    def _build_picture(self) -> None:
        """The 2D picture with its legend and the legend check box laid over it."""
        self.picture = OverlaySvgWidget()
        self.picture.zoom_settled.connect(self._zoom_settled)
        self._legend = QLabel()
        self._legend.setTextFormat(Qt.RichText)
        self._legend.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._legend_check = QCheckBox("Legend")
        self._legend_check.setChecked(self.model.app_settings.legend_visible)  # remembered between runs (U5)
        self._legend_check.toggled.connect(self._legend_toggled)
        # The checkbox sits in a frame that carries the background: a style sheet on the checkbox itself
        # made its box disappear with some styles.
        self._legend_box = QFrame()
        self._legend_box.setObjectName("legendBox")
        box_layout = QHBoxLayout(self._legend_box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.addWidget(self._legend_check)
        self.picture.add_overlay(self._legend, TOP_LEFT)
        self.picture.add_overlay(self._legend_box, TOP_RIGHT)

    def _build_stack(self) -> None:
        """The pages in the centre: the picture, the 3D view, the tools, the workholding."""
        self.stack = QStackedWidget()
        self.stack.addWidget(self.picture)
        self.stack.addWidget(self.view3d)
        self.tools_view = ToolsView(self.model)
        self.stack.addWidget(scrolling(self.tools_view))  # in scroll areas: the width and height these pages ask for must not set the smallest size of the window
        self.workholding_view = WorkholdingView(self.model)
        self.stack.addWidget(scrolling(self.workholding_view))

    def _build_layout(self) -> None:
        top = QHBoxLayout()
        top.addWidget(self.button_2d)
        top.addWidget(self.button_3d)
        top.addWidget(self.upto)
        top.addWidget(self.step_check)
        top.addWidget(self.reset_button)
        top.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        stepping = QHBoxLayout()
        for key in ("start", "back", "forward", "end"):
            stepping.addWidget(self._step_buttons[key])
        stepping.addWidget(self._slider, 1)
        stepping.addWidget(self._step_label)
        self._stepping_row = QWidget()
        self._stepping_row.setLayout(stepping)
        stepping.setContentsMargins(0, 0, 0, 0)
        self._stepping_row.setVisible(False)
        layout.addLayout(top)
        layout.addWidget(self._stepping_row)
        layout.addWidget(self.stack, 1)

    def _reset_view(self) -> None:
        (self.view3d if self.is_3d else self.picture).reset_view()

    # --- state -----------------------------------------------------------------------

    @property
    def is_3d(self) -> bool:
        return self.button_3d.isChecked()

    def upto_block(self) -> int | None:
        """The last block shown (the selected one), or None for the whole program."""
        return self.model.selected if self.upto.isChecked() else None

    @property
    def stepping(self) -> bool:
        return self.step_check.isChecked()

    def step_number(self) -> int | None:
        """The step shown (None: not stepping, or the program has no steps)."""
        if not self.stepping:
            return None
        stepper = self.model.stepper()
        return self.step if stepper is not None and 0 <= self.step < stepper.count else None

    # --- stepping through (V2) -------------------------------------------------------

    def _stepping_toggled(self, on: bool) -> None:
        self._stepping_row.setVisible(on)
        self.upto.setEnabled(not on)
        if on:
            self._start_at_selection()
        self._cache_materials()
        self.redraw()

    def _start_at_selection(self) -> None:
        stepper = self.model.stepper()
        if stepper is None or stepper.count == 0:
            self.step = 0
            return
        first = stepper.first_step_of_block(self.model.selected) if self.model.selected is not None else None
        self.step = first if first is not None else 0

    def _go_later(self, delta: int, absolute: int | None = None) -> None:
        """Move to a step (`absolute`) or `delta` steps from where the last request went, but draw only once the input
        that is waiting has been handled: dragging the slider or holding a key shows the newest step, not every one."""
        base = self.step if self._pending_step is None else self._pending_step
        self._pending_step = absolute if absolute is not None else base + delta
        self._pending_timer.start()

    def _go_pending(self) -> None:
        step, self._pending_step = self._pending_step, None
        if step is not None:
            self._go(step)

    def _cache_materials(self) -> None:
        """While stepping: the materials of the steps are worked out in the background, from the shown step on, so that a
        jump of the slider does not wait for them. Stops when stepping stops; starts again for a new plan."""
        stepper = self.model.stepper() if self.stepping else None
        if stepper is self._cached_stepper:
            return
        if self._cached_stepper is not None:
            self._cached_stepper.stop_precompute()
        self._cached_stepper = stepper
        if stepper is not None and stepper.count:
            stepper.precompute(self.step)

    def _go(self, step: int) -> None:
        stepper = self.model.stepper()
        if not self.stepping or stepper is None or stepper.count == 0:
            return
        self.step = max(0, min(step, stepper.count - 1))
        block = stepper.frame(self.step).block_index
        if block != self.model.selected and not self._busy:
            self._busy = True
            try:
                self.model.select(block)  # the flow list follows; this redraws through the window
            finally:
                self._busy = False
        self.redraw()

    def _go_block_start(self) -> None:
        stepper = self.model.stepper()
        if self.stepping and stepper is not None and stepper.count:
            at = stepper.block_start(min(self.step, stepper.count - 1))
            # a second press goes to the start of the block before
            self._go(at if self.step != at or at == 0 else stepper.block_start(at - 1))

    def _go_block_end(self) -> None:
        stepper = self.model.stepper()
        if self.stepping and stepper is not None and stepper.count:
            at = stepper.block_end(min(self.step, stepper.count - 1))
            self._go(at if self.step != at or at == stepper.count - 1 else stepper.block_end(at + 1))

    def _follow_selection(self) -> None:
        """The user picked another block while stepping: continue at its first move."""
        stepper = self.model.stepper()
        if self._busy or stepper is None or stepper.count == 0 or self.model.selected is None:
            return
        if self.step < stepper.count and stepper.frame(self.step).block_index == self.model.selected:
            return
        first = stepper.first_step_of_block(self.model.selected)
        if first is not None:
            self.step = first

    def _update_step_controls(self) -> None:
        stepper = self.model.stepper()
        count = 0 if stepper is None else stepper.count
        self.step = max(0, min(self.step, max(count - 1, 0)))
        for key, button in self._step_buttons.items():
            button.setEnabled(count > 0)
        self._slider.blockSignals(True)
        self._slider.setRange(0, max(count - 1, 0))
        self._slider.setValue(self.step)
        self._slider.setEnabled(count > 0)
        self._slider.blockSignals(False)
        text = "no moves"
        if count:
            frame = stepper.frame(self.step)
            text = f"Block {frame.block_number}, move {frame.move_number} of {frame.moves_in_block}"
            if stepper.collisions(self.step, self.model.analysis.findings):
                text += "   COLLISION"  # the message box has the details
        self._step_label.setText(text)

    def toggle_mode(self) -> None:
        if not self.opengl:
            return  # no 3D on this computer
        (self.button_2d if self.is_3d else self.button_3d).setChecked(True)

    def _mode_changed(self, _on: bool) -> None:
        self.stack.setCurrentIndex(PAGE_3D if self.is_3d else PAGE_2D)
        self.redraw()

    # --- drawing -----------------------------------------------------------------------

    def redraw(self) -> None:
        if self.model.tools_view:  # the Tools view replaces the picture
            self.stack.setCurrentIndex(PAGE_TOOLS)
            self.tools_view.refresh()
            return
        if self.model.workholding_view:  # the Workholding view replaces the picture
            self.stack.setCurrentIndex(PAGE_WORKHOLDING)
            self.workholding_view.refresh()
            return
        if self.model.chosen_contour() is not None:  # a contour is chosen: draw it instead of the program
            self.stack.setCurrentIndex(PAGE_2D)
            svg = contour_svg(self.model.chosen_contour(), self.model.colors)
            self.picture.load(QByteArray(svg.encode("utf-8")))
            self._legend.setVisible(False)
            self._legend_box.setVisible(False)
            self.picture.place_overlays()
            return
        self.stack.setCurrentIndex(PAGE_3D if self.is_3d else PAGE_2D)
        if self.stepping:
            self._follow_selection()
            self._update_step_controls()
            self._cache_materials()
        if self.is_3d:
            self.view3d.draw()
            return
        self._legend_box.setVisible(True)
        step = self.step_number()
        upto = self.upto_block()
        if step is not None:
            shown = self.model.step_view(step)
            upto = shown[0] if shown else upto
        self._load_picture(upto, step)
        self._fill_legend(upto)

    def _load_picture(self, upto: int | None, step: int | None) -> None:
        text = self.model.picture(upto, with_legend=False, step=step, line_scale=self.picture.line_scale())  # the legend is the overlay below
        self.picture.load(QByteArray(text.encode("utf-8")))

    def _zoom_settled(self) -> None:
        """The 2D picture was zoomed: draw it again with lines of the same width on the screen."""
        if self.is_3d or self.model.tools_view or self.model.workholding_view or self.model.chosen_contour() is not None:
            return
        step = self.step_number()
        upto = self.upto_block()
        if step is not None:
            shown = self.model.step_view(step)
            upto = shown[0] if shown else upto
        self._load_picture(upto, step)

    def _overlay_style(self) -> str:
        window = self.palette().color(QPalette.Window)
        return (
            f"background-color: rgba({window.red()}, {window.green()}, {window.blue()}, {LEGEND_BACKGROUND_ALPHA});"
            f" border-radius: {OVERLAY_RADIUS_PX}px; padding: {OVERLAY_PADDING_PX}px;"
        )

    def _fill_legend(self, upto: int | None) -> None:
        legend = self.model.legend(upto)
        shown = legend.blocks[:LEGEND_MAX_ROWS]
        lines = [f'<span style="color:{color}">{LEGEND_MARKER}</span> {escape(text)}' for color, text in shown]
        if len(legend.blocks) > len(shown):
            lines.append(f"+ {len(legend.blocks) - len(shown)} more")
        key_color = self.model.colors.key_text
        lines += [f'<span style="color:{key_color}">{escape(text)}</span>' for text in legend.key]
        style = self._overlay_style()
        self._legend.setStyleSheet(style)
        self._legend_box.setStyleSheet(f"QFrame#legendBox {{ {style} }}")
        self._legend.setText("<br>".join(lines))
        self._legend.setVisible(self._legend_check.isChecked())
        self.picture.place_overlays()

    def _legend_toggled(self, on: bool) -> None:
        self.model.set_legend_visible(on)
        self._legend.setVisible(on)
        self.picture.place_overlays()
