# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for yearbook_read: the Yearbook's page model as pages to read in the window. No window here.

Run:  .venv\\Scripts\\python -m unittest test_yearbook_read -v
"""

import dataclasses
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


class PageKeyTests(unittest.TestCase):
    """Each page's key names what it shows by archive identity: never its place in the book, a score or a club."""

    def keys(self, *pages):
        return [p.page_key for p in yr.read_pages(book(*pages))[0]]

    def test_each_kind_of_page_has_a_key_from_its_competition_key(self):
        league = dataclasses.replace(week(3), competition_key=12)
        late = dataclasses.replace(week(3), competition_key=12, rescheduled=True, when=D(2026, 9, 2))
        cup = dataclasses.replace(CUP, competition_key=14)
        places = dataclasses.replace(PLACES, competition_key=12)
        final = dataclasses.replace(FINAL, keys=(("Premier League", 12),))
        self.assertEqual(self.keys(league, late, cup, places, final),
                         ["title", "league/12/3", "league/12/3/rescheduled/2026-09-02",
                          "cup/14/2026-03-18/Quarter-final/2nd leg", "places/12", "final/12", "home/12", "away/12"])

    def test_a_renamed_competition_keeps_its_keys(self):
        league = dataclasses.replace(week(1), competition_key=12)
        renamed = dataclasses.replace(league, competition="English Premier Division")
        self.assertEqual(self.keys(league), self.keys(renamed))

    def test_the_key_does_not_move_when_pages_are_added_before_it(self):
        target = dataclasses.replace(week(2), competition_key=12)
        alone = self.keys(target)[1]
        later = self.keys(dataclasses.replace(week(1), competition_key=12), target)[2]
        self.assertEqual(alone, later)

    def test_keys_are_unique_across_a_book(self):
        pages = (dataclasses.replace(week(1), competition_key=12), dataclasses.replace(CUP, competition_key=14),
                 dataclasses.replace(week(2), competition_key=12), dataclasses.replace(PLACES, competition_key=12),
                 dataclasses.replace(FINAL, keys=(("Premier League", 12),)))
        keys = self.keys(*pages)
        self.assertEqual(len(keys), len(set(keys)))


COVER = archive.BookCoverage(1, D(2026, 8, 9), D(2026, 8, 9), (), True)


class VolumeTests(unittest.TestCase):
    def test_a_volume_holds_the_book_its_pages_and_the_coverage_it_was_built_from(self):
        built = book(week(1), CUP)
        volume = yr.volume(built, 2026, "archive-1", COVER)
        self.assertEqual((volume.season, volume.archive_id, volume.coverage, volume.book), (2026, "archive-1", COVER, built))
        self.assertEqual([list(volume.pages), list(volume.contents)], list(yr.read_pages(built)))
        self.assertEqual(volume.season_label, "2026/27")

    def test_the_edition_is_named_from_the_coverages_last_date(self):
        self.assertEqual((yr.volume(book(), 2026, "a", COVER).edition, yr.volume(book(), 2026, "a", COVER).edition_label),
                         ("2026-08-09", "9 Aug 2026"))
        unknown = archive.BookCoverage(0, None, None, (), False)
        self.assertEqual((yr.volume(book(), 2026, "a", unknown).edition, yr.volume(book(), 2026, "a", unknown).edition_label),
                         ("unknown", "date unknown"))


    def test_a_volume_matches_the_same_coverage_whatever_the_book_says_about_progress(self):
        volume = yr.volume(book(), 2026, "a", COVER)
        self.assertTrue(volume.matches(archive.BookCoverage(1, D(2026, 8, 9), D(2026, 8, 9), (), False)))
        self.assertFalse(volume.matches(archive.BookCoverage(2, D(2026, 8, 9), D(2026, 9, 21), (), True)))


class SpreadTests(unittest.TestCase):
    def test_the_title_page_stands_alone_and_the_rest_pair_up(self):
        self.assertEqual(yr.spreads(0), [])
        self.assertEqual(yr.spreads(1), [(0,)])
        self.assertEqual(yr.spreads(2), [(0,), (1,)])
        self.assertEqual(yr.spreads(5), [(0,), (1, 2), (3, 4)])

    def test_an_odd_last_page_stands_alone(self):
        self.assertEqual(yr.spreads(4), [(0,), (1, 2), (3,)])

    def test_any_page_finds_its_spread(self):
        self.assertEqual([yr.spread_at(i, 5) for i in range(5)], [(0,), (1, 2), (1, 2), (3, 4), (3, 4)])
        self.assertEqual(yr.spread_at(9, 4), (3,))          # past the end: the last spread
        self.assertEqual(yr.spread_at(-1, 4), (0,))

    def test_the_label_says_reader_spread_never_a_printed_page_pair(self):
        self.assertEqual(yr.spread_label((0,), 5), "Page 1 of 5")
        self.assertEqual(yr.spread_label((1, 2), 5), "Pages 2–3 of 5 · reader spread")


class StripTests(unittest.TestCase):
    def test_the_strip_shows_a_bounded_window_around_the_current_chapter(self):
        self.assertEqual(yr.strip_window(3, 0, 7), (0, 3))
        self.assertEqual(yr.strip_window(20, 0, 7), (0, 7))
        self.assertEqual(yr.strip_window(20, 10, 7), (7, 14))
        self.assertEqual(yr.strip_window(20, 19, 7), (13, 20))

    def test_a_long_chapter_name_is_shortened_with_an_ellipsis(self):
        self.assertEqual(yr.strip_text("FA Cup"), "FA Cup")
        long = "The Extraordinarily Long Regional Premier Division North"
        self.assertEqual(len(yr.strip_text(long)), yr.STRIP_CHARS)
        self.assertTrue(yr.strip_text(long).endswith("…"))


class BookmarkTests(unittest.TestCase):
    def test_a_bookmark_round_trips_through_the_settings_value(self):
        stored = yr.with_bookmark(None, "archive-1", 2026, "2026-08-09", "league/12/3")
        self.assertEqual(yr.read_bookmark(stored, "archive-1", 2026), "league/12/3")
        self.assertEqual(stored, {"archive-1|2026": {"edition": "2026-08-09", "page_key": "league/12/3"}})

    def test_another_playthrough_or_season_has_no_bookmark(self):
        stored = yr.with_bookmark({}, "archive-1", 2026, "2026-08-09", "league/12/3")
        self.assertIsNone(yr.read_bookmark(stored, "archive-2", 2026))
        self.assertIsNone(yr.read_bookmark(stored, "archive-1", 2025))

    def test_a_badly_shaped_value_reads_as_no_bookmark(self):
        for value in (None, [], "x", 3, {"archive-1|2026": "league/12/3"}, {"archive-1|2026": {"page_key": 7}},
                      {"archive-1|2026": {"page_key": ""}}, {"archive-1|2026": {"page_key": "x" * 500}},
                      {"archive-1|2026": {"edition": [], "page_key": "title"}}):
            self.assertIsNone(yr.read_bookmark(value, "archive-1", 2026), value)

    def test_writing_drops_badly_shaped_entries_and_keeps_good_ones(self):
        value = {"bad": 3, "archive-1|2025": {"edition": "2025-05-01", "page_key": "title"}, 4: {"page_key": "x"}}
        stored = yr.with_bookmark(value, "archive-1", 2026, "2026-08-09", "cup/14/2026-03-18/Final/")
        self.assertEqual(set(stored), {"archive-1|2025", "archive-1|2026"})
        self.assertEqual(value["bad"], 3)                            # the value read from the settings is untouched

    def test_writing_a_badly_shaped_value_starts_afresh(self):
        self.assertEqual(set(yr.with_bookmark(["junk"], "a", 2026, "e", "title")), {"a|2026"})

    def test_the_number_of_bookmarks_is_bounded_and_the_newest_are_kept(self):
        stored = None
        for season in range(1900, 1900 + yr.BOOKMARK_LIMIT + 10):
            stored = yr.with_bookmark(stored, "a", season, "e", "title")
        self.assertEqual(len(stored), yr.BOOKMARK_LIMIT)
        self.assertIn(f"a|{1900 + yr.BOOKMARK_LIMIT + 9}", stored)
        self.assertNotIn("a|1900", stored)

    def test_a_page_key_finds_its_page_or_nothing(self):
        pages = yr.read_pages(book(dataclasses.replace(week(1), competition_key=12)))[0]
        self.assertEqual(yr.page_index(pages, "league/12/1"), 1)
        self.assertIsNone(yr.page_index(pages, "league/12/9"))
        self.assertIsNone(yr.page_index(pages, None))

    def test_the_reader_mode_is_single_unless_spread_was_chosen(self):
        self.assertEqual([yr.reader_mode(v) for v in ("spread", "single", None, 3, "SPREAD")],
                         ["spread", "single", "single", "single", "single"])


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


TRAJECTORY = yb.TrajectoryPage("Leeds United", (yb.Trajectory(
    "Premier League", 4, (yb.TrajectoryPoint(1, D(2026, 8, 8), 3), yb.TrajectoryPoint(2, D(2026, 8, 15), None),
                          yb.TrajectoryPoint(3, D(2026, 8, 22), 1))),))
NO_CHART = yb.TrajectoryPage("Wigan Rovers", (), yb.NO_TRAJECTORY_NOTE.format(club="Wigan Rovers"))


class TrajectoryReadTests(unittest.TestCase):
    def test_each_chart_is_a_page_that_carries_the_chart_and_the_shared_note(self):
        pages, contents = yr.read_pages(book(TRAJECTORY))
        page = pages[1]
        self.assertEqual((page.kind, page.heading, page.chart is TRAJECTORY.charts[0], page.notes),
                         ("trajectory", "Leeds United · Season trajectory · Premier League", True, (yb.TRAJECTORY_NOTE,)))
        self.assertEqual(page.page_key, "trajectory/0")
        self.assertIn(("Leeds United: Season trajectory", 1), contents)

    def test_the_lines_list_the_same_places_the_chart_plots_and_a_blank_stays_blank(self):
        (_, page), _ = yr.read_pages(book(TRAJECTORY))
        self.assertEqual(page.columns, ("Matchweek", "To", "Place"))
        self.assertEqual(page.rows, (("1", "Sat 8 Aug", "3"), ("2", "Sat 15 Aug", ""), ("3", "Sat 22 Aug", "1")))

    def test_a_club_with_no_chart_has_a_note_page_and_no_chart(self):
        (_, page), _ = yr.read_pages(book(NO_CHART))
        self.assertEqual((page.kind, page.chart, page.lines), ("trajectory", None, (NO_CHART.note,)))


HONOURS = yb.honours_page([
    yb.HonoursEntry("Premier League", ("Calculated leader: Hull City, 9 points from 3 matches [1]",), (yb.DEDUCTIONS_NOTE,)),
    yb.HonoursEntry("FA Cup", ("Winner: unresolved. Hull City 1-1 Leeds United in the final [1]",), (yb.CUP_LEVEL_NOTE,))])


class HonoursReadTests(unittest.TestCase):
    def test_the_page_reads_every_entry_and_the_same_numbered_footnotes_the_pdf_prints(self):
        pages, contents = yr.read_pages(book(HONOURS))
        page = pages[1]
        self.assertEqual((page.kind, page.heading, page.page_key), ("honours", "Honours", "honours"))
        self.assertEqual(page.lines, ("Premier League: Calculated leader: Hull City, 9 points from 3 matches [1]",
                                      "FA Cup: Winner: unresolved. Hull City 1-1 Leeds United in the final [2]"))
        self.assertEqual(page.notes, HONOURS.notes)
        self.assertIn(("Honours", 1), contents)


RETRO = yb.RetrospectivePage("Leeds United", ("Premier League: 4th on the calculated table after 3 matches (0 won, 1 drawn, 2 lost; 0 scored, 5 conceded; 1 point)",
                                              "FA Cup: the Final against Hull City is unresolved [1]"),
                             (yb.RETRO_NOTE, f"[1] {yb.RETRO_UNRESOLVED_NOTE}"))


class RetrospectiveReadTests(unittest.TestCase):
    def test_the_page_reads_the_lines_and_notes_the_pdf_prints(self):
        pages, contents = yr.read_pages(book(RETRO))
        page = pages[1]
        self.assertEqual((page.kind, page.heading, page.lines, page.notes, page.page_key),
                         ("retrospective", "Leeds United · Season retrospective", RETRO.lines, RETRO.notes, "retrospective"))
        self.assertIn(("Leeds United: Season retrospective", 1), contents)
