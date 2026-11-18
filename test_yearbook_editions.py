# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for yearbook_editions: where a season's Yearbook editions live and when one is written.

Run:  .venv\\Scripts\\python -m unittest test_yearbook_editions -v
"""

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import archive
import fm_data as fd
import yearbook_editions as ed
from test_fm_data import D, fx
from test_yearbook import banked

NAMES = {12: "Premier League"}
FIXTURES = [fx(D(2026, 8, 8), 1, 2, 2, 0, md=1), fx(D(2026, 8, 15), 2, 1, 0, 1, md=2)]


class NamingTests(unittest.TestCase):
    def test_a_season_folder_turns_the_slash_into_a_hyphen(self):
        self.assertEqual(ed.season_folder(Path("X"), "2026/27"), Path("X") / "Yearbooks" / "2026-27")
        self.assertEqual(ed.season_folder(Path("X"), "2026"), Path("X") / "Yearbooks" / "2026")

    def test_a_file_is_named_from_the_in_game_date_not_the_clock(self):
        self.assertEqual(ed.edition_file_name("2026/27", dt.date(2026, 11, 12)), "Yearbook 2026-27 (in-game 12 Nov 2026).pdf")
        self.assertEqual(ed.edition_file_name("2026", dt.date(2027, 1, 3)), "Yearbook 2026 (in-game 3 Jan 2027).pdf")

    def test_a_season_with_no_banked_date_is_still_named(self):
        self.assertEqual(ed.edition_file_name("2026", None), "Yearbook 2026 (in-game date unknown).pdf")

    def test_editions_are_listed_newest_first_and_other_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            folder = ed.season_folder(Path(root), "2026/27")
            folder.mkdir(parents=True)
            for d in (dt.date(2026, 11, 12), dt.date(2026, 11, 19), dt.date(2026, 9, 3)):
                (folder / ed.edition_file_name("2026/27", d)).write_bytes(b"%PDF-")
            (folder / "Yearbook 2026-27 (in-game 1 Dec 2026).pdf.part").write_bytes(b"x")
            (folder / "notes.txt").write_text("x")
            self.assertEqual([e.date for e in ed.list_editions(Path(root), "2026/27")],
                             [dt.date(2026, 11, 19), dt.date(2026, 11, 12), dt.date(2026, 9, 3)])

    def test_no_folder_means_no_editions(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(ed.list_editions(Path(root), "2026/27"), [])


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def have(self, *dates):
        folder = ed.season_folder(self.root, "2026/27")
        folder.mkdir(parents=True, exist_ok=True)
        for d in dates:
            (folder / ed.edition_file_name("2026/27", d)).write_bytes(b"%PDF-")

    def plan(self, last, rebuild=False):
        return ed.plan_edition(self.root, "2026/27", last, rebuild=rebuild)

    def test_the_first_edition_is_just_saved(self):
        plan = self.plan(dt.date(2026, 11, 12))
        self.assertEqual((plan.action, plan.message), ("new", "Saved the 12 Nov 2026 edition."))

    def test_a_later_date_writes_a_new_file_and_leaves_the_older_edition_alone(self):
        self.have(dt.date(2026, 11, 12))
        plan = self.plan(dt.date(2026, 11, 19))
        self.assertEqual(plan.action, "new")
        self.assertEqual(plan.message, "Saved a new edition, 19 Nov 2026. The 12 Nov 2026 edition is unchanged.")
        self.assertNotEqual(plan.path, ed.list_editions(self.root, "2026/27")[0].path)

    def test_the_same_date_again_writes_nothing_and_says_so(self):
        self.have(dt.date(2026, 11, 12))
        plan = self.plan(dt.date(2026, 11, 12))
        self.assertEqual((plan.action, plan.message), ("already", "This edition is already saved."))

    def test_build_it_again_replaces_only_that_dates_file(self):
        self.have(dt.date(2026, 11, 12), dt.date(2026, 11, 5))
        plan = self.plan(dt.date(2026, 11, 12), rebuild=True)
        self.assertEqual((plan.action, plan.message), ("replace", "Updated the 12 Nov 2026 edition."))
        self.assertEqual(plan.path.name, ed.edition_file_name("2026/27", dt.date(2026, 11, 12)))

    def test_a_missing_file_with_rebuild_is_just_a_new_edition(self):
        self.assertEqual(self.plan(dt.date(2026, 11, 12), rebuild=True).action, "new")


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.TemporaryDirectory()
        self.addCleanup(self.out.cleanup)
        self.root = Path(self.out.name)
        self.book, self.folder = banked(FIXTURES, game=D(2026, 8, 15))
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(self.book.close)

    @staticmethod
    def fake_render(built, path):
        Path(path).write_bytes(b"%PDF-" + built.season_label.encode())

    def save(self, **kw):
        with mock.patch.object(ed.yearbook_pdf, "render", side_effect=self.fake_render) as render:
            plan = ed.save_edition(self.book, 2026, NAMES, self.root, **kw)
        return plan, render

    def test_the_first_save_writes_the_dated_file_in_the_season_folder(self):
        plan, _ = self.save()
        self.assertEqual(plan.path, ed.season_folder(self.root, "2026") / "Yearbook 2026 (in-game 15 Aug 2026).pdf")
        self.assertTrue(plan.path.is_file())

    def test_saving_the_same_coverage_again_builds_nothing(self):
        self.save()
        plan, render = self.save()
        self.assertEqual(plan.action, "already")
        render.assert_not_called()

    def test_build_it_again_renders_over_the_same_file(self):
        first, _ = self.save()
        plan, render = self.save(rebuild=True)
        self.assertEqual((plan.action, plan.path), ("replace", first.path))
        render.assert_called_once()

    def test_a_failed_build_leaves_every_edition_as_it_was(self):
        first, _ = self.save()
        before = first.path.read_bytes()
        with mock.patch.object(ed.yearbook_pdf, "render", side_effect=RuntimeError("out of paper")):
            with self.assertRaises(RuntimeError):
                ed.save_edition(self.book, 2026, NAMES, self.root, rebuild=True)
        self.assertEqual(first.path.read_bytes(), before)
        self.assertEqual([p.name for p in first.path.parent.iterdir()], [first.path.name])


if __name__ == "__main__":
    unittest.main()
