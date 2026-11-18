# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for yearbook_pdf: drawing the Yearbook page model as a PDF.

Run:  .venv\\Scripts\\python -m unittest test_yearbook_pdf -v
"""

import datetime as dt
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import archive
import palette
import yearbook as yb
import yearbook_pdf

D = dt.date


def table(*teams):
    return tuple(yb.TableLine(i, t, 3, 2, 1, 0, 5, 2, 3, 7, "WWD") for i, t in enumerate(teams, start=1))


def week(n, home="Hull City", away="Leeds United"):
    return yb.LeaguePage("Premier League", n, f"Matchweek {n} · Sat 8 – Mon 10 Aug",
                         (yb.BookMatch("Sat 8", home, away, "2-0"), yb.BookMatch("Mon 10", "Derby County", "Wrexham", "n/a")),
                         table(home, away, "Derby County", "Wrexham"), D(2026, 8, 8 + n))


def book(*pages):
    cover = archive.BookCoverage(1, D(2026, 8, 9), D(2026, 8, 9), (), True)
    title = yb.TitlePage("2026/27", ("Built from 1 banked save.", "Season in progress."))
    return yb.Yearbook("2026/27", cover, (title, *pages))


class FormColourTests(unittest.TestCase):
    def test_win_draw_and_loss_are_three_different_colours_that_read_on_white_paper(self):
        self.assertEqual(set(yearbook_pdf.FORM_INK), set("WDL"))
        self.assertEqual(len(set(yearbook_pdf.FORM_INK.values())), 3)
        for letter, colour in yearbook_pdf.FORM_INK.items():
            self.assertGreaterEqual(palette.contrast_ratio(colour, "#ffffff"), 4.5, letter)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "Yearbook 2026-27.pdf"

    def render(self, built):
        yearbook_pdf.render(built, self.path)
        return self.path.read_bytes()

    def test_render_writes_a_pdf(self):
        data = self.render(book(week(1)))
        self.assertTrue(data.startswith(b"%PDF-"))

    def test_a_full_matchweek_with_a_twenty_club_table_takes_a_page_of_its_own(self):
        def full(n):
            clubs = [f"Club {i}" for i in range(20)]
            matches = tuple(yb.BookMatch("Sat 8", clubs[i], clubs[i + 10], "1-0") for i in range(10))
            return yb.LeaguePage("Premier League", n, f"Matchweek {n} · Sat 8 – Mon 10 Aug", matches, table(*clubs),
                                 D(2026, 8, 8 + n))
        data = self.render(book(full(1), full(2), full(3)))
        self.assertGreaterEqual(len(re.findall(rb"/Type\s*/Page\b", data)), 4)       # the title page and three more

    def test_names_outside_latin_one_print_because_a_unicode_font_is_embedded(self):
        data = self.render(book(week(1, home="Łódź FC", away="Dinamo Zagreb")))
        self.assertIn(b"DejaVuSans", data)

    def test_cup_blocks_and_final_tables_render(self):
        cup = yb.CupBlock("FA Cup", "Quarter-final", "2nd leg", "Wed 18 Mar",
                          (yb.BookMatch("", "Leeds United", "Hull City", "2-0", "(2-2 agg; Hull City advance)"),), D(2026, 3, 18))
        final = yb.FinalTablesPage((("Premier League", table("Hull City", "Leeds United")),))
        self.assertTrue(self.render(book(week(1), cup, final)).startswith(b"%PDF-"))

    def test_a_small_block_shares_its_page_with_the_matchweek_that_follows_when_both_fit(self):
        cup = yb.CupBlock("FA Cup", "Fourth round", "", "Sat 1 Aug", (yb.BookMatch("", "Hull City", "Leeds United", "2-1"),),
                          D(2026, 8, 1))
        data = self.render(book(cup, week(1)))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page\b", data)), 2)        # the title page, then one page for both

    def test_a_failure_while_drawing_leaves_no_file_and_no_scrap_behind(self):
        with mock.patch.object(yearbook_pdf, "SimpleDocTemplate") as doc:
            doc.return_value.build.side_effect = RuntimeError("out of paper")
            with self.assertRaises(RuntimeError):
                yearbook_pdf.render(book(week(1)), self.path)
        self.assertEqual(list(Path(self.folder.name).iterdir()), [])

    def test_a_failure_keeps_an_earlier_book_that_was_already_there(self):
        yearbook_pdf.render(book(week(1)), self.path)
        before = self.path.read_bytes()
        with mock.patch.object(yearbook_pdf, "SimpleDocTemplate") as doc:
            doc.return_value.build.side_effect = RuntimeError("out of paper")
            with self.assertRaises(RuntimeError):
                yearbook_pdf.render(book(week(1), week(2)), self.path)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
