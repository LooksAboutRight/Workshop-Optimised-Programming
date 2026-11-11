"""The sketch editor window (experimental, built next to the old contour editor).

A canvas to draw on (zoom with the wheel, pan with the middle mouse button) and a strip of square buttons with pictograms.
All the logic is in `SketchSession`; this file only turns mouse and keys into session calls and paints the result.
Opened for a target (a contour of the part, a tool shape, an outline of workholding) it has OK and Cancel and says what
is still wrong with the outline; without a target it is a free sketch that is only looked at.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.dxf_contour import DxfAxes
from ...core.sketch.modes import TURNING
from ...core.sketch.model import SketchError
from ..number_text import number_from_text
from ..sketch_constants import CORNER_ACTIONS, TOOL_SELECT
from ..model.helpers import ModelError
from ..sketch_session import SketchSession
from ..sketch_target import SketchTarget
from .window_parts.helpers import DXF_FILTER
from .sketch_canvas import SketchCanvas
from .panel_splitter import RightPanelSplitter
from .sketch_panel import ConstraintPanel, ask_value
from .sketch_toolbox import SketchToolbox
from .small_screens import scrolling
from .sketch_view_constants import DEFAULT_CORNER_MM, FEED_EDIT_WIDTH_PX, PANEL_WIDTH_PX, WINDOW_HEIGHT_PX, WINDOW_WIDTH_PX


class SketchDialog(QDialog):
    def __init__(
        self, parent: QWidget | None = None, session: SketchSession | None = None, target: SketchTarget | None = None
    ) -> None:
        super().__init__(parent)
        self.session = session or SketchSession(target=target)
        self.setWindowTitle(self.session.target.title)
        self.resize(WINDOW_WIDTH_PX, WINDOW_HEIGHT_PX)
        self.canvas = SketchCanvas(self.session)
        self.prompt = QLabel()
        self.prompt.setWordWrap(True)
        self.message = QLabel()
        self.toolbox = SketchToolbox(
            self.session, self._tool_clicked, self._relation, self._modify, self._name, self._import_dxf
        )
        self.tool_buttons = self.toolbox.tool_buttons
        self.relation_buttons = self.toolbox.relation_buttons
        self.modify_buttons = self.toolbox.modify_buttons
        self.name_buttons = self.toolbox.name_buttons
        layout = QVBoxLayout(self)
        picture = QWidget()  # the strip of buttons and the drawing: one part, the tray beside it can be folded away
        beside = QHBoxLayout(picture)
        beside.setContentsMargins(0, 0, 0, 0)
        beside.addWidget(scrolling(self.toolbox))  # the column of buttons scrolls in a low window: it must not set the smallest height of the dialog
        beside.addWidget(self.canvas, 1)
        self.panel = ConstraintPanel(self.session)
        self.splitter = RightPanelSplitter()
        self.splitter.addWidget(picture)
        self.splitter.addWidget(self.panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setCollapsible(0, False)
        self.splitter.setSizes([WINDOW_WIDTH_PX - PANEL_WIDTH_PX, PANEL_WIDTH_PX])
        self.splitter.close_panel(1)  # the tray of relations and dimensions starts folded; its handle opens it
        self.canvas.dimension_edit_requested.connect(self.panel.edit_constraint)
        layout.addWidget(self.splitter, 1)
        layout.addWidget(self.prompt)
        layout.addWidget(self.message)
        self.problems = QLabel()
        self.problems.setWordWrap(True)
        layout.addWidget(self.problems)
        self.notes = QLabel()  # what was lost when the locked things moved (dimensions that were removed)
        self.notes.setWordWrap(True)
        layout.addWidget(self.notes)
        self.step_row = QWidget()  # a path: step through its pieces (the arrow keys do the same)
        step_layout = QHBoxLayout(self.step_row)
        step_layout.setContentsMargins(0, 0, 0, 0)
        self.back_button, self.forward_button = QPushButton("< Step back"), QPushButton("Step forward >")
        for button, handler in ((self.back_button, self.session.step_back), (self.forward_button, self.session.step_forward)):
            button.setFocusPolicy(Qt.NoFocus)  # the arrow keys must stay with the drawing
            button.clicked.connect(lambda _checked=False, h=handler: h())
            step_layout.addWidget(button)
        self.step_label = QLabel()
        step_layout.addWidget(self.step_label, 1)
        self.step_row.setVisible(self.session.can_step)
        layout.addWidget(self.step_row)
        self.feed_row = QWidget()  # a path: the feed of the selected piece
        feed_layout = QHBoxLayout(self.feed_row)
        feed_layout.setContentsMargins(0, 0, 0, 0)
        feed_layout.addWidget(QLabel("Feed of the selected piece (mm per revolution, empty: the feed of the block):"))
        self.feed_edit = QLineEdit()
        self.feed_edit.setMaximumWidth(FEED_EDIT_WIDTH_PX)
        self.feed_edit.editingFinished.connect(self._feed_edited)
        feed_layout.addWidget(self.feed_edit)
        feed_layout.addStretch(1)
        self.feed_row.setVisible(self.session.mode.piece_feeds)
        layout.addWidget(self.feed_row)
        self.ok_button = None
        if self.session.target.commit is not None:
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(self._accept)
            buttons.rejected.connect(self.reject)
            self.ok_button = buttons.button(QDialogButtonBox.Ok)
            self.ok_button.setAutoDefault(False)  # Enter must not store the sketch by accident
            self.ok_button.setDefault(False)
            layout.addWidget(buttons)
        QShortcut(QKeySequence.Undo, self, activated=self.session.undo)
        QShortcut(QKeySequence.Redo, self, activated=self.session.redo)
        self.session.subscribe(self._refresh)
        self._refresh()
        self.canvas.setFocus()  # Delete and Esc go to the drawing from the start

    def _feed_edited(self) -> None:
        text = self.feed_edit.text().strip()
        value = number_from_text(text) if text else None
        if text and (value is None or value <= 0):
            self.session.message = "The feed must be a number greater than zero"
        else:
            self.session.set_piece_feed(value)
        self._refresh()

    def _refresh_feed(self) -> None:
        feed_pieces = [i for i in self.session.selected_pieces if i not in self.session.sketch.rapid_pieces]  # a rapid has no feed
        chosen = {self.session.sketch.piece_feeds.get(i) for i in feed_pieces}
        self.feed_edit.setEnabled(bool(feed_pieces))
        if not self.feed_edit.hasFocus():
            self.feed_edit.setText("" if len(chosen) != 1 or None in chosen else f"{chosen.pop():g}")

    def _refresh(self) -> None:
        self.toolbox.refresh()
        self.notes.setText("\n".join(f"- {note}" for note in self.session.notes))
        if self.session.mode.piece_feeds:
            self._refresh_feed()
        self.step_label.setText(self.session.step_text or "Step through the path with the buttons or the Left and Right arrow keys")
        self.prompt.setText(self.session.prompt)
        self.message.setText(self.session.message)
        found = self.session.problems
        if self.session.mode.needs_outline:
            self.problems.setText("The outline can be used." if not found else "\n".join(f"- {problem}" for problem in found))
        if self.ok_button is not None:
            self.ok_button.setEnabled(not found)

    def keyPressEvent(self, event) -> None:
        """Esc ends what is being drawn and selects; it never closes the window (Cancel and the close button do)."""
        if event.key() == Qt.Key_Escape:
            self.session.escape()
        elif event.key() not in (Qt.Key_Return, Qt.Key_Enter):
            super().keyPressEvent(event)

    def _tool_clicked(self, tool: str) -> None:
        """A tool button turns its tool on; the button of the tool that is on turns it off (back to selecting)."""
        self.session.set_tool(TOOL_SELECT if self.session.tool == tool else tool)
        self._refresh()  # the button the user clicked may have flipped on its own

    def _accept(self) -> None:
        try:
            self.session.target.commit(self.session.result())
        except (SketchError, ModelError) as error:
            QMessageBox.warning(self, self.windowTitle(), str(error))  # stays open so the sketch can be corrected
            return
        self.accept()

    def _import_dxf(self) -> None:
        if self.session.sketch.pieces() and QMessageBox.question(self, self.windowTitle(), "Replace the sketch with a drawing?") != QMessageBox.Yes:
            return
        name, _filter = QFileDialog.getOpenFileName(self, "Import DXF", "", DXF_FILTER)
        if not name:
            return
        axes = DxfAxes.HORIZONTAL
        if self.session.mode is TURNING:
            choices = [a.value for a in DxfAxes]
            chosen, accepted = QInputDialog.getItem(self, self.windowTitle(), "How does the part lie in the drawing?", choices, 0, False)
            if not accepted:
                return
            axes = next(a for a in DxfAxes if a.value == chosen)
        messages = self.session.load_drawing(Path(name), axes)
        if messages:
            QMessageBox.information(self, self.windowTitle(), "\n".join(messages))

    def _name(self, name: str) -> None:
        self.session.use_name(name)
        self._refresh()

    def _modify(self, name: str) -> None:
        """A fillet or chamfer asks for its size once (when the button is pressed); every corner clicked after that gets it."""
        value = 0.0
        if name in CORNER_ACTIONS and self.session.armed != name:
            label = "Radius" if name == "fillet" else "Distance from the corner"
            asked = ask_value(self, name.capitalize(), f"{label} (mm):", DEFAULT_CORNER_MM)
            if asked is None:
                self._refresh()  # the button flipped on its own
                return
            value = asked
        self.session.use_modify(name, value)
        self._refresh()

    def _relation(self, ui_kind: str) -> None:
        self.session.use_relation(ui_kind)
        self._refresh()
