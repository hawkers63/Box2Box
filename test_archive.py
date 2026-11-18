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
import dataclasses
import datetime as dt
import itertools
from types import SimpleNamespace as NS
from unittest import mock

import fm_data as fd
from test_fm_data import D, fx, info, rules_listing, unresolved_away


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


def bank_dataset(fixtures, *, file="a.fm", game=D(2026, 9, 1), nations=None, rules=()):
    """A Dataset in the one competition (database id 12); every club is English (nation 5) unless `nations`
    (club uid -> nation id) says otherwise."""
    base = dataclasses.replace(info(), file_name=file, path=file, game_date=game)
    nations = nations or {i: 5 for i in range(1, 6)}
    clubs = [NS(uid=i, reputation=1, teams=(), nation_id=n) for i, n in nations.items()]
    return fd.build_dataset(base, fixtures, clubs=clubs, competitions=[NS(id=101, database_id=12)], rules=list(rules))


def thirty(score=(1, 0), *, until=30):
    """Thirty meetings of one pair (a long run of matchdays) with the given score, played up to matchday `until`."""
    return [fx(D(2026, 8, 1) + dt.timedelta(days=md), 1, 2, *(score if md <= until else (None, None)), md=md)
            for md in range(1, 31)]


class BankTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "archive.sqlite"

    def rows(self, path=None, table="fixtures"):
        order = "1, 2, 3, 4, 5" if table in ("fixtures", "conflicts") else "1"
        with contextlib.closing(sqlite3.connect(path or self.path)) as db:
            return db.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()

    def test_the_first_bank_adds_every_fixture_and_records_the_import(self):
        data = bank_dataset([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 15), 3, 4, 2, 2, md=2),
                             fx(D(2026, 8, 22), 1, 3, md=3)])
        with archive.Archive.open(self.path) as a:
            report = a.bank(data)
            records = a.imports()
        self.assertEqual((report.added, report.updated, report.conflicts, report.already_banked), (3, 0, 0, False))
        self.assertEqual(len(self.rows()), 3)
        self.assertEqual([(r.file_name, r.game_date, r.added) for r in records], [("a.fm", D(2026, 9, 1), 3)])

    def test_banking_the_same_save_again_is_a_no_op_that_says_so(self):
        data = bank_dataset([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1)])
        with archive.Archive.open(self.path) as a:
            a.bank(data)
            before = self.rows()
            report = a.bank(data)
            self.assertEqual(len(a.imports()), 1)
        self.assertTrue(report.already_banked)
        self.assertEqual(report.describe(), "Already banked.")
        self.assertEqual(self.rows(), before)

    def test_fixtures_with_an_unresolvable_team_are_skipped_and_counted(self):
        data = bank_dataset([unresolved_away(fx(D(2026, 8, 8), 1, 2, 1, 0, md=1)), fx(D(2026, 8, 15), 3, 4, 0, 0, md=2)])
        with archive.Archive.open(self.path) as a:
            report = a.bank(data)
        self.assertEqual((report.added, report.skipped_unresolved), (1, 1))
        self.assertEqual(len(self.rows()), 1)
        self.assertIn("1 skipped", report.describe())

    def test_the_report_reads_in_words(self):
        report = archive.BankReport(added=412, updated=3, unchanged=0, conflicts=0, skipped_unresolved=0,
                                    already_banked=False)
        self.assertEqual(report.describe(), "Banked: 412 new fixtures, 3 updated, 0 conflicts.")

    def test_two_saves_banked_in_either_order_give_the_same_archive(self):
        early = bank_dataset([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 15), 3, 4, None, None, md=2),
                              fx(D(2026, 8, 22), 1, 3, None, None, md=3)], file="early.fm", game=D(2026, 9, 1))
        late = bank_dataset([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 19), 3, 4, 2, 2, md=2),
                             fx(D(2026, 8, 22), 1, 3, None, None, md=3), fx(D(2026, 8, 29), 2, 4, 3, 1, md=4)],
                            file="late.fm", game=D(2026, 10, 1))
        one, two = Path(self.folder.name) / "one.sqlite", Path(self.folder.name) / "two.sqlite"
        with archive.Archive.open(one) as a:
            a.bank(early)
            a.bank(late)
        with archive.Archive.open(two) as a:
            a.bank(late)
            a.bank(early)
        self.assertEqual(self.rows(one), self.rows(two))
        self.assertEqual(self.rows(one, "clubs"), self.rows(two, "clubs"))
        moved = [r for r in self.rows(one) if r[3] == 4 and r[2] == 3][0]        # the rescheduled, then played, match
        self.assertEqual((moved[5], moved[9]), ("2026-08-19", 1))                # on its real date, and played

    def test_a_different_playthrough_is_refused_and_changes_nothing(self):
        with archive.Archive.open(self.path) as a:
            a.bank(bank_dataset(thirty((1, 0))))
            before = (self.rows(), self.rows(table="imports"))
            with self.assertRaises(archive.WorldMismatch) as caught:
                a.bank(bank_dataset(thirty((0, 3)), file="other.fm", game=D(2026, 10, 1)))
        self.assertIn("different playthrough", str(caught.exception))
        self.assertEqual((self.rows(), self.rows(table="imports")), before)

    def test_a_few_disagreements_among_many_overlaps_are_a_conflict_not_a_different_world(self):
        with archive.Archive.open(self.path) as a:
            a.bank(bank_dataset(thirty((1, 0))))
            data = thirty((1, 0))
            data[3] = fx(D(2026, 8, 5), 1, 2, 5, 5, md=4)
            report = a.bank(bank_dataset(data, file="b.fm", game=D(2026, 10, 1)))
        self.assertEqual(report.conflicts, 1)
        self.assertEqual(len(self.rows(table="conflicts")), 1)

    def test_a_failure_part_way_leaves_the_archive_as_it_was(self):
        data = bank_dataset([fx(D(2026, 8, 8), 1, 2, 1, 0, md=1), fx(D(2026, 8, 15), 3, 4, 2, 2, md=2),
                             fx(D(2026, 8, 22), 1, 3, 0, 0, md=3)])
        with archive.Archive.open(self.path) as a:
            real, calls = archive.merge_fixture, []

            def failing(old, new):
                calls.append(1)
                if len(calls) == 3:
                    raise RuntimeError("disk full")
                return real(old, new)

            with mock.patch.object(archive, "merge_fixture", failing), self.assertRaises(RuntimeError):
                a.bank(data)
            self.assertEqual(a.imports(), [])
        self.assertEqual((self.rows(), self.rows(table="imports"), self.rows(table="clubs")), ([], [], []))


class CompetitionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "archive.sqlite"

    LEAGUE = [fx(D(2026, 8, 8), 1, 3, 1, 0, md=1), fx(D(2026, 8, 8), 2, 5, 1, 1, md=1),
              fx(D(2026, 8, 15), 1, 4, 0, 4, md=2), fx(D(2026, 8, 15), 2, 3, 2, 2, md=2)]

    def only(self, **bank):
        with archive.Archive.open(self.path) as a:
            a.bank(bank_dataset(self.LEAGUE, **bank))
            (comp,) = a.competitions()
        return comp

    def test_a_competition_of_mostly_one_nation_belongs_to_it(self):
        comp = self.only(nations={1: 5, 2: 5, 3: 5, 4: 5, 5: 7})
        self.assertEqual((comp.key, comp.database_id, comp.nation, comp.continental, comp.seasons),
                         (12, 12, 5, False, (2026,)))

    def test_a_competition_of_several_nations_is_continental(self):
        comp = self.only(nations={1: 5, 2: 5, 3: 6, 4: 6, 5: 7})
        self.assertEqual((comp.nation, comp.continental), (None, True))

    def test_the_tie_break_codes_are_kept(self):
        comp = self.only(rules=[rules_listing(2, 0, 1)])
        self.assertEqual(comp.tie_breaks, (2, 0, 1))

    def test_the_newer_save_wins_on_a_competitions_metadata_whichever_is_banked_first(self):
        early = bank_dataset(self.LEAGUE, file="early.fm", game=D(2026, 9, 1), rules=[rules_listing(2, 0, 1)])
        late = bank_dataset(self.LEAGUE, file="late.fm", game=D(2026, 10, 1), rules=[rules_listing(0, 1)])
        for order in ((early, late), (late, early)):
            path = Path(self.folder.name) / f"{order[0].info.file_name}.sqlite"
            with archive.Archive.open(path) as a:
                for data in order:
                    a.bank(data)
                (comp,) = a.competitions()
            self.assertEqual(comp.tie_breaks, (0, 1), order[0].info.file_name)


if __name__ == "__main__":
    unittest.main()
