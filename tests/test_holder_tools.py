"""ISO holders and boring bars: codes, dropdown lists kept in step, and the shapes built (Python 3.11 and later)."""

import unittest
from dataclasses import replace

from wop.core.constants import BORING_BARS, BORING_STYLES, HOLDER_STYLES
from wop.core.tooling.holder_designation import (
    HolderError,
    format_bar_code,
    format_holder_code,
    insert_size_codes,
    parse_bar_code,
    parse_holder_code,
    sections_for,
    shapes_for_kappa,
)
from wop.core.tooling.tool import ToolError, ToolSegmentRole
from wop.core.files.tool_io import tool_from_dict, tool_to_dict
from wop.core.tool_types import TOOL_TYPES, definition_of, info_of, make_tool
from wop.ui.block_forms import FieldKind, form_for

LEFT, RIGHT = "L", "R"


def holder_definition(**changes):
    kind = TOOL_TYPES.get("holder")
    return kind.reconcile(kind.default(), replace(kind.default(), **changes))


class CodeTests(unittest.TestCase):
    def test_a_holder_code_is_read_and_written_again(self):
        parts = parse_holder_code("pclnr2525m12")
        self.assertEqual((parts.clamping, parts.shape, parts.style, parts.hand, parts.section, parts.length, parts.size),
                         ("P", "C", "L", "R", "2525", "M", "12"))
        self.assertEqual(format_holder_code(parts), "PCLNR 2525 M12")

    def test_the_tolerance_and_manufacturer_part_of_a_holder_code_is_accepted(self):
        self.assertEqual(parse_holder_code("PCLNR 2525 M12-X").size, "12")

    def test_a_boring_bar_code_is_read_and_written_again(self):
        parts = parse_bar_code("S25S-PCLNR 12")
        self.assertEqual((parts.bar_type, parts.diameter, parts.length, parts.style, parts.size), ("S", "25", "S", "L", "12"))
        self.assertEqual(format_bar_code(parts), "S25S-PCLNR 12")

    def test_wrong_codes_name_the_position(self):
        with self.assertRaises(HolderError):
            parse_holder_code("PCLNR 2525")
        with self.assertRaises(HolderError) as caught:
            parse_holder_code("PCXNR 2525 M12")
        self.assertIn("style", str(caught.exception))
        with self.assertRaises(HolderError):
            parse_bar_code("S27S-PCLNR 12")


class ShapeTests(unittest.TestCase):
    def test_every_style_and_fitting_shape_gives_a_closed_shape_with_a_cutter_and_a_holder(self):
        kind = TOOL_TYPES.get("holder")
        for style in HOLDER_STYLES:
            for shape in shapes_for_kappa(style[1]):
                for hand in (RIGHT, LEFT):
                    size = insert_size_codes(shape)[1]
                    d = replace(kind.default(), style=style[0], shape=shape, hand=hand, insert_size=size,
                                section=sections_for(style[0])[0], insert_code=f"{shape}NMG {size}0408")
                    tool = make_tool("holder", 1, d)
                    roles = {p.role for p in tool.shape.pieces}
                    self.assertEqual(roles, {ToolSegmentRole.CUTTER, ToolSegmentRole.HOLDER}, (style[0], shape, hand))

    def test_a_left_hand_holder_is_the_right_hand_one_mirrored_in_z(self):
        right = make_tool("holder", 1, holder_definition(hand=RIGHT)).shape.segments
        left = make_tool("holder", 1, holder_definition(hand=LEFT)).shape.segments
        self.assertEqual(len(right), len(left))
        for a, b in zip(right, left):
            self.assertAlmostEqual(a.start.x, b.start.x)
            self.assertAlmostEqual(a.start.z, -b.start.z)

    def test_the_boring_bar_body_is_towards_the_axis_and_the_shank_runs_along_z(self):
        tool = make_tool("boring_bar", 1, TOOL_TYPES.get("boring_bar").default())
        points = [s.start for s in tool.shape.segments]
        self.assertLess(min(p.x for p in points), 0)
        self.assertGreater(max(p.z for p in points), 0)

    def test_boring_bars_of_all_sizes_and_styles_are_valid_or_refused_with_a_reason(self):
        kind = TOOL_TYPES.get("boring_bar")
        built = 0
        for style in BORING_STYLES:
            for shape in shapes_for_kappa(style[1]):
                for bar in BORING_BARS:
                    size = insert_size_codes(shape)[0]
                    d = replace(kind.default(), style=style[0], shape=shape, diameter=str(bar[0]), insert_size=size,
                                insert_code=f"{shape}NMG {size}0408")
                    try:
                        make_tool("boring_bar", 1, d)
                        built += 1
                    except ToolError:
                        pass
        self.assertGreater(built, len(BORING_BARS))

    def test_a_too_big_insert_for_a_small_bar_is_refused(self):
        kind = TOOL_TYPES.get("boring_bar")
        d = kind.reconcile(kind.default(), replace(kind.default(), insert_code="TNMG 220408"))
        with self.assertRaises(ToolError):
            make_tool("boring_bar", 1, replace(d, diameter="8"))


class ReconcileTests(unittest.TestCase):
    def test_typing_the_holder_code_sets_the_parts_and_the_insert_code(self):
        d = holder_definition(holder_code="SDJNL 2020 K11")
        self.assertEqual((d.clamping, d.shape, d.style, d.hand, d.section, d.length, d.insert_size),
                         ("S", "D", "J", "L", "2020", "K", "11"))
        self.assertEqual(d.insert_code, "DNMG 110408")

    def test_typing_the_insert_code_sets_the_parts_and_the_holder_code(self):
        d = holder_definition(insert_code="TNMG 160408")
        self.assertEqual((d.shape, d.insert_size, d.holder_code), ("T", "16", "PTLNR 2525 M16"))

    def test_choosing_a_part_rewrites_both_codes(self):
        d = holder_definition(hand=LEFT, thickness="06")
        self.assertEqual(d.holder_code, "PCLNL 2525 M12")
        self.assertEqual(d.insert_code, "CNMG 120608")

    def test_a_style_that_does_not_fit_the_shape_changes_the_shape(self):
        d = holder_definition(shape="C", style="H")  # 107.5 + 80 degrees is more than a straight angle
        self.assertNotEqual(d.shape, "C")
        make_tool("holder", 1, d)

    def test_a_wrong_typed_code_is_an_error(self):
        kind = TOOL_TYPES.get("holder")
        with self.assertRaises(ValueError):
            kind.reconcile(kind.default(), replace(kind.default(), holder_code="nonsense"))

    def test_an_insert_that_disagrees_with_the_holder_is_refused_by_build(self):
        d = replace(holder_definition(), insert_code="TNMG 160408")
        with self.assertRaises(ToolError):
            make_tool("holder", 1, d)


class FormTests(unittest.TestCase):
    def test_the_parts_are_dropdowns_and_the_codes_are_text(self):
        specs = {s.path[0]: s for s in form_for(TOOL_TYPES.get("holder").default())}
        for name in ("shape", "style", "hand", "section", "length", "insert_size", "corner_radius"):
            self.assertIs(specs[name].kind, FieldKind.CHOICE, name)
        for name in ("clamping", "clearance", "tolerance", "insert_type", "thickness"):
            self.assertNotIn(name, specs)
        self.assertIs(specs["holder_code"].kind, FieldKind.TEXT)
        self.assertIs(specs["insert_code"].kind, FieldKind.TEXT)

    def test_the_shape_list_only_offers_shapes_that_fit_the_style(self):
        d = holder_definition(style="H")
        shapes = {s.path[0]: s for s in form_for(d)}["shape"].choices
        self.assertNotIn("C", [c.value for c in shapes])
        self.assertTrue(shapes)

    def test_the_size_list_follows_the_shape(self):
        sizes = {s.path[0]: s for s in form_for(holder_definition(shape="T", insert_code="TNMG 160408"))}["insert_size"].choices
        self.assertIn("16", [c.value for c in sizes])

    def test_the_current_value_is_always_in_its_list(self):
        d = replace(holder_definition(), section="5050")
        choices = {s.path[0]: s for s in form_for(d)}["section"].choices
        self.assertIn("5050", [c.value for c in choices])


class StorageTests(unittest.TestCase):
    def test_the_definition_survives_saving_and_reloading(self):
        for type_name in ("holder", "boring_bar"):
            tool = make_tool(type_name, 3, TOOL_TYPES.get(type_name).default())
            again = tool_from_dict(tool_to_dict(tool))
            self.assertEqual(definition_of(again), definition_of(tool))
            self.assertEqual(again.shape, tool.shape)

    def test_the_info_names_the_guessed_values(self):
        for type_name in ("holder", "boring_bar"):
            tool = make_tool(type_name, 1, TOOL_TYPES.get(type_name).default())
            self.assertTrue(any("Guessed" in line for line in info_of(tool)))


if __name__ == "__main__":
    unittest.main()
