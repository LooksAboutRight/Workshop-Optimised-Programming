"""The form in the right panel: what it shows, what an edit does."""

from __future__ import annotations

from PySide6.QtCore import QTimer

from ....core.program_model.touched import SETUP_OWNER
from ....core.sketch.model import SketchError
from ...app_model import ModelError
from ...display_units import shown_text
from ...block_forms import FieldSpec, form_for, form_state, get_value, set_value
from ...material_form import NewMaterial
from ...setup_form import SETUP_TITLE, stock_summary
from ..dialogs import FormDialog
from ..sketch_dialog import SketchDialog
from ..theme_qt import untouched_text_color
from .helpers import MODE_CONTOUR, MODE_SETUP, MODE_TOOLS, MODE_WORKHOLDING


class FormMixin:
    """The form in the right panel: what it shows, what an edit does. (A part of MainWindow: it uses the attributes that MainWindow.__init__ sets.)"""

    def _edit_object(self):
        if self._mode == MODE_SETUP:
            return self.model.setup_form()
        if self._mode == MODE_TOOLS:
            return None if self.model.selected_tool is None else self.model.tool_form(self.model.selected_tool)
        if self._mode == MODE_WORKHOLDING:
            name = self.model.selected_workholding
            return None if name is None or self.model.selected_workholding_item() is None else self.model.workholding_form(name)
        block = self.model.selected_block()
        return None if block is None else self.model.shown_block(self.model.selected)  # greyed fields with what the plan worked out

    def _edit_owner(self) -> str | None:
        """The name under which the model remembers the touched fields of the object in the form."""
        if self._mode == MODE_SETUP:
            return SETUP_OWNER
        if self._mode == MODE_TOOLS:
            return None  # tool values are not marked as touched
        if self._mode == MODE_WORKHOLDING:
            return None
        return None if self.model.selected is None else self.model.block_owner(self.model.selected)

    def _form_title(self) -> str:
        if self._mode == MODE_SETUP:
            return SETUP_TITLE
        if self._mode == MODE_TOOLS:
            return "" if self.model.selected_tool is None else f"Tool T{self.model.selected_tool}"
        if self._mode == MODE_WORKHOLDING:
            return self.model.selected_workholding or ""
        block = self.model.selected_block()
        return "" if block is None else f"Block {self.model.selected + 1}: {block.display_label()}"

    def _show_form(self) -> None:
        if self._mode == MODE_CONTOUR and self.model.selected_contour is not None:
            self.right_stack.setCurrentIndex(1)
            self.form_title.setText(f"Contour: {self._contour_name()}")
            self.setup_info.setVisible(False)
            self.contour_panel.show_contour()
            return
        self.right_stack.setCurrentIndex(0)
        obj = self._edit_object()
        self.form_title.setText(self._form_title())
        self._update_setup_info()
        if obj is None:
            self.form.clear()
            return
        specs = form_for(obj, self.model.form_context())
        owner = self._edit_owner()
        self.form.set_form(
            obj,
            specs,
            self.model.project.settings.x_mode,
            None if owner is None else (lambda path, o=owner: self.model.is_touched(o, path)),
            untouched_text_color(self.palette()),
        )

    def _contour_name(self) -> str:
        found = [c.name for c in self.model.program.contours if c.contour_id == self.model.selected_contour]
        return found[0] if found else ""

    def _update_setup_info(self) -> None:
        """Under the Setup form: what the stock does behind the clamping plane and its total length (R7)."""
        self.setup_info.setVisible(self._mode == MODE_SETUP)
        if self._mode == MODE_SETUP:
            self.setup_info.setText(shown_text(stock_summary(self.model.setup_form()) + "\n" + self.model.workholding_note()))

    def _new_material(self, spec: FieldSpec) -> None:
        """"New..." in the material list: ask for name and cutting force, keep the material, use it."""
        dialog = FormDialog(self, "New material", NewMaterial(), self._x_mode())
        if dialog.exec():
            entered = dialog.value
            try:
                name = self.model.add_material(entered.name, entered.specific_cutting_force_n_mm2)
            except ModelError as error:
                self._say(str(error))
            else:
                self._value_edited(spec, name)
        self._show_form()  # shows the list with the new entry, or the old value again

    def _reset_field(self, spec: FieldSpec) -> None:
        """"Reset to default" of one field: its value in a fresh object, and untouched again (U6)."""
        owner = self._edit_owner()
        default = None if owner is None else self.model.default_object(owner, spec.path[0])
        if default is None:
            return
        self._value_edited(spec, get_value(default, spec.path), touched=False)
        self._show_form()

    def _value_edited(self, spec: FieldSpec, value, touched: bool = True) -> None:
        self._editing = True
        try:
            obj = self._edit_object()
            if obj is None:
                return
            owner = self._edit_owner()
            new = set_value(obj, spec.path, value)
            if form_state(obj) != form_state(new):
                QTimer.singleShot(0, self._show_form)  # the form has other fields now, after this handler has ended
            if self._mode == MODE_SETUP:
                self.model.set_setup_form(new)
                if self.model.setup_form() != new:  # the safe positions followed the part: show them now
                    QTimer.singleShot(0, self._show_form)  # after this handler has ended (the field was left, not typed in)
            elif self._mode == MODE_TOOLS:
                self.model.edit_tool(self.model.selected_tool, new)
                QTimer.singleShot(0, self._show_form)  # codes and dropdowns of a holder follow each other
            elif self._mode == MODE_WORKHOLDING:
                self.model.edit_workholding(self.model.selected_workholding, new)
                QTimer.singleShot(0, self._show_form)  # a renamed item has a new title
            else:
                self.model.replace_block(self.model.selected, new)
                if self.model.blocks[self.model.selected] != new:  # other fields followed (designation, tool defaults)
                    QTimer.singleShot(0, self._show_form)  # show them now, after this handler has ended
            if owner is not None:
                self.model.set_touched(owner, spec.path, touched)
            self._update_setup_info()
        except ValueError as error:
            self._say(str(error))
            self._editing = False
            QTimer.singleShot(0, self._show_form)  # show the old value again, after this edit handler has ended
        finally:
            self._editing = False

    def _form_action(self, spec: FieldSpec) -> None:
        """A button of the form: the one in Setup opens the machine settings (the same as File > Machines)."""
        if spec.path == ("machine_settings",):
            QTimer.singleShot(0, self._machines)  # after the click has ended
        elif spec.path == ("draw_raw_part",):
            QTimer.singleShot(0, self._draw_raw_part)
        elif spec.path == ("plain_bar",):
            QTimer.singleShot(0, self._plain_bar)
        elif spec.path == ("draw_path",):
            QTimer.singleShot(0, self._draw_path)

    def _draw_path(self) -> None:
        index = self.model.selected
        if index is None:
            return
        try:
            SketchDialog(self, target=self.model.path_sketch_target(index)).exec()
        except (ModelError, SketchError) as error:
            self._say(str(error))
        self._show_form()

    def _draw_raw_part(self) -> None:
        try:
            SketchDialog(self, target=self.model.raw_part_sketch_target()).exec()
        except (ModelError, SketchError) as error:
            self._say(str(error))
        self._show_form()

    def _plain_bar(self) -> None:
        try:
            self.model.use_plain_bar()
        except ModelError as error:
            self._say(str(error))
        self._show_form()
