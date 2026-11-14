"""Tests for fm_export: what each export holds, how it looks, and how it fails.

Run:  .venv\\Scripts\\python -m unittest -v
"""

import csv
import dataclasses
import datetime as dt
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import openpyxl

import fm_data as fd
import fm_export as fx
from palette import COLOURS, FOCUS, ZONE_COLOURS
from test_fm_data import D, fx as fixture, info, team
from test_fm_review_ui import dataset

WHEN = dt.datetime(2026, 11, 14, 20, 30)


def request(**changes) -> fx.ExportRequest:
    """The Championship-like league from the UI tests: a stored table and 1/1/1 rules."""
    base = fx.ExportRequest(dataset(), 8, 2026, names={12: "Championship"}, focus=team(1), exported_at=WHEN)
    return dataclasses.replace(base, **changes)


def argb(colour: str) -> str:
    return "FF" + colour.lstrip("#").upper()


def find_row(sheet, column: int, value) -> int:
    return next(r for r in range(1, sheet.max_row + 1) if sheet.cell(row=r, column=column).value == value)


class NamingTests(unittest.TestCase):
    def test_file_name_carries_competition_season_and_in_game_date(self):
        self.assertEqual(fx.file_stem("Championship", "2026/27", D(2026, 7, 16)), "Championship 2026-27 (2026-07-16)")
        self.assertEqual(fx.snapshot(request()).stem, "Championship 2026 (2026-09-01)")

    def test_file_name_is_safe_on_windows(self):
        stem = fx.file_stem('Cup: "Final"? <A/B> | C*.', "2026/27", None)
        self.assertIsNone(re.search(r'[<>:"/\\|?*]', stem))
        self.assertFalse(stem.endswith((".", " ")))

    def test_sheet_names_follow_excel_rules(self):
        name = fx._sheet_name("Brighton [U21]: A/B * C? and a very long name", {"Table"})
        self.assertIsNone(re.search(r"[\[\]:*?/\\]", name))
        self.assertLessEqual(len(name), 31)
        self.assertEqual(fx._sheet_name("results", {"Results"}), "Followed team")


class WorkbookTests(unittest.TestCase):
    def setUp(self):
        self.book = fx.workbook(fx.snapshot(request()))

    def test_sheets(self):
        self.assertEqual(self.book.sheetnames, ["Table", "Grid", "Results", "Sheffield United", "About"])
        self.assertEqual(fx.workbook(fx.snapshot(request(focus=None))).sheetnames,
                         ["Table", "Grid", "Results", "About"])

    def test_table_has_zone_and_followed_team_colours(self):
        sheet = self.book["Table"]
        top = find_row(sheet, 1, "Pos") + 1
        self.assertEqual([sheet.cell(row=top + i, column=2).value for i in range(4)],
                         ["Sheffield United", "Derby County", "Leeds United", "Hull City"])   # the stored order
        zones = [sheet.cell(row=top + i, column=1).fill.start_color.rgb for i in range(4)]
        self.assertEqual(zones, [argb(ZONE_COLOURS[fd.ZONE_PROMOTION][0]), argb(ZONE_COLOURS[fd.ZONE_PLAYOFF][0]),
                                 "00000000", argb(ZONE_COLOURS[fd.ZONE_RELEGATION][0])])
        self.assertEqual(sheet.cell(row=top, column=2).fill.start_color.rgb, argb(FOCUS[0]))
        self.assertEqual(sheet.cell(row=top, column=10).value, 6)                  # the game's points
        self.assertEqual(sheet.cell(row=top, column=9).number_format, "+0;-0;0")
        notes = " ".join(str(sheet.cell(row=r, column=1).value) for r in range(1, top))
        self.assertIn("game's rules", notes)
        self.assertIn("cyan = play-offs", notes)
        self.assertIn("unverified build", notes)

    def test_grid_cells_match_the_app(self):
        sheet = self.book["Grid"]
        top = find_row(sheet, 1, "Home \\ Away")
        column = {sheet.cell(row=top, column=c).value: c for c in range(2, sheet.max_column + 1)}
        row = find_row(sheet, 1, "Sheffield United")
        win = sheet.cell(row=row, column=column["Leeds"])
        self.assertEqual(win.value, "2-1")                # kept as text, never turned into a date
        self.assertEqual(win.fill.start_color.rgb, argb(COLOURS[fd.HOME_WIN][0]))
        unplayed = sheet.cell(row=row, column=column["Hull"])
        self.assertEqual((unplayed.value, unplayed.fill.start_color.rgb), ("26 Sep", argb(COLOURS[fd.SCHEDULED][0])))
        self.assertEqual(sheet.cell(row=row, column=1).fill.start_color.rgb, argb(FOCUS[0]))

    def test_results_have_real_dates_and_marked_scores(self):
        sheet = self.book["Results"]
        top = find_row(sheet, 1, "Date") + 1
        rows = [r for r in range(top, sheet.max_row + 1) if sheet.cell(row=r, column=3).value]
        first = rows[0]
        self.assertEqual(sheet.cell(row=first, column=1).value, D(2026, 8, 8))       # a real date, not text
        self.assertEqual(sheet.cell(row=first, column=1).number_format, "ddd d mmm yyyy")
        scores = {sheet.cell(row=r, column=4).value: sheet.cell(row=r, column=4).fill.start_color.rgb for r in rows}
        self.assertEqual(scores["n/a"], argb(COLOURS[fd.UNAVAILABLE][0]))
        self.assertEqual(scores["v"], argb(COLOURS[fd.SCHEDULED][0]))

    def test_followed_team_sheet_has_results_and_running_points(self):
        sheet = self.book["Sheffield United"]
        top = find_row(sheet, 1, "Date") + 1
        played = [(sheet.cell(row=r, column=7).value, sheet.cell(row=r, column=8).value,
                   sheet.cell(row=r, column=7).fill.start_color.rgb)
                  for r in range(top, sheet.max_row + 1) if sheet.cell(row=r, column=7).value]
        self.assertEqual(played, [("W", 3, argb(COLOURS["W"][0])), ("W", 6, argb(COLOURS["W"][0]))])

    def test_about_sheet_says_where_the_data_came_from(self):
        text = " ".join(str(cell.value) for row in self.book["About"].iter_rows() for cell in row if cell.value)
        for needle in ("Championship (competition id 8, database id 12)", "6 fixtures · 4 played", "fmsave 0",
                       "Unverified build", "1 promoted, 1 in the play-offs, 1 relegated", "14 November 2026 at 20:30"):
            self.assertIn(needle, text)


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.tables = fx.csv_tables(fx.snapshot(request()))

    def test_results_are_one_flat_row_per_fixture(self):
        header, *rows = self.tables["Results"]
        self.assertEqual(header[:8], ["Date", "Kick-off", "Round", "Home", "Away", "Home goals", "Away goals", "Score"])
        self.assertEqual(len(rows), 6)
        by_teams = {(r[3], r[4]): r for r in rows}
        win = by_teams[("Sheffield United", "Leeds United")]
        self.assertEqual((win[0], win[5], win[6], win[7], win[8]), ("2026-08-08", 2, 1, "2–1", "Played"))
        missing = by_teams[("Leeds United", "Hull City")]
        self.assertEqual((missing[5], missing[7], missing[8]), ("", "n/a", "Played, score not recovered"))
        unplayed = by_teams[("Sheffield United", "Hull City")]
        self.assertEqual((unplayed[7], unplayed[8]), ("", "To play"))

    def test_table_names_its_zones(self):
        header, *rows = self.tables["Table"]
        self.assertEqual(header[-1], "Zone")
        self.assertEqual([r[-1] for r in rows], ["promotion", "play-offs", "", "relegation"])

    def test_grid_scores_and_dates_survive_excel(self):
        header, *rows = self.tables["Grid"]
        self.assertEqual(header[0], "Home \\ Away")
        cells = {value for row in rows for value in row[1:] if value}
        self.assertIn("2–1", cells)                # an en dash, so Excel does not read a date
        self.assertIn("2026-09-26", cells)              # still to play: an ISO date
        self.assertNotIn("2-1", cells)

    def test_files_are_written_with_a_byte_order_mark(self):
        with tempfile.TemporaryDirectory() as folder:
            target = fx.export(fx.CSV, request(), Path(folder))
            self.assertEqual(sorted(p.name for p in target.iterdir()), ["About.csv", "Grid.csv", "Results.csv", "Table.csv"])
            raw = (target / "Results.csv").read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            with (target / "About.csv").open(encoding="utf-8-sig", newline="") as handle:
                about = dict(row for row in csv.reader(handle) if len(row) == 2)
            self.assertEqual(about["Season"], "2026")


class WebPageTests(unittest.TestCase):
    def test_page_is_standalone_and_has_every_section(self):
        page = fx.web_page(fx.snapshot(request()))
        for needle in ('id="table"', 'id="grid"', 'id="results"', 'id="team"', 'id="about"', 'id="filter"',
                       "td class=\"c z-promotion\"", 'class="k-home_win"', 'tr class="focus"', "<style>"):
            self.assertIn(needle, page)
        self.assertNotIn("<link", page)
        self.assertNotIn("src=", page)                  # nothing is fetched from anywhere
        self.assertEqual(page.count("<table"), page.count("</table>"))
        self.assertEqual(page.count("<tr"), page.count("</tr>"))

    def test_names_are_escaped(self):
        page = fx.web_page(fx.snapshot(request(names={12: 'Cup <b>"&"</b>'})))
        self.assertIn("Cup &lt;b&gt;&quot;&amp;&quot;&lt;/b&gt;", page)
        self.assertNotIn('<b>"&"</b>', page)

    def test_no_followed_team_means_no_team_section(self):
        self.assertNotIn('id="team"', fx.web_page(fx.snapshot(request(focus=None))))


class LargeCompetitionTests(unittest.TestCase):
    def test_too_many_teams_for_a_grid_still_exports(self):
        many = [dataclasses.replace(fixture(D(2026, 8, 8), 1, 2, 1, 0, comp=131, season=None),
                                    home_team_id=1000 + 2 * i, away_team_id=1001 + 2 * i) for i in range(31)]
        ds = fd.build_dataset(info(managed_uid=None), many)
        snap = fx.snapshot(fx.ExportRequest(ds, 131, 2026))
        self.assertIsNone(snap.grid)
        message = "62 teams, too many for a grid"
        self.assertIn(message, " ".join(str(c.value) for row in fx.workbook(snap)["Grid"].iter_rows() for c in row))
        self.assertIn(message, fx.csv_tables(snap)["Grid"][0][0])
        self.assertIn(message, fx.web_page(snap))


class FailureTests(unittest.TestCase):
    def test_a_workbook_open_in_excel_is_left_alone(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / f"{fx.snapshot(request()).stem}.xlsx"
            target.write_bytes(b"the earlier export")
            with mock.patch.object(fx.os, "replace", side_effect=PermissionError(13, "in use")):
                with self.assertRaises(fx.ExportFailed) as raised:
                    fx.export(fx.EXCEL, request(), Path(folder))
            self.assertIn("open in another program", str(raised.exception))
            self.assertEqual(target.read_bytes(), b"the earlier export")
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), [target.name])   # no partial file

    def test_a_folder_that_cannot_be_made_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            blocker = Path(folder) / "not a folder"
            blocker.write_text("x")
            with self.assertRaises(fx.ExportFailed):
                fx.export(fx.HTML, request(), blocker / "exports")


if __name__ == "__main__":
    unittest.main()
