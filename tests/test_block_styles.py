import unittest

from wop.core.blocks.styles import DEFAULT_STYLE_KEY, STYLES, StyleError, StyleInfo, StyleRegistry


class StyleRegistryTests(unittest.TestCase):
    def test_a_type_without_styles_has_the_default_one(self):
        self.assertEqual([s.key for s in STYLES.styles_for("facing")], [DEFAULT_STYLE_KEY])
        self.assertEqual(STYLES.get("facing", "").key, DEFAULT_STYLE_KEY)  # an old project stores nothing

    def test_a_second_style_comes_after_the_default_and_is_found_by_its_key(self):
        registry = StyleRegistry()
        registry.register("facing", StyleInfo("inside_out", "From the centre outwards", "Starts at the centre. Leaves a pip."))
        self.assertEqual([s.key for s in registry.styles_for("facing")], [DEFAULT_STYLE_KEY, "inside_out"])
        self.assertEqual(registry.get("facing", "inside_out").label, "From the centre outwards")

    def test_a_style_is_registered_once_and_an_unknown_one_is_refused(self):
        registry = StyleRegistry()
        registry.register("turning", StyleInfo("zigzag", "Zigzag"))
        with self.assertRaises(StyleError):
            registry.register("turning", StyleInfo("zigzag", "Again"))
        with self.assertRaises(StyleError):
            registry.get("turning", "nope")


class ContractTests(unittest.TestCase):
    def test_the_contract_compares_removed_region_and_end(self):
        from wop.core.blocks.styles import contract_problems
        from wop.core.geometry import Point
        from wop.core.geometry.region import Region

        box = Region.from_points([Point(0, 0), Point(5, 0), Point(5, -5), Point(0, -5)])
        smaller = Region.from_points([Point(0, 0), Point(5, 0), Point(5, -2), Point(0, -2)])
        self.assertEqual(contract_problems(box, Point(9, 9), box, Point(9, 9)), [])
        found = contract_problems(box, Point(9, 9), smaller, Point(8, 8))
        self.assertEqual(len(found), 2)


if __name__ == "__main__":
    unittest.main()
