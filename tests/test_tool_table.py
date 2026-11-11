import unittest

from wop.core.tooling.tool_table import ToolTable, ToolTableEntry, ToolTableError


def entry(number, comment=""):
    return ToolTableEntry(number, number, comment=comment)


class ToolTableTests(unittest.TestCase):
    def test_find_and_replace(self):
        table = ToolTable((entry(1, "a"), entry(2, "b")))
        self.assertEqual(table.find(2).comment, "b")
        self.assertIsNone(table.find(3))
        changed = table.with_entry(entry(2, "new"))
        self.assertEqual([e.comment for e in changed.entries], ["a", "new"])
        self.assertEqual(table.find(2).comment, "b")

    def test_append_remove_rename(self):
        table = ToolTable((entry(1),)).with_entry(entry(5))
        self.assertEqual([e.number for e in table.entries], [1, 5])
        self.assertEqual([e.number for e in table.without(1).entries], [5])
        self.assertEqual(table.renamed(5, "boring bar").find(5).comment, "boring bar")
        with self.assertRaises(ToolTableError):
            table.renamed(9, "x")

    def test_invalid_data_is_rejected(self):
        with self.assertRaises(ToolTableError):
            ToolTable((entry(1), entry(1)))
        with self.assertRaises(ToolTableError):
            ToolTableEntry(-1, 1)
        with self.assertRaises(ToolTableError):
            ToolTableEntry(1, 1, orientation=10)


if __name__ == "__main__":
    unittest.main()
