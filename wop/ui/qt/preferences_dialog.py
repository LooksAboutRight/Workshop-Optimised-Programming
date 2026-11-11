"""File > Preferences: the values the user may change (rows generated from the table in core/conventions.py).

A valid entry is saved to conventions.json at once; a wrong one stays in its box, marked red with the reason, and the
file keeps the last good value. Values apply after a restart of WOP (the window says so).
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFontDatabase, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.conventions import CHOICE, MATERIAL
from ..app_model import AppModel
from ..preferences_model import PreferenceRow, PreferencesModel, value_text
from ..ui_constants import RESET_TO_DEFAULT_TEXT
from .theme_qt import untouched_text_color
from .qt_constants import (
    PREFERENCES_DIALOG_HEIGHT_PX,
    PREFERENCES_DIALOG_WIDTH_PX,
    PREFERENCES_ERROR_STYLE,
    PREFERENCES_FIELD_WIDTH_PX,
    PREFERENCES_FIXED_HEIGHT_PX,
    PREFERENCES_FIXED_WIDTH_PX,
    PREFERENCES_MEANING_MIN_WIDTH_PX,
    PREFERENCES_NAME_STYLE,
    PREFERENCES_RESTART_TEXT,
)


class _Box(QLineEdit):
    """A text box that selects everything when entered (like the number boxes of the forms)."""

    def focusInEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().focusInEvent(event)
        self.selectAll()


class FixedValuesDialog(QDialog):
    """The constants that cannot be changed, as plain read only text."""

    def __init__(self, parent: QWidget, text: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fixed values (read only)")
        self.resize(PREFERENCES_FIXED_WIDTH_PX, PREFERENCES_FIXED_HEIGHT_PX)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        view.setPlainText(text)
        view.setLineWrapMode(QPlainTextEdit.NoWrap)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(view)
        layout.addWidget(close)


class PreferencesDialog(QDialog):
    def __init__(self, parent: QWidget, model: AppModel, preferences: PreferencesModel | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(PREFERENCES_DIALOG_WIDTH_PX, PREFERENCES_DIALOG_HEIGHT_PX)
        self.model = model
        self.preferences = preferences or PreferencesModel()
        self._editors: dict[str, QWidget] = {}
        self._resets: dict[str, QPushButton] = {}
        self._dim = untouched_text_color(self.palette())  # the colour the forms use for a value that was not touched
        self._restart = QLabel(PREFERENCES_RESTART_TEXT)
        self._restart.setWordWrap(True)
        self._message = QLabel("")
        self._message.setWordWrap(True)
        body = QWidget()
        self._grid = QGridLayout(body)
        self._build_rows()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        fixed = QPushButton("Fixed values...")
        fixed.setToolTip("The constants that cannot be changed here (tables and standards), as text")
        fixed.clicked.connect(lambda _checked=False: self._show_fixed())
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(fixed)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        if self.preferences.problems:
            problems = QLabel("The file had entries that cannot be used:\n" + "\n".join(self.preferences.problems))
            problems.setWordWrap(True)
            layout.addWidget(problems)
        layout.addWidget(scroll, 1)
        layout.addWidget(self._message)
        layout.addWidget(self._restart)
        layout.addLayout(buttons)
        self._refresh_marks()

    # --- building -----------------------------------------------------------------------------------

    def _build_rows(self) -> None:
        line = 0
        for heading, rows in self.preferences.groups():
            title = QLabel(heading)
            font = title.font()
            font.setBold(True)
            font.setPointSize(font.pointSize() + 1)
            title.setFont(font)
            self._grid.addWidget(title, line, 0, 1, -1)
            line += 1
            for row in rows:
                self._add_row(line, row)
                line += 1
        self._grid.setColumnMinimumWidth(0, PREFERENCES_MEANING_MIN_WIDTH_PX)
        self._grid.setColumnStretch(0, 1)
        self._grid.setRowStretch(line, 1)

    def _add_row(self, line: int, row: PreferenceRow) -> None:
        convention = row.convention
        text = QLabel(f"{convention.meaning}<br><span style='{PREFERENCES_NAME_STYLE}'>{convention.name}: {row.rule_text}</span>")
        text.setWordWrap(True)
        editor = self._make_editor(row)
        reset = QPushButton("Reset")
        reset.setToolTip("Back to the default value")
        reset.clicked.connect(lambda _checked=False, name=convention.name: self._reset(name))
        self._editors[convention.name] = editor
        editor.setContextMenuPolicy(Qt.CustomContextMenu)
        editor.customContextMenuRequested.connect(lambda point, name=convention.name: self._menu(name, point))
        self._resets[convention.name] = reset
        for column, widget in enumerate((text, editor, reset)):
            self._grid.addWidget(widget, line, column)

    def _make_editor(self, row: PreferenceRow) -> QWidget:
        convention = row.convention
        name = convention.name
        if convention.rule in (CHOICE, MATERIAL):
            box = QComboBox()
            items = [value_text(choice) for choice in convention.choices] if convention.rule == CHOICE else self._material_names()
            current = value_text(row.value)
            if current not in items:
                items.append(current)
            box.addItems(items)
            box.setCurrentText(current)
            box.setMinimumWidth(PREFERENCES_FIELD_WIDTH_PX)
            box.activated.connect(lambda _index=0, name=name: self._edited(name))
            return box
        edit = _Box(value_text(row.value))
        edit.setMinimumWidth(PREFERENCES_FIELD_WIDTH_PX)
        edit.editingFinished.connect(lambda name=name: self._edited(name))
        return edit

    def _material_names(self) -> list[str]:
        return [material.name for material in self.model.materials.all()]

    # --- reading the boxes ---------------------------------------------------------------------------

    def _text_of(self, name: str) -> str:
        editor = self._editors[name]
        return editor.currentText() if isinstance(editor, QComboBox) else editor.text()

    def _show(self, name: str) -> None:
        """Put the stored value into the box (blocking its signals)."""
        editor = self._editors[name]
        text = value_text(self.preferences.row(name).value)
        editor.blockSignals(True)
        if isinstance(editor, QComboBox):
            if editor.findText(text) < 0:
                editor.addItem(text)
            editor.setCurrentText(text)
        else:
            editor.setText(text)
            editor.setStyleSheet("")
        editor.blockSignals(False)

    def _edited(self, name: str) -> None:
        editor = self._editors[name]
        if not isinstance(editor, QComboBox) and self._text_of(name).strip() == value_text(self.preferences.row(name).value):
            editor.setStyleSheet("")  # nothing typed that differs; also clears an old red mark
            return
        error = self.preferences.set_text(name, self._text_of(name))
        if error:
            editor.setStyleSheet(PREFERENCES_ERROR_STYLE)
            self._message.setText(f"{name}: {error}")
            return
        editor.setStyleSheet("")
        self._save()
        self._show(name)
        self._refresh_marks()

    def _reset(self, name: str) -> None:
        self.preferences.reset(name)
        self._show(name)
        self._message.setText("")
        self._save()
        self._refresh_marks()

    def _save(self) -> None:
        try:
            self.preferences.save()
            self._message.setText("")
        except OSError as error:
            self._message.setText(f"The file {self.preferences.path} could not be written: {error}")

    # --- marks ----------------------------------------------------------------------------------------

    def _refresh_marks(self) -> None:
        for _heading, rows in self.preferences.groups():
            for row in rows:
                name = row.convention.name
                changed = row.changed
                self._resets[name].setEnabled(changed)
                self._look(name, changed)
                tip = f"Default: {value_text(row.default)}"
                self._editors[name].setToolTip(tip)
                self._resets[name].setToolTip(f"Back to the default value ({value_text(row.default)})")
        self._restart.setVisible(self.preferences.needs_restart())

    def _look(self, name: str, changed: bool) -> None:
        """Grey while the value is the default, the normal colour once it differs (like the untouched fields of the forms)."""
        editor = self._editors[name]
        if changed:
            editor.setPalette(QPalette())
            return
        palette = QPalette(editor.palette())
        for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
            palette.setColor(role, self._dim)
        editor.setPalette(palette)

    def _menu(self, name: str, point: QPoint) -> None:
        """Right click on a box: reset this value to its default."""
        editor = self._editors[name]
        menu = QMenu(editor)
        action = menu.addAction(RESET_TO_DEFAULT_TEXT)
        action.setEnabled(self.preferences.row(name).changed)
        if menu.exec(editor.mapToGlobal(point)) is action:
            self._reset(name)

    def _show_fixed(self) -> None:
        FixedValuesDialog(self, self.preferences.fixed_text()).exec()
