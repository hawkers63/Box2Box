# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for fm_schedule_view: pure filter logic (ScheduleFilter, apply_filter).

Run:  .venv\\Scripts\\python -m unittest test_fm_schedule_view -v
"""

import datetime as dt
import unittest
from dataclasses import replace
from unittest.mock import MagicMock

import fm_data as fd
from fm_schedule_view import ScheduleFilter, apply_filter


def _fixture(date=None, competition_id=1, home_id=100, away_id=200):
    f = MagicMock()
    f.date = date
    f.competition_id = competition_id
    f.home_club_id = home_id
    f.away_club_id = away_id
    return f


def _item(*, competition_id=1, venue="H", opponent="Chelsea", outcome="W",
          played=True, date=None, when=fd.WHEN_PLAYED, days=None):
    item = MagicMock(spec=fd.ScheduleItem)
    item.competition_id = competition_id
    item.venue = venue
    item.opponent = opponent
    item.outcome = outcome if played else None
    item.played = played
    item.score = "2-1" if played else ""
    item.when = when
    item.days = days
    # fixture with date for month filtering
    f = MagicMock()
    f.date = date
    item.fixture = f
    return item


class ScheduleFilterTests(unittest.TestCase):
    def test_empty_filter_is_not_active(self):
        self.assertFalse(ScheduleFilter().active)

    def test_competition_id_makes_filter_active(self):
        self.assertTrue(ScheduleFilter(competition_id=5).active)

    def test_venue_makes_filter_active(self):
        self.assertTrue(ScheduleFilter(venue="H").active)

    def test_month_makes_filter_active(self):
        self.assertTrue(ScheduleFilter(month=8).active)

    def test_result_makes_filter_active(self):
        self.assertTrue(ScheduleFilter(result="W").active)

    def test_search_makes_filter_active(self):
        self.assertTrue(ScheduleFilter(search="city").active)

    def test_describe_empty_gives_empty_string(self):
        self.assertEqual(ScheduleFilter().describe(), "")

    def test_describe_includes_venue_name(self):
        self.assertIn("home", ScheduleFilter(venue="H").describe())
        self.assertIn("away", ScheduleFilter(venue="A").describe())
        self.assertIn("neutral", ScheduleFilter(venue="N").describe())

    def test_describe_includes_month_name(self):
        self.assertIn("August", ScheduleFilter(month=8).describe())

    def test_describe_includes_result_word(self):
        self.assertIn("wins", ScheduleFilter(result="W").describe())
        self.assertIn("draws", ScheduleFilter(result="D").describe())

    def test_describe_includes_search_quoted(self):
        d = ScheduleFilter(search="city").describe()
        self.assertIn("city", d)

    def test_describe_combines_active_parts(self):
        d = ScheduleFilter(venue="H", result="W").describe()
        self.assertIn("home", d)
        self.assertIn("wins", d)

    def test_filter_is_frozen(self):
        f = ScheduleFilter()
        with self.assertRaises((AttributeError, TypeError)):
            f.venue = "H"


class ApplyFilterTests(unittest.TestCase):
    def setUp(self):
        self.items = (
            _item(competition_id=1, venue="H", opponent="Chelsea",   outcome="W", played=True,  date=dt.date(2027, 8, 10)),
            _item(competition_id=1, venue="A", opponent="Arsenal",   outcome="L", played=True,  date=dt.date(2027, 9, 5)),
            _item(competition_id=2, venue="H", opponent="Spurs",     outcome="D", played=True,  date=dt.date(2027, 8, 20)),
            _item(competition_id=1, venue="H", opponent="City",      outcome=None,played=False, date=dt.date(2027, 10, 1), when=fd.WHEN_UPCOMING),
        )

    def test_no_filter_returns_all(self):
        self.assertEqual(apply_filter(self.items, ScheduleFilter()), self.items)

    def test_competition_filter_keeps_matching(self):
        result = apply_filter(self.items, ScheduleFilter(competition_id=2))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].opponent, "Spurs")

    def test_venue_filter_home(self):
        result = apply_filter(self.items, ScheduleFilter(venue="H"))
        self.assertTrue(all(i.venue == "H" for i in result))
        self.assertEqual(len(result), 3)

    def test_venue_filter_away(self):
        result = apply_filter(self.items, ScheduleFilter(venue="A"))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].opponent, "Arsenal")

    def test_month_filter_august(self):
        result = apply_filter(self.items, ScheduleFilter(month=8))
        self.assertEqual(len(result), 2)
        self.assertTrue(all(i.fixture.date.month == 8 for i in result))

    def test_month_filter_excludes_undated(self):
        items = self.items + (_item(date=None, played=False, when=fd.WHEN_UNDATED),)
        result = apply_filter(items, ScheduleFilter(month=8))
        # undated item excluded
        self.assertTrue(all(i.fixture.date is not None for i in result))

    def test_result_filter_wins(self):
        result = apply_filter(self.items, ScheduleFilter(result="W"))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].opponent, "Chelsea")

    def test_result_filter_excludes_unplayed(self):
        result = apply_filter(self.items, ScheduleFilter(result="W"))
        self.assertTrue(all(i.played for i in result))

    def test_search_case_insensitive(self):
        result = apply_filter(self.items, ScheduleFilter(search="CHELSEA"))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].opponent, "Chelsea")

    def test_search_partial_match(self):
        result = apply_filter(self.items, ScheduleFilter(search="en"))
        # Arsenal and Chelsea both contain "en"
        self.assertGreaterEqual(len(result), 1)
        self.assertTrue(all("en" in i.opponent.lower() for i in result))

    def test_search_no_match_returns_empty(self):
        result = apply_filter(self.items, ScheduleFilter(search="xxxxxxx"))
        self.assertEqual(result, ())

    def test_filters_combine_as_and(self):
        result = apply_filter(self.items, ScheduleFilter(competition_id=1, venue="H"))
        # comp=1 AND home: Chelsea (W) and City (upcoming)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(i.competition_id == 1 and i.venue == "H" for i in result))

    def test_result_tuple(self):
        result = apply_filter(self.items, ScheduleFilter())
        self.assertIsInstance(result, tuple)


if __name__ == "__main__":
    unittest.main()
