import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from wop.adapters.linuxcnc_tools import (
    ToolTableBusy,
    apply_program_tool_table,
    backup_tool_table,
    format_tool_table,
    list_backups,
    parse_tool_table,
    read_tool_table,
    restore_tool_table,
    write_tool_table,
)
from wop.core.tooling.tool_table import ToolTableError
from wop.core.program_model.units import UnitSystem

SAMPLE_TABLE = """\
T1 P1 X+0.500000 Z-0.250000 D+0.800000 I+95.000000 J+25.000000 Q3 ;rough OD
T2 P2 X+0.000000 Z+0.000000 D+3.000000 I+0.000000 J+0.000000 Q0 U+1.5 ;groove 3mm
T12 P5 X+1.000000 Z+1.000000 D+0.000000 I+0.000000 J+0.000000 Q9
"""
FIRST = datetime(2026, 10, 14, 10, 0, 0)
SECOND = datetime(2026, 10, 14, 10, 0, 1)


class ParseTests(unittest.TestCase):
    """Requirement T4."""

    def test_sample_tools_appear(self):
        table = parse_tool_table(SAMPLE_TABLE)
        self.assertEqual([e.number for e in table.entries], [1, 2, 12])
        first = table.find(1)
        self.assertEqual((first.pocket, first.x_offset_mm, first.z_offset_mm), (1, 0.5, -0.25))
        self.assertEqual((first.front_angle_deg, first.back_angle_deg, first.orientation), (95, 25, 3))
        self.assertEqual(first.comment, "rough OD")
        self.assertEqual(table.find(12).pocket, 5)

    def test_unknown_words_are_kept(self):
        self.assertEqual(parse_tool_table(SAMPLE_TABLE).find(2).unparsed_words, ("U+1.5",))

    def test_pocket_defaults_to_the_tool_number(self):
        self.assertEqual(parse_tool_table("T7 X1").find(7).pocket, 7)

    def test_blank_lines_are_skipped(self):
        self.assertEqual(len(parse_tool_table("\nT1 P1\n\nT2 P2\n").entries), 2)

    def test_bad_lines_name_the_line(self):
        for text in ("T1 P1\nX1 Z1\n", "T1 P1 Xabc\n", "T1 P1 5\n"):
            with self.subTest(text=text):
                with self.assertRaises(ToolTableError) as caught:
                    parse_tool_table(text)
                self.assertIn("line", str(caught.exception))

    def test_imperial_values_are_converted(self):
        table = parse_tool_table("T1 P1 X1 Z-2 D0.5\n", UnitSystem.IMPERIAL)
        self.assertAlmostEqual(table.find(1).x_offset_mm, 25.4)
        self.assertAlmostEqual(table.find(1).z_offset_mm, -50.8)


class WriteTests(unittest.TestCase):
    def test_change_is_written_back_in_the_correct_format(self):
        table = parse_tool_table(SAMPLE_TABLE).renamed(1, "finish OD")
        text = format_tool_table(table)
        self.assertIn("T1 P1 X+0.500000 Z-0.250000 D+0.800000 I+95.000000 J+25.000000 Q3 ;finish OD", text)
        self.assertIn("U+1.5 ;groove 3mm", text)

    def test_parse_format_parse_is_stable(self):
        table = parse_tool_table(SAMPLE_TABLE)
        self.assertEqual(parse_tool_table(format_tool_table(table)), table)
        self.assertEqual(format_tool_table(table), SAMPLE_TABLE)

    def test_imperial_round_trip(self):
        table = parse_tool_table("T1 P1 X+1.000000 Z-2.000000 D+0.500000 I+0.000000 J+0.000000 Q0\n", UnitSystem.IMPERIAL)
        text = format_tool_table(table, UnitSystem.IMPERIAL)
        self.assertEqual(parse_tool_table(text, UnitSystem.IMPERIAL), table)

    def test_empty_table(self):
        self.assertEqual(format_tool_table(parse_tool_table("")), "")


class FileTests(unittest.TestCase):
    """Requirements T6 and T7."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "tool.tbl"
        # Original file with odd spacing so a rewrite would differ from it.
        self.original = b"T1  P1 X0.5   ;odd spacing\r\nT2 P2\r\n"
        self.path.write_bytes(self.original)

    def program_table(self):
        return parse_tool_table("T1 P1 X9 ;program tool\n")

    def test_read_and_write(self):
        table = read_tool_table(self.path)
        self.assertEqual(table.find(1).x_offset_mm, 0.5)
        write_tool_table(table.renamed(2, "two"), self.path)
        self.assertEqual(read_tool_table(self.path).find(2).comment, "two")

    def test_applying_makes_a_backup_and_restore_is_byte_identical(self):
        backup = apply_program_tool_table(
            self.program_table(), self.path, UnitSystem.METRIC, lambda: False, FIRST
        )
        self.assertNotEqual(self.path.read_bytes(), self.original)
        self.assertEqual(read_tool_table(self.path).find(1).comment, "program tool")
        restore_tool_table(backup, self.path)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_nothing_is_written_while_a_program_runs(self):
        with self.assertRaises(ToolTableBusy):
            apply_program_tool_table(
                self.program_table(), self.path, UnitSystem.METRIC, lambda: True, FIRST
            )
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(list_backups(self.path), [])

    def test_backups_are_never_replaced(self):
        first = backup_tool_table(self.path, FIRST)
        second = backup_tool_table(self.path, SECOND)
        self.assertEqual(list_backups(self.path), [first, second])
        with self.assertRaises(ToolTableError):
            backup_tool_table(self.path, FIRST)

    def test_applying_when_there_is_no_file_yet(self):
        new_path = Path(self.folder.name) / "new.tbl"
        result = apply_program_tool_table(
            self.program_table(), new_path, UnitSystem.METRIC, lambda: False, FIRST
        )
        self.assertIsNone(result)
        self.assertTrue(new_path.exists())


class RealToolTableTests(unittest.TestCase):
    """The tool.tbl of the Schaublin 125 CNC: has Y A B C U V W words and no signs."""

    def setUp(self):
        path = Path(__file__).parent / "data" / "schaublin_125_tool.tbl"
        self.table = read_tool_table(path)

    def test_tools_are_read(self):
        self.assertEqual([e.number for e in self.table.entries], [1, 2, 3, 4])
        third = self.table.find(3)
        self.assertEqual((third.x_offset_mm, third.z_offset_mm, third.diameter_mm), (-12.455, -6.131, 0.2))
        self.assertEqual((third.front_angle_deg, third.back_angle_deg, third.orientation), (105, 75, 6))
        self.assertEqual(third.comment, "Sample Tool")

    def test_other_axis_words_are_kept_when_written(self):
        text = format_tool_table(self.table)
        for word in ("Y0.0", "A0.0", "C0.0", "W0.0"):
            self.assertIn(word, text)
        self.assertEqual(parse_tool_table(text), self.table)


if __name__ == "__main__":
    unittest.main()
