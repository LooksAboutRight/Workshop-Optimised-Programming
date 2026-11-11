"""The buttons of the sketch editor: square, with a pictogram, the name as a hover text, in sections with a heading.

The sections (`SECTIONS`): Draw (makes basic geometry), Edit (changes geometry that is there already), Constraints (the
dimension first, then the relations), Mark (what a line or a point is: helper, centre line, cutting edge, a name) and
General (DXF import, undo, redo, snap). A relation or a change acts on the selection when that fits; otherwise the button
turns it on as a tool (shown pressed) and the things to act on are clicked.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QToolButton, QWidget

from ..sketch_constants import MODIFY_ITEMS, NAME_PREFIX, RELATION_ITEMS, SECTIONS, TOOL_NAMES, TOOL_SELECT
from ..sketch_session import SketchSession
from .sketch_icons import make_icon
from .qt_constants import DXF_SHAPE_HINT
from .sketch_view_constants import BUTTON_PX, HEADING_SCALE, ICON_PX, SECTION_GAP_PX, TOOLBOX_COLUMNS

UNDO_TIP = "Undo (Ctrl+Z)"
REDO_TIP = "Redo (Ctrl+Y)"
SNAP_TIP = "Snap to points and to horizontal / vertical while drawing"
IMPORT_TIP = "Import DXF: replace the sketch with a drawing"
SHOW_RELATIONS_TIP = "Show the relations (H, V, ||, tan ...) in the picture"
SHOW_DIMENSIONS_TIP = "Show the dimensions in the picture"


class SketchToolbox(QWidget):
    def __init__(
        self,
        session: SketchSession,
        on_tool: Callable[[str], None],
        on_relation: Callable[[str], None],
        on_modify: Callable[[str], None],
        on_name: Callable[[str], None],
        on_import: Callable[[], None],
    ) -> None:
        super().__init__()
        self.session = session
        self.tool_buttons: dict[str, QToolButton] = {}  # no Select button: selecting is what you get when no tool is on
        self.relation_buttons: dict[str, QToolButton] = {}
        self.modify_buttons: dict[str, QToolButton] = {}
        self.name_buttons: dict[str, QToolButton] = {}  # one per kind of named point the target offers (not the automatic tip)
        self.sections: list[tuple[str, list[str]]] = []  # (heading, the names of its buttons in order), as built
        self.headings: list[QLabel] = []
        every: dict[str, QToolButton] = {}
        for name, label in TOOL_NAMES:
            if name != TOOL_SELECT:
                self.tool_buttons[name] = every[name] = self._button(name, label, checkable=True)
                self.tool_buttons[name].clicked.connect(lambda _c=False, n=name: on_tool(n))
        for name, label in RELATION_ITEMS:
            self.relation_buttons[name] = every[name] = self._button(name, label, checkable=True)
            self.relation_buttons[name].clicked.connect(lambda _c=False, n=name: on_relation(n))
        for name, label in MODIFY_ITEMS:
            if (name != "cutting" or session.mode.cutting_edges) and (name != "rapid" or session.mode.rapid_lines):
                self.modify_buttons[name] = every[name] = self._button(name, label, checkable=True)
                self.modify_buttons[name].clicked.connect(lambda _c=False, n=name: on_modify(n))
        if session.mode.named_points:
            for kind in session.target.point_kinds:
                if not kind.automatic:
                    self.name_buttons[kind.name] = every[NAME_PREFIX + kind.name] = self._button(kind.icon, kind.label, checkable=True)
                    self.name_buttons[kind.name].clicked.connect(lambda _c=False, n=kind.name: on_name(n))
        self.import_button = every["import"] = self._button(
            "import", IMPORT_TIP + (" " + DXF_SHAPE_HINT if session.mode.named_points else "")
        )
        self.import_button.clicked.connect(lambda _c=False: on_import())
        self.undo_button = every["undo"] = self._button("undo", UNDO_TIP)
        self.undo_button.clicked.connect(lambda _c=False: session.undo())
        self.redo_button = every["redo"] = self._button("redo", REDO_TIP)
        self.redo_button.clicked.connect(lambda _c=False: session.redo())
        self.snap_button = every["snap"] = self._button("snap", SNAP_TIP, checkable=True)
        self.snap_button.setChecked(True)
        self.snap_button.toggled.connect(lambda on: setattr(session, "snapping", on))
        self.relations_button = every["show_relations"] = self._button("show_relations", SHOW_RELATIONS_TIP, checkable=True)
        self.relations_button.setChecked(session.show_relations)
        self.relations_button.toggled.connect(lambda on: self._show("show_relations", on))
        self.dimensions_button = every["show_dimensions"] = self._button("show_dimensions", SHOW_DIMENSIONS_TIP, checkable=True)
        self.dimensions_button.setChecked(session.show_dimensions)
        self.dimensions_button.toggled.connect(lambda on: self._show("show_dimensions", on))

        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        row = 0
        for heading, names in SECTIONS:
            present = [name for name in self._expanded(names) if name in every]
            if not present:
                continue
            label = QLabel(heading)
            font = label.font()
            font.setBold(True)
            font.setPointSizeF(font.pointSizeF() * HEADING_SCALE)
            label.setFont(font)
            label.setEnabled(False)  # the muted colour of the theme
            self._layout.addWidget(label, row, 0, 1, TOOLBOX_COLUMNS)
            self.headings.append(label)
            row += 1
            for index, name in enumerate(present):
                self._layout.addWidget(every[name], row + index // TOOLBOX_COLUMNS, index % TOOLBOX_COLUMNS)
            row += math.ceil(len(present) / TOOLBOX_COLUMNS)
            self._layout.setRowMinimumHeight(row, SECTION_GAP_PX)
            row += 1
            self.sections.append((heading, present))
        self._layout.setRowStretch(row, 1)
        self.setFixedWidth(TOOLBOX_COLUMNS * BUTTON_PX + (TOOLBOX_COLUMNS - 1) * self._layout.spacing())

    def _expanded(self, names: tuple[str, ...]) -> list[str]:
        """"names" in a section stands for the buttons of the kinds of point."""
        return [item for name in names for item in ([NAME_PREFIX + k for k in self.name_buttons] if name == "names" else [name])]

    def _show(self, what: str, on: bool) -> None:
        setattr(self.session, what, on)
        self.session.refresh()

    def _button(self, icon_name: str, tip: str, checkable: bool = False) -> QToolButton:
        button = QToolButton()
        button.setIcon(make_icon(icon_name, self.palette().buttonText().color()))
        button.setIconSize(QSize(ICON_PX, ICON_PX))
        button.setFixedSize(BUTTON_PX, BUTTON_PX)
        button.setToolTip(tip)
        button.setCheckable(checkable)
        button.setFocusPolicy(Qt.NoFocus)  # a clicked button must not keep the keyboard (Esc, Delete)
        return button

    def refresh(self) -> None:
        """Show which tool is on (a relation or change too: it can always be turned on, then its things are clicked)."""
        session = self.session
        for tool, button in self.tool_buttons.items():
            button.setChecked(tool == session.tool)
            button.setEnabled(session.available_tool(tool))
        for name, button in {**self.relation_buttons, **self.modify_buttons}.items():
            button.setChecked(session.armed == name)
        for name, button in self.name_buttons.items():
            button.setChecked(session.armed == NAME_PREFIX + name)
        self.undo_button.setEnabled(session.can_undo)
        self.redo_button.setEnabled(session.can_redo)
