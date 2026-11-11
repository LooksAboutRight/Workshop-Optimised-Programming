"""The Setup form: raw part, safe positions and the machine of the project."""

from __future__ import annotations

from dataclasses import replace

from ...core.contour import Contour
from ...core.program_model.raw_outline import raw_part_from_outline
from ...core.program_model.raw_part import RawPart, RawPartError
from ...core.program_model.touched import SETUP_OWNER
from ...core.lathe.workholding import JAWS_KIND
from ..setup_form import PROJECT_COPY_SUFFIX, safe_positions, setup_from_program, setup_to_parts, SetupForm
from .helpers import ModelError


class SetupMixin:
    """The Setup form: raw part, safe positions and the machine of the project. (A part of AppModel: it uses the attributes that AppModel.__init__ sets.)"""

    def setup_form(self) -> SetupForm:
        """Raw part, material and safe positions as the Setup form shows them."""
        machine = self.project.machine
        choices = [(m.name, m.name) for m in self.machines]
        if machine is not None and machine.name not in {name for name, _text in choices}:
            choices.append((machine.name, machine.name + PROJECT_COPY_SUFFIX))
        offsets = self.post_library.choose(self.postprocessor_id)[0].work_offsets
        return replace(
            setup_from_program(self.program),
            work_offset_choices=offsets,
            jaw_names=self.workholding_names(JAWS_KIND),
            title=self.project.settings.title,
            x_mode=self.project.settings.x_mode,
            work_offset=self.project.settings.work_offset,
            machine="" if machine is None else machine.name,
            machine_choices=tuple(choices),
        )

    def set_setup_form(self, form: SetupForm) -> None:
        """Take the values of the Setup form. Raises ModelError for a raw part that cannot exist."""
        previous = self.setup_form()
        if form.machine != previous.machine:  # another machine: it may bring its own tool change position
            self.use_machine(form.machine or None)
            now = self.setup_form()
            form = replace(form, change_radius_mm=now.change_radius_mm, change_z_mm=now.change_z_mm)
            previous = now
        form = self._follow_the_part(previous, form)
        try:
            raw_part, safety = setup_to_parts(form)
        except ValueError as error:
            raise ModelError(str(error)) from error
        holding = self._workholding_from_form(form)
        settings = replace(self.project.settings, title=form.title, x_mode=form.x_mode, work_offset=form.work_offset)
        self.project = replace(
            self.project, settings=settings,
            program=replace(self.program, raw_part=raw_part, safety=safety, workholding=holding),
        )
        self._changed()

    def draw_raw_part(self, outline: Contour) -> None:
        """Take a drawn raw part: the numbers of the Setup follow the drawing, and so do the safe positions that were not typed."""
        form = self.setup_form()
        try:
            raw = raw_part_from_outline(form.material, outline)
        except RawPartError as error:
            raise ModelError(str(error)) from error
        self.set_setup_form(replace(
            form, outer_diameter_mm=raw.outer_diameter_mm, inner_diameter_mm=raw.inner_diameter_mm, length_outside_mm=raw.length_outside_mm,
            stock_runs_through=False, length_mm=raw.length_mm, front_z_mm=raw.front_z_mm, raw_outline=outline,
        ))

    def use_plain_bar(self) -> None:
        """Forget the drawing; the numbers it gave stay, and can be edited again."""
        self.set_setup_form(replace(self.setup_form(), raw_outline=None))

    def _follow_the_machine(self) -> None:
        """The tool change position that was not typed follows the machine (its position, else the part)."""
        form = self.setup_form()
        follow = self._follow_the_part(form, form, only=("change_radius_mm", "change_z_mm"))
        if follow != form:
            _raw, safety = setup_to_parts(follow)
            self.project = replace(self.project, program=replace(self.program, safety=safety))

    def _follow_the_part(self, previous: SetupForm, form: SetupForm, only: tuple[str, ...] | None = None) -> SetupForm:
        """The safe position and the tool change position follow the part (outer radius and front Z plus the two margins of the preferences) as long
        as the user has not typed them; the tool change position follows the machine when that has one. A field
        that is edited right now is left as it is. `only` limits the fields looked at."""
        radius, z = safe_positions(form.outer_diameter_mm, form.front_z_mm)
        machine = self.project.machine
        change_radius = radius if machine is None or machine.change_radius_mm is None else machine.change_radius_mm
        change_z = z if machine is None or machine.change_z_mm is None else machine.change_z_mm
        for name, value in (
            ("safe_radius_mm", radius), ("change_radius_mm", change_radius), ("safe_z_mm", z), ("change_z_mm", change_z),
        ):
            if only is not None and name not in only:
                continue
            if getattr(form, name) == getattr(previous, name) and not self.is_touched(SETUP_OWNER, (name,)):
                form = replace(form, **{name: value})
        return form

    def set_raw_part(self, raw_part: RawPart) -> None:
        self.project = replace(self.project, program=replace(self.program, raw_part=raw_part))
        self._changed()
