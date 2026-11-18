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


if __name__ == "__main__":
    unittest.main()
