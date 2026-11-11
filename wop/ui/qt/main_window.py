"""The main window: flow column, picture, input form and messages."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QGridLayout, QLabel, QListWidgetItem, QMainWindow, QMenu, QPlainTextEdit, QPushButton, QScrollArea, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from ..app_model import AppModel
from ..setup_form import SETUP_TITLE
from ..svg_preview import block_color
from .centre_view import CentreView
from .contour_panel import ContourPanel
from .flow_delegate import FlowList, KIND_BLOCK, KIND_CONTOUR, KIND_HEADER, KIND_SETUP, ROLE_COLOR, ROLE_KIND, ROLE_NAME, ROLE_NOTE, ROLE_TITLE, ROLE_WARN
from .form_panel import FormPanel
from .panel_splitter import PanelSplitter, StackSplitter
from ...post.post_constants import WOP_VERSION_TEXT
from .qt_constants import APP_NAME, ERROR_LOG_CHECK_MS, FLOW_COLLISION_NOTE, FLOW_PANEL_MIN_WIDTH_PX, FLOW_PANEL_WIDTH_PX, FORM_PANEL_MIN_WIDTH_PX, FORM_PANEL_WIDTH_PX, MESSAGE_PANEL_HEIGHT_PX, MESSAGE_PANEL_MIN_HEIGHT_PX, SHOW_NEUTRAL_CODE_MENU, SPLITTER_PICTURE_STRETCH, STATUS_MESSAGE_MS, WARNING_MARK, WINDOW_HEIGHT_PX, WINDOW_WIDTH_PX, WORK_NOTE_SAVED_PART, WORK_NOTES, WORK_TEXTS
from .theme_qt import color_set_from_palette
from .window_parts.menus import MenusMixin
from .window_parts.form import FormMixin
from .window_parts.actions import ActionsMixin
from .window_parts.files import FilesMixin
from .window_parts.helpers import (  # noqa: F401  (names other modules import from here)
    CONTOURS_HEADER,
    CONTOUR_MENU_TEXT,
    GCODE_ENCODING,
    GCODE_FILTER,
    LIBRARY_FILTER,
    MODE_BLOCK,
    MODE_CONTOUR,
    MODE_SETUP,
    MODE_TOOLS,
    MODE_WORKHOLDING,
    PROJECT_FILTER,
)


class MainWindow(
    MenusMixin, FormMixin, ActionsMixin, FilesMixin, QMainWindow,
):
    def __init__(self, model: AppModel, error_log=None) -> None:
        super().__init__()
        self.model = model
        self._error_log = error_log  # tells the user when an error was written to the log (wop/ui/error_log.py)
        self._errors_told = 0
        self._editing = False  # True while the form itself causes the change
        self._notice = ""  # the last notice (a refused value, an import note), shown in the messages box
        self._ready = False  # the window follows palette changes only once it is built
        self._mode = MODE_SETUP  # what the right panel shows
        self._contour_rows: dict[int, str] = {}  # flow list row -> contour id
        self.resize(WINDOW_WIDTH_PX, WINDOW_HEIGHT_PX)
        self._restore_geometry()
        self._build_menu()
        self._build_body()
        self.model.set_colors(color_set_from_palette(self.palette()))  # pictures in the colours of the theme
        self._work_label = QLabel()  # what the background work is doing (planning, checking), right in the status bar
        self.statusBar().addPermanentWidget(self._work_label)
        self.model.subscribe(self._model_changed)
        self.model.subscribe_results(self._results_arrived)
        self._model_changed()
        self._ready = True
        if self._error_log is not None:  # look for new errors a moment after they happened
            self._error_timer = QTimer(self)
            self._error_timer.timeout.connect(self._check_error_log)
            self._error_timer.start(ERROR_LOG_CHECK_MS)

    def _apply_start_sizes(self) -> None:
        """The columns as the user left them; at the first start both side panels are open. The message box opens at its usual height."""
        self.centre_split.setSizes([max(self.centre_split.height() - MESSAGE_PANEL_HEIGHT_PX, 1), MESSAGE_PANEL_HEIGHT_PX])
        saved = self.model.app_settings.panel_sizes
        if len(saved) == self.splitter.count() and sum(saved) > 0:
            self.splitter.setSizes(list(saved))
            return
        handles = 2 * self.splitter.handleWidth()
        room = self.width() - handles - self.splitter.widget(1).minimumSizeHint().width()  # what the two panels may take and leave the middle usable
        flow, form = FLOW_PANEL_WIDTH_PX, FORM_PANEL_WIDTH_PX
        too_much = flow + form - room  # a narrow window: the panels open narrower (the form first), never below their smallest
        form -= min(max(too_much, 0), form - FORM_PANEL_MIN_WIDTH_PX)
        flow -= min(max(flow + form - room, 0), flow - FLOW_PANEL_MIN_WIDTH_PX)
        self.splitter.setSizes([flow, max(self.width() - handles - flow - form, 1), form])

    def _build_body(self) -> None:
        left, middle, right = self._build_flow_column(), self._build_centre_column(), self._build_form_column()
        self.splitter = PanelSplitter()
        for part in (left, middle, right):
            self.splitter.addWidget(part)
        self.splitter.setStretchFactor(1, SPLITTER_PICTURE_STRETCH)
        self.setCentralWidget(self.splitter)
        QTimer.singleShot(0, self._apply_start_sizes)  # both side panels start open

    def _build_flow_column(self) -> QWidget:
        """Left: the list of blocks with its buttons."""
        self.flow = FlowList()
        self.flow.currentRowChanged.connect(self._flow_selected)
        self.flow.clicked.connect(self._flow_clicked)
        self.flow.doubleClicked.connect(lambda _index: self._open_right())
        self.flow.itemChanged.connect(self._flow_ticked)
        if SHOW_NEUTRAL_CODE_MENU:
            self.flow.setContextMenuPolicy(Qt.CustomContextMenu)
            self.flow.customContextMenuRequested.connect(self._flow_menu)
        self.tick_all = QCheckBox("Tick all blocks for export")
        self.tick_all.setTristate(True)
        self.tick_all.clicked.connect(self._tick_all_clicked)
        add_button = QToolButton()
        add_button.setText("Add block")
        add_button.setPopupMode(QToolButton.InstantPopup)
        self._block_menu = QMenu(add_button)
        self._fill_block_menu()
        add_button.setMenu(self._block_menu)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self._delete)
        up_button = QPushButton("Up")
        up_button.clicked.connect(lambda: self._move(-1))
        down_button = QPushButton("Down")
        down_button.clicked.connect(lambda: self._move(1))
        export_button = QPushButton("Export selected...")
        export_button.setToolTip("Show and export only the blocks with a tick")
        export_button.clicked.connect(self._export_selected)
        # two rows keep the panel narrow: Up sits over Down
        buttons = QGridLayout()
        buttons.addWidget(add_button, 0, 0)
        buttons.addWidget(delete_button, 0, 1)
        buttons.addWidget(up_button, 0, 2)
        buttons.addWidget(export_button, 1, 0, 1, 2)
        buttons.addWidget(down_button, 1, 2)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.tick_all)
        left_layout.addWidget(self.flow)
        left_layout.addLayout(buttons)
        left.setMinimumWidth(FLOW_PANEL_MIN_WIDTH_PX)
        return left

    def _build_centre_column(self) -> QWidget:
        """Middle: the picture and the messages."""
        self.centre = CentreView(self.model)  # 2D picture or 3D view, with the toggle
        self.centre.tools_view.notice.connect(self._say)
        self.centre.workholding_view.notice.connect(self._say)
        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMinimumHeight(MESSAGE_PANEL_MIN_HEIGHT_PX)
        self.centre_split = StackSplitter()  # the border between the picture and the messages can be dragged
        self.centre_split.addWidget(self.centre)
        self.centre_split.addWidget(self.messages)
        self.centre_split.setStretchFactor(0, SPLITTER_PICTURE_STRETCH)  # a larger window gives its room to the picture
        self.centre_split.setStretchFactor(1, 0)
        return self.centre_split

    def _build_form_column(self) -> QWidget:
        """Right: the form of the block (or the contour panel)."""
        self.form_title = QLabel()
        self.form_title.setStyleSheet("font-weight: bold")
        self.setup_info = QLabel()
        self.setup_info.setWordWrap(True)
        self.form = FormPanel()
        self.form.edited.connect(self._value_edited)
        self.form.rejected.connect(self._say)
        self.form.reset_requested.connect(self._reset_field)
        self.form.action_requested.connect(self._form_action)
        self.form.new_requested.connect(self._new_material)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.contour_panel = ContourPanel(self.model)
        self.contour_panel.sketch_requested.connect(self._sketch_for_contour)
        self.right_stack = QStackedWidget()
        block_page = QWidget()  # the block form
        block_layout = QVBoxLayout(block_page)
        block_layout.setContentsMargins(0, 0, 0, 0)
        block_layout.addWidget(scroll, 1)
        self.right_stack.addWidget(block_page)
        self.right_stack.addWidget(self.contour_panel)
        right_layout.addWidget(self.form_title)
        right_layout.addWidget(self.right_stack)
        right_layout.addWidget(self.setup_info)
        right.setMinimumWidth(FORM_PANEL_MIN_WIDTH_PX)
        return right

    def _model_changed(self) -> None:
        self.setWindowTitle(f"{self.model.title()} - {APP_NAME} {WOP_VERSION_TEXT}")  # the version is in the title, for a report of a problem
        self._fill_flow()
        self._undo_action.setEnabled(self.model.can_undo)
        self._redo_action.setEnabled(self.model.can_redo)
        self._redraw()
        self._notice = ""  # a change of the project ends the last notice
        self._fill_messages()
        told = self.model.take_notice()  # for example: the machine of the list replaced an older copy in the project
        if told:
            self._say(told)
        if not self._editing:
            self._show_form()
        self._show_work()

    def _results_arrived(self) -> None:
        """The plan or the check made in the background is there: the picture, the flow list and the messages follow; the form
        stays as it is (it may be being typed into); only its greyed fields show what the plan worked out (the Start Z of auto)."""
        self._fill_flow()
        self._redraw()
        self._fill_messages()
        self._show_work()
        if self._mode == MODE_BLOCK and self.model.selected_block() is not None:
            self.form.show_greyed(self.model.shown_block(self.model.selected))

    def _show_work(self) -> None:
        working = self.model.analysis.working
        self._work_label.setText(WORK_TEXTS.get(working, ""))

    def _fill_flow(self) -> None:
        """The flow list: Setup first, then the blocks with a dot in their colour in the picture."""
        flagged = {f.block_index for f in self.model.analysis.findings}
        if self.model.selected is not None:
            self._mode = MODE_BLOCK  # a selected block is what the right panel shows
        elif self.model.selected_contour is not None:
            self._mode = MODE_CONTOUR
        elif self.model.tools_view:
            self._mode = MODE_TOOLS
        elif self.model.workholding_view:
            self._mode = MODE_WORKHOLDING
        elif self._mode in (MODE_BLOCK, MODE_CONTOUR, MODE_TOOLS, MODE_WORKHOLDING):
            self._mode = MODE_SETUP
        self._fill_block_menu()
        self.flow.blockSignals(True)
        self.flow.clear()
        self.flow.addItem(self._card(KIND_SETUP, SETUP_TITLE))
        for index, block in enumerate(self.model.blocks):
            note = self.model.block_note(index)
            warn = index in flagged
            if warn:
                note = f"{WARNING_MARK} {note or FLOW_COLLISION_NOTE}"
            label = block.display_label()
            name = block.title if block.title and block.title != label else ""
            item = self._card(KIND_BLOCK, f"{index + 1}: {label}", name, note, warn, block_color(self.model.colors, index))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if self.model.is_ticked(index) else Qt.Unchecked)
            self.flow.addItem(item)
        self._contour_rows = {}
        if self.model.program.contours:
            header = self._card(KIND_HEADER, CONTOURS_HEADER)
            header.setFlags(Qt.NoItemFlags)  # a heading, not an entry
            self.flow.addItem(header)
        for contour in self.model.program.contours:
            users = len(self.model.contour_users(contour.contour_id))
            note = f"{users} block{'s' if users != 1 else ''}"
            if not contour.is_valid:
                note += f" - {contour.error or 'not valid'}"
            self._contour_rows[self.flow.count()] = contour.contour_id
            self.flow.addItem(self._card(KIND_CONTOUR, contour.name, "", note, not contour.is_valid))
        contour_row = next((r for r, i in self._contour_rows.items() if i == self.model.selected_contour), -1)
        rows = {
            MODE_SETUP: 0, MODE_BLOCK: (self.model.selected or 0) + 1, MODE_CONTOUR: contour_row, MODE_TOOLS: -1,
            MODE_WORKHOLDING: -1,
        }
        self.flow.setCurrentRow(rows[self._mode])
        self.flow.blockSignals(False)
        state = self.model.tick_state()
        self.tick_all.blockSignals(True)
        self.tick_all.setCheckState({"all": Qt.Checked, "none": Qt.Unchecked, "some": Qt.PartiallyChecked}[state])
        self.tick_all.blockSignals(False)

    @staticmethod
    def _card(kind: str, title: str, name: str = "", note: str = "", warn: bool = False, color: str = "") -> QListWidgetItem:
        """A flow list entry; the delegate draws it from these roles."""
        item = QListWidgetItem(" - ".join(part for part in (title, name, note) if part))  # plain text, also the tooltip
        item.setToolTip(item.text())
        item.setData(ROLE_KIND, kind)
        item.setData(ROLE_TITLE, title)
        item.setData(ROLE_NAME, name)
        item.setData(ROLE_NOTE, note)
        item.setData(ROLE_WARN, warn)
        item.setData(ROLE_COLOR, color)
        return item

    def _redraw(self) -> None:
        self.centre.redraw()

    def _fill_messages(self) -> None:
        analysis = self.model.analysis
        lines = [f"NOTICE: {self._notice}"] if self._notice else []
        if analysis.working:
            lines.append(WORK_NOTE_SAVED_PART if analysis.plan is None and analysis.preview is not None else WORK_NOTES[analysis.working])
        if analysis.error:
            lines.append(f"PROBLEM: {analysis.error}")
        if not analysis.error and not analysis.checked and not analysis.working:
            lines.append("NOT CHECKED: collisions and power were not checked since the last change (Check > Verify now, F5).")
        lines += [f"note: {message}" for message in analysis.messages]
        lines += [f"COLLISION: {f.message} - {f.remedy}" for f in analysis.findings]
        self.messages.setPlainText("\n".join(lines) if lines else "No problems found.")

    def _check_error_log(self) -> None:
        """An error that was only printed (a handler failed) is not silent: tell the user where to look."""
        if self._error_log is not None and self._error_log.errors > self._errors_told:
            self._errors_told = self._error_log.errors
            self._say(f"An internal error happened (details in {self._error_log.path}). Save your project under another name and restart WOP.")

    def _say(self, text: str) -> None:
        """A short notice: in the status bar and at the top of the messages box, where it is seen."""
        self.statusBar().showMessage(text, STATUS_MESSAGE_MS)
        self._notice = text
        self._fill_messages()

    def _flow_selected(self, row: int) -> None:
        if row < 0:
            return
        if row == 0:  # the Setup entry
            self._mode = MODE_SETUP
            self.model.select(None)
        elif row in self._contour_rows:
            self._mode = MODE_CONTOUR
            self.model.select_contour(self._contour_rows[row])
        elif row <= len(self.model.blocks):
            self._mode = MODE_BLOCK
            self.model.select(row - 1)

    def _flow_clicked(self, _index) -> None:
        """Choosing a contour opens the form at once; choosing a block or Setup does not (double click does)."""
        if self.flow.currentRow() in self._contour_rows:
            self._open_right()

    def _flow_ticked(self, item: QListWidgetItem) -> None:
        """A checkbox of the flow list was clicked (the Setup entry has none)."""
        row = self.flow.row(item)
        if 1 <= row <= len(self.model.blocks):
            ticked = item.checkState() == Qt.Checked
            # Later: this signal comes from inside the item, and the model change rebuilds the list.
            QTimer.singleShot(0, lambda: self.model.set_ticked(row - 1, ticked))

    def _tick_all_clicked(self) -> None:
        self.model.set_all_ticked(self.model.tick_state() != "all")

    def event(self, event) -> bool:
        """When the window gets the focus back: libraries and machines may have been changed by someone else."""
        if self._ready and event.type() == QEvent.WindowActivate:
            note = self.model.reload_changed_files()
            if note:
                self._say(note)
        return super().event(event)

    def changeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        """The OS theme changed: the pictures get the colours that fit it."""
        if self._ready and event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange):
            self.model.set_colors(color_set_from_palette(self.palette()))  # does nothing if the set is the same
            self._show_form()  # the dimmed text colour depends on the theme too
        super().changeEvent(event)
