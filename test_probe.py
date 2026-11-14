"""Smoke test for fm27_probe.py using fake records in place of a real save."""
import datetime as dt
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import fmsave
import fm27_probe

names = ["Sheffield United", "Leeds", "Hull", "Derby"]
clubs = [NS(uid=i, name=n, short_name=n[:5], teams=(NS(team_id=100 + i, is_affiliate=False),)) for i, n in enumerate(names)]


def fx(d, h, a, hg, ag, played=True, comp=7, rnd=0):
    return NS(competition_id=comp, season_start_year=2026, date=d, kick_off_time=dt.time(15, 0), round_index=rnd,
              home_team_id=100 + h, away_team_id=100 + a, home_club_name=names[h], away_club_name=names[a],
              home_club_short_name=names[h][:5], away_club_short_name=names[a][:5],
              home_goals=hg, away_goals=ag, played=played)


D = dt.date
fixtures = [
    fx(D(2026, 8, 8), 0, 1, 2, 1), fx(D(2026, 8, 8), 2, 3, 0, 0),
    fx(D(2026, 8, 15), 1, 0, None, None),          # played, score missing
    fx(D(2026, 8, 22), 0, 1, 1, 1),                # repeated pairing
    fx(D(2026, 9, 1), 3, 0, None, None, played=False),
    fx(None, 2, 0, None, None, played=False, comp=None),
]
row = NS(position=1, club_name="Sheffield United", team_id=100, played=3, won=1, drawn=1, lost=0,
         goals_for=3, goals_against=2, points=4)
stat = NS(competition_id=7, home_team_id=100, away_team_id=101, date=D(2026, 8, 8))


class FakeSave:
    info = NS(game="FM27", build="27.0.1+999", known_build=False, game_date=D(2026, 9, 2))

    def __enter__(self):
        warnings.warn("borrowed layout", fmsave.UnknownBuildWarning)
        return self

    def __exit__(self, *a):
        return False

    def managed_clubs(self):
        return [NS(club_uid=0, club_name="Sheffield United")]

    def clubs(self):
        return clubs

    def fixtures(self):
        return fixtures

    def competitions(self):
        return [NS(id=7, name=None)]

    def league_tables(self):
        return [NS(competition_id=7, club_count=4, rows=(row,))]

    def team_match_stats(self):
        raise fmsave.UnsupportedGameError("no report layout")


class ProbeSmokeTest(unittest.TestCase):
    def test_probe_output(self):
        with tempfile.TemporaryDirectory() as folder:
            out_path = Path(folder) / "probe_report.txt"
            with mock.patch.object(fmsave, "open", lambda path, **kw: FakeSave()):
                with mock.patch.object(sys, "argv", ["fm27_probe.py", "fake.fm", "--out", str(out_path)]):
                    fm27_probe.main()
            text = out_path.read_text(encoding="utf-8")
            for needle in ["Played, result unavailable:   1", "pairings that occur more than once: 1",
                           "result unavailable", "NO - layouts", "UnknownBuildWarning", "Sheffield United  2-1"]:
                self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
