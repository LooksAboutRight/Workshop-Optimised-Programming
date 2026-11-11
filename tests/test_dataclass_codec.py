import unittest
from dataclasses import dataclass
from enum import Enum

from wop.core.files.dataclass_codec import CodecError, from_data, to_data


class Colour(Enum):
    RED = "r"
    BLUE = "b"


@dataclass(frozen=True)
class Inner:
    size: float = 1


@dataclass(frozen=True)
class Outer:
    name: str
    colour: Colour
    inner: Inner
    limit: float | None = None
    items: tuple[Inner, ...] = ()
    flag: bool = False


SAMPLE = Outer("x", Colour.BLUE, Inner(2.5), 3, (Inner(1), Inner(2)), True)


class CodecTests(unittest.TestCase):
    def test_round_trip(self):
        data = to_data(SAMPLE)
        self.assertEqual(from_data(Outer, data), SAMPLE)

    def test_enums_are_stored_by_name_and_numbers_keep_their_kind(self):
        data = to_data(SAMPLE)
        self.assertEqual(data["colour"], "BLUE")
        self.assertIsInstance(data["limit"], int)
        self.assertIsInstance(from_data(Outer, data).limit, int)

    def test_missing_optional_fields_use_the_default(self):
        data = {"name": "x", "colour": "RED", "inner": {}}
        self.assertEqual(from_data(Outer, data), Outer("x", Colour.RED, Inner(1)))

    def test_problems_are_reported_in_words(self):
        good = to_data(SAMPLE)
        for change in (
            {"colour": "GREEN"}, {"name": 3}, {"flag": 1}, {"limit": "high"},
            {"items": 5}, {"unknown": 1},
        ):
            with self.subTest(change=change):
                with self.assertRaises(CodecError):
                    from_data(Outer, {**good, **change})
        missing = dict(good)
        del missing["name"]
        with self.assertRaises(CodecError):
            from_data(Outer, missing)


if __name__ == "__main__":
    unittest.main()
