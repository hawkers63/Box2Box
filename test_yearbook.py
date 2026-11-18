# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for yearbook: the page model of the season Yearbook, built from the archive.

Run:  .venv\\Scripts\\python -m unittest test_yearbook -v
"""

import dataclasses
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import archive
import fm_data as fd
import yearbook
from fmsave import CodedValue, CompetitionRound
from test_fm_data import D, fx, info


def banked(fixtures, *, nations=None, competitions=None, game=D(2026, 12, 31), path=None):
    """Bank one save of `fixtures` into a temporary archive and return (archive, folder)."""
    folder = tempfile.TemporaryDirectory()
    base = dataclasses.replace(info(), file_name="a.fm", path="a.fm", game_date=game)
    nations = nations or {i: 5 for i in range(1, 6)}
    clubs = [NS(uid=i, reputation=1, teams=(), nation_id=n) for i, n in nations.items()]
    comps = competitions or [NS(id=101, database_id=12)]
    data = fd.build_dataset(base, fixtures, clubs=clubs, competitions=comps)
    book = archive.Archive.open(Path(folder.name) / "archive.sqlite")
    book.bank(data)
    return book, folder


class LeaguePageTests(unittest.TestCase):
    NAMES = {12: "Premier League"}

    def make(self, fixtures, names=None, **kw):
        book, folder = banked(fixtures, **kw)
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        return yearbook.build_yearbook(book, 2026, self.NAMES if names is None else names)

    def league_pages(self, book):
        return [p for p in book.pages if isinstance(p, yearbook.LeaguePage)]

    def test_a_league_round_is_one_page_with_a_dated_heading_and_lines(self):
        book = self.make([fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 8), 3, 4, 1, 1, md=1),
                          fx(D(2026, 8, 10), 5, 1, 0, 3, md=1)])
        (page,) = self.league_pages(book)
        self.assertEqual((page.competition, page.matchweek, page.heading),
                         ("Premier League", 1, "Matchweek 1 · Sat 8 – Mon 10 Aug"))
        self.assertEqual([(m.date_text, m.home, m.score, m.away) for m in page.matches],
                         [("Sat 8", "Hull City", "2-0", "Leeds United"),
                          ("Sat 8", "Sheffield United", "1-1", "Derby County"),
                          ("Mon 10", "Wrexham", "0-3", "Hull City")])
        self.assertEqual(page.table[0].team, "Hull City")
        self.assertEqual(page.table[0].points, 6)

    def test_a_played_match_with_no_recoverable_score_reads_n_a(self):
        book = self.make([fx(D(2026, 8, 8), 1, 2, None, None, played=True, md=1)])
        (page,) = self.league_pages(book)
        self.assertEqual(page.matches[0].score, "n/a")

    def test_matches_still_to_play_are_not_results_and_are_left_out(self):
        book = self.make([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 15), 1, 3, md=2)])
        self.assertEqual([p.matchweek for p in self.league_pages(book)], [1])

    def test_a_rescheduled_match_prints_on_the_day_it_is_played_and_the_table_leaves_it_out(self):
        book = self.make([fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 8), 3, 4, 1, 1, md=1),
                          fx(D(2026, 8, 19), 4, 5, 2, 1, md=1),                     # moved: round 2 has begun
                          fx(D(2026, 8, 15), 1, 3, 1, 0, md=2), fx(D(2026, 8, 15), 2, 5, 0, 0, md=2)])
        pages = self.league_pages(book)
        first, later, moved = [p for p in pages if p.matchweek == 1 and not p.rescheduled][0], \
            [p for p in pages if p.matchweek == 2][0], [p for p in pages if p.rescheduled][0]
        self.assertEqual(len(first.matches), 2)                                     # the moved match is not here
        self.assertEqual({t.team: t.played for t in first.table}["Wrexham"], 0)    # and the table has not counted it
        self.assertEqual((moved.heading, moved.matches[0].home, moved.table), ("Matchweek 1, rescheduled · Wed 19 Aug",
                                                                              "Derby County", ()))
        self.assertEqual([p.when for p in pages], sorted(p.when for p in pages))     # in the order they happened
        self.assertEqual([p.matchweek for p in pages if not p.rescheduled], [1, 2])

    def test_a_round_that_crosses_a_month_names_both_months(self):
        book = self.make([fx(D(2026, 8, 29), 1, 2, 1, 0, md=1), fx(D(2026, 9, 1), 3, 4, 0, 0, md=1)])
        (page,) = self.league_pages(book)
        self.assertEqual(page.heading, "Matchweek 1 · Sat 29 Aug – Tue 1 Sep")
        self.assertEqual([m.date_text for m in page.matches], ["Sat 29", "Tue 1 Sep"])


class WhichCompetitionsTests(unittest.TestCase):
    COMPS = [NS(id=101, database_id=12), NS(id=102, database_id=14), NS(id=103, database_id=15)]
    FIXTURES = [fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 8), 4, 5, 2, 2, comp=102, md=1),
                fx(D(2026, 8, 8), 2, 3, 0, 1, comp=103, md=1)]
    NATIONS = {1: 5, 2: 5, 3: 5, 4: 7, 5: 7}

    def make(self, names):
        book, folder = banked(self.FIXTURES, nations=self.NATIONS, competitions=self.COMPS)
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        return yearbook.build_yearbook(book, 2026, names), book

    def test_only_named_competitions_of_the_home_nation_get_pages(self):
        # 12 is the Premier League (English clubs), 14 a Spanish league, 15 an English league nobody has named.
        built, _ = self.make({12: "Premier League", 14: "La Liga"})
        self.assertEqual({p.competition for p in built.pages if isinstance(p, yearbook.LeaguePage)}, {"Premier League"})

    def test_the_home_nation_is_the_nation_of_the_competition_named_premier_league(self):
        _, book = self.make({12: "Premier League"})
        self.assertEqual(yearbook.home_nation(book.competitions(), {12: "premier league", 14: "La Liga"}), 5)
        self.assertEqual(yearbook.home_nation(book.competitions(), {14: "La Liga"}), None)

    def test_with_no_premier_league_named_every_named_league_is_included(self):
        built, _ = self.make({14: "La Liga", 15: "Segunda"})
        self.assertEqual({p.competition for p in built.pages if isinstance(p, yearbook.LeaguePage)},
                         {"La Liga", "Segunda"})


QF = CodedValue(CompetitionRound.QUARTER_FINAL, 16)
SF = CodedValue(CompetitionRound.SEMI_FINAL, 17)


class CupBlockTests(unittest.TestCase):
    NAMES = {14: "Europa League"}
    COMPS = [NS(id=102, database_id=14)]

    def make(self, fixtures, names=None, **kw):
        book, folder = banked(fixtures, competitions=self.COMPS, game=D(2026, 3, 20), **kw)
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        return yearbook.build_yearbook(book, 2026, self.NAMES if names is None else names)

    @staticmethod
    def blocks(built):
        return [p for p in built.pages if isinstance(p, yearbook.CupBlock)]

    def tie(self, **kw):
        """Ajax (1) v Anderlecht (2): 2-0, then Anderlecht 2-0 on the second leg."""
        return [fx(D(2026, 3, 4), 1, 2, 2, 0, comp=102, md=1, rnd=QF),
                fx(D(2026, 3, 18), 2, 1, 2, 0, comp=102, md=1, rnd=QF)]

    def test_two_legs_are_two_dated_blocks_with_the_aggregate_on_the_second_leg_only(self):
        first, second = self.blocks(self.make(self.tie()))
        self.assertEqual(first.heading, "Europa League, Quarter-final, 1st leg · Wed 4 Mar")
        self.assertEqual(second.heading, "Europa League, Quarter-final, 2nd leg · Wed 18 Mar")
        self.assertEqual([(m.home, m.score, m.away, m.note) for m in first.matches], [("Hull City", "2-0", "Leeds United", "")])
        self.assertEqual([(m.home, m.score, m.away) for m in second.matches], [("Leeds United", "2-0", "Hull City")])
        self.assertEqual(second.matches[0].note, "(2-2 agg, level)")           # nobody is known to have gone through

    def test_a_level_aggregate_names_who_advanced_only_when_a_later_round_shows_them(self):
        later = [fx(D(2026, 4, 8), 1, 3, 0, 0, comp=102, md=2, rnd=SF)]         # Hull City play on, Leeds do not
        _, second = self.blocks(self.make(self.tie() + later))[:2]
        self.assertEqual((second.matches[0].note, second.matches[0].advanced), ("(2-2 agg)", "away"))   # Hull City are the away side
        self.assertEqual(second.footnote, yearbook.LEVEL_TIE_FOOTNOTE)

    def test_an_unlevel_aggregate_is_just_the_aggregate_from_the_second_legs_home_side(self):
        legs = [fx(D(2026, 3, 4), 4, 3, 3, 0, comp=102, md=1, rnd=QF), fx(D(2026, 3, 18), 3, 4, 1, 3, comp=102, md=1, rnd=QF)]
        _, second = self.blocks(self.make(legs))
        self.assertEqual(second.matches[0].note, "(1-6 agg)")                   # Sheffield 0+1, Derby 3+3

    def test_a_drawn_single_match_names_who_advanced_when_a_later_round_shows_them_and_else_says_level(self):
        drawn = [fx(D(2026, 3, 4), 1, 2, 1, 1, comp=102, md=1, rnd=QF)]
        (block,) = self.blocks(self.make(drawn))
        self.assertEqual((block.matches[0].note, block.matches[0].advanced, block.footnote), ("(level)", "", ""))
        later = drawn + [fx(D(2026, 4, 8), 2, 3, 0, 0, comp=102, md=2, rnd=SF)]
        first = self.blocks(self.make(later, nations={i: 5 for i in range(1, 6)}))[0]
        self.assertEqual((first.matches[0].note, first.matches[0].advanced), ("", "away"))      # Leeds United went through
        self.assertEqual(first.footnote, yearbook.LEVEL_TIE_FOOTNOTE)

    def test_the_book_never_prints_extra_time_or_penalties(self):
        built = self.make(self.tie() + [fx(D(2026, 4, 8), 1, 3, 1, 1, comp=102, md=2, rnd=SF)])
        for block in self.blocks(built):
            for m in block.matches:
                self.assertNotIn("aet", m.note)
                self.assertNotIn("pens", m.note)

    def test_a_group_stage_where_a_pair_meets_in_two_rounds_has_no_tie_notes(self):
        group = CodedValue(CompetitionRound.UNKNOWN, 1)
        games = [fx(D(2026, 3, 4), 1, 2, 1, 1, comp=102, md=1, rnd=group), fx(D(2026, 3, 18), 2, 1, 0, 0, comp=102, md=2, rnd=group)]
        blocks = self.blocks(self.make(games))
        self.assertEqual(len(blocks), 2)
        self.assertEqual({m.note for b in blocks for m in b.matches}, {""})
        self.assertEqual({b.leg for b in blocks}, {""})

    def test_a_block_with_no_level_tie_has_no_footnote(self):
        first, second = self.blocks(self.make(self.tie()))
        self.assertEqual((first.footnote, second.footnote), ("", ""))

    def test_the_footnote_claims_only_what_the_save_supports(self):
        self.assertNotIn("4-3", yearbook.LEVEL_TIE_FOOTNOTE)
        self.assertIn("extra time or on penalties", yearbook.LEVEL_TIE_FOOTNOTE)

    def test_the_rounds_of_a_group_stage_are_named_matchday_1_matchday_2(self):
        group = CodedValue(CompetitionRound.UNKNOWN, 1)
        games = [fx(D(2026, 3, 4), 1, 2, 1, 1, comp=102, md=1, rnd=group), fx(D(2026, 3, 18), 2, 1, 0, 0, comp=102, md=2, rnd=group)]
        self.assertEqual([b.round_name for b in self.blocks(self.make(games))], ["Matchday 1", "Matchday 2"])

    def test_a_league_phase_is_matches_with_no_tie_notes(self):
        group = CodedValue(CompetitionRound.UNKNOWN, 1)
        games = [fx(D(2026, 3, 4), h, a, 1, 1, comp=102, md=1, rnd=group)       # four sides, each playing three times
                 for h, a in ((1, 2), (3, 4), (1, 3), (2, 4), (1, 4), (2, 3))]
        (block,) = self.blocks(self.make(games))
        self.assertEqual({m.note for m in block.matches}, {""})


class WholeBookTests(unittest.TestCase):
    NAMES = {12: "Premier League", 14: "FA Cup"}
    COMPS = [NS(id=101, database_id=12), NS(id=102, database_id=14), NS(id=103, database_id=16)]

    def make(self, fixtures, coverage=None):
        book, folder = banked(fixtures, competitions=self.COMPS, game=D(2026, 8, 20))
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        cover = coverage or book.coverage(2026)
        return yearbook.yearbook_from(book.dataset(), book.competitions(), cover, 2026, self.NAMES)

    SEASON = [fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 8), 3, 4, 0, 0, md=1),
              fx(D(2026, 8, 12), 1, 3, 2, 2, comp=102, md=1, rnd=QF),
              fx(D(2026, 8, 15), 1, 3, 1, 0, md=2), fx(D(2026, 8, 15), 2, 4, 3, 1, md=2)]

    def test_a_cup_day_lands_between_the_two_matchweeks_around_it(self):
        built = self.make(self.SEASON)
        kinds = [(type(p).__name__, getattr(p, "matchweek", None)) for p in built.pages]
        self.assertEqual(kinds, [("TitlePage", None), ("LeaguePage", 1), ("CupBlock", None), ("LeaguePage", 2),
                                 ("FinalTablesPage", None)])

    def test_the_title_page_states_the_saves_the_span_the_gaps_and_whether_the_season_is_in_progress(self):
        cover = archive.BookCoverage(2, D(2026, 9, 1), D(2026, 10, 1), ((D(2026, 9, 1), D(2026, 10, 1)),), True)
        title = self.make(self.SEASON, cover).pages[0]
        text = " ".join(title.coverage_lines)
        self.assertEqual(title.season_label, "2026")
        for part in ("2 banked saves", "1 September 2026", "1 October 2026", "No save was banked between 1 Sep and 1 Oct",
                     "Season complete", "Premier League", "FA Cup"):
            self.assertIn(part, text)

    def test_a_single_save_reads_as_one_date(self):
        cover = archive.BookCoverage(1, D(2026, 9, 1), D(2026, 9, 1), (), False)
        text = " ".join(self.make(self.SEASON, cover).pages[0].coverage_lines)
        self.assertIn("Built from 1 banked save, in-game 1 September 2026.", text)

    def test_the_title_page_says_when_no_competition_is_named_premier_league(self):
        book, folder = banked(self.SEASON, competitions=self.COMPS, game=D(2026, 8, 20))
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        built = yearbook.yearbook_from(book.dataset(), book.competitions(), book.coverage(2026), 2026, {14: "FA Cup"})
        self.assertIn("No competition is named Premier League", " ".join(built.pages[0].coverage_lines))

    def test_a_season_is_in_progress_only_if_a_competition_in_the_book_has_matches_to_play(self):
        extra = [fx(D(2026, 8, 22), 2, 3, comp=103, md=1)]            # an unnamed competition: not in the book
        self.assertIn("Season complete", " ".join(self.make(self.SEASON + extra).pages[0].coverage_lines))

    def test_final_tables_appear_only_when_every_league_match_is_played(self):
        done = self.make(self.SEASON)
        self.assertEqual([t[0] for t in done.pages[-1].tables], ["Premier League"])
        unfinished = self.make(self.SEASON + [fx(D(2026, 8, 22), 1, 4, md=3)])
        self.assertFalse([p for p in unfinished.pages if isinstance(p, yearbook.FinalTablesPage)])
        self.assertIn("Season in progress", " ".join(unfinished.pages[0].coverage_lines))


if __name__ == "__main__":
    unittest.main()
