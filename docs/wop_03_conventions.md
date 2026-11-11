# WOP: Conventions

How code and docs are written here. `tools/check_conventions.py` (also run by a test) checks what a tool can check.

## Code
- Layers: core (pure Python) -> post -> adapters (files, DXF) -> ui (`AppModel`, forms, no toolkit) -> `ui/qt` (PySide6). A lower layer never imports a higher one; core imports no ui, adapters, post, GUI toolkit or linuxcnc. ezdxf only in `wop/adapters/dxf_files.py`, PySide6 only in `wop/ui/qt/`.
- Small files, dataclasses as structs. A source file of more than 600 lines or a function of more than 200 lines fails `tests/test_source_size.py` (tests are not counted): split by topic.
- No module-level dicts in `wop/core` outside `wop/core/constants.py`. Constants of other layers: `wop/ui/app_constants.py`, `wop/ui/ui_constants.py`, `wop/post/post_constants.py`. Insert new constants before the `REPLACED_DEFAULTS = ...` line at the end of `constants.py`.
- A value someone would tune (a clearance, a tolerance, a default, a catalogue value) is a constant. A number whose meaning is plain where it stands (an index, a half, a count of corners) and whose effect stays inside its function may be written in place.
- A constant the user may change goes above the line `NOT_EDITABLE_BELOW` and gets an entry (heading, meaning, rule) in `wop/core/conventions.py` (File > Preferences); the user's values are in `conventions.json` (only the changed ones, unknown names are ignored and reported). `tests/test_preferences.py` fails when the two disagree.
- Compiled core: the modules of `wop/core/compiled.py` are compiled with `tools/build_compiled.py` (mypyc). They must pass mypy and have no free attributes (use fields with `init=False`). After a change build again or `--clean`: Python takes the compiled file and an old one hides the change.
- A guessed value (a standard, a catalogue) is a constant in the code, a note in the form and a line marked GUESS in the design notes.
- Files are LF.

## Data
- Units mm. X is the radius (diameter only at the UI and G-code boundary), Z is axial; Z is drawn to the right, X up, the chuck on the left. Angles are counter-clockwise from +X towards +Z; feeds are mm per revolution.
- The input mode is per X field (Dia. / Rad. button); the G-code mode (G7 / G8) is one setting; the post converts.
- Every block sets spindle and coolant at its start and does not switch back at its end.

## Files
- Before the first release (0.1) there is no backwards compatibility for project and machine files: change the example and test files. From 0.1 on every file of a release (project, machine, settings, library, post) must keep opening: a change of a format gets a converter (the format number in the file) and a test with an old file.

## Docs
- Four documents in `docs/`: the design notes, the requirements, these conventions and the code tour. Short bullets, the current state only, no history (that is git log).
- Requirements: one row names one concept in a few words; IDs are stable (never renumber or reuse one); each acceptance criterion is a line that can become a test.
- `tests/test_docs_sync.py` fails when a document names a file in backticks that does not exist.

## Pitfalls
- Exact geometry needs one tolerance policy and retries where a boolean meets a coincidence.
- The material a block hands on must come from its moves, never from bookkeeping.
- A Python error in a Qt slot is only printed: tests call model and window code directly; errors go to `wop.log`.
- Defer form rebuilds out of edit handlers and check that a widget still exists in deferred calls.
- A post remembers modal values: generate on a fresh copy.
- One truth for a value that is shown and used (the machine of the project), with a test.
- A planning thread needs `sys.setswitchinterval` so the window stays quick; tools that touch files work on copies.
- Speed work: keep every real gain when plans, findings and G-code stay identical; profile before and measure after without the profiler; count `removal.cut` calls or alternate old and new on single projects, a wall-clock total shows only gains above 4 %.
