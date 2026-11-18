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


class ZoneTintTests(unittest.TestCase):
    def test_every_named_zone_has_a_tint_the_black_figures_read_on(self):
        self.assertEqual(set(yearbook_pdf.ZONE_TINT), set(yb.ZONE_NAMES))
        self.assertEqual(len(set(yearbook_pdf.ZONE_TINT.values())), len(yb.ZONE_NAMES))
        for zone, tint in yearbook_pdf.ZONE_TINT.items():
            self.assertGreaterEqual(palette.contrast_ratio(tint, "#000000"), 7.0, zone)

    def test_the_note_under_a_table_names_the_zones_shown_and_says_it_is_calculated(self):
        plain = (yb.TableLine(1, "Hull City", 3, 2, 1, 0, 5, 2, 3, 7, "WWD"),)
        zoned = plain + (yb.TableLine(2, "Leeds United", 3, 0, 1, 2, 2, 5, -3, 1, "LLD", "relegation"),)
        self.assertEqual(yearbook_pdf.table_note(plain), "Table calculated from the results.")
        self.assertEqual(yearbook_pdf.table_note(zoned), "Table calculated from the results. Shaded: Relegation.")


class MarkTests(unittest.TestCase):
    def test_the_side_that_went_through_a_level_tie_gets_an_asterisk_after_its_name(self):
        m = yb.BookMatch("", "Birmingham City", "Cardiff City", "0-0", "", advanced="away")
        self.assertEqual(yearbook_pdf.side_text(m, "home"), "Birmingham City")
        self.assertEqual(yearbook_pdf.side_text(m, "away"), "Cardiff City*")

    def test_names_are_escaped_for_the_pdf_and_no_mark_means_no_asterisk(self):
        m = yb.BookMatch("", "Al-Jazira Sports & Culture Club", "Hull City", "2-1")
        self.assertEqual(yearbook_pdf.side_text(m, "home"), "Al-Jazira Sports &amp; Culture Club")


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

    def test_a_league_phase_block_renders_with_its_cut_table_and_says_it_is_cut(self):
        lines = tuple(yb.TableLine(i, f"Club {i}", 1, 1, 0, 0, 2, 0, 2, 3, "W") for i in range(1, 17))
        block = yb.CupBlock("Champions League", "Matchday 1", "", "Wed 16 Sep",
                            (yb.BookMatch("", "Club 1", "Club 17", "2-0"),), D(2026, 9, 16), lines, "Top 16 of 36 shown")
        parts = yearbook_pdf._block_parts(block, yearbook_pdf._styles())
        self.assertTrue(any("Top 16 of 36 shown" in getattr(p, "text", "") for p in parts))
        self.assertTrue(self.render(book(block)).startswith(b"%PDF-"))

    def test_a_zoned_table_renders(self):
        zoned = yb.LeaguePage("Premier League", 30, "Matchweek 30 · Sat 8 – Mon 10 Aug",
                              (yb.BookMatch("Sat 8", "Hull City", "Leeds United", "2-0"),),
                              (yb.TableLine(1, "Hull City", 3, 2, 1, 0, 5, 2, 3, 7, "WWD", "ucl"),
                               yb.TableLine(2, "Leeds United", 3, 0, 1, 2, 2, 5, -3, 1, "LLD", "relegation")), D(2026, 8, 8))
        self.assertTrue(self.render(book(zoned)).startswith(b"%PDF-"))

    def test_a_block_with_a_marked_side_renders_with_its_footnote(self):
        cup = yb.CupBlock("League Cup", "Round 2", "", "Sat 8 Aug",
                          (yb.BookMatch("", "Birmingham City", "Cardiff City", "0-0", "", advanced="away"),), D(2026, 8, 8))
        self.assertTrue(self.render(book(cup)).startswith(b"%PDF-"))

    @staticmethod
    def full_week(n, clubs=24):
        names = [f"Club {i}" for i in range(clubs)]
        matches = tuple(yb.BookMatch("Sat 8", names[i], names[i + clubs // 2], "1-0") for i in range(clubs // 2))
        return yb.LeaguePage("Championship", n, f"Matchweek {n} · Sat 8 – Mon 10 Aug", matches, table(*names),
                             D(2026, 8, 8 + n))

    def test_a_championship_sized_matchweek_and_a_small_cup_block_share_a_page(self):
        cup = yb.CupBlock("FA Cup", "Fourth round", "", "Tue 4 Aug",
                          tuple(yb.BookMatch("", f"Home {i}", f"Away {i}", "2-1") for i in range(3)), D(2026, 8, 4))
        data = self.render(book(cup, self.full_week(1)))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page" + chr(92).encode() + b"b", data)), 2)    # the title page, then one page

    def test_a_small_block_that_does_fit_with_the_matchweek_stays_before_it_in_date_order(self):
        cup = yb.CupBlock("FA Cup", "Fourth round", "", "Tue 4 Aug", (yb.BookMatch("", "Home", "Away", "2-1"),), D(2026, 8, 4))
        order = yearbook_pdf.order_for_pages([cup, self.full_week(1, clubs=6)])
        self.assertEqual([type(p).__name__ for p in order], ["CupBlock", "LeaguePage"])

    def test_a_block_played_well_before_the_matchweek_keeps_its_place_even_when_they_do_not_fit(self):
        shield = yb.CupBlock("Community Shield", "", "", "Sun 16 Aug",
                             tuple(yb.BookMatch("", f"Home {i}", f"Away {i}", "2-1") for i in range(8)), D(2026, 8, 16))
        week = self.full_week(1)
        week = yb.LeaguePage(week.competition, 1, week.heading, week.matches, week.table, D(2026, 8, 21))
        order = yearbook_pdf.order_for_pages([shield, week])
        self.assertEqual([type(p).__name__ for p in order], ["CupBlock", "LeaguePage"])

    def test_pages_that_do_not_fit_together_are_reordered_matchweek_first(self):
        cup = yb.CupBlock("FA Cup", "Fourth round", "", "Fri 7 Aug",
                          tuple(yb.BookMatch("", f"Home {i}", f"Away {i}", "2-1") for i in range(6)), D(2026, 8, 7))
        order = yearbook_pdf.order_for_pages([cup, self.full_week(1)])
        self.assertEqual([type(p).__name__ for p in order], ["LeaguePage", "CupBlock"])

    def test_a_failure_while_drawing_leaves_no_file_and_no_scrap_behind(self):
        with mock.patch.object(yearbook_pdf, "BookDocTemplate") as doc:
            doc.return_value.build.side_effect = RuntimeError("out of paper")
            with self.assertRaises(RuntimeError):
                yearbook_pdf.render(book(week(1)), self.path)
        self.assertEqual(list(Path(self.folder.name).iterdir()), [])

    def test_a_failure_keeps_an_earlier_book_that_was_already_there(self):
        yearbook_pdf.render(book(week(1)), self.path)
        before = self.path.read_bytes()
        with mock.patch.object(yearbook_pdf, "BookDocTemplate") as doc:
            doc.return_value.build.side_effect = RuntimeError("out of paper")
            with self.assertRaises(RuntimeError):
                yearbook_pdf.render(book(week(1), week(2)), self.path)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()


def _texts(flowables):
    """Every Paragraph's text in a flow, looking inside tables and keep-together groups."""
    from reportlab.platypus import KeepTogether, Paragraph, Table
    found = []
    for item in flowables:
        if isinstance(item, Paragraph):
            found.append(item.text)
        elif isinstance(item, KeepTogether):
            found += _texts(item._content)
        elif isinstance(item, Table):
            for row in item._cellvalues:
                found += [c.text for c in row if isinstance(c, Paragraph)] + [str(c) for c in row if not isinstance(c, Paragraph)]
    return found


def moving(pos, team, movement, ppg, marked=False):
    return yb.TableLine(pos, team, 3, 2, 1, 0, 5, 2, 3, 7, "WWD", "", movement, ppg, marked)


class MovingTableDrawingTests(unittest.TestCase):
    def table(self, *lines):
        return yearbook_pdf._standings(lines, yearbook_pdf._styles())

    def test_movement_and_ppg_columns_appear_only_when_a_line_carries_them(self):
        plain = self.table(yb.TableLine(1, "Hull City", 3, 2, 1, 0, 5, 2, 3, 7, "WWD"))
        moved = self.table(moving(1, "Hull City", "▲2", "2.33"))
        self.assertNotIn("±", plain._cellvalues[0])
        self.assertNotIn("PPG", plain._cellvalues[0])
        self.assertEqual((moved._cellvalues[0][0], "PPG" in moved._cellvalues[0]), ("±", True))

    def test_a_table_with_every_column_still_fits_the_text_area(self):
        table = self.table(moving(1, "Hull City", "▲2", "2.33"))
        self.assertLessEqual(sum(table._colWidths), yearbook_pdf.FRAME_WIDTH)

    def test_a_rise_a_fall_and_no_change_use_the_win_loss_and_muted_inks(self):
        table = self.table(moving(1, "A", "▲2", "1.00"), moving(2, "B", "▼1", "1.00"), moving(3, "C", "•", "1.00"))
        cells = [row[0].text for row in table._cellvalues[1:]]
        self.assertIn(yearbook_pdf.FORM_INK["W"], cells[0])
        self.assertIn(yearbook_pdf.FORM_INK["L"], cells[1])
        self.assertIn(yearbook_pdf.MUTED, cells[2])

    def test_the_marked_club_is_bold_with_a_rule_under_its_row_and_nobody_else(self):
        table = self.table(moving(1, "Hull City", "•", "1.00"), moving(2, "Leeds United", "•", "1.00", marked=True))
        names = [row[2 if False else 2].text for row in table._cellvalues[1:]]
        self.assertNotIn("<b>", names[0])
        self.assertIn("<b>Leeds United</b>", names[1])
        rules = [c for c in table._linecmds if c[0] == "LINEBELOW" and c[3] == 0.6 and c[1][1] == 2]
        self.assertEqual(len(rules), 1)

    def test_the_note_explains_the_movement_column_and_the_star_on_a_ppg(self):
        lines = (moving(1, "Hull City", "▲2", "2.33*"),)
        note = yearbook_pdf.table_note(lines)
        self.assertIn("± is the change in place since the previous table", note)
        self.assertIn("* a match with no score is left out of PPG", note)
        self.assertNotIn("PPG", yearbook_pdf.table_note((moving(1, "Hull City", "▲2", "2.33"),)))

    def test_a_final_page_with_splits_prints_home_and_away_blocks_after_the_overall_table(self):
        overall = (moving(1, "Hull City", "", "2.33"), moving(2, "Leeds United", "", "1.00"))
        final = yb.FinalTablesPage((("Premier League", overall),), splits=(("Premier League", overall, overall, overall),))
        texts = _texts(yearbook_pdf._flow(book(final)))
        self.assertIn("Premier League · home record", texts)
        self.assertIn("Premier League · away record", texts)
        self.assertLess(texts.index("Premier League · final table"), texts.index("Premier League · home record"))
        self.assertIn("Home and away records are calculated from the results, in the order of the overall table.",
                      texts)


def places(weeks=3, clubs=("Hull City", "Leeds United", "Derby County", "Wrexham"), zone="", marked=()):
    rows = tuple(yb.PlacesRow(c, tuple(range(i + 1, i + 1 + weeks)) if False else tuple(i + 1 for _ in range(weeks)), zone,
                              c in marked, i + 1) for i, c in enumerate(clubs))
    return yb.PlacesPage("Premier League", tuple(range(1, weeks + 1)), rows)


class PlacesGridDrawingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "book.pdf"

    def render(self, *pages):
        yearbook_pdf.render(book(*pages), self.path)
        return self.path.read_bytes()

    def test_a_whole_season_fits_one_chunk_and_the_type_never_drops_below_seven_points(self):
        self.assertEqual(yearbook_pdf.places_chunks(38), [(0, 38)])
        self.assertGreaterEqual(yearbook_pdf.PLACES_FONT, 7)

    def test_weeks_that_will_not_fit_split_into_equal_halves_in_order(self):
        narrow = yearbook_pdf.places_chunks(46, width=yearbook_pdf.PLACES_NAME + yearbook_pdf.PLACES_NOW + 30 * yearbook_pdf.PLACES_CELL)
        self.assertEqual(narrow, [(0, 23), (23, 46)])

    def test_no_chunk_ever_has_more_weeks_than_fit_and_none_is_dropped(self):
        for weeks in (10, 38, 46, 90):
            for width in (200, 300, 600):
                chunks = yearbook_pdf.places_chunks(weeks, width=width)
                self.assertEqual(sum(b - a for a, b in chunks), weeks)
                self.assertEqual([a for a, _ in chunks][1:], [b for _, b in chunks][:-1])

    def test_a_championship_sized_grid_fits_the_landscape_text_area_at_the_stated_size(self):
        names = [f"Club {i}" for i in range(24)]
        page = places(weeks=46, clubs=names)
        (table,) = [t for t in yearbook_pdf._places_tables(page, yearbook_pdf._styles())]
        self.assertLessEqual(sum(table._colWidths), yearbook_pdf.LANDSCAPE_FRAME_WIDTH)
        self.assertEqual(len(table._cellvalues), 25)                      # a header and every club: none dropped
        self.assertEqual(len(table._cellvalues[0]), 46 + 2)               # every week, the name and the latest place

    def test_a_blank_week_prints_nothing_not_zero(self):
        page = yb.PlacesPage("L", (1, 2), (yb.PlacesRow("Hull City", (None, 3), "", False, 3),))
        (table,) = yearbook_pdf._places_tables(page, yearbook_pdf._styles())
        self.assertEqual(table._cellvalues[1][1:], ["", "3", "3"])

    def test_the_latest_place_is_shaded_by_its_zone_and_the_marked_club_is_bold(self):
        page = places(zone="relegation", marked=("Wrexham",))
        (table,) = yearbook_pdf._places_tables(page, yearbook_pdf._styles())
        shaded = [c for c in table._bkgrndcmds if c[0] == "BACKGROUND" and c[1][0] == len(page.matchweeks) + 1]
        self.assertEqual(len(shaded), 4)
        self.assertIn("<b>Wrexham</b>", [row[0].text for row in table._cellvalues[1:]])

    def test_the_grid_is_landscape_and_the_pages_around_it_stay_portrait(self):
        week_ = week(1)
        final = yb.FinalTablesPage((("Premier League", table("Hull City", "Leeds United")),))
        data = self.render(week_, places(), final)
        sizes = re.findall(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", data)
        widths = [float(w) for w, _ in sizes]
        self.assertEqual([w > 800 for w in widths], [False, False, True, False])        # title, week, grid, final

    def test_a_grid_that_ends_the_book_leaves_no_blank_page_after_it(self):
        data = self.render(places())
        self.assertEqual(len(re.findall(rb"/Type\s*/Page\b", data)), 2)

    def test_the_grid_and_its_headings_say_what_they_are(self):
        texts = _texts(yearbook_pdf._flow(book(places(weeks=3))))
        self.assertIn("Premier League · How they stood, matchweeks 1–3", texts)
        self.assertTrue(any("a blank means the club had not yet played" in t for t in texts))


class ResultsStripDrawingTests(unittest.TestCase):
    def test_the_strip_sits_under_the_final_table_with_its_own_heading(self):
        lines = ("Most wins: Hull City (3)", "A match with no score is not part of a run.")
        final = yb.FinalTablesPage((("Premier League", table("Hull City", "Leeds United")),),
                                   strips=(("Premier League", lines),))
        texts = _texts(yearbook_pdf._flow(book(final)))
        self.assertLess(texts.index("Premier League · final table"), texts.index("Premier League · from the results"))
        for line in lines:
            self.assertIn(line, texts)


def outline_of(*pages):
    flow = yearbook_pdf._flow(book(*pages))
    return [f._outline for f in flow if getattr(f, "_outline", None)]


class OutlineTests(unittest.TestCase):
    CUP = yb.CupBlock("FA Cup", "Quarter-final", "", "Wed 18 Mar", (yb.BookMatch("", "Leeds United", "Hull City", "2-0"),),
                      D(2026, 3, 18))
    FINAL = yb.FinalTablesPage((("Premier League", table("Hull City", "Leeds United")),))

    def test_the_season_then_each_competition_once_then_the_closing_sections(self):
        self.assertEqual(outline_of(week(1), self.CUP, week(2), places(), self.FINAL),
                         [(0, "Football Yearbook 2026/27"), (1, "Premier League"), (1, "FA Cup"),
                          (1, "Premier League: How they stood"), (1, "Final tables")])

    def test_a_leagues_play_off_rounds_belong_to_the_league_not_a_new_entry(self):
        playoffs = yb.CupBlock("Premier League play-offs", "Semi-final", "", "Sat 9 May", (yb.BookMatch("", "Leeds United", "Hull City", "1-0"),), D(2026, 5, 9))
        self.assertEqual([t for _, t in outline_of(week(1), playoffs)], ["Football Yearbook 2026/27", "Premier League"])

    def test_every_matchweek_is_not_bookmarked(self):
        self.assertEqual(len(outline_of(*[week(n) for n in range(1, 9)])), 2)       # the season and the one league

    def test_the_rendered_pdf_carries_the_outline_in_order(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "b.pdf"
            yearbook_pdf.render(book(week(1), self.CUP, self.FINAL), path)
            data = path.read_bytes()
        self.assertIn(b"/Outlines", data)
        titles = [t.decode("latin-1") for t in re.findall(rb"/Title \((.*?)\)", data)]
        self.assertEqual(titles[1:], ["Football Yearbook 2026/27", "Premier League", "FA Cup", "Final tables"])   # [0] is the file's own title

    def test_a_competition_bookmark_lands_on_its_first_page(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "b.pdf"
            yearbook_pdf.render(book(week(1), self.FINAL), path)
            data = path.read_bytes()
        self.assertEqual(len(re.findall(rb"/Dest\s*\[", data)), 3)                    # season, league, final tables
