# WOP tools

All commands are run from the project root (the folder that holds `wop/`, `tools/`, `examples/`), for example `python tools/wop_run.py ...`.
Ask any tool with arguments for help: `python tools/<name>.py --help` (only the ones using argparse: `wop_run`, `make_animation`).

## Daily use

### wop_app.py: start the window
`python tools/wop_app.py [-p [report]] [project file]`
- `project file`: open this project at start (optional)
- `-p` / `--profile`: measure where the time goes; a text report is written when the window closes
- `report`: report file name after `-p` (default `wop_profile.txt`)
- `--selftest`: no window; checks that all parts are loadable and writes `wop_selftest.txt` (used by `build_exe`)
- Needs PySide6.

### wop_run.py: check a project, write G-code and a picture (no window)
`python tools/wop_run.py project.wop.json [options]`
- `project`: the project file (required)
- `--block N`: run only block N (1 = first); the material left by the blocks before it counts
- `--out FOLDER`: output folder (default `wop_output`); writes `<name>.ngc` and `<name>.svg`
- `--machine FILE`: machine definition; checks sizes, RPM and power
- `--accept-all`: accept every suggested remedy of the postprocessor

### make_animation.py: video of the machining of a project
`python tools/make_animation.py project.wop.json [options]`
Needs PySide6 (or playwright with Chromium, or ImageMagick with SVG support) and ffmpeg on PATH (Windows: `winget install ffmpeg`, then open a new terminal). Without ffmpeg a GIF is written.
- `project`: the project file (required)
- `--out FILE`: result, `.mp4` or `.gif` (default `animation.mp4`)
- `--step MM`: mm of path per frame while cutting (default 1; smaller = smoother and longer)
- `--rapid-frames N`: frames per rapid move (default 6)
- `--fps N`: frames per second of the video (default 25)
- `--width PX`, `--height PX`: video size (default 1280 x 720)
- `--view side|3d`: 2D side view or 3D view (default `side`)
- `--steps-per-turn N`: 3D only, how smooth round surfaces are (default 24); the 3D view of a video is made as SVG by `scene_svg.py` (sorted triangles, no graphics card needed), not with OpenGL
- `--blocks A-B`: only these blocks, for example `3` or `2-4` (1 = first)
- `--max-frames N`: stop after N frames (a test run; try `200` first)
- `--realtime N`: time-true from feed and RPM, N times faster than the machine
- `--jobs N`: processes, one block per process (default 1; `0` = all processors)
- `--rasterizer auto|qt|chromium|imagemagick`: how SVG becomes PNG (default `auto`: Qt first)
- `--png-folder FOLDER`: write PNG files there instead of a video
- Helper module `animation_frames.py` makes the frames; it is not run by itself.

### make_screenshots.py: pictures of the window and every dialog (to check layout and colours)
`python tools/make_screenshots.py [folder]` (default folder `screenshots`, not in the repository)
- Takes pictures of: the window with every block of the example projects (2D and 3D), a new block, tool and workholding of every type, every menu, every dialog that a menu entry opens (with its tabs and the pages of its lists), the shape editors, the sketch editor (`special_sketch_editor`, tray closed and open), a post with a problem (red page, red line), the export questions.
- The names are `<what>_<dark or light>.png`. The theme is the one of Windows: run it, change the theme by hand, run it again into the same folder, and compare the pairs. Nothing of the system is changed.
- It uses a temporary folder for settings and copies of the example projects; the menu entries Save, New project, Quit and the folders are not triggered. `_problems_<theme>.txt` lists what failed and what was skipped.
- A view that needs a state made by hand is a scene in `special_scenes` in the tool.
- Limits (what the pictures do NOT show):
  - Only the state after a click: no open dropdown or popup, no hover text, no focus frame, no field being edited, no drag. (For the manual, `tools/manual_scenes.py` makes pictures with a menu, a dropdown or a hover text open: see `make_manual.py` below.)
  - Pictures of a widget, not of the screen: no title bar, no window frame, no Windows dialog (file chooser, colour chooser); a file chooser or a question box of the program is answered with nothing, so what happens after it is not shown.
  - The window has a fixed size (1600 x 950); a smaller window may lay out differently. The Setup, the tool and the other views are shown with the example projects and a new object of each type, not with the user's own data.
  - Dialogs that only a button inside a form opens are not found by themselves (only those listed in `special_scenes`); lists with more than 40 rows are not walked; only the first level of tabs and lists inside a dialog.
  - Error and warning states only where a scene makes one (a post with a problem, the example project with a collision, the export questions); a form with a refused value, the verification findings of other projects, the step-through and an open contour editor with problems are not made.
  - The entries Save, Save as, New project and Quit and the folder entries are not triggered; an entry that is greyed out in the start state is not triggered either (its dialog is missing).
- Needs PySide6. The window is really opened (the screen may flicker for a few seconds); it takes about 15 seconds.

### make_manual.py: build the user manual as a PDF
`python tools/make_manual.py [--pictures]`
- The manual is LaTeX in `docs/manual` (`main.tex`, `preamble.tex`, one file per chapter in `docs/manual/chapters`, the pictures in `docs/manual/images`). The PDF is `docs/manual/build/WOP_manual.pdf` (the `build` folder is not in the repository).
- Without an option it builds the PDF from the pictures that are in `docs/manual/images`. With `--pictures` it first runs `tools/make_screenshots.py` and copies the pictures the manual uses (the list `PICTURES` in the tool) into `docs/manual/images`, so the pictures follow the program. Set the Windows theme to light first: the manual is printed on white paper (the tool warns when the pictures are dark).
- Needs LaTeX: MiKTeX (`pdflatex`). The tool looks in the PATH and in the usual MiKTeX folders; missing LaTeX packages are fetched by MiKTeX the first time. It runs `pdflatex` until the contents and references have settled and reports pages, box warnings and undefined references.
- Pictures with something open above the window (a menu, the list of a dropdown, a hover text), with the mouse pointer and red callouts, the main window with its numbered parts, the right column (a form) cropped from a tall window, and the sketch editor of the raw part and of a custom path: `tools/manual_scenes.py` (run by `--pictures`, or alone: `python tools/manual_scenes.py [folder]`). A scene opens the thing from code, grabs it as a window of its own and pastes it onto the picture of the window at its place on the screen (`tools/picture_marks.py`), so nothing of the real screen or mouse is used. The pointer is drawn into the picture (white with a black edge), callouts and frames are red. `Picture.pointer`, `callout(number, at, target)`, `frame(rect)`, `add_popup(window)`, `crop(rect)`; `open_menu`, `open_dropdown`, `show_hover_text`, `entry_point`, `dropdown_item_point` open and find the popups. Add a scene as a function and list its name in `COMPOSED` of both `tools/manual_scenes.py` and `tools/make_manual.py`.
- A new picture of the usual kind: add the scene to `tools/make_screenshots.py` if it is not there, add the pair (picture, name) to `PICTURES`, and use `\shot{name}{caption}` in a chapter. `tests/test_manual.py` checks (without LaTeX) that every file, picture and reference of the manual exists.

### install_linux.sh: install WOP on Linux (tested on Debian 13 only)
`tools/install_linux.sh [--prefix DIR] [--uninstall] [--dry-run]`: makes a venv (default `~/.local/share/wop`), installs the repository into it with pip (`.[gui]`: ezdxf, numpy, PySide6), writes the start command `~/.local/bin/wop` and a menu entry, and runs the self-test (`QT_QPA_PLATFORM=offscreen`). It needs Python 3.11 or newer with the venv module (Debian: `sudo apt install python3-venv`) and an internet connection; run it as your normal user, never with `sudo` (it refuses root), and with `bash tools/install_linux.sh` when the file lost its executable mark (copied from Windows); it says which Debian packages of the Qt xcb plug-in are missing (checked with `dpkg -s` before the install, and with `ldd` after it; the packages are also listed in the README). The core is not compiled in this install. `--uninstall` removes it all; the settings in `~/.config/WOP` stay. Run on Debian 13 on 2026-10-30: it works (no other Debian version or distribution is tested, the user's decision); the buttons of some dialogs look a little different from Windows (the Qt style).

### install_linux_compiled.sh: install WOP on Linux and compile the core (worked on an Intel N100 lathe PC)
`tools/install_linux_compiled.sh [--prefix DIR] [--uninstall] [--no-desktop-icon] [--dry-run]`: runs `install_linux.sh` with the same options, then installs `mypy` and `setuptools` into its venv, builds the core with `build_compiled.py` in a temporary copy of the repository (nothing is written into the repository), copies the compiled files to the same places in the installed package (the modules next to their sources, the shared file `wop_compiled__mypyc...` next to the folder `wop`), checks that Python takes the compiled file, and runs the self-test again. It needs `gcc` and `python3-dev` (Debian); without them, or when anything fails, the plain install stays and the script says `NOT COMPILED` with the reason (exit code 3). `install_linux.sh` run again removes the compiled files (pip does not know them).

### build_exe.py: build WOP.exe (run on Windows)
`python tools/build_exe.py [options]`
First time: `pip install pyinstaller` (PySide6 and ezdxf must be installed too).
- `--name NAME`: program name (default `WOP`)
- `--onefile`: one `.exe` file (default: a folder `dist/WOP/` with `WOP.exe`, starts faster)
- `--console`: also show a text window (use it when the `.exe` does not start, to see the error)
- `--icon FILE.ico`: program icon
- `--dist FOLDER`, `--work FOLDER`: result folder (default `dist`) and working folder (default `build/pyinstaller_work`; never start an `.exe` from there, only from `dist`)
- `--zip`: also pack the result into `dist/WOP-<version>-windows.zip` (the version of `pyproject.toml`), after the self-test; the zip holds the folder `WOP` without the self-test report and without the builder's own settings in `user_data` (only its README); the SHA-256 of the zip is printed
- `--no-test`: skip the selftest after the build
- `--plain`: do not compile the core first, and remove compiled files left from an earlier build (see `build_compiled.py`; without mypyc it is not compiled anyway, the `.exe` is then slower)
- Copies the PDF of the manual (`docs/manual/build/WOP_manual.pdf`, made by `make_manual.py`) next to the `.exe` when it exists, and says so when it does not.
- Copies `LICENSE`, `THIRD_PARTY_NOTICES.md` and the folder `licenses` (LGPL-3.0 and GPL-3.0 texts, for the Qt libraries in the folder) next to the `.exe` (folder mode).
- Creates `user_data` next to the `.exe`: settings, machines and libraries are kept there (portable). Without that folder they are in `%APPDATA%\WOP`.
- Folder mode: it removes what WOP does not use from the built folder (`PRUNE`: Qt translations, unused Qt plug-ins and DLLs, the C speed-ups and C sources of ezdxf; PIL, lxml, yaml and the unused Qt modules are excluded): 133 MB instead of 198 MB, 56 MB zipped. Kept on purpose: `opengl32sw.dll` (20 MB, the software OpenGL for a computer without OpenGL 2).
- Afterwards it starts the `.exe` with `--selftest` and says OK or FAILED: every part found by name, a DXF written and read, the main window built and painted (Qt platform `offscreen`); the report also says how many modules of the core run compiled.
- First it compiles the core with `build_compiled.py` when mypyc is installed.

### build_compiled.py: compile the core (about twice as fast)
`python tools/build_compiled.py [--clean]`
First time: `pip install mypy setuptools`, and a C compiler: on Windows the C++ build tools of Visual Studio (Visual Studio 2022 Community with 'Desktop development with C++' is enough).
- Compiles the modules listed in `wop/core/compiled.py` (`COMPILED_MODULES`: the geometry, the chains, the tests of the analytic planner) with mypyc, in about 10 seconds. The compiled files (`.pyd`) lie next to the sources, the shared one (`wop_compiled__mypyc...pyd`) in the project folder; they are not in git.
- The program is the same with or without them, only faster with them (left_hand_rest_machining: planning 3.3 s instead of 6.8 s, the check 1.0 s instead of 2.1 s).
- After a change of one of the compiled sources run it again (or `--clean`): Python takes a compiled file instead of its source, so an old one hides the change. `tests/test_compiled_current.py` fails then.
- `--clean`: remove every compiled file, WOP runs as plain Python again.

## Make example files

### make_example_project.py
`python tools/make_example_project.py [file]`: writes the reference project (default `examples/reference.wop.json`; its tools are made from codes: an ISO holder with a VNMG insert and a small boring bar).

### make_block_examples.py
`python tools/make_block_examples.py [folder]`: one small project per block type (default `examples/blocks`), except the custom path: its example (trepanning in a groove, with a tool drawn for it) is saved from the window.

### make_machine_tests.py
`python tools/make_machine_tests.py [folder]`: the air-cut projects for the first day on the lathe (default `wop_output/machine_tests`, not kept in the repository: basics, arcs, thread, four single drilled holes) and the back boring test; the shipped LinuxCNC post writes G41 / G42. The fourth test is `tests/data/projects/compensation_test.wop.json` (`make_compensation_test.py`).

### make_collision_demo.py
`python tools/make_collision_demo.py [file]`: a project that gives collision findings (default `tests/data/projects/collision_demo.wop.json`, a test project).

### example_values.py
Not a tool: the cutting values of the example projects (mild steel, coated carbide, a lathe of 2.5 kW: roughing CSS 150 m/min and feed 0.2, finishing CSS 180 and feed 0.1, boring CSS 100, grooving CSS 80, drilling 1400 rpm, threading 500 rpm), used by `make_example_project.py` and `make_block_examples.py`. The pawn, the rest machining example and the custom path example are saved from the window with the same numbers.

### make_example_machine.py
`python tools/make_example_machine.py [file]`: writes `examples/example.machine.json` (placeholder values, edit them), or the file given.

### make_example_post.py
`python tools/make_example_post.py [file]`: writes `examples/posts/linuxcnc_custom_function.post.ini`, made from the shipped LinuxCNC post plus a custom machine function (a bar feeder: three codes, a modal group, the concept `bar_feed`). It follows the LinuxCNC post: `tests/test_examples_current.py` fails when the committed file is not what the tool writes.

### make_example_post_ramp.py
`python tools/make_example_post_ramp.py [file]`: writes `examples/posts/linuxcnc_spindle_ramp.post.ini`, made from the shipped LinuxCNC post plus a speed ramp before every spindle stop (the settings `spindle_ramp_*`, the template `[spindle_ramp_step]`, the token `<spindle ramp>`). `tests/test_examples_current.py` fails when the committed file is not what the tool writes.

## Checks and tests

### check_small_screen.py: do the windows fit a small screen
`python tools/check_small_screen.py [--width 1024] [--height 768] [--taskbar 48]`: builds the main window (both side panels open, one shut, both shut) and every dialog offscreen with the Windows font Segoe UI 9 and prints the smallest size each lets the user make it; exit 1 when one is larger than the free part of the screen (screen less taskbar, less the room of the frame: `SCREEN_MARGIN_X_PX`, `SCREEN_MARGIN_Y_PX`). Without the font it says so and checks nothing. `tests/test_small_screen.py` runs it. Not measured: Windows display scaling (125 % makes everything larger) and touch.

### run_tests.py: all tests in several processes (about a minute)
`python tools/run_tests.py [-j N] [--fresh] [module ...]`
- no module: every test; first all example and test projects are planned at once, then the test modules run, the longest first
- `module`: only these, for example `tests.test_verify`
- `-j N`: processes (default 8)
- `--fresh`: every test module in a new process (slower; finds a module that only passes because another one loaded something first)
- prints one line per module, the full text of every failure, then `OK` or `FAILED`; keeps the times of the modules in `.test_times.json` (git ignores it)
- `python -m unittest discover -s tests -t .` still runs everything in one process (about 5 minutes)

### check_conventions.py
`python tools/check_conventions.py [core_dir]`: checks the coding rules of `wop/core` (numbers, module dicts, imports). Prints `conventions ok` or the violations; exit code 1 on violations.

### make_compensation_test.py
`python tools/make_compensation_test.py [file]`: writes `tests/data/projects/compensation_test.wop.json`, a test project: the project for the air-cut test of cutter compensation (facing, rough turning along a contour, finishing with 'Cutter compensation' ticked; the contour has a chamfer, a round corner and a taper).

### list_post_tokens.py
`python tools/list_post_tokens.py`: prints the concepts, the tokens and the options of the post engine as Markdown tables (the registry in `wop/post/tokens.py` is the one source). No arguments.

## Sandbox only (not for your PC)
`tools/sandbox_standin/` runs the tests in a sandbox without shapely and PySide6. You do not need it on your machine.
- `run_tests.py tests.<module>`, `run_script.py <script> [args]`, `run_all.py [jobs] [module ...]`
