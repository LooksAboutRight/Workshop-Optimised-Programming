# Changelog

All notable changes to WOP are listed here, newest first.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

Work happens on the branch `dev`; `main` holds released versions only.
Every user-visible change gets a line under `Unreleased` in the same commit.
At a release, `Unreleased` becomes the new version heading with its date.

## [Unreleased]

### Added
- Window unit: File > Preferences > Program > DISPLAY_UNITS shows lengths, feeds and sketch dimensions in inches or millimetres (after a restart), whatever the unit of the machine. Messages and summaries follow it. A spindle speed field names its unit (RPM, m/min, or ft/min in inch). ISO tool sizes, the values in Preferences and the taper rise per 100 mm stay metric.
- G-code in inches: an imperial machine writes `G20`, lengths and feeds in inches and constant surface speed in feet per minute (new post token `<units code>`, post settings `decimals_inch` and `feed_decimals_inch`).
### Changed
- The 2D picture again holds all tool paths, also the moves to the tool change position, but still opens zoomed to the part: zoom out (mouse wheel) to see everything, double click to come back.
- Posts you made or copied before this change do not follow the new inch output. On an imperial machine they still write `G21` in the header (their setup uses `<code units_mm>`) while the numbers are in inches, so they must be updated: add `units_inch = G20` to `[codes]`, `G20` to the `units` group of `[modal_groups]`, and replace `<code units_mm>` with `<units code>` in the setup. Metric machines are not affected.
### Fixed
### Removed

## [0.1.0]

First release.
