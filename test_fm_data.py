# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for fm_data, using fmsave's real Fixture record with made-up matches.

Run:  .venv\\Scripts\\python -m unittest -v
"""

import dataclasses
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

from fmsave import CodedValue, CompetitionRound, Fixture, TeamMatchStats

import fm_data as fd

CLUBS = {
    1: ("Hull City", "Hull"),
    2: ("Leeds United", "Leeds"),
    3: ("Sheffield United", "Sheff Utd"),
    4: ("Derby County", "Derby"),
    5: ("Wrexham", "Wrexham"),
}
D = dt.date


def team(club, slot=0):
    return club * 100 + slot


def fx(day, home, away, hg=None, ag=None, *, played=None, comp=101, season=2026, md=None,
       home_slot=0, away_slot=0, ko=(15, 0), rnd=None):
    """A Fixture between clubs (by number) with the fields fmsave fills in."""
    return Fixture(
        stage_id=comp * 10, competition_id=comp, competition_name=None, round=rnd,
        round_index=None if md is None else md - 1, date=day,
        kick_off_time=dt.time(*ko) if ko else None, season_start_year=season,
        home_team_id=team(home, home_slot), home_club_uid=home, home_club_name=CLUBS[home][0],
        home_club_short_name=CLUBS[home][1], home_team_slot=home_slot,
        away_team_id=team(away, away_slot), away_club_uid=away, away_club_name=CLUBS[away][0],
        away_club_short_name=CLUBS[away][1], away_team_slot=away_slot,
        home_goals=hg, away_goals=ag, played=(hg is not None) if played is None else played,
        is_neutral_venue=False, stadium_uid=None, stadium_name=None, referee_id=None,
        match_rules_template=(), unknown={},
    )


def info(managed_uid=1):
    return fd.ImportInfo(
        path="x.fm", file_name="x.fm", game="FM27", build="27.0.1+1", known_build=False,
        game_date=D(2026, 9, 1), fmsave_version="0", imported_at=dt.datetime(2026, 9, 1),
        seconds=0.0, warnings=(), managed_club_uid=managed_uid,
        managed_club_name=CLUBS.get(managed_uid, ("",))[0],
    )


def club(uid, reputation=1000, slots=(0,)):
    return NS(uid=uid, reputation=reputation,
              teams=tuple(NS(team_id=team(uid, s), slot=s, is_affiliate=False) for s in slots))


def row(club_no, position, played=0, won=0, drawn=0, lost=0, gf=0, ga=0, points=0):
    return NS(position=position, team_id=team(club_no), club_name=CLUBS[club_no][0], played=played,
              won=won, drawn=drawn, lost=lost, goals_for=gf, goals_against=ga, points=points)


def unresolved_away(f):
    """The same match against a team the save cannot resolve: no club, no slot."""
    return dataclasses.replace(f, away_team_id=999, away_club_uid=None, away_club_name=None,
                               away_club_short_name=None, away_team_slot=None)


def league_season(comp, first_day, matchdays=12, pairs=((1, 2), (3, 4))):
    """Every pair meets on each matchday, a week apart, nothing played yet."""
    return [fx(first_day + dt.timedelta(weeks=md), h, a, comp=comp, md=md + 1)
            for md in range(matchdays) for h, a in pairs]


def rules_block(promotion, playoff, relegation, *, comp=None, first_day=None, rounds=12, numbered=False):
    """A competition-rules block as fmsave reads it. Before a season starts the save stores it with
    no competition and, often, with unnumbered rounds (fmsave reports those as 256)."""
    days = [first_day + dt.timedelta(weeks=i) for i in range(rounds)] if first_day else []
    return NS(competition_id=comp, promotion_places=promotion, playoff_places=playoff,
              relegation_places=relegation, fixtures_per_club=rounds,
              rounds=tuple(NS(number=i + 1 if numbered else 256, date=day) for i, day in enumerate(days)))


LEAGUE = [
    fx(D(2026, 8, 8), 1, 2, 2, 1, md=1),
    fx(D(2026, 8, 8), 3, 4, 0, 0, md=1),
    fx(D(2026, 8, 15), 2, 3, None, None, played=True, md=2),   # played, score not recovered
    fx(D(2026, 8, 15), 4, 1, 1, 3, md=2),
    fx(D(2026, 9, 26), 1, 3, md=3),                            # still to play
    fx(D(2026, 8, 22), 4, 2, md=3),                            # still to play
]

HULL_SCORES = {"W": (1, 0), "D": (1, 1), "L": (0, 1), "?": (None, None)}


def hull_season(letters, *, start=D(2026, 8, 1)):
    """Hull City's played matches, a week apart, at home first and then alternately away, against
    Leeds, Sheffield United, Derby and Wrexham in turn. W is won 1-0, D drawn 1-1, L lost 0-1, and
    ? played with no recoverable score."""
    fixtures = []
    for i, letter in enumerate(letters):
        opponent = (2, 3, 4, 5)[i % 4]
        hull, other = HULL_SCORES[letter]
        if i % 2 == 0:
            fixtures.append(fx(start + dt.timedelta(weeks=i), 1, opponent, hull, other, played=True, md=i + 1))
        else:
            fixtures.append(fx(start + dt.timedelta(weeks=i), opponent, 1, other, hull, played=True, md=i + 1))
    return fixtures


def hull_steps(letters):
    fixtures = hull_season(letters)
    return fd.team_steps(fixtures, team(1), fd.team_labels(fixtures))


class SeasonTests(unittest.TestCase):
    def test_labels_for_split_and_calendar_year_seasons(self):
        self.assertEqual(fd.season_label(2026, [fx(D(2026, 8, 8), 1, 2), fx(D(2027, 5, 1), 2, 1)]), "2026/27")
        self.assertEqual(fd.season_label(2026, [fx(D(2026, 3, 1), 1, 2), fx(D(2026, 11, 1), 2, 1)]), "2026")

    def test_friendly_without_a_stored_season_uses_a_july_boundary(self):
        self.assertEqual(fd.season_key(fx(D(2027, 1, 10), 1, 2, season=None)), 2026)
        self.assertEqual(fd.season_key(fx(D(2026, 7, 10), 1, 2, season=None)), 2026)

    def test_default_season_is_latest_played_else_first_to_come(self):
        ds = fd.build_dataset(info(), LEAGUE + [fx(D(2027, 8, 7), 1, 2, season=2027, md=1)])
        self.assertEqual(fd.default_season(ds, 101), 2026)
        unplayed = fd.build_dataset(info(), [fx(D(2026, 8, 8), 1, 2, md=1), fx(D(2027, 8, 7), 1, 2, season=2027, md=1)])
        self.assertEqual(fd.default_season(unplayed, 101), 2026)


class CoverageTests(unittest.TestCase):
    def test_counts_and_wording(self):
        cov = fd.coverage(LEAGUE)
        self.assertEqual((cov.fixtures, cov.played, cov.scored, cov.unavailable, cov.to_play), (6, 4, 3, 1, 2))
        self.assertIn("1 played with no recoverable score", cov.describe())

    def test_played_without_score_is_never_shown_as_goalless(self):
        f = LEAGUE[2]
        self.assertEqual(fd.result_kind(f), fd.UNAVAILABLE)
        self.assertEqual(fd.score_text(f), "n/a")
        self.assertIsNone(fd.outcome_for(f, team(2)))


class LabelTests(unittest.TestCase):
    def test_second_team_of_the_same_club_is_told_apart(self):
        labels = fd.team_labels([fx(D(2026, 7, 1), 1, 1, away_slot=1), fx(D(2026, 7, 2), 2, 1)])
        self.assertEqual(labels[team(1)], "Hull City")
        self.assertEqual(labels[team(1, 1)], "Hull City (team 2)")
        self.assertEqual(labels[team(2)], "Leeds United")

    def test_youth_league_shows_plain_names(self):
        labels = fd.team_labels([fx(D(2026, 8, 1), 1, 2, home_slot=1, away_slot=1)])
        self.assertEqual(labels[team(1, 1)], "Hull City")

    def test_short_labels(self):
        self.assertEqual(fd.team_labels(LEAGUE, short=True)[team(1)], "Hull")

    def test_club_names_cover_reserve_sides_and_skip_unresolved_teams(self):
        names = fd.team_club_names([fx(D(2026, 7, 1), 1, 1, away_slot=1),
                                    unresolved_away(fx(D(2026, 7, 2), 2, 3))])
        self.assertEqual(names, {team(1): "Hull City", team(1, 1): "Hull City", team(2): "Leeds United"})


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.labels = fd.team_labels(LEAGUE)

    def headings(self, rows):
        return [r.heading.split("   ·")[0] for r in rows if r.is_heading]

    def test_weeks_start_on_monday_and_follow_the_calendar(self):
        rows = fd.timeline(LEAGUE, self.labels, group_by=fd.GROUP_BY_WEEK)
        self.assertEqual(self.headings(rows), [
            "Week of Monday 3 August 2026", "Week of Monday 10 August 2026",
            "Week of Monday 17 August 2026", "Week of Monday 21 September 2026"])

    def test_postponed_match_sits_on_its_date_but_keeps_its_matchday(self):
        by_week = fd.timeline(LEAGUE, self.labels, group_by=fd.GROUP_BY_WEEK)
        late = [r for r in by_week if r.home == "Hull City" and r.away == "Sheffield United"][0]
        self.assertEqual((late.date, late.round), ("Sat 26 Sep", "Md 3"))
        by_matchday = fd.timeline(LEAGUE, self.labels, group_by=fd.GROUP_BY_MATCHDAY)
        self.assertEqual(self.headings(by_matchday), ["Matchday 1", "Matchday 2", "Matchday 3"])
        md3 = by_matchday[by_matchday.index(next(r for r in by_matchday if r.heading.startswith("Matchday 3"))) + 1:]
        self.assertEqual([r.home for r in md3], ["Derby County", "Hull City"])

    def test_focus_team_gets_results_and_running_points(self):
        rows = [r for r in fd.timeline(LEAGUE, self.labels, focus_team=team(1)) if not r.is_heading]
        self.assertEqual([(r.result, r.points) for r in rows], [("W", "3"), ("W", "6"), ("", "")])

    def test_running_points_after_a_missing_score_are_marked_incomplete(self):
        rows = [r for r in fd.timeline(LEAGUE, self.labels, focus_team=team(2)) if not r.is_heading]
        self.assertEqual([(r.result, r.points) for r in rows], [("L", "0"), ("?", "0*"), ("", "")])

    def test_cup_round_headings(self):
        final = fx(D(2027, 5, 20), 1, 2, 1, 0, comp=99, rnd=CodedValue(CompetitionRound.FINAL, 19))
        odd = fx(D(2026, 9, 1), 3, 4, 2, 2, comp=99, rnd=CodedValue(CompetitionRound.UNKNOWN, 5))
        rows = fd.timeline([odd, final], fd.team_labels([odd, final]), group_by=fd.GROUP_BY_MATCHDAY)
        self.assertEqual(self.headings(rows), ["Round (code 5)", "Final"])
        self.assertEqual(fd.round_text(final), "Final")


class GridTests(unittest.TestCase):
    def test_every_meeting_is_kept_and_away_only_teams_get_a_row(self):
        fixtures = [
            fx(D(2026, 8, 8), 1, 2, 2, 1),
            fx(D(2026, 12, 8), 1, 2, 1, 1),          # second meeting at the same ground
            fx(D(2026, 8, 15), 2, 1, None, None, played=True),
            fx(D(2027, 2, 13), 3, 1),                # still to play
            fx(D(2026, 9, 1), 1, 5, 0, 1),           # Wrexham only ever plays away
        ]
        labels, short = fd.team_labels(fixtures), fd.team_labels(fixtures, short=True)
        grid = fd.fixture_grid(fixtures, labels, short)
        self.assertEqual(grid.row_labels, ("Hull City", "Leeds United", "Sheffield United", "Wrexham"))
        self.assertEqual(grid.column_labels, ("Hull", "Leeds", "Sheff Utd", "Wrexham"))
        cell = lambda h, a: grid.cells[grid.team_ids.index(team(h))][grid.team_ids.index(team(a))]
        self.assertEqual((cell(1, 2).text, cell(1, 2).kind), ("2-1 / 1-1", fd.MIXED))
        self.assertEqual((cell(2, 1).text, cell(2, 1).kind), ("n/a", fd.UNAVAILABLE))
        self.assertEqual((cell(3, 1).text, cell(3, 1).kind), ("13 Feb", fd.SCHEDULED))
        self.assertEqual((cell(1, 5).text, cell(1, 5).kind), ("0-1", fd.AWAY_WIN))
        self.assertEqual(cell(1, 1).kind, "self")
        self.assertEqual(cell(5, 1).text, "")

    def test_too_many_teams_gives_no_grid(self):
        self.assertIsNone(fd.fixture_grid(LEAGUE, {}, {}, max_teams=3))


class TableTests(unittest.TestCase):
    def test_calculated_table_ignores_matches_without_a_score(self):
        ds = fd.build_dataset(info(), LEAGUE)
        result = fd.standings(ds, 101, 2026, fd.season_fixtures(ds, 101, 2026), fd.team_labels(LEAGUE))
        self.assertFalse(result.stored)
        self.assertIn("incomplete", result.note)
        rows = {r.team: r for r in result.groups[0][1]}
        self.assertEqual(rows["Hull City"].position, 1)
        self.assertEqual((rows["Hull City"].played, rows["Hull City"].points), (2, 6))
        self.assertEqual(rows["Hull City"].form, "WW")
        self.assertEqual(rows["Leeds United"].played, 1)       # the unscored match is left out
        self.assertEqual(rows["Sheffield United"].form, "D")

    def test_competition_with_nothing_played_lists_every_team_on_zero(self):
        fixtures = [fx(D(2026, 8, 8), 1, 2, md=1), fx(D(2026, 8, 8), 3, 4, md=1), fx(D(2026, 8, 15), 5, 1, md=2)]
        ds = fd.build_dataset(info(), fixtures)
        result = fd.standings(ds, 101, 2026, fixtures, fd.team_labels(fixtures))
        self.assertEqual(len(result.groups[0][1]), 5)
        self.assertTrue(all(r.played == 0 and r.points == 0 for r in result.groups[0][1]))

    def test_stored_table_is_used_for_the_latest_played_season_only(self):
        stored = NS(competition_id=101, rows=(row(1, 1, 2, 2, 0, 0, 5, 2, 9), row(4, 2), row(2, 3), row(3, 4)))
        ds = fd.build_dataset(info(), LEAGUE + [fx(D(2027, 8, 7), 1, 2, season=2027, md=1)], tables=[stored])
        labels = fd.team_labels(LEAGUE)
        current = fd.standings(ds, 101, 2026, fd.season_fixtures(ds, 101, 2026), labels)
        self.assertTrue(current.stored)
        self.assertEqual(current.groups[0][1][0].points, 9)     # the game's number, deductions and all
        self.assertEqual(current.groups[0][1][0].form, "WW")
        next_season = fd.standings(ds, 101, 2027, fd.season_fixtures(ds, 101, 2027), labels)
        self.assertFalse(next_season.stored)

    def test_stored_table_with_unknown_clubs_is_not_trusted(self):
        stored = NS(competition_id=101, rows=(row(1, 1), row(5, 2)))   # Wrexham is not in this league
        ds = fd.build_dataset(info(), LEAGUE, tables=[stored])
        self.assertFalse(fd.standings(ds, 101, 2026, fd.season_fixtures(ds, 101, 2026), {}).stored)

    def test_zone_for_position(self):
        self.assertEqual(fd.zone_for_position(1, 20), fd.ZONE_UCL)
        self.assertEqual(fd.zone_for_position(4, 20), fd.ZONE_UCL)
        self.assertEqual(fd.zone_for_position(5, 20), fd.ZONE_EUROPA)
        self.assertEqual(fd.zone_for_position(17, 20), fd.ZONE_NONE)
        self.assertEqual(fd.zone_for_position(18, 20), fd.ZONE_RELEGATION)

        self.assertEqual(fd.zone_for_position(1, 24), fd.ZONE_PROMOTION)
        self.assertEqual(fd.zone_for_position(2, 24), fd.ZONE_PROMOTION)
        self.assertEqual(fd.zone_for_position(3, 24), fd.ZONE_PLAYOFF)
        self.assertEqual(fd.zone_for_position(6, 24), fd.ZONE_PLAYOFF)
        self.assertEqual(fd.zone_for_position(21, 24), fd.ZONE_RELEGATION)

    def test_split_standings(self):
        ds = fd.build_dataset(info(), LEAGUE)
        labels = fd.team_labels(LEAGUE)
        fxs = fd.season_fixtures(ds, 101, 2026)

        home = fd.standings(ds, 101, 2026, fxs, labels, split=fd.SPLIT_HOME)
        self.assertEqual(home.note, "Home matches only. 3 points for a win, 1 for a draw.")
        home_rows = {r.team: r for r in home.groups[0][1]}
        self.assertEqual(home_rows["Hull City"].played, 1)
        self.assertEqual(home_rows["Hull City"].won, 1)
        self.assertEqual(home_rows["Leeds United"].played, 0)

        away = fd.standings(ds, 101, 2026, fxs, labels, split=fd.SPLIT_AWAY)
        self.assertEqual(away.note, "Away matches only. 3 points for a win, 1 for a draw.")
        away_rows = {r.team: r for r in away.groups[0][1]}
        self.assertEqual(away_rows["Hull City"].played, 1)
        self.assertEqual(away_rows["Hull City"].won, 1)
        self.assertEqual(away_rows["Leeds United"].played, 1)

        form = fd.standings(ds, 101, 2026, fxs, labels, split=fd.SPLIT_FORM)
        self.assertIn("Form guide", form.note)
        self.assertEqual(len(form.groups[0][1]), 4)


class FormStepTests(unittest.TestCase):
    def test_played_matches_from_one_side_oldest_first(self):
        steps = fd.team_steps(LEAGUE, team(2), fd.team_labels(LEAGUE))
        self.assertEqual([(s.opponent, s.venue, s.score, s.outcome) for s in steps],
                         [("Hull City", "A", "1-2", "L"), ("Sheffield United", "H", "n/a", "?")])
        self.assertEqual([s.date for s in steps], [D(2026, 8, 8), D(2026, 8, 15)])

    def test_points_and_goals_are_none_when_the_save_holds_no_score(self):
        lost, unknown = fd.team_steps(LEAGUE, team(2), fd.team_labels(LEAGUE))
        self.assertEqual((lost.points, lost.goals_for, lost.goals_against), (0, 1, 2))
        self.assertEqual((unknown.points, unknown.goals_for, unknown.goals_against), (None, None, None))

    def test_an_away_win_reads_from_the_teams_side(self):
        (win,) = [s for s in fd.team_steps(LEAGUE, team(1), fd.team_labels(LEAGUE)) if s.venue == "A"]
        self.assertEqual((win.opponent, win.score, win.outcome, win.points), ("Derby County", "3-1", "W", 3))

    def test_neutral_ground_is_its_own_venue_but_keeps_the_side(self):
        final = dataclasses.replace(fx(D(2027, 5, 20), 1, 2, 1, 0), is_neutral_venue=True)
        (step,) = fd.team_steps([final], team(2), fd.team_labels([final]))
        self.assertEqual((step.venue, step.home, step.outcome), ("N", False, "L"))


class FormStepTextTests(unittest.TestCase):
    """One match of a form strip in words, for a tooltip."""

    def test_a_home_win_reads_as_won_the_score_v_the_opponent_and_the_date(self):
        self.assertEqual(fd.describe_form_step(hull_steps("W")[0]), "Won 1-0 v Leeds United, Sat 1 Aug")

    def test_an_away_defeat_reads_as_lost_at_the_opponent(self):
        self.assertEqual(fd.describe_form_step(hull_steps("WL")[1]), "Lost 0-1 at Sheffield United, Sat 8 Aug")

    def test_a_draw_reads_as_drew(self):                   # a guard: the mapping arrived with the defeat's
        self.assertEqual(fd.describe_form_step(hull_steps("D")[0]), "Drew 1-1 v Leeds United, Sat 1 Aug")

    def test_a_match_with_no_recoverable_score_says_so(self):
        self.assertEqual(fd.describe_form_step(hull_steps("?")[0]),
                         "Played, score not recoverable (n/a), v Leeds United, Sat 1 Aug")


class FormStripTests(unittest.TestCase):
    def test_strip_is_the_last_five_played_oldest_first(self):
        self.assertEqual(fd.form_strip(hull_steps("WWLDW?W")).letters, "LDW?W")

    def test_points_per_game_leave_out_the_match_with_no_score(self):
        totals = fd.form_strip(hull_steps("WWLDW?W")).totals
        self.assertEqual((totals.points, totals.scored, totals.unavailable), (7, 4, 1))
        self.assertEqual(totals.ppg, 1.75)
        self.assertTrue(totals.incomplete)

    def test_caption_names_the_matches_behind_the_figure(self):
        self.assertEqual(fd.form_strip(hull_steps("WWLDW?W")).describe(), "PPG 1.75 from 4 scored (1 n/a)")
        self.assertEqual(fd.form_strip(hull_steps("WDL")).describe(), "PPG 1.33 from 3 scored")

    def test_no_points_per_game_without_a_scored_match(self):
        self.assertIsNone(fd.form_strip(hull_steps("??")).totals.ppg)
        self.assertIsNone(fd.form_strip(()).totals.ppg)
        self.assertEqual(fd.form_strip(()).letters, "")


class TotalsTests(unittest.TestCase):
    def test_a_match_with_no_score_counts_as_played_and_nothing_else(self):
        totals = fd.team_totals(hull_steps("WD?LW"))
        self.assertEqual((totals.played, totals.scored, totals.unavailable), (5, 4, 1))
        self.assertEqual((totals.won, totals.drawn, totals.lost, totals.points), (2, 1, 1, 7))
        self.assertEqual((totals.goals_for, totals.goals_against, totals.goal_difference), (3, 2, 1))
        self.assertEqual((totals.clean_sheets, totals.failed_to_score), (2, 1))
        self.assertTrue(totals.incomplete)

    def test_home_and_away(self):
        steps = hull_steps("WD?LW")      # home, away, home, away, home
        home = fd.team_totals(s for s in steps if s.home)
        away = fd.team_totals(s for s in steps if not s.home)
        self.assertEqual((home.played, home.scored, home.points, home.incomplete), (3, 2, 6, True))
        self.assertEqual((away.played, away.scored, away.points, away.incomplete), (2, 2, 1, False))


class StreakTests(unittest.TestCase):
    def runs(self, letters):
        return fd.streaks(hull_steps(letters))

    def lengths(self, runs):
        return {kind: (run.length, run.incomplete) for kind, run in runs.items()}

    def test_current_runs_count_back_from_the_latest_match(self):
        self.assertEqual(self.lengths(self.runs("WWDWW").current), {
            fd.STREAK_WINNING: (2, False), fd.STREAK_UNBEATEN: (5, False),
            fd.STREAK_WINLESS: (0, False), fd.STREAK_LOSING: (0, False)})

    def test_a_match_with_no_score_stops_the_current_run_and_marks_it_incomplete(self):
        winning = self.runs("L?WW").current[fd.STREAK_WINNING]
        self.assertEqual((winning.length, winning.incomplete, winning.ceiling), (2, True, 3))
        self.assertEqual(winning.describe(), "Won at least 2 in a row")

    def test_longest_runs_either_side_of_a_match_with_no_score(self):
        self.assertEqual(self.lengths(self.runs("WW?WWWDL").longest), {
            fd.STREAK_WINNING: (3, True),     # six in a row if the ? was a win
            fd.STREAK_UNBEATEN: (4, True),
            fd.STREAK_WINLESS: (2, False),    # the ? sits between wins: it cannot beat D L
            fd.STREAK_LOSING: (1, False)})
        self.assertEqual(self.runs("WW?WWWDL").longest[fd.STREAK_WINNING].ceiling, 6)

    def test_a_gap_is_incomplete_only_where_it_could_beat_the_longest_run(self):
        longest = self.runs("WWWWL?L").longest
        self.assertEqual((longest[fd.STREAK_WINNING].length, longest[fd.STREAK_WINNING].incomplete), (4, False))
        self.assertEqual((longest[fd.STREAK_LOSING].length, longest[fd.STREAK_LOSING].incomplete), (1, True))
        tie = self.runs("?LWLL").longest[fd.STREAK_LOSING]     # "?L" could only equal "LL"
        self.assertEqual((tie.length, tie.incomplete), (2, False))

    def test_a_run_knows_its_first_and_last_match(self):
        winning = self.runs("LWWWD").longest[fd.STREAK_WINNING]
        self.assertEqual((winning.first, winning.last), (D(2026, 8, 8), D(2026, 8, 22)))

    def test_headline_is_the_longest_current_run_and_a_strict_run_wins_a_tie(self):
        self.assertEqual(self.runs("DWW").headline.describe(), "Unbeaten in 3")
        self.assertEqual(self.runs("LWW").headline.describe(), "Won 2 in a row")
        self.assertEqual(self.runs("WDL").headline.describe(), "Without a win in 2")
        self.assertEqual(self.runs("WLL").headline.describe(), "Lost 2 in a row")

    def test_headline_when_the_latest_match_has_no_score(self):
        headline = self.runs("WW?").headline
        self.assertEqual((headline.length, headline.incomplete), (0, True))
        self.assertIn("no recoverable score", headline.describe())

    def test_no_matches_no_headline(self):
        self.assertIsNone(fd.streaks(()).headline)
        self.assertEqual(fd.streaks(()).longest[fd.STREAK_UNBEATEN].length, 0)

    def test_current_form_in_words(self):
        self.assertEqual(self.runs("LW").describe_current(), "Won the last match")
        self.assertEqual(self.runs("D").describe_current(), "Drew the last match")
        self.assertEqual(self.runs("LD").describe_current(), "Without a win in 2")
        self.assertEqual(self.runs("WWL").describe_current(), "Lost the last match")
        self.assertEqual(self.runs("DWW").describe_current(), "Unbeaten in 3")
        self.assertIn("no recoverable score", self.runs("W?").describe_current())
        self.assertEqual(fd.streaks(()).describe_current(), "No matches played")


class DisplayTextTests(unittest.TestCase):
    def test_a_match_from_one_side_in_words(self):
        steps = fd.team_steps(LEAGUE, team(2), fd.team_labels(LEAGUE))
        self.assertEqual([s.describe() for s in steps], ["L 1-2 at Hull City", "? n/a v Sheffield United"])
        final = dataclasses.replace(fx(D(2027, 5, 20), 1, 2, 1, 0), is_neutral_venue=True)
        (step,) = fd.team_steps([final], team(1), fd.team_labels([final]))
        self.assertEqual(step.describe(), "W 1-0 v Leeds United (neutral ground)")

    def test_run_lengths_for_a_table_cell(self):
        runs = fd.streaks(hull_steps("WW?WWWDL")).longest
        self.assertEqual([runs[kind].short() for kind in fd.STREAK_KINDS], ["3+", "4+", "2", "1"])
        self.assertEqual(fd.streaks(hull_steps("DDD")).longest[fd.STREAK_WINNING].short(), "")    # never won
        self.assertEqual(fd.streaks(hull_steps("??")).longest[fd.STREAK_WINNING].short(), "?")

    def test_points_per_game_for_a_table_cell(self):
        self.assertEqual(fd.team_totals(hull_steps("WDL")).ppg_text(), "1.33")
        self.assertEqual(fd.team_totals(hull_steps("WD?")).ppg_text(), "2.00*")
        self.assertEqual(fd.team_totals(()).ppg_text(), "")

    def test_table_order_uses_the_table_holding_every_team(self):
        fixtures = [fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 8), 3, 4, 2, 0, md=1)]
        east = NS(competition_id=101, rows=(row(2, 1), row(1, 2)))
        west = NS(competition_id=101, rows=(row(3, 1), row(4, 2)))
        overall = NS(competition_id=101, rows=(row(3, 1), row(1, 2), row(2, 3), row(4, 4)))

        def order(tables):
            ds = fd.build_dataset(info(), fixtures, tables=tables)
            return fd.standings(ds, 101, 2026, fixtures, fd.team_labels(fixtures)).order

        self.assertEqual(order([east, west]), (team(2), team(1), team(3), team(4)))      # each in turn
        self.assertEqual(order([east, west, overall]), (team(3), team(1), team(2), team(4)))


class FormGuideTests(unittest.TestCase):
    def guide(self, fixtures, **options):
        return fd.form_guide(fixtures, fd.team_labels(fixtures), **options)

    def test_every_team_in_calculated_table_order(self):
        rows = self.guide(LEAGUE).rows
        self.assertEqual([r.team for r in rows], ["Hull City", "Sheffield United", "Derby County", "Leeds United"])
        self.assertEqual([r.strip.letters for r in rows], ["WW", "D?", "DL", "L?"])

    def test_a_given_order_comes_first(self):
        rows = self.guide(LEAGUE, order=[team(4), team(1)]).rows
        self.assertEqual([r.team for r in rows], ["Derby County", "Hull City", "Sheffield United", "Leeds United"])

    def test_each_row_carries_totals_splits_and_runs(self):
        leeds = self.guide(LEAGUE).rows[-1]
        self.assertEqual((leeds.totals.played, leeds.totals.scored, leeds.totals.incomplete), (2, 1, True))
        self.assertEqual((leeds.home.played, leeds.away.played), (1, 1))
        self.assertEqual(leeds.streaks.headline.describe(), "Not known (no recoverable score)")

    def test_a_team_yet_to_play_is_still_listed(self):
        fixtures = [fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 15), 3, 4, md=2)]
        rows = {r.team: r for r in self.guide(fixtures).rows}
        self.assertEqual(len(rows), 4)
        self.assertEqual((rows["Derby County"].totals.played, rows["Derby County"].strip.letters), (0, ""))
        self.assertIsNone(rows["Derby County"].streaks.headline)

    def test_coverage_sentence(self):
        text = self.guide(LEAGUE).describe()
        self.assertIn("from 3 scored matches", text)
        self.assertIn("1 played match has no recoverable score", text)
        self.assertNotIn("no recoverable score", self.guide(LEAGUE[:2]).describe())
        self.assertIn("No matches played yet", self.guide(LEAGUE[4:]).describe())


class SeasonRecordTests(unittest.TestCase):
    MINI = [
        fx(D(2026, 8, 8), 1, 2, 3, 0, md=1),     # Hull 3-0 Leeds
        fx(D(2026, 8, 8), 3, 4, 2, 2, md=1),     # Sheffield United 2-2 Derby
        fx(D(2026, 8, 15), 2, 3, 0, 1, md=2),    # Leeds 0-1 Sheffield United
        fx(D(2026, 8, 15), 4, 1, 0, 0, md=2),    # Derby 0-0 Hull
    ]

    def records(self, fixtures):
        found = fd.season_records(fd.form_guide(fixtures, fd.team_labels(fixtures)))
        return {r.title: r for r in found}

    def test_holders_and_shared_records(self):
        records = self.records(self.MINI)
        self.assertEqual((records["Most goals"].teams, records["Most goals"].value),
                         (("Hull City", "Sheffield United"), "3"))
        self.assertEqual((records["Fewest conceded"].teams, records["Fewest conceded"].value), (("Hull City",), "0"))
        self.assertEqual(records["Most clean sheets"].teams, ("Hull City",))
        self.assertEqual(records["Best points per game"].value, "2.00")
        self.assertEqual((records["Longest losing run"].teams, records["Longest losing run"].value),
                         (("Leeds United",), "2"))
        self.assertFalse(any(r.incomplete for r in records.values()))

    def test_a_record_nobody_has_set_is_left_out(self):
        no_clean_sheets = [fx(D(2026, 8, 8), 1, 2, 1, 1, md=1), fx(D(2026, 8, 15), 2, 1, 2, 1, md=2)]
        records = self.records(no_clean_sheets)
        self.assertNotIn("Most clean sheets", records)
        self.assertIn("Most goals", records)

    def test_a_missing_score_marks_the_records_it_could_change(self):
        gap = [
            fx(D(2026, 8, 8), 1, 2, 1, 0, md=1),                       # Hull 1-0 Leeds
            fx(D(2026, 8, 8), 3, 4, 1, 0, md=1),                       # Sheffield United 1-0 Derby
            fx(D(2026, 8, 15), 1, 3, 2, 0, md=2),                      # Hull 2-0 Sheffield United
            fx(D(2026, 8, 15), 2, 4, None, None, played=True, md=2),   # Leeds v Derby, no score
        ]
        records = self.records(gap)
        self.assertTrue(records["Most goals"].incomplete)              # Leeds or Derby may have scored
        self.assertTrue(records["Longest losing run"].incomplete)      # either may have lost twice
        self.assertEqual(records["Longest winning run"].teams, ("Hull City",))
        self.assertFalse(records["Longest winning run"].incomplete)    # a win there makes only one

    def test_no_records_before_a_match_is_scored(self):
        self.assertEqual(self.records(LEAGUE[4:]), {})


TIE_BREAK_SEASON = [
    fx(D(2026, 8, 8), 1, 3, 1, 0, md=1),      # Hull beat Sheffield United...
    fx(D(2026, 8, 8), 2, 5, 1, 1, md=1),      # ...while Leeds draw
    fx(D(2026, 8, 15), 1, 4, 0, 4, md=2),     # Hull lose heavily: 3 points, one win, GD -3
    fx(D(2026, 8, 15), 2, 3, 2, 2, md=2),
    fx(D(2026, 8, 22), 2, 4, 0, 0, md=3),     # Leeds: 3 points from three draws, GD 0
]


def rules_listing(*codes, comp=101):
    """A rules block the save links to a competition, listing tie-break codes in order."""
    return NS(competition_id=comp, promotion_places=0, playoff_places=0, relegation_places=0, rounds=(),
              unknown={f"tie_break_{i:02d}": code for i, code in enumerate(codes)})


class TieBreakTests(unittest.TestCase):
    def order(self, rows):
        return [r.team for r in rows]

    def test_level_teams_go_by_goal_difference_by_default(self):
        rows = fd.calculate_standings(TIE_BREAK_SEASON, fd.team_labels(TIE_BREAK_SEASON))
        self.assertEqual(self.order(rows)[:3], ["Derby County", "Leeds United", "Hull City"])

    def test_wins_first_when_the_rules_list_wins_first(self):
        rows = fd.calculate_standings(TIE_BREAK_SEASON, fd.team_labels(TIE_BREAK_SEASON), tie_breaks=(2, 0, 1))
        self.assertEqual(self.order(rows)[:3], ["Derby County", "Hull City", "Leeds United"])

    def test_each_competition_gets_the_tie_breaks_its_rules_list(self):
        ds = fd.build_dataset(info(), TIE_BREAK_SEASON, rules=[rules_listing(2, 0, 1, 3, 10)])
        self.assertEqual(ds.tie_breaks[101], (2, 0, 1, 3, 10))
        disagree = fd.build_dataset(info(), TIE_BREAK_SEASON, rules=[rules_listing(2, 0, 1), rules_listing(0, 1)])
        self.assertNotIn(101, disagree.tie_breaks)

    def test_table_and_positions_follow_the_competitions_tie_breaks(self):
        ds = fd.build_dataset(info(), TIE_BREAK_SEASON, rules=[rules_listing(2, 0, 1, 3)])
        fixtures, labels = fd.season_fixtures(ds, 101, 2026), fd.team_labels(TIE_BREAK_SEASON)
        table = fd.standings(ds, 101, 2026, fixtures, labels)
        self.assertEqual(self.order(table.groups[0][1])[:3], ["Derby County", "Hull City", "Leeds United"])
        self.assertIn("wins, then goal difference, then goals scored", table.note)
        chart = fd.positions_by_matchday(ds, 101, 2026, fixtures, labels)
        final = {t.team: t.positions[-1] for t in chart.groups[0].tracks}
        self.assertEqual((final["Hull City"], final["Leeds United"]), (2, 3))
        self.assertIn("wins, then goal difference, then goals scored", chart.describe())

    def test_a_first_tie_break_that_cannot_be_worked_out_is_said_so(self):
        ds = fd.build_dataset(info(), TIE_BREAK_SEASON, rules=[rules_listing(3, 0, 1)])
        fixtures, labels = fd.season_fixtures(ds, 101, 2026), fd.team_labels(TIE_BREAK_SEASON)
        table = fd.standings(ds, 101, 2026, fixtures, labels)
        self.assertEqual(self.order(table.groups[0][1])[:3], ["Derby County", "Leeds United", "Hull City"])
        self.assertIn("cannot follow", table.note)


class PositionTests(unittest.TestCase):
    def chart(self, fixtures, **build):
        ds = fd.build_dataset(info(), fixtures, **build)
        season = fd.season_fixtures(ds, 101, 2026)
        return fd.positions_by_matchday(ds, 101, 2026, season, fd.team_labels(season))

    def tracks(self, chart, group=0):
        return {t.team: t.positions for t in chart.groups[group].tracks}

    def test_position_after_each_played_matchday(self):
        chart = self.chart(LEAGUE)
        self.assertEqual(chart.matchdays, (1, 2))
        # After matchday 1 Derby and Sheffield United are level on everything: name order decides.
        self.assertEqual(self.tracks(chart), {"Hull City": (1, 1), "Derby County": (2, 3),
                                              "Sheffield United": (3, 2), "Leeds United": (4, 4)})
        self.assertEqual([t.team for t in chart.groups[0].tracks][0], "Hull City")   # final order
        hull = chart.groups[0].tracks[0]
        self.assertEqual((hull.points, hull.played), ((3, 6), (1, 2)))

    def test_matches_with_no_score_are_left_out_and_counted(self):
        chart = self.chart(LEAGUE)
        self.assertEqual(chart.unscored, 1)
        self.assertIn("1 played match with no recoverable score", chart.describe())

    def test_a_match_played_late_counts_towards_its_own_matchday(self):
        fixtures = [
            fx(D(2026, 8, 8), 1, 2, 0, 1, md=1),      # Leeds win
            fx(D(2026, 8, 29), 3, 4, 5, 0, md=1),     # matchday 1, played three weeks late
            fx(D(2026, 8, 15), 1, 3, 1, 1, md=2),
            fx(D(2026, 8, 15), 2, 4, 1, 1, md=2),
        ]
        tracks = self.tracks(self.chart(fixtures))
        self.assertEqual(tracks["Sheffield United"][0], 1)    # 5-0 counts after matchday 1
        self.assertEqual(tracks["Derby County"][0], 4)

    def test_teams_whose_every_match_lacks_a_score_are_skipped(self):
        fixtures = [fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 8), 3, 4, None, None, played=True, md=1)]
        chart = self.chart(fixtures)
        self.assertEqual(set(self.tracks(chart)), {"Hull City", "Leeds United"})
        self.assertEqual(chart.skipped, ("Derby County", "Sheffield United"))
        self.assertIn("2 clubs", chart.describe())

    def test_groups_follow_the_stored_tables_and_are_checked_against_them(self):
        fixtures = [fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 8), 3, 4, 2, 0, md=1),
                    fx(D(2026, 8, 15), 1, 3, md=2)]
        east = NS(competition_id=101, rows=(row(2, 1), row(1, 2)))     # the game has Leeds top
        west = NS(competition_id=101, rows=(row(3, 1), row(4, 2)))
        chart = self.chart(fixtures, tables=[east, west])
        self.assertEqual([g.title for g in chart.groups], ["Table 1 of 2", "Table 2 of 2"])
        self.assertEqual(self.tracks(chart, 0), {"Hull City": (1,), "Leeds United": (2,)})
        self.assertEqual(self.tracks(chart, 1), {"Sheffield United": (1,), "Derby County": (2,)})
        self.assertEqual((chart.agreeing, chart.compared), (2, 4))
        self.assertIn("2 of 4", chart.describe())

    def test_zones_follow_the_rules_and_say_so(self):
        rules = [NS(competition_id=101, promotion_places=1, playoff_places=1, relegation_places=1, rounds=())]
        chart = self.chart(LEAGUE, rules=rules)
        self.assertEqual(chart.groups[0].zones, (fd.ZONE_PROMOTION, fd.ZONE_PLAYOFF, fd.ZONE_NONE, fd.ZONE_RELEGATION))
        self.assertIn("game's rules", chart.zones_note)
        self.assertEqual(self.chart(LEAGUE).zones_note, "")      # four teams and no rules: no zones

    def test_nothing_played_yet(self):
        chart = self.chart(LEAGUE[4:])
        self.assertEqual(chart.matchdays, ())
        self.assertIn("No matchday has been played", chart.describe())

    def test_a_cup_has_no_matchdays(self):
        final = fx(D(2027, 5, 20), 1, 2, 1, 0, rnd=CodedValue(CompetitionRound.FINAL, 19))
        self.assertIsNone(self.chart([final]))


def stats_row(f, home, xg, npxg=None, **changes):
    """One side's statistics for a match, as fmsave reads them: a real TeamMatchStats record whose
    figures other than expected goals are made up."""
    row = TeamMatchStats(
        competition_id=f.competition_id, home_team_id=f.home_team_id, away_team_id=f.away_team_id,
        date=f.date, kick_off_time=f.kick_off_time, team_id=f.home_team_id if home else f.away_team_id,
        is_home=home, detailed_report=False, players=16, shots=10, shots_on_target=4, blocked_shots=2,
        shots_outside_box=3, clear_cut_chances=1, woodwork=0, fouls_made=11, offsides=2, yellow_cards=1,
        red_cards=0, crosses_attempted=12, crosses_completed=3, tackles_attempted=20, tackles_completed=14,
        aerial_challenges_attempted=30, headers_won=15, distance_km=110.5, expected_goals=xg,
        non_penalty_expected_goals=xg if npxg is None else npxg, corners=5, passes_attempted=400,
        passes_completed=330, final_third_passes=60, progressive_passes=None, possession_percent=50,
        ball_distribution_percent=50)
    return dataclasses.replace(row, **changes)


def match_stats(f, home_xg, away_xg):
    return [stats_row(f, True, home_xg), stats_row(f, False, away_xg)]


XG_SEASON = [
    fx(D(2026, 8, 8), 1, 2, 2, 1, md=1),      # Hull 2-1 Leeds, xG 1.82-0.45
    fx(D(2026, 8, 8), 3, 4, 0, 0, md=1),      # Sheffield United 0-0 Derby: the save kept no report
    fx(D(2026, 8, 15), 2, 3, 3, 0, md=2),     # Leeds 3-0 Sheffield United, xG 1.10-0.90
    fx(D(2026, 8, 22), 4, 1, md=3),           # still to play
]
XG_STATS = match_stats(XG_SEASON[0], 1.82, 0.45) + match_stats(XG_SEASON[2], 1.10, 0.90)


class ExpectedGoalsTests(unittest.TestCase):
    def dataset(self, fixtures=XG_SEASON, stats=XG_STATS):
        return fd.build_dataset(info(), fixtures, match_stats=stats)

    def test_a_match_report_gives_each_side_its_expected_goals(self):
        ds = self.dataset()
        xg = fd.xg_for(ds, XG_SEASON[0])
        self.assertEqual((xg.home, xg.away), (1.82, 0.45))
        self.assertEqual(xg.describe(), "1.82-0.45")
        report = ds.xg_report
        self.assertEqual((report.rows, report.matches, report.joined, report.unmatched, report.rejected), (4, 2, 2, 0, 0))

    def test_non_penalty_expected_goals_are_kept_too(self):
        stats = [stats_row(XG_SEASON[0], True, 1.82, 1.06), stats_row(XG_SEASON[0], False, 0.45)]
        xg = fd.xg_for(self.dataset(stats=stats), XG_SEASON[0])
        self.assertEqual((xg.home_non_penalty, xg.away_non_penalty), (1.06, 0.45))

    def test_no_report_means_no_expected_goals_never_zero(self):
        ds = self.dataset()
        self.assertIsNone(fd.xg_for(ds, XG_SEASON[1]))
        self.assertIsNone(fd.xg_for(ds, XG_SEASON[3]))

    def test_coverage_counts_played_matches_only(self):
        text = fd.xg_coverage(self.dataset(), XG_SEASON).describe()
        self.assertIn("Expected goals for 2 of 3 played matches", text)
        self.assertIn("No matches played yet", fd.xg_coverage(self.dataset(), XG_SEASON[3:]).describe())

    def test_scoreline(self):
        ds = self.dataset()
        self.assertEqual(fd.xg_scoreline(XG_SEASON[0], fd.xg_for(ds, XG_SEASON[0]), fd.team_labels(XG_SEASON)),
                         "Hull City [1.82] 2-1 [0.45] Leeds United")

    def test_team_figures_cover_only_the_matches_with_a_report(self):
        ds = self.dataset()
        rows = {r.team: r for r in fd.xg_table(ds, XG_SEASON, fd.team_labels(XG_SEASON))}
        sheffield = rows["Sheffield United"]
        self.assertEqual((sheffield.played, sheffield.covered, sheffield.goals_for, sheffield.goals_against), (2, 1, 0, 3))
        self.assertAlmostEqual(sheffield.xg_for, 0.90)
        self.assertAlmostEqual(sheffield.prevention, -1.90)      # conceded 3 from 1.10 expected
        leeds = rows["Leeds United"]
        self.assertAlmostEqual(leeds.xg_for, 1.55)
        self.assertAlmostEqual(leeds.finishing, 2.45)           # 4 goals from 1.55 expected
        derby = rows["Derby County"]
        self.assertEqual((derby.played, derby.covered), (1, 0))
        self.assertEqual((derby.xg_for, derby.xg_against, derby.goals_for, derby.finishing, derby.prevention),
                         (None, None, None, None, None))       # nothing to show, so nothing, not 0.00
        # Best xG difference first (Hull +1.37, Sheffield -0.20, Leeds -1.17); no reports, last.
        self.assertEqual(list(rows), ["Hull City", "Sheffield United", "Leeds United", "Derby County"])

    def test_rows_that_are_not_one_home_and_one_away_row_are_rejected(self):
        extra = XG_STATS + [stats_row(XG_SEASON[0], True, 0.70)]          # a second home row
        ds = self.dataset(stats=extra)
        self.assertIsNone(fd.xg_for(ds, XG_SEASON[0]))
        self.assertEqual((ds.xg_report.joined, ds.xg_report.rejected), (1, 1))
        lonely = self.dataset(stats=XG_STATS[:1])
        self.assertEqual((lonely.xg_report.joined, lonely.xg_report.rejected), (0, 1))

    def test_unreadable_values_are_rejected(self):
        ds = self.dataset(stats=match_stats(XG_SEASON[0], float("nan"), 0.45))
        self.assertIsNone(fd.xg_for(ds, XG_SEASON[0]))
        self.assertEqual(ds.xg_report.rejected, 1)

    def test_a_key_that_fits_two_fixtures_is_rejected(self):
        twin = dataclasses.replace(XG_SEASON[0], kick_off_time=dt.time(19, 45))   # same teams, same day
        ds = self.dataset(fixtures=XG_SEASON + [twin])
        self.assertIsNone(fd.xg_for(ds, XG_SEASON[0]))
        self.assertEqual(ds.xg_report.rejected, 1)

    def test_reports_for_matches_the_fixtures_do_not_hold_are_counted(self):
        elsewhere = fx(D(2026, 8, 8), 1, 2, 2, 1, comp=55)
        stats = XG_STATS + match_stats(elsewhere, 1.0, 1.0) + match_stats(XG_SEASON[3], 0.5, 0.5)
        ds = self.dataset(stats=stats)
        self.assertEqual((ds.xg_report.joined, ds.xg_report.unmatched), (2, 2))
        self.assertIsNone(fd.xg_for(ds, XG_SEASON[3]))                   # never joined to an unplayed match

    def test_not_read_yet_and_could_not_be_read(self):
        pending = fd.build_dataset(info(), XG_SEASON)
        self.assertIsNone(pending.xg_report)
        self.assertIn("not been read yet", fd.xg_coverage(pending, XG_SEASON).describe())
        failed = fd.with_expected_goals(pending, None, "UnsupportedGameError: no match reports")
        self.assertIn("no match reports", failed.xg_report.failed)
        self.assertIn("could not be read", fd.xg_coverage(failed, XG_SEASON).describe())

    def test_over_and_under_performance_beyond_a_dead_zone(self):
        self.assertEqual([fd.xg_tint(v) for v in (0.3, 0.25, -0.25, -0.3)], [fd.XG_ABOVE, "", "", fd.XG_BELOW])

    def test_a_seasons_difference_is_judged_per_match(self):
        self.assertEqual(fd.xg_tint(3.0, matches=15), "")              # 0.20 a match: noise
        self.assertEqual(fd.xg_tint(4.5, matches=15), fd.XG_ABOVE)     # 0.30 a match
        self.assertEqual(fd.xg_tint(-4.5, matches=15), fd.XG_BELOW)


class FakeSave:
    """Stands in for an open fmsave Save: the readers load_dataset calls, serving real fixture and
    match statistics records, and a log of which were read."""

    def __init__(self, fixtures, stats=(), stats_error=None):
        self.info = NS(game="FM27", build="27.0.1+1", known_build=False, game_date=D(2026, 9, 1))
        self._fixtures, self._stats, self._stats_error = fixtures, stats, stats_error
        self.read = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def managed_clubs(self):
        return []

    def clubs(self):
        return []

    def competitions(self):
        return []

    def fixtures(self):
        self.read.append("fixtures")
        return iter(self._fixtures)

    def league_tables(self):
        return []

    def competition_rules(self):
        return []

    def team_match_stats(self):
        self.read.append("stats")
        if self._stats_error:
            raise self._stats_error
        return iter(self._stats)


class StagedLoadTests(unittest.TestCase):
    def test_the_save_is_ready_before_its_expected_goals_are_read(self):
        save = FakeSave(XG_SEASON, XG_STATS)
        seen = []
        with mock.patch.object(fd.fmsave, "open", return_value=save):
            final = fd.load_dataset("career.fm", ready=lambda ds: seen.append((ds.xg_report, list(save.read))))
        self.assertEqual(seen, [(None, ["fixtures"])])      # handed over before the stats were read
        self.assertEqual(final.xg_report.joined, 2)
        self.assertEqual(final.fixture_total, 4)

    def test_a_failure_in_the_ready_callback_is_raised_not_blamed_on_the_statistics(self):
        save = FakeSave(XG_SEASON, XG_STATS)

        def broken(_dataset):
            raise ValueError("the window could not take it")

        with mock.patch.object(fd.fmsave, "open", return_value=save):
            with self.assertRaisesRegex(ValueError, "the window could not take it"):
                fd.load_dataset("career.fm", ready=broken)

    def test_a_failure_to_read_expected_goals_keeps_everything_else(self):
        save = FakeSave(XG_SEASON, stats_error=RuntimeError("the report index does not walk"))
        with mock.patch.object(fd.fmsave, "open", return_value=save):
            final = fd.load_dataset("career.fm")
        self.assertEqual(final.fixture_total, 4)
        self.assertIn("the report index does not walk", final.xg_report.failed)
        self.assertTrue(any(w.startswith("Match statistics (xG) could not be read") for w in final.info.warnings))


class ZoneTests(unittest.TestCase):
    CHAMPIONSHIP = fd.ZoneRules(promotion=2, playoff=6, relegation=3)

    def test_championship_zones_follow_the_rules(self):
        zones = [fd.zone_for_position(p, 24, self.CHAMPIONSHIP) for p in range(1, 25)]
        self.assertEqual(zones[:2], [fd.ZONE_PROMOTION] * 2)
        self.assertEqual(zones[2:8], [fd.ZONE_PLAYOFF] * 6)          # 3rd to 8th
        self.assertEqual(zones[8:21], [fd.ZONE_NONE] * 13)
        self.assertEqual(zones[21:], [fd.ZONE_RELEGATION] * 3)        # 22nd to 24th

    def test_top_flight_keeps_estimated_european_places(self):
        top = fd.ZoneRules(promotion=0, playoff=0, relegation=3)
        zones = [fd.zone_for_position(p, 20, top) for p in range(1, 21)]
        self.assertEqual(zones[:6], [fd.ZONE_UCL] * 4 + [fd.ZONE_EUROPA] * 2)
        self.assertEqual(zones[6:17], [fd.ZONE_NONE] * 11)
        self.assertEqual(zones[17:], [fd.ZONE_RELEGATION] * 3)

    def test_rules_that_do_not_fit_or_say_nothing_mark_no_zones(self):
        nothing = fd.ZoneRules(promotion=0, playoff=0, relegation=0)
        self.assertEqual({fd.zone_for_position(p, 20, nothing) for p in range(1, 21)}, {fd.ZONE_NONE})
        self.assertEqual({fd.zone_for_position(p, 4, self.CHAMPIONSHIP) for p in range(1, 5)}, {fd.ZONE_NONE})

    def test_unlinked_rules_are_matched_to_their_league_by_calendar(self):
        fixtures = league_season(101, D(2026, 8, 8)) + league_season(9, D(2026, 8, 9))
        rules = [rules_block(2, 6, 3, first_day=D(2026, 8, 8)), rules_block(2, 4, 4, first_day=D(2026, 8, 9))]
        ds = fd.build_dataset(info(), fixtures, rules=rules)
        self.assertEqual(ds.zone_rules[101], fd.ZoneRules(2, 6, 3, matched_by_calendar=True))
        self.assertEqual(ds.zone_rules[9], fd.ZoneRules(2, 4, 4, matched_by_calendar=True))

    def test_numbered_rounds_match_their_matchday(self):
        ds = fd.build_dataset(info(), league_season(101, D(2026, 8, 8)),
                              rules=[rules_block(2, 6, 3, first_day=D(2026, 8, 8), numbered=True)])
        self.assertEqual(ds.zone_rules[101].playoff, 6)

    def test_leagues_sharing_a_calendar_get_rules_only_when_their_blocks_agree(self):
        same_day = D(2026, 8, 8)
        fixtures = league_season(9, same_day) + league_season(10, same_day)
        disagree = fd.build_dataset(info(), fixtures, rules=[rules_block(2, 4, 4, first_day=same_day),
                                                             rules_block(3, 4, 2, first_day=same_day)])
        self.assertNotIn(9, disagree.zone_rules)
        self.assertNotIn(10, disagree.zone_rules)
        agree = fd.build_dataset(info(), fixtures, rules=[rules_block(1, 6, 4, first_day=same_day)])
        self.assertEqual(agree.zone_rules[9], agree.zone_rules[10])

    def test_fmsave_link_wins_and_short_or_unmatched_calendars_are_ignored(self):
        fixtures = (league_season(101, D(2026, 8, 8)) + league_season(50, D(2026, 8, 8), matchdays=3)
                    + league_season(60, D(2026, 8, 10)))
        rules = [
            rules_block(2, 6, 3, comp=101),                                   # linked by fmsave
            rules_block(1, 0, 1, first_day=D(2026, 8, 8)),                  # fits 101 too: ignored
            rules_block(1, 0, 0, first_day=D(2026, 8, 8), rounds=3),        # too short to trust
            rules_block(4, 0, 0, first_day=D(2027, 1, 2)),                  # no calendar fits
            rules_block(None, 2, 2, comp=60),                               # unreadable places
        ]
        ds = fd.build_dataset(info(), fixtures, rules=rules)
        self.assertEqual(ds.zone_rules, {101: fd.ZoneRules(2, 6, 3)})

    def test_standings_mark_zones_on_the_overall_table_only(self):
        rules = [NS(competition_id=101, promotion_places=1, playoff_places=1, relegation_places=1, rounds=())]
        ds = fd.build_dataset(info(), LEAGUE, rules=rules)
        fxs, labels = fd.season_fixtures(ds, 101, 2026), fd.team_labels(LEAGUE)
        overall = fd.standings(ds, 101, 2026, fxs, labels)
        self.assertEqual([r.zone for r in overall.groups[0][1]],
                         [fd.ZONE_PROMOTION, fd.ZONE_PLAYOFF, fd.ZONE_NONE, fd.ZONE_RELEGATION])
        self.assertIn("game's rules", overall.zones_note)
        self.assertIn("1 in the play-offs", overall.zones_note)
        home = fd.standings(ds, 101, 2026, fxs, labels, split=fd.SPLIT_HOME)
        self.assertEqual({r.zone for r in home.groups[0][1]}, {fd.ZONE_NONE})
        self.assertEqual(home.zones_note, "")

    def test_estimated_zones_say_so(self):
        # 20 teams and no rules: the zones are a guess from the league's size, and the note says so.
        fixtures = [dataclasses.replace(fx(D(2026, 8, 8), 1, 2, md=1), home_team_id=1000 + 2 * i,
                                        away_team_id=1001 + 2 * i) for i in range(10)]
        ds = fd.build_dataset(info(), fixtures)
        result = fd.standings(ds, 101, 2026, fd.season_fixtures(ds, 101, 2026), fd.team_labels(fixtures))
        self.assertEqual(len(result.groups[0][1]), 20)
        self.assertIn("estimated", result.zones_note)


class DatasetTests(unittest.TestCase):
    def test_managed_club_competitions_come_first(self):
        fixtures = LEAGUE + [
            fx(D(2026, 8, 9), 2, 3, 1, 0, comp=50),                       # someone else's league
            fx(D(2026, 8, 10), 1, 4, 0, 0, comp=60, home_slot=1, away_slot=1),  # our youth side
        ]
        ds = fd.build_dataset(info(), fixtures, clubs=[club(1, slots=(0, 1)), club(2, 9000), club(3), club(4)])
        self.assertEqual([c.id for c in ds.competitions], [101, 60, 50])
        self.assertTrue(ds.by_id[101].managed_first_team)
        self.assertFalse(ds.by_id[60].managed_first_team)
        self.assertEqual(ds.first_team_id, team(1))
        self.assertEqual(ds.by_id[50].top_clubs, ("Leeds", "Sheff Utd"))

    def test_managed_teams_fall_back_to_fixtures_without_a_club_table(self):
        ds = fd.build_dataset(info(), LEAGUE)
        self.assertEqual(ds.first_team_id, team(1))
        self.assertTrue(ds.by_id[101].is_yours)

    def test_search_finds_clubs_and_given_names(self):
        ds = fd.build_dataset(info(), LEAGUE, competitions=[NS(id=101, database_id=777)])
        comp = ds.by_id[101]
        self.assertTrue(fd.matches_search(comp, {}, "derby"))
        self.assertFalse(fd.matches_search(comp, {}, "championship"))
        self.assertTrue(fd.matches_search(comp, {777: "Championship"}, "champ"))
        self.assertEqual(fd.competition_list_label(comp, {}), "[101] Derby, Hull, Leeds")

    def test_competitions_summary_and_categories(self):
        ds = fd.build_dataset(info(), LEAGUE, competitions=[NS(id=101, database_id=777)])
        summaries = fd.competitions_summary(ds, {777: "Championship"})
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].name, "Championship")
        self.assertEqual(summaries[0].category, fd.COMP_CAT_YOURS)
        self.assertEqual(summaries[0].teams, 4)
        self.assertEqual((summaries[0].played, summaries[0].scored), (4, 3))

    def test_categories_go_by_what_most_fixtures_look_like(self):
        fixtures = [
            fx(D(2026, 7, 20), 2, 3, 1, 1, comp=131, season=None),                       # friendly
            fx(D(2026, 8, 1), 2, 3, comp=60, home_slot=1, away_slot=1),                  # youth league
            fx(D(2026, 8, 8), 2, 3, comp=21, md=1),                                      # senior league...
            fx(D(2026, 8, 15), 4, 2, comp=21, md=2, home_slot=1),                        # ...with a B team
            fx(D(2026, 8, 22), 3, 4, comp=21, md=3),
            fx(D(2027, 5, 20), 2, 4, comp=99, rnd=CodedValue(CompetitionRound.FINAL, 19)),   # cup
        ]
        ds = fd.build_dataset(info(managed_uid=None), fixtures)
        categories = {s.id: s.category for s in fd.competitions_summary(ds, {})}
        self.assertEqual(categories, {131: fd.COMP_CAT_FRIENDLY, 60: fd.COMP_CAT_YOUTH,
                                      21: fd.COMP_CAT_LEAGUE, 99: fd.COMP_CAT_CUP})

    def test_summary_copes_with_teams_the_save_cannot_resolve(self):
        # The save leaves club and slot empty for some teams; the hub used to crash on them.
        fixtures = [unresolved_away(fx(D(2026, 8, 8), 2, 3, 1, 0, comp=70)), fx(D(2026, 8, 9), 3, 2, comp=70)]
        ds = fd.build_dataset(info(managed_uid=None), fixtures)
        (summary,) = fd.competitions_summary(ds, {})
        self.assertEqual((summary.category, summary.teams), (fd.COMP_CAT_LEAGUE, 3))
        self.assertEqual(fd.team_labels(fixtures)[999], "Team 999")


class ImportTests(unittest.TestCase):
    def test_missing_file_fails_cleanly(self):
        with self.assertRaises(fd.ImportFailed):
            fd.load_dataset(Path(tempfile.gettempdir()) / "no_such_save_here.fm")

    def test_a_file_that_is_not_a_save_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "notes.fm"
            path.write_text("not a save")
            with self.assertRaises(fd.ImportFailed):
                fd.load_dataset(path)


class NameFileTests(unittest.TestCase):
    def test_names_round_trip_in_the_format_fmsave_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "competition_names.csv"
            self.assertEqual(fd.load_competition_names(path), {})
            names = {12: "Championship", 3: "League One, North"}
            fd.save_competition_names(path, names)
            self.assertEqual(fd.load_competition_names(path), names)


if __name__ == "__main__":
    unittest.main()


class ClubIndexTests(unittest.TestCase):
    """The clubs a command palette offers: those of senior league and cup competitions."""

    @staticmethod
    def index():
        fixtures = LEAGUE + [
            fx(D(2026, 8, 8), 2, 3, 1, 0, comp=102, md=1),                               # another league
            fx(D(2026, 8, 15), 3, 2, 0, 0, comp=102, md=2, away_slot=1),                  # Leeds' second team
            fx(D(2026, 8, 20), 4, 5, 2, 0, comp=103, rnd=CompetitionRound.FINAL),         # a cup
            fx(D(2026, 7, 20), 1, 5, 2, 2, comp=131, season=None),                       # a friendly Hull play in
            fx(D(2026, 8, 10), 3, 4, 1, 0, comp=60, home_slot=1, away_slot=1),            # youth league
            unresolved_away(fx(D(2026, 8, 9), 2, 3, 1, 0, comp=104, md=1)),               # an unresolved team
        ]
        dataset = fd.build_dataset(info(), fixtures, clubs=[club(n) for n in range(1, 6)])
        return fd.club_index(dataset)

    def pairs(self):
        return {(e.team_id, e.competition_id) for e in self.index()}

    def test_clubs_of_other_leagues_and_cups_are_listed(self):
        pairs = self.pairs()
        self.assertIn((team(3), 102), pairs)
        self.assertIn((team(5), 103), pairs)

    def test_the_users_own_league_is_listed_but_not_its_friendlies(self):
        pairs = self.pairs()
        self.assertIn((team(1), 101), pairs)
        self.assertFalse([p for p in pairs if p[1] == 131])      # Hull's friendly: a managed competition, still a friendly

    def test_youth_and_reserve_competitions_are_left_out(self):
        self.assertFalse([p for p in self.pairs() if p[1] == 60])

    def test_a_club_in_two_competitions_appears_once_in_each(self):
        entries = [e for e in self.index() if e.team_id == team(2)]
        self.assertEqual(sorted(e.competition_id for e in entries), [101, 102, 104])

    def test_a_team_the_save_cannot_resolve_is_left_out(self):
        self.assertNotIn(999, {e.team_id for e in self.index()})

    def test_each_entry_says_whether_its_competition_is_a_league_or_a_cup(self):
        kinds = {(e.team_id, e.competition_id): e.category for e in self.index()}
        self.assertEqual(kinds[(team(3), 102)], fd.COMP_CAT_LEAGUE)
        self.assertEqual(kinds[(team(5), 103)], fd.COMP_CAT_CUP)
        self.assertEqual(kinds[(team(1), 101)], fd.COMP_CAT_LEAGUE)          # the user's own league

    def test_a_second_team_is_told_apart(self):
        labels = {e.team_id: e.label for e in self.index() if e.competition_id == 102}
        self.assertEqual(labels[team(2, 1)], "Leeds United (team 2)")
        self.assertEqual(labels[team(2)], "Leeds United")

    def test_entries_are_ordered_by_competition_then_label(self):
        keys = [(e.competition_id, e.label.casefold()) for e in self.index()]
        self.assertEqual(keys, sorted(keys))


class MatchReportTests(unittest.TestCase):
    """Each side's statistics for a match, typed, beside its expected goals."""

    MATCH = XG_SEASON[0]                                     # Hull 2-1 Leeds

    def dataset(self, rows, fixtures=XG_SEASON):
        return fd.build_dataset(info(), fixtures, match_stats=rows)

    def test_a_report_gives_each_side_its_figures(self):
        ds = self.dataset([stats_row(self.MATCH, True, 1.82, shots=14, possession_percent=57),
                           stats_row(self.MATCH, False, 0.45, shots=6, possession_percent=43)])
        report = fd.match_stats_for(ds, self.MATCH)
        self.assertEqual((report.home.shots, report.away.shots), (14, 6))
        self.assertEqual((report.home.possession_percent, report.away.possession_percent), (57, 43))
        self.assertEqual((report.home.expected_goals, report.away.expected_goals), (1.82, 0.45))
        self.assertEqual((report.home.corners, report.home.fouls, report.home.yellow_cards), (5, 11, 1))
        self.assertEqual((report.home.passes_attempted, report.home.passes_completed), (400, 330))

    def test_an_unreadable_figure_is_none_never_zero(self):
        rows = [stats_row(self.MATCH, True, 1.0, shots=None, corners=-1, fouls_made=float("inf")),
                stats_row(self.MATCH, False, 0.5)]
        report = fd.match_stats_for(self.dataset(rows), self.MATCH)
        self.assertEqual((report.home.shots, report.home.corners, report.home.fouls), (None, None, None))
        self.assertEqual(report.away.shots, 10)

    def test_a_report_without_readable_expected_goals_still_gives_its_other_figures(self):
        rows = [stats_row(self.MATCH, True, float("nan")), stats_row(self.MATCH, False, 0.5)]
        ds = self.dataset(rows)
        report = fd.match_stats_for(ds, self.MATCH)
        self.assertIsNone(report.home.expected_goals)
        self.assertEqual(report.home.shots, 10)
        self.assertIsNone(fd.xg_for(ds, self.MATCH))                  # expected goals behave exactly as before
        self.assertEqual(ds.xg_report.rejected, 1)

    def test_a_match_that_does_not_join_has_no_report(self):
        one_row = [stats_row(self.MATCH, True, 1.0)]
        two_home = [stats_row(self.MATCH, True, 1.0), stats_row(self.MATCH, True, 1.0)]
        unplayed = match_stats(XG_SEASON[3], 1.0, 1.0)
        for rows, fixture in ((one_row, self.MATCH), (two_home, self.MATCH), (unplayed, XG_SEASON[3])):
            self.assertIsNone(fd.match_stats_for(self.dataset(rows), fixture))

    def test_a_key_that_fits_two_fixtures_has_no_report(self):
        twin = fx(D(2026, 8, 8), 1, 2, 0, 0, md=1)
        ds = self.dataset(match_stats(self.MATCH, 1.0, 1.0), fixtures=[self.MATCH, twin])
        self.assertIsNone(fd.match_stats_for(ds, self.MATCH))

    def test_statistics_that_could_not_be_read_leave_no_reports(self):
        ds = fd.with_expected_goals(fd.build_dataset(info(), XG_SEASON), None, "boom")
        self.assertEqual(dict(ds.match_reports), {})

    def test_a_dataset_built_without_statistics_has_none(self):
        self.assertIsNone(fd.match_stats_for(fd.build_dataset(info(), XG_SEASON), self.MATCH))

    def lines(self, rows):
        report = fd.match_stats_for(self.dataset(rows), self.MATCH)
        return {line.label: (line.home, line.away) for line in fd.describe_match_stats(report)}

    def test_the_lines_are_formatted_for_reading(self):
        lines = self.lines([stats_row(self.MATCH, True, 1.82, shots=14, possession_percent=57),
                            stats_row(self.MATCH, False, 0.45, passes_attempted=300, passes_completed=240)])
        self.assertEqual(lines["xG"], ("1.82", "0.45"))
        self.assertEqual(lines["Shots"], ("14", "10"))
        self.assertEqual(lines["Possession"], ("57%", "50%"))
        self.assertEqual(lines["Passes"], ("330 of 400 (82%)", "240 of 300 (80%)"))
        self.assertEqual([line.label for line in fd.describe_match_stats(fd.match_stats_for(
            self.dataset([stats_row(self.MATCH, True, 1.0), stats_row(self.MATCH, False, 1.0)]), self.MATCH))],
            ["xG", "Shots", "On target", "Possession", "Passes", "Corners", "Fouls", "Yellow cards", "Red cards"])

    def test_missing_figures_show_a_dash_and_passes_degrade(self):
        lines = self.lines([stats_row(self.MATCH, True, float("nan"), shots=None, possession_percent=None,
                                      passes_attempted=0, passes_completed=0),
                            stats_row(self.MATCH, False, 0.5, passes_attempted=None, passes_completed=200)])
        self.assertEqual(lines["xG"], ("—", "0.50"))
        self.assertEqual(lines["Shots"], ("—", "10"))
        self.assertEqual(lines["Possession"], ("—", "50%"))
        self.assertEqual(lines["Passes"], ("—", "200"))          # only the completed figure is known

    def test_meetings_are_the_matches_between_two_teams_in_date_order(self):
        fixtures = [fx(D(2026, 12, 12), 2, 1, md=4), fx(D(2026, 8, 8), 1, 2, 2, 1, md=1), fx(D(2026, 9, 5), 1, 3, md=2),
                    fx(D(2026, 10, 3), 3, 2, md=3)]
        found = fd.meetings(fixtures, team(1), team(2))
        self.assertEqual([f.date for f in found], [D(2026, 8, 8), D(2026, 12, 12)])
        self.assertEqual(fd.meetings(fixtures, team(1), team(4)), ())

    def test_the_next_match_is_the_earliest_one_still_to_play(self):
        fixtures = [fx(D(2026, 9, 5), 1, 3, md=2), fx(D(2026, 8, 8), 1, 2, 2, 1, md=1), fx(D(2026, 10, 3), 4, 1, md=3)]
        self.assertEqual(fd.next_match(fixtures, team(1)).date, D(2026, 9, 5))
        self.assertIsNone(fd.next_match(fixtures[1:2], team(1)))
        self.assertIsNone(fd.next_match(fixtures, team(5)))


class TwoLeggedTieTests(unittest.TestCase):
    """A tie: the same pair meeting twice in one round, home and away swapped."""

    def ties(self, fixtures):
        return fd.two_legged_ties(fixtures, fd.team_labels(fixtures))

    def test_two_meetings_in_one_round_make_a_tie_with_an_aggregate(self):
        legs = [fx(D(2026, 8, 8), 1, 2, 2, 0, comp=639, md=1), fx(D(2026, 8, 15), 2, 1, 0, 2, comp=639, md=1)]
        (tie,) = self.ties(legs)
        self.assertEqual((tie.team_a, tie.team_b), (team(1), team(2)))        # the first leg's home side is A
        self.assertEqual((tie.first.date, tie.second.date), (D(2026, 8, 8), D(2026, 8, 15)))
        self.assertEqual(tie.aggregate, (4, 0))

    # Guards: these rules arrived with the first implementation.
    def test_a_leagues_pairs_in_different_rounds_are_not_ties(self):
        league = [fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 12, 12), 2, 1, 0, 0, md=20)]
        self.assertEqual(self.ties(league), ())

    def test_three_meetings_in_a_round_are_not_a_tie(self):
        three = [fx(D(2026, 8, d), 1 + d % 2, 2 - d % 2, 1, 0, md=1) for d in (8, 9, 10)]
        self.assertEqual(self.ties(three), ())

    def test_an_unplayed_or_unscored_leg_gives_no_aggregate(self):
        unplayed = [fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 15), 2, 1, md=1)]
        unscored = [fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 15), 2, 1, None, None, played=True, md=1)]
        self.assertIsNone(self.ties(unplayed)[0].aggregate)
        self.assertIsNone(self.ties(unscored)[0].aggregate)

    def test_ties_come_in_round_then_date_order(self):
        legs = [fx(D(2026, 9, 20), 3, 4, 1, 1, md=2), fx(D(2026, 9, 27), 4, 3, 0, 0, md=2),
                fx(D(2026, 8, 15), 2, 1, 0, 2, md=1), fx(D(2026, 8, 8), 1, 2, 2, 0, md=1)]
        self.assertEqual([t.round_index for t in self.ties(legs)], [0, 1])

    def outcome(self, legs):
        (tie,) = self.ties(legs)
        return fd.tie_outcome(tie, fd.team_labels(legs))

    def test_the_aggregate_names_the_side_going_through(self):
        legs = [fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 15), 2, 1, 0, 2, md=1)]
        self.assertEqual(self.outcome(legs), "Hull City go through")

    def test_a_level_aggregate_says_the_save_does_not_decide_it(self):
        legs = [fx(D(2026, 8, 8), 1, 2, 1, 1, md=1), fx(D(2026, 8, 15), 2, 1, 0, 0, md=1)]
        self.assertEqual(self.outcome(legs),
                         "Level on aggregate (the save stores no away goals, extra time or penalties)")

    def test_a_tie_still_to_finish_says_what_is_missing(self):
        second_to_play = [fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 15), 2, 1, md=1)]
        first_to_play = [fx(D(2026, 8, 8), 1, 2, md=1), fx(D(2026, 8, 15), 2, 1, md=1)]
        no_score = [fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 15), 2, 1, None, None, played=True, md=1)]
        self.assertEqual(self.outcome(second_to_play), "Second leg to play")
        self.assertEqual(self.outcome(first_to_play), "First leg to play")
        self.assertEqual(self.outcome(no_score), "Not known: a leg has no recoverable score (n/a)")

    def test_a_replay_is_not_a_second_leg(self):
        # A cup round with a drawn tie that was replayed and another settled in one match: not a two-legged round.
        round_one = [fx(D(2026, 11, 14), 1, 2, 1, 1, md=1), fx(D(2026, 11, 14), 3, 4, 2, 0, md=1),
                     fx(D(2026, 11, 17), 2, 1, 1, 0, md=1)]       # the replay, three days later
        self.assertEqual(self.ties(round_one), ())

    def test_a_two_legged_pair_in_a_round_with_single_matches_is_still_a_tie(self):
        # The European competitions in a save hold a league phase (single matches) and two-legged playoffs under
        # one round index; the pair meeting a week apart, even after a drawn first leg, is a tie.
        mixed = [fx(D(2026, 9, 16), 1, 2, 1, 1, md=1), fx(D(2026, 9, 23), 2, 1, 0, 2, md=1),
                 fx(D(2026, 9, 16), 3, 4, 2, 0, md=1)]
        (tie,) = self.ties(mixed)
        self.assertEqual((tie.team_a, tie.team_b, tie.aggregate), (team(1), team(2), (3, 1)))

    def test_a_round_where_every_pair_meets_twice_is_still_two_legged(self):    # a guard
        legs = [fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 15), 2, 1, 0, 0, md=1),
                fx(D(2026, 8, 8), 3, 4, 2, 2, md=1), fx(D(2026, 8, 15), 4, 3, 1, 0, md=1)]
        self.assertEqual(len(self.ties(legs)), 2)


class CupRoundTests(unittest.TestCase):
    """A knockout competition as rounds of ties, with each tie's winner."""

    def rounds(self, fixtures):
        return fd.cup_rounds(fixtures, fd.team_labels(fixtures))

    def test_single_matches_make_ties_in_round_order_with_the_winner_by_score(self):
        cup = [fx(D(2026, 11, 14), 1, 2, 2, 0, comp=151, md=1), fx(D(2026, 11, 14), 3, 4, 0, 1, comp=151, md=1),
               fx(D(2027, 1, 16), 1, 4, 1, 0, comp=151, md=2)]
        first, final = self.rounds(cup)
        self.assertEqual([r.index for r in (first, final)], [0, 1])
        self.assertEqual([(t.team_a, t.team_b, t.winner, t.how) for t in first.ties],
                         [(team(1), team(2), team(1), "score"), (team(3), team(4), team(4), "score")])
        self.assertEqual((final.ties[0].winner, final.ties[0].how), (team(1), "score"))

    def test_a_drawn_match_is_decided_by_who_appears_in_the_next_round(self):
        cup = [fx(D(2026, 11, 14), 1, 2, 1, 1, comp=151, md=1), fx(D(2026, 11, 14), 3, 4, 0, 1, comp=151, md=1),
               fx(D(2027, 1, 16), 2, 4, 1, 0, comp=151, md=2)]               # 2 went through after the draw
        first, _ = self.rounds(cup)
        self.assertEqual([(t.winner, t.how) for t in first.ties],
                         [(team(2), "next round"), (team(4), "score")])

    def test_a_replay_belongs_to_its_tie_and_its_score_decides_it(self):
        cup = [fx(D(2026, 11, 14), 1, 2, 1, 1, comp=151, md=1), fx(D(2026, 11, 14), 3, 4, 0, 1, comp=151, md=1),
               fx(D(2026, 11, 17), 2, 1, 2, 0, comp=151, md=1)]              # 2 won the replay at home
        (first,) = self.rounds(cup)
        self.assertEqual(len(first.ties), 2)                                  # the replay is not a third tie
        drawn = next(t for t in first.ties if t.team_a == team(1))
        self.assertEqual([f.date for f in drawn.fixtures], [D(2026, 11, 14), D(2026, 11, 17)])
        self.assertEqual((drawn.winner, drawn.how), (team(2), "score"))

    def test_two_legs_are_decided_on_aggregate_even_when_the_second_leg_goes_the_other_way(self):
        cup = [fx(D(2027, 1, 12), 1, 2, 3, 0, comp=662, md=1), fx(D(2027, 2, 2), 2, 1, 1, 0, comp=662, md=1),
               fx(D(2027, 3, 21), 1, 3, 1, 0, comp=662, md=2)]               # 2 won the second leg, 1 the tie 3-1
        first, _ = self.rounds(cup)
        (tie,) = first.ties
        self.assertEqual((len(tie.fixtures), tie.winner, tie.how), (2, team(1), "aggregate"))

    # Guards: these follow from the winner logic above.
    def test_a_level_aggregate_is_settled_by_the_next_round(self):
        cup = [fx(D(2027, 1, 12), 1, 2, 1, 1, comp=662, md=1), fx(D(2027, 1, 19), 2, 1, 0, 0, comp=662, md=1),
               fx(D(2027, 3, 21), 2, 3, 1, 0, comp=662, md=2)]
        (tie,) = self.rounds(cup)[0].ties
        self.assertEqual((tie.winner, tie.how), (team(2), "next round"))

    def test_a_drawn_final_or_an_unplayed_tie_has_no_winner(self):
        cup = [fx(D(2027, 1, 12), 1, 2, 1, 1, comp=662, md=1), fx(D(2027, 3, 21), 3, 4, comp=662, md=2)]
        first, final = self.rounds(cup)
        self.assertEqual((first.ties[0].winner, first.ties[0].how), (None, ""))
        self.assertEqual((final.ties[0].winner, final.ties[0].how), (None, ""))

    def names(self, fixtures):
        return [r.name for r in self.rounds(fixtures)]

    def test_a_round_the_save_names_keeps_its_name_and_one_it_does_not_is_named_from_its_size(self):
        def matches(md, n, rnd=None):                              # n different pairs in round md
            return [fx(D(2026, 9, 1 + md), 2 * i + 1, 2 * i + 2, 1, 0, comp=151, md=md, rnd=rnd) for i in range(n)]

        final = CodedValue(CompetitionRound.FINAL, 19)
        with mock.patch.dict(CLUBS, {n: (f"Club {n}", f"C{n}") for n in range(6, 17)}):
            cup = matches(1, 8) + matches(2, 4) + matches(3, 1, final)
            self.assertEqual(self.names(cup), ["Last 16", "Last 8", "Final"])
            odd = matches(1, 3) + matches(2, 2)                    # three ties is no power of two: no size to name it by
            self.assertEqual(self.names(odd), ["Round 1", "Last 4"])

    def test_a_round_where_a_side_plays_more_than_twice_is_a_group_phase_not_a_knockout(self):
        group = [fx(D(2026, 9, 1), 1, 2, 1, 0, comp=664, md=1), fx(D(2026, 9, 8), 1, 3, 0, 0, comp=664, md=1),
                 fx(D(2026, 9, 15), 1, 4, 2, 1, comp=664, md=1), fx(D(2026, 9, 1), 3, 4, 1, 1, comp=664, md=1)]
        knockout = [fx(D(2026, 10, 1), 1, 3, 1, 0, comp=664, md=2)]
        first, second = self.rounds(group + knockout)
        self.assertFalse(first.knockout)                 # team 1 plays three times in the round
        self.assertTrue(second.knockout)

    @staticmethod
    def matches(md, n, rnd=None):                              # n different pairs in round md
        return [fx(D(2026, 9, 1 + md), 2 * i + 1, 2 * i + 2, 1, 0, comp=151, md=md, rnd=rnd) for i in range(n)]

    def test_the_last_rounds_that_halve_down_to_a_single_final_are_the_tree_and_the_rest_the_list(self):
        with mock.patch.dict(CLUBS, {n: (f"Club {n}", f"C{n}") for n in range(6, 17)}):
            cup = self.matches(1, 5) + self.matches(2, 4) + self.matches(3, 2) + self.matches(4, 1)
            earlier, tree = fd.bracket_split(self.rounds(cup))
        self.assertEqual([len(r.ties) for r in earlier], [5])           # five does not halve into four: stop there
        self.assertEqual([len(r.ties) for r in tree], [4, 2, 1])

    def test_a_competition_not_ending_in_a_single_final_has_no_tree(self):
        with mock.patch.dict(CLUBS, {n: (f"Club {n}", f"C{n}") for n in range(6, 17)}):
            cup = self.matches(1, 4) + self.matches(2, 3)                # ends in three ties: no one final
            earlier, tree = fd.bracket_split(self.rounds(cup))
        self.assertEqual((len(earlier), tree), (2, ()))
