"""The menus of the window: File, Check, Edit, the library menus, the block menu and the flow list menu."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMenu, QMessageBox, QPlainTextEdit, QVBoxLayout
from pathlib import Path

from ....core.constants import LIBRARY_KIND_MATERIALS, LIBRARY_KIND_TOOLS, LIBRARY_KIND_WORKHOLDING
from ...app_model import ModelError
from ..qt_constants import APP_NAME, NEUTRAL_CODE_HEIGHT_PX, NEUTRAL_CODE_MENU_TEXT, NEUTRAL_CODE_SINGLE_MOVES_MENU_TEXT, NEUTRAL_CODE_WIDTH_PX
from .helpers import CONTOUR_MENU_TEXT, COPY_MENU_TEXT, LIBRARY_FILTER


class MenusMixin:
    """The menus of the window: File, Check, Edit, the library menus, the block menu and the flow list menu. (A part of MainWindow: it uses the attributes that MainWindow.__init__ sets.)"""

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("&File")
        for text, handler, shortcut in (
            ("&New", self._new, "Ctrl+N"),
            ("&Open...", self._open, "Ctrl+O"),
            ("&Save", self._save, "Ctrl+S"),
            ("Save &as...", self._save_as, "Ctrl+Shift+S"),
            (None, None, None),
            ("Export &G-code...", lambda: self._export(None), "Ctrl+E"),
            ("Export &selected blocks...", self._export_selected, None),
            ("&Machines...", self._machines, None),
            ("&Postprocessors...", self._posts, None),
            (None, None, None),
            ("Pre&ferences...", self._preferences, None),
            (None, None, None),
            ("&Quit", self.close, "Ctrl+Q"),
        ):
            if text is None:
                menu.addSeparator()
                continue
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(handler)
            menu.addAction(action)
        edit_menu = self.menuBar().addMenu("&Edit")
        self._undo_action = QAction("&Undo", self)
        self._undo_action.setShortcut("Ctrl+Z")
        self._undo_action.triggered.connect(self.model.undo)
        self._redo_action = QAction("&Redo", self)
        self._redo_action.setShortcuts(["Ctrl+Y", "Ctrl+Shift+Z"])
        self._redo_action.triggered.connect(self.model.redo)
        edit_menu.addAction(self._undo_action)
        edit_menu.addAction(self._redo_action)
        tools_menu = self.menuBar().addMenu("&Tools")
        show_tools = QAction("&Show tools", self)
        show_tools.triggered.connect(self._show_tools)
        tools_menu.addAction(show_tools)
        add_menu = tools_menu.addMenu("&Add tool")
        for type_name, label in self.model.tool_type_choices():
            add_menu.addAction(label).triggered.connect(lambda _checked=False, t=type_name: self._add_tool(t))
        use_toolbox = tools_menu.addMenu("&Use toolbox")
        use_toolbox.aboutToShow.connect(lambda m=use_toolbox: self._fill_toolbox_menu(m))
        tools_menu.addAction("Edit &toolboxes...").triggered.connect(lambda _checked=False: self._toolboxes())
        self._add_library_menu(tools_menu, LIBRARY_KIND_TOOLS)
        holding_menu = self.menuBar().addMenu("&Workholding")
        show_holding = QAction("&Show workholding", self)
        show_holding.triggered.connect(self._show_workholding)
        holding_menu.addAction(show_holding)
        add_holding = holding_menu.addMenu("&Add workholding")
        for type_name, label in self.model.workholding_type_choices():
            add_holding.addAction(label).triggered.connect(lambda _checked=False, t=type_name: self._add_workholding(t))
        self._add_library_menu(holding_menu, LIBRARY_KIND_WORKHOLDING)
        materials_menu = self.menuBar().addMenu("&Materials")
        edit_materials = QAction("&Edit materials...", self)
        edit_materials.triggered.connect(self._materials)
        materials_menu.addAction(edit_materials)
        self._add_library_menu(materials_menu, LIBRARY_KIND_MATERIALS)
        QShortcut(QKeySequence("Ctrl+3"), self).activated.connect(self._toggle_3d)  # the 2D / 3D buttons are in the picture

    def _fill_toolbox_menu(self, submenu) -> None:
        submenu.clear()
        default = self.model.default_toolbox
        for box in self.model.toolboxes:
            mark = " (default)" if default is not None and box.name.casefold() == default.casefold() else ""
            submenu.addAction(box.name + mark).triggered.connect(lambda _checked=False, n=box.name: self._use_toolbox(n))
        if not self.model.toolboxes:
            submenu.addAction("(no toolbox in this library: Edit toolboxes...)").setEnabled(False)

    def _add_library_menu(self, menu, kind: str) -> None:
        """The Library submenu of a menu (LIB1): the libraries to choose from, new, save as, import."""
        menu.addSeparator()
        submenu = menu.addMenu("&Library")
        submenu.aboutToShow.connect(lambda m=submenu, k=kind: self._fill_library_menu(m, k))

    def _fill_library_menu(self, submenu, kind: str) -> None:
        submenu.clear()
        active = self.model.active_library_name(kind)
        for name in self.model.library_names(kind):
            action = submenu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name.casefold() == active.casefold())
            action.triggered.connect(lambda _checked=False, n=name: self._library_action(self.model.switch_library, kind, n))
        submenu.addSeparator()
        submenu.addAction("&New library...").triggered.connect(lambda _checked=False: self._library_name_action(kind, "New library", self.model.new_library))
        submenu.addAction("&Save as library...").triggered.connect(lambda _checked=False: self._library_name_action(kind, "Save as library", self.model.save_library_as))
        submenu.addAction("&Import library file...").triggered.connect(lambda _checked=False: self._import_library(kind))
        submenu.addAction("&Open library folder").triggered.connect(lambda _checked=False: self._open_library_folder(kind))
        submenu.addSeparator()
        in_use = not self.model.active_library_name(kind).casefold() == "example"
        rename = submenu.addAction("&Rename this library...")
        rename.setEnabled(in_use)
        rename.triggered.connect(lambda _checked=False: self._rename_library(kind))
        delete = submenu.addAction("&Delete this library...")
        delete.setEnabled(in_use)
        delete.triggered.connect(lambda _checked=False: self._delete_library(kind))

    def _open_library_folder(self, kind: str) -> None:
        folder = self.model.library_folder_path(kind)
        if folder is None:
            self._say("The settings are not kept in a folder, so there is no library folder.")
            return
        self._say(f"Library folder: {folder}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _library_action(self, action, *arguments) -> None:
        try:
            self._say(action(*arguments))
        except ModelError as error:
            self._say(str(error))

    def _library_name_action(self, kind: str, title: str, action) -> None:
        name, accepted = QInputDialog.getText(self, title, "Name of the library:")
        if accepted and name.strip():
            self._library_action(action, kind, name)

    def _rename_library(self, kind: str) -> None:
        old = self.model.active_library_name(kind)
        name, accepted = QInputDialog.getText(self, "Rename library", "New name:", text=old)
        if accepted and name.strip():
            self._library_action(self.model.rename_library, kind, old, name)

    def _delete_library(self, kind: str) -> None:
        name = self.model.active_library_name(kind)
        answer = QMessageBox.question(self, APP_NAME, f"Delete the library {name!r}? The file is removed; the Example is used instead.")
        if answer == QMessageBox.Yes:
            self._library_action(self.model.delete_library, kind, name)

    def _import_library(self, kind: str) -> None:
        name, _filter = QFileDialog.getOpenFileName(self, "Import library file", self._dialog_start(), LIBRARY_FILTER)
        if self._chosen(name):
            self._library_action(self.model.import_library, kind, Path(name))

    def _fill_block_menu(self) -> None:
        """The Add block menu."""
        self._block_menu.clear()
        for type_name, label in self.model.block_choices():
            action = self._block_menu.addAction(label)
            action.triggered.connect(lambda _checked=False, t=type_name: self._add_block(t))
        self._block_menu.addSeparator()
        self._block_menu.addAction(CONTOUR_MENU_TEXT).triggered.connect(lambda _checked=False: self._contour_action(self._new_contour))

    def _flow_menu(self, point) -> None:
        """Right click on a block or contour of the flow list: Copy, and for a block its neutral operations as text."""
        row = self.flow.row(self.flow.itemAt(point)) if self.flow.itemAt(point) is not None else -1
        index = row - 1  # row 0 is the Setup
        contour_id = self._contour_rows.get(row)
        if contour_id is None and not 0 <= index < len(self.model.blocks):
            return
        menu = QMenu(self)
        copy = menu.addAction(COPY_MENU_TEXT)
        if contour_id is None:
            menu.addAction(NEUTRAL_CODE_MENU_TEXT)
            menu.addAction(NEUTRAL_CODE_SINGLE_MOVES_MENU_TEXT)
        chosen = menu.exec(self.flow.mapToGlobal(point))
        if chosen is copy:
            if contour_id is not None:
                self._contour_action(lambda: self.model.copy_contour(contour_id))
            else:
                self._contour_action(lambda: self.model.copy_block(index))
        elif chosen is not None:
            self._show_neutral_code(index, chosen.text() == NEUTRAL_CODE_SINGLE_MOVES_MENU_TEXT)

    def _show_neutral_code(self, index: int, single_moves: bool = False) -> None:
        block = self.model.blocks[index]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Operations of block {index + 1}: {block.title or block.display_label()}")
        text = QPlainTextEdit(self.model.block_operations_text(index, single_moves))
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        text.setFont(font)
        layout = QVBoxLayout(dialog)
        layout.addWidget(text)
        dialog.resize(NEUTRAL_CODE_WIDTH_PX, NEUTRAL_CODE_HEIGHT_PX)
        dialog.exec()
