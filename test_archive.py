# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for archive: the local fixture archive that every opened save is banked into.

Run:  .venv\\Scripts\\python -m unittest test_archive -v
"""

import contextlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

import archive
import datetime as dt
import itertools
from test_fm_data import D, fx


class ArchiveFileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "archive.sqlite"

    def connect(self):
        """A connection to the file that commits on success and is closed afterwards."""
        return contextlib.closing(sqlite3.connect(self.path))

    def version(self) -> int:
        with self.connect() as db:
            return db.execute("SELECT schema_version FROM meta").fetchone()[0]

    def test_opening_a_new_path_creates_the_file_at_the_current_schema(self):
        with archive.Archive.open(self.path):
            pass
        self.assertTrue(self.path.exists())
        self.assertEqual(self.version(), archive.SCHEMA_VERSION)

    def test_reopening_keeps_the_schema_and_the_data(self):
        with archive.Archive.open(self.path):
            pass
        with self.connect() as db:
            db.execute("INSERT INTO clubs (uid, name, short_name, nation_id) VALUES (1, 'Hull City', 'Hull', 5)")
            db.commit()
        with archive.Archive.open(self.path):
            pass
        self.assertEqual(self.version(), archive.SCHEMA_VERSION)
        with self.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM clubs").fetchone()[0], 1)

    def test_a_newer_schema_is_refused_and_left_alone(self):
        with archive.Archive.open(self.path):
            pass
        with self.connect() as db:
            db.execute("UPDATE meta SET schema_version = 99")
            db.commit()
        with self.assertRaises(archive.ArchiveError) as caught:
            archive.Archive.open(self.path)
        self.assertIn("newer", str(caught.exception))
        self.assertEqual(self.version(), 99)


def af(played=False, hg=None, ag=None, *, date=dt.date(2026, 11, 8), source=dt.date(2026, 11, 1), key=(12, 2026, 1, 2, 0),
       round_index=4):
    """An ArchivedFixture for the merge tests."""
    return archive.ArchivedFixture(
        key=key, date=date, kick_off=dt.time(15, 0), home_goals=hg, away_goals=ag, played=played,
        round_index=round_index, round_label=None, round_raw=None, home_name="Hull City", away_name="Derby County",
        source_date=source)


class MergeTests(unittest.TestCase):
    def test_a_fixture_with_nothing_before_it_is_added(self):
        result = archive.merge_fixture(None, af())
        self.assertEqual((result.outcome, result.fixture), ("added", af()))

    def test_the_same_fixture_again_is_unchanged(self):
        self.assertEqual(archive.merge_fixture(af(), af()).outcome, "unchanged")

    def test_a_later_save_moving_the_date_updates_it(self):
        moved = af(date=dt.date(2026, 11, 12), source=dt.date(2026, 11, 8))
        result = archive.merge_fixture(af(), moved)
        self.assertEqual((result.outcome, result.fixture.date), ("updated", dt.date(2026, 11, 12)))

    def test_a_played_result_is_never_replaced_by_not_played(self):
        played = af(True, 2, 1, source=dt.date(2026, 11, 1))
        later_unplayed = af(False, source=dt.date(2026, 12, 1))
        result = archive.merge_fixture(played, later_unplayed)
        self.assertTrue(result.fixture.played)
        self.assertEqual((result.fixture.home_goals, result.fixture.away_goals), (2, 1))

    def test_an_older_save_that_played_it_still_beats_a_newer_one_that_did_not(self):
        result = archive.merge_fixture(af(False, source=dt.date(2026, 12, 1)), af(True, 2, 1, source=dt.date(2026, 11, 1)))
        self.assertEqual((result.outcome, result.fixture.played), ("updated", True))

    def test_a_played_fixture_with_no_score_never_replaces_one_with_a_score(self):
        scored = af(True, 2, 1, source=dt.date(2026, 11, 1))
        no_score = af(True, None, None, source=dt.date(2026, 12, 1))
        self.assertEqual(archive.merge_fixture(scored, no_score).fixture.home_goals, 2)
        self.assertEqual(archive.merge_fixture(no_score, scored).fixture.home_goals, 2)

    def test_two_played_results_that_differ_are_a_conflict_and_the_later_save_is_kept(self):
        old, new = af(True, 2, 1, source=dt.date(2026, 11, 1)), af(True, 0, 0, source=dt.date(2026, 11, 8))
        result = archive.merge_fixture(old, new)
        self.assertEqual((result.outcome, result.fixture.home_goals), ("conflict", 0))

    def test_merging_is_the_same_whichever_way_round(self):
        samples = [
            af(), af(True, 2, 1), af(True, 0, 0, source=dt.date(2026, 11, 8)), af(True, None, None),
            af(False, date=dt.date(2026, 11, 12), source=dt.date(2026, 12, 1)),
            af(True, 2, 1, source=dt.date(2026, 11, 8), date=dt.date(2026, 11, 9)),
            af(True, 1, 2, source=dt.date(2026, 11, 8)),          # equal source date to another, different score
        ]
        for a, b in itertools.permutations(samples, 2):
            self.assertEqual(archive.merge_fixture(a, b).fixture, archive.merge_fixture(b, a).fixture, (a, b))


class FixtureKeyTests(unittest.TestCase):
    @staticmethod
    def keys(fixtures):
        return archive.fixture_keys(fixtures, lambda f: 12)

    def test_a_key_is_competition_season_home_away_and_meeting(self):
        (key,) = self.keys([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1)])
        self.assertEqual(key, (12, 2026, 1, 2, 0))

    def test_a_replay_is_the_pairs_second_meeting_by_round_and_a_moved_date_does_not_change_it(self):
        first = fx(D(2026, 11, 8), 1, 2, 1, 1, md=1)
        replay = fx(D(2026, 11, 18), 1, 2, None, None, md=2)
        moved = fx(D(2026, 11, 25), 1, 2, None, None, md=2)
        self.assertEqual(self.keys([first, replay])[1], (12, 2026, 1, 2, 1))
        self.assertEqual(self.keys([replay, first])[0], (12, 2026, 1, 2, 1))     # input order does not matter
        self.assertEqual(self.keys([first, moved])[1], (12, 2026, 1, 2, 1))     # nor does the date

    def test_a_fixture_with_an_unresolvable_team_has_no_key(self):
        from test_fm_data import unresolved_away
        keys = self.keys([unresolved_away(fx(D(2026, 8, 8), 1, 2, 1, 0, md=1)), fx(D(2026, 8, 9), 3, 4, 0, 0, md=1)])
        self.assertEqual([k is None for k in keys], [True, False])

    def test_competition_keys_use_the_database_id_or_a_negative_stand_in(self):
        self.assertEqual(archive.competition_key(8, 12), 12)
        self.assertEqual(archive.competition_key(8, None), -9)


if __name__ == "__main__":
    unittest.main()
