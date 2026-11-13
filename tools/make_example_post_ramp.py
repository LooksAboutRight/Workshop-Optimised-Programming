"""Write examples/posts/linuxcnc_spindle_ramp.post.ini: the shipped LinuxCNC post plus a speed ramp before every spindle stop.

Usage (project root):  python tools/make_example_post_ramp.py [file]
For a spindle whose drive trips (overvoltage) when it is stopped from a high speed in one go: the spindle is slowed down in steps with a wait
after each one, then stopped. The example is made from `wop/post/posts/linuxcnc.post.ini`, so it follows that post: only the settings, the
template of one step and the token `<spindle ramp>` in front of the two stop codes are added. `tests/test_examples_current.py` fails when
the committed example is not what this tool writes.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_POST = PROJECT_ROOT / "wop" / "post" / "posts" / "linuxcnc.post.ini"
DEFAULT_FILE = PROJECT_ROOT / "examples" / "posts" / "linuxcnc_spindle_ramp.post.ini"
NAME = "LinuxCNC with a spindle ramp (example)"
DESCRIPTION = "the LinuxCNC post plus a speed ramp before every spindle stop"

HEADER = """# EXAMPLE post: the LinuxCNC post with a speed ramp before every spindle stop, for a spindle whose drive trips (overvoltage) when it is
# stopped from a high speed in one go. Import it in File > Postprocessors (Import...). What is new compared to the LinuxCNC post:
#   [settings]            spindle_ramp_step (rpm per step, 0 = no ramp), spindle_ramp_dwell (seconds to wait after a step), spindle_ramp_min (the
#                         last step is not below this speed)
#   [spindle_ramp_step]   the template of ONE step: a speed and a wait
#   [tool_change]         <spindle ramp> in front of the stop code
#   [spindle_stop]        <spindle ramp> in front of the stop code (the end of the program and the machine function "spindle stop")
# From 1000 rpm with a step of 100 and a minimum of 100 the post writes  M3 S900, G4 P1.0, M3 S800, G4 P1.0 ... M3 S100, G4 P1.0, M5.
# With constant surface speed the speed is worked out from the radius of the last cut, not above the rpm limit of the block or the highest
# speed of the machine; without any of them the post refuses to write the ramp (it does not guess). A Fanuc-style controller waits with
# G4 U1.0 (or X1.0) instead of G4 P1.0: change the second line of [spindle_ramp_step]. The drive itself (its deceleration time, a brake
# chopper) is the real cure: this only keeps the program from asking for a stop it cannot take. NOTHING here was run on a machine; every
# post can crash a machine.
"""

SETTINGS = """# The speed ramp before a spindle stop (see <spindle ramp> in [tool_change] and [spindle_stop]).
spindle_ramp_step = 100
spindle_ramp_dwell = 1.0
spindle_ramp_min = 100
"""

STEP = """
[spindle_ramp_step]
# ONE step of the ramp: <S> is the speed of the step, <dwell> the wait of spindle_ramp_dwell. The code of the spindle direction is the one of
# the last start (M3 or M4). G97: a ramp in constant surface speed goes down in plain speeds.
<code rpm> S<S> <spindle code>
<code dwell> P<dwell decimals=1 zeros>
"""


def example_text(base: str) -> str:
    """The text of the example post made from the text of the LinuxCNC post."""
    text = base.replace("\r\n", "\n")
    first_section = text.index("\n[post]")
    text = HEADER + text[first_section:]  # the comment lines of the LinuxCNC post are replaced
    for old, new in (
        ("\nname = LinuxCNC\n", f"\nname = {NAME}\n"),
        ("\ndescription = LinuxCNC lathe: G7/G8, G95, G96/G97, G76\n", f"\ndescription = {DESCRIPTION}\n"),
        ("\n[settings]\n", f"\n[settings]\n{SETTINGS}"),
        ("<code coolant_off>\n<code spindle_stop>\nT<tool number>", "<code coolant_off>\n<spindle ramp>\n<code spindle_stop>\nT<tool number>"),
        ("\n[spindle_stop]\n<code spindle_stop>\n", "\n[spindle_stop]\n<spindle ramp>\n<code spindle_stop>\n"),
    ):
        if text.count(old) != 1:
            raise SystemExit(f"the LinuxCNC post has changed: {old.strip()!r} is not there once, change this tool")
        text = text.replace(old, new)
    return text.rstrip("\n") + "\n" + STEP


def main(argv: list[str]) -> None:
    target = Path(argv[1]) if len(argv) > 1 else DEFAULT_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(example_text(BASE_POST.read_text(encoding="utf-8")))
    print(f"written {target}")


if __name__ == "__main__":
    main(sys.argv)
