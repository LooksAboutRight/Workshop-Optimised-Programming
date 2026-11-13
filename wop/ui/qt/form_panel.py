"""Turns a list of FieldSpec (see ui/block_forms.py) into input widgets."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QWidget,
)

from ...core.program_model.units import XInputMode
from ..block_forms import (
    NEW_MATERIAL,
    FieldKind,
    FieldSpec,
    FormError,
    end_to_length,
    from_display,
    get_value,
    length_to_end,
    TAPER_RISE_CHOICE,
    parse_text,
    spec_scale,
    spec_unit,
    set_value,
    taper_from_display,
    taper_label,
    taper_to_display,
    to_display,
)
from .. import app_constants
from ..display_units import is_inch
from ..ui_constants import RESET_TO_DEFAULT_TEXT
from .number_boxes import NumberBox, WholeNumberBox
from .style_preview import StyleCombo
from .qt_constants import SPIN_DECIMALS, SPIN_DECIMALS_INCH, SPIN_LIMIT, SPIN_STEP, SPIN_STEP_INCH, TEXT_EDIT_DELAY_MS


class FormPanel(QWidget):
    """One row per field. Emits `edited(spec, value)` when the user changes a value.

    The value is already converted to what the model stores (a diameter typed in
    diameter mode arrives as a radius). A bad entry emits `rejected(message)`.
    """

    edited = Signal(object, object)
    rejected = Signal(str)
    reset_requested = Signal(object)  # the spec of a field whose "Reset to default" was chosen
    new_requested = Signal(object)  # the spec of a list field whose "New..." entry was chosen
    action_requested = Signal(object)  # the spec of a BUTTON field that was clicked

    def __init__(self) -> None:
        super().__init__()
        self._layout = QFormLayout(self)
        self._layout.setRowWrapPolicy(QFormLayout.WrapLongRows)  # a long label goes above its field instead of clipping
        self._layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._x_mode = XInputMode.DIAMETER
        self._loading = False
        self._timers: list[QTimer] = []
        self._is_touched: Callable[[tuple[str, ...]], bool] | None = None
        self._dim_color: QColor | None = None
        self._widgets: dict[tuple[str, ...], QWidget] = {}
        self._specs: dict[tuple[str, ...], FieldSpec] = {}
        self._obj: Any = None  # the object shown, kept up to date with every edit (the Abs./Rel. rows read the start from it)
        self._relative_shows: list[Callable[[], None]] = []  # redraw the Abs./Rel. rows after an edit
        self._taper_as_rise: bool | None = None  # how tapers are shown; kept while the panel lives, first from the preference TAPER_INPUT

    def clear(self) -> None:
        for timer in self._timers:
            timer.stop()
        self._timers.clear()
        self._widgets.clear()
        self._relative_shows.clear()
        while self._layout.rowCount():
            self._layout.removeRow(0)

    def set_form(
        self,
        obj: Any,
        specs: list[FieldSpec],
        x_mode: XInputMode,
        is_touched: Callable[[tuple[str, ...]], bool] | None = None,
        dim_color: QColor | None = None,
    ) -> None:
        """Show the values of obj. Call again after a change that alters the choices.

        With `is_touched` (field path -> bool) the fields the user has not touched are shown in `dim_color`
        (requirement U6) and get "Reset to default" in their context menu; without it all fields look normal.
        """
        focus = self.focusWidget()
        focused = None
        if focus is not None:
            focused = next((path for path, w in self._widgets.items() if w is focus or w.isAncestorOf(focus)), None)
        self.clear()
        self._obj = obj
        self._specs = {spec.path: spec for spec in specs}
        self._x_mode = x_mode
        self._is_touched = is_touched
        self._dim_color = dim_color
        self._loading = True
        try:
            index = 0
            while index < len(specs):
                spec = specs[index]
                following = specs[index + 1] if index + 1 < len(specs) else None
                index += 1
                if spec.heading:
                    self._add_heading(spec.heading)
                if spec.kind is FieldKind.BUTTON:
                    button = QPushButton(spec.button_text)
                    button.clicked.connect(lambda _checked=False, s=spec: self.action_requested.emit(s))
                    self._layout.addRow("", button)
                    continue
                model_value = get_value(obj, spec.path)
                if spec.relative_to and spec.kind is FieldKind.FLOAT:
                    self._add_relative_row(spec)
                    continue
                if spec.is_radius and spec.kind is FieldKind.FLOAT:
                    self._add_radius_row(spec, model_value)
                    continue
                if spec.is_taper and spec.kind is FieldKind.FLOAT:
                    self._add_taper_row(spec, model_value)
                    continue
                value = to_display(spec, model_value, x_mode)
                widget = self._widget_for(spec, value)
                self._decorate(spec, widget)
                widget.setEnabled(spec.enabled)
                label = spec.display_label(x_mode)
                if spec.kind is FieldKind.OPTIONAL_FLOAT and spec.unit:  # a text field has no unit suffix
                    label += f" ({spec_unit(spec)})"
                if following is not None and following.same_line and not following.heading:
                    index += 1  # the next field shares this line: widget, its small label, its widget
                    second = self._widget_for(following, to_display(following, get_value(obj, following.path), x_mode))
                    self._decorate(following, second)
                    second.setEnabled(following.enabled)
                    row = QWidget()
                    layout = QHBoxLayout(row)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.addWidget(widget)
                    layout.addWidget(QLabel(following.display_label(x_mode)))
                    layout.addWidget(second, 1)
                    self._layout.addRow(label, row)
                    continue
                self._layout.addRow(label, widget)
                if spec.note:
                    note = QLabel(spec.note)
                    note.setWordWrap(True)
                    self._layout.addRow(note)
        finally:
            self._loading = False
        if focused in self._widgets:  # a rebuilt form keeps the cursor in the field it was in
            self._widgets[focused].setFocus()

    def show_greyed(self, obj: Any) -> None:
        """The values of `obj` in the greyed number fields (the Start Z auto worked out, when a plan arrives), without rebuilding the form:
        a field being typed into stays as it is."""
        if self._obj is None:
            return
        self._loading = True
        try:
            for path, widget in self._widgets.items():
                spec = self._specs.get(path)
                if spec is None or widget.isEnabled() or not isinstance(widget, NumberBox):
                    continue
                value = get_value(obj, path)
                widget.setValue(float(to_display(spec, value, self._x_mode)))
                self._obj = set_value(self._obj, path, value)
        finally:
            self._loading = False

    def _add_heading(self, text: str) -> None:
        """A section heading; a horizontal divider line goes above it unless it is the first row."""
        if self._layout.rowCount():
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            self._layout.addRow(line)
        heading = QLabel(text)
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        self._layout.addRow(heading)

    def _add_radius_row(self, spec: FieldSpec, radius: float) -> None:
        """An X input with its own Dia./Rad. button (requirement B7).

        The button changes only this input, and only what is shown. The program
        always keeps the radius.
        """
        state = {"mode": self._x_mode, "radius": radius}
        box = self._number_box(spec)
        label = QLabel(spec.display_label(state["mode"]))
        button = QToolButton()

        def show() -> None:
            box.blockSignals(True)
            box.setValue(float(to_display(spec, state["radius"], state["mode"])))
            box.blockSignals(False)
            label.setText(spec.display_label(state["mode"]))
            button.setText("Dia." if state["mode"] is XInputMode.DIAMETER else "Rad.")

        def typed(value: float) -> None:
            state["radius"] = from_display(spec, value, state["mode"])
            if not self._loading:
                try:
                    self._obj = set_value(self._obj, spec.path, state["radius"])
                except ValueError:
                    pass  # the window shows the reason when it takes the value
                self.edited.emit(spec, state["radius"])
                self._show_touched(spec)
                for show in self._relative_shows:
                    show()

        def toggle() -> None:
            state["mode"] = (
                XInputMode.RADIUS if state["mode"] is XInputMode.DIAMETER else XInputMode.DIAMETER
            )
            show()

        box.valueChanged.connect(typed)
        button.clicked.connect(lambda _checked=False: toggle())
        show()
        self._decorate(spec, box)
        box.setEnabled(spec.enabled)
        button.setEnabled(spec.enabled)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(box)
        layout.addWidget(button)
        self._layout.addRow(label, row)

    def _add_taper_row(self, spec: FieldSpec, angle: float) -> None:
        """A taper with its own deg / per 100 mm button: the included angle, or the rise of the diameter per 100 mm. The label says which.
        The button changes only what is shown (in every taper of this panel, until the window closes); the program keeps the angle."""
        if self._taper_as_rise is None:
            self._taper_as_rise = app_constants.TAPER_INPUT == TAPER_RISE_CHOICE
        state = {"angle": angle}
        box = NumberBox()
        box.setDecimals(SPIN_DECIMALS)
        box.setRange(-SPIN_LIMIT, SPIN_LIMIT)
        box.setSingleStep(SPIN_STEP)
        box.setKeyboardTracking(False)
        label = QLabel()
        button = QToolButton()

        def show() -> None:
            text, unit = taper_label(bool(self._taper_as_rise))
            box.blockSignals(True)
            box.setSuffix(f" {unit}")
            box.setValue(taper_to_display(state["angle"], bool(self._taper_as_rise)))
            box.blockSignals(False)
            label.setText(text)
            button.setText("/100" if self._taper_as_rise else "deg")

        def typed(value: float) -> None:
            state["angle"] = taper_from_display(value, bool(self._taper_as_rise))
            self._emit(spec, state["angle"])

        def toggle() -> None:
            self._taper_as_rise = not self._taper_as_rise
            show()

        box.valueChanged.connect(typed)
        button.clicked.connect(lambda _checked=False: toggle())
        show()
        self._decorate(spec, box)
        box.setEnabled(spec.enabled)
        button.setEnabled(spec.enabled)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(box)
        layout.addWidget(button)
        self._layout.addRow(label, row)
        if spec.note:
            note = QLabel(spec.note)
            note.setWordWrap(True)
            self._layout.addRow(note)

    def _add_relative_row(self, spec: FieldSpec) -> None:
        """An end position with its own Abs./Rel. button: the absolute Z, or the length from the start field.

        The button changes only what is shown in this input. The program always keeps the absolute Z.
        """
        state = {"relative": False}
        box = self._number_box(spec)
        label = QLabel(spec.label)
        button = QToolButton()

        def start() -> float:
            return float(get_value(self._obj, (spec.relative_to,)))

        def show() -> None:
            end = float(get_value(self._obj, spec.path))
            box.blockSignals(True)
            box.setValue((end_to_length(start(), end) if state["relative"] else end) * spec_scale(spec))
            box.blockSignals(False)
            label.setText(spec.relative_label if state["relative"] else spec.label)
            button.setText("Rel." if state["relative"] else "Abs.")

        def typed(value: float) -> None:
            if not self._loading:
                stored = value / spec_scale(spec)
                self._emit(spec, length_to_end(start(), stored) if state["relative"] else stored, shown=False)

        def toggle() -> None:
            state["relative"] = not state["relative"]
            show()

        box.valueChanged.connect(typed)
        button.clicked.connect(lambda _checked=False: toggle())
        self._relative_shows.append(show)
        show()
        self._decorate(spec, box)
        box.setEnabled(spec.enabled)
        button.setEnabled(spec.enabled)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(box)
        layout.addWidget(button)
        self._layout.addRow(label, row)

    # --- one widget per kind ------------------------------------------------------

    def _emit(self, spec: FieldSpec, value: Any, shown: bool = True) -> None:
        """Report an edit. `shown`: the value is as displayed (diameter, inches); False: it already is what the model stores."""
        if not self._loading:
            model_value = from_display(spec, value, self._x_mode) if shown else value
            try:
                self._obj = set_value(self._obj, spec.path, model_value)  # stays current for the Abs./Rel. rows
            except ValueError:
                pass  # the window shows the reason when it takes the value
            self.edited.emit(spec, model_value)
            self._show_touched(spec)
            for show in self._relative_shows:
                show()

    # --- untouched fields (U6) -------------------------------------------------------

    def _decorate(self, spec: FieldSpec, widget: QWidget) -> None:
        """Remember the widget of a field; dim it when untouched and give it the reset menu."""
        self._widgets[spec.path] = widget
        if self._is_touched is None:
            return
        widget.setContextMenuPolicy(Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(lambda point, s=spec, w=widget: self._menu(s, w, point))
        self._show_touched(spec, self._is_touched(spec.path))

    def _show_touched(self, spec: FieldSpec, touched: bool = True) -> None:
        widget = self._widgets.get(spec.path)
        if widget is None or self._dim_color is None:
            return
        if touched:
            widget.setPalette(QPalette())  # back to the colours of the window
            return
        palette = QPalette(widget.palette())
        for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
            palette.setColor(role, self._dim_color)
        widget.setPalette(palette)

    def _menu(self, spec: FieldSpec, widget: QWidget, point: QPoint) -> None:
        menu = QMenu(widget)
        action = menu.addAction(RESET_TO_DEFAULT_TEXT)
        if menu.exec(widget.mapToGlobal(point)) is action:
            self.reset_requested.emit(spec)

    def _number_box(self, spec: FieldSpec) -> NumberBox:
        """A number field of the unit the window shows (inches: finer decimals and step, limits and unit converted)."""
        box = NumberBox()
        scale = spec_scale(spec)
        box.setDecimals(SPIN_DECIMALS_INCH if scale < 1 else SPIN_DECIMALS)
        low = -SPIN_LIMIT if spec.minimum is None else spec.minimum * scale
        high = SPIN_LIMIT if spec.maximum is None else spec.maximum * scale
        box.setRange(low, high)
        box.setSingleStep(SPIN_STEP_INCH if scale < 1 else SPIN_STEP)
        box.setKeyboardTracking(False)
        unit = spec_unit(spec)
        box.setSuffix(f" {unit}" if unit else "")
        return box

    def _widget_for(self, spec: FieldSpec, value: Any) -> QWidget:
        """The input widget for one field by its kind, filled with `value`; an edit is reported through `_emit`."""
        kind = spec.kind
        if kind is FieldKind.FLOAT:
            box = self._number_box(spec)
            box.setValue(float(value))
            box.valueChanged.connect(lambda v, s=spec: self._emit(s, v))
            return box
        if kind is FieldKind.INT:
            box = WholeNumberBox()
            box.setRange(-SPIN_LIMIT if spec.minimum is None else int(spec.minimum), SPIN_LIMIT if spec.maximum is None else int(spec.maximum))
            box.setKeyboardTracking(False)
            box.setValue(int(value))
            box.valueChanged.connect(lambda v, s=spec: self._emit(s, v))
            return box
        if kind is FieldKind.OPTIONAL_FLOAT:
            line = QLineEdit("" if value is None else f"{value:.{SPIN_DECIMALS_INCH}g}" if is_inch() else f"{value:g}")
            line.setPlaceholderText("not set")
            line.editingFinished.connect(lambda s=spec, w=line: self._from_text(s, w.text()))
            return line
        if kind is FieldKind.TEXT:
            line = QLineEdit(str(value))
            line.editingFinished.connect(lambda s=spec, w=line: self._emit(s, w.text()))
            return line
        if kind is FieldKind.MULTILINE:
            edit = QPlainTextEdit(str(value))
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(TEXT_EDIT_DELAY_MS)
            timer.timeout.connect(lambda s=spec, w=edit: self._emit(s, w.toPlainText()))
            edit.textChanged.connect(lambda: timer.start())
            self._timers.append(timer)
            return edit
        if kind is FieldKind.BOOL:
            check = QCheckBox()
            check.setChecked(bool(value))
            check.toggled.connect(lambda v, s=spec: self._emit(s, v))
            return check
        combo = StyleCombo(spec.preview) if spec.preview else QComboBox()
        values = [choice.value for choice in spec.choices]
        labels = [choice.label for choice in spec.choices]
        if value not in values:  # for example a material of a loaded project that is not in the list
            values.insert(0, value)
            labels.insert(0, str(value))
        combo.addItems(labels)
        if spec.preview:
            for position, item_value in enumerate(values):
                combo.setItemData(position, item_value)  # the pictures of the hovered entry are found by its key
        combo.setCurrentIndex(values.index(value))
        combo.currentIndexChanged.connect(lambda index, s=spec, v=values: self._chosen(s, v, index))
        return combo

    def _chosen(self, spec: FieldSpec, values: list, index: int) -> None:
        if index < 0 or self._loading:
            return
        if values[index] == NEW_MATERIAL:
            self.new_requested.emit(spec)
        else:
            self._emit(spec, values[index])

    def _from_text(self, spec: FieldSpec, text: str) -> None:
        try:
            self._emit(spec, parse_text(spec, text))
        except FormError as error:
            self.rejected.emit(str(error))
