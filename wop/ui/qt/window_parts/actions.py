"""What the buttons and menu entries do to the model: blocks, contours, tools, workholding and the dialogs."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from ....core.sketch.model import SketchError
from ...app_model import ModelError
from ..machines_dialog import MachinesDialog
from ..materials_dialog import MaterialsDialog
from ..post_editor_dialog import PostEditorDialog
from ..toolboxes_dialog import ToolboxesDialog
from ..preferences_dialog import PreferencesDialog
from ..sketch_dialog import SketchDialog
from ..qt_constants import APP_NAME, RIGHT_PANEL
from .helpers import MODE_TOOLS, MODE_WORKHOLDING


class ActionsMixin:
    """What the buttons and menu entries do to the model: blocks, contours, tools, workholding and the dialogs. (A part of MainWindow: it uses the attributes that MainWindow.__init__ sets.)"""

    def _add_block(self, type_name: str) -> None:
        self._open_right()
        self.model.add_block(type_name)

    def _contour_action(self, handler) -> None:
        self._open_right()
        handler()

    def _open_right(self) -> None:
        """Work that needs the form opens the right panel, also when the user had closed it by hand
        (new block, new tool, show tools, contours, choosing a contour, double click on the flow list)."""
        if self.splitter.is_collapsed(RIGHT_PANEL):
            self.splitter.open_panel(RIGHT_PANEL)

    def _delete(self) -> None:
        if self.model.selected_contour is not None:
            self._delete_contour()
        elif self.model.selected is not None:
            self.model.delete_block(self.model.selected)

    def _move(self, step: int) -> None:
        if self.model.selected is not None:
            self.model.move_block(self.model.selected, step)

    def _x_mode(self):
        return self.model.project.settings.x_mode

    def _show_tools(self) -> None:
        self._open_right()
        self._mode = MODE_TOOLS
        self.model.show_tools(self.model.selected_tool)

    def _show_workholding(self) -> None:
        self._open_right()
        self._mode = MODE_WORKHOLDING
        self.model.show_workholding(self.model.selected_workholding)

    def _add_workholding(self, type_name: str) -> None:
        self._open_right()
        self._mode = MODE_WORKHOLDING
        try:
            self.model.add_workholding_item(type_name)
        except ModelError as error:
            self._say(str(error))

    def _add_tool(self, type_name: str) -> None:
        self._open_right()
        try:
            self.model.add_tool_of_type(type_name)
        except ModelError as error:
            self._say(str(error))

    def _new_contour(self) -> None:
        """A new contour is chosen and the sketch editor opens for it; when the editor is closed the contour stays chosen."""
        self.model.new_contour()
        self._sketch_for_contour()

    def _delete_contour(self) -> None:
        found = [c for c in self.model.program.contours if c.contour_id == self.model.selected_contour]
        if not found:
            self._say("Choose a contour in the flow list first.")
            return
        contour = found[0]
        users = self.model.contour_users(contour.contour_id)
        if not users:
            self.model.delete_contour(contour.contour_id, with_blocks=False)
            return
        numbers = ", ".join(str(i + 1) for i in users)
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Question)
        box.setText(f"The contour {contour.name} is used by block {numbers}.")
        with_blocks = box.addButton("Delete with these blocks", QMessageBox.DestructiveRole)
        keep_blocks = box.addButton("Delete, keep the blocks without a contour", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is with_blocks:
            self.model.delete_contour(contour.contour_id, with_blocks=True)
        elif box.clickedButton() is keep_blocks:
            self.model.delete_contour(contour.contour_id, with_blocks=False)

    def _toggle_3d(self) -> None:
        self.centre.toggle_mode()

    def _materials(self) -> None:
        MaterialsDialog(self, self.model).exec()

    def _toolboxes(self) -> None:
        ToolboxesDialog(self, self.model).exec()

    def _use_toolbox(self, name: str) -> None:
        """Put a toolbox into the project. The blocks that would lose their tool or get another number are told first."""
        try:
            change = self.model.toolbox_change(name)
            if change.changes_blocks:
                lines = [f"Block {i + 1} {self.model.blocks[i].display_label()}: no tool chosen" for i in change.unhooked]
                lines += [f"Block {i + 1} {self.model.blocks[i].display_label()}: keeps its tool, which has another number" for i in change.renumbered]
                answer = QMessageBox.question(
                    self, APP_NAME,
                    f"The toolbox {change.toolbox!r} replaces the tools of this project.\n\n" + "\n".join(lines) + "\n\nGo on?",
                )
                if answer != QMessageBox.Yes:
                    return
            self.model.apply_toolbox(name)
        except ModelError as error:
            self._say(str(error))
            return
        self._say(f"The toolbox {change.toolbox!r} is in the project" + (f"; {len(change.unhooked)} block(s) have no tool chosen" if change.unhooked else ""))

    def _machines(self) -> None:
        MachinesDialog(self, self.model).exec()

    def _posts(self) -> None:
        PostEditorDialog(self, self.model).exec()
        self._show_form()  # the post dropdown of the machine form may have new names

    def _sketch_for_contour(self) -> None:
        """Open the chosen contour of the part in the sketch editor."""
        selected = self.model.selected_contour
        if selected is None:
            self._say("Choose or add a contour first.")
            return
        try:
            SketchDialog(self, target=self.model.contour_sketch_target(selected)).exec()
        except (ModelError, SketchError) as error:
            self._say(str(error))

    def _preferences(self) -> None:
        PreferencesDialog(self, self.model).exec()
