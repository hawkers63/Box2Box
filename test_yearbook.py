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
from unittest import mock

import archive
import fm_data as fd
import yearbook
from fmsave import CodedValue, CompetitionRound
from test_fm_data import D, fx, info


def banked(fixtures, *, nations=None, competitions=None, game=D(2026, 12, 31), path=None, rules=()):
    """Bank one save of `fixtures` into a temporary archive and return (archive, folder)."""
    folder = tempfile.TemporaryDirectory()
    base = dataclasses.replace(info(), file_name="a.fm", path="a.fm", game_date=game)
    nations = nations or {i: 5 for i in range(1, 6)}
    clubs = [NS(uid=i, reputation=1, teams=(), nation_id=n) for i, n in nations.items()]
    comps = competitions or [NS(id=101, database_id=12)]
    data = fd.build_dataset(base, fixtures, clubs=clubs, competitions=comps, rules=list(rules))
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

    @staticmethod
    def long_named(home_name, home_short, **kw):
        base = fx(D(2026, 8, 8), 1, 2, 2, 0, md=1, **kw)
        return dataclasses.replace(base, home_club_name=home_name, home_club_short_name=home_short)

    def test_a_long_club_name_is_replaced_by_the_games_short_name_in_the_results_and_the_table(self):
        book = self.make([self.long_named("Al-Jazira Sports & Culture Club", "Al-Jazira SCC"), fx(D(2026, 8, 9), 3, 4, 0, 0, md=1)])
        (page,) = self.league_pages(book)
        self.assertEqual(page.matches[0].home, "Al-Jazira SCC")
        self.assertIn("Al-Jazira SCC", [t.team for t in page.table])

    def test_a_name_that_is_not_long_is_kept_even_when_the_game_has_a_shorter_one(self):
        book = self.make([self.long_named("Sheffield United", "Sheff Utd"), fx(D(2026, 8, 9), 4, 5, 0, 0, md=1)])
        (page,) = self.league_pages(book)
        self.assertEqual(page.matches[0].home, "Sheffield United")

    def test_a_long_name_stays_when_the_short_name_is_no_shorter(self):
        book = self.make([self.long_named("Al-Jazira Sports & Culture Club", "Al-Jazira Sports & Culture Club"), fx(D(2026, 8, 9), 3, 4, 0, 0, md=1)])
        (page,) = self.league_pages(book)
        self.assertEqual(page.matches[0].home, "Al-Jazira Sports & Culture Club")

    def test_a_played_match_with_no_recoverable_score_reads_n_a(self):
        book = self.make([fx(D(2026, 8, 8), 1, 2, None, None, played=True, md=1), fx(D(2026, 8, 9), 3, 4, 0, 0, md=1)])
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
    FIXTURES = [fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 15), 2, 1, 0, 0, md=2),
                fx(D(2026, 8, 8), 4, 5, 2, 2, comp=102, md=1), fx(D(2026, 8, 15), 5, 4, 1, 3, comp=102, md=2),
                fx(D(2026, 8, 8), 2, 3, 0, 1, comp=103, md=1), fx(D(2026, 8, 15), 3, 2, 1, 1, comp=103, md=2)]
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

    def test_two_legs_stored_in_consecutive_rounds_are_still_one_tie_with_its_aggregate(self):
        legs = [fx(D(2026, 3, 4), 1, 2, 2, 0, comp=102, md=1, rnd=QF), fx(D(2026, 3, 4), 3, 4, 1, 1, comp=102, md=1, rnd=QF),
                fx(D(2026, 3, 18), 2, 1, 2, 0, comp=102, md=2, rnd=QF), fx(D(2026, 3, 18), 4, 3, 0, 2, comp=102, md=2, rnd=QF),
                fx(D(2026, 4, 8), 1, 3, 0, 0, comp=102, md=3, rnd=SF)]
        blocks = self.blocks(self.make(legs))
        self.assertEqual([(b.round_name, b.leg) for b in blocks[:2]], [("Quarter-final", "1st leg"), ("Quarter-final", "2nd leg")])
        notes = {(m.home, m.away): (m.note, m.advanced) for m in blocks[1].matches}
        self.assertEqual(notes[("Leeds United", "Hull City")], ("(2-2 agg)", "away"))       # level, Hull City went through
        self.assertEqual(notes[("Derby County", "Sheffield United")], ("(1-3 agg)", ""))    # unlevel: just the aggregate

    def test_qualifying_rounds_that_all_use_round_index_zero_are_separate_rounds_by_date(self):
        q = CodedValue(CompetitionRound.UNKNOWN, 3)
        games = [fx(D(2026, 7, 8), 1, 2, 2, 0, comp=102, md=1, rnd=q), fx(D(2026, 7, 15), 2, 1, 1, 0, comp=102, md=1, rnd=q),
                 fx(D(2026, 8, 5), 3, 4, 1, 0, comp=102, md=1, rnd=q), fx(D(2026, 8, 12), 4, 3, 0, 0, comp=102, md=1, rnd=q)]
        blocks = self.blocks(self.make(games))
        self.assertEqual([(b.round_name, b.leg) for b in blocks],
                         [("Round 1", "1st leg"), ("Round 1", "2nd leg"), ("Round 2", "1st leg"), ("Round 2", "2nd leg")])
        self.assertEqual(blocks[1].matches[0].note, "(1-2 agg)")          # the second leg's home side (club 2) first

    def test_weekly_qualifying_rounds_on_one_round_index_stay_separate_ties_not_one_big_round(self):
        q = CodedValue(CompetitionRound.UNKNOWN, 3)
        games = [fx(D(2026, 8, 5), 1, 2, 1, 0, comp=102, md=1, rnd=q), fx(D(2026, 8, 12), 2, 1, 1, 1, comp=102, md=1, rnd=q),
                 fx(D(2026, 8, 19), 1, 3, 2, 0, comp=102, md=1, rnd=q), fx(D(2026, 8, 26), 3, 1, 0, 0, comp=102, md=1, rnd=q)]
        blocks = self.blocks(self.make(games))
        self.assertEqual([(b.round_name, b.leg) for b in blocks],
                         [("Round 1", "1st leg"), ("Round 1", "2nd leg"), ("Round 2", "1st leg"), ("Round 2", "2nd leg")])

    def test_parallel_qualifying_paths_on_the_same_dates_are_never_mistaken_for_a_league_phase(self):
        q = CodedValue(CompetitionRound.UNKNOWN, 3)
        games = [fx(D(2026, 8, 5), 1, 2, 1, 0, comp=102, md=1, rnd=q), fx(D(2026, 8, 5), 3, 4, 2, 2, comp=102, md=1, rnd=q),
                 fx(D(2026, 8, 12), 2, 1, 1, 1, comp=102, md=1, rnd=q), fx(D(2026, 8, 12), 4, 3, 0, 1, comp=102, md=1, rnd=q),
                 fx(D(2026, 8, 5), 1, 3, 0, 0, comp=102, md=3, rnd=q), fx(D(2026, 8, 5), 2, 4, 1, 1, comp=102, md=3, rnd=q),
                 fx(D(2026, 8, 12), 3, 1, 2, 1, comp=102, md=3, rnd=q), fx(D(2026, 8, 12), 4, 2, 0, 0, comp=102, md=3, rnd=q),
                 fx(D(2026, 8, 5), 1, 4, 1, 0, comp=102, md=2, rnd=q), fx(D(2026, 8, 12), 4, 1, 2, 2, comp=102, md=2, rnd=q)]
        names = [b.round_name for b in self.blocks(self.make(games))]
        self.assertFalse([n for n in names if n.startswith("Matchday")], names)

    def test_two_legs_weeks_apart_stay_one_tie(self):
        legs = [fx(D(2027, 1, 5), 1, 2, 2, 0, comp=102, md=1, rnd=SF), fx(D(2027, 2, 2), 2, 1, 1, 0, comp=102, md=1, rnd=SF)]
        blocks = self.blocks(self.make(legs))
        self.assertEqual([(b.round_name, b.leg) for b in blocks], [("Semi-final", "1st leg"), ("Semi-final", "2nd leg")])
        self.assertEqual(blocks[1].matches[0].note, "(1-2 agg)")

    def test_a_league_phase_where_no_pair_meets_twice_is_still_matchdays_not_ties(self):
        group = CodedValue(CompetitionRound.UNKNOWN, 1)
        games = [fx(D(2026, 3, 4), 1, 2, 1, 1, comp=102, md=1, rnd=group), fx(D(2026, 3, 4), 3, 4, 0, 0, comp=102, md=1, rnd=group),
                 fx(D(2026, 3, 18), 1, 3, 2, 2, comp=102, md=2, rnd=group), fx(D(2026, 3, 18), 2, 4, 1, 1, comp=102, md=2, rnd=group),
                 fx(D(2026, 4, 1), 1, 4, 0, 0, comp=102, md=3, rnd=group), fx(D(2026, 4, 1), 2, 3, 3, 3, comp=102, md=3, rnd=group)]
        blocks = self.blocks(self.make(games))
        self.assertEqual([b.round_name for b in blocks], ["Matchday 1", "Matchday 2", "Matchday 3"])
        self.assertEqual({m.note for b in blocks for m in b.matches}, {""})

    def test_knockout_rounds_that_halve_the_field_are_still_ties(self):
        games = [fx(D(2026, 3, 4), 1, 2, 1, 1, comp=102, md=1, rnd=QF), fx(D(2026, 3, 4), 3, 4, 2, 0, comp=102, md=1, rnd=QF),
                 fx(D(2026, 4, 8), 1, 3, 0, 0, comp=102, md=2, rnd=SF)]
        first = self.blocks(self.make(games))[0]
        self.assertEqual(first.round_name, "Quarter-final")

    GROUP = CodedValue(CompetitionRound.UNKNOWN, 1)

    def swiss(self):
        """Four clubs, three matchdays, no pair twice; matchday 1 is split over two days."""
        g = self.GROUP
        return [fx(D(2026, 3, 4), 1, 2, 3, 0, comp=102, md=1, rnd=g), fx(D(2026, 3, 5), 3, 4, 0, 0, comp=102, md=1, rnd=g),
                fx(D(2026, 3, 18), 1, 3, 2, 2, comp=102, md=2, rnd=g), fx(D(2026, 3, 18), 2, 4, 1, 0, comp=102, md=2, rnd=g),
                fx(D(2026, 4, 1), 1, 4, 0, 0, comp=102, md=3, rnd=g), fx(D(2026, 4, 1), 2, 3, 3, 3, comp=102, md=3, rnd=g)]

    def test_a_league_phase_gets_a_table_after_the_last_day_of_each_matchday_cut_to_the_top_places(self):
        with mock.patch.object(yearbook, "LEAGUE_PHASE_SHOWN", 2):
            blocks = self.blocks(self.make(self.swiss()))
        self.assertEqual([bool(b.table) for b in blocks], [False, True, True, True])       # not after 4 March, after 5 March
        after_one = blocks[1]
        self.assertEqual([(t.pos, t.team, t.points) for t in after_one.table], [(1, "Hull City", 3), (2, "Derby County", 1)])
        self.assertEqual(len(after_one.table), 2)
        self.assertEqual(after_one.table_note, "Top 2 of 4 shown")

    def test_a_small_league_phase_shows_every_club_and_makes_no_cut_note(self):
        blocks = self.blocks(self.make(self.swiss()))
        self.assertEqual((len(blocks[-1].table), blocks[-1].table_note), (4, ""))

    def test_knockout_blocks_and_separate_groups_have_no_table(self):
        self.assertEqual({bool(b.table) for b in self.blocks(self.make(self.tie()))}, {False})
        g = self.GROUP
        groups = [fx(D(2026, 3, 4), 1, 2, 1, 0, comp=102, md=1, rnd=g), fx(D(2026, 3, 4), 3, 4, 0, 0, comp=102, md=1, rnd=g),
                  fx(D(2026, 3, 18), 2, 1, 2, 2, comp=102, md=2, rnd=g), fx(D(2026, 3, 18), 4, 3, 1, 1, comp=102, md=2, rnd=g)]
        self.assertEqual({bool(b.table) for b in self.blocks(self.make(groups))}, {False})

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


class SingleMatchAndPlayOffTests(unittest.TestCase):
    def make(self, fixtures, names, competitions):
        book, folder = banked(fixtures, competitions=competitions, game=D(2027, 6, 1))
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        return yearbook.build_yearbook(book, 2026, names)

    def test_a_one_match_competition_is_a_single_dated_block_not_a_matchweek_with_a_two_club_table(self):
        shield = [fx(D(2026, 8, 16), 1, 2, 2, 1, comp=101, md=1)]
        built = self.make(shield, {12: "Community Shield"}, [NS(id=101, database_id=12)])
        self.assertFalse([p for p in built.pages if isinstance(p, yearbook.LeaguePage)])
        (block,) = [p for p in built.pages if isinstance(p, yearbook.CupBlock)]
        self.assertEqual(block.heading, "Community Shield · Sun 16 Aug")
        self.assertEqual([(m.home, m.score, m.away) for m in block.matches], [("Hull City", "2-1", "Leeds United")])

    def test_cup_rounds_inside_a_league_are_its_play_offs(self):
        league = [fx(D(2026, 8, 8), 1, 2, 1, 0, comp=101, md=1), fx(D(2026, 8, 8), 3, 4, 0, 0, comp=101, md=1)]
        playoff = [fx(D(2027, 5, 16), 1, 3, 2, 1, comp=101, md=2, rnd=SF)]
        built = self.make(league + playoff, {12: "Championship"}, [NS(id=101, database_id=12)])
        (block,) = [p for p in built.pages if isinstance(p, yearbook.CupBlock)]
        self.assertTrue(block.heading.startswith("Championship play-offs, Semi-final"), block.heading)


class ContinentalTests(unittest.TestCase):
    """A continental competition (clubs from several nations) whose league phase is stored as matchdays."""
    NATIONS = {1: 5, 2: 6, 3: 7, 4: 8, 5: 9}
    NAMES = {14: "UEFA Champions League"}
    COMPS = [NS(id=102, database_id=14)]

    def make(self, fixtures):
        book, folder = banked(fixtures, nations=self.NATIONS, competitions=self.COMPS, game=D(2027, 6, 1))
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        return yearbook.build_yearbook(book, 2026, self.NAMES)

    LEAGUE = [fx(D(2026, 9, 15), 1, 2, 3, 0, comp=102, md=1), fx(D(2026, 9, 15), 3, 4, 0, 0, comp=102, md=1),
              fx(D(2026, 9, 29), 1, 3, 2, 2, comp=102, md=2), fx(D(2026, 9, 29), 2, 4, 1, 0, comp=102, md=2)]

    def test_a_league_phase_reads_matchday_and_its_table_is_cut_to_the_top_places(self):
        with mock.patch.object(yearbook, "LEAGUE_PHASE_SHOWN", 2):
            built = self.make(self.LEAGUE)
        pages = [p for p in built.pages if isinstance(p, yearbook.LeaguePage)]
        self.assertEqual([p.heading for p in pages], ["Matchday 1 · Tue 15 Sep", "Matchday 2 · Tue 29 Sep"])
        self.assertEqual([len(p.table) for p in pages], [2, 2])
        self.assertEqual(pages[0].table_note, "Top 2 of 4 shown")

    def test_a_small_league_phase_shows_every_club_and_no_cut_note(self):
        pages = [p for p in self.make(self.LEAGUE).pages if isinstance(p, yearbook.LeaguePage)]
        self.assertEqual((len(pages[0].table), pages[0].table_note), (4, ""))

    def test_a_continental_competitions_knockout_rounds_are_not_play_offs(self):
        built = self.make(self.LEAGUE + [fx(D(2027, 3, 4), 1, 2, 1, 0, comp=102, md=3, rnd=QF)])
        (block,) = [p for p in built.pages if isinstance(p, yearbook.CupBlock)]
        self.assertTrue(block.heading.startswith("UEFA Champions League, Quarter-final"), block.heading)

    def test_the_title_page_lists_competitions_not_their_play_off_blocks(self):
        built = self.make(self.LEAGUE + [fx(D(2027, 3, 4), 1, 2, 1, 0, comp=102, md=3, rnd=QF)])
        line = next(l for l in built.pages[0].coverage_lines if l.startswith("Competitions:"))
        self.assertEqual(line, "Competitions: UEFA Champions League.")


class ZoneTests(unittest.TestCase):
    NAMES = {12: "Premier League"}
    RELEGATION = NS(competition_id=101, promotion_places=0, playoff_places=0, relegation_places=1, rounds=(), unknown={})

    def make(self, rounds, rules=(RELEGATION,)):
        """Two clubs meeting once a week for `rounds` matchweeks: Hull City always win, so Leeds are bottom."""
        games = [fx(D(2026, 8, 1) + dt.timedelta(days=7 * i), 1, 2, 1, 0, md=i + 1) for i in range(rounds)]
        book, folder = banked(games, rules=list(rules))
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        return yearbook.build_yearbook(book, 2026, self.NAMES)

    @staticmethod
    def week(built, n):
        return next(p for p in built.pages if isinstance(p, yearbook.LeaguePage) and p.matchweek == n)

    def test_zones_start_in_the_last_eleven_matches_of_a_38_match_season_and_the_last_ten_of_a_46_match_one(self):
        self.assertEqual((yearbook.zones_from_matchweek(38), yearbook.zones_from_matchweek(46)), (27, 36))

    def test_the_table_shows_no_zones_before_that_point_and_zones_from_it(self):
        built = self.make(38)
        self.assertEqual({t.zone for t in self.week(built, 26).table}, {""})
        self.assertEqual([t.zone for t in self.week(built, 27).table], ["", "relegation"])
        self.assertEqual(yearbook.zone_legend(self.week(built, 27).table), "Relegation")
        self.assertEqual(yearbook.zone_legend(self.week(built, 26).table), "")

    def test_the_final_table_always_shows_the_zones(self):
        built = self.make(38)
        (final,) = [p for p in built.pages if isinstance(p, yearbook.FinalTablesPage)]
        self.assertEqual([t.zone for t in final.tables[0][1]], ["", "relegation"])

    def test_stray_extra_rounds_in_the_fixture_list_do_not_move_the_start_of_the_zones(self):
        games = [fx(D(2026, 8, 1) + dt.timedelta(days=7 * i), h, a, 1, 0, md=i + 1) for i in range(38) for h, a in ((1, 2), (3, 4))]
        games += [fx(D(2027, 5, 20), 5, 1, 1, 0, md=39), fx(D(2027, 5, 27), 1, 5, 1, 0, md=40)]    # two extra rounds
        book, folder = banked(games, rules=[self.RELEGATION])
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        built = yearbook.build_yearbook(book, 2026, self.NAMES)
        shown = [p.matchweek for p in built.pages if isinstance(p, yearbook.LeaguePage) and p.table and any(t.zone for t in p.table)]
        self.assertEqual(min(shown), 27)                  # a 38-match season, not a 40-round fixture list

    def test_the_legend_lists_zones_from_the_top_of_the_table_down(self):
        lines = (yearbook.TableLine(1, "A", 1, 1, 0, 0, 1, 0, 1, 3, "W", "ucl"), yearbook.TableLine(2, "B", 1, 0, 1, 0, 0, 0, 0, 1, "D", "europa"),
                 yearbook.TableLine(3, "C", 1, 0, 0, 1, 0, 1, -1, 0, "L", "relegation"))
        self.assertEqual(yearbook.zone_legend(lines),
                         "Champions League places (estimated) · Europa League places (estimated) · Relegation")

    def test_a_league_whose_rules_the_save_does_not_give_shows_no_zones(self):
        built = self.make(38, rules=())
        self.assertEqual({t.zone for t in self.week(built, 38).table}, {""})

    def test_a_short_league_shows_zones_from_the_start(self):
        built = self.make(5)
        self.assertEqual([t.zone for t in self.week(built, 1).table], ["", "relegation"])


if __name__ == "__main__":
    unittest.main()


class MovingTableTests(unittest.TestCase):
    NAMES = {12: "Premier League"}

    def pages(self, fixtures, marked=None):
        book, folder = banked(fixtures)
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        built = yearbook.build_yearbook(book, 2026, self.NAMES, marked_club=marked)
        return [p for p in built.pages if isinstance(p, yearbook.LeaguePage) and p.table], built

    ROUNDS = [fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 8), 3, 4, 1, 0, md=1),
              fx(D(2026, 8, 15), 2, 3, 3, 0, md=2), fx(D(2026, 8, 15), 4, 1, 0, 0, md=2)]

    def by_team(self, page):
        return {t.team: t for t in page.table}

    def test_the_first_table_has_no_previous_one_so_every_club_reads_a_dash(self):
        first, _ = self.pages(self.ROUNDS)[0]
        self.assertEqual({t.movement for t in first.table}, {"–"})

    def test_a_club_that_rose_fell_or_stayed_reads_the_places_it_moved(self):
        _, second = self.pages(self.ROUNDS)[0]
        moves = {t.team: t.movement for t in second.table}
        self.assertEqual(moves, {"Hull City": "•", "Leeds United": "▲2", "Derby County": "▼1",
                                 "Sheffield United": "▼1"})

    def test_a_club_that_had_not_played_at_the_previous_table_reads_a_dash(self):
        pages, _ = self.pages([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 15), 3, 4, 2, 0, md=2)])
        self.assertEqual({t.team: t.movement for t in pages[1].table}["Derby County"], "–")

    def test_points_per_game_is_points_over_scored_matches_to_two_places(self):
        pages, _ = self.pages(self.ROUNDS)
        self.assertEqual(self.by_team(pages[1])["Hull City"].ppg, "2.00")

    def test_a_played_match_with_no_score_is_left_out_and_starred(self):
        pages, _ = self.pages([fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 15), 1, 3, None, None, played=True, md=2)])
        self.assertEqual(self.by_team(pages[1])["Hull City"].ppg, "3.00*")

    def test_a_club_with_no_scored_match_has_no_ppg(self):
        pages, _ = self.pages([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 15), 3, 4, md=2)])
        self.assertEqual(self.by_team(pages[0])["Sheffield United"].ppg, "")

    def test_the_marked_club_is_flagged_and_nobody_else(self):
        pages, _ = self.pages(self.ROUNDS, marked=2)
        self.assertEqual([t.team for t in pages[1].table if t.marked], ["Leeds United"])
        self.assertFalse(any(t.marked for t in self.pages(self.ROUNDS)[0][1].table))

    def test_the_final_table_carries_home_and_away_blocks_in_the_overall_order(self):
        full = [fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 15), 2, 1, 0, 1, md=2)]
        _, built = self.pages(full)
        final = built.pages[-1]
        (name, overall, home, away), = final.splits
        self.assertEqual(name, "Premier League")
        self.assertEqual([t.team for t in home], [t.team for t in overall])
        self.assertEqual([t.team for t in away], [t.team for t in overall])
        hull_home = {t.team: t for t in home}["Hull City"]
        hull_away = {t.team: t for t in away}["Hull City"]
        self.assertEqual((hull_home.played, hull_home.points, hull_away.played, hull_away.points), (1, 3, 1, 3))
        self.assertEqual([t.pos for t in home], [t.pos for t in overall])
