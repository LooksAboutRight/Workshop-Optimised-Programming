"""Work in the background for the window: a job runs in its own thread, its result comes back in the window's thread.

`AppModel.run_in_background(BackgroundRunner(window).start)`: the model plans and checks a changed program this way, so the
window does not freeze while it waits. Python runs one thread at a time: the window gets its turn every
`THREAD_SWITCH_INTERVAL_S` (set by `app.py`), so it stays usable; the work is not made faster.
"""

from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal, Slot


class BackgroundRunner(QObject):
    _finished = Signal(object, object)  # (what to call, the result): sent from the job's thread, received in the window's

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._finished.connect(self._deliver)  # the runner lives in the window's thread: the signal is queued there

    def start(self, job: Callable[[], object], done: Callable[[object], None]) -> None:
        """Run `job()` in a new thread; `done(result)` is called in the window's thread when it is ready. The thread starts after the
        window has handled what is waiting (a repaint: the part saved in the file is drawn before the plan begins)."""
        thread = threading.Thread(target=lambda: self._finished.emit(done, job()), daemon=True)
        QTimer.singleShot(0, thread.start)

    @Slot(object, object)
    def _deliver(self, done: Callable[[object], None], result: object) -> None:
        """A slot of the runner, which lives in the window's thread: Qt queues the signal of the job's thread to it."""
        done(result)
