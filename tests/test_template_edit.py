"""The changes of a template text for the modifier buttons (no toolkit)."""

import unittest

from wop.ui.template_edit import (
    TemplateEditError,
    apply_changed,
    apply_comment,
    apply_optional,
    apply_protect,
    apply_unwrap,
    available_options,
    remove_option,
    set_option,
    token_at,
    written_options,
)

LINE = "<code feed> X<X> Z<Z> I<I> K<K> F<F>"
F = LINE.index("F<F>")


def select(text, piece):
    start = text.index(piece)
    return start, start + len(piece)


class ChangedTests(unittest.TestCase):
    def test_a_selected_statement_becomes_optional_and_changed_with_its_space_inside(self):
        edit = apply_changed(LINE, *select(LINE, "F<F>"))
        self.assertEqual(edit.text, "<code feed> X<X> Z<Z> I<I> K<K>[ F<F changed>]")
        self.assertEqual(edit.text[edit.start:edit.end], "[ F<F changed>]")

    def test_without_a_selection_the_statement_under_the_cursor_is_meant(self):
        for cursor in (F, F + 2, F + 4):
            self.assertEqual(apply_changed(LINE, cursor, cursor).text, "<code feed> X<X> Z<Z> I<I> K<K>[ F<F changed>]")

    def test_a_second_click_takes_the_brackets_and_changed_away(self):
        edit = apply_changed(LINE, F, F)
        again = apply_changed(edit.text, edit.start, edit.end)
        self.assertEqual(again.text, LINE)
        inside = edit.text.index("F<F changed>") + 3
        self.assertEqual(apply_changed(edit.text, inside, inside).text, LINE)  # the cursor inside the brackets does it too

    def test_several_tokens_all_get_changed(self):
        text = "G1 X<X> Z<Z>"
        edit = apply_changed(text, *select(text, "X<X> Z<Z>"))
        self.assertEqual(edit.text, "G1[ X<X changed> Z<Z changed>]")

    def test_a_code_token_with_its_word_is_changed(self):
        text = "<code rapid> X<X>"
        self.assertEqual(apply_changed(text, 0, 0).text, "[<code rapid changed>] X<X>")

    def test_a_token_that_cannot_be_changed_is_refused(self):
        with self.assertRaises(TemplateEditError):
            apply_changed("N<N> (<comment text>)", *select("N<N> (<comment text>)", "(<comment text>)"))

    def test_on_a_part_that_is_optional_already_it_adds_changed(self):
        self.assertEqual(apply_changed("[X<X>]", 2, 2).text, "[X<X changed>]")

    def test_each_selected_line_is_changed_on_its_own(self):
        text = "X<X>\nZ<Z>"
        self.assertEqual(apply_changed(text, 0, len(text)).text, "[X<X changed>]\n[Z<Z changed>]")

    def test_a_selection_that_cuts_a_token_is_refused(self):
        with self.assertRaises(TemplateEditError):
            apply_changed(LINE, F, F + 3)

    def test_comment_lines_are_left_alone(self):
        text = "# F<F>\nF<F>"
        self.assertEqual(apply_changed(text, 0, len(text)).text, "# F<F>\n[F<F changed>]")


class OtherButtonTests(unittest.TestCase):
    def test_optional_puts_brackets_round_the_statement(self):
        self.assertEqual(apply_optional("G1 X<X> Z<Z>", *select("G1 X<X> Z<Z>", "X<X>")).text, "G1[ X<X>] Z<Z>")
        with self.assertRaises(TemplateEditError):
            apply_optional("[X<X>]", 2, 2)

    def test_unwrap_takes_one_level_of_brackets_and_leaves_the_tokens(self):
        self.assertEqual(apply_unwrap("a[ F<F changed>]", 5, 5).text, "a F<F changed>")
        self.assertEqual(apply_unwrap("a[ F<F>]", 1, len("a[ F<F>]")).text, "a F<F>")
        with self.assertRaises(TemplateEditError):
            apply_unwrap("a F<F>", 3, 3)

    def test_protect_text_and_back(self):
        text = "G1 (a [b])"
        edit = apply_protect(text, *select(text, "(a"))
        self.assertTrue(edit.text.startswith("G1 <text>(a</text>"))
        back = apply_protect(edit.text, edit.start, edit.end)
        self.assertEqual(back.text, text)

    def test_comment_out_and_back(self):
        text = "a\nb\nc"
        edit = apply_comment(text, 0, 3)
        self.assertEqual(edit.text, "# a\n# b\nc")
        self.assertEqual(apply_comment(edit.text, 0, 7).text, "a\nb\nc")
        self.assertEqual(apply_comment("a\nb", 3, 3).text, "a\n# b")  # the cursor line

    def test_a_change_that_would_not_read_is_refused(self):
        with self.assertRaises(TemplateEditError):
            apply_optional("X<X] ", 0, 4)  # a stray bracket: nothing is changed


class OptionTests(unittest.TestCase):
    def test_the_token_under_the_cursor_or_in_the_selection(self):
        text = "G1 X<X scaled> Z<Z>"
        found = token_at(text, text.index("X<X") + 3, text.index("X<X") + 3)
        self.assertEqual((found.token.name, found.options), ("X", ("scaled",)))
        self.assertEqual(token_at(text, 0, len(text)).token.name, "X")  # the first token of a selection
        self.assertIsNone(token_at(text, 1, 1))

    def test_the_options_a_token_has(self):
        found = token_at("<tool name>", 3, 3)
        names = [name for name, _meaning, _value in available_options(found.token)]
        self.assertIn("safe", names)
        self.assertIn("upper", names)
        self.assertNotIn("scaled", names)

    def test_a_flag_is_added_and_removed(self):
        text = "X<X>"
        found = token_at(text, 2, 2)
        added = set_option(text, found, "scaled", None)
        self.assertEqual(added.text, "X<X scaled>")
        self.assertEqual(written_options(token_at(added.text, 2, 2)), {"scaled": ""})
        self.assertEqual(remove_option(added.text, token_at(added.text, 2, 2), "scaled").text, "X<X>")

    def test_a_value_option_is_written_with_its_value_and_replaced(self):
        text = "X<X>"
        added = set_option(text, token_at(text, 2, 2), "decimals", "2")
        self.assertEqual(added.text, "X<X decimals=2>")
        self.assertEqual(set_option(added.text, token_at(added.text, 2, 2), "decimals", "4").text, "X<X decimals=4>")
        spaced = set_option(text, token_at(text, 2, 2), "prefix", "X ")
        self.assertEqual(spaced.text, 'X<X prefix="X ">')

    def test_an_option_the_token_does_not_know_does_not_break_the_edit_check_here(self):
        # the editor shows only options of the token; the reader of the template (the red line) judges the rest
        text = "N<N>"
        self.assertEqual(set_option(text, token_at(text, 2, 2), "upper", None).text, "N<N upper>")


if __name__ == "__main__":
    unittest.main()
