"""The template language: reading a line, and the way numbers are written."""

import unittest

from wop.post.numbers import NumberFormat, OptionError, format_number, parse_options
from wop.post.template import Literal, OptionalPart, RawToken, TemplateError, parse_line, split_words

PLAIN = NumberFormat(3)


def number(value, *words, base=PLAIN):
    allowed = frozenset(w.partition("=")[0] for w in words)
    return format_number(value, base, parse_options(tuple(words), allowed))


class ParseTests(unittest.TestCase):
    def test_text_and_tokens(self):
        nodes = parse_line("G1 X<X> Z<Z>")
        self.assertEqual(nodes, (Literal("G1 X"), RawToken(("X",), 4), Literal(" Z"), RawToken(("Z",), 9)))

    def test_a_token_has_words_and_options(self):
        node = parse_line("<I absolute decimals=2>")[0]
        self.assertEqual(node.words, ("I", "absolute", "decimals=2"))

    def test_an_optional_part_holds_text_and_tokens_and_can_nest(self):
        nodes = parse_line("A [ B<X> [C] ] D")
        self.assertEqual(nodes[0], Literal("A "))
        outer = nodes[1]
        self.assertIsInstance(outer, OptionalPart)
        self.assertIsInstance(outer.parts[-2] if len(outer.parts) > 2 else outer.parts[-1], (OptionalPart, Literal))
        self.assertTrue(any(isinstance(p, OptionalPart) for p in outer.parts))
        self.assertEqual(nodes[2], Literal(" D"))

    def test_text_tags_hold_anything_as_it_is(self):
        nodes = parse_line("<text>[a <b>]</text><X>")
        self.assertEqual(nodes[0], Literal("[a <b>]", protected=True))
        self.assertEqual(nodes[1].words, ("X",))

    def test_a_quote_holds_spaces(self):
        self.assertEqual(split_words('X prefix="G1 "', 0), ("X", "prefix=G1 "))

    def test_an_empty_text_tag_is_an_explicit_blank_line(self):
        self.assertEqual(parse_line("<text></text>"), (Literal("", protected=True),))

    def test_errors_say_where(self):
        for text, column in (("G1 <X", 3), ("G1 [X", 3), ("G1 X]", 4), ("<text>abc", 0), ("A <> B", 2), ('<X prefix="a>', 0)):
            with self.subTest(text=text):
                with self.assertRaises(TemplateError) as caught:
                    parse_line(text)
                self.assertEqual(caught.exception.position, column)


class NumberTests(unittest.TestCase):
    def test_the_default_is_the_shortest_text(self):
        self.assertEqual([number(v) for v in (10, 10.5, 0.1234, -3.0)], ["10", "10.5", "0.123", "-3"])

    def test_minus_zero_is_zero(self):
        self.assertEqual(number(-0.0004), "0")

    def test_decimals_and_zeros(self):
        self.assertEqual(number(10.5, "decimals=1"), "10.5")
        self.assertEqual(number(10, "zeros"), "10.000")
        self.assertEqual(number(10, "zeros", "decimals=1"), "10.0")

    def test_a_decimal_point_is_written_when_asked(self):
        self.assertEqual(number(10, "point"), "10.")
        self.assertEqual(number(0, "point"), "0.")
        self.assertEqual(number(0.5, "point"), "0.5")

    def test_the_post_defaults_are_the_same_as_the_options(self):
        fanuc = NumberFormat(3, point=True)
        self.assertEqual(number(10, base=fanuc), "10.")
        self.assertEqual(number(-2.5, base=fanuc), "-2.5")

    def test_the_point_of_the_post_is_not_written_into_whole_numbers_that_are_asked_for(self):
        fanuc = NumberFormat(3, point=True)
        self.assertEqual(number(0.92, "scale=1000", "decimals=0", base=fanuc), "920")
        self.assertEqual(number(10.5, "scaled", base=fanuc), "10500")
        self.assertEqual(number(10, "decimals=0", "point", base=fanuc), "10.")  # unless the token asks for it

    def test_sign_options(self):
        self.assertEqual(number(5, "plus"), "+5")
        self.assertEqual(number(-5, "abs"), "5")
        self.assertEqual(number(0, "plus"), "0")

    def test_scale_and_scaled_integers(self):
        self.assertEqual(number(0.92, "scale=1000", "decimals=0"), "920")
        self.assertEqual(number(10.5, "scaled"), "10500")
        self.assertEqual(number(10.5, "scaled", "decimals=1"), "105")

    def test_width_fills_with_zeros(self):
        self.assertEqual(number(2, "decimals=0", "width=2"), "02")
        self.assertEqual(number(29.5, "decimals=0", "width=2"), "30")
        self.assertEqual(number(-2, "decimals=0", "width=3"), "-002")


class OptionTests(unittest.TestCase):
    def test_an_unknown_option_names_the_ones_there_are(self):
        with self.assertRaises(OptionError) as caught:
            parse_options(("zeroes",), frozenset({"zeros"}))
        self.assertIn("zeros", str(caught.exception))

    def test_a_value_option_needs_its_value_and_a_flag_takes_none(self):
        with self.assertRaises(OptionError):
            parse_options(("decimals",), frozenset({"decimals"}))
        with self.assertRaises(OptionError):
            parse_options(("zeros=1",), frozenset({"zeros"}))

    def test_contradictions_are_refused(self):
        with self.assertRaises(OptionError):
            parse_options(("incremental", "absolute"), frozenset({"incremental", "absolute"}))
        with self.assertRaises(OptionError):
            parse_options(("diameter", "radius"), frozenset({"diameter", "radius"}))

    def test_decimals_must_be_a_whole_number(self):
        with self.assertRaises(OptionError):
            parse_options(("decimals=x",), frozenset({"decimals"}))


if __name__ == "__main__":
    unittest.main()
