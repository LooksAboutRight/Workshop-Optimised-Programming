"""The posts of WOP for the tests of the generator and the blocks."""

from __future__ import annotations

from dataclasses import replace
from functools import cache
from pathlib import Path

from wop.adapters.post_library import load_post_library
from wop.post.base import Feature
from wop.post.engine import TemplatePost
from wop.post.post_definition import CODE_FEATURES, parse_post


BAR_FEEDER_FILE = "examples/posts/linuxcnc_custom_function.post.ini"
ALL_FEATURES = (  # the settings and codes that make a post support every feature (what `[supports] all` was)
    "[settings]\nx_diameters = yes\narcs_in_diameters = yes\n"
    "[codes]\ncss = G96\ncoolant_flood = M8\ncoolant_mist = M7\nprogram_stop = M0\noptional_stop = M1\nspindle_stop = M5\nspindle_ccw = M4\ndwell = G4\narc_ccw = G2\narc_cw = G3\n"
)


@cache
def _library():
    return load_post_library()


REFERENCE_FOLDER = Path(__file__).resolve().parent.parent / "examples" / "posts"
REFERENCE_POSTS = ("fanuc", "plain_gcode")  # the reference posts of the examples: not shipped, imported by the user


def reference_text(post_id: str) -> str:
    return (REFERENCE_FOLDER / f"{post_id}.post.ini").read_text(encoding="utf-8")


def reference_definition(post_id: str):
    """The definition of a reference post (`examples/posts`), with the default post behind it."""
    return parse_post(reference_text(post_id), post_id, _library().posts["generic"])


def reference_post(post_id: str) -> TemplatePost:
    return TemplatePost(reference_definition(post_id))


def install_reference_post(user_folder: Path, post_id: str) -> None:
    """Copy a reference post into the `posts` folder of a user folder, as the user does with Import."""
    folder = user_folder / "posts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{post_id}.post.ini").write_text(reference_text(post_id), encoding="utf-8", newline=chr(10))


def unnumbered(definition):
    """The definition without line numbers: most tests compare the plain lines (the numbers have tests of their own)."""
    return replace(definition, settings=replace(definition.settings, line_numbers=False))


def shipped_post(post_id: str = "linuxcnc") -> TemplatePost:
    """A new engine on one of the posts that come with WOP (LinuxCNC unless told otherwise), without line numbers."""
    return TemplatePost(unnumbered(_library().posts[post_id]))


def expanded_post() -> TemplatePost:
    """The LinuxCNC post with `drilling_style = expanded`: a hole is written as plain moves."""
    definition = _library().posts["linuxcnc"]
    return TemplatePost(replace(unnumbered(definition), settings=replace(definition.settings, line_numbers=False, drilling_style="expanded")))


def limited_post(unsupported=(), controller_id: str = "linuxcnc") -> TemplatePost:
    """The LinuxCNC post with some features taken away, to test the checks and the remedies of the generator (O4). A feature is
    worked out from the post (see `PostDefinition.features`), so it is taken away by taking away what it comes from."""
    definition = unnumbered(_library().posts["linuxcnc"])
    codes = dict(definition.codes)
    settings = definition.settings
    templates = dict(definition.templates)
    for feature in unsupported:
        for code_feature, name in CODE_FEATURES:
            if feature is code_feature:
                codes.pop(name, None)
        if feature is Feature.ARCS:
            codes.pop("arc_ccw", None)
            codes.pop("arc_cw", None)
        if feature is Feature.DIAMETER_MODE:
            settings = replace(settings, x_diameters=False)
        if feature is Feature.ARCS_IN_DIAMETER_MODE:
            settings = replace(settings, arcs_in_diameters=False)
        if feature is Feature.TOOL_CHANGE:
            templates.pop("tool_change", None)
    fallback = None if Feature.TOOL_CHANGE in set(unsupported) else definition.fallback  # the default post would bring them back
    return TemplatePost(replace(definition, post_id=controller_id, codes=codes, settings=settings, templates=templates, fallback=fallback))


def bar_feeder_definition():
    """The definition of the example post with the custom function bar_feed (the file in examples/posts)."""
    from pathlib import Path

    from wop.post.post_definition import parse_post

    text = (Path(__file__).resolve().parent.parent / BAR_FEEDER_FILE).read_text(encoding="utf-8")
    return unnumbered(parse_post(text, "bar_feeder", _library().posts["linuxcnc"]))  # as the other helpers: no line numbers


def bar_feeder_post() -> TemplatePost:
    return TemplatePost(bar_feeder_definition())
