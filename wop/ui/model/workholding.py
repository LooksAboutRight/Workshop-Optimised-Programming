"""Workholding: the library, the view and what the Setup chooses."""

from __future__ import annotations

from dataclasses import replace

from ...core.constants import JAWS_MOUNT_POINT
from ...core.contour import Contour
from ...core.lathe.workholding import CHUCK_KIND, GripMode, JAWS_KIND, library_find, library_with, library_without, place_workholding, raw_part_notes, Workholding, workholding_notes, WorkholdingError, WorkholdingItem
from ...core.workholding_types import example_item, WORKHOLDING_TYPES
from ..setup_form import SetupForm
from ..workholding_form import form_of_item, item_from_form, WorkholdingForm
from .helpers import ModelError


class WorkholdingMixin:
    """Workholding: the library, the view and what the Setup chooses. (A part of AppModel: it uses the attributes that AppModel.__init__ sets.)"""

    @property
    def workholding_library(self) -> tuple[WorkholdingItem, ...]:
        return self.app_settings.workholding

    def workholding_type_choices(self) -> tuple[tuple[str, str], ...]:
        """(type name, label) of the workholding types for the Add menu."""
        return tuple((t.type_name, t.label) for t in WORKHOLDING_TYPES.types())

    def workholding_choices(self) -> tuple[tuple[str, str], ...]:
        """What the one Workholding dropdown of the Setup lists: (name, label), jaws first, then chuck bodies."""
        chucks = set(self.workholding_names(CHUCK_KIND))
        jaws = self.workholding_names(JAWS_KIND)
        return tuple((name, f"{name} (jaws)") for name in jaws) + tuple((name, f"{name} (chuck body)") for name in sorted(chucks, key=str.casefold) if name not in jaws)

    def workholding_names(self, kind: str) -> tuple[str, ...]:
        """Names of the library items of a kind, plus the project's own copy when it is not in the library."""
        names = [item.name for item in self.workholding_library if item.kind == kind]
        current = self.program.workholding
        own = None if current is None else (current.jaws if kind == JAWS_KIND else current.chuck)
        if own is not None and own.name.casefold() not in {name.casefold() for name in names}:
            names.append(own.name)
        return tuple(names)

    def jaw_point_names(self) -> tuple[str, ...]:
        """The named points of the jaws the project uses (what the Setup can put on the part)."""
        current = self.program.workholding
        if current is None or current.jaws is None:
            return ()
        return tuple(point.name for point in current.jaws.points)

    def selected_workholding_item(self) -> WorkholdingItem | None:
        if self.selected_workholding is None:
            return None
        return library_find(self.workholding_library, self.selected_workholding)

    def _set_workholding_library(self, items: tuple[WorkholdingItem, ...]) -> None:
        self._set_app_settings(replace(self.app_settings, workholding=items))

    def _unique_workholding_name(self, wanted: str) -> str:
        name, number = wanted, 2
        while library_find(self.workholding_library, name) is not None:
            name, number = f"{wanted} {number}", number + 1
        return name

    def show_workholding(self, name: str | None = None) -> None:
        """Show the Workholding view in the centre with an item chosen (the first one if none is given)."""
        self.selected = None
        self.selected_contour = None
        self.tools_view = False
        self.workholding_view = True
        names = [item.name for item in self.workholding_library]
        keep = name if name in names else self.selected_workholding if self.selected_workholding in names else None
        self.selected_workholding = keep if keep is not None else (names[0] if names else None)
        self._notify()

    def select_workholding(self, name: str | None) -> None:
        self.selected_workholding = name
        self._notify()

    def add_workholding_item(self, type_name: str) -> str:
        """Add an item of a type (placeholder shape, to be reshaped in the Sketch editor) to the library and choose it."""
        try:
            label = WORKHOLDING_TYPES.get(type_name).label
            item = example_item(type_name, self._unique_workholding_name(label))
        except ValueError as error:
            raise ModelError(str(error)) from error
        self._set_workholding_library(library_with(self.workholding_library, item))
        self.selected_workholding = item.name
        self.show_workholding(item.name)
        self._changed(dirty=False)
        return item.name

    def workholding_form(self, name: str) -> WorkholdingForm:
        item = library_find(self.workholding_library, name)
        if item is None:
            raise ModelError(f"there is no workholding item {name!r}")
        return form_of_item(item, self.workholding_names(CHUCK_KIND))

    def _store_workholding_item(self, old_name: str, item: WorkholdingItem) -> None:
        """Replace an item of the library (also when it is renamed); the project's copy follows when it uses it."""
        others = [i for i in self.workholding_library if i.name.casefold() != old_name.casefold()]
        if item.name.casefold() != old_name.casefold() and library_find(tuple(others), item.name) is not None:
            raise ModelError(f"there is already a workholding item called {item.name!r}")
        old = library_find(self.workholding_library, old_name)
        position = self.workholding_library.index(old) if old is not None else len(others)
        listed = tuple(others[:position]) + (item,) + tuple(others[position:])
        if item.kind == CHUCK_KIND and item.name.casefold() != old_name.casefold():  # jaws on this chuck follow its new name
            listed = tuple(
                replace(i, chuck=item.name) if i.kind == JAWS_KIND and i.chuck.casefold() == old_name.casefold() else i
                for i in listed
            )
        self._set_workholding_library(listed)
        self.selected_workholding = item.name
        current = self.program.workholding
        if current is not None:
            uses_jaws = current.jaws is not None and current.jaws.name.casefold() == old_name.casefold()
            uses_chuck = current.chuck is not None and current.chuck.name.casefold() == old_name.casefold()
            if uses_jaws or uses_chuck:
                chuck = item if uses_chuck else current.chuck
                if uses_jaws:  # the jaws bring the chuck body they name now
                    chuck = library_find(self.workholding_library, item.chuck) if item.chuck else None
                holding = replace(current, jaws=item if uses_jaws else current.jaws, chuck=chuck)
                self.project = replace(self.project, program=replace(self.program, workholding=holding))
                self._changed()
                return
        self._changed(dirty=False)

    def edit_workholding(self, name: str, form: WorkholdingForm) -> None:
        """Apply the form of an item (name, jaw count and width). Raises ModelError for impossible values."""
        item = library_find(self.workholding_library, name)
        if item is None:
            raise ModelError(f"there is no workholding item {name!r}")
        try:
            new = item_from_form(item, form)
        except ValueError as error:
            raise ModelError(str(error)) from error
        self._store_workholding_item(name, new)

    def set_workholding_shape(self, name: str, contour: Contour) -> None:
        """Give an item the outline and the named points of an edited contour. Raises ModelError if it is not usable."""
        item = library_find(self.workholding_library, name)
        if item is None:
            raise ModelError(f"there is no workholding item {name!r}")
        try:
            new = replace(item, outline=replace(contour, contour_id=item.outline.contour_id, name=item.name))
        except ValueError as error:  # an open or invalid outline
            raise ModelError(str(error)) from error
        self._store_workholding_item(name, new)

    def remove_workholding(self, name: str) -> None:
        """Delete an item from the library. A project that uses it keeps its copy."""
        if library_find(self.workholding_library, name) is None:
            raise ModelError(f"there is no workholding item {name!r}")
        removed = library_find(self.workholding_library, name)
        rest = library_without(self.workholding_library, name)
        if removed.kind == CHUCK_KIND:  # jaws that sat on this chuck body are left without one
            rest = tuple(replace(i, chuck="") if i.kind == JAWS_KIND and i.chuck.casefold() == name.casefold() else i for i in rest)
        self._set_workholding_library(rest)
        names = [item.name for item in self.workholding_library]
        if self.selected_workholding is not None and self.selected_workholding.casefold() == name.casefold():
            self.selected_workholding = names[0] if names else None
        self._changed(dirty=False)

    def _pick_workholding(self, name: str, kind: str, own: WorkholdingItem | None) -> WorkholdingItem | None:
        """The item the Setup form names: the project's copy if it has that name, else the library's."""
        if not name:
            return None
        if own is not None and own.name.casefold() == name.casefold():
            return own
        found = library_find(self.workholding_library, name)
        if found is None or found.kind != kind:
            raise ModelError(f"there is no {kind} called {name!r} in the workholding list")
        return found

    def _workholding_from_form(self, form: SetupForm) -> Workholding | None:
        """What the program uses after a Setup edit: None when nothing is chosen.

        The dropdown names jaws or a chuck body. Jaws bring the chuck body they name (if any).
        """
        current = self.program.workholding
        name = form.workholding
        if not name:
            return None
        own_jaws = None if current is None else current.jaws
        own_chuck = None if current is None else current.chuck
        found = self._pick_named_workholding(name, own_jaws, own_chuck)
        if found.kind != JAWS_KIND:
            return Workholding(None, found, "", GripMode.OUTSIDE)
        chuck = self._pick_workholding(found.chuck, CHUCK_KIND, own_chuck) if found.chuck else None
        anchor = form.jaw_anchor
        changed = current is None or current.jaws is None or current.jaws.name.casefold() != found.name.casefold()
        if (anchor and found.point(anchor) is None) or changed:
            points = [p.name for p in found.points if p.name != JAWS_MOUNT_POINT]
            anchor = points[0] if points else ""
        grip = GripMode.INSIDE if form.grip_inside else GripMode.OUTSIDE
        return Workholding(found, chuck, anchor, grip)

    def _pick_named_workholding(self, name: str, own_jaws: WorkholdingItem | None, own_chuck: WorkholdingItem | None) -> WorkholdingItem:
        """The item the dropdown names (jaws or chuck body): the project's copy if it has that name, else the library's."""
        for own in (own_jaws, own_chuck):
            if own is not None and own.name.casefold() == name.casefold():
                return own
        found = library_find(self.workholding_library, name)
        if found is None:
            raise ModelError(f"there is nothing called {name!r} in the workholding list")
        return found

    def workholding_note(self) -> str:
        """Under the Setup form: where the jaws sit, or why the workholding is not used."""
        holding = self.program.workholding
        if holding is None or holding.is_none:
            return "No workholding: the flat clamping plane is checked."
        try:
            placed = place_workholding(self.program.raw_part, holding)
        except WorkholdingError as error:
            return f"Workholding is not used: {error}. The flat clamping plane is checked instead."
        lines = []
        if placed.anchor_target is not None:
            target = placed.anchor_target
            lines.append(f"Jaw point {holding.anchor!r} sits at diameter {target.x * 2:g}, Z {target.z:g}.")
        elif holding.jaws is not None:
            lines.append("The jaws stay where they are drawn.")
        if holding.chuck is not None:
            lines.append("The chuck body sits behind the jaws.")
        lines.extend(f"Note: {text}." for text in raw_part_notes(self.program.raw_part, holding) + workholding_notes(self.program.raw_part, holding))
        return " ".join(lines)
