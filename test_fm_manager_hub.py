# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for fm_manager_hub: pure hub_rows model.

Run:  .venv\\Scripts\\python -m unittest test_fm_manager_hub -v
"""

import unittest
from unittest.mock import MagicMock
import datetime as dt

import fm_data as fd
from fm_manager_hub import hub_rows, HubRow


def _followed(name="Hull City"):
    fc = MagicMock(spec=fd.FollowedClub)
    fc.name = name
    return fc


def _rank(rank=3, points=45):
    return fd.RankBefore(position=rank, of=20, points=points, played=10, cutoff=fd.Cutoff(dt.date(2099, 10, 1), None),
                         unscored=0)


def _schedule_item(opponent="Burnley", venue="H", outcome="W", played=True,
                   when=fd.WHEN_UPCOMING, days=3, competition_id=1, date=None):
    item = MagicMock(spec=fd.ScheduleItem)
    item.opponent = opponent
    item.venue = venue
    item.outcome = outcome if played else None
    item.played = played
    item.when = when
    item.days = days
    item.competition_id = competition_id
    f = MagicMock()
    f.date = date or dt.date(2027, 10, 15)
    item.fixture = f
    return item


def _snapshot(followed=None, managed=True, manager_name="Bob Smith",
              next_item=None, next_scope_label="Championship",
              form=(), rank=None):
    s = MagicMock(spec=fd.ManagerSnapshot)
    s.followed = followed or _followed()
    s.managed = managed
    s.manager_name = manager_name
    s.next_item = next_item
    s.next_scope_label = next_scope_label
    s.form = tuple(form)
    s.rank_before_next = rank
    return s


class HubRowsTests(unittest.TestCase):
    def test_club_name_appears_in_rows(self):
        rows = hub_rows(_snapshot(followed=_followed("Hull City")))
        labels = [r.label for r in rows]
        values = [r.value for r in rows]
        self.assertIn("Club", labels)
        self.assertIn("Hull City", values)

    def test_managed_role_includes_manager_name(self):
        rows = hub_rows(_snapshot(managed=True, manager_name="Bob Smith"))
        role_row = next(r for r in rows if r.label == "Role")
        self.assertIn("Bob Smith", role_row.value)

    def test_observer_role_is_muted(self):
        rows = hub_rows(_snapshot(managed=False, manager_name=None))
        role_row = next(r for r in rows if r.label == "Role")
        self.assertTrue(role_row.muted)
        self.assertIn("Observer", role_row.value)

    def test_rank_appears_when_present(self):
        rows = hub_rows(_snapshot(rank=_rank(rank=3, points=45)))
        pos_row = next(r for r in rows if r.label == "Position")
        self.assertIn("3", pos_row.value)
        self.assertIn("45", pos_row.value)

    def test_no_rank_row_when_absent(self):
        rows = hub_rows(_snapshot(rank=None))
        labels = [r.label for r in rows]
        self.assertNotIn("Position", labels)

    def test_form_outcomes_shown(self):
        form = (_schedule_item(outcome="W"), _schedule_item(outcome="D"), _schedule_item(outcome="L"))
        rows = hub_rows(_snapshot(form=form))
        form_row = next(r for r in rows if r.label == "Form")
        self.assertEqual(form_row.value, "WDL")

    def test_no_form_shows_dash(self):
        rows = hub_rows(_snapshot(form=()))
        form_row = next(r for r in rows if r.label == "Form")
        self.assertEqual(form_row.value, "—")
        self.assertTrue(form_row.muted)

    def test_next_fixture_opponent_shown(self):
        ni = _schedule_item(opponent="Burnley", venue="H", played=False,
                            when=fd.WHEN_UPCOMING, days=3)
        rows = hub_rows(_snapshot(next_item=ni))
        next_row = next(r for r in rows if r.label == "Next")
        self.assertIn("Burnley", next_row.value)
        self.assertIn("home", next_row.value)

    def test_competition_name_lookup_used(self):
        ni = _schedule_item(competition_id=5, played=False, when=fd.WHEN_UPCOMING)
        rows = hub_rows(_snapshot(next_item=ni), competition_names={5: "Premier League"})
        comp_row = next(r for r in rows if r.label == "Competition")
        self.assertEqual(comp_row.value, "Premier League")

    def test_competition_fallback_to_scope_label(self):
        ni = _schedule_item(competition_id=99, played=False, when=fd.WHEN_UPCOMING)
        rows = hub_rows(_snapshot(next_item=ni, next_scope_label="Championship"),
                        competition_names={})
        comp_row = next(r for r in rows if r.label == "Competition")
        self.assertEqual(comp_row.value, "Championship")

    def test_no_next_fixture_shows_muted_message(self):
        rows = hub_rows(_snapshot(next_item=None))
        next_row = next(r for r in rows if r.label == "Next")
        self.assertTrue(next_row.muted)

    def test_returns_list_of_hub_rows(self):
        rows = hub_rows(_snapshot())
        self.assertIsInstance(rows, list)
        self.assertTrue(all(isinstance(r, HubRow) for r in rows))


if __name__ == "__main__":
    unittest.main()
