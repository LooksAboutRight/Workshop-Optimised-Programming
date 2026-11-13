# WOP for LinuxCNC Lathe: Requirements

What the program does, with a test for each and how far it is. Design, decisions and guesses: `wop_01_design_notes.md`. Target: LinuxCNC lathe (XZ); the standalone app (Windows and Linux) is the product, with no LinuxCNC integration in the first release.

Rules for this list:
- One row names one concept, in a few words; it does not explain it (detail belongs in the design notes).
- Row IDs are stable: never renumber or reuse one. The rows are grouped by topic, so the numbers are not in order; a new row takes the next free number of its letter and is put in its topic.
- Each acceptance criterion is one short line that can become a test.
- Status: Done = built and tested; "not tried" = the user has not tried it yet; "not run on a machine" = the G-code has not run on the lathe. Partly / Open / Future / Dropped / Removed as named.

## Architecture

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| A1 | The core is pure Python | Every module in `core/` imports without PySide6, GTK and LinuxCNC. | Done |
| A2 | The standalone app runs without LinuxCNC | On a Windows PC without LinuxCNC: raw part, contour and turning block give G-code. | Done |
| A3 | Plugin in the gmoccapy screen | - | Dropped (the app is the product) |
| A4 | Plugin on other LinuxCNC screens | - | Dropped (with A3) |
| A5 | Coding rules | The convention check finds no layer breach and no module-level dict outside `constants.py`. | Done |
| A6 | A small bridge to LinuxCNC | - | Future (after the first release) |
| A7 | Extra axes later (C axis, live tooling) | A machine with an extra axis loads and saves without loss; v1 blocks ignore it. | Partly: not tested with a project file |
| C3 | Open-source libraries where one fits | The libraries and licences are in `THIRD_PARTY_NOTICES.md`. | Done |

## Program and blocks

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| B1 | A program is an ordered list of blocks | Add, delete, move: window, file and G-code have the same order. | Done |
| B2 | Block types facing, turning, threading | One block of each type generates G-code and reloads equal. | Done |
| B3 | Block types boring, grooving, drilling | Each type has an example that generates G-code and passes the reach check. | Done |
| B20 | A groove wall can have a chamfer or a fillet on its edge, also for a cut-off | A cut-off with a chamfer on the part: the groove is opened to the edge size, then the edge and the wall of the part are cut in one move, the part comes off at its length; a large edge is cut in passes (`tests/test_groove_edges.py`). | Done, not tried on a machine |
| B12 | Custom path block (path drawn in the sketch editor) | A path with rapids, feed lines and an arc is planned, drawn, checked and written (`tests/test_custom_path.py`, `tests/test_sketch_path.py`). | Done, not tried |
| B13 | Machine function block (follows the functions of the post) | A function the post lacks is not offered; a block whose function is missing is left out at export with the reason. | Done |
| B8 | Hand-written G-code block | - | Removed (a post function does it, B13) |
| B14 | Machine setting "Enable G-code blocks" | - | Removed (with B8) |
| B10 | A block type is one registered unit | A dummy block type is added in a test by one file. | Done |
| B16 | Styles for a block type (grooving, turning contour) | Both grooving styles remove the same material on every sample groove. | Done |
| B17 | Styles as user files | - | Dropped (styles are part of the program) |
| B18 | Inside turning across X on a solid bar feeds down, never rapids | `tests/test_inside_across_x.py` | Done |
| B19 | Turning along Z: way back keeps off the wall skin | `tests/test_inside_review.py` | Done |
| B20 | A wall drawn beyond the stock is cut to the stock | `tests/test_inside_review.py` | Done |
| B21 | Roughing keeps off the finished part (at most 30 % of the allowance); finishing follows the contour | `tests/test_roughing_keeps_off_the_part.py`, `tests/test_inside_review.py` | Done |
| B22 | Outside turning with a left-hand tool | No gouge, holder or rapid-in-material finding (`tests/test_left_hand_turning.py`). | Done |
| B23 | No roughing of a thin skin over the part | - | Dropped (the analytic planner does it) |
| B24 | Finishing leaves the contour at its last cut | - | Dropped (superseded by B26) |
| B26 | The finishing pass follows the whole contour, never shortened | `tests/test_finishing_pass.py` | Done |
| B27 | A note names the nose radius that would follow a narrow groove or small arc | `tests/test_finishing_pass.py` | Done |
| B25 | After a change only the changed block and those after it are planned again | The result equals a plan from scratch (`tests/test_block_cache.py`). | Done |
| B28 | Far side: a tool that stands the other way works on the far side of the axis | Same material, mirrored moves, same findings (`tests/test_far_side.py`). | Done, not run on a machine |
| B29 | Spindle direction in every block (clockwise or counter-clockwise) | `tests/test_spindle_direction.py` | Done, not run on a machine |
| B4 | A program is saved as a file of blocks | Save, load, save: the two files are byte-identical. | Done |
| B9 | A single block can be run on its own | The moves of block 3 alone equal those in the full program. | Done |
| B15 | Export selected (checkbox per block) | Only block 3 ticked gives its moves alone; the header names the blocks. | Done |
| N12 | Copy of a block or contour | A copy of a roughing block with another tool plans only the rest; Undo removes it. | Done |

### Settings that every block has

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| B5 | Coolant per block | Three blocks with the three settings write the matching codes. | Done |
| B6 | Spindle mode per block (CSS or RPM, with limit) | A CSS block then an RPM block write G96 with the limit, then G97. | Done |
| B7 | X as radius or diameter | The same X in both modes gives the same geometry. | Done |
| B11 | One G-code mode (G7 or G8) per program | A mixed program is written in one mode with correct values. | Done |
| U6 | Untouched fields are dimmed | A new block shows all fields dimmed; Reset dims one again. | Done |
| N2 | Finishing allowance follows the nose radius | A tool with a nose radius gives 0.5 times it; a typed value stays. | Done (factor 0.5 guessed) |

## Raw part, setup and residual material

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| R1 | Raw part: material, outer and inner diameter | Inner 0 is solid; an inner not smaller than the outer is rejected. | Done |
| R2 | Stick-out and whole length | A new program needs the outside length; an empty inside length is infinite. | Done |
| R7 | Stock behind the clamping plane runs through or ends inside the jaws | "Ends inside" asks for a length; the values reload unchanged. | Done |
| R8 | Notes for a stick-out longer than the part and for bar thicker than the chuck bore | Both cases give a note. | Done |
| R9 | Raw part drawn in the sketch editor | `tests/test_raw_outline.py`, `tests/test_setup_form.py` | Done |
| R10 | Work offset of the project (from the post) | The choice reloads; the LinuxCNC header has the code. | Done, not run on a machine |
| U3 | Setup entry first in the flow list | Setup is first and has no checkbox. | Done |
| U7 | Project settings and machine in Setup | A typed tool change position in Setup wins over the machine's. | Done |
| M5 | Material table, editable | An edited value survives a restart; a material without cutting data gives a warning. | Done |
| R3 | Residual part after each block | On a reference program the residual never grows. | Done |
| R4 | Residuals follow reordering and edits | After swapping blocks 2 and 3 the residuals equal those of a program built in that order. | Done |
| R5 | The residual drives rest machining and collision checks | A finishing block after roughing cuts only the rest. | Done |

## Workholding

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| R6 | Chuck body and jaws as saved shapes for collision | Without jaws a path across the clamping plane is reported; with jaws, touching a step is reported. | Partly: moving onto components and sets, and inside-clamping fixes, are open |
| N10 | Inside grip check | A note names how far the jaws reach into the wall. | Done, not tried |

## Contours

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| C1 | A contour of lines and arcs | A contour of 5 lines and 3 arcs is saved and reloaded unchanged. | Done |
| C5 | One contour shared by several blocks | Editing it changes both blocks; deleting a used one is refused. | Done |
| C9 | Contours are entries in the flow list | `tests/test_contour_selection.py`, `tests/test_qt_real.py` | Done |
| C14 | Deleting a used contour offers three choices | Abort, delete with the blocks, or keep the blocks without a contour. | Done |
| C10 | A block without a valid contour is left out | The export marks the program incomplete (DO NOT RUN). | Done |
| C8 | Crossings are checked | A crossing is reported with element numbers and cannot be used (`tests/test_sketch_modes.py`). | Done |
| C2 | Corner with a tangent radius by coordinates or intersection | Both inputs give the same contour. | Done |
| C11 | Line step by any two of angle, end X, end Z | - | Removed (the sketch editor replaces it, N21, N22) |
| C15 | Angle of a line step measured from -Z | - | Removed (the sketch editor, N22) |
| C12 | Arc step with all its fields | - | Removed (the sketch editor) |
| C13 | Arcs from any valid combination of inputs | To be defined. | Future |
| C4 | Ellipses and B-splines as a polyline | An ellipse and a B-spline convert within the tolerance. | Open: named as ignored in a DXF import |
| C6 | DXF import in the sketch editor | A DXF with lines and arcs imports; unsupported entities are listed. | Done: tried with one real drawing |
| C7 | One shape editor for contour, tool and workholding | `tests/test_sketch_targets.py` | Done |
| N7 | Mirror, rotate by 90 degrees, move and offset of shapes | Each change leaves a shape that solves. | Done, not tried |

## Sketch editor

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| N20 | 2D sketch of lines, arcs and circles with snapping, selection, drag, Undo | Every Sketch editor button opens it for its target. | Done |
| N21 | Relations and dimensions with a solver | A conflicting one is refused and changes nothing. | Done |
| N22 | One Dimension tool | `tests/test_sketch_dimension_tool.py` | Done |
| N27 | Dimensions drawn CAD style and movable | `tests/test_sketch_dimension_move.py`, `tests/test_sketch_text_place.py` | Done |
| N23 | Diameter across a centre line or the spindle axis | `tests/test_sketch_centre_line.py` | Done |
| N24 | Trim, mirror, fillet, chamfer, construction lines | `tests/test_sketch_edit.py`, `tests/test_sketch_swipe_trim.py`, `tests/test_sketch_modify_session.py` | Done |
| N25 | Modes for part contour, tool shape and workholding outline | `tests/test_sketch_modes.py`, `tests/test_sketch_targets.py`, `tests/test_sketch_real_data.py` | Done |
| N40 | Ctrl+click selects several things | Ctrl+click on three things selects them; on a selected one takes it out. | Done |
| N41 | Horizontal and Vertical with one point wait for a second pick | Nothing changes until a second point or the origin is clicked. | Done |
| N42 | Radius or diameter between a thing and a centre line | `tests/test_sketch_radius_dimension.py` | Done |
| N43 | A fillet or chamfer is one unit | `tests/test_sketch_corner_link.py` | Done |
| N44 | Fillet and chamfer between line and arc and between two arcs | `tests/test_sketch_corner_arcs.py` | Done |
| N45 | Angle between a line and the spindle axis | `tests/test_sketch_angle_to_axis.py` | Done |
| N46 | Dragging a point that is not fully defined | `tests/test_sketch_free_drag.py` | Done |
| N47 | Locked points and lines supplied by the program | `tests/test_sketch_locked.py` | Done |
| N48 | Dimensions to the part are dropped when the part changes shape | `tests/test_sketch_locked.py`, `tests/test_custom_path.py` | Done, not tried |
| N49 | Stepping through a path in the sketch editor | `tests/test_sketch_stepping.py`, `tests/test_qt_real.py` | Done, not tried |
| N28 | DXF import and diameter display in the sketch editor | `tests/test_sketch_modes.py` | Done |
| N26 | Square buttons with pictograms in sections | `tests/test_sketch_buttons.py`, `tests/test_sketch_session.py` | Done |
| N33 | A relation works select-first or button-first | `tests/test_sketch_action_tool.py`, `tests/test_sketch_buttons.py` | Done |
| N34 | Selection drawn in its own colour | Looked at by the user. | Done |
| N36 | One button per kind of named point | `tests/test_sketch_action_tool.py`, `tests/test_point_kinds.py` | Done |
| N37 | A new mode and Esc drop the selection | `tests/test_sketch_action_tool.py` | Done |
| N38 | "," or "." as the decimal point everywhere | `tests/test_decimal_comma.py` | Done |
| N35 | Buttons to hide relations and dimensions | `tests/test_sketch_buttons.py` | Done |

## Tools

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| T1 | A tool is a contour of cutter and holder pieces | Holder contact with the residual is a collision, cutter contact inside the cut is not. | Done |
| T8 | Tool types with their own forms (Tools view) | The drill form has no insert field; a new type is one file. | Done |
| N13 | Turning tool (standard shape) | Every combination that builds is a valid outline. | Done |
| N29 | Order of the tool types in the Add menu | `TOOL_TYPE_ORDER` gives it. | Done |
| N15 | Boring bar (standard shape) | Every combination that builds is a valid outline. | Done |
| N16 | Grooving tool (standard shape, inside and outside, hand) | A left-hand tool gives the same groove. | Done |
| N30 | Touch-off corner of the grooving tool | The same removed area for either corner. | Done |
| N17 | Threading tool (standard shape) | The example thread has no findings. | Done |
| N9 | Run-out of a threading tool from its flank angle | A drawn V gives its own angle; the standard tool 30 degrees. | Done |
| N11 | Thread designation fills the thread values | Values match the standard tables; editing a derived number clears the designation. | Done |
| N14 | DXF import of a tool as drawn | `tests/test_sketch_targets.py` | Done |
| T2 | Presets for insert shapes and drills | A drill of 118 degrees, 8 mm, 40 mm gives the expected contour. | Done |
| T12 | Tools from ISO holder and insert codes | `PCLNR 2525 M12` with `CNMG 120408` gives a closed shape. | Done: values partly guessed |
| T16 | Hand of the boring bar | `tests/test_far_side.py` | Done |
| T17 | Named toolboxes in the tool library | A toolbox keeps its numbers; two entries with one number are refused. | Done |
| T18 | A new project has no tools, or the default toolbox | A block without a tool is reported, not planned. | Done |
| T19 | Changing the toolbox of a project | `tests/test_toolbox_project.py`, `tests/test_toolboxes_window.py` | Done |
| T13 | Touch-off reference point of a tool | The named point replaces the computed one. | Done |
| T14 | Finishing path offset by the nose radius | A CNMG tool on a cylinder, a stepped shaft, a slope, an arc and a taper leaves nothing uncut. | Partly: grooving corner choice open |
| T15 | Tool offset number | 5 on T2 gives `G43 H5` after `T2 M6`. | Done, not run on a machine |
| T10 | Tool material | The value saves and reloads. | Done |
| T11 | Suggested depth of cut, feed and speed | - | Dropped (not wanted) |
| T9 | Turning insert tool type by ISO designation alone | - | Removed (T8, T12) |
| T3 | Tool holder and turret as components and sets | - | Removed (T1 and the sketch editor) |

### Tool table

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| T4 | LinuxCNC tool table | Tools of a sample `tool.tbl` appear; a change is written back. | Adapter done, no UI |
| T5 | A program stores its own tool table | A saved program opens with another table and keeps its tools. | Done |
| T6 | Backup when a program tool table is applied | Restoring gives the original byte for byte. | Adapter done, no UI |
| T7 | No applying while a program runs | With LinuxCNC running, applying is refused. | Adapter done, no UI |

## Machine and units

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| M1 | Machine definition (RPM, velocities, extents, power) | Saved and loaded; a missing value is reported. | Done |
| M2 | Values read from the LinuxCNC configuration | From a sample ini, limits and units are filled in. | Done |
| M8 | Machine importers, one file per format | A dummy importer is added in a test by one file. | Done |
| M9 | Machines in a list, one is the default | Two machines are saved; after a restart the default is loaded. | Done |
| M12 | The project keeps a copy of its machine | A project without that machine uses its copy. | Done |
| M7 | Machine capabilities can be switched off | A machine without CSS gets no warning for such a block. | Partly: hiding inputs not done |
| M10 | Spindle sync as a capability | With it off, a threading block is reported. | Done |
| M6 | Metric by default, imperial selectable | A metric ini gives metric, an imperial ini imperial. | Partly: the window shows metric only |
| M13 | G-code in the unit of the machine | An imperial machine gives `G20`, lengths and feeds in inches (`tests/test_post_inch.py`). | Done in tests, not tried on a machine |
| M15 | A length can be typed with its unit (25mm, 25 mm, 1inch, 1", also m/min, mm/rev) in any unit setting | 1" typed in a window set to mm is stored as 25.4 mm. | Future |
| M14 | The window shows the unit of a preference, independent of the machine | Window in inch, G-code in mm, and the reverse (`tests/test_display_units.py`). | Partly: form fields, sketch dimensions and messages; what stays metric is in the design notes; not tried by the user |
| M11 | Machine codes of functions (chuck, bar feeder) | - | Removed (they are in the post, N19) |

## Checks and toolpaths

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| X2 | Reach check | A groove too narrow or deep for the tool is reported with the element. | Done |
| X3 | Collision check of tool and holder | A holder that touches the shoulder is reported with block and position. | Done |
| M3 | Cuts beyond the machine are flagged | A cut beyond the extent and an RPM outside the limits are flagged. | Done |
| M4 | Spindle power check (an estimate) | A heavy cut is flagged, a light one is not. | Done: the sum per block not tried |
| X8 | Written as drawn: the tool never shortens the geometry | An undercut the tool cannot reach: finishing goes as drawn, the problem list names the collision. | Done |
| X4 | Explicit moves; threading and drilling as single operations | A post without cycles maps them to moves. | Done |
| X1 | Complex turning with automatic roughing | Roughing leaves the allowance and cuts nothing beyond the contour. | Done |
| X5 | Facing block | The residual has a flat face at the given Z. | Done |
| X9 | Facing overtravel past the centre | The preset follows the tool. | Done |
| X6 | Turning block, simple form | The residual equals the expected shape in both directions. | Done |
| X13 | Taper in the simple turning block | A taper of 10 degrees gives the radius 10 + 30 tan 5 degrees at 30 mm. | Done |
| X14 | Taper input as angle or rise per 100 mm | Switching shows the same taper the other way. | Done |
| X7 | Turning block, contour form | The residual equals the part plus allowance before finishing. | Done |
| X10 | Roughing lines follow the contour; no cut deeper than the depth of cut | Tests on the bump and pocket project. | Done |
| X11 | The back of the tool keeps its free angle from a pocket wall | No move has the back closer to the wall than the free angle. | Partly: the old planner (other blocks, inside, left-hand tools) still enters along the wall |
| X12 | Rapids keep one clearance from the standing material | `tests/test_analytic_replay.py` | Partly: blocks on the old planner are not checked |
| X17 | A start corner cuts the edge of a bar also when the target is the bar diameter or more | `tests/test_turning_edge_only.py` | Done, not tried |
| X18 | A finishing pass past a wall lower than the nose radius ends away from the part | `tests/test_turning_edge_only.py` | Done, not tried |
| X19 | What the nose of the tool cannot reach stands after the block | The material after a block with a nose radius keeps the corner of a sharp inner corner; the next block and the picture get it (`tests/test_nose_leftover.py`). | Done, not tried |
| X15 | Simple turning starts where the material of the block begins | `tests/test_turning_start_z.py` | Done, not tried |

## Preview

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| V1 | 2D picture of the neutral operations | The reference program gives a picture with raw part, finished shape and paths. | Done |
| V2 | Stepping through moves | Forward then back gives the same picture; a collision shows as a cross. | Done, not tried |
| V7 | Stepping stays responsive | `tests/test_stepper.py`, `tests/test_qt_real.py` | Done |
| V8 | Planning and checking in the background | `tests/test_background_analysis.py` | Done |
| V9 | A saved project shows its part at once | `tests/test_saved_part.py` | Done |
| V10 | The 2D picture opens on the part and can be zoomed out to all tool paths | A far tool change position is not in the first view, and zooming out shows it (`tests/test_overlay_home.py`). | Done, not tried by the user |
| V3 | Legend as an overlay; findings as crosses | 20 blocks do not move the drawing. | Done |
| V4 | Pictures follow the OS theme | Light and dark are readable. | Done |
| V5 | 3D view in the centre with a 2D/3D toggle | The toggle does not move the window. | Done |
| N8 | Zoom and pan of the 2D picture | Wheel and drag change the view; a double click shows the whole picture. | Done |
| N50 | The 2D picture fits the part and the cutting moves | The extent has no point that only a rapid reaches. | Done |
| N51 | Lines keep their width when zoomed | The picture is drawn again with widths divided by the zoom (`tests/test_qt_real.py`). | Done |
| Z1 | 3D view built block by block | `tests/test_view3d.py`, `tests/test_gl_view.py` | Done |
| Z2 | 3D view with OpenGL 2 and a fallback | `tests/test_gl_view.py` | Done on Windows; Pi and Linux not tried |
| V6 | Colour presets (colour vision) | To be defined. | Future |

## Postprocessors

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| O1 | G-code from a controller-neutral operation list | The core tests contain no G-code text. | Done |
| O12 | A post is a text file written by one engine | Engine tests with invented posts (`tests/data/posts/fake_*.post.ini`). | Partly: engine, tokens, three posts, switch and editor are done |
| O4 | Another controller needs only a new post file | A dummy post is added in a test by one file. | Done |
| O7 | The post is chosen in the machine settings | Switching the post changes the output, not the program. | Done |
| O13 | A post lists what the controller can do (`[supports]`) | The checks and remedies use it. | Done |
| O2 | Missing controller feature: message and remedy | A post without CSS: the message proposes a fixed RPM; accepting lists it in the header. | Done |
| N18 | Code table with fixed names and own codes | Every project with every shipped post writes the same G-code as before. | Done |
| N31 | No coolant capability in the machine | The Machines dialog has none. | Done |
| N54 | A post can slow the spindle down in steps before it stops | The example post writes M3 S900, G4 P1.0 ... before M5 (`tests/test_spindle_ramp.py`); a speed it cannot know is refused. | Done, not tried on a machine |
| N55 | The move to the tool change position can be written with the code of the controller | A post with `[change_position]` writes it before every tool change and at the end (`tests/test_post_change_position.py`). | Done, not tried on a machine |
| N19 | Custom functions in a post with typed variables | `linuxcnc_bar_feeder.post.ini` writes the bar feed; a value outside min and max is an error. | Done |
| O14 | Post editor window with sample output | `tests/test_post_editor.py`, `tests/test_post_editor_dialog.py` | Done |
| N3 | Plain G-code post | Every example project can be written with it. | Done |
| N4 | Fanuc-style post (reference file) | Every example is written with it. | Done: nothing verified on a controller |
| O6 | Next posts: Siemens, Mazak, Okuma, Heidenhain, Mach3/4 | A post file loads and writes every example. | Open |
| O5 | Every shipped and reference post is tested against all examples | `tests/test_shipped_posts.py` | Changed: no golden files, the user checks what a post writes |
| N5 | Every registered post is tested against all examples | `tests/test_shipped_posts.py` | Done, not tried |
| O15 | Cutter compensation of the finishing pass (G41 / G42 / G40) | `tests/test_compensated_finish.py`, `tests/test_post_compensation.py` | Partly: turning and contour turning; facing, grooving and threading follow |
| O16 | LinuxCNC post: safe tool change, modal output | `tests/test_linuxcnc_post.py` | Done, not run on a machine |
| O31 | Tool change position in machine coordinates (`G53`) | `tests/test_machine_tool_change.py` | Done |
| O33 | Only the LinuxCNC post is shipped | The list holds only LinuxCNC (`tests/test_shipped_posts.py`). | Done |
| O34 | Line numbers in a post | `tests/test_app_model.py` | Done, not tried |
| O32 | Drilling cycles in a post | `tests/test_drill_cycles.py` | Partly: air cut fine; not tried in material |
| O3 | The first post is for LinuxCNC, tested on a real machine | The G-code of a reference program runs on a LinuxCNC lathe. | Done: one lathe (Schaublin 125 CNC), see the README |
| O8 | Verification recorded per feature of a post | - | Dropped (the user checks what a post writes) |
| O9 | Header comment for an unverified feature | - | Dropped |
| O10 | Ask the user to send in machine results | - | Dropped |
| O11 | Mark hand-written G-code with a controller | - | Removed (with B8) |

## User interface, settings and libraries

| **ID** | **Requirement** | **Acceptance criteria** | **Status** |
|--------|-----------------|-------------------------|------------|
| U1 | Flow column on the left, forms on the right | All block parameters are reachable. | Done |
| U2 | Lines from blocks to their contours | Each block shows a line to its contour. | Open: nice to have |
| U5 | A settings file in the user's folder | Deleting it gives defaults without an error. | Done |
| N6 | The window remembers size, panels and folders | A restart shows the same layout (`tests/test_qt_real.py`). | Done: the separate export folder not tried |
| N52 | Every dialog remembers its size and place | `tests/test_qt_real.py`, `tests/test_app_settings.py` | Done |
| N53 | Project name and version in the window title | `tests/test_version.py` | Done, not tried |
| N39 | The export dialog suggests a file name | `tests/test_qt_real.py` | Done |
| N32 | Changed library and machine files are read again | A file changed outside is taken over with a message. | Done |
| U8 | Libraries for materials, workholding and tools | Choosing, New, Save as and Import work; closing with differing tools asks. | Done |
| U9 | The window and dialogs fit 1024 x 768 | `tools/check_small_screen.py`, `tests/test_small_screen.py` | Partly: not looked at on a real 1024 x 768 monitor or with 125 % scaling |
| N1 | Preferences (`conventions.json`) | A wrong entry is ignored and reported; a right one changes the value after a restart. | Done, not tried |
