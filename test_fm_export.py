# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
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
import palette
from palette import COLOURS, FOCUS, ZONE_COLOURS
from test_fm_data import D, fx as fixture, info, team
from test_fm_review_ui import dataset

WHEN = dt.datetime(2026, 11, 14, 20, 30)


def request(**changes) -> fx.ExportRequest:
    """The Championship-like league from the UI tests: a stored table and 1/1/1 rules."""
    base = fx.ExportRequest(dataset(), 101, 2026, names={12: "Championship"}, focus=team(1), exported_at=WHEN)
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
        self.assertEqual(self.book.sheetnames, ["Table", "Grid", "Results", "Hull City", "About"])
        self.assertEqual(fx.workbook(fx.snapshot(request(focus=None))).sheetnames,
                         ["Table", "Grid", "Results", "About"])

    def test_table_has_zone_and_followed_team_colours(self):
        sheet = self.book["Table"]
        top = find_row(sheet, 1, "Pos") + 1
        self.assertEqual([sheet.cell(row=top + i, column=2).value for i in range(4)],
                         ["Hull City", "Derby County", "Leeds United", "Sheffield United"])   # the stored order
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
        row = find_row(sheet, 1, "Hull City")
        win = sheet.cell(row=row, column=column["Leeds"])
        self.assertEqual(win.value, "2-1")                # kept as text, never turned into a date
        self.assertEqual(win.fill.start_color.rgb, argb(COLOURS[fd.HOME_WIN][0]))
        unplayed = sheet.cell(row=row, column=column["Sheff Utd"])
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
        sheet = self.book["Hull City"]
        top = find_row(sheet, 1, "Date") + 1
        played = [(sheet.cell(row=r, column=7).value, sheet.cell(row=r, column=8).value,
                   sheet.cell(row=r, column=7).fill.start_color.rgb)
                  for r in range(top, sheet.max_row + 1) if sheet.cell(row=r, column=7).value]
        self.assertEqual(played, [("W", 3, argb(COLOURS["W"][0])), ("W", 6, argb(COLOURS["W"][0]))])

    def test_about_sheet_says_where_the_data_came_from(self):
        text = " ".join(str(cell.value) for row in self.book["About"].iter_rows() for cell in row if cell.value)
        for needle in ("Championship (competition id 101, database id 12)", "6 fixtures · 4 played", "fmsave 0",
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
        win = by_teams[("Hull City", "Leeds United")]
        self.assertEqual((win[0], win[5], win[6], win[7], win[8]), ("2026-08-08", 2, 1, "2–1", "Played"))
        missing = by_teams[("Leeds United", "Sheffield United")]
        self.assertEqual((missing[5], missing[7], missing[8]), ("", "n/a", "Played, score not recovered"))
        unplayed = by_teams[("Hull City", "Sheffield United")]
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


class ThemedExportTests(unittest.TestCase):
    """Exports wear the theme the window had when they were made, club colours included."""

    def test_the_workbook_takes_the_theme(self):
        hc = palette.HIGH_CONTRAST
        sheet = fx.workbook(fx.snapshot(request(theme=hc)))["Table"]
        top = find_row(sheet, 1, "Pos") + 1
        self.assertEqual(sheet.cell(row=top, column=1).fill.start_color.rgb, argb("#34d399"))   # promotion, a step lighter
        self.assertEqual(sheet.cell(row=top, column=2).fill.start_color.rgb, argb("#ffffff"))   # the followed team
        results = fx.workbook(fx.snapshot(request(theme=hc)))["Hull City"]
        wins = [c.fill.start_color.rgb for row in results.iter_rows(min_col=7, max_col=7) for c in row
                if c.value == "W"]                                  # the Res column of the followed team's sheet
        self.assertEqual(wins, [argb("#34d399")] * 2)

    def test_the_followed_teams_name_stays_readable_on_a_white_sheet(self):
        # High-Contrast's focus colour is white, so its name must not be written in white on white.
        sheet = fx.workbook(fx.snapshot(request(theme=palette.HIGH_CONTRAST)))["Results"]
        names = [c for row in sheet.iter_rows(min_col=3, max_col=3) for c in row if c.value == "Hull City"]
        self.assertTrue(names)
        for cell in names:
            ink = "#" + cell.font.color.rgb[2:]
            self.assertGreaterEqual(palette.contrast_ratio(ink, "#ffffff"), 4.5)

    def test_the_web_page_writes_the_theme_as_css_variables(self):
        cp = palette.CYBER_PITCH
        page = fx.web_page(fx.snapshot(request(theme=cp)))
        self.assertIn(f"--bg: {cp.table[0]};", page)
        self.assertIn(f".k-W {{ background: {cp.colours['W'][0]};", page)
        self.assertIn("--link: #22d3ee;", page)

    def test_the_default_theme_page_keeps_todays_colours(self):
        page = fx.web_page(fx.snapshot(request()))
        for value in ("--bg: #1b1b1b;", "--text: #e3e3e3;", "--muted: #a3a3a3;", "--section: #d8b44a;",
                      "--link: #60a5fa;", "--grid: #2b2b2b;", "--head: #151515;", "--field: #262626;",
                      "--field-border: #3f3f3f;", ".k-W { background: #059669; color: #ffffff; }",
                      "tr.heading td { background: #111e2e; color: #38bdf8;"):
            self.assertIn(value, page)

    def test_the_base_stylesheet_fixes_no_colour_of_its_own(self):
        # Every colour the page needs is a theme variable, so a theme can never leave one behind.
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,8}\b", fx._BASE_CSS), [])

    def test_the_club_tint_reaches_the_exports(self):
        me = palette.MIDNIGHT_EMERALD
        tinted = palette.with_club(me, palette.club_tint(me, ("#ee2737", "#ffffff")))
        snap = fx.snapshot(request(theme=tinted))
        sheet = fx.workbook(snap)["Table"]
        top = find_row(sheet, 1, "Pos") + 1
        self.assertEqual(sheet.cell(row=top, column=2).fill.start_color.rgb, argb(tinted.focus[0]))
        page = fx.web_page(snap)
        self.assertIn(f"tr.focus td, tr th.focus, thead th.focus {{ background: {tinted.focus[0]};", page)
        self.assertIn(f"--link: {tinted.link};", page)
        self.assertEqual(sheet.cell(row=top + 3, column=1).fill.start_color.rgb,       # Sheffield United, 4th
                         argb(tinted.zones[fd.ZONE_RELEGATION][0]))                    # zones keep their own colours

    def test_the_csv_is_plain_text_whatever_the_theme(self):
        plain = fx.csv_tables(fx.snapshot(request()))
        themed = fx.csv_tables(fx.snapshot(request(theme=palette.HIGH_CONTRAST)))
        self.assertEqual(plain, themed)


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


class PostTests(unittest.TestCase):
    """Copy for a post: the same content as Markdown (Reddit) and as an HTML table (rich editors)."""

    def snap(self, **changes):
        return fx.snapshot(request(**changes))

    def test_the_table_post_is_a_markdown_table_with_the_followed_club_in_bold(self):
        snap = self.snap()
        lines = fx.post_table(snap).markdown.splitlines()
        hull = snap.standings.groups[0][1][0]
        self.assertEqual(lines[0], f"**Championship {snap.season_label}**")
        self.assertEqual(lines[1], "")
        self.assertEqual(lines[2], "| Pos | Club | P | W | D | L | GF | GA | GD | Pts | Form |")
        self.assertEqual(lines[3], "|--:|:--|--:|--:|--:|--:|--:|--:|--:|--:|:--|")
        self.assertEqual(lines[4], f"| 1 | **Hull City** | 2 | 2 | 0 | 0 | 5 | 2 | +3 | 6 | {' '.join(hull.form)} |")

    def test_a_post_ends_with_the_in_game_date_and_the_coverage(self):
        snap = self.snap()
        last = fx.post_table(snap).markdown.splitlines()[-1]
        self.assertEqual(last, f"*In-game date {dict(snap.details)['In-game date']} · {snap.coverage.describe()}*")
        self.assertIn("no recoverable score", last)          # the league has one played match without a score

    def test_a_pipe_in_a_name_is_escaped_so_the_table_holds(self):
        snap = self.snap()
        (name, rows), *rest = snap.standings.groups
        odd = dataclasses.replace(rows[1], team="Brighton | Hove")
        standings = dataclasses.replace(snap.standings, groups=((name, (rows[0], odd, *rows[2:])), *rest))
        markdown = fx.post_table(dataclasses.replace(snap, standings=standings)).markdown
        self.assertIn("| Brighton \| Hove |", markdown)

    def test_the_table_post_has_the_same_table_in_plain_html(self):
        snap = self.snap()
        html = fx.post_table(snap).html
        self.assertTrue(html.startswith(f"<p><b>Championship {snap.season_label}</b></p>\n<table>\n<thead>"))
        self.assertIn("<tr><th>Pos</th><th>Club</th><th>P</th>", html)
        self.assertIn("<tr><td>1</td><td><b>Hull City</b></td><td>2</td>", html)
        self.assertTrue(html.endswith(f"</table>\n<p><i>{fx._post_footer(snap)}</i></p>"))

    def test_names_are_escaped_in_the_html(self):        # a guard: escaping arrived with the HTML table
        snap = self.snap()
        (name, rows), *rest = snap.standings.groups
        odd = dataclasses.replace(rows[1], team="Brighton & Hove <Albion>")
        standings = dataclasses.replace(snap.standings, groups=((name, (rows[0], odd, *rows[2:])), *rest))
        page = fx.post_table(dataclasses.replace(snap, standings=standings)).html
        self.assertIn("<td>Brighton &amp; Hove &lt;Albion&gt;</td>", page)

    def test_my_clubs_results_list_each_played_match_with_running_points(self):
        snap = self.snap()
        lines = fx.post_team_results(snap).markdown.splitlines()
        self.assertEqual(lines[0], f"**Hull City: Championship {snap.season_label}**")
        self.assertEqual(lines[2:6], ["| Date | Opponent | H/A | Score | Res | Pts |", "|:--|:--|:-:|:-:|:-:|--:|",
                                      "| Sat 8 Aug | Leeds United | H | 2-1 | W | 3 |",
                                      "| Sat 15 Aug | Derby County | A | 3-1 | W | 6 |"])

    def test_with_no_followed_club_there_is_no_club_post(self):    # a guard: the case arrived with the builder
        self.assertIsNone(fx.post_team_results(self.snap(focus=None)))

    def test_my_clubs_results_end_with_the_next_match(self):
        post = fx.post_team_results(self.snap())
        self.assertIn("\n\nNext: Sheffield United (H), Sat 26 Sep\n\n", post.markdown)
        self.assertIn("<p>Next: Sheffield United (H), Sat 26 Sep</p>", post.html)

    def test_a_played_match_with_no_recoverable_score_reads_n_a(self):     # a guard: arrived with the builder
        markdown = fx.post_team_results(self.snap(focus=team(2))).markdown
        self.assertIn("| Sheffield United | H | n/a |", markdown)

    def test_recent_results_are_the_latest_group_with_a_played_match(self):
        snap = self.snap()
        lines = fx.post_recent_results(snap).markdown.splitlines()
        self.assertTrue(lines[0].startswith(f"**Championship {snap.season_label}: "))
        self.assertEqual(lines[2:6], ["| Date | Home | Score | Away |", "|:--|--:|:-:|:--|",
                                      "| Sat 15 Aug | Derby County | 1-3 | Hull City |",
                                      "| Sat 15 Aug | Leeds United | n/a | Sheffield United |"])

    def test_a_season_with_nothing_played_has_no_recent_results(self):     # a guard: arrived with the builder
        self.assertIsNone(fx.post_recent_results(self.snap(season=2027)))

    def test_a_club_that_has_played_nothing_has_no_results_post(self):
        self.assertIsNone(fx.post_team_results(self.snap(season=2027)))     # Hull followed, nothing played yet
