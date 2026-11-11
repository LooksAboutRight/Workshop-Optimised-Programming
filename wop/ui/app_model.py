"""The state and the actions of the application, without any GUI toolkit.

The window shows this model and calls its methods. Every change goes through
here, so it can be tested without a screen. After each change the program is
planned and checked again (`refresh`); the window then redraws."""

from __future__ import annotations

import threading
from pathlib import Path

from ..adapters.app_settings_files import load_app_settings
from ..adapters.post_library import load_post_library
from ..adapters.project_files import load_project_and_preview, save_project
from ..core.geometry.chains import loops_of_region, region_of_loops
from ..core.files.app_settings import AppSettings
from ..core.blocks import BLOCK_TYPES
from ..core.blocks.base import Block
from ..core.program_model.plan_cache import PlanCache
from ..core.program_model.program import Program
from ..core.program_model.project import Project
from ..core.files.project_io import ProjectError
from .app_constants import UNDO_LIMIT, WORKING_PLANNING
from .block_forms import FormContext
from .stepper import Stepper
from .theme import ColorSet, LIGHT_COLORS
from .model.posts import PostsMixin
from .model.machines import MachinesMixin
from .model.views import ViewsMixin
from .model.export import ExportMixin
from .model.blocks import BlocksMixin
from .model.contours import ContoursMixin
from .model.settings_libraries import SettingsMixin
from .model.setup import SetupMixin
from .model.tools import ToolsMixin
from .model.toolboxes import ToolboxesMixin
from .model.workholding import WorkholdingMixin
from .model.sketch_targets import SketchTargetsMixin
from .model.helpers import (  # noqa: F401  (the names other modules import from here)
    Analysis,
    EMPTY_CONTENT,
    ExportReport,
    Listener,
    ModelError,
    ShapeToolForm,
    TOOL_DIFFERS_FROM_LIBRARY,
    TOOL_NOT_IN_LIBRARY,
    TOOL_SAME_AS_LIBRARY,
    default_contour,
    new_project,
    tool_core,
)


class AppModel(
    PostsMixin, MachinesMixin, ViewsMixin, ExportMixin, BlocksMixin, ContoursMixin, SettingsMixin, SetupMixin,
    ToolsMixin, ToolboxesMixin, WorkholdingMixin, SketchTargetsMixin,
):
    def __init__(
        self, project: Project | None = None, path: Path | None = None, settings_path: Path | None = None
    ) -> None:
        """settings_path: the application settings file; None keeps the settings in memory only (tests)."""
        self.settings_path = settings_path
        self.app_settings = AppSettings()
        self.settings_message = ""  # what went wrong when the settings file was read, for the window to show
        self._notices: list[str] = []  # things the user should be told about (`take_notice`)
        self._plan_cache: tuple | None = None  # (program, {(selection, unticked_done): plan}) (`_plan`)
        self._block_cache = PlanCache()  # the plans and checks of single blocks, for the next plan of a changed program (`plan_cache.py`)
        self._work_lock = threading.RLock()  # the caches are used by one thread at a time (the window plans in the background)
        self._runner = None  # runs a job in the background and hands its result to the window's thread (`run_in_background`)
        self._generation = 0  # counts the requests for a new analysis: an older one stops and its result is thrown away
        if settings_path is not None:
            self.app_settings, self.settings_message = load_app_settings(settings_path)
        self.post_library = load_post_library(None if settings_path is None else settings_path.parent)  # the posts that come with WOP and the user's own
        self._load_libraries()
        self._load_machines()
        self._remember_disk_state()
        self.project = project or self._new_project()
        self.path = path
        self.dirty = self._sync_project_machine()  # a project made with an older copy of a listed machine is changed
        self.selected: int | None = None
        self.selected_contour: str | None = None  # the contour shown in the centre; its name is in the right panel, its outline is drawn in the sketch editor (C9)
        self.tools_view = False  # the Tools view is shown in the centre (T8)
        self.selected_tool: int | None = None
        self.workholding_view = False  # the Workholding view is shown in the centre (WH2)
        self.selected_workholding: str | None = None  # name of the chosen item of the library
        self._unticked: set[str] = set()  # ids of blocks whose export checkbox is off (B15; not saved in the project)
        self.unticked_done = True  # do the unticked blocks count as done (their material is gone) or not
        self.analysis = Analysis()
        self.auto_check = True  # collisions and power are checked after every change; False only for tests and tools that do not need the check
        self._force_check = False  # verify_now: the next analysis checks although `auto_check` is off
        self._history: list[Project] = [self.project]  # states for Undo / Redo
        self._history_pos = 0
        self._stepper: Stepper | None = None
        self.colors: ColorSet = LIGHT_COLORS  # the window sets the set that fits its theme
        self._listeners: list[Listener] = []
        self._result_listeners: list[Listener] = []  # told when a result of the background work arrives (`subscribe_results`)
        machine = self.project.machine
        if machine is not None:
            self._apply_machine_libraries(machine.name)
        self.refresh()

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)
        if listener in self._result_listeners:
            self._result_listeners.remove(listener)

    def subscribe_results(self, listener: Listener) -> None:
        """`listener` is called when the plan or the check made in the background arrives (`run_in_background`): the analysis
        changed, the project did not (a form being typed into stays as it is)."""
        self._result_listeners.append(listener)

    def _notify_results(self) -> None:
        for listener in list(self._result_listeners):
            listener()

    def _changed(self, dirty: bool = True) -> None:
        if self._sync_project_machine():  # whatever changed (an edit, Undo, files read again): the machine shown is the machine used
            dirty = True
        self.dirty = self.dirty or dirty
        self._record()
        self._drop_missing_contour()
        self.refresh()
        for listener in list(self._listeners):
            listener()

    def _record(self) -> None:
        """Remember the project as a new state if it differs from the current one."""
        if self.project == self._history[self._history_pos]:
            return
        del self._history[self._history_pos + 1 :]
        self._history.append(self.project)
        if len(self._history) > UNDO_LIMIT:
            del self._history[0]
        self._history_pos = len(self._history) - 1

    def _reset_history(self) -> None:
        self._history = [self.project]
        self._history_pos = 0

    @property
    def can_undo(self) -> bool:
        return self._history_pos > 0

    @property
    def can_redo(self) -> bool:
        return self._history_pos < len(self._history) - 1

    def undo(self) -> bool:
        return self._go_in_history(-1)

    def redo(self) -> bool:
        return self._go_in_history(1)

    def _go_in_history(self, step: int) -> bool:
        target = self._history_pos + step
        if not 0 <= target < len(self._history):
            return False
        self._history_pos = target
        self.project = self._history[target]
        if self._sync_project_machine():  # an old state holds an old copy of the machine
            self._history[target] = self.project
        self._drop_missing_contour()
        if self.selected is not None and self.selected >= len(self.blocks):
            self.selected = len(self.blocks) - 1 if self.blocks else None
        self.dirty = True
        self.refresh()
        for listener in list(self._listeners):
            listener()
        return True

    @property
    def program(self) -> Program:
        return self.project.program

    @property
    def blocks(self) -> tuple[Block, ...]:
        return self.program.blocks

    def selected_block(self) -> Block | None:
        if self.selected is None or not 0 <= self.selected < len(self.blocks):
            return None
        return self.blocks[self.selected]

    def form_context(self) -> FormContext:
        return FormContext(
            materials=tuple(material.name for material in self.materials.all()),
            postprocessors=self.post_choices(),
            tools=tuple((t.number, t.name) for t in sorted(self.program.tools, key=lambda t: t.number)),
            contours=tuple((c.contour_id, c.name) for c in self.program.contours),
            functions=self.available_machine_functions(),
            workholding=self.workholding_choices(),
            jaw_points=self.jaw_point_names(),
        )

    def block_choices(self) -> list[tuple[str, str]]:
        """(type name, label) of the block types on offer."""
        return [(name, BLOCK_TYPES.get(name).display_label()) for name in BLOCK_TYPES.names()]

    def block_types(self) -> list[str]:
        return [name for name, _label in self.block_choices()]

    def title(self) -> str:
        name = self.path.name if self.path else "unsaved project"
        return f"{name}{' *' if self.dirty else ''}"

    def select(self, index: int | None) -> None:
        self.selected = index if index is not None and 0 <= index < len(self.blocks) else None
        self.selected_contour = None
        self.tools_view = False
        self.workholding_view = False
        self._notify()

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    def new(self) -> None:
        self.project, self.path, self.dirty, self.selected = self._new_project(), None, False, None
        self._unticked = set()
        self._reset_history()
        self._changed(dirty=False)

    def open(self, path: Path) -> None:
        try:
            project, preview = load_project_and_preview(path)
        except ProjectError as error:
            raise ModelError(str(error)) from error
        self.project, self.path, self.dirty, self.selected = project, path, False, None
        self.analysis = Analysis(preview=region_of_loops(preview) if preview else None)  # the part as saved, until the plan is there (V9)
        self._unticked = set()
        self.dirty = self._sync_project_machine()  # the project file is now older than what is shown
        self.dirty = self._use_default_machine() or self.dirty
        self._reset_history()
        if self.project.machine is not None and self._apply_machine_libraries(self.project.machine.name):  # its machine's libraries
            self.selected_workholding = None
        self._changed(dirty=False)

    def _finished_part(self) -> list | None:
        """The loops of the finished part of the shown plan, for the file (V9); None when the shown plan is not the one of this program."""
        shown = self.analysis
        if shown.plan is None or shown.program is not self.program or shown.working == WORKING_PLANNING:
            return None
        final = shown.plan.final_residual
        return None if final.is_empty else loops_of_region(final)

    def save(self, path: Path | None = None, with_part: bool = True) -> None:
        """Write the project. `with_part`: with the finished part of the shown plan (V9); the example tools write none (their files would
        change with every change of the planner)."""
        target = path or self.path
        if target is None:
            raise ModelError("there is no file name yet")
        save_project(target, self.project, self._finished_part() if with_part else None)
        self.path, self.dirty = target, False
        for listener in list(self._listeners):
            listener()
