"""Start the application."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QMessageBox

from ...adapters.app_settings_files import default_settings_path
from ...core.files.convention_overrides import ensure_file, problems as convention_problems
from ...core.files.user_folder import user_folder
from .. import crash_log, error_log
from ..app_model import AppModel, ModelError
from . import click_commit, unit_text
from .background import BackgroundRunner
from .gl_view import opengl_works
from .main_window import MainWindow
from .dialog_memory import DialogMemory
from .small_screens import ScreenFitFilter
from .qt_constants import APP_NAME, THREAD_SWITCH_INTERVAL_S


SOFTWARE_OPENGL_VARIABLE = "LIBGL_ALWAYS_SOFTWARE"  # Mesa: draw with the processor instead of the graphics chip


def retry_with_software_opengl(argv: list[str]) -> None:
    """On Linux a computer whose graphics cannot give OpenGL 2 (old graphics, a virtual machine, a remote screen) can still
    draw the 3D view with the software renderer of Mesa: the program starts again, once, with that switched on."""
    works, _why_not = opengl_works()
    if works or not sys.platform.startswith("linux") or os.environ.get(SOFTWARE_OPENGL_VARIABLE):
        return
    os.environ[SOFTWARE_OPENGL_VARIABLE] = "1"
    command = [sys.executable, *argv[1:]] if getattr(sys, "frozen", False) else [sys.executable, *argv]
    os.execv(sys.executable, command)


def _qt_message(kind: QtMsgType, _context, message: str) -> None:
    """Qt's own warnings and errors, in wop.log (a fatal one ends the program: the crash log shows where)."""
    sys.stderr.write(f"Qt {kind.name}: {message}\n")


def main(argv: list[str]) -> int:
    application = QApplication(argv)
    retry_with_software_opengl(argv)
    click_commit.install(application)
    unit_text.install(application)
    fit_filter = ScreenFitFilter(application)  # a window larger than the screen is made smaller when it is first shown
    application.installEventFilter(fit_filter)
    log = error_log.install(user_folder() / error_log.LOG_FILE_NAME)  # errors inside handlers are only printed: keep them
    qInstallMessageHandler(_qt_message)  # what Qt itself says goes to the same log (it is written to the C error output otherwise)
    recorder = crash_log.install(user_folder() / crash_log.CRASH_FILE_NAME)  # a crash without a message leaves the stacks here
    if recorder is not None:
        application.aboutToQuit.connect(recorder.stop)
    ensure_file()  # conventions.json: created empty when it does not exist (File > Preferences)
    model = AppModel(settings_path=default_settings_path())
    application.installEventFilter(DialogMemory(model, application))  # after the fit filter, so it runs before it: a dialog gets its last size and place back
    window = MainWindow(model, log)
    model.run_in_background(BackgroundRunner(window).start)  # plan and check without freezing the window
    sys.setswitchinterval(THREAD_SWITCH_INTERVAL_S)  # the window gets its turn soon while the background work runs
    window.show()
    open_error = ""
    if len(argv) > 1:  # opened after the window: the part saved in the file shows at once, the plan follows (V9)
        try:
            model.open(Path(argv[1]))
        except ModelError as error:
            open_error = f"Cannot open {argv[1]}: {error}"  # a windowed .exe has no console: say it in a box
    if open_error:
        QMessageBox.warning(window, APP_NAME, open_error)
    if model.settings_message:
        QMessageBox.warning(window, APP_NAME, model.settings_message)
    if convention_problems():  # conventions.json (File > Preferences) was read when the constants loaded
        QMessageBox.warning(window, APP_NAME, "Some entries of conventions.json cannot be used and were ignored:" + chr(10) + chr(10).join(convention_problems()))
    return application.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
