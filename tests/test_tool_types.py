import json
import unittest
from dataclasses import replace

from wop.core.tooling.tool import ToolError, ToolMaterial
from wop.core.files.tool_io import tool_from_dict, tool_to_dict
from wop.core.tool_types import TOOL_TYPES, definition_of, make_tool
from wop.ui.block_forms import form_for
from wop.ui.tool_preview import tool_svg


class ToolTypeTests(unittest.TestCase):
    def test_every_type_builds_a_tool_from_its_default_definition(self):
        for tool_type in TOOL_TYPES.types():
            with self.subTest(type=tool_type.type_name):
                tool = make_tool(tool_type.type_name, 7, tool_type.default())
                self.assertEqual(tool.number, 7)
                self.assertEqual(tool.kind, tool_type.type_name)
                self.assertTrue(tool.name)

    def test_the_forms_only_hold_the_fields_of_their_type(self):
        paths = {t.type_name: {spec.path[0] for spec in form_for(t.default())} for t in TOOL_TYPES.types()}
        self.assertNotIn("nose_radius_mm", paths["drill"])
        self.assertNotIn("diameter_mm", paths["turning"])
        self.assertIn("diameter_mm", paths["drill"])
        self.assertIn("side_edge_angle_deg", paths["turning"])
        for names in paths.values():
            self.assertIn("material", names)

    def test_the_definition_survives_a_save_and_load_and_rebuilds_the_same_tool(self):
        for tool_type in TOOL_TYPES.types():
            with self.subTest(type=tool_type.type_name):
                tool = make_tool(tool_type.type_name, 3, replace(tool_type.default(), material=ToolMaterial.CERMET))
                loaded = tool_from_dict(json.loads(json.dumps(tool_to_dict(tool))))
                self.assertEqual(loaded, tool)
                self.assertEqual(definition_of(loaded), definition_of(tool))
                self.assertEqual(loaded.material, ToolMaterial.CERMET)

    def test_a_tool_file_without_type_or_material_still_loads(self):
        data = tool_to_dict(make_tool("turning", 1, TOOL_TYPES.get("turning").default()))
        for key in ("kind", "definition", "material"):
            data.pop(key, None)
        tool = tool_from_dict(data)
        self.assertEqual(tool.kind, "")
        self.assertEqual(tool.material, ToolMaterial.CARBIDE)
        self.assertIsNone(definition_of(tool))

    def test_impossible_values_are_refused(self):
        with self.assertRaises(ToolError):
            make_tool("drill", 1, replace(TOOL_TYPES.get("drill").default(), diameter_mm=0))
        with self.assertRaises(ToolError):
            make_tool("groove", 1, replace(TOOL_TYPES.get("groove").default(), reach_mm=0))

    def test_inside_gives_a_tool_for_boring(self):
        tool = make_tool("groove", 1, replace(TOOL_TYPES.get("groove").default(), inside=True))
        self.assertTrue(all(p.segment.end.x <= 0 for p in tool.shape.pieces))

    def test_the_turning_form_has_the_dimensions_but_not_the_front_edge_length(self):
        names = {spec.path[0] for spec in form_for(TOOL_TYPES.get("turning").default())}
        for name in ("hand", "nose_radius_mm", "side_edge_length_mm", "side_edge_angle_deg", "front_edge_angle_deg", "width_mm", "length_mm"):
            self.assertIn(name, names)
        self.assertNotIn("front_edge_length_mm", names)

    def test_the_boring_form_has_the_dimensions_and_the_hand(self):
        names = {spec.path[0] for spec in form_for(TOOL_TYPES.get("boring").default())}
        for name in ("nose_radius_mm", "wall_edge_length_mm", "wall_edge_angle_deg", "end_edge_angle_deg", "front_width_mm",
                     "bar_width_mm", "length_mm", "hand"):
            self.assertIn(name, names)

    def test_the_add_menu_order(self):
        self.assertEqual(
            [t.label for t in TOOL_TYPES.types()],
            ["Turning tool", "Turning tool (ISO holder)", "Boring bar", "Boring bar (ISO)", "Grooving tool", "Threading tool", "Drill"],
        )

    def test_a_new_type_is_one_registration(self):
        from wop.core.tool_types.base import ToolType, ToolTypeRegistry
        from dataclasses import dataclass
        from wop.core.tooling.tool_presets import block_tool

        @dataclass(frozen=True)
        class Definition:
            name: str = ""
            material: ToolMaterial = ToolMaterial.HSS

        registry = ToolTypeRegistry()

        @registry.register
        class Custom(ToolType):
            type_name = "custom"
            label = "Custom"
            definition_class = Definition

            def build(self, number, definition):
                return block_tool(number, definition.name or "custom")

        self.assertEqual([t.type_name for t in registry.types()], ["custom"])

    def test_the_picture_has_cutter_holder_and_tip(self):
        tool = make_tool("turning", 1, TOOL_TYPES.get("turning").default())
        text = tool_svg(tool)
        self.assertIn("<polyline", text)
        self.assertIn("<circle", text)


if __name__ == "__main__":
    unittest.main()
