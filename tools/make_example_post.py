"""Write examples/posts/linuxcnc_custom_function.post.ini: the shipped LinuxCNC post plus a custom machine function (a bar feeder).

Usage (project root):  python tools/make_example_post.py [file]
The example is made from `wop/post/posts/linuxcnc.post.ini`, so it follows that post: only the parts of the bar feeder are added (three
codes, a modal group of their own, the custom concept `bar_feed` with its variables and its template). `tests/test_examples_current.py`
fails when the committed example is not what this tool writes.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_POST = PROJECT_ROOT / "wop" / "post" / "posts" / "linuxcnc.post.ini"
DEFAULT_FILE = PROJECT_ROOT / "examples" / "posts" / "linuxcnc_custom_function.post.ini"
NAME = "LinuxCNC with a custom machine function (example)"
DESCRIPTION = "the LinuxCNC post plus a custom machine function for a bar feeder"

HEADER = """# EXAMPLE post: the LinuxCNC post with a custom machine function (a bar feeder), to show the syntax of custom codes, custom modal groups
# and custom concepts. Import it in File > Postprocessors (Import...). What is new compared to the LinuxCNC post:
#   [codes]            three codes of the bar feeder at the end (M100 to M102 are the user M codes of LinuxCNC)
#   [modal_groups]     a group of your own, "barfeeder", for the three codes
#   [functions]        one custom concept, bar_feed, that opens the feeder, moves the bar and clamps it again
#   [bar_feed_variables]  what the concept needs: the distance (a float with limits), and whether to pull the bar back first (a bool)
#   [bar_feed]         the template: it uses the three codes and the two variables
# A custom concept is written like any other concept (see the pages of the editor). Choose it in a Machine function block
# (the function list follows the post). NOTHING here was run on a machine; every post can crash a machine.
"""

CODES = """# the codes of the bar feeder: a name of your own and the code of your controller
barfeeder_open = M100
barfeeder_move = M101
barfeeder_clamp = M102"""

MODAL_GROUP = """# a group of your own: its codes cancel each other, so two of them cannot stand in one line
barfeeder = M100 M101 M102"""

FUNCTION = """
[functions]
# name = what it does (the name is the name of the section with the template)
bar_feed = Open the bar feeder, push the bar and clamp it again

[bar_feed_variables]
# name = type, then min= max= default= unit= label= (all of them are optional). The template uses a variable as <name>.
# float, int, uint (0 or more), bool and string are the types. A number can have limits.
distance = float min=0 max=500 default=30 unit=mm label="Feed distance"
pull_back = bool default=no label="Pull the bar back first"

[bar_feed]
# <distance> and <pull_back> are the variables above. A bool writes 1 when it is true and nothing when it is false; with yes="..." it writes
# that text instead of the 1 (and no="..." writes a text when it is false), so [ <pull_back yes="R1">] appears only when the bar is pulled back.
(bar feed <distance decimals=1 zeros> mm)
<code barfeeder_open>
<code barfeeder_move> D<distance decimals=1 zeros>[ <pull_back yes="R1">]
<code barfeeder_clamp>
"""


def example_text(base: str) -> str:
    """The text of the example post made from the text of the LinuxCNC post."""
    text = base.replace("\r\n", "\n")
    first_section = text.index("\n[post]")
    text = HEADER + text[first_section:]  # the comment lines of the LinuxCNC post are replaced
    for old, new in (
        ("\nname = LinuxCNC\n", f"\nname = {NAME}\n"),
        ("\ndescription = LinuxCNC lathe: G7/G8, G95, G96/G97, G76\n", f"\ndescription = {DESCRIPTION}\n"),
        ("\n\n[modal_groups]", f"\n{CODES}\n\n[modal_groups]"),
        ("\n\n[header]", f"\n{MODAL_GROUP}\n\n[header]"),
    ):
        if text.count(old) != 1:
            raise SystemExit(f"the LinuxCNC post has changed: {old.strip()!r} is not there once, change this tool")
        text = text.replace(old, new)
    return text.rstrip("\n") + "\n" + FUNCTION


def main(argv: list[str]) -> None:
    target = Path(argv[1]) if len(argv) > 1 else DEFAULT_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(example_text(BASE_POST.read_text(encoding="utf-8")))
    print(f"written {target}")


if __name__ == "__main__":
    main(sys.argv)
