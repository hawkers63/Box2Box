"""Tests for fm_data, using fmsave's real Fixture record with made-up matches.

Run:  .venv\\Scripts\\python -m unittest -v
"""

import dataclasses
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from fmsave import CodedValue, CompetitionRound, Fixture

import fm_data as fd

CLUBS = {
    1: ("Sheffield United", "Sheff Utd"),
    2: ("Leeds United", "Leeds"),
    3: ("Hull City", "Hull"),
    4: ("Derby County", "Derby"),
    5: ("Wrexham", "Wrexham"),
}
D = dt.date


def team(club, slot=0):
    return club * 100 + slot


def fx(day, home, away, hg=None, ag=None, *, played=None, comp=8, season=2026, md=None,
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


class SeasonTests(unittest.TestCase):
    def test_labels_for_split_and_calendar_year_seasons(self):
        self.assertEqual(fd.season_label(2026, [fx(D(2026, 8, 8), 1, 2), fx(D(2027, 5, 1), 2, 1)]), "2026/27")
        self.assertEqual(fd.season_label(2026, [fx(D(2026, 3, 1), 1, 2), fx(D(2026, 11, 1), 2, 1)]), "2026")

    def test_friendly_without_a_stored_season_uses_a_july_boundary(self):
        self.assertEqual(fd.season_key(fx(D(2027, 1, 10), 1, 2, season=None)), 2026)
        self.assertEqual(fd.season_key(fx(D(2026, 7, 10), 1, 2, season=None)), 2026)

    def test_default_season_is_latest_played_else_first_to_come(self):
        ds = fd.build_dataset(info(), LEAGUE + [fx(D(2027, 8, 7), 1, 2, season=2027, md=1)])
        self.assertEqual(fd.default_season(ds, 8), 2026)
        unplayed = fd.build_dataset(info(), [fx(D(2026, 8, 8), 1, 2, md=1), fx(D(2027, 8, 7), 1, 2, season=2027, md=1)])
        self.assertEqual(fd.default_season(unplayed, 8), 2026)


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
        self.assertEqual(labels[team(1)], "Sheffield United")
        self.assertEqual(labels[team(1, 1)], "Sheffield United (team 2)")
        self.assertEqual(labels[team(2)], "Leeds United")

    def test_youth_league_shows_plain_names(self):
        labels = fd.team_labels([fx(D(2026, 8, 1), 1, 2, home_slot=1, away_slot=1)])
        self.assertEqual(labels[team(1, 1)], "Sheffield United")

    def test_short_labels(self):
        self.assertEqual(fd.team_labels(LEAGUE, short=True)[team(1)], "Sheff Utd")


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
        late = [r for r in by_week if r.home == "Sheffield United" and r.away == "Hull City"][0]
        self.assertEqual((late.date, late.round), ("Sat 26 Sep", "Md 3"))
        by_matchday = fd.timeline(LEAGUE, self.labels, group_by=fd.GROUP_BY_MATCHDAY)
        self.assertEqual(self.headings(by_matchday), ["Matchday 1", "Matchday 2", "Matchday 3"])
        md3 = by_matchday[by_matchday.index(next(r for r in by_matchday if r.heading.startswith("Matchday 3"))) + 1:]
        self.assertEqual([r.home for r in md3], ["Derby County", "Sheffield United"])

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
        result = fd.standings(ds, 8, 2026, fd.season_fixtures(ds, 8, 2026), fd.team_labels(LEAGUE))
        self.assertFalse(result.stored)
        self.assertIn("incomplete", result.note)
        rows = {r.team: r for r in result.groups[0][1]}
        self.assertEqual(rows["Sheffield United"].position, 1)
        self.assertEqual((rows["Sheffield United"].played, rows["Sheffield United"].points), (2, 6))
        self.assertEqual(rows["Sheffield United"].form, "WW")
        self.assertEqual(rows["Leeds United"].played, 1)       # the unscored match is left out
        self.assertEqual(rows["Hull City"].form, "D")

    def test_competition_with_nothing_played_lists_every_team_on_zero(self):
        fixtures = [fx(D(2026, 8, 8), 1, 2, md=1), fx(D(2026, 8, 8), 3, 4, md=1), fx(D(2026, 8, 15), 5, 1, md=2)]
        ds = fd.build_dataset(info(), fixtures)
        result = fd.standings(ds, 8, 2026, fixtures, fd.team_labels(fixtures))
        self.assertEqual(len(result.groups[0][1]), 5)
        self.assertTrue(all(r.played == 0 and r.points == 0 for r in result.groups[0][1]))

    def test_stored_table_is_used_for_the_latest_played_season_only(self):
        stored = NS(competition_id=8, rows=(row(1, 1, 2, 2, 0, 0, 5, 2, 9), row(4, 2), row(2, 3), row(3, 4)))
        ds = fd.build_dataset(info(), LEAGUE + [fx(D(2027, 8, 7), 1, 2, season=2027, md=1)], tables=[stored])
        labels = fd.team_labels(LEAGUE)
        current = fd.standings(ds, 8, 2026, fd.season_fixtures(ds, 8, 2026), labels)
        self.assertTrue(current.stored)
        self.assertEqual(current.groups[0][1][0].points, 9)     # the game's number, deductions and all
        self.assertEqual(current.groups[0][1][0].form, "WW")
        next_season = fd.standings(ds, 8, 2027, fd.season_fixtures(ds, 8, 2027), labels)
        self.assertFalse(next_season.stored)

    def test_stored_table_with_unknown_clubs_is_not_trusted(self):
        stored = NS(competition_id=8, rows=(row(1, 1), row(5, 2)))   # Wrexham is not in this league
        ds = fd.build_dataset(info(), LEAGUE, tables=[stored])
        self.assertFalse(fd.standings(ds, 8, 2026, fd.season_fixtures(ds, 8, 2026), {}).stored)

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
        fxs = fd.season_fixtures(ds, 8, 2026)

        home = fd.standings(ds, 8, 2026, fxs, labels, split=fd.SPLIT_HOME)
        self.assertEqual(home.note, "Home matches only. 3 points for a win, 1 for a draw.")
        home_rows = {r.team: r for r in home.groups[0][1]}
        self.assertEqual(home_rows["Sheffield United"].played, 1)
        self.assertEqual(home_rows["Sheffield United"].won, 1)
        self.assertEqual(home_rows["Leeds United"].played, 0)

        away = fd.standings(ds, 8, 2026, fxs, labels, split=fd.SPLIT_AWAY)
        self.assertEqual(away.note, "Away matches only. 3 points for a win, 1 for a draw.")
        away_rows = {r.team: r for r in away.groups[0][1]}
        self.assertEqual(away_rows["Sheffield United"].played, 1)
        self.assertEqual(away_rows["Sheffield United"].won, 1)
        self.assertEqual(away_rows["Leeds United"].played, 1)

        form = fd.standings(ds, 8, 2026, fxs, labels, split=fd.SPLIT_FORM)
        self.assertIn("Form guide", form.note)
        self.assertEqual(len(form.groups[0][1]), 4)


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
        fixtures = league_season(8, D(2026, 8, 8)) + league_season(9, D(2026, 8, 9))
        rules = [rules_block(2, 6, 3, first_day=D(2026, 8, 8)), rules_block(2, 4, 4, first_day=D(2026, 8, 9))]
        ds = fd.build_dataset(info(), fixtures, rules=rules)
        self.assertEqual(ds.zone_rules[8], fd.ZoneRules(2, 6, 3, matched_by_calendar=True))
        self.assertEqual(ds.zone_rules[9], fd.ZoneRules(2, 4, 4, matched_by_calendar=True))

    def test_numbered_rounds_match_their_matchday(self):
        ds = fd.build_dataset(info(), league_season(8, D(2026, 8, 8)),
                              rules=[rules_block(2, 6, 3, first_day=D(2026, 8, 8), numbered=True)])
        self.assertEqual(ds.zone_rules[8].playoff, 6)

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
        fixtures = (league_season(8, D(2026, 8, 8)) + league_season(50, D(2026, 8, 8), matchdays=3)
                    + league_season(60, D(2026, 8, 10)))
        rules = [
            rules_block(2, 6, 3, comp=8),                                   # linked by fmsave
            rules_block(1, 0, 1, first_day=D(2026, 8, 8)),                  # fits 8 too: ignored
            rules_block(1, 0, 0, first_day=D(2026, 8, 8), rounds=3),        # too short to trust
            rules_block(4, 0, 0, first_day=D(2027, 1, 2)),                  # no calendar fits
            rules_block(None, 2, 2, comp=60),                               # unreadable places
        ]
        ds = fd.build_dataset(info(), fixtures, rules=rules)
        self.assertEqual(ds.zone_rules, {8: fd.ZoneRules(2, 6, 3)})

    def test_standings_mark_zones_on_the_overall_table_only(self):
        rules = [NS(competition_id=8, promotion_places=1, playoff_places=1, relegation_places=1, rounds=())]
        ds = fd.build_dataset(info(), LEAGUE, rules=rules)
        fxs, labels = fd.season_fixtures(ds, 8, 2026), fd.team_labels(LEAGUE)
        overall = fd.standings(ds, 8, 2026, fxs, labels)
        self.assertEqual([r.zone for r in overall.groups[0][1]],
                         [fd.ZONE_PROMOTION, fd.ZONE_PLAYOFF, fd.ZONE_NONE, fd.ZONE_RELEGATION])
        self.assertIn("game's rules", overall.zones_note)
        self.assertIn("1 in the play-offs", overall.zones_note)
        home = fd.standings(ds, 8, 2026, fxs, labels, split=fd.SPLIT_HOME)
        self.assertEqual({r.zone for r in home.groups[0][1]}, {fd.ZONE_NONE})
        self.assertEqual(home.zones_note, "")

    def test_estimated_zones_say_so(self):
        # 20 teams and no rules: the zones are a guess from the league's size, and the note says so.
        fixtures = [dataclasses.replace(fx(D(2026, 8, 8), 1, 2, md=1), home_team_id=1000 + 2 * i,
                                        away_team_id=1001 + 2 * i) for i in range(10)]
        ds = fd.build_dataset(info(), fixtures)
        result = fd.standings(ds, 8, 2026, fd.season_fixtures(ds, 8, 2026), fd.team_labels(fixtures))
        self.assertEqual(len(result.groups[0][1]), 20)
        self.assertIn("estimated", result.zones_note)


class DatasetTests(unittest.TestCase):
    def test_managed_club_competitions_come_first(self):
        fixtures = LEAGUE + [
            fx(D(2026, 8, 9), 2, 3, 1, 0, comp=50),                       # someone else's league
            fx(D(2026, 8, 10), 1, 4, 0, 0, comp=60, home_slot=1, away_slot=1),  # our youth side
        ]
        ds = fd.build_dataset(info(), fixtures, clubs=[club(1, slots=(0, 1)), club(2, 9000), club(3), club(4)])
        self.assertEqual([c.id for c in ds.competitions], [8, 60, 50])
        self.assertTrue(ds.by_id[8].managed_first_team)
        self.assertFalse(ds.by_id[60].managed_first_team)
        self.assertEqual(ds.first_team_id, team(1))
        self.assertEqual(ds.by_id[50].top_clubs, ("Leeds", "Hull"))

    def test_managed_teams_fall_back_to_fixtures_without_a_club_table(self):
        ds = fd.build_dataset(info(), LEAGUE)
        self.assertEqual(ds.first_team_id, team(1))
        self.assertTrue(ds.by_id[8].is_yours)

    def test_search_finds_clubs_and_given_names(self):
        ds = fd.build_dataset(info(), LEAGUE, competitions=[NS(id=8, database_id=777)])
        comp = ds.by_id[8]
        self.assertTrue(fd.matches_search(comp, {}, "derby"))
        self.assertFalse(fd.matches_search(comp, {}, "championship"))
        self.assertTrue(fd.matches_search(comp, {777: "Championship"}, "champ"))
        self.assertEqual(fd.competition_list_label(comp, {}), "[8] Derby, Hull, Leeds")

    def test_competitions_summary_and_categories(self):
        ds = fd.build_dataset(info(), LEAGUE, competitions=[NS(id=8, database_id=777)])
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
