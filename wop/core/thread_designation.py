"""Thread designations (M8x1, M17.3x0.73, Tr40x7, 1/4-20 UNC, #10-24) turned into the numbers of the threading block.

The designation gives the major diameter and the pitch; the profile rules give the rest:
- ISO metric and unified threads (60 degree profile): a bolt thread is turned to the major diameter and cut
  `THREAD_DEPTH_FACTOR_EXTERNAL` x pitch deep; a nut thread is bored to the basic minor diameter (major - 2 x
  `THREAD_DEPTH_FACTOR_INTERNAL` x pitch) and cut `THREAD_DEPTH_FACTOR_INTERNAL` x pitch deep.
- ISO trapezoidal threads (Tr, flanks 30 degrees apart): flank height 0.5 x pitch plus a clearance that depends on the
  pitch (ISO 2904 table in constants); the nut is bored to major - pitch.
- Tolerance classes (6g, 6H) are NOT applied; two fit allowances in constants (`THREAD_EXTERNAL_CREST_ALLOWANCE_MM`,
  `THREAD_INTERNAL_BORE_ALLOWANCE_MM`, both 0) shift the crest diameter for everyone.
The names for the user: major diameter (nominal size), pitch diameter, minor diameter (root of a bolt thread, bore of
a nut thread).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from .constants import (
    METRIC_COARSE_PITCHES,
    MM_PER_INCH,
    NUMBERED_SCREW_BASE_IN,
    NUMBERED_SCREW_STEP_IN,
    THREAD_COMPOUND_MARGIN_DEG,
    THREAD_DEPTH_FACTOR_EXTERNAL,
    THREAD_DEPTH_FACTOR_INTERNAL,
    THREAD_EXTERNAL_CREST_ALLOWANCE_MM,
    THREAD_FLANK_HALF_ANGLE_DEG,
    THREAD_INTERNAL_BORE_ALLOWANCE_MM,
    THREAD_PITCH_DIAMETER_FACTOR,
    THREAD_SIZE_MATCH_TOLERANCE_IN,
    THREAD_TRAPEZOID_CLEARANCES,
    THREAD_TRAPEZOID_FLANK_HALF_ANGLE_DEG,
    THREAD_TRAPEZOID_HEIGHT_FACTOR,
    UNC_THREADS,
    UNF_THREADS,
)

EXAMPLES = "M8, M8x1, M17.3x0.73, Tr40x7, 1/4-20 UNC, #10-24"
METRIC, TRAPEZOIDAL, UNIFIED = "metric", "trapezoidal", "unified"

_NUMBER = r"\d+(?:[.,]\d+)?"
_METRIC = re.compile(rf"^M\s*(?P<d>{_NUMBER})(?:\s*[x×]\s*(?P<p>{_NUMBER}))?$", re.IGNORECASE)
_TRAPEZOID = re.compile(rf"^Tr\s*(?P<d>{_NUMBER})\s*[x×]\s*(?P<p>{_NUMBER})$", re.IGNORECASE)
_SIZE = r"\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+"
_UNIFIED = re.compile(
    rf"^(?P<numbered>#|no\.?\s*)?(?P<size>{_SIZE})(?:\s*[-x×]\s*(?P<tpi>\d*\.?\d+))?\s*(?P<series>unc|unf|unef|uns|un)?$",
    re.IGNORECASE,
)


class ThreadDesignationError(ValueError):
    """The text is not a thread designation we understand (the message says what to write instead)."""


@dataclass(frozen=True)
class ThreadValues:
    """What the block takes over for one side."""

    pitch_mm: float
    crest_radius_mm: float  # outside: the major radius, inside: the radius of the bore
    depth_mm: float
    compound_angle_deg: float
    major_diameter_mm: float
    pitch_diameter_mm: float
    minor_diameter_mm: float  # outside: root of the thread, inside: the bore
    flank_half_angle_deg: float

    def summary(self, designation: str, outside: bool) -> str:
        kind = "outside" if outside else "inside"
        return (
            f"{designation} {kind}: major diameter {self.major_diameter_mm:.3f}, pitch diameter "
            f"{self.pitch_diameter_mm:.3f}, minor diameter {self.minor_diameter_mm:.3f}"
            f"{'' if outside else ' (the bore before cutting)'}, thread depth {self.depth_mm:.3f}"
        )


@dataclass(frozen=True)
class ThreadSpec:
    designation: str  # normalised text
    family: str
    major_diameter_mm: float
    pitch_mm: float

    @property
    def flank_half_angle_deg(self) -> float:
        return THREAD_TRAPEZOID_FLANK_HALF_ANGLE_DEG if self.family == TRAPEZOIDAL else THREAD_FLANK_HALF_ANGLE_DEG

    def _trapezoid_flank_height(self) -> float:
        clearance = THREAD_TRAPEZOID_CLEARANCES[-1][1]
        for limit, value in THREAD_TRAPEZOID_CLEARANCES:
            if self.pitch_mm <= limit:
                clearance = value
                break
        return THREAD_TRAPEZOID_HEIGHT_FACTOR * self.pitch_mm + clearance

    def values_for(self, outside: bool) -> ThreadValues:
        d, pitch = self.major_diameter_mm, self.pitch_mm
        if self.family == TRAPEZOIDAL:
            height = self._trapezoid_flank_height()
            pitch_diameter = d - THREAD_TRAPEZOID_HEIGHT_FACTOR * pitch
            bore = d - pitch  # basic minor diameter of the nut
            root_outside = d - 2 * height
            full_depth_inside = height  # from the bore to the root of the nut (major diameter plus clearance)
        else:
            pitch_diameter = d - THREAD_PITCH_DIAMETER_FACTOR * pitch
            bore = d - 2 * THREAD_DEPTH_FACTOR_INTERNAL * pitch
            root_outside = d - 2 * THREAD_DEPTH_FACTOR_EXTERNAL * pitch
            height = THREAD_DEPTH_FACTOR_EXTERNAL * pitch
            full_depth_inside = THREAD_DEPTH_FACTOR_INTERNAL * pitch
        if outside:
            crest_diameter = d - THREAD_EXTERNAL_CREST_ALLOWANCE_MM
            depth = height - THREAD_EXTERNAL_CREST_ALLOWANCE_MM / 2  # the root stays where it is
            minor = root_outside
        else:
            crest_diameter = bore + THREAD_INTERNAL_BORE_ALLOWANCE_MM
            depth = full_depth_inside - THREAD_INTERNAL_BORE_ALLOWANCE_MM / 2
            minor = crest_diameter
        return ThreadValues(
            pitch_mm=pitch, crest_radius_mm=crest_diameter / 2, depth_mm=depth,
            compound_angle_deg=self.flank_half_angle_deg - THREAD_COMPOUND_MARGIN_DEG,
            major_diameter_mm=d, pitch_diameter_mm=pitch_diameter, minor_diameter_mm=minor,
            flank_half_angle_deg=self.flank_half_angle_deg,
        )


def _decimal(text: str) -> float:
    return float(text.replace(",", "."))


def _text(value: float) -> str:
    return f"{value:g}"


def _inches(size: str, numbered: bool) -> float:
    size = size.strip()
    if numbered:
        if not size.isdigit():
            raise ThreadDesignationError(f"a screw number must be a whole number, for example #10 (not {size!r})")
        return NUMBERED_SCREW_BASE_IN + NUMBERED_SCREW_STEP_IN * int(size)
    if " " in size:
        whole, fraction = size.split()
        return int(whole) + float(Fraction(fraction))
    if "/" in size:
        return float(Fraction(size))
    return float(size)


def _standard_tpi(inches: float, series: str) -> float | None:
    table = UNF_THREADS if series == "unf" else UNC_THREADS
    for label, tpi in table:
        if abs(_inches(label.lstrip("#"), label.startswith("#")) - inches) <= THREAD_SIZE_MATCH_TOLERANCE_IN:
            return tpi
    return None


def parse_designation(text: str) -> ThreadSpec:
    """The thread a designation stands for. Raises ThreadDesignationError with a hint what to write."""
    wanted = text.strip()
    if not wanted:
        raise ThreadDesignationError(f"write a thread, for example {EXAMPLES}")
    found = _METRIC.match(wanted)
    if found:
        diameter = _decimal(found["d"])
        if found["p"] is not None:
            pitch = _decimal(found["p"])
        else:
            pitch = next((p for d, p in METRIC_COARSE_PITCHES if abs(d - diameter) <= THREAD_SIZE_MATCH_TOLERANCE_IN), 0.0)
            if pitch <= 0:
                raise ThreadDesignationError(
                    f"M{_text(diameter)} has no standard coarse pitch: write the pitch too, for example M{_text(diameter)}x1"
                )
        return _checked(ThreadSpec(f"M{_text(diameter)}x{_text(pitch)}", METRIC, diameter, pitch))
    found = _TRAPEZOID.match(wanted)
    if found:
        diameter, pitch = _decimal(found["d"]), _decimal(found["p"])
        return _checked(ThreadSpec(f"Tr{_text(diameter)}x{_text(pitch)}", TRAPEZOIDAL, diameter, pitch))
    found = _UNIFIED.match(wanted)
    if found:
        numbered = bool(found["numbered"])
        inches = _inches(found["size"], numbered)
        series = (found["series"] or "unc").lower()
        if found["tpi"] is not None:
            tpi = _decimal(found["tpi"])
        else:
            tpi = _standard_tpi(inches, series) if series in ("unc", "unf") else None
            if tpi is None:
                raise ThreadDesignationError(
                    f"no standard threads per inch known for {wanted}: write them too, for example {wanted}-20"
                )
        if tpi <= 0:
            raise ThreadDesignationError("the threads per inch must be greater than zero")
        label = ("#" + found["size"].strip()) if numbered else found["size"].strip()
        name = f"{label}-{_text(tpi)}" + (f" {series.upper()}" if found["series"] else "")
        return _checked(ThreadSpec(name, UNIFIED, inches * MM_PER_INCH, MM_PER_INCH / tpi))
    raise ThreadDesignationError(f"cannot read {wanted!r} as a thread; write for example {EXAMPLES}")


def _checked(spec: ThreadSpec) -> ThreadSpec:
    if spec.major_diameter_mm <= 0 or spec.pitch_mm <= 0:
        raise ThreadDesignationError("the diameter and the pitch must be greater than zero")
    if spec.pitch_mm >= spec.major_diameter_mm / 2:
        raise ThreadDesignationError(f"the pitch {spec.pitch_mm:g} is too big for a diameter of {spec.major_diameter_mm:g}")
    return spec
