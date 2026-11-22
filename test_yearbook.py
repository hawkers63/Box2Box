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
from test_fm_data import D, fx, info, match_stats as report_rows


def banked(fixtures, *, nations=None, competitions=None, game=D(2026, 12, 31), path=None, rules=(), match_stats=None):
    """Bank one save of `fixtures` into a temporary archive and return (archive, folder)."""
    folder = tempfile.TemporaryDirectory()
    base = dataclasses.replace(info(), file_name="a.fm", path="a.fm", game_date=game)
    nations = nations or {i: 5 for i in range(1, 6)}
    clubs = [NS(uid=i, reputation=1, teams=(), nation_id=n) for i, n in nations.items()]
    comps = competitions or [NS(id=101, database_id=12)]
    data = fd.build_dataset(base, fixtures, clubs=clubs, competitions=comps, rules=list(rules), match_stats=match_stats)
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
                                 ("HonoursPage", None), ("PlacesPage", None), ("FinalTablesPage", None)])

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

    def test_every_match_carries_the_archives_own_fixture_key(self):
        book, folder = banked(self.SEASON, competitions=self.COMPS, game=D(2026, 8, 20))
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        built = yearbook.yearbook_from(book.dataset(), book.competitions(), book.coverage(2026), 2026, self.NAMES)
        stored = set(book._db.execute("SELECT competition_key, season, home_uid, away_uid, meeting FROM fixtures"))
        matches = [m for p in built.pages for m in getattr(p, "matches", ())]
        self.assertEqual(len(matches), 5)
        self.assertEqual({m.fixture for m in matches}, stored)

    def test_pages_carry_their_competitions_archive_key(self):
        built = self.make(self.SEASON)
        keys = {type(p).__name__: getattr(p, "competition_key", None) for p in built.pages}
        self.assertEqual((keys["LeaguePage"], keys["CupBlock"], keys["PlacesPage"]), (12, 14, 12))
        self.assertEqual(built.pages[-1].keys, (("Premier League", 12),))

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


class BookBuilder:
    NAMES = {12: "Premier League"}
    # Three rounds of a four-club league, all played: Hull City win every match.
    FINISHED = [fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 8), 3, 4, 1, 1, md=1),
                fx(D(2026, 8, 15), 1, 3, 1, 0, md=2), fx(D(2026, 8, 15), 4, 2, 3, 0, md=2),
                fx(D(2026, 8, 22), 1, 4, 3, 1, md=3), fx(D(2026, 8, 22), 2, 3, 0, 0, md=3)]

    def build(self, fixtures, **kw):
        book, folder = banked(fixtures, **kw)
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        return yearbook.build_yearbook(book, 2026, self.NAMES)


class PlacesPageTests(BookBuilder, unittest.TestCase):
    def places(self, built):
        return [p for p in built.pages if isinstance(p, yearbook.PlacesPage)]

    def test_each_league_with_two_or_more_tables_gets_a_grid_of_the_places_its_weekly_tables_printed(self):
        built = self.build(self.FINISHED)
        (page,) = self.places(built)
        weekly = [p for p in built.pages if isinstance(p, yearbook.LeaguePage) and p.table]
        self.assertEqual((page.competition, page.matchweeks), ("Premier League", (1, 2, 3)))
        for row in page.rows:
            printed = tuple({t.team: t.pos for t in p.table}[row.team] for p in weekly)
            self.assertEqual(row.places, printed, row.team)

    def test_the_rows_follow_the_latest_table_and_the_last_column_is_the_current_place(self):
        (page,) = self.places(self.build(self.FINISHED))
        self.assertEqual([(r.team, r.now) for r in page.rows],
                         [("Hull City", 1), ("Derby County", 2), ("Sheffield United", 3), ("Leeds United", 4)])

    def test_a_club_that_had_not_played_yet_is_blank_not_zero(self):
        built = self.build([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 15), 3, 4, 2, 0, md=2),
                            fx(D(2026, 8, 15), 1, 2, 0, 0, md=2)])
        (page,) = self.places(built)
        self.assertEqual({r.team: r.places[0] for r in page.rows}["Derby County"], None)

    def test_a_league_with_a_single_table_has_no_grid(self):
        self.assertEqual(self.places(self.build(self.FINISHED[:2])), [])

    def test_the_grid_comes_before_the_final_tables_and_after_every_weekly_page(self):
        pages = self.build(self.FINISHED).pages
        kinds = [type(p).__name__ for p in pages]
        self.assertEqual(kinds[-2:], ["PlacesPage", "FinalTablesPage"])

    def test_an_unfinished_season_still_gets_its_grid_at_the_end(self):
        built = self.build([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 15), 1, 2, 0, 0, md=2),
                            fx(D(2026, 8, 22), 1, 2, md=3)])
        self.assertEqual(type(built.pages[-1]).__name__, "PlacesPage")

    def test_the_marked_club_is_flagged_in_the_grid(self):
        book, folder = banked(self.FINISHED)
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        built = yearbook.build_yearbook(book, 2026, self.NAMES, marked_club=2)
        (page,) = self.places(built)
        self.assertEqual([r.team for r in page.rows if r.marked], ["Leeds United"])


class BiggestMovesTests(unittest.TestCase):
    @staticmethod
    def page(*rows):
        return yearbook.PlacesPage("L", (1, 2, 3, 4), tuple(yearbook.PlacesRow(t, p, "", p[-1] or 0) for t, p in rows))

    def test_a_rise_is_the_biggest_climb_from_an_earlier_week_to_a_later_one(self):
        page = self.page(("A", (5, 6, 3, 2)), ("B", (1, 2, 2, 3)), ("C", (2, 1, 1, 1)))
        rise, fall, left_out = yearbook.biggest_moves(page)
        self.assertEqual(rise, (yearbook.Move("A", 6, 2, 2, 4),))
        self.assertEqual(fall, (yearbook.Move("B", 1, 1, 3, 4),))
        self.assertFalse(left_out)

    def test_clubs_that_tie_for_the_biggest_rise_are_all_returned(self):
        page = self.page(("A", (6, 2, 2, 2)), ("B", (8, 4, 4, 4)), ("C", (3, 3, 3, 3)))
        rise, _, _ = yearbook.biggest_moves(page)
        self.assertEqual([m.team for m in rise], ["A", "B"])

    def test_clubs_that_tie_for_the_biggest_fall_are_all_returned(self):
        page = self.page(("A", (1, 3, 3, 3)), ("B", (2, 4, 4, 4)), ("C", (1, 1, 1, 2)))
        _, fall, _ = yearbook.biggest_moves(page)
        self.assertEqual([m.team for m in fall], ["A", "B"])

    def test_a_longer_climb_of_the_same_size_does_not_tie_with_a_shorter_one(self):
        page = self.page(("A", (4, 2, 2, 2)), ("B", (4, 4, 3, 2)))
        rise, _, _ = yearbook.biggest_moves(page)
        self.assertEqual([m.team for m in rise], ["A"])

    def test_a_club_is_named_once_however_many_windows_tie(self):
        page = self.page(("A", (5, 3, 5, 3)))
        rise, _, _ = yearbook.biggest_moves(page)
        self.assertEqual([m.team for m in rise], ["A"])

    def test_one_club_reads_as_it_always_did(self):
        move = yearbook.Move("A", 6, 2, 2, 4)
        self.assertEqual(yearbook.describe_moves("Biggest rise", (move,)),
                         "Biggest rise: A, from 6th after matchweek 2 to 2nd after matchweek 4")

    def test_the_results_strip_names_every_club_tied_for_the_biggest_rise(self):
        page = self.page(("A", (6, 2, 2, 2)), ("B", (8, 4, 4, 4)), ("C", (3, 3, 3, 3)))
        lines = yearbook.results_strip([], [], [], {}, page)
        self.assertEqual(lines[0], "Biggest rise, shared by 2 clubs: A, from 6th after matchweek 1 to 2nd after "
                                   "matchweek 2; B, from 8th after matchweek 1 to 4th after matchweek 2")

    def test_every_tied_club_is_named_in_the_line(self):
        moves = (yearbook.Move("A", 6, 1, 2, 2), yearbook.Move("B", 9, 3, 5, 4))
        self.assertEqual(
            yearbook.describe_moves("Biggest fall", moves),
            "Biggest fall, shared by 2 clubs: A, from 6th after matchweek 1 to 2nd after matchweek 2; "
            "B, from 9th after matchweek 3 to 5th after matchweek 4")

    def test_a_club_that_had_not_played_every_week_is_left_out_and_counted(self):
        page = self.page(("A", (None, 9, 3, 2)), ("B", (4, 4, 4, 4)))
        rise, fall, left_out = yearbook.biggest_moves(page)
        self.assertEqual((rise, fall, left_out), ((), (), 1))

    def test_a_league_that_never_moved_has_no_rise_or_fall(self):
        self.assertEqual(yearbook.biggest_moves(self.page(("A", (1, 1, 1, 1)), ("B", (2, 2, 2, 2))))[:2], ((), ()))


class ResultsStripTests(BookBuilder, unittest.TestCase):
    def strip(self, fixtures):
        built = self.build(fixtures)
        final = built.pages[-1]
        self.assertIsInstance(final, yearbook.FinalTablesPage)
        return dict(final.strips)["Premier League"]

    def test_a_finished_league_gets_its_figures_taken_from_the_final_table_and_the_results(self):
        lines = self.strip(self.FINISHED)
        self.assertIn("Most wins: Hull City (3)", lines)
        self.assertIn("Best goal difference: Hull City (+5)", lines)
        self.assertIn("Fewest goals against: Hull City (1)", lines)
        self.assertIn("Most draws: Sheffield United (2)", lines)
        self.assertIn("Longest winning run: Hull City (3)", lines)
        self.assertIn("Longest unbeaten run: Hull City (3)", lines)

    def test_clubs_that_share_a_record_are_all_named(self):
        lines = self.strip([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 8), 3, 4, 1, 0, md=1),
                            fx(D(2026, 8, 15), 1, 3, 0, 0, md=2), fx(D(2026, 8, 15), 2, 4, 0, 0, md=2)])
        self.assertIn("Most wins: Hull City and Sheffield United (1)", lines)

    def test_a_season_not_finished_has_no_strip(self):
        built = self.build(self.FINISHED[:-1] + [fx(D(2026, 8, 22), 2, 3, md=3)])
        self.assertFalse([p for p in built.pages if isinstance(p, yearbook.FinalTablesPage)])

    def test_a_match_with_no_score_ends_a_run_and_the_strip_says_so(self):
        fixtures = [dataclasses.replace(f, home_goals=None, away_goals=None) if f.round_index == 1 and f.home_club_uid == 1
                    else f for f in self.FINISHED]
        lines = self.strip(fixtures)
        self.assertIn("Longest winning run: Derby County and Hull City (1)", lines)
        self.assertEqual(lines[-1], "A match with no score is not part of a run.")

    def test_the_strip_never_names_a_player_or_an_award(self):
        text = " ".join(self.strip(self.FINISHED)).lower()
        for word in ("player", "manager", "award", "signing"):
            self.assertNotIn(word, text)

    def test_ordinals_read_naturally(self):
        self.assertEqual([yearbook.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 24)],
                         ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "24th"])


class ExcludedCompetitionTests(BookBuilder, unittest.TestCase):
    """The U18 competitions never appear in the book, even when the user has named them."""

    FIXTURES = [fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 15), 2, 1, 0, 1, md=2),
                fx(D(2026, 8, 8), 3, 4, 1, 1, comp=102, md=1), fx(D(2026, 8, 15), 4, 3, 0, 0, comp=102, md=2)]
    COMPS = [NS(id=101, database_id=12), NS(id=102, database_id=95041306)]

    def build_with(self, names):
        book, folder = banked(self.FIXTURES, competitions=self.COMPS)
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        return yearbook.build_yearbook(book, 2026, names)

    def test_a_named_u18_competition_gets_no_pages_and_is_not_listed(self):
        built = self.build_with({12: "Premier League", 95041306: "U18 Premier League"})
        self.assertEqual({p.competition for p in built.pages if hasattr(p, "competition")}, {"Premier League"})
        self.assertNotIn("U18", " ".join(built.pages[0].coverage_lines))

    def test_both_u18_ids_are_excluded(self):
        self.assertTrue({95041306, 95041309} <= set(yearbook.EXCLUDED_DATABASE_IDS))

    def test_an_excluded_competition_named_premier_league_does_not_decide_the_home_nation(self):
        built = self.build_with({12: "Premier League", 95041306: "Premier League"})
        self.assertEqual({p.competition for p in built.pages if hasattr(p, "competition")}, {"Premier League"})


class XgColumnsTests(BookBuilder, unittest.TestCase):
    """Expected goals on a finished league's final table, from what the archive kept."""

    def reports(self, which):
        """Match reports for the FINISHED fixtures (by index): every home side 1.5 xG, every away side 0.5."""
        rows = []
        for i in which:
            rows += report_rows(self.FINISHED[i], 1.5, 0.5)
        return rows

    def final(self, which):
        book, folder = banked(self.FINISHED, match_stats=self.reports(which))
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        built = yearbook.build_yearbook(book, 2026, self.NAMES)
        page = built.pages[-1]
        self.assertIsInstance(page, yearbook.FinalTablesPage)
        return built, {t.team: t for t in page.tables[0][1]}, dict(page.xg_notes).get("Premier League", "")

    def test_with_a_report_for_every_match_the_final_table_gains_xg_xga_and_goals_minus_xg(self):
        built, lines, note = self.final(range(6))
        hull = lines["Hull City"]
        self.assertEqual((hull.xg_for, hull.xg_against, hull.xg_over), ("4.50", "1.50", "+1.50"))
        self.assertEqual(yearbook.standings_head(tuple(lines.values()))[-5:], ("PPG", "xG", "xGA", "G-xG", "Last six"))
        self.assertIn("xG and xGA are expected goals for and against", note)
        self.assertIn("G-xG is goals scored minus xG", note)
        self.assertNotIn("of", note.split("xGA")[-1].split(".")[0])          # no "N of M" when everything is covered

    def test_a_league_whose_reports_never_arrived_has_no_xg_columns_at_all(self):
        built, lines, note = self.final([])
        self.assertEqual({(t.xg_for, t.xg_against, t.xg_over) for t in lines.values()}, {("", "", "")})
        self.assertNotIn("xG", yearbook.standings_head(tuple(lines.values())))
        self.assertEqual(note, "")

    def test_with_some_reports_missing_the_totals_are_partial_and_the_note_says_how_many_and_no_comparison_is_made(self):
        built, lines, note = self.final([0, 1, 2])
        self.assertEqual(yearbook.standings_head(tuple(lines.values()))[-4:], ("PPG", "xG", "xGA", "Last six"))
        self.assertTrue(all(t.xg_over == "" for t in lines.values()))
        self.assertIn("Expected goals for 3 of 6 played matches.", note)
        self.assertNotIn("G-xG", note)

    def test_a_club_with_no_report_at_all_is_blank_never_0_00(self):
        built, lines, _ = self.final([0])                                    # only Hull City v Leeds United has one
        self.assertEqual((lines["Derby County"].xg_for, lines["Derby County"].xg_against), ("", ""))
        self.assertEqual(lines["Hull City"].xg_for, "1.50")

    def test_a_match_with_a_report_but_no_score_is_not_counted_in_the_totals(self):
        fixtures = [dataclasses.replace(f, home_goals=None, away_goals=None) if i == 0 else f for i, f in enumerate(self.FINISHED)]
        rows = []
        for f in fixtures:
            rows += report_rows(f, 1.5, 0.5)
        book, folder = banked(fixtures, match_stats=rows)
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        page = yearbook.build_yearbook(book, 2026, self.NAMES).pages[-1]
        hull = {t.team: t for t in page.tables[0][1]}["Hull City"]
        self.assertEqual((hull.played, hull.xg_for), (2, "3.00"))

    def test_the_weekly_tables_never_carry_expected_goals(self):
        built, _, _ = self.final(range(6))
        weekly = [t for p in built.pages if isinstance(p, yearbook.LeaguePage) for t in p.table]
        self.assertEqual({(t.xg_for, t.xg_against, t.xg_over) for t in weekly}, {("", "", "")})


class TrajectoryTests(BookBuilder, unittest.TestCase):
    """Stage 1 (2.10): the dated season trajectory of the marked club, from the places the weekly tables printed."""

    def built(self, fixtures, marked=2):
        book, folder = banked(fixtures)
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        return yearbook.build_yearbook(book, 2026, self.NAMES, marked_club=marked)

    def trajectory(self, built):
        return [p for p in built.pages if isinstance(p, yearbook.TrajectoryPage)]

    def test_the_marked_club_gets_a_chart_of_the_exact_places_and_cutoff_dates_of_the_weekly_tables(self):
        built = self.built(self.FINISHED)
        (page,) = self.trajectory(built)
        (chart,) = page.charts
        weekly = [p for p in built.pages if isinstance(p, yearbook.LeaguePage) and p.table]
        self.assertEqual((page.club, chart.competition, chart.clubs), ("Leeds United", "Premier League", 4))
        self.assertEqual([(p.matchweek, p.through, p.place) for p in chart.points],
                         [(w.matchweek, w.through, {t.team: t.pos for t in w.table}["Leeds United"]) for w in weekly])
        self.assertEqual([p.through for p in chart.points], [D(2026, 8, 8), D(2026, 8, 15), D(2026, 8, 22)])

    def test_a_club_that_had_not_played_is_a_gap_and_the_line_does_not_join_across_it(self):
        built = self.built([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 15), 3, 4, 2, 0, md=2),
                            fx(D(2026, 8, 15), 1, 5, 0, 0, md=2), fx(D(2026, 8, 22), 2, 3, 1, 1, md=3),
                            fx(D(2026, 8, 22), 1, 4, 2, 0, md=3)], marked=5)
        (chart,) = self.trajectory(built)[0].charts
        self.assertEqual([p.place is None for p in chart.points], [True, False, False])
        self.assertEqual([[p.matchweek for p in run] for run in yearbook.trajectory_segments(chart)], [[2, 3]])

    def test_a_matchweek_with_no_printed_table_breaks_the_line_without_interpolating(self):
        point = lambda week, place: yearbook.TrajectoryPoint(week, D(2026, 8, 1) + dt.timedelta(days=7 * week), place)
        chart = yearbook.Trajectory("Premier League", 4, (point(1, 3), point(2, 2), point(4, 2), point(5, None), point(6, 1)))
        self.assertEqual([[p.matchweek for p in run] for run in yearbook.trajectory_segments(chart)], [[1, 2], [4], [6]])

    def test_the_hover_results_are_the_clubs_own_matches_of_that_matchweek_only(self):
        (chart,) = self.trajectory(self.built(self.FINISHED))[0].charts
        self.assertEqual([[(m.home, m.score, m.away) for m in p.results] for p in chart.points],
                         [[("Hull City", "2-0", "Leeds United")], [("Derby County", "3-0", "Leeds United")],
                          [("Leeds United", "0-0", "Sheffield United")]])

    def test_no_marked_club_means_no_trajectory_page(self):
        self.assertEqual(self.trajectory(self.built(self.FINISHED, marked=None)), [])

    def test_a_marked_club_in_no_league_gets_a_short_note_instead_of_a_chart(self):
        page = self.trajectory(self.built(self.FINISHED, marked=2))[0]
        self.assertTrue(page.charts)                               # the club in a league has a chart and no note
        self.assertEqual(page.note, "")
        none = yearbook.trajectory_page("Wigan Rovers", [], [])
        self.assertEqual((none.charts, none.note), ((), "Wigan Rovers is in no league of this book, so there is no league trajectory to chart."))
        thin = yearbook.trajectory_page("Wigan Rovers", [], ["Premier League"])
        self.assertIn("fewer than two weekly tables", thin.note)

    def test_the_zones_come_from_the_latest_table_and_the_chart_carries_the_estimated_note(self):
        (chart,) = self.trajectory(self.built(self.FINISHED))[0].charts
        self.assertEqual(chart.zones, ())                          # these made-up rules name no zone
        self.assertIn("estimated", yearbook.TRAJECTORY_NOTE)
        self.assertIn("not calendar weeks", yearbook.TRAJECTORY_NOTE)


def line(pos, team, points, gd=0, zone="", played=3):
    return yearbook.TableLine(pos, team, played, 0, 0, 0, max(gd, 0), max(-gd, 0), gd, points, "", zone)


class LeagueHonourTests(unittest.TestCase):
    """Stage 2 (2.10): a league's honour is a calculated leader, with the reason it is not an official champion."""

    def test_the_leader_is_called_calculated_and_the_missing_deductions_are_the_footnoted_reason(self):
        honour = yearbook.league_honour("Premier League", (line(1, "Hull City", 9), line(2, "Leeds United", 6)), (0, 1))
        self.assertEqual(honour.lines[0], "Calculated leader: Hull City, 9 points from 3 matches [1]")
        self.assertEqual(honour.notes[0], yearbook.DEDUCTIONS_NOTE)
        self.assertNotIn("champion", honour.lines[0].lower())
        self.assertEqual(len(honour.lines), 1)

    def test_a_tie_on_points_is_named_with_the_tie_break_it_rests_on_or_cannot_follow(self):
        table = (line(1, "Hull City", 9, gd=4), line(2, "Leeds United", 9, gd=2))
        resolved = yearbook.league_honour("Premier League", table, (0, 1))
        self.assertIn("Level on points with Leeds United [2]", resolved.lines[1])
        self.assertIn("goal difference", resolved.notes[1])
        later_rule = yearbook.league_honour("Premier League", table, (0, 1, 99))      # a rule this cannot follow comes after
        self.assertIn("separated by goal difference", later_rule.notes[1])
        unresolved = yearbook.league_honour("Premier League", table, (99, 0))        # one it cannot follow comes first
        self.assertIn("may differ", unresolved.notes[1])
        self.assertIn("unresolved", unresolved.notes[1])
        nothing_listed = yearbook.league_honour("Premier League", table, ())
        self.assertIn("unresolved", nothing_listed.notes[1])

    def test_a_dead_level_leader_is_unresolved_even_when_the_rules_list_tie_breaks(self):
        table = (line(1, "Hull City", 9, gd=2), line(2, "Leeds United", 9, gd=2))
        honour = yearbook.league_honour("Premier League", table, (0,))
        self.assertIn("unresolved", honour.notes[1])

    def test_promotion_and_play_off_places_are_places_not_outcomes(self):
        table = (line(1, "Hull City", 9, zone="promotion"), line(2, "Leeds United", 7, zone="promotion"),
                 line(3, "Derby County", 6, zone="playoff"), line(4, "Wrexham", 3))
        honour = yearbook.league_honour("Championship", table, (0, 1))
        text = "\n".join(honour.lines)
        self.assertIn("In the promotion places on the calculated table: Hull City, Leeds United [", text)
        self.assertIn("In the play-off places on the calculated table: Derby County [", text)
        notes = "\n".join(honour.notes)
        self.assertIn(yearbook.PROMOTION_NOTE, notes)
        self.assertIn(yearbook.PLAYOFF_NOTE, notes)
        self.assertNotIn("promoted", text.lower())
        self.assertNotIn("won the play-off", text.lower())

    def test_a_table_with_no_scored_leader_makes_no_claim(self):
        self.assertIsNone(yearbook.league_honour("Premier League", (), (0,)))


FINAL = CodedValue(CompetitionRound.FINAL, 18)


class CupHonourTests(unittest.TestCase):
    """Stage 2 (2.10): a cup winner needs a decisive score, an aggregate or later-round evidence."""
    NAMES = {14: "FA Cup"}
    COMPS = [NS(id=102, database_id=14)]

    def honour(self, fixtures, names=None):
        book, folder = banked(fixtures, competitions=self.COMPS, game=D(2026, 5, 30))
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        built = yearbook.build_yearbook(book, 2026, self.NAMES if names is None else names)
        pages = [p for p in built.pages if isinstance(p, yearbook.HonoursPage)]
        return pages[0] if pages else None

    def final(self, hg, ag, **kw):
        return [fx(D(2026, 5, 16), 1, 2, hg, ag, comp=102, md=1, rnd=FINAL, **kw)]

    def test_a_decisive_final_score_names_the_winner_with_no_footnote(self):
        page = self.honour(self.final(2, 1))
        (entry,) = page.entries
        self.assertEqual((entry.competition, entry.lines), ("FA Cup", ("Winner: Hull City, 2-1 against Leeds United, won on the final's score",)))
        self.assertEqual((entry.notes, page.notes), ((), ()))

    def test_an_away_winner_is_named_as_the_winner(self):
        (entry,) = self.honour(self.final(0, 1)).entries
        self.assertTrue(entry.lines[0].startswith("Winner: Leeds United"))

    def test_a_level_final_with_no_resolved_winner_stays_unresolved_and_says_why(self):
        page = self.honour(self.final(1, 1))
        (entry,) = page.entries
        self.assertEqual(entry.lines, ("Winner: unresolved. Hull City 1-1 Leeds United in the final [1]",))
        self.assertEqual(page.notes, (f"[1] {yearbook.CUP_LEVEL_NOTE}",))
        self.assertNotIn("Winner: Hull", entry.lines[0])

    def test_two_legs_are_decided_on_aggregate_and_a_level_aggregate_is_unresolved(self):
        legs = lambda g1, g2: [fx(D(2026, 5, 9), 1, 2, g1[0], g1[1], comp=102, md=1, rnd=FINAL),
                               fx(D(2026, 5, 16), 2, 1, g2[0], g2[1], comp=102, md=1, rnd=FINAL)]
        (won,) = self.honour(legs((1, 0), (1, 1))).entries              # Hull 2-1 on aggregate
        self.assertEqual(won.lines, ("Winner: Hull City, won on aggregate (2-1 against Leeds United)",))
        level = self.honour(legs((1, 0), (1, 0)))                         # 1-1 on aggregate... Leeds 1-0 second leg
        self.assertEqual(level.entries[0].lines[0][:19], "Winner: unresolved.")

    def test_a_final_not_yet_played_or_a_round_that_is_not_a_final_gives_no_honour(self):
        self.assertIsNone(self.honour([fx(D(2026, 5, 16), 1, 2, comp=102, md=1, rnd=FINAL)]))
        self.assertIsNone(self.honour([fx(D(2026, 5, 16), 1, 2, 2, 1, comp=102, md=1, rnd=SF)]))


class HonoursPageTests(unittest.TestCase):
    def test_footnotes_are_numbered_across_the_page_and_the_same_reason_keeps_one_number(self):
        one = yearbook.HonoursEntry("Premier League", ("Calculated leader: A, 9 points from 3 matches [1]", "Level on points with B [2]"),
                                    (yearbook.DEDUCTIONS_NOTE, "Tie-break unresolved: x"))
        two = yearbook.HonoursEntry("Championship", ("Calculated leader: C, 7 points from 3 matches [1]",), (yearbook.DEDUCTIONS_NOTE,))
        cup = yearbook.HonoursEntry("FA Cup", ("Winner: unresolved. [1]",), (yearbook.CUP_LEVEL_NOTE,))
        page = yearbook.honours_page([one, None, two, cup])
        self.assertEqual([e.lines for e in page.entries],
                         [("Calculated leader: A, 9 points from 3 matches [1]", "Level on points with B [2]"),
                          ("Calculated leader: C, 7 points from 3 matches [1]",), ("Winner: unresolved. [3]",)])
        self.assertEqual(page.notes, (f"[1] {yearbook.DEDUCTIONS_NOTE}", "[2] Tie-break unresolved: x",
                                      f"[3] {yearbook.CUP_LEVEL_NOTE}"))

    def test_no_entries_means_no_page(self):
        self.assertIsNone(yearbook.honours_page([None, None]))
        self.assertIsNone(yearbook.honours_page([]))


class RetrospectiveTests(BookBuilder, unittest.TestCase):
    """Stage 3 (2.10): the followed club's season, from results only: no venue, attendance, scorer or manager claim."""

    def built(self, fixtures, marked=2, comps=None, names=None):
        book, folder = banked(fixtures, competitions=comps, game=D(2026, 5, 30))
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        return yearbook.build_yearbook(book, 2026, names or self.NAMES, marked_club=marked)

    def retro(self, built):
        pages = [p for p in built.pages if isinstance(p, yearbook.RetrospectivePage)]
        return pages[0] if pages else None

    def test_the_league_record_is_the_calculated_place_and_the_scored_results(self):
        page = self.retro(self.built(self.FINISHED, marked=2))
        self.assertEqual(page.club, "Leeds United")
        self.assertIn("Premier League: 4th on the calculated table after 3 matches (0 won, 1 drawn, 2 lost; 0 scored, "
                      "5 conceded; 1 point)", page.lines)

    def test_the_biggest_win_is_by_margin_and_every_win_level_on_it_is_named(self):
        page = self.retro(self.built(self.FINISHED, marked=1))
        self.assertIn("Biggest win (by 2): Hull City 2-0 Leeds United (Premier League, Sat 8 Aug); "
                      "Hull City 3-1 Derby County (Premier League, Sat 22 Aug)", page.lines)

    def test_a_club_that_never_won_has_no_biggest_win_line(self):
        page = self.retro(self.built(self.FINISHED, marked=2))
        self.assertFalse(any(line.startswith("Biggest win") for line in page.lines))

    def test_the_longest_unbeaten_and_winless_runs_are_league_runs_with_their_dates(self):
        lines = self.retro(self.built(self.FINISHED, marked=2)).lines
        self.assertIn("Premier League: Unbeaten in 1 (Sat 22 Aug)", lines)
        self.assertIn("Premier League: Without a win in 3 (Sat 8 – Sat 22 Aug)", lines)
        hull = self.retro(self.built(self.FINISHED, marked=1)).lines
        self.assertIn("Premier League: Unbeaten in 3 (Sat 8 – Sat 22 Aug)", hull)
        self.assertFalse(any("Without a win" in line for line in hull))             # no such run: nothing is invented

    def test_the_page_points_to_the_trajectory_and_never_claims_venues_or_people(self):
        page = self.retro(self.built(self.FINISHED, marked=2))
        self.assertIn("The season trajectory page charts Leeds United's place after each matchweek.", page.lines)
        text = " ".join(page.lines + page.notes).lower()
        for word in ("attendance", "scorer", "manager", "at home", "away from home", "derby", "comeback"):
            self.assertNotIn(word, text.replace("derby county", ""))

    def test_no_followed_club_leaves_the_chapter_out(self):
        self.assertIsNone(self.retro(self.built(self.FINISHED, marked=None)))

    def test_the_book_closes_with_the_retrospective_after_the_final_tables_and_honours(self):
        kinds = [type(p).__name__ for p in self.built(self.FINISHED, marked=2).pages]
        self.assertEqual(kinds[-1], "RetrospectivePage")
        self.assertLess(kinds.index("TrajectoryPage"), kinds.index("FinalTablesPage"))


class RetrospectiveCupTests(unittest.TestCase):
    NAMES = {14: "FA Cup"}
    COMPS = [NS(id=102, database_id=14)]

    def retro(self, fixtures, marked=1):
        book, folder = banked(fixtures, competitions=self.COMPS, game=D(2026, 5, 30))
        self.addCleanup(folder.cleanup)
        self.addCleanup(book.close)
        built = yearbook.build_yearbook(book, 2026, self.NAMES, marked_club=marked)
        return next((p for p in built.pages if isinstance(p, yearbook.RetrospectivePage)), None), built

    def test_a_cup_only_club_has_cup_progress_and_no_league_lines_and_no_trajectory_pointer(self):
        fixtures = [fx(D(2026, 3, 4), 1, 2, 2, 0, comp=102, md=1, rnd=QF), fx(D(2026, 4, 8), 1, 3, 0, 1, comp=102, md=2, rnd=SF)]
        page, built = self.retro(fixtures)
        self.assertIn("FA Cup: out in the Semi-final, to Sheffield United", page.lines)
        self.assertIn("Biggest win (by 2): Hull City 2-0 Leeds United (FA Cup, Wed 4 Mar)", page.lines)
        self.assertFalse(any("trajectory" in line for line in page.lines))
        trajectory = [p for p in built.pages if isinstance(p, yearbook.TrajectoryPage)]
        self.assertEqual(trajectory[0].charts, ())                       # a short note, not a chart
        self.assertIn("is in no league of this book", trajectory[0].note)

    def test_winning_the_final_on_a_decisive_score_is_the_only_way_to_be_called_the_winner(self):
        page, _ = self.retro([fx(D(2026, 5, 16), 1, 2, 2, 1, comp=102, md=1, rnd=FINAL)])
        self.assertIn("FA Cup: won the final against Leeds United", page.lines)
        level, _ = self.retro([fx(D(2026, 5, 16), 1, 2, 1, 1, comp=102, md=1, rnd=FINAL)])
        self.assertIn("FA Cup: the Final against Leeds United is unresolved [1]", level.lines)
        self.assertEqual(level.notes[-1], f"[1] {yearbook.RETRO_UNRESOLVED_NOTE}")
        self.assertFalse(any("won the final" in line for line in level.lines))

    def test_a_tie_not_yet_played_is_not_a_result(self):
        page, _ = self.retro([fx(D(2026, 3, 4), 1, 2, 2, 0, comp=102, md=1, rnd=QF), fx(D(2026, 4, 8), 1, 3, comp=102, md=2, rnd=SF)])
        self.assertIn("FA Cup: in the Semi-final against Sheffield United, not yet played", page.lines)
