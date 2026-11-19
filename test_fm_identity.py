# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for the identity and schedule contracts in fm_data (notes_10 stage 1), with made-up clubs.

Run:  .venv\\Scripts\\python -m unittest test_fm_identity -v
"""

import dataclasses
import datetime as dt
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import fm_data as fd
from test_fm_data import CLUBS, D, FakeSave, club, fx, info, team, unresolved_away


def dataset(fixtures, *, managed=1, clubs=None, game_date=D(2026, 9, 1)):
    base = info(managed)
    return fd.build_dataset(dataclasses.replace(base, game_date=game_date), fixtures,
                            clubs=clubs if clubs is not None else [club(1, slots=(0, 1)), club(2), club(3), club(4)])


SEASON = [
    fx(D(2026, 8, 8), 1, 2, 2, 1, md=1),
    fx(D(2026, 8, 8), 3, 4, 0, 0, md=1),
    fx(D(2026, 8, 15), 4, 1, 1, 3, md=2),
    fx(D(2026, 8, 15), 2, 3, 0, 0, md=2),
    fx(D(2026, 9, 12), 1, 3, md=3),
    fx(D(2026, 9, 12), 4, 2, md=3),
]


class TeamIdentityTests(unittest.TestCase):
    def test_every_team_in_the_fixtures_records_its_club_and_slot(self):
        ds = dataset(SEASON + [fx(D(2026, 8, 20), 1, 2, 1, 1, comp=102, home_slot=1, md=1)])
        self.assertEqual(ds.teams[team(1)], fd.TeamIdentity(team(1), 1, "Hull City", 0))
        self.assertEqual(ds.teams[team(1, 1)], fd.TeamIdentity(team(1, 1), 1, "Hull City", 1))

    def test_a_team_the_save_cannot_resolve_has_no_club(self):
        ds = dataset([unresolved_away(fx(D(2026, 8, 8), 1, 2, 1, 0, md=1))])
        self.assertEqual(ds.teams[999], fd.TeamIdentity(999, None, None, None))


class FollowedClubTests(unittest.TestCase):
    def setUp(self):
        self.ds = dataset(SEASON + [fx(D(2026, 8, 20), 1, 2, 1, 1, comp=102, home_slot=1, md=1),
                                    unresolved_away(fx(D(2026, 8, 22), 1, 2, comp=102, md=2))])

    def test_the_senior_scope_is_the_first_team_only(self):
        self.assertEqual(fd.followed_team_ids(self.ds, fd.FollowedClub(1)), frozenset({team(1)}))

    def test_the_reserve_scope_is_every_other_team_of_the_club(self):
        self.assertEqual(fd.followed_team_ids(self.ds, fd.FollowedClub(1, fd.SCOPE_RESERVE)),
                         frozenset({team(1, 1)}))

    def test_a_club_the_save_does_not_hold_has_no_teams(self):
        self.assertEqual(fd.followed_team_ids(self.ds, fd.FollowedClub(77)), frozenset())

    def test_an_unresolved_team_belongs_to_no_club(self):
        every = fd.followed_team_ids(self.ds, fd.FollowedClub(1)) | fd.followed_team_ids(
            self.ds, fd.FollowedClub(1, fd.SCOPE_RESERVE))
        self.assertNotIn(999, every)

    def test_the_default_is_the_managed_clubs_senior_side(self):
        self.assertEqual(fd.default_followed_club(self.ds), fd.FollowedClub(1, fd.SCOPE_SENIOR, "Hull City"))

    def test_an_observer_save_follows_nobody_by_default(self):
        observer = dataset(SEASON, managed=None)
        self.assertIsNone(fd.default_followed_club(observer))

    def test_a_managed_club_with_no_fixtures_is_not_followed(self):
        self.assertIsNone(fd.default_followed_club(dataset(SEASON, managed=5)))


class FixtureRefTests(unittest.TestCase):
    def test_a_reference_names_the_competition_season_teams_and_date(self):
        ref = fd.fixture_refs([SEASON[0]])[0]
        self.assertEqual(ref, fd.FixtureRef(101, 2026, team(1), team(2), D(2026, 8, 8), 0))

    def test_a_reference_survives_a_different_order_of_the_list(self):
        refs = fd.fixture_refs(SEASON)
        self.assertEqual(list(reversed(refs)), fd.fixture_refs(list(reversed(SEASON))))

    def test_two_matches_with_one_key_get_different_ordinals_in_date_and_time_order(self):
        first = fx(D(2026, 8, 8), 1, 2, 1, 0, md=1, ko=(12, 0))
        replay = fx(D(2026, 8, 8), 1, 2, 2, 2, md=1, ko=(19, 45))
        refs = fd.fixture_refs([replay, first])
        self.assertEqual([r.ordinal for r in refs], [1, 0])

    def test_a_reference_resolves_back_to_its_fixture(self):
        ds = dataset(SEASON)
        for f, ref in zip(ds.fixtures[101], fd.fixture_refs(ds.fixtures[101])):
            self.assertIs(fd.resolve_fixture(ds, ref), f)

    def test_a_reference_the_save_does_not_hold_resolves_to_none(self):
        ds = dataset(SEASON)
        self.assertIsNone(fd.resolve_fixture(ds, fd.FixtureRef(101, 2026, team(1), team(2), D(2030, 1, 1), 0)))
        self.assertIsNone(fd.resolve_fixture(ds, fd.FixtureRef(999, 2026, team(1), team(2), D(2026, 8, 8), 0)))
        self.assertIsNone(fd.resolve_fixture(ds, fd.FixtureRef(101, 2026, team(1), team(2), D(2026, 8, 8), 5)))

    def test_an_undated_fixture_still_has_a_reference(self):
        undated = fx(None, 1, 2, md=9)
        self.assertEqual(fd.fixture_refs([undated])[0].date, None)


def played_scores(rows):
    """{team uid: (played, points)} from standings rows, for brevity."""
    return {r.team_id // 100: (r.played, r.points) for r in rows}


class CutoffTests(unittest.TestCase):
    def target(self, day=D(2026, 8, 8), ko=(15, 0)):
        return fx(day, 1, 3, md=3, ko=ko)

    def before(self, others, target=None):
        target = target or self.target()
        return [(f.home_club_uid, f.away_club_uid) for f in fd.played_before(others + [target], target)]

    def test_a_match_on_an_earlier_day_counts_and_the_match_itself_does_not(self):
        earlier = fx(D(2026, 8, 7), 2, 4, 1, 0, md=2)
        self.assertEqual(self.before([earlier]), [(2, 4)])

    def test_a_later_match_never_counts(self):
        later = fx(D(2026, 8, 9), 2, 4, 1, 0, md=4)
        self.assertEqual(self.before([later]), [])

    def test_a_match_that_kicked_off_two_hours_or_more_earlier_that_day_counts(self):
        self.assertEqual(self.before([fx(D(2026, 8, 8), 2, 4, 1, 0, md=3, ko=(13, 0))]), [(2, 4)])

    def test_a_match_that_may_still_have_been_on_is_left_out(self):
        self.assertEqual(self.before([fx(D(2026, 8, 8), 2, 4, 1, 0, md=3, ko=(14, 0))]), [])

    def test_a_match_at_the_same_kick_off_is_left_out(self):
        self.assertEqual(self.before([fx(D(2026, 8, 8), 2, 4, 1, 0, md=3, ko=(15, 0))]), [])

    def test_a_same_day_match_with_no_time_cannot_be_shown_to_be_earlier(self):
        self.assertEqual(self.before([fx(D(2026, 8, 8), 2, 4, 1, 0, md=3, ko=None)]), [])

    def test_a_match_with_no_kick_off_time_counts_only_what_was_played_on_earlier_days(self):
        target = self.target(ko=None)
        same_day = fx(D(2026, 8, 8), 2, 4, 1, 0, md=3, ko=(10, 0))
        eve = fx(D(2026, 8, 7), 2, 4, 1, 0, md=2, ko=(20, 0))
        self.assertEqual(self.before([same_day, eve], target), [(2, 4)])

    def test_an_unplayed_or_undated_match_never_counts(self):
        unplayed = fx(D(2026, 8, 1), 2, 4, md=1)
        undated = fx(None, 2, 4, 1, 0, md=1)
        self.assertEqual(self.before([unplayed, undated]), [])

    def test_a_match_with_no_date_has_nothing_before_it(self):
        target = fx(None, 1, 3, md=3)
        self.assertEqual(self.before([fx(D(2026, 8, 1), 2, 4, 1, 0, md=1)], target), [])

    def test_the_cutoff_says_when_it_is_a_prior_day_snapshot(self):
        exact = fd.cutoff_for(self.target())
        prior = fd.cutoff_for(self.target(ko=None))
        self.assertTrue(exact.exact)
        self.assertFalse(prior.exact)
        self.assertIn("kick-off", exact.label())
        self.assertIn("Prior-day snapshot", prior.label())
        self.assertIn("7 Aug", prior.label())
        self.assertIn("Date not set", fd.cutoff_for(fx(None, 1, 3, md=3)).label())


class StandingsBeforeTests(unittest.TestCase):
    LEAGUE = [
        fx(D(2026, 8, 1), 1, 2, 3, 0, md=1),
        fx(D(2026, 8, 1), 3, 4, 1, 1, md=1),
        fx(D(2026, 8, 8), 1, 3, 2, 0, md=2),           # the match the table is wanted before
        fx(D(2026, 8, 8), 2, 4, 5, 0, md=2, ko=(12, 0)),
        fx(D(2026, 8, 15), 4, 1, 1, 1, md=3),
    ]

    def rows(self, target_index=2, ko=True):
        target = self.LEAGUE[target_index]
        if not ko:
            target = dataclasses.replace(target, kick_off_time=None)
        fixtures = [target if f is self.LEAGUE[target_index] else f for f in self.LEAGUE]
        labels = fd.team_labels(fixtures)
        return fd.standings_before(fixtures, labels, target), target, fixtures, labels

    def test_the_table_leaves_out_the_selected_match_and_every_later_one(self):
        rows, *_ = self.rows()
        self.assertEqual(played_scores(rows)[1], (1, 3))        # Hull's 2-0 over Sheffield United is not in it
        self.assertEqual(played_scores(rows)[3], (1, 1))
        self.assertEqual(played_scores(rows)[4], (2, 1))        # the draw at Derby on 15 August is not in it

    def test_an_earlier_kick_off_that_day_is_in_the_table_when_it_was_over(self):
        rows, *_ = self.rows()
        self.assertEqual(played_scores(rows)[2], (2, 3))        # Leeds' 5-0 at 12:00 is in

    def test_without_a_kick_off_time_the_snapshot_is_the_end_of_the_day_before(self):
        rows, *_ = self.rows(ko=False)
        self.assertEqual(played_scores(rows)[2], (1, 0))        # the 12:00 match that day is not counted

    def test_a_team_in_the_table_has_a_rank_before_the_match(self):
        _, target, fixtures, labels = self.rows()
        rank = fd.rank_before(fixtures, labels, target, team(1))
        self.assertEqual((rank.position, rank.of), (1, 4))
        self.assertTrue(rank.cutoff.exact)

    def test_a_snapshot_without_a_kick_off_time_says_so_in_its_label(self):
        _, target, fixtures, labels = self.rows(ko=False)
        self.assertIn("Prior-day snapshot", fd.rank_before(fixtures, labels, target, team(1)).label())

    def test_matches_counted_with_no_recoverable_score_are_reported(self):
        _, target, fixtures, labels = self.rows()
        unscored = [dataclasses.replace(f, home_goals=None, away_goals=None) if f is self.LEAGUE[1] else f
                    for f in fixtures]
        self.assertEqual(fd.rank_before(unscored, labels, target, team(1)).unscored, 1)

    def test_a_team_outside_the_competition_has_no_rank(self):
        _, target, fixtures, labels = self.rows()
        self.assertIsNone(fd.rank_before(fixtures, labels, target, team(5)))


class FormBeforeTests(unittest.TestCase):
    SEASON = fd_season = [
        fx(D(2026, 8, 1), 1, 2, 1, 0, md=1),
        fx(D(2026, 8, 8), 3, 1, 2, 2, md=2),
        fx(D(2026, 8, 15), 1, 4, 0, 3, md=3),
        fx(D(2026, 8, 22), 1, 2, 4, 0, md=4),
        fx(D(2026, 8, 29), 3, 1, 0, 1, md=5),
    ]

    def test_form_counts_only_what_came_before_the_selected_match(self):
        target = self.SEASON[2]
        labels = fd.team_labels(self.SEASON)
        form = fd.form_before(self.SEASON, [team(1)], target, labels, scope=fd.FORM_LEAGUE)
        self.assertEqual(form.strip.letters, "WD")

    def test_the_form_names_its_scope_and_its_cutoff(self):
        target = self.SEASON[2]
        labels = fd.team_labels(self.SEASON)
        league = fd.form_before(self.SEASON, [team(1)], target, labels, scope=fd.FORM_LEAGUE)
        everything = fd.form_before(self.SEASON, [team(1)], target, labels, scope=fd.FORM_ALL)
        self.assertEqual(league.scope_label, "league only")
        self.assertEqual(everything.scope_label, "all competitions")
        self.assertTrue(league.cutoff.exact)

    def test_the_first_match_of_the_season_has_no_form_before_it(self):
        labels = fd.team_labels(self.SEASON)
        form = fd.form_before(self.SEASON, [team(1)], self.SEASON[0], labels, scope=fd.FORM_ALL)
        self.assertEqual(form.strip.letters, "")

    def test_only_five_matches_are_shown_but_every_earlier_one_is_considered(self):
        many = [fx(D(2026, 8, 1) + dt.timedelta(days=7 * i), 1, 2, 1, 0, md=i + 1) for i in range(8)]
        target = fx(D(2026, 10, 1), 1, 2, md=9)
        form = fd.form_before(many + [target], [team(1)], target, fd.team_labels(many), scope=fd.FORM_ALL)
        self.assertEqual(form.strip.letters, "WWWWW")

    def test_a_match_with_no_recoverable_score_is_a_question_mark(self):
        unscored = dataclasses.replace(self.SEASON[1], home_goals=None, away_goals=None, played=True)
        fixtures = [self.SEASON[0], unscored, self.SEASON[2]]
        form = fd.form_before(fixtures, [team(1)], fixtures[2], fd.team_labels(fixtures), scope=fd.FORM_ALL)
        self.assertEqual(form.strip.letters, "W?")


class GroundSave(FakeSave):
    """A FakeSave that also holds a stadium table (or fails to read it)."""

    def __init__(self, fixtures, grounds=(), grounds_error=None, **kwargs):
        super().__init__(fixtures, **kwargs)
        self._grounds, self._grounds_error = grounds, grounds_error

    def stadiums(self):
        self.read.append("stadiums")
        if self._grounds_error:
            raise self._grounds_error
        return iter(self._grounds)


def stadium(uid, name=None, total=30000, capacity=999):
    return NS(uid=uid, name=name, total_capacity=total, capacity=capacity)


class GroundReadTests(unittest.TestCase):
    def load(self, save, **kwargs):
        with mock.patch.object(fd.fmsave, "open", return_value=save):
            return fd.load_dataset("career.fm", **kwargs)

    def test_the_total_capacity_is_kept_never_the_additional_capacity_figure(self):
        final = self.load(GroundSave(SEASON, [stadium(7, "Riverside", total=31000, capacity=500)]))
        self.assertEqual(final.grounds[7], fd.Ground(7, "Riverside", 31000))

    def test_a_missing_or_zero_capacity_is_unknown_not_zero(self):
        final = self.load(GroundSave(SEASON, [stadium(7, total=0), stadium(8, total=None)]))
        self.assertEqual((final.grounds[7].total_capacity, final.grounds[8].total_capacity), (None, None))

    def test_the_save_is_ready_before_the_grounds_are_read(self):
        save = GroundSave(SEASON, [stadium(7)])
        seen = []
        self.load(save, ready=lambda ds: seen.append((ds.grounds, list(save.read))))
        self.assertEqual(seen, [(None, ["fixtures"])])

    def test_a_failure_to_read_the_grounds_keeps_everything_else_and_says_so(self):
        final = self.load(GroundSave(SEASON, grounds_error=RuntimeError("no stadium table")))
        self.assertIsNone(final.grounds)
        self.assertIn("no stadium table", final.ground_failure)
        self.assertEqual(final.fixture_total, len(SEASON))
        self.assertTrue(any(w.startswith("Grounds could not be read") for w in final.info.warnings))

    def test_a_save_reader_without_a_stadium_table_is_a_failure_to_read_it(self):
        final = self.load(FakeSave(SEASON))
        self.assertIsNone(final.grounds)
        self.assertTrue(final.ground_failure)


class ManagedSave(FakeSave):
    def __init__(self, fixtures, manager_name):
        super().__init__(fixtures)
        self._manager_name = manager_name

    def managed_clubs(self):
        return [NS(club_uid=1, club_name="Hull City", manager_name=self._manager_name)]


class ManagerNameTests(unittest.TestCase):
    def load(self, save):
        with mock.patch.object(fd.fmsave, "open", return_value=save):
            return fd.load_dataset("career.fm")

    def test_the_managed_clubs_manager_name_is_kept_when_the_save_gives_it(self):
        self.assertEqual(self.load(ManagedSave(SEASON, "A. Manager")).info.managed_manager_name, "A. Manager")

    def test_a_missing_manager_name_stays_none(self):
        self.assertIsNone(self.load(ManagedSave(SEASON, None)).info.managed_manager_name)

    def test_an_observer_save_has_no_manager_name(self):
        self.assertIsNone(self.load(FakeSave(SEASON)).info.managed_manager_name)


def with_grounds(fixtures, grounds=None, failure="", stats_done=True):
    ds = dataset(fixtures)
    if stats_done:
        ds = fd.with_expected_goals(ds, [])
    return fd.with_grounds(ds, grounds, failure) if grounds is not None or failure else ds


class VenueTests(unittest.TestCase):
    def fixture(self, **changes):
        return dataclasses.replace(SEASON[0], **changes)

    def test_a_ground_the_fixture_names_and_the_table_holds_gives_a_capacity(self):
        ds = with_grounds([self.fixture(stadium_uid=7)], [stadium(7, "Riverside", 31000)])
        venue = fd.venue_for(ds, ds.fixtures[101][0])
        self.assertEqual((venue.stadium_uid, venue.name, venue.total_capacity, venue.capacity_state),
                         (7, "Riverside", 31000, fd.STATE_KNOWN))

    def test_a_fixture_with_no_ground_is_unrecorded_and_nothing_is_guessed_from_the_home_club(self):
        ds = with_grounds([self.fixture()], [stadium(7, "Riverside", 31000)])
        venue = fd.venue_for(ds, ds.fixtures[101][0])
        self.assertEqual((venue.stadium_uid, venue.name, venue.total_capacity, venue.capacity_state),
                         (None, None, None, fd.STATE_UNRECORDED))

    def test_the_fixtures_own_name_wins_over_the_tables(self):
        ds = with_grounds([self.fixture(stadium_uid=7, stadium_name="Old Ground")], [stadium(7, "Riverside")])
        self.assertEqual(fd.venue_for(ds, ds.fixtures[101][0]).name, "Old Ground")

    def test_a_ground_without_a_name_stays_unnamed(self):
        ds = with_grounds([self.fixture(stadium_uid=7)], [stadium(7, None, 31000)])
        venue = fd.venue_for(ds, ds.fixtures[101][0])
        self.assertIsNone(venue.name)
        self.assertIn("Ground name not recorded", venue.lines())

    def test_a_ground_the_table_does_not_hold_has_an_unavailable_capacity(self):
        ds = with_grounds([self.fixture(stadium_uid=99)], [stadium(7)])
        self.assertEqual(fd.venue_for(ds, ds.fixtures[101][0]).capacity_state, fd.STATE_UNAVAILABLE)

    def test_a_ground_with_an_unknown_capacity_is_unavailable_not_zero(self):
        ds = with_grounds([self.fixture(stadium_uid=7)], [stadium(7, total=0)])
        venue = fd.venue_for(ds, ds.fixtures[101][0])
        self.assertEqual((venue.total_capacity, venue.capacity_state), (None, fd.STATE_UNAVAILABLE))

    def test_while_the_grounds_are_still_being_read_the_capacity_is_pending(self):
        ds = with_grounds([self.fixture(stadium_uid=7)], stats_done=False)
        self.assertEqual(fd.venue_for(ds, ds.fixtures[101][0]).capacity_state, fd.STATE_PENDING)

    def test_after_a_failed_read_the_capacity_is_unavailable(self):
        ds = with_grounds([self.fixture(stadium_uid=7)], failure="boom")
        self.assertEqual(fd.venue_for(ds, ds.fixtures[101][0]).capacity_state, fd.STATE_UNAVAILABLE)

    def test_the_neutral_flag_keeps_true_false_and_unknown_apart(self):
        ds = dataset([self.fixture(is_neutral_venue=v) for v in (True, False, None)])
        neutral = [fd.venue_for(ds, f).neutral for f in ds.fixtures[101]]
        self.assertEqual(neutral, [True, False, None])

    def test_the_lines_say_what_is_known_and_never_mention_attendance(self):
        ds = with_grounds([self.fixture(stadium_uid=7, is_neutral_venue=True)], [stadium(7, "Riverside", 31000)])
        lines = fd.venue_for(ds, ds.fixtures[101][0]).lines()
        self.assertEqual(lines, ("Neutral ground", "Riverside", "Capacity 31,000"))
        unknown = fd.venue_for(dataset([self.fixture(is_neutral_venue=None)]), self.fixture(is_neutral_venue=None))
        self.assertIn("Neutral ground: unknown", unknown.lines())
        self.assertFalse(any("ttendance" in line for line in lines + unknown.lines()))


if __name__ == "__main__":
    unittest.main()
