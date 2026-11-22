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


def _item(opponent="Eastholm Athletic", venue="H", played=False, date=dt.date(2099, 8, 29),
          when=fd.WHEN_UPCOMING, days=4):
    f = MagicMock()
    f.date, f.played = date, played
    i = MagicMock(spec=fd.ScheduleItem)
    i.opponent, i.venue, i.fixture, i.played, i.when, i.days = opponent, venue, f, played, when, days
    i.outcome = "W" if played else None
    i.score = "2-1" if played else ""
    i.competition_id = 101
    return i


def _table(position=1, of=4, points=6, played=2, unscored=0):
    return fd.HubTable(position, of, points, played, unscored, ())


def _step(title="Matchday 4", table=None, form="WD", fixture=None, cutoff=True, previous=None):
    cut = fd.Cutoff(dt.date(2099, 8, 29), dt.time(15, 0)) if cutoff else None
    steps = tuple(MagicMock(outcome=c) for c in form)
    strip = MagicMock(spec=fd.FormStrip)
    strip.letters = form
    strip.steps = steps
    return fd.HubStep(title, dt.date(2099, 8, 29), cut, fixture, table, strip, previous)


class StepRowsTests(unittest.TestCase):
    """The Hub's rows at one step of the matchday stepper (made-up clubs and dates)."""

    def rows(self, step, **kw):
        return {r.label: r for r in hub_rows(_snapshot(followed=_followed("Northbridge Rovers"), next_scope_label="Invented League"), step=step, **kw)}

    def test_the_position_is_the_calculated_place_at_that_step(self):
        row = self.rows(_step(table=_table(2, 4, 6, 2)))["Position"]
        self.assertEqual(row.value, "2nd of 4 · 6 pts from 2 played (calculated from the results)")

    def test_matches_with_no_score_are_said_to_be_left_out(self):
        row = self.rows(_step(table=_table(2, 4, 6, 3, unscored=1)))["Position"]
        self.assertIn("1 match played with no score left out", row.value)

    def test_before_any_league_match_there_is_no_place_to_give(self):
        row = self.rows(_step(table=_table(1, 4, 0, 0)))["Position"]
        self.assertEqual((row.value, row.muted), ("No league match played yet", True))

    def test_a_club_with_no_league_match_has_no_league_rank(self):
        row = self.rows(_step(title="Match 1", table=None))["Position"]
        self.assertEqual((row.value, row.muted), ("No league rank: no league match this season", True))

    def test_form_is_the_steps_own_and_names_its_scope(self):
        self.assertEqual(self.rows(_step(form="WDW"))["Form"].value, "WDW (all competitions)")
        empty = self.rows(_step(form=""))["Form"]
        self.assertEqual((empty.value, empty.muted), ("—", True))

    def test_the_next_match_never_shows_a_result_even_when_it_has_been_played_since(self):
        played = _item(played=True, when=fd.WHEN_PLAYED, days=None)
        row = self.rows(_step(fixture=played))["Next league match"]
        self.assertEqual(row.value, "Eastholm Athletic (home) · 29 Aug 2099")
        self.assertNotIn("2-1", " ".join(r.value for r in hub_rows(_snapshot(followed=_followed("Northbridge Rovers")), step=_step(fixture=played))))

    def test_a_club_with_no_league_steps_to_its_next_match(self):
        self.assertIn("Next match", self.rows(_step(title="Match 2", fixture=_item()), league=False))

    def test_the_end_of_the_season_has_no_next_match(self):
        row = self.rows(_step(title=fd.END_OF_SEASON, fixture=None, cutoff=False))["Next league match"]
        self.assertEqual((row.value, row.muted), ("Season complete", True))

    def test_the_snapshot_row_names_the_matchday_and_its_date(self):
        self.assertEqual(self.rows(_step())["Snapshot"].value, "Matchday 4 · Before kick-off, Sat 29 Aug 15:00")

    def test_today_also_gives_the_next_match_in_any_competition_with_its_countdown(self):
        cup = _item(opponent="Kingsbay City", venue="A", date=dt.date(2099, 8, 27), days=2)
        rows = hub_rows(_snapshot(followed=_followed("Northbridge Rovers"), next_item=cup, next_scope_label="Invented Cup"), step=_step(fixture=_item()), today=True)
        labels = [r.label for r in rows]
        self.assertIn("Next (any competition)", labels)
        self.assertIn("In 2 days", [r.value for r in rows])

    def test_away_from_today_there_is_no_countdown(self):
        rows = hub_rows(_snapshot(followed=_followed("Northbridge Rovers"), next_item=_item(), next_scope_label="Invented League"), step=_step(fixture=_item()), today=False)
        self.assertNotIn("Next (any competition)", [r.label for r in rows])
        self.assertFalse(any(r.value.startswith("In ") for r in rows))


def _meeting(score="2-1", date=dt.date(2099, 8, 8), competition_id=101):
    f = MagicMock()
    f.date, f.competition_id = date, competition_id
    return fd.PreviousMeeting(f, score)


class PreviousMeetingRowTests(unittest.TestCase):
    """The Hub's "Previous meeting" row under the upcoming opponent (made-up clubs and dates)."""

    NAMES = {101: "Invented League", 102: "Invented Cup"}

    def rows(self, step):
        snapshot = _snapshot(followed=_followed("Northbridge Rovers"), next_scope_label="Invented League")
        return hub_rows(snapshot, self.NAMES, step=step)

    def test_it_gives_the_date_competition_and_score_of_the_earlier_meeting(self):
        rows = self.rows(_step(fixture=_item(), previous=_meeting("2-1", competition_id=102)))
        row = next(r for r in rows if r.label == "Previous meeting")
        self.assertEqual(row.value, "8 Aug 2099 ┬À Invented Cup ┬À Northbridge Rovers 2-1 Eastholm Athletic")

    def test_it_sits_directly_beneath_the_upcoming_opponent(self):
        labels = [r.label for r in self.rows(_step(fixture=_item(), previous=_meeting()))]
        self.assertEqual(labels.index("Previous meeting"), labels.index("Next league match") + 1)

    def test_a_meeting_with_no_recoverable_score_says_so_never_a_zero(self):
        row = next(r for r in self.rows(_step(fixture=_item(), previous=_meeting(score=None)))
                   if r.label == "Previous meeting")
        self.assertEqual(row.value, "8 Aug 2099 ┬À Invented League ┬À Score unavailable")

    def test_with_no_earlier_meeting_the_row_says_so(self):
        row = next(r for r in self.rows(_step(fixture=_item(), previous=None)) if r.label == "Previous meeting")
        self.assertEqual((row.value, row.muted), ("No earlier meeting found in this save", True))

    def test_the_end_of_the_season_has_no_previous_meeting_row(self):
        step = _step(title=fd.END_OF_SEASON, fixture=None, cutoff=False)
        self.assertNotIn("Previous meeting", [r.label for r in self.rows(step)])


if __name__ == "__main__":
    unittest.main()
