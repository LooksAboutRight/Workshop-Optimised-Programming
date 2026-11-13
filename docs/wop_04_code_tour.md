# WOP: a tour of the code (what calls what, and why)

For a reader who knows the program from the window and wants to find the way in the code. It does not explain single lines. It says which file does what, in which order things are called, and why the parts are separate. The rules of the project are in `CLAUDE.md`, the design in `wop_01_design_notes.md`. If this page and the code disagree, the code is right: say so and the page is corrected.

Contents: 1 the map, 2 the central idea, 3 from a block to G-code, 4 roughing, 5 the window, 6 the other blocks, 7 the checks, 8 contours and the sketch editor, 9 tools, workholding, 10 posts in more detail, 11 files, settings, libraries, conventions, 12 styles, 13 pictures, 3D and the stepper, 14 where to look when ... Written 2026-10-24 from the code; if something here is wrong, say so.

## 1. The map

There are five layers. A layer may use the layers above it in this list, never below.

| Layer | Folder | What it is | Why it is separate |
|---|---|---|---|
| core | `wop/core` | The model and the rules: raw part, tools, contours, blocks, the planning of the moves, the checks. Pure Python, no library for the areas (`wop/core/geometry`). | It must run without a window and without LinuxCNC, so it can be tested on any PC. |
| post | `wop/post` | Turns the neutral list of moves into G-code, using a text file per controller. | A new controller is a new text file, not new Python. |
| adapters | `wop/adapters` | Everything that touches files or the outside: project, machine and library files, DXF, LinuxCNC ini and tool table. | The core never opens a file. |
| ui | `wop/ui` | `AppModel` (the state of the application and every action) and the forms, without any toolkit. | The behaviour of the program is testable without a window. |
| ui/qt | `wop/ui/qt` | The PySide6 window. It only shows the model and calls it. | The only place that knows Qt. |

The rule behind the layers: `tools/check_conventions.py` fails if a lower layer imports a higher one.

Plug-in kinds register themselves and are found by name: blocks (`BLOCK_TYPES`), tool types (`TOOL_TYPES`), workholding and block styles. A new file in the right folder is enough; nothing else has to be changed. That is why `wop/core/blocks/__init__.py` is only a list of imports.

### The folders in one line each

- `wop/core`: `constants.py` (all fixed numbers), `conventions.py` (the numbers the user may change), `compiled.py` (the modules `tools/build_compiled.py` compiles with mypyc, and the test that the compiled files belong to the sources), `contour*.py` (contours), `reach.py` and `verify.py` (collision checks), `passes.py` (the levels of passes), `material.py` (materials); the rest in topic folders:
- `wop/core/program_model`: `program.py` (the program and `plan_program`), `project.py`, `raw_part.py`, `raw_outline.py` (a raw part drawn in the sketch editor, opened from the Setup form by `AppModel.raw_part_sketch_target`: its stock, its numbers, the sketch to start from; the rule is `core/sketch/raw_part_rule.py`), `stock.py` (the material as areas), `operations.py` (the neutral moves), `units.py`, `plan_cache.py` (what the last plan worked out per block: `plan_program` and `verify_plan` take a block from it when its inputs and its material before are the same; the window keeps one).
- `wop/core/tooling`: `tool.py` and the `tool_*` files, the standard shapes (`*_tool_shape.py`, `holder_tools.py`), the designations of inserts and holders.
- `wop/core/lathe`: `machine.py` and `machine_check.py` (the machine and its check), `workholding.py`, `assembly.py` (components and sets), `power.py`, `spindle.py`.
- `wop/core/files`: what is saved and loaded (`*_io.py`, `dataclass_codec.py`), the user folder, the settings, the libraries and the user's conventions.
- `wop/core/blocks`: one file per block type (`facing.py`, `turning.py`, `turning_contour.py`, `grooving.py`, `drilling.py`, `threading.py`, `custom_path.py`, `machine_function.py`), the shared base `base.py`, and what the turning blocks share (`turning_common.py`, `turning_job.py`: the side, the direction, the merging of rapids). The turning planner itself is `wop/core/analytic` (section 15).
- `wop/core/geometry`: the fast geometry (section 16): points and pieces, the areas (`Region`), the tool as loops of edges, what a move sweeps; it imports nothing of WOP but the constants.
- `wop/core/tool_types`, `wop/core/sketch`: the tool types with their forms, and the sketch (points, lines, arcs, relations, solver) that draws contours, tools and holding outlines.
- `wop/post`: `engine.py` (writes G-code from a post file), `tokens.py` (what a template may contain), `post_definition.py` (reads a post file), `generate.py` (runs a plan through a post), `context.py` (what a post may know besides the moves), the posts themselves in `wop/post/posts`.
- `wop/ui`: `app_model.py` and `wop/ui/model/*` (the actions by topic), the forms (`block_forms.py`, `setup_form.py`, ...; `display_units.py` converts lengths when the window shows inches), the 2D picture as SVG text (`svg_preview.py`), the 3D scene as numbers (`view3d.py`: meshes, lines and fills, no SVG; drawn with OpenGL by `ui/qt/gl_view.py`), `stepper.py`, `error_log.py` and `crash_log.py` (what the program writes to `wop.log`, and the stacks of a crash to `crash.log`).
- `wop/ui/qt`: `main_window.py` and the pieces of the window, one file per view or dialog. `small_screens.py` keeps the windows usable on a screen of 1024 x 768: `scrolling` puts a page into a scroll area (so it does not set the smallest size of the window), `ScreenFitFilter` makes a window that opens larger than the screen smaller; `panel_splitter.py` lets a shut side panel count as nothing in the width of the window, and has the `StackSplitter` between the picture and the messages (the user drags the border).

## 2. The central idea: blocks make operations, a post makes text

```
  Project (what the user edits)
     │   Program = raw part + tools + contours + blocks      core/program_model/program.py
     ▼
  plan_program()                                           core/program_model/program.py
     │   for every block:  block.generate(context)          core/blocks/*.py
     ▼
  ProgramPlan = per block: neutral OPERATIONS + removed area + notes
     │                                                      core/program_model/operations.py
     ├──► pictures, 3D, stepper, checks   (read the plan)
     └──► generate_gcode(plan, post)  ───►  G-code text      post/generate.py
```

The operations are neutral: `Rapid(point)`, `LinearMove(point, feed)`, `ArcMove(...)`, `ToolChange(n)`, `SetSpindle(...)`, `ThreadOperation(...)`, and so on. They say what the machine does, not how a controller writes it. This one list is used by everything: the picture, the collision check, the power estimate, the stepper and the post. That is the reason the blocks do not know any G-code, and the post does not know any geometry.

## 3. From one block to G-code, step by step

Example: the reference project, a turning block "outside, along Z". Window or command line, the path is the same.

### 3.1 The data

- A `Block` (a frozen dataclass, `core/blocks/base.py`) holds only what the user typed: tool number, spindle, target radius, end Z, feed, depth of cut, allowance. The form in the window is made from these fields (see 5).
- `Program` (`core/program_model/program.py`) holds the raw part, the tools, the contours, the safe positions and the blocks.
- `Project` (`core/program_model/project.py`) is the program plus the settings that belong to the file (title, X mode, work offset) and a copy of the machine.

All of these are immutable: an edit makes a new object (`dataclasses.replace`). That is why undo is a list of old projects, and why a plan can be cached "for the same program object" (`_plan` in `ui/model/views.py`).

The undo list is small. It lives in memory only (nothing is written until Save), and the old states are not copies: `replace` builds a new top-level object but points to every part that did not change (the other blocks, the tools, the contours, the machine). One edit therefore costs a new block plus a few small wrapper objects, a few hundred bytes to a few kilobytes. The list keeps at most `UNDO_LIMIT` states (200, editable in Preferences) and drops the oldest. No plan or picture is stored in it; they are made again from the project. The sketch editor has its own undo list while it is open, and only the finished contour goes into the project history.

### 3.2 `plan_program` (core/program_model/program.py)

It is the loop over the blocks (the small helpers around it: `_reason_to_skip`, `_generate`, `_moves_before`, `_block_operations`, `_advance`, `_closing`; `_MachineState` holds position, tool, spindle and coolant between blocks). For each block:

1. `program.contour_problem(block)`: does the contour exist? If not, the block is left out with a reason.
2. `program.equipped_tool(n)`: the tool, moved so that its reference point is the origin, .
3. `BlockContext(raw_part, tool, residual, safety, contours, jaws)`: everything the block may know. `residual` is the material that is still there after the blocks before. Note: the block gets the material, not the previous block. Blocks are independent of each other.
4. `block.generate(context)`: the block returns a `BlockResult` (operations, the removed area, messages). An error is caught: that block is left out, the others are still planned.
5. Around the block's moves, `plan_program` adds what is the same for every block: the rapid to the safe or tool change position, `ToolChange`, `SetSpindle`, `SetCoolant`. So a block never writes its own tool change.
6. `residual = residual - result.removed`. The next block starts with the smaller material. `split_off` removes a piece that a cut has separated from the part.

At the end it adds the closing moves (rapid to the change position, spindle stop) and returns `ProgramPlan`. Every block starts from an unknown machine state, so a plan of one selected block is also complete.

### 3.3 A turning block generates (core/blocks/turning.py, turning_contour.py)

`TurningBlock.generate(context)` works out the outline from the form (the stock radius from the residual, the Start Z, `_outline`: face, chamfer, shoulder, fillet) and plans it as a contour block on that outline (`_as_contour`); facing does the same (`FacingBlock`). So every turning block ends in `ContourTurningBlock.generate(context)`:

1. `_analytic_inputs`: what the planner needs from the form and the material, as a `PlanInputs` (the contour with its last wall run on to the material, the material as loops, inside or outside, the direction of the lines, the front).
2. `whole`: the area between the stock and the contour (`wanted_lines.removal_ring`). Nothing there: a note and no moves.
3. `_analytic_roughing`: the cut list of the analytic planner (`roughing_cuts`, section 15), as moves (`cut_operations`), and the notes.
4. `_analytic_finishing` when the block has a finishing pass (`cut_operations.finishing_pass`).
5. The `BlockResult`: the block begin, a rapid to the start point (outside; inside the first rapid goes straight over the bore), the roughing, the finishing pass, the block end; removed is what the roughing took (`_taken`: the material minus what the cut list leaves), and with a finishing pass all of `whole` (it follows the contour); `protected` is everything outside `whole`.

Planning rule (CLAUDE.md): the geometry to cut comes from the form values only. The tool body is only asked in the roughing, where a line is shortened or left out if the tool body cannot reach; the finishing pass follows the contour whatever the tool can reach.

### 3.4 What the plan holds

`ProgramPlan.blocks[i]` is a `BlockPlan`: the block, its operations (with the tool change and spindle in front), the `BlockResult`, the residual before and after. The 2D picture (`ui/svg_preview.py`), the 3D scene (`ui/view3d.py`), the stepper, `verify_plan` (collisions), the power estimate and the machine check all read this one structure.

### 3.5 From the plan to text (post/generate.py, post/engine.py)

`ui/model/export.py: gcode()` does the set-up:

1. `plan = self._plan(...)`: the plan (cached).
2. `post_library.choose(id)` loads the post definition from the file; `TemplatePost(definition)` is the engine.
3. `make_context(...)` (`post/context.py`): what a post may know that is not a move (tool names, offsets, the block list, the project title, the work offset).
4. `generate_gcode(plan, post, settings, accepted, notes, context)`:
   - `find_issues`: (one small function per kind of operation: `_operation_issues`) what the controller cannot do (a post without constant surface speed, without arcs). Each issue has a remedy the user may accept; a block with an open issue is left out and the result is marked incomplete.
   - `post.header(...)`: the `[header]` and `[setup]` templates.
   - For every operation `_emit` calls the matching method of the engine: `post.rapid`, `post.linear`, `post.arc`, `post.tool_change`, `post.thread`, ... A rapid to where the tool already is, is skipped.
   - `post.footer()`.

In the engine (`post/engine.py`) each method does the same: put the numbers of the operation into a scope and call `render_concept("feed", scope)`. That takes the template lines of the concept from the post file (`post/post_definition.py`) and fills them: each `<token>` is a registered function in `post/tokens.py` that reads the scope and the engine state. Options such as `changed` (leave it out if it is the same as last time), `diameter`, `decimals` change how a value is written. A line whose tokens are all empty disappears. The engine state (`EngineState`) is the memory for "changed": last position, last feed, last code of every modal group.

Example, the line `G1 Z-5 F0.2`: `Block.generate` made `LinearMove(Point(x, -5), 0.2)`. `post.linear` put x, z and feed into the scope. The template of `[feed]` in `linuxcnc.post.ini` is `<code feed changed>[ X<X changed>][ Z<Z changed>][ F<F changed>]`. `<code feed changed>` is `G1`, left out when the last motion code was G1 already; `X` is left out because X is the same as the last position; `Z-5` and `F0.2` are new, so they are written.

### 3.6 Why it is built this way

- One list of operations for everything: a picture and a G-code can never disagree, and a collision check sees exactly what the machine would do.
- Blocks get material and tool, not each other: a block can be planned alone (export of a selection), and a failing block does not stop the others.
- Immutable data: undo, caching and "the same program, the same plan" cost nothing.
- Posts as text: the user can change a post without Python, and the engine is tested with invented posts.

## 4. Roughing in one example

Outside, along Z, bar 30 to 20 mm, depth of cut 1, allowance 0.2 (the details are in section 15).

`wanted_plan` (`analytic/wanted_plan.py`) makes the area to rough: the material minus the part grown by the allowance, as loops of exact lines and arcs. Lines are laid through it at the radii 15, 14, 13 ... down to 10.2 (`levels` in `passes.py`, from the raw bar); where a line crosses the border of the area it is cut into stretches. A stretch with a wall at both ends is a pocket line (the plunge depth of cut).

`roughing_cuts` (`analytic/roughing_cuts.py`) takes the lines from the front, level by level (or in the order of the roughing style, `rough_style.style_sequence`). For each stretch: `reach.end_intervals` shortens it to where the tool may stand without its body touching the part, `ride_up` lets the tool ride up the contour at the end, `_entry` finds the way in (from the air along the line, or down along the wall of a pocket), `removal.cut` takes away what the tool sweeps from the material, and the next line works on what is left. At the end the passes along the contour under the lines (`dips.py`) and the rapids between the cuts (`rapids.connect_cuts`: one clearance from the material, X12). `cut_operations` turns the cut list into moves.

## 5. The window

```
click / typing in a form
    │  window_parts/form.py: _value_edited
    ▼
AppModel.replace_block(index, new_block)          ui/model/blocks.py
    │  (fills fields that follow others, derived fields such as a thread designation)
    ▼
AppModel._changed()                               ui/app_model.py
    ├─ _record()         remember the project for Undo
    ├─ refresh()         analysis = plan + checks  ui/model/views.py: _analyse
    │                    (in the window: in the background, see below)
    └─ listeners         the window's _model_changed
                           ├─ _fill_flow()   the block list
                           ├─ _redraw()      model.picture() → SVG, or the 3D scene
                           ├─ _fill_messages()
                           └─ _show_form()   the right panel
```

In the window the plan and the check run in the background (`AppModel.run_in_background`, set by `ui/qt/app.py` with
`ui/qt/background.py: BackgroundRunner`; the tests and tools have no runner and work at once):

```
refresh()                       the shown Analysis stays, marked working=planning
    ├─ job in a thread: _planned(program)     the plan of this program (plan_program with the block cache)
    │      └─ in the window's thread: analysis = plan, working=checking → listeners of subscribe_results
    │                                         (the window's _results_arrived: flow list, picture, messages; not the form)
    └─ job in a thread: _checked(...)         estimate_power (one sum per block) and verify_plan (with the block cache)
           └─ in the window's thread: analysis = plan + findings → _results_arrived
```

- A newer change counts up `_generation`: the older job stops before its next block (`should_stop`, `PlanningStopped`) and
  its result is not shown. The caches are used under `_work_lock`, by one thread at a time.
- After `open`, the analysis holds the finished part saved in the file (`Analysis.preview`, V9): the picture and the 3D view draw it until the plan is there (`_preview_plan`); `save` writes the part of the shown plan (`_finished_part`, `project_io.project_to_json(project, preview)`).
- `analysis_now()` is what the export uses: the shown analysis when it belongs to the current program and is finished, else
  worked out at once (an export never uses the plan of an older program).
- `core/program_model/plan_cache.py: PlanCache` (one per model): a block with the same inputs and the same material before it is taken
  from the last plan; its check too. So after a change only that block and the later ones are new.

- `AppModel` (`ui/app_model.py`) is made of mixins by topic in `wop/ui/model/` (blocks, tools, setup, machines, posts, export, views ...). A new action goes into the part of its topic. The model holds the project, the undo list, the selection and the last `Analysis`. It never imports Qt.
- A form is made from the fields of a dataclass (`ui/block_forms.py`: `FieldSpec`), so a new block type needs no form code. A block or form can add hooks (`form_fields`, `form_labels`, `form_headings`, `form_disabled`, `field_choices`, `form_buttons`). `ui/qt/form_panel.py` turns the specs into widgets.
- `Analysis` is the plan, the findings of `verify_plan`, the notes and the power estimate. The check runs after every change (there is no Check menu and no switch; `AppModel.auto_check` is a plain attribute that tests and tools set to False when they need no check, `verify_now` checks anyway).
- The pictures are made in the `ui` layer and only drawn by the `ui/qt` layer, so they can be tested without a window. The 2D picture is SVG text (`svg_preview.py`, shown by Qt's SVG widget). The 3D view is not SVG: `view3d.py` builds a `Scene` of numbers (triangle meshes, strokes, fills) from the plan, and `gl_view.py` draws it with OpenGL (without OpenGL the 2D picture is used).
- The Setup entry, the Tools, Workholding and Contour views are modes of the same window; the model says which mode is shown (`selected`, `tools_view`, ...).

Start-up: `tools/wop_app.py` → `wop/ui/qt/app.py: main` → creates `AppModel` and `MainWindow` → `AppModel` reads the settings, machines and libraries through the adapters.

## 6. The other blocks

All blocks have the same shape: a frozen dataclass with the typed values, a `generate(context)` that returns a `BlockResult`, registered with `@BLOCK_TYPES.register`. The common work (tool change, spindle, coolant, safe positions) is done by `plan_program`, not by the block. What differs is how the moves are made.

| Block | File | How it makes its moves |
|---|---|---|
| Facing | `facing.py` | Outside in: the face line at the target as a flat contour, planned by the contour block across X (`_as_contour`, the lines run on past the centre by the overtravel), then its own finishing pass (`_finishing`, the ways in and out by `rapids.clear_way`). Centre out (`_centre_out`): passes of its own at levels from the raw bar (`pass_levels`, `passes.py`), made by `_passes` like the finishing pass. |
| Turning (simple) | `turning.py` | Works out the outline (face, chamfer, shoulder, fillet, taper) from its Start Z (`start_z`: where the material begins, `material_start`) and plans it as a contour by the contour block (`_from_start`, `_as_contour`, with `BlockContext.front_z` at the start edge); its result carries the Start Z for the greyed field (`BlockResult.shown_values`, shown by `AppModel.shown_block` and `FormPanel.show_greyed`). |
| Turning, taper | `turning.py` | `taper_deg` and `radius_at`: the outline is a cone; planned as a contour (`_as_contour`) as every simple turning block. The form shows it with its own button (`form_panel._add_taper_row`). |
| Turning contour | `turning_contour.py` | The same with a stored contour as the outline, plus the style of the roughing (section 12) and optional cutter compensation. Checks the contour first. |
| Grooving | `grooving.py` with `groove_plan.py`, `groove_style.py`, `groove_path.py` | `groove_plan` works out where the blade plunges (pure numbers). A style (section 12) decides the order and depth of plunges. `GroovePath` (`groove_path.py`) moves the blade with the `Sweeper` (`sweep.py`) so it stops before a collision, and cuts what it passes; `GroovingBlock.generate` is the list of steps: checks, the place, the plunges of the style, the way out, the report. |
| Drilling | `drilling.py` | The hole is a shape (a cone tip and a cylinder). The mode of the form (drilling, peck drilling, peck drilling with full retract) and the peck depth decide the pecks; there are no drilling styles. The block makes `DrillOperation`s or plain moves; the post decides whether to write a canned cycle (`drilling_style` in the post file). |
| Threading | `threading.py` with `thread_designation.py` | A designation such as M36x3 fills pitch, depth and angle (`with_derived_fields`). The block first turns or bores to the crest radius if needed, then makes one `ThreadOperation`. The post writes it as a cycle (G76), as packed numbers (Fanuc) or as plain passes (generic). |
| Custom path | `custom_path.py`, `path_locked.py` | A path drawn in the sketch editor (mode 'custom path', `sketch/path_walk.py` gives the order of its pieces). `resolved` puts the safe point and, when a relation refers to it, the part before the block (`path_locked_items`) into the stored sketch, solves it and makes `PathStep`s of it; `path_moves` makes the moves. The material the tool passes counts as removed. |
| Machine function | `machine_function.py` | No geometry: one operation (spindle stop, dwell, program stop, or a function of the post file with values). `needs_tool` is false, so `plan_program` adds no tool change before it. |

Shared helpers: `passes.py` (`pass_levels`, `levels`), `turning_job.py` (`merge_straight_rapids`), `uncut.py` (section 7), `sweep.py`.

## 7. The checks

There are four checks. They read the plan and none changes it. They run in `AppModel._analyse` (`ui/model/views.py`) after the plan is made; the collision and power checks always (`AppModel.auto_check` is False only in tests and tools).

```
_analyse()
 ├─ plan = plan_program(...)                       the moves
 ├─ plan.messages                                  notes the planners made
 ├─ check_against_machine(program, plan, machine)  core/lathe/machine_check.py
 ├─ estimate_power(...)                            core/lathe/power.py
 └─ verify_plan(program, plan)                     core/verify.py   (the collision check)
```

### 7.1 Notes made while planning
While a block is planned it can say that it did not do something, as a message in `BlockResult.messages`: a line was shortened because the tool body cannot reach, a pocket stays, an area stays uncut (`uncut.py: report_uncut`, requirement X8: pieces that were planned but are still in the material and big enough to matter). These notes show in the message box and in the export check. A block that raises `BlockError` is left out (`ProgramPlan.left_out`).

### 7.2 Collision check: `verify_plan` (core/verify.py)
It walks every move of every block with a model of the material (`current`, starting with `residual_before` of the block) and the tool placed at each position (`reach.py: prepare_tool`, `placed_shrunk`). At each position `check_prepared` (`reach.py`) asks three questions:
- GOUGE: does the tool body overlap the part that must stay (`protected`: the finished part, or what the block leaves standing)?
- HOLDER_IN_MATERIAL: does a holder piece run into material that is still there? Cutter pieces may.
- JAWS: does the tool touch the jaws?

Rapids also report RAPID_IN_MATERIAL. A cutting move removes the area of the tool body as it goes, so later positions see it gone. Other findings: CLAMP_PLANE (a cut behind the clamping plane) and SPINDLE_OFF (a cutting move with the spindle stopped). For a straight move it first asks the quick exact test (`_clearly_free`: the contact events of the analytic planner, `contacts.free_all_along`, with half the collision tolerance: the tool body against the finished part and the jaws, on a rapid the whole tool against the material, on a cutting move the holder), then, when that is not clearly free and the move is 1 mm long or more, the swept area (`_sweep_verdict`, which also says where a contact begins); a thin obstacle between two steps is not missed, and a clean move skips the steps. The material is kept by `_Material`: the cuts of the last moves are collected and taken out of it only when a test needs it exactly (free of the larger, older material is free of the material now). Rapid moves skip positions that are far from everything. A tool that reaches past the axis is also tested mirrored against the near side (the part is round). Each problem becomes a `Finding` (kind, block, move, point, text, remedy); the window marks the block and the export asks about them.

The planning rule of the project: the planner makes the geometry as drawn and does not hide a collision; this check reports every one.

### 7.3 Machine check and power
- `machine_check.py`: the block needs a capability the machine lacks (constant surface speed, spindle-synchronised moves for threading), the part is bigger than the machine allows, the spindle speed is out of range, a feed is too fast for the axis.
- `power.py`: the specific cutting force model, `kc * A * vc`, one sum per block from its form (`_chip`: the chip of its biggest cut) at the biggest radius it cuts. An estimate, labelled as one.

### 7.4 Checks on data
`core/contour_check.py` (crossings in a contour), `Program.contour_problem` (does the contour of a block exist and fit), `workholding_problem` and `raw_part_notes` (the clamping), `adapters/style_check.py` (a style on its samples, section 12).

## 8. Contours and the sketch editor

A **contour** (`core/contour.py: Contour`) is a list of exact lines and arcs, a name, flags for cutting edges and named points. The program stores contours separately; a block names one by id (`contour_id`). The same type is used for part outlines, tool shapes and holding outlines.

There are two ways to make one:
- **Step-wise definition:** `ContourDefinition` is a start point and steps (`LineStep`, `ArcRadiusStep`, `ArcCenterStep`, corners with fillet or chamfer). `contour_solver.py: build_contour` turns it into exact segments. Used by tests, examples and the custom path steps (`PathStep`, which the drawn path of a custom path block is turned into).
- **The sketch editor** (the normal way now): a free 2D sketch with points, lines, arcs, relations (horizontal, tangent, equal ...) and dimensions.

### The sketch (core/sketch)
- `model.py`: points, lines and arcs that share points (a shared point is a join). Every piece has an id.
- `relations.py`: each relation or dimension is a few equations that are zero when it holds.
- `solver.py`: moves the points until all equations hold (damped Newton steps, so points move as little as possible) and says how many degrees of freedom are left.
- `modes.py`: what the sketch is for (`TURNING`, `TOOL`, `WORKHOLDING`, `FREE`) and what the outline must look like in that mode. `contour_from_sketch` turns a good sketch into a `Contour` and keeps the sketch inside it, so it can be edited again; `sketch_from_contour` is the way back.
- `locked.py`: points and construction lines that a target supplies by key (`LockedPoint`, `LockedLine`); `sync_locked` brings the sketch in line with them each time the editor opens and removes the dimensions that no longer fit (with notes); the solver pins locked points, `SketchSession._edit` refuses any change that touches them.
- The rest (`corners.py` makes a fillet or chamfer (lines and arcs) and its `CornerLink`, which `model.py` keeps and repairs; `trim.py`, `mirror.py`, `loops.py`, `pick.py`; where pieces cross is `geometry/intersect.py`) are the operations of the editor.

### The editor without a window (ui)
`ui/sketch_session.py` holds the editor: the active tool, snapping, selection, undo. It is built from mixins (`sketch_action_tool.py`, `sketch_dimension_tool.py`, `sketch_modify.py`, `sketch_relations.py`, `sketch_stepping.py`: stepping through a custom path). The window (`ui/qt/sketch_dialog.py`, `sketch_canvas.py`, `sketch_toolbox.py`, `sketch_panel.py`) sends mouse positions in sketch coordinates and draws what the session says. A `SketchTarget` (`ui/sketch_target.py`) says what the editor was opened for: the mode, the start contour, and a `commit` function that stores the result. `ui/model/sketch_targets.py` makes the targets (a contour of the part, a tool shape, a workholding outline). A DXF file (`adapters/dxf_files.py` with `core/dxf_contour.py`) is read into a contour that the sketch can start from.

## 9. Tools, workholding

### Tools
- A `Tool` (`core/tooling/tool.py`) is a shape (an outline of pieces, each tagged cutter or holder), a material, a tool offset number, named points (`tip`), and for a tool made from a type its type and the definition of the form.
- **Tool types** (`core/tool_types`, registry `TOOL_TYPES`): each type is one file with a definition dataclass (its form is made from the fields, like a block form) and a `build` that draws the shape (`turning_tool_shape.py`, `holder_tools.py` for ISO holders with `insert_designation.py` and `holder_designation.py`, `groove_tool_shape.py`, `thread_tool_shape.py`, `boring_tool_shape.py`). `make_tool` adds the type and the definition, so the tool can be edited again with the same form. A tool drawn in the sketch has no type form.
- **Reference point** (`tool_reference.py`): the point where the tool is touched off (the corner of the box round the cutting edges, or the named point `tip`). `with_tip_at_origin` moves the tool so that point is the origin. That is the tool the planners and checks use: `Program.equipped_tool(n)` is the tool at its reference point with its holding attached.
- **Nose compensation** (`nose_compensation.py`): the path of the reference point that makes a round nose follow a contour (the contour moved by the nose radius). This is WOP's own compensation. With cutter compensation in the post, the nominal contour is written instead (section 10).
- The tool library is in the settings (`ui/model/tools.py`); its toolboxes (named lists of library tools with numbers, T17) are `core/tooling/toolbox.py` (data), saved in the tool library file by `core/files/tool_io.py` and `core/files/libraries.py`, edited through `ui/model/toolboxes.py`, which also puts a toolbox into a project (`apply_toolbox`, asked for by `ui/qt/toolboxes_dialog.py` and the Tools menu; a block with `NO_TOOL_NUMBER` is left out by `plan_program`, a block that needs no tool uses `core/tooling/stand_in.py`); `adapters/linuxcnc_tools.py` reads and writes `tool.tbl` (with a backup) and `core/tooling/tool_table.py` is its model.

### Workholding
`core/lathe/workholding.py`: chuck body and jaws (items of a library), the grip (outside, or inside a tube), the placement against the raw part, and the checks and notes. `reach.py: program_jaws` turns that into the region the tool must not touch (or the flat clamping plane when nothing is chosen).

## 10. Posts in more detail

The path from a plan to text is in section 3.6. The pieces of the post system:

- **The file** (`wop/post/posts/*.post.ini`): `[post]`, `[settings]` (number formats, thread and drilling style, cutter compensation yes or no), `[codes]` (names for G and M codes, so a template says `<code feed>` and never a literal G1), `[modal_groups]` (which codes cancel each other), `[functions]` (custom concepts) and one section per concept (`[rapid]`, `[feed]`, `[tool_change]` ...).
- **Reading it:** `adapters/post_files.py` reads the text, `post/post_definition.py` parses and checks it into a `PostDefinition`, `post/template.py` reads one template line (text, tokens, optional parts in square brackets), `post/concepts.py` lists the concepts (which are needed), `post/modal_groups.py` the groups. A concept that the post lacks is taken from the `generic` post.
- **Tokens** (`post/tokens.py`, one registry): each has a name, the concepts it works in, the options it accepts, and a function that reads the scope and the engine state. `post/token_codes.py` has the `<code>` token and the compensation codes. `python tools/list_post_tokens.py` prints the list.
- **Features and issues:** each post lists what the controller can do (`Feature`: diameter mode, arcs, constant surface speed ...). `generate.find_issues` compares that with what the plan uses and offers remedies (fixed RPM, arcs as short lines, radius values).
- **Cutter compensation:** in a finishing pass with the box ticked, the planner marks the lead-in and lead-out (`MoveRole`) and gives each move the nominal contour point (`contour_end`). A post with `cutter_compensation = yes` writes the contour point and G41 or G42 on the lead-in, G40 on the lead-out; otherwise it writes WOP's offset path.
- **The editor:** `ui/post_editor_model.py` keeps the text of one post, changes it section by section, checks it and makes sample output (`post/samples.py`); `ui/qt/post_editor_dialog.py` is the window. `ui/template_edit.py` has the text changes behind the buttons (such as `changed`).
- **Where the user's posts live:** `adapters/post_library.py` (shipped posts are read-only; the user's are in the `posts` folder of the user folder; "Edit" on a shipped post makes a copy).

## 11. Files, settings, libraries, conventions

- **The user folder** (`core/files/user_folder.py`): `user_data` next to the program when that folder exists, otherwise `%APPDATA%\WOP`. It holds the settings, machines, libraries, posts, styles and `conventions.json`.
- **Projects** (`core/files/project_io.py`, `adapters/project_files.py`): a JSON file with a format number. The blocks and settings are stored by `core/files/dataclass_codec.py` (`to_data` and `from_data` read the type hints, so a new field needs no code); tools, contours, the machine copy, the workholding copy has their own `*_io.py` files. Files are written in one step (`atomic_file.py`), so a crash leaves no half file. There is no migration code until the first release.
- **Settings** (`core/files/app_settings.py`, `adapters/app_settings_files.py`): materials, machines, the active libraries, the tool library, the window layout. Not part of a project.
- **Libraries** (`core/files/libraries.py`, `adapters/library_files.py`, `ui/model/settings_libraries.py`): materials, workholding and tools; one file per library, one folder per kind. The library "Example" is built in.
- **Machines** (`core/lathe/machine.py`, `machine_io.py`, `adapters/machine_files.py`, `machine_folder.py`, the importers in `adapters/machine_import*.py` including the LinuxCNC `.ini`): per machine the post, the tool change position, the limits, the spindle range and the capabilities. A project keeps a copy.
- **Constants and conventions:** every fixed number is in `core/constants.py` (or `ui/app_constants.py`, `ui/ui_constants.py`, `post/post_constants.py`). The ones above `NOT_EDITABLE_BELOW` are the user's conventions: listed in `core/conventions.py` (heading, meaning, rule), edited in File > Preferences (`ui/preferences_model.py`, `ui/qt/preferences_dialog.py`), stored as differences in `conventions.json` (`core/files/convention_overrides.py`), applied when the constants module loads (the last line of `constants.py`). A change takes effect after a restart. `tools/check_conventions.py` keeps the core free of literals and forbidden imports.
- **Start-up** (`AppModel.__init__`): settings, the post library, the styles, the libraries, the machines, then the project, then the first `refresh()`.
- The program is the standalone app; there is no LinuxCNC integration in the first release. A small bridge to LinuxCNC is planned for after the first release.

## 12. Styles

A style decides only the order and depth of steps; the block does the moving. The styles are part of the program (no style files, the user's decision 2026-10-25). There are two kinds: grooving (`plan(groove)` gives a list of plunges; standard and layers, `core/blocks/groove_style.py`), turning contour (`plan(line)` gives a `Cut`: when to cut a roughing line; standard and pockets last, `core/blocks/rough_style.py`).

- Registry: `core/blocks/styles.py` (`STYLES`). The block type asks `styles_for(...)` for its dropdown and calls the chosen style's function.
- A style is registered with `STYLES.register(block type, StyleInfo(key, label, hint, function))` in the module of its kind.
- The turning contour on the analytic planner: `ContourTurningBlock.roughing_cuts` hands `rough_style.style_sequence` (the style asked about every line: the order, and the lines kept for later) to `analytic.roughing_cuts` as `sequence`; `_roughing_cuts` cuts the lines in that order.
- The check (`adapters/style_check.py`, samples in `adapters/style_samples.py`): the style is tried on small sample blocks and must remove the same material as the standard style, give only finite numbers, start and end the same, and make no collision the standard style does not. The tests run it on every style (`tests/test_rough_styles.py`).
- Pictures: `ui/style_picture.py` draws the path of a style on its samples; `ui/qt/style_preview.py` shows it when the dropdown entry is hovered.

## 13. Pictures, 3D and the stepper

- **2D picture** (`ui/svg_preview.py`): SVG text of the plan, the material, the findings, the tool and the jaws, in a colour set (`ui/theme.py`; `ui/qt/theme_qt.py` takes it from the window palette). Shown by Qt's SVG widget in `ui/qt/centre_view.py`; the zoom and pan state is `ui/view_zoom.py`.
- **3D** (`ui/view3d.py`): a `Scene` of numbers (meshes, strokes, fills) made from the plan; `ui/qt/gl_view.py` draws it with OpenGL; `view3d_widget.py` and `view3d_dialog.py` are the places it appears. Without OpenGL 2 the window uses the 2D picture.
- **Stepper** (`ui/stepper.py`): a list of every move of the plan as a `StepFrame`; for a step it works out the material at that moment (the cuts of the block so far, as `verify_plan` does) and the tool and holder at the tip. The slider and the arrow keys in the window use it.
- **Other pictures:** a contour (`ui/contour_picture.py`), a tool (`ui/tool_preview.py`), the path of a style (`ui/style_picture.py`).

## 14. Where to look when ...

| You want to know | Look in |
|---|---|
| why a move is in the G-code | the block's `generate`, then `plan_program` for the moves around it |
| why a line of G-code is written like that | the template of the concept in `wop/post/posts/*.post.ini`, then `post/tokens.py` for the token |
| why a block was left out | `ProgramPlan.left_out`, `plan_program` (the `except`), the message text |
| why a roughing line is missing or shortened | the notes of the block (`BlockResult.messages`), then `analytic/roughing_cuts.py` (`_Roughing.cut_stretch`, `_leave_out`) and `analytic/reach.py` (where the tool may stand) |
| why a collision is reported | `verify_plan` (`core/verify.py`) and the kind in `FindingKind`; the tool and holder pieces in `core/reach.py` |
| what the window does on a click | the `_value_edited` or the menu action in `ui/qt/window_parts`, then the `AppModel` method it calls |
| where a number comes from | `core/constants.py`, `ui/app_constants.py`; the ones the user may change are listed in `core/conventions.py` |
| how a new block type, tool type, style or post is added | one new file in the right folder (sections 6, 9, 12, 10); the registries find it by name |
| where a file of the user is | section 11 (the user folder) |


## 15. The analytic planner (core/analytic)

The turning planner (since 2026-10-25 the only one; the old planner of `turning_planner.py` is gone). It makes the roughing moves of the contour block, of the simple turning block and of facing (outside and inside; every case goes through the frame, `frame.py`: an inside block mirrored in X with both sides of the axis in its material, then a left-hand tool mirrored in Z, then lines across X with X and Z swapped, the reflections in `mirror.py`; the rapids in `rapids.py`; `ContourTurningBlock._analytic_roughing`, through `cut_operations.py`, and the finishing pass; the block puts the result together itself, section 3.3); a tool that stands the other way round (the left-hand boring bar: back boring on the far wall) is turned over the axis before the block is planned and its moves are turned back (`far_side.py`, called from `plan_program`, `verify_plan` and the `Stepper`); grooving, drilling and threading have planners of their own. The tests use `wanted_plan` and the replay as an independent check of the cut list. It works with chains (section 16): closed loops of exact lines and arcs, no polygons, no chords, no shapely. The entry is `ContourTurningBlock.wanted_plan` (the lines) and `ContourTurningBlock.roughing_cuts(context, first_level_only=False)` (the cut of all lines); `ui/model/views.py` asks for them and `ui/svg_preview.py` draws them. The planning is in `wop/core/analytic/`, the geometry it uses in `wop/core/geometry/` (section 16):

- `material.py`, `wanted_lines.py`, `pockets.py`, `wanted_plan.py`: step A. The stock becomes chains (the raw bar exactly, the material of earlier blocks as its loops, cleaned when they fail), the lines come from the depth of cut (parallel lines inside the region, the levels laid out from the raw bar so the same block always gets the same levels), a stretch with a wall at both ends is a pocket line and gets the plunge depth of cut.
- `tool_outline.py`: the tool as loops of edges (`geometry/tool_edges.py`); the planning copy has its back edge turned by the clearance angle.
- `reach.py`: step B, how far a line goes (`end_intervals`), the ride up and the ride over (`ride_up`, `ride_over`).
- `tip_curves.py` and `tip_walk.py`: the curves along which the tool tip stays in touch with the part (a corner on a piece, a piece corner on an edge, arc and line or arc and arc tangent) and the walk along them (`TipCurves`, `tip_walk`): the one helper for the ride up, the ride over, the slide to the contour, the passes and the way out (`way_out`). No scan: a piece of a curve is cut where it crosses another contact curve (`marks_along`), and a test in the middle and at the end of each part says whether the tool may stand there (`first_blocked` for any test); the curves against the standing stock or any other region are made when first needed (`RegionCurves`). `dips.py`: the stretches of a line with no line under them (`uncovered`) and the pass along the contour there (`follow_dip`).
- `roughing_cuts.py` (the state of one roughing is the class `_Roughing`, its steps are called in order by `_roughing_cuts`): the loop over the lines (front first, from the free side towards the part), one `cut` per line on the material the lines before left, the join over a bump, the passes at the end, then one more try for the stretches that were left out (the passes may have cleared the room they needed). A line, its ride and a pass stop where an edge that does not cut would meet standing material (`cut_limits.holder_stop`, the test of the replay `replay.holder_meets`). Inside, a cut takes the same on the far side of the axis (`cut_limits.taken_on_both_sides`) and the top of a column counts this side only (`cut_limits.column_top`); `cut_limits.goes_into` tells a plunge. The result is a list of `Cut` entries (`cut_list.py`: start, end, ride, kind, the wanted line, `joined`, `entry`) in `RoughingCuts`. `_wall_entry` is tried first for a line that starts at a wall: the tool rides up the wall (`reach.ride_up`) to the top of the material in front of the start and the way in goes down along it, so a falling wall is cut on the way in; where that is the same as a straight plunge, or no ride leads up, `_entry` is used. `_entry` makes the way in to the start of a cut: `tip_walk.way_out` finds it backwards from the start (a search along the contact curves to the first place clear of the standing stock), one clearance more orthogonal to the line at a wall, along the line at an open start; the path is reversed and cut forward with the line. `rapids.connect_cuts` (`rapids.py`) joins the cuts: it trims a way in the tool already stands on, otherwise `_rapid` (a rise at feed out of the clearance, `_clear_above`; then straight, round the corner, or over a lane above the stock, every leg tested with the tool grown by the clearance, `geometry/tool_edges.grown_loops`; a feed move down to a start on the material), and when the tool is in a notch it first goes back the way it came (`retreat`, `_leaving`). The block begins at the safe radius and ends at the safe point (`begin`, `finish`).

- `cut_operations.py`: the cut list as the moves of the machine (`Rapid`, `LinearMove`, `ArcMove`): per cut the feed moves before the rapid, the rapid, the way in (plunge feed at a wall), the line and its ride. `finishing_pass` is the finishing pass: the whole tool path along the contour at the finishing feed, the way to and from it by `rapids.clear_way` (X12), with cutter compensation the lead-in and lead-out; `ContourTurningBlock._analytic_finishing` calls it (mirrored for a left-hand tool).
- `nose_follow.py`: whether the nose can follow the contour (`misses`) and the largest nose radius that would (`largest_following_radius`): the note of the finishing pass. `roughing_cuts.left_standing` is the material the cut cannot reach: a note (the next block gets all the material the cut list leaves, `RoughingCuts.residual`).
- `replay.py`: step E, the check. The moves of a cut list run once more in the order the machine makes them, with the real tool: no edge into the part and its allowance, no holder into the material standing at that moment (the material the same move has cut before is gone), no rapid through material and none closer to it than the clearance (X12, with `RAPID_CLEARANCE_TOLERANCE_MM`); a move whose box (its path grown by the tool) meets nothing is proven free by that alone, otherwise the exact test of the walk. The material after the last move is the material the block leaves. The window draws the findings as red crosses in the picture of the analytic cut (`views.wanted_lines_for_picture`).

Reading order for the flow: `roughing_cuts.roughing_cuts` -> `reach.end_intervals` (where the tool may stand) -> `roughing_cuts._wall_entry` / `_entry` / `tip_walk.way_out` (the way in) -> `reach.ride_up` / `tip_walk` -> `geometry/removal.cut` -> `dips.follow_dip`. The design is in `docs/wop_01_design_notes.md` (section 7, with the frame), the decisions beside it.


## 16. The fast geometry (core/geometry)

Everything the planner, the checks and the pictures ask of the plane: it imports nothing of WOP but `constants.py`, and the hot modules are compiled with mypyc (`compiled.py`, `tools/build_compiled.py`; without the compiled files the same code runs as plain Python).

- `primitives.py`: `Point`, `LineSegment`, `ArcSegment` (imported as `wop.core.geometry`). `distance.py`, `intersect.py`: how far a point is from a piece and where two pieces cross. `offset.py`: pieces moved sideways, joined at the corners (`offset_segments`). `reflect.py`: points, pieces and loops reflected (x -> -x, z -> -z, x <-> z).
- `chains.py`: the loops and the boolean (cut at the crossings, classify every piece as inside, outside or on, link). `tidy.py` takes steps and slivers of the snap distance out of a loop after every cut and drops loose loops thinner than the roughing accuracy (`tidied`). `chain_index.py`: where a piece is cut at fractions (`split_at`), where a line crosses the loops (`crossings`), the exact box of a piece, and `ChainIndex`, which answers 'which pieces are near this box' from a grid of the boxes and 'which pieces does this ray cross' from slabs along each axis (`chains.py` hands its names on).
- `region.py`: `Region`, the areas of the program (stock, part, residual, tool shape) on the chains: booleans, the exact offset (`region_offset.py`), the swept area, polygons for drawing, the triangles of the 3D view (`triangulate.py`); `region_types.py` holds its small types.
- `tool_edges.py`: the tool as loops of edges marked cutting or not, placed and grown by the clearance (`grown_loops`). `penetration.py`: which edges of a placed tool go into a region. `contacts.py`: the free stretches along a straight move, from the places where tool and part touch (exact, no scan).
- `removal.py`, `tip_sweep.py` and `arc_sweep.py`: the material a move removes, what the tool sweeps: on a straight move the tip of the tool (its cutting edges closed by a chord, convex) swept as one region (`tip_sweep.swept_tip`, one split of the material per move); along an arc, or for a tool whose tip is not convex, the strips of the cutting edges (exact; an arc edge along an arc is cut along the fold lines). `cut` tries other tolerances when the boolean cannot decide.
