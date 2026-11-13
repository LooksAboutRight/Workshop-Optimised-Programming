# Changelog

All notable changes to WOP are listed here, newest first.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

Work happens on the branch `dev`; `main` holds released versions only.
Every user-visible change gets a line under `Unreleased` in the same commit.
At a release, `Unreleased` becomes the new version heading with its date.

## [Unreleased]

### Added
- Postprocessors: the new concept `[change_position]` writes the move to the tool change position with the code of the controller for it (for example G28 U0 W0). Without it nothing changes.
- Postprocessors: a speed ramp before every spindle stop for a drive that trips when it is stopped from speed: the settings `spindle_ramp_step`, `spindle_ramp_dwell` and `spindle_ramp_min`, the template `[spindle_ramp_step]` and the token `<spindle ramp>` in front of the stop code. Off in the shipped posts; new example post `linuxcnc_spindle_ramp.post.ini`. A post you made earlier keeps working unchanged.
- Grooving: a chamfer or a fillet on the edge of each groove wall (left: chuck side, right: face side), with the new style "Edges before full depth" for a cut-off with a chamfer or fillet on the part. The edge and the wall are cut in one move (pecked as the form says), a large edge in several passes (at most the one-sided cut). New preferences GROOVE_EDGE_SIZE_MM, GROOVE_EDGE_SKIN_MM and GROOVE_EDGE_RELIEF_MM.
- Window unit: File > Preferences > Program > DISPLAY_UNITS shows lengths, feeds and sketch dimensions in inches or millimetres (after a restart), whatever the unit of the machine. Messages and summaries follow it. A spindle speed field names its unit (RPM, m/min, or ft/min in inch). ISO tool sizes, the values in Preferences and the taper rise per 100 mm stay metric.
- G-code in inches: an imperial machine writes `G20`, lengths and feeds in inches and constant surface speed in feet per minute (new post token `<units code>`, post settings `decimals_inch` and `feed_decimals_inch`).
### Changed
- Turning: the material that the rounded nose of the tool cannot reach (the corner of a sharp inner corner) now stays standing after the block, in the picture and for the next block; before, the block took the finished shape as cut. A note names it when it is more than 0.25 mm2.
- Grooving: a cut-off (a groove to the axis) now starts its full-depth cutting at the wall of the part, so the part comes off at its length; before, the first plunge could be one one-sided cut away from it.
- Grooving: the value of the one-sided cut and its mode entry "mm" follow the unit of the window.
- The 2D picture again holds all tool paths, also the moves to the tool change position, but still opens zoomed to the part: zoom out (mouse wheel) to see everything, double click to come back.
- Posts you made or copied before this change do not follow the new inch output. On an imperial machine they still write `G21` in the header (their setup uses `<code units_mm>`) while the numbers are in inches, so they must be updated: add `units_inch = G20` to `[codes]`, `G20` to the `units` group of `[modal_groups]`, and replace `<code units_mm>` with `<units code>` in the setup. Metric machines are not affected.
### Fixed
- Turning: a start chamfer or fillet now works on the edge of the part also when the target X is the diameter of the bar or more; before, the block refused with "the material is already at or beyond the target radius".
- Turning (simple and along a contour): when the contour ends just inside the material (a shoulder lower than the nose radius of the tool), the finishing pass no longer ends with a move back into the material.
- A machine with a tool change position in machine coordinates (G53) now gets the move before every tool change, also when the previous block ended at that position.
### Removed

## [0.1.0]

First release.
