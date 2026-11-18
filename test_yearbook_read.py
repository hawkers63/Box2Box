# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for yearbook_read: the Yearbook's page model as pages to read in the window. No window here.

Run:  .venv\\Scripts\\python -m unittest test_yearbook_read -v
"""

import datetime as dt
import unittest

import archive
import yearbook as yb
import yearbook_pdf
import yearbook_read as yr

D = dt.date


def table(*teams, moves=True):
    return tuple(yb.TableLine(i, t, 3, 2, 1, 0, 5, 2, 3, 7, "WWD", "relegation" if i == len(teams) else "",
                              "▲1" if moves else "", "2.33" if moves else "") for i, t in enumerate(teams, start=1))


def week(n):
    return yb.LeaguePage("Premier League", n, f"Matchweek {n} · Sat 8 – Mon 10 Aug",
                         (yb.BookMatch("Sat 8", "Hull City", "Leeds United", "2-0"),
                          yb.BookMatch("Mon 10", "Derby County", "Wrexham", "n/a")),
                         table("Hull City", "Leeds United", "Derby County", "Wrexham"), D(2026, 8, 8 + n),
                         table_note="")


def book(*pages):
    cover = archive.BookCoverage(1, D(2026, 8, 9), D(2026, 8, 9), (), True)
    title = yb.TitlePage("2026/27", ("Built from 1 banked save.", "Season in progress."))
    return yb.Yearbook("2026/27", cover, (title, *pages))


CUP = yb.CupBlock("FA Cup", "Quarter-final", "2nd leg", "Wed 18 Mar",
                  (yb.BookMatch("", "Leeds United", "Hull City", "2-2", "(3-3 agg)", advanced="away"),), D(2026, 3, 18))
PLACES = yb.PlacesPage("Premier League", (1, 2, 3), (yb.PlacesRow("Hull City", (1, 1, 2), "", False, 2),
                                                     yb.PlacesRow("Leeds United", (None, 2, 1), "", False, 1)))
FINAL = yb.FinalTablesPage((("Premier League", table("Hull City", "Leeds United", moves=False)),),
                           splits=(("Premier League", table("Hull City", "Leeds United", moves=False),
                                    table("Hull City", "Leeds United", moves=False),
                                    table("Hull City", "Leeds United", moves=False)),),
                           strips=(("Premier League", ("Most wins: Hull City (3)", "A match with no score is not part of a run.")),))


class PageTests(unittest.TestCase):
    def test_the_title_page_is_its_lines_and_nothing_else(self):
        (page, *_), _ = yr.read_pages(book(week(1)))
        self.assertEqual((page.heading, page.lines, page.columns), ("Football Yearbook 2026/27",
                                                                    ("Built from 1 banked save.", "Season in progress."), ()))

    def test_a_matchweek_reads_its_results_then_its_table(self):
        pages, _ = yr.read_pages(book(week(1)))
        page = pages[1]
        self.assertEqual(page.heading, "Premier League · Matchweek 1 · Sat 8 – Mon 10 Aug")
        self.assertEqual(page.lines, ("Sat 8   Hull City 2-0 Leeds United", "Mon 10   Derby County n/a Wrexham"))
        self.assertEqual(page.rows[0], ("▲1", "1", "Hull City", "3", "2", "1", "0", "5", "2", "+3", "7", "2.33", "WWD"))

    def test_the_sheet_has_exactly_the_columns_the_pdf_prints(self):
        pages, _ = yr.read_pages(book(week(1)))
        lines = week(1).table
        yearbook_pdf._register_fonts()
        pdf_head = [c for c in yearbook_pdf._standings(lines, yearbook_pdf._styles())._cellvalues[0]]
        self.assertEqual(list(pages[1].columns), pdf_head)

    def test_without_movement_or_ppg_those_columns_are_absent_as_in_the_pdf(self):
        plain = yb.LeaguePage("L", 1, "Matchweek 1", (), table("A", "B", moves=False), D(2026, 8, 8))
        pages, _ = yr.read_pages(book(plain))
        self.assertEqual(pages[1].columns, ("#", "Team", "P", "W", "D", "L", "F", "A", "GD", "Pts", "Last six"))

    def test_the_footnotes_travel_with_the_page(self):
        pages, _ = yr.read_pages(book(week(1)))
        self.assertEqual(pages[1].notes, (yearbook_pdf.table_note(week(1).table),))
        cut = yb.LeaguePage("Champions League", 1, "Matchday 1", (), table("A", "B"), D(2026, 9, 1), table_note="Top 16 of 36 shown")
        self.assertTrue(yr.read_pages(book(cut))[0][1].notes[0].startswith("Top 16 of 36 shown. Table calculated"))

    def test_a_cup_day_shows_the_asterisk_the_aggregate_and_the_level_tie_footnote(self):
        page = yr.read_pages(book(CUP))[0][1]
        self.assertEqual(page.heading, "FA Cup, Quarter-final, 2nd leg · Wed 18 Mar")
        self.assertEqual(page.lines, ("Leeds United 2-2 Hull City*   (3-3 agg)",))
        self.assertEqual(page.notes, (yb.LEVEL_TIE_FOOTNOTE,))

    def test_a_cup_day_with_nothing_to_footnote_has_no_notes(self):
        plain = yb.CupBlock("FA Cup", "Round 1", "", "Sat 1 Aug", (yb.BookMatch("", "A", "B", "1-0"),), D(2026, 8, 1))
        self.assertEqual(yr.read_pages(book(plain))[0][1].notes, ())

    def test_a_league_phase_block_carries_its_cut_table(self):
        block = yb.CupBlock("Champions League", "Matchday 1", "", "Wed 16 Sep", (yb.BookMatch("", "A", "B", "1-0"),),
                            D(2026, 9, 16), table("A", "B", moves=False), "Top 16 of 36 shown")
        page = yr.read_pages(book(block))[0][1]
        self.assertEqual(len(page.rows), 2)
        self.assertTrue(page.notes[0].startswith("Top 16 of 36 shown. Table calculated"))

    def test_how_they_stood_is_a_grid_with_blanks_not_zeros(self):
        page = yr.read_pages(book(PLACES))[0][1]
        self.assertEqual(page.heading, "Premier League · How they stood, matchweeks 1–3")
        self.assertEqual(page.columns, ("Team", "1", "2", "3", "Now"))
        self.assertEqual(page.rows, (("Hull City", "1", "1", "2", "2"), ("Leeds United", "", "2", "1", "1")))
        self.assertIn("a blank means the club had not yet played", page.notes[0])

    def test_final_tables_give_the_table_the_strip_and_home_and_away_records(self):
        pages, _ = yr.read_pages(book(FINAL))
        self.assertEqual([p.heading for p in pages[1:]], ["Premier League · final table",
                                                          "Premier League · home record", "Premier League · away record"])
        self.assertEqual(pages[1].lines, ("Most wins: Hull City (3)", "A match with no score is not part of a run."))
        self.assertEqual(pages[2].columns, ("#", "Team", "P", "W", "D", "L", "F", "A", "Pts"))
        self.assertIn("Home and away records are calculated from the results", pages[2].notes[0])

    def test_a_marked_club_is_flagged_in_the_page_so_the_window_can_bold_it(self):
        marked = (yb.TableLine(1, "Hull City", 3, 2, 1, 0, 5, 2, 3, 7, "WWD", marked=True),)
        page = yr.read_pages(book(yb.LeaguePage("L", 1, "Matchweek 1", (), marked, D(2026, 8, 8))))[0][1]
        self.assertEqual(page.marked_rows, (0,))


class ContentsTests(unittest.TestCase):
    def test_the_contents_jump_to_each_competition_once_and_to_the_closing_pages(self):
        pages, contents = yr.read_pages(book(week(1), CUP, week(2), PLACES, FINAL))
        self.assertEqual([label for label, _ in contents],
                         ["Title page", "Premier League", "FA Cup", "Premier League: How they stood", "Final tables"])
        self.assertEqual(pages[dict(contents)["FA Cup"]].competition, "FA Cup")
        self.assertEqual(dict(contents)["Premier League"], 1)
        self.assertEqual(pages[dict(contents)["Final tables"]].heading, "Premier League · final table")

    def test_a_leagues_play_off_rounds_do_not_add_an_entry(self):
        playoff = yb.CupBlock("Premier League play-offs", "Semi-final", "", "Sat 9 May",
                              (yb.BookMatch("", "A", "B", "1-0"),), D(2026, 5, 9))
        _, contents = yr.read_pages(book(week(1), playoff))
        self.assertEqual([label for label, _ in contents], ["Title page", "Premier League"])


if __name__ == "__main__":
    unittest.main()
