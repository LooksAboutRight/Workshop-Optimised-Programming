"""The pages of the post editor: the widgets of each page."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget

from ...post_editor_model import PostEditorModel
from ..qt_constants import POST_CHOOSER_MIN_CHARACTERS, POST_DISCLAIMER, POST_ERROR_COLOR, POST_HINT_COLOR, POST_OWN_NOTE, POST_PAGE_LIST_WIDTH_PX, POST_PREVIEW_DELAY_MS, POST_SAMPLE_MIN_HEIGHT_PX, POST_TEMPLATE_MIN_HEIGHT_PX
from ..small_screens import scrolling
from .helpers import CHOICES, SPIN_MAX


class PagesMixin:
    """The pages of the post editor: the widgets of each page. (A part of PostEditorDialog: it uses the attributes that PostEditorDialog.__init__ sets.)"""

    def _build(self) -> None:
        self._page_problem_labels: dict[str, QLabel] = {}  # page key -> the red text with what is wrong on the page
        self._posts = QComboBox()
        self._posts.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)  # a long name of a post must not widen the dialog
        self._posts.setMinimumContentsLength(POST_CHOOSER_MIN_CHARACTERS)
        self._posts.currentIndexChanged.connect(self._post_chosen)
        top = QHBoxLayout()
        top.addWidget(QLabel("Post:"))
        top.addWidget(self._posts, 1)
        self._buttons: dict[str, QPushButton] = {}
        for key, text, handler in (
            ("new", "New", self._new),
            ("save", "Save", self._save),
            ("copy", "Save as copy...", self._save_as),
            ("import", "Import...", self._import),
            ("delete", "Delete", self._delete),
            ("folder", "Folder", self._open_folder),
        ):
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, h=handler: h())
            top.addWidget(button)
            self._buttons[key] = button
        top.addSpacing(16)
        top.addWidget(QLabel("Sample X:"))
        self._x_mode = QComboBox()
        self._x_mode.addItems(["diameter", "radius"])
        self._x_mode.currentIndexChanged.connect(lambda _index: self._show_preview())
        top.addWidget(self._x_mode)

        self._pages = QListWidget()
        self._pages.setMaximumWidth(POST_PAGE_LIST_WIDTH_PX)
        self._pages.currentRowChanged.connect(self._page_chosen)
        self._stack = QStackedWidget()
        for page in (self._build_post_page(), self._build_settings_page(), self._build_codes_page(), self._build_modal_groups_page(), self._build_concept_page()):
            self._stack.addWidget(scrolling(page))  # a page scrolls when the window is small: the tallest page must not set the smallest size of the dialog
        splitter = QSplitter()
        splitter.addWidget(self._build_page_buttons())
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(1, 1)

        self._message = QLabel("")
        self._message.setWordWrap(True)
        disclaimer = QLabel(POST_DISCLAIMER)
        disclaimer.setWordWrap(True)
        font = disclaimer.font()
        font.setBold(True)
        disclaimer.setFont(font)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addWidget(disclaimer, 1)
        bottom.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._message)
        layout.addLayout(bottom)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(POST_PREVIEW_DELAY_MS)
        self._preview_timer.timeout.connect(self._template_edited)

    def _problem_label(self, key: str) -> QLabel:
        label = QLabel("")
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {POST_ERROR_COLOR}")
        self._page_problem_labels[key] = label
        return label

    def _build_post_page(self) -> QWidget:
        page = QWidget()
        self._id_label = QLabel("")
        self._name = QLineEdit()
        self._name.textEdited.connect(lambda text: self._edit(lambda: self.editor.set_meta("name", text)))
        self._description = QLineEdit()
        self._description.textEdited.connect(lambda text: self._edit(lambda: self.editor.set_meta("description", text)))
        self._file_note = QLabel("")
        self._file_note.setWordWrap(True)
        form = QFormLayout(page)
        form.addRow("File", self._id_label)
        form.addRow("Name", self._name)
        form.addRow("Description", self._description)
        form.addRow(self._file_note)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        sample = PostEditorModel.setting_names()
        defaults = self.model.post_library.posts["generic"].settings
        for key in sample:
            default = getattr(defaults, key)
            if key in CHOICES:
                widget = QComboBox()
                widget.addItems(CHOICES[key])
                widget.currentTextChanged.connect(lambda text, k=key: self._setting_changed(k, text))
            elif isinstance(default, bool):
                widget = QCheckBox()
                widget.toggled.connect(lambda on, k=key: self._setting_changed(k, "yes" if on else "no"))
            elif isinstance(default, int):
                widget = QSpinBox()
                widget.setRange(-SPIN_MAX, SPIN_MAX)
                widget.valueChanged.connect(lambda value, k=key: self._setting_changed(k, str(value)))
            else:
                widget = QLineEdit()
                widget.textEdited.connect(lambda text, k=key: self._setting_changed(k, text))
            widget.setToolTip(PostEditorModel.setting_help(key))
            label = QLabel(key.replace("_", " "))
            label.setToolTip(PostEditorModel.setting_help(key))
            form.addRow(label, widget)
            self._setting_widgets[key] = widget
        form.addRow(self._problem_label("settings"))
        return page

    def _build_concept_page(self) -> QWidget:
        page = QWidget()
        self._concept_title = QLabel("")
        font = self._concept_title.font()
        font.setBold(True)
        self._concept_title.setFont(font)
        self._own = QCheckBox(POST_OWN_NOTE)
        self._own.toggled.connect(self._own_toggled)
        self._template = QPlainTextEdit()
        self._template.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._template.setMinimumHeight(POST_TEMPLATE_MIN_HEIGHT_PX)
        self._template.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._template.textChanged.connect(self._preview_timer_start)
        self._problem = QLabel("")
        self._problem.setWordWrap(True)
        self._problem.setStyleSheet(f"color: {POST_ERROR_COLOR}")
        self._hint = QLabel("")  # a hint, not a problem: a code that is in the code table, written out
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(f"color: {POST_HINT_COLOR}")
        self._present_title = QLabel("Every optional part present, everything changed")
        self._absent_title = QLabel("Nothing changed, every optional part gone")
        self._present = self._sample_box()
        self._absent = self._sample_box()
        samples = QGridLayout()
        samples.addWidget(self._present_title, 0, 0)
        samples.addWidget(self._absent_title, 0, 1)
        samples.addWidget(self._present, 1, 0)
        samples.addWidget(self._absent, 1, 1)
        self._tokens = QTabWidget()
        all_tokens = QPushButton("All tokens...")
        all_tokens.clicked.connect(self._all_tokens)
        layout = QVBoxLayout(page)
        self._function_box = self._build_function_box()
        self._function_box.setVisible(False)
        layout.addWidget(self._concept_title)
        layout.addWidget(self._own)
        layout.addWidget(self._function_box)
        layout.addWidget(self._template, 2)
        layout.addWidget(self._problem)
        layout.addWidget(self._hint)
        layout.addLayout(samples)
        layout.addLayout(self._build_modifier_row())
        layout.addWidget(QLabel("Tokens that work here (click to put one into the template):"))
        layout.addWidget(self._tokens, 2)
        layout.addWidget(all_tokens, 0, Qt.AlignLeft)
        return page

    @staticmethod
    def _sample_box() -> QPlainTextEdit:
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        box.setMinimumHeight(POST_SAMPLE_MIN_HEIGHT_PX)
        box.setLineWrapMode(QPlainTextEdit.NoWrap)
        return box
