# WOP (Workshop Optimised Programming) for LinuxCNC Lathe – Design Notes

How the program is built and why: the current state only, in short bullets. History: git log. Requirements: `wop_02_requirements.md`. Conventions: `wop_03_conventions.md`. Who calls what: `wop_04_code_tour.md`. A value marked GUESS is not from a standard or a measurement; the user corrects it.

## 1. Goal
- Workshop-style programming for LinuxCNC lathes (XZ): blocks on a raw part, contours, tools, collision checks, 2D and 3D picture, posts.
- Product: the standalone app (also the development tool). No LinuxCNC integration in the first release; a small bridge to LinuxCNC is planned for after the first release.
- Controller independent through posts; LinuxCNC first.
- From scratch; Andy Pugh's Lathe Macros (GPL-2.0) are only an inspiration, none of their code or text is used. Values of standards are typed in as numbers in our own forms, no standard text is copied. Licence MIT; `THIRD_PARTY_NOTICES.md` names every third-party part (Qt / PySide6 under the LGPL-3.0, kept as replaceable files in the folder build).
- Must not block later C axis, live tooling, milling.
- A quick workshop tool, not a CAM package. Not wanted (the user's decisions): a hand-written G-code block (a post function does it), suggested cutting data, stick-out from step jaws, acceleration and rapid checks, accept / refuse buttons for findings, the spindle number of G76 (several spindles are for an industrial CAM).

## 2. Architecture
- Layers: core (pure Python) -> post -> adapters (files, DXF, LinuxCNC files) -> ui (`AppModel`, forms, pictures, no toolkit) -> `ui/qt` (PySide6, thin).
- core never imports post, ui, adapters, a GUI toolkit or linuxcnc (`tools/check_conventions.py`).
- The window does everything through `AppModel` (`wop/ui/app_model.py`: state, observers, Undo / Redo, files); its actions are mixins by topic in `wop/ui/model/` (shared types in `helpers.py`).
- Plug-in types register themselves and are imported by name (`BLOCK_TYPES`, `TOOL_TYPES`, `WORKHOLDING_TYPES`, `STYLES`): a new file in the folder, no other change.
- Compiled core: the hot modules listed in `wop/core/compiled.py` are compiled with mypyc (`tools/build_compiled.py`); without the build the same code runs as plain Python.
- Size: a file over 600 lines or a function over 200 lines fails `tests/test_source_size.py`; split by topic.
- Written for Python 3.11+ and PySide6 6.6+ (Debian 12 machines); developed on Windows with Python 3.13.

## 3. Conventions
- In `wop_03_conventions.md`.

## 4. Data model
- `Project`: settings (title, X mode, work offset), `Program`, machine copy, touched marks.
- `Program`: raw part, safety (safe position, optional tool change position, clearance), ordered blocks, contours, its own tools, workholding copy.
- `RawPart`: material, outer and inner diameter (0 = solid), stick-out, length (None = bar stock).
- `Contour`: id, name, solved segments, the definition or the sketch, cutting flags, named points; blocks refer to it by id.
- `Tool`: number, shape (closed outline of CUTTER and HOLDER pieces, tip at the origin), material, type and definition, named points, offset number, holding.
- `Block`: base fields (tool, spindle, feed, coolant) plus type fields; a type is one file in `core/blocks/`; its form comes from the type hints.
- The material (residual) is worked out block after block; every block gets the material, not the block before.

## 5. Contours, sketch editor, DXF
- Chains of lines and arcs; a turning contour starts at its highest Z and ends at its lowest Z.
- Sketch editor (`wop/core/sketch/`, session in `wop/ui/sketch_session.py`, window in `wop/ui/qt/`): free 2D points, lines, arcs, circles; relations and dimensions; own solver (Levenberg-Marquardt on numpy, moves the points as little as possible, refuses conflicts); constraint state by colour.
- Modes: turning contour, tool shape, workholding outline, free; a mode says what the outline must be and makes the program's `Contour` with the sketch kept inside.
- Tools: one smart Dimension tool; centre lines (the spindle axis always) make diameters through a hidden mirror point; fillet and chamfer keep the sharp corner as reference lines; trim (also by swiping), mirror, construction lines, cutting edges, named points.
- A relation button works on the selection, or stays on while things are clicked; selection in its own colour.
- Selection: Ctrl+click toggles a thing; Horizontal / Vertical with one point wait for a second pick (the origin is valid). The spindle axis is a line in relations (`AXIS_LINE` = -1): a point or line and a centre line give a radius (`distance_line`) on the thing's side and a diameter (mirror point) across the centre line; a line and the axis give an `angle` relation.
- A fillet or chamfer is one unit (`CornerLink`, `core/sketch/corners.py`: line-line, line-arc, arc-arc): the thin reference pieces cannot be selected; deleting the bevel or a shortened piece undoes the corner.
- Drag: every other point is held softly (`DRAG_STAY_WEIGHT`) and a drag the relations cannot follow is tried with a smaller pull (`DRAG_BACKOFF`), so the free part of a loosely defined shape follows the mouse.
- Limits the user accepts: no offset or rotate of a whole outline, mirror or move of a whole shape only by hand, no step list, a part from DXF in three steps.
- Add > Contour makes an empty contour and opens the editor; the centre draws the stored `Contour`.
- No or invalid contour: the block is left out, the G-code says "INCOMPLETE - DO NOT RUN".
- DXF (`dxf_files.read_dxf`, ezdxf): LINE, ARC, polylines, points and text as named points; everything else counted in the notes.
- Part contour from DXF: axis horizontal or vertical, mirrored from below the axis, lines on the axis dropped, longest chain, turned to start at the highest Z.
- As drawn (tools, workholding, components): nothing moved, turned or mirrored, no line dropped; one closed outline.

## 6. Areas and checks
- Areas are exact closed chains of lines and arcs (`Region` in `wop/core/geometry/region.py`, kernel in `wop/core/geometry/chains.py`): booleans by trim-and-link, exact offsets, triangles for 3D; no chords, no library.
- Tolerances: geometry 1e-6 scale; snap `CHAIN_SNAP_MM` 0.002; roughing accuracy 0.01 (`CUT_END_SNAP_MM`, `DIP_MIN_AREA_MM2`); a boolean that cannot decide retries with small shifts (`CUT_JITTER_MM`) and tolerances.
- Planning rule (X8, written as drawn): the geometry comes from the form values only; roughing keeps the tool body off the part (at most 30 % of the allowance into it), a line is cut as far as the tool reaches and the rest stays with a note; finishing follows the contour whatever the tool can reach; a block stops only when there is nothing to make; the checker reports every collision; a failing block is left out with its reason (`LeftOutBlock`); `tests/test_as_drawn.py` lists every block that asks the tool body.
- `verify_plan` (`core/verify.py`): follows every move; cutting moves remove what the tool sweeps; a quick exact test first (`_clearly_free`), then the swept area (`_sweep_verdict`), steps only where needed.
- Findings: GOUGE (tool in part plus allowance), HOLDER_IN_MATERIAL (holder in the material), JAWS, CLAMP_PLANE, SPINDLE_OFF, RAPID_IN_MATERIAL.
- Touching is not collision: overlap deeper than `COLLISION_PENETRATION_TOLERANCE_MM` (0.005 mm).
- `BlockResult.protected`: what the block's tool must never touch (else: what the block leaves standing).
- Far side: a tool whose body reaches below x = 0 is also tested mirrored; the 2D picture draws the mirrored material faint.

## 7. Turning planner (`wop/core/analytic/`)
- The geometry it uses (chains, areas, the tool as loops, removal, the compiled modules) is in `wop/core/geometry/`, which imports nothing of WOP but the constants.
- Used by every turning block: the contour block, the simple turning block (its outline as a contour) and facing outside in (the face as a flat contour across X).
- Steps:
  - A wanted lines (`wanted_plan.py`, `wanted_lines.py`, `pockets.py`): the area between material and contour plus allowance; lines at the depth of cut, levels laid out from the raw bar; a stretch with walls at both ends is a pocket line at the plunge depth of cut.
  - B reach (`reach.py`, `contacts.py`, `tool_outline.py`): the planning tool = the real tool with its back edge turned by the block's free angle; each line ends where the planning tool may stand (exact contact events, no scan).
  - Cut (`roughing_cuts.py`): front first, from the free side towards the part, or in the order of the roughing style; each line cut on what the lines before left.
  - Ride up (`tip_walk.py`, `tip_curves.py`): at a wall the tool rides up along the contact curves of the tip to the top of the material in that column; a lower bump is ridden over and the line behind it joined; across X only the material joined to the line counts and the ride ends where it no longer cuts.
  - Dips (`dips.py`): under the lowest lines a pass along the contour takes what the lines left.
  - Retry: a stretch the planner left out (holder in the material, no way in, under a stretch that stays) is tried once more when the passes along the contour are made (`cut_stretch(..., retry=True)`); the retried cuts come last.
  - Way in: found backwards from the start along the contact curves; at a wall orthogonal to the line, otherwise along it; else a straight plunge; none: the line and the lines under it stay (note).
  - A line that starts at a wall: the way in follows the wall up to the top of the material in front of it (`_wall_entry`); the line above is always cut first in every style, so the top is never more than one depth of cut higher.
  - Holder stop (`cut_limits.py`): a line, ride or pass stops where a non-cutting edge would meet standing material.
  - Rapids (`rapids.py`): X12, rapids keep one clearance from the material, closer moves at feed; rise out of the clearance first, retreat along the path out of a notch, the long way round where nothing is free (note).
  - Removal (`removal.py`, `tip_sweep.py`, `arc_sweep.py`): a move removes what the tool sweeps (the convex tip along a line, the strips of the cutting edges along an arc).
  - Moves (`cut_operations.py`): `Rapid`, `LinearMove`, `ArcMove`; plunges at the plunge feed.
  - Replay (`replay.py`): an independent check of the cut list (part, holder, rapids, clearance); used by the tests only.
- Finishing pass (`cut_operations.finishing_pass`): the tool path along the whole contour at the finishing feed, also through the air; the ways to and from it like the rapids; cutter compensation adds lead-in and lead-out; `nose_follow.py` names the nose radius that would follow where the nose cannot.
- What a block hands on (`ContourTurningBlock.generate`): without a finishing pass the material the tool really left; with one all the material between stock and contour; slivers of a retried cut are not counted.
- Start: an outside block rapids to the safe radius one clearance in front of the material; an inside block's first rapid goes straight over the bore; the block ends at the safe point.
- Styles (`rough_style.py`): Standard, Pockets last; a style only orders the lines (`style_sequence`).
- A sliver between stock and contour thinner than the largest `CUT_JITTER_MM` shift (0.0053 mm) is no removal.
- Not done: transverse passes only open to the outside, one depth grid per contour, plunge into pockets, undercut cutting.
- The finishing pass of a left-hand tool (outside) is planned mirrored in Z and turned back with the same reflections (`mirror.Flip.operation`).

### The frame (`frame.py`)
- The planner knows one case only; every other case is reflected into it (`mirror.py`) and back; no rules for hand, side or direction inside the planner (the planner gets the frame and asks it where the axis and the free sides are, and whether the column above a line end runs beside the part).
- The one case: outside, lines along Z, the tool cutting from the front towards the chuck, its body over the layers already cut.
- Questions, in this order:
  1. the tool works on the far side of the axis (back boring)? Not inside the planner: `analytic/far_side.py` turns the tool over the axis before the block is planned (`plan_program`) and turns the moves back; the safe point is turned with it (the block begins and ends at the real safe point), and the checks and the stepper fold the block over the axis in the same way. The part is round, so the far wall is the mirror of the near wall. The spindle direction (M4) is a value of the block, not geometry.
  2. Inside? Mirror in X. The part and its allowance are made after this step (X is the radius there).
  3. Left-hand tool (body towards the chuck, asked on the real tool)? Mirror in Z.
  4. Lines across X? Swap X and Z.
- Every step is a reflection: arcs change direction, a right-hand tool becomes left-hand; undone in reverse order.
- Data the frame carries: the axis in its coordinates (inside: material on both sides), the free sides (the outside of the part and the front).
- The free sides decide only the far moves: the lane over the material and the long way out; never towards the chuck. The short rise out of the clearance is tested against the material and may go either way.
- A left-hand tool across X: its planes run from the chuck side towards the front; where the air is only in front (rest material at a back wall) little can be reached and a note says what stays.
- Parts: preparation (`roughing_cuts.roughing_cuts`, from a `RoughingJob` the block fills by name), feed planner (`_roughing_cuts`: the class `_Roughing` holds the material and the cuts, its steps share a `_Planner`), rapid planner (`rapids.py`), back through the frame (`Frame.back`).

## 8. Blocks
- Common: feeds per revolution; what stays uncut is reported; a block may list `tool_default_fields` that follow the tool until typed (U6).
- Contours make no code. Threading and drilling are neutral operations that the post turns into cycles or moves; boring is turning with the side INSIDE. Every block sets spindle and coolant at its start.
- Defaults (GUESS): finishing allowance 0.5 x nose radius until typed; facing overtravel 2 nose radii; finishing speed follows the roughing speed until typed; block copy = title + " copy", right after the original.
- Facing: flat face at a target Z; outside in by the turning planner across X, running past the centre by the overtravel (2 nose radii); its own finishing pass; centre out by passes of its own (`_centre_out`), the ways between them over the top.
- Turning, simple (outside = turning, inside = boring) with a start chamfer or fillet: works on the edge of the part also when the target is the diameter of the bar or more (the corner is cut, the rest is the finishing pass along the outline); without a corner or when the corner cuts nothing it says the material is already at or beyond the target. Otherwise: target radius at Z 0, optional taper (included angle, or rise per 100 mm), Start Z (not an input: where the block's material begins, shown greyed), end Z, start and shoulder corner, along Z or across X, finishing pass with its own feed and speed, cutter compensation; planned as a contour (`_as_contour`); the stock in front of the Start Z is not the block's (`BlockContext.front_z`).
- Turning along a contour: the same on a stored contour, plus plunge feed and depth, back clearance (free angle), style.
- Grooving (`groove_plan.py`, styles Standard and Layers): plunges from the front wall, each with air on one side and at most the one-sided cut (mm or % of the blade); finishing plunges and passes along the bottom; pecking (chip breaking or full retract); parting off (radius 0); rapids through air an earlier cut left. Edges (`groove_edges.py`): each wall has an edge kind (none, chamfer of 45 degrees, fillet) and a size; the right edge is the wall nearer the face (the part of a cut-off), the left the wall nearer the chuck. The corner of the blade (taken as sharp) cuts the edge and goes on straight down the wall in the same move (`Plunge.edge`, `GroovePath.edge_cut(depth_x=...)`), so the edge and the wall are one cut and leave no burr (the move down the wall is pecked as the form says, counted from the end of the edge); a large edge is first cut in smaller passes, each at most the one-sided cut (`edge_sizes`, `EdgeCut.size_mm`). The roughing leaves a skin of `GROOVE_EDGE_SKIN_MM` on a wall with an edge (the finishing allowance when there is one); in a groove as wide as the blade the first plunges reach that much past the wall nearer the chuck (`relief_low_z`). A groove to the axis cuts the part off, so its first full-depth plunge is at the wall of the part (`rough_plunges(wall_first=True)`, all styles), or the part comes off too long. The style Edges before full depth opens the groove only as deep as the edge size plus `GROOVE_EDGE_RELIEF_MM`, then cuts the wall of the part with its edge in one move, then the rest; Standard and Layers cut the edge with the wall at the end (a groove to the axis then says the part is off before its edge). The one-sided cut value has the unit of its mode (`form_units`).
- Drilling: on the axis to an absolute depth (to the tip or to the full diameter); dwell; modes drilling, peck, peck with full retract; air skipped where an earlier drill went; the post may write a cycle.
- Threading: 60 degree (or the tool's) thread along Z, outside or inside; G76 words as fields (crest, pitch, start and end Z, depth, first cut, degression, compound angle, spring passes, taper); fixed RPM; designations (M8x1, Tr40x7, 1/4-20 UNC) fill the numbers; run-out from the reach of each flank of the tool. Thread values (GUESS): compound angle = flank half angle - 0.5 (29.5, 14.5); depth 0.6134 x pitch outside, 0.5413 inside; trapezoidal flank height 0.5 x pitch + a clearance table; plain `M8` = coarse pitch, `1/4` = UNC; no tolerance classes (6g, 6H), no UNJ or pipe threads; the block does not compare the flat of a trapezoid tool with the thread root (the user checks it).
- Machine function: a fixed function (program stop, optional stop, dwell, spindle stop) or a custom concept of the post with its variables.
- Custom path: drawn in the sketch editor (mode 'custom path'): one path from the locked safe point, piece after piece in the order drawn (it may come back along a line and cross itself); a line is a feed move unless marked rapid, an arc is always feed, a piece can have a feed of its own; the part before the block is there as locked lines and arcs to dimension to; the sketch is solved with the current safe point and part each time the block is planned (`resolved`); the swept tool counts as removed; a note when the path is not fully constrained.
- Not done: back boring (a left-hand inside tool on the far wall, spindle reversed) for the grooving and threading blocks; the turning blocks do it (`wop/core/analytic/far_side.py`).
- Cut-off pieces (`core/program_model/cutoff.py`): when a block separates the material, the held piece stays (the grip decides), the other is dropped and drawn dashed.

## 9. Plan, step-through, export, power
- `plan_program(program, selection, unticked_done, cache, should_stop)`: plans the selected blocks; adds safe retract, tool change, spindle and coolant around each.
- Block cache (`plan_cache.py`): a block with the same inputs and the same material object is not planned again; `verify_plan` keeps its findings the same way.
- The window plans and checks in the background after every change, the picture first; a newer change stops the older job before its next block; no Check menu, no setting.
- Export: the export check window lists findings and left-out blocks, or says that no checks ran; Export selected (unticked blocks count as done by default).
- Step-through (`ui/stepper.py`): every move a step, the material worked out on demand and ahead in a thread; the small crests between sampled positions are kept.
- Power (`power.py`): one sum per block from the form, P = kc x A x vc / 60000 / 0.8 at the largest radius it cuts; chip A by kind (turning: depth of cut x feed; grooving: edge x feed; drilling: half the diameter x feed at a quarter of the diameter; threading: the first pass; custom path: twice its mean thickness x feed). Always an estimate (`POWER_PEAK_TO_MEAN` 2, `THREAD_HALF_ANGLE_DEG` 30; a finishing block is estimated high).
- Machine checks (always run): RPM, feed speed of each move on X and Z, travel.

## 10. Pictures
- One `ColorSet` (`ui/theme.py`), light or dark from the window colour.
- 2D (`ui/svg_preview.py`): material, moves, findings as crosses (stepping: a cross appears with its move; a finding names the block and the move as the stepper shows them, `Finding.move_number`), a block that cut into the part shows it missing from there on (`ui/damage.py`: only the pictures, never the plan, the files or the export), workholding behind, the finished shape of the chosen block dashed; zoom and pan (the window's picture holds everything, the rapid moves to the tool change position too, but opens on the "home" view, the raw part and the cutting moves, written into the SVG as `data-home` (`render_svg(whole=True)`, `svg_home`); zooming out goes past home to the whole picture, a double click returns home; zoomed, it is drawn again with all line widths divided by the zoom, `line_scale`); the legend as a Qt overlay.
- 3D (`ui/view3d.py` scene, `ui/qt/gl_view.py` OpenGL 2.1 / ES 2.0): the part revolved 270 degrees, cut faces, chuck and jaws, path and tool on the other cut face; without OpenGL the 3D button is greyed (Linux: one restart with the software renderer).
- The saved part (`"preview"` in the project) is drawn at once when a file opens, until the plan is there.
- Style pictures: hovering an entry of the open style dropdown shows the style on its samples.

## 11. Tools
- Types (Add menu order): turning tool, turning tool (ISO holder), boring bar, boring bar (ISO), grooving tool, threading tool, drill.
- A type is a dataclass that builds the outline; `reconcile` keeps dependent fields in step; a tool edited in the sketch editor becomes a free shape.
- Reference point (`core/tooling/tool_reference.py`): the corner of the box round the cutting edges (where it is touched off), with rules for edges that lean forward; a named point `tip` overrides; `Program.equipped_tool` puts it at the origin.
- Material after a turning block (`ContourTurningBlock._without_what_stands`): the finishing pass is replayed on the material (`finishing_pass_on` returns what stands after it) and what the rounded nose cannot reach (the corner of a sharp inner corner, about r squared times 0.2146) is taken out of `removed`, so it is in the material after the block, in the picture and in the next block; the thin film the cut leaves along the contour (thinner than two shifts of a retried cut) is no material and is cut off the corner, but the tapering ends of a corner stay (a flat cut-off end made the next tool go into the part: `tests/data/projects/nose_rest_cleanup.wop.json`), the corner is grown by `ATTACH_MM` to meet the part again, and a note names it when it is at least `UNREACHED_MIN_AREA_MM2`. Not worked out: the block takes the shape as cut, as before.
- Finishing path (`core/nose_compensation.py`): the contour offset by the nose radius; the nominal contour is kept for G41 / G42. A piece that the joins of the offset turn around (a wall lower than the nose radius, a small arc) is left out of an open chain (`geometry/offset.py`), so the pass ends on the cylinder and goes straight away, not back into the material.
- Hand (`tool_back_angle.back_direction`): body towards larger Z = right-hand; two back edges within `NEUTRAL_NOSE_TOLERANCE_DEG` = neutral (cuts like right-hand).
- ISO inserts (ISO 1832) and holders (ISO 5608, boring bars ISO 6261 / 5609): type the code or choose the parts. GUESS, to check against the standards: offset shank f about 1.25 x width, straight f = b, l1 per letter, head and neck, shank sizes per style (ISO 5610-1 table 2 missing), boring bar styles (ISO 6261 positions 6 to 10 missing), edge angles (ISO 5608 table 3); not modelled: tolerance letter, manufacturer part, flats on bars, cartridges, insert hand, round and parallelogram inserts.
- Tool table (`core/tooling/tool_table.py`, `adapters/linuxcnc_tools.py`): read, write, refused while a program runs; backups are copies `tool.tbl.wop-backup-<timestamp>`; a table without G7 / G8 is radius mode, without units metric with a note.
- Toolboxes (`core/tooling/toolbox.py`): the tool library file holds the tools and named toolboxes (library tool, tool number, offset number; numbers unique; one default per library); the machine remembers its library. A new project has no tools, or a copy of the default toolbox; it keeps its own tool copies, each with its origin and the name of its toolbox. Tests use two stub tools (`NEW_PROJECT_USES_STUB_TOOLS`).
- Putting a toolbox into a project asks first (`apply_toolbox`): the same tool of the same library keeps its block and follows its new number; every other block gets "no tool chosen" (`NO_TOOL_NUMBER` = 0: the planner leaves the block out with that reason); a box of another library unhooks every block.
- Standard tool values (GUESS; the turning tool follows the user's drawing): turning tool edges 96 degrees, nose 0.3, edge 20, width 20, length 100; boring bar end edge 96, wall edge 100, diameter 16, front width 19.5, nose 0.3, length 100, edge 25; grooving tool blade 3, reach 10, corner 0.2, front angle 90, holder 12 x 100, touched off at the left corner; threading tool 60 degrees, radius 0.1, no flat, height 5, tip distance 6, width 12, length 100.

## 12. Workholding
- Workholding: a chuck body and jaws (`core/lathe/workholding.py`, types in `core/workholding_types/`); one dropdown in Setup, an anchor point on the part, grip outside or inside; a ring around the axis for the checks; notes when the jaws and the Setup clamping plane disagree.
- Tool holding (turret, adapter) is not modelled: a holder or turret that matters is drawn as holder pieces in the sketch of the tool.
- Libraries hold the items; the project keeps copies.
- Placeholder shapes (GUESS): jaws (two steps, radius 25 / 15, shoulder 12), chuck (radius 20 to 100, depth 70), three jaws of 60 degrees. The inside grip note counts only jaw points at or behind the clamping plane. For the first release only the clamping plane (stick-out) is recommended.

## 13. Machine, materials, settings
- Machine: RPM limits, axis speeds, X/Z extents, spindle power, capabilities, post, default tool change position; one file per machine in the `machines` folder; importers (LinuxCNC ini, WOP file).
- The machine of the project is the list entry of that name; the copy in the project is used only without one.
- A project opened without a machine gets the default machine of the list (a notice, the project is marked changed). A machine replaced by the list entry is a change without an Undo step.
- Materials: built-in table, user list; looked up by name.
- Libraries (materials, workholding, tools): files `libraries/<kind>/<name>.json`; "Example" built in; the first change forks it; a machine remembers its libraries.
- Settings: `settings.json` in the user folder (`user_data` next to the program if it exists, else `%APPDATA%\WOP`); a damaged file is set aside.
- File > Preferences: rows from `conventions.py`; changes apply after a restart.
- Window unit (preference `DISPLAY_UNITS`, mm or inch; independent of the unit of the G-code): the program and the files stay in mm. `ui/display_units.py` converts what a form field (units `mm`, `mm/rev`, `mm/min`, by `to_display` / `from_display` in `block_forms.py`) and a sketch dimension show and take; inch boxes have 6 decimals so a value survives the round trip. Messages (message box, status bar, problem lists, block notes, setup summary, message dialogs) get `shown_text`: every `<number> mm`, `mm/rev`, `mm/min` in the text becomes inches, so a message must not hold a range ("1 to 5 mm") or an ISO size in mm.
- Stays metric whatever the window unit (the user's decision): ISO tool sizes and codes (`IsoDefinition.metric_only`), the values and meanings in File > Preferences (names end in `_MM`), the taper rise per 100 mm, the list of operations of a block (File > ... Operations) and the G-code (the unit of the machine), the post editor, DXF import units and the pictures. Thread pitch is shown in the window unit (the designation text stays as typed). A spindle speed field carries the unit of its mode: RPM, m/min, or ft/min in the window that shows inches (`_with_spindle_units`).
- Untouched fields are dimmed; Reset to default.

## 14. Window
- Flow list: Setup, the blocks as cards (tick for export, note, warning), then the contours.
- Right panel: the form of what is chosen (Setup, block, contour, tool, workholding).
- Forms from dataclasses (`block_forms.form_for`; hooks `form_fields`, `form_labels`, `form_headings`, `form_disabled`, `form_buttons`, `field_choices`, `form_notes`); greyed values a block worked out are shown without a rebuild (`shown_values`).
- Number boxes: "." and ",", select all on entering; a click anywhere commits the value.
- Panels collapse; smallest window 1024 x 768; notices instead of boxes when no action is needed.
- Errors go to `wop.log`; the window says once that an internal error happened.

## 15. Posts
- Core emits neutral operations (rapid, feed, arc, thread, drill, machine function, function call, dwell, tool change, spindle, coolant, comment); a post never changes the program.
- A post is a text file `*.post.ini` (`wop/post/posts/`: linuxcnc = the only shipped post, generic = the default inside the program, not offered; the user's own in the user folder; reference posts to import in `examples/posts`: fanuc, plain_gcode); one engine (`post/engine.py`) writes them.
- File: `[post]`, `[settings]`, `[codes]`, `[modal_groups]`, `[functions]` with their sections and variables, one section per concept; a missing concept comes from the generic post.
- Inch G-code: the unit of the machine (`unit_system`) is `PostSettings.unit`; the program stays in mm and the engine converts per token (`Token.dimension`: lengths and feeds / 25.4, constant surface speed to ft/min, rpm and times unchanged); inch decimals are the post settings `decimals_inch`, `feed_decimals_inch`; `<units code>` writes `units_mm` or `units_inch` of the code table. Other lengths in the post (variables of custom functions) are not converted. Not done: showing inch in the window.
- Move to the tool change position (`Rapid.at_change`, one before every tool change and one at the end, also when the tool stands there already): written as a plain rapid in work coordinates, with `[machine_rapid]` in machine coordinates (G53) when the machine has the position, or with `[change_position]`, which wins over both: the code of the controller for it (G28 U0 W0, G30 ...). X and Z in that template are the machine position when the machine has one, else the work position. The generator writes this move every time and the work position is unknown after it (`has_change_position`, `_machine_move`).
- Spindle ramp (`TemplatePost.spindle_ramp`, token `<spindle ramp>`, template `[spindle_ramp_step]`, settings `spindle_ramp_step` / `_dwell` / `_min`): before a stop the speed goes down in fixed rpm steps with a wait each, for a drive that trips when it stops from speed. The token stands in front of the stop code in `[tool_change]`, `[spindle_stop]` or `[footer]` (the stop is inline in the tool change, so the engine cannot do it alone); off with step 0 (the shipped posts have it off, `examples/posts/linuxcnc_spindle_ramp.post.ini` shows it). The speed is the fixed rpm, or with constant surface speed worked out from the radius of the last cut (`state.cut_x`), not above the rpm limit of the block or the machine's highest speed; with none of them the post refuses (no guess). The spindle counts as stopped after the ramp (no second ramp).
- Templates: text, `<token options>`, optional parts `[ ... ]`; a line of empty tokens writes nothing; tokens in one registry (`post/tokens.py`, `tools/list_post_tokens.py`).
- Code table with fixed names (`FIXED_CODES`); templates use `<code name>`; the features of a post follow from the table and the settings.
- Modal groups: fixed groups plus the user's; `changed` compares inside a group; two codes of one group in one line is a problem. A shipped post lists only the codes of its code table.
- Work offsets: the codes `work_offset_1`, `work_offset_2` ... of the code table, in the order of their numbers (`PostDefinition.work_offsets`); the Setup form offers those of the post of the machine; the post editor shows them as a section of the code table (rows named by their order); a post with none writes none and the field is greyed.
- Remedies at export (never changing the program): fixed RPM for CSS, no coolant, arcs as lines, radius values, a function left out; a block with an open issue is left out and the output marked incomplete.
- Cutter compensation: a post with `cutter_compensation = yes` writes the nominal contour with G41 / G42 / G40 on the lead moves, else the tool path; a post with the setting but without the codes is an error.
- Post editor (File > Postprocessors): pages per concept, live sample output in two cases, token grid, modifier buttons; a post with problems opens with red pages and can be saved.
- No golden files, nothing marked verified: every post can crash a machine; the user checks.
- LinuxCNC post (the only one run on a lathe, a Schaublin 125 CNC; nothing else is verified): spindle codes (G96 / G97, M3 / M4) are written in full every time; I, J, K of G76 are diameter values in G7 mode (`by_mode`); the move to the tool change position is `G53 G0 X.. Z..` when the machine has a machine-coordinate change position (else `G0`), then `M9`, `M5`, `T.. M6`, `G43 H..`; the work offset line comes after the mode codes; line numbers and cutter compensation are on; drilling cycles G81 / G82 / G83 / G73 inside `G17 ... G80 G18` (one concept per cycle type, picked by `cycle_concept` in `post/engine.py`; a cycle without a template, or a hole inside a hole that is there, is written as plain moves).
- Generic post (GUESS): `G21 G90 G94 G18`, radius only, CSS refused (remedy fixed RPM), tool change = comment + `M0`, thread = comment + passes, drill = plain moves, F mm/min = feed x RPM of the last `M3 S`. Fanuc-style reference post (GUESS): X diameters, `G99`, `T0101`, `G50 S..` then `G96`, two-block `G76`, arcs with I and K. Both are written from memory.
- Engine: the offset number is the tool number unless set; `<estimated time>` takes rapids at the axis maxima, else `ESTIMATED_RAPID_MM_PER_MIN`; a missing post id is LinuxCNC, missing sections come from generic; codes in modal groups are compared by their first word (G00 = G0).
- Next posts, in this order: Siemens, then Mazak, Okuma, Heidenhain, Mach3/4, Centroid, Haas. Keep the neutral operations few: each must work in every post or have a remedy.

## 16. Files
- Project: versioned JSON; blocks as `type` + `parameters` written from the type hints (`dataclass_codec`); save-load-save gives the same bytes; damaged or newer files give a `ProjectError`.
- Command line: `tools/wop_run.py file.wop.json [--block N] [--out folder] [--accept-all] [--machine file]`.
- The `examples` folder is shipped in the Windows zip: the pawn and the rest machining project (saved from the window, `tests/test_examples_current.py` checks that they open, plan and find their post), the reference project, `blocks/`, `posts/` and the example machine (written by the `tools/make_*.py` tools, the same test checks them). Test projects (collision demo, compensation test) are in `tests/data/projects`; the machine tests are made on demand by `tools/make_machine_tests.py`.
- Windows release: the zip of `python tools/build_exe.py --zip` (`dist\WOP-<version>-windows.zip`), no installer; `opengl32sw.dll` (software OpenGL, 20 MB) stays in as the fallback for an old lathe PC; no UPX; the exe is not signed (SmartScreen or a virus scanner may warn). The examples carry the author's machine; the README says so.
- Linux install: `tools/install_linux_compiled.sh` (the one the README names) runs `tools/install_linux.sh` and then compiles the core with mypyc in a temporary copy; the plain script removes leftover compiled files. Venv in `~/.local/share/wop`, start command `~/.local/bin/wop`, a menu entry, an offscreen self-test; it refuses root; the Debian packages of the Qt xcb plug-in are checked with `dpkg -s` before and `ldd` after the install (the offscreen self-test does not need them). Without the compiled core the window froze while planning the pawn on a small PC (Intel N100). Only Debian 13 is tested.
- Crash log: `crash.log` next to `wop.log` (`wop/ui/crash_log.py`, `faulthandler`) holds the stacks of all threads at a crash; a log without an 'end' line is a crash. No watchdog for freezes: its dump from a second thread crashed the program on a slow computer.
- GitHub release: the private history stays on the Gitea server; the public repository gets one commit per release, a tag `v<version>`, the zip attached, the SHA-256 and a note about SmartScreen in the release notes (compare the SHA-256 after every copy).
- README: first person; the pictures `docs/images/window_3d.png` and `docs/images/window_2d.png` are copied by hand from `tools/make_screenshots.py` and made again when the window changes. The manual (`docs/manual`) says only that it is machine generated.

## 17. Integration
- None in the first release. A small bridge to LinuxCNC is planned for after the first release.
- All logic in core, so another GUI binding stays cheap.
- The lathe PC (Schaublin 125 CNC): LinuxCNC 2.9.8, Debian 13, X11; `linuxcnc.stat().tool_table` is a list of `[toolno, x, y, z, a, b, c, u, v, w, diameter, frontangle, backangle, orientation]`, entry 0 is the tool in the spindle, comments only in `tool.tbl` (which has extra words Y A B C U V W, kept); `[HALUI] MDI_COMMAND`, `USER_M_PATH` and `COORDINATES = XZ` in the ini; both files are fixtures in `tests/data/`. Never start `linuxcnc` from a script.
