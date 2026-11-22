# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Smoke test for the Box2Box window with a small made-up dataset, and its About screen.

Run:  .venv\\Scripts\\python -m unittest -v
"""

import ctypes
import dataclasses
import json
import sys
import sqlite3
import tempfile
import time
import tkinter as tk
import unittest
from tkinter import font as tkfont
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import customtkinter as ctk

import club_colours
import command_palette
import archive
import fm_data as fd
import fm_review
import inspector
import yearbook
import yearbook_editions
import yearbook_read
import yearbook_reader_ui
import palette
import test_fm_data
from test_fm_data import LEAGUE, D, club, fx, info, match_stats, row, team, unresolved_away

HULL_LEEDS_XG = match_stats(LEAGUE[0], 1.82, 0.45)     # the report the save kept for Hull 2-1 Leeds

# The first line of LICENSE, word for word.
COPYRIGHT = "Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved."


def texts_in(widget) -> list[str]:
    """The text of every label in a window, in the order they were built."""
    found = []
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkLabel):
            found.append(child.cget("text"))
        found += texts_in(child)
    return found


def dataset(match_stats=None, extra=()) -> fd.Dataset:
    fixtures = LEAGUE + list(extra) + [
        fx(D(2027, 8, 7), 1, 2, season=2027, md=1),                          # next season, unplayed
        fx(D(2026, 7, 20), 1, 5, 2, 2, comp=131, season=None),               # a friendly
        fx(D(2026, 8, 10), 1, 4, 1, 0, comp=60, home_slot=1, away_slot=1),   # youth league
        unresolved_away(fx(D(2026, 8, 9), 2, 3, 1, 0, comp=70, md=1)),       # a team the save can't resolve
    ]
    stored = NS(competition_id=101, rows=(row(1, 1, 2, 2, 0, 0, 5, 2, 6), row(4, 2), row(2, 3), row(3, 4)))
    rules = [NS(competition_id=101, promotion_places=1, playoff_places=1, relegation_places=1, rounds=())]
    return fd.build_dataset(info(), fixtures, clubs=[club(1, slots=(0, 1)), club(2), club(3), club(4), club(5)],
                            competitions=[NS(id=101, database_id=12), NS(id=102, database_id=13)], tables=[stored], rules=rules,
                            match_stats=match_stats)


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        folder = Path(self.folder.name)
        patches = [
            mock.patch.object(fm_review, "SETTINGS_PATH", folder / "settings.json"),
            mock.patch.object(fm_review, "NAMES_PATH", folder / "names.csv"),
            mock.patch.object(fm_review, "ERROR_LOG", folder / "errors.log"),
            mock.patch.object(fm_review, "ARCHIVE_PATH", folder / "archive.sqlite"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        ctk.set_appearance_mode("dark")
        self.app = fm_review.FMReviewApp()
        self.app.geometry("1300x800+-4000+0")
        self.app.report_callback_exception = lambda *exc: (_ for _ in ()).throw(exc[1])
        self.app.update()

    def tearDown(self):
        bank = getattr(self.app, "_bank_thread", None)             # a banking thread must not outlive its folder
        if bank is not None:
            bank.join(10)
        # Let CustomTkinter's own short timers (window icons, scaling checks) run first.
        stop = time.monotonic() + 0.5
        while time.monotonic() < stop:
            self.app.update()
            time.sleep(0.02)
        self.app.destroy()
        self.folder.cleanup()

    def test_every_view_renders_and_follows_the_team(self):
        app = self.app
        app.install_dataset(dataset())
        app.update()
        self.assertEqual(app.comp_id, 101)                    # managed club's league first
        self.assertEqual(app.season, 2026)
        self.assertEqual(app.team_box.get(), "Hull City")
        for view in fm_review.VIEWS:
            app.set_view(view)
            for grouping in fm_review.GROUPINGS:
                app._on_group(grouping)
                app.update()
        app.set_view("Table")
        self.assertEqual(app.sheets["Table"].get_cell_data(0, 9), 6)   # the stored table's points
        app.set_view("Results")
        app.set_focus(None)
        app._on_team_typed()
        app.update()
        self.assertEqual(app.team_box.get(), fm_review.ALL_TEAMS)
        app.team_box.set("sheffield")
        app._on_team_typed()
        self.assertEqual(app.labels[app.focus], "Sheffield United")
        self.assertEqual(list(app.season_by_label), ["2027", "2026"])     # newest first
        app._on_season("2027")
        app.update()
        self.assertEqual(app.season, 2027)
        self.assertEqual(app.labels[app.focus], "Hull City")   # Sheffield United have no 2027 fixture yet
        for comp in app.dataset.competitions:
            app.select_competition(comp.id)
            for view in fm_review.VIEWS:
                app.set_view(view)
                app.update()
                for analysis in fm_review.ANALYSES if view == fm_review.ANALYSIS else ():
                    app._on_analysis(analysis)
                    app.update()

    def test_analysis_shows_form_positions_and_expected_goals(self):
        app = self.app
        app.install_dataset(dataset(match_stats=HULL_LEEDS_XG))
        app.set_view(fm_review.ANALYSIS)
        app.update()
        sheet = app.sheets[fm_review.ANALYSIS]
        self.assertEqual(app.analysis_switch.get(), "Form")
        self.assertEqual(sheet.get_cell_data(0, 0), "Hull City")                  # the stored table's order
        self.assertEqual([sheet.get_cell_data(0, c) for c in range(1, 6)], ["", "", "", "W", "W"])
        self.assertNotIn("", sheet.headers())          # tksheet shows a column letter for an empty header
        self.assertIn("Form from 3 scored matches", app.note_label.cget("text"))
        self.assertIn("W 3-1 at Derby County", app.detail_label.cget("text"))     # the followed team's form
        app._on_analysis("Positions")
        app.update()
        self.assertEqual([sheet.get_cell_data(0, c) for c in range(3)], ["Hull City", 1, 1])
        self.assertIn("after each matchday", app.note_label.cget("text"))
        app._on_analysis("xG")
        app.update()
        self.assertEqual([sheet.get_cell_data(0, c) for c in range(3)], ["Hull City", "1 of 2", "1.82"])
        self.assertIn("Expected goals for 1 of 4 played matches", app.note_label.cget("text"))
        sheet.select_cell(1, 0, redraw=False, run_binding_func=False)
        app._on_sheet_select(fm_review.ANALYSIS)
        self.assertEqual(app.focus, team(4))                 # a click follows the team, as in the table

    def test_positions_mode_switch_is_hidden_when_only_one_season(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view(fm_review.ANALYSIS)
        app._on_analysis("Positions")
        app.update()
        self.assertEqual(app.positions_mode_switch.winfo_manager(), "")

    def _install_two_season_dataset(self):
        ds = fd.build_dataset(
            info(),
            test_fm_data.TWO_SEASON_LEAGUE,
            clubs=[club(1), club(2), club(3)],
            competitions=[NS(id=101, database_id=12)],
        )
        self.app.install_dataset(ds)
        return ds

    def test_positions_mode_switch_is_shown_with_both_segments_when_a_comparison_is_available(self):
        app = self.app
        self._install_two_season_dataset()
        app.set_view(fm_review.ANALYSIS)
        app._on_analysis("Positions")
        app.update()
        self.assertEqual(app.positions_mode_switch.winfo_manager(), "pack")
        self.assertEqual(list(app.positions_mode_switch.cget("values")), list(fm_review.POSITIONS_MODES))
        self.assertEqual(app.positions_mode_switch.get(), "Matchday chart")

    def test_season_vs_season_fills_the_sheet_with_the_expected_headers_and_first_row(self):
        app = self.app
        self._install_two_season_dataset()
        app.set_view(fm_review.ANALYSIS)
        app._on_analysis("Positions")
        app._on_positions_mode("Season vs season")
        app.update()
        sheet = app.sheets[fm_review.ANALYSIS]
        self.assertEqual(list(sheet.headers()),
                         ["Team", "2027 Pos", "2027 Pts", "2026 Pos", "2026 Pts", "Δ Pos"])
        # Row 0: Sheffield United finished 2nd in 2026 (5 pts) and leads 2027 on 3 pts, a one-place climb.
        self.assertEqual([sheet.get_cell_data(0, c) for c in range(6)],
                         ["Sheffield United", 1, 3, 2, 5, "+1"])

    def test_switching_away_from_positions_hides_the_mode_switch(self):
        app = self.app
        self._install_two_season_dataset()
        app.set_view(fm_review.ANALYSIS)
        app._on_analysis("Positions")
        app.update()
        self.assertEqual(app.positions_mode_switch.winfo_manager(), "pack")
        app._on_analysis("Form")
        app.update()
        self.assertEqual(app.positions_mode_switch.winfo_manager(), "")

    def test_single_season_competition_still_shows_the_existing_matchday_panel(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view(fm_review.ANALYSIS)
        app._on_analysis("Positions")
        app.update()
        self.assertEqual(app.positions_mode_switch.winfo_manager(), "")
        self.assertIn("after each matchday", app.note_label.cget("text"))

    def test_switching_positions_mode_keeps_competition_season_and_followed_club(self):
        app = self.app
        self._install_two_season_dataset()
        app.set_focus(team(2))                 # follow Leeds
        app._on_season("2027")
        app.set_view(fm_review.ANALYSIS)
        app._on_analysis("Positions")
        app.update()
        self.assertEqual((app.comp_id, app.season, app.focus), (101, 2027, team(2)))
        app._on_positions_mode("Season vs season")
        app.update()
        self.assertEqual((app.comp_id, app.season, app.focus), (101, 2027, team(2)))
        app._on_positions_mode("Matchday chart")
        app.update()
        self.assertEqual((app.comp_id, app.season, app.focus), (101, 2027, team(2)))

    def test_season_vs_season_highlights_the_followed_club_row(self):
        app = self.app
        self._install_two_season_dataset()
        app.set_focus(team(1))                 # follow Hull City
        app.set_view(fm_review.ANALYSIS)
        app._on_analysis("Positions")
        app._on_positions_mode("Season vs season")
        app.update()
        sheet = app.sheets[fm_review.ANALYSIS]
        # Hull is row 2 (Sheffield, Leeds, Hull by 2027 position).
        self.assertEqual(sheet.get_cell_data(2, 0), "Hull City")
        self.assertEqual(sheet.props(2, 0, "highlight").bg, app.view_theme.focus[0])

    def test_season_vs_season_paints_each_seasons_zone_fill(self):
        app = self.app
        rules = [NS(competition_id=101, promotion_places=1, playoff_places=0, relegation_places=1, rounds=())]
        ds = fd.build_dataset(info(), test_fm_data.TWO_SEASON_LEAGUE,
                              clubs=[club(1), club(2), club(3)],
                              competitions=[NS(id=101, database_id=12)],
                              rules=rules)
        app.install_dataset(ds)
        app.set_view(fm_review.ANALYSIS)
        app._on_analysis("Positions")
        app._on_positions_mode("Season vs season")
        app.update()
        sheet = app.sheets[fm_review.ANALYSIS]
        theme = app.view_theme
        # Row 0 is Sheffield (2027 Pos 1 → promotion, 2026 Pos 2 → no zone).
        self.assertEqual(sheet.props(0, 1, "highlight").bg, theme.zones[fd.ZONE_PROMOTION][0])
        # Row 2 is Hull (2027 Pos 3 → relegation, 2026 Pos 1 → promotion).
        self.assertEqual(sheet.props(2, 1, "highlight").bg, theme.zones[fd.ZONE_RELEGATION][0])
        self.assertEqual(sheet.props(2, 3, "highlight").bg, theme.zones[fd.ZONE_PROMOTION][0])

    def test_results_show_expected_goals_where_the_save_kept_a_report(self):
        app = self.app
        app.install_dataset(dataset(match_stats=HULL_LEEDS_XG))
        app.set_view("Results")
        app.update()
        sheet = app.sheets["Results"]
        found = [i for i, r in enumerate(app.result_rows) if r.fixture is LEAGUE[0]]
        self.assertEqual(sheet.get_cell_data(found[0], 4), "1.82-0.45")
        sheet.select_cell(found[0], 2, redraw=False, run_binding_func=False)
        app._on_sheet_select("Results")
        self.assertIn("Hull City [1.82] 2-1 [0.45] Leeds United", app.detail_label.cget("text"))

    def test_the_save_opens_before_its_expected_goals_arrive(self):
        app = self.app
        pending = dataset()
        app.loading_since, app._loading_file = time.monotonic(), "x.fm"     # as open_save leaves them
        app.handle_event(("loaded", pending))
        app.set_view("Results")
        app.update()
        self.assertIs(app.dataset, pending)
        self.assertEqual(app.open_button.cget("state"), "disabled")          # still reading
        self.assertIn("not been read yet", app.note_label.cget("text"))
        found = [i for i, r in enumerate(app.result_rows) if r.fixture is LEAGUE[0]][0]
        self.assertEqual(app.sheets["Results"].get_cell_data(found, 4), "")
        app.handle_event(("xg", fd.with_expected_goals(pending, HULL_LEEDS_XG)))
        app.update()
        self.assertEqual(app.dataset.xg_report.joined, 1)
        self.assertEqual(app.open_button.cget("state"), "normal")
        self.assertEqual(app.sheets["Results"].get_cell_data(found, 4), "1.82-0.45")
        self.assertIn("Expected goals for 1 of 4 played matches", app.note_label.cget("text"))

    def test_the_worker_hands_over_the_save_then_its_expected_goals(self):
        pending = dataset()
        full = fd.with_expected_goals(pending, HULL_LEEDS_XG)

        def load(path, progress, ready):
            ready(pending)
            return full

        with mock.patch.object(fm_review.fd, "load_dataset", side_effect=load):
            self.app._load_worker(Path("x.fm"))
        self.assertEqual([self.app.events.get_nowait() for _ in range(2)], [("loaded", pending), ("xg", full)])

    def test_list_search_and_details(self):
        app = self.app
        app.install_dataset(dataset())
        app.search_entry.insert(0, "derby")
        app._fill_competition_list()
        self.assertEqual([c for c in app.list_rows if c is not None], [101, 60])
        app.search_entry.delete(0, "end")
        app.search_entry.insert(0, "wrexham")
        app._fill_competition_list()
        self.assertEqual([c for c in app.list_rows if c is not None], [131])
        app.show_details()
        app.update()

    def test_naming_a_competition_is_kept_in_the_names_file(self):
        app = self.app
        app.install_dataset(dataset())
        with mock.patch.object(fm_review.ctk, "CTkInputDialog") as dialog:
            dialog.return_value.get_input.return_value = "  Championship "
            app.rename_competition()
        self.assertEqual(app.title_label.cget("text"), "Championship")
        self.assertEqual(fd.load_competition_names(fm_review.NAMES_PATH), {12: "Championship"})
        self.assertIn("Championship", app.comp_list.get(0, "end")[1])
        with mock.patch.object(fm_review.ctk, "CTkInputDialog") as dialog:
            dialog.return_value.get_input.return_value = ""      # empty removes the name
            app.rename_competition()
        self.assertEqual(app.title_label.cget("text"), "Competition 101")
        self.assertEqual(fd.load_competition_names(fm_review.NAMES_PATH), {})

    def test_picking_a_competition_in_the_list_leaves_the_hub(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view("Table")
        app.set_view(fm_review.HUB)        # used to crash on the unresolved team in competition 70
        app.update()
        self.assertCountEqual(app.comp_row_ids, [101, 60, 131, 70])
        self.assertEqual(app.season_menu.cget("state"), "disabled")
        app.comp_list.selection_clear(0, "end")
        app.comp_list.selection_set(app.list_rows.index(70))
        app._on_list_select()
        app.update()
        self.assertEqual((app.view, app.comp_id, app.view_switch.get()), ("Table", 70, "Table"))
        self.assertEqual(app.season_menu.cget("state"), "normal")

    def test_the_team_box_keeps_up_with_a_competition_picked_in_the_hub(self):
        app = self.app
        app.install_dataset(dataset())
        self.assertEqual(app.team_box.get(), "Hull City")
        app.set_view(fm_review.HUB)          # the team box is disabled here, and ignored set() calls
        app.select_competition(70)           # Hull do not play in it, so nobody is followed
        app.set_view("Results")
        self.assertIsNone(app.focus)
        self.assertEqual(app.team_box.get(), fm_review.ALL_TEAMS)

    def test_hub_click_selects_in_place_and_double_click_opens(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view("Grid")
        app.set_view(fm_review.HUB)
        app.update()
        filled = app._hub_key
        hub = app.sheets[fm_review.HUB]
        hub.select_cell(app.comp_row_ids.index(60), 2, redraw=False, run_binding_func=False)
        app._on_sheet_select(fm_review.HUB)
        self.assertEqual((app.view, app.comp_id), (fm_review.HUB, 60))
        self.assertEqual(app._hub_key, filled)             # not refilled, so it keeps its scroll position
        self.assertEqual(app.list_rows[app.comp_list.curselection()[0]], 60)
        self.assertIn("Selected:", app.detail_label.cget("text"))
        hub.select_column(1, redraw=False, run_binding_func=False)      # a header click picks nothing
        app._on_sheet_select(fm_review.HUB)
        self.assertEqual(app.comp_id, 60)
        hub.select_cell(app.comp_row_ids.index(60), 2, redraw=False, run_binding_func=False)
        app._open_from_hub()
        app.update()
        self.assertEqual((app.view, app.comp_id), ("Grid", 60))

    def test_table_shows_rule_zones_and_ignores_header_clicks(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view("Table")
        note = app.note_label.cget("text")
        self.assertIn("game's rules", note)
        self.assertIn("Play-offs", app.zone_key_meanings)        # the colour key, under the sheet
        app.set_focus(team(3))
        table = app.sheets["Table"]
        table.select_column(3, redraw=False, run_binding_func=False)
        app._on_sheet_select("Table")
        self.assertEqual(app.focus, team(3))               # a header click used to follow the leaders
        table.select_cell(1, 1, redraw=False, run_binding_func=False)
        app._on_sheet_select("Table")
        self.assertEqual(app.focus, team(4))               # Derby are second in the stored table
        app._on_table_split(fd.SPLIT_HOME)
        self.assertEqual(app.zone_key_meanings, [])             # zones belong to the overall table

    def overlay_texts(self, name):
        canvas = self.app.sheets[name].MT
        return [canvas.itemcget(i, "text") for i in canvas.find_withtag(fm_review.SheetOverlay.TAG)
                if canvas.type(i) == "text"]

    def test_form_is_drawn_as_pills_and_the_cells_keep_their_letters(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view("Table")
        app.update()
        form = [app.sheets["Table"].get_cell_data(r, 10) for r in range(len(app.table_rows))]
        self.assertTrue("".join(form).strip())                   # there is some form to draw
        self.assertEqual(sorted(self.overlay_texts("Table")), sorted("".join(form).replace(" ", "")))
        app.set_view(fm_review.ANALYSIS)
        app.update()
        sheet = app.sheets[fm_review.ANALYSIS]
        letters = [sheet.get_cell_data(r, c) for r in range(len(app.analysis_rows)) for c in range(1, 6)]
        self.assertEqual(sorted(self.overlay_texts(fm_review.ANALYSIS)), sorted(x for x in letters if x))
        app._on_analysis("Positions")
        app.update()
        self.assertEqual(self.overlay_texts(fm_review.ANALYSIS), [])

    def test_each_form_pill_has_a_faint_bevel_that_leaves_the_letter_alone(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view("Table")
        app.update()
        canvas = app.sheets["Table"].MT
        items = canvas.find_withtag(fm_review.SheetOverlay.TAG)
        pills = len(self.overlay_texts("Table"))
        arcs = [i for i in items if canvas.type(i) == "arc"]
        self.assertEqual(len(arcs), 2 * pills)
        letter = next(i for i in items if canvas.type(i) == "text")
        self.assertEqual(canvas.itemcget(letter, "fill"), app.view_theme.colours[canvas.itemcget(letter, "text")][1])

    def test_the_form_cell_carries_a_place_spark_under_its_pills(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view("Table")
        app.update()
        overlay = app.overlays["Table"]
        row = app.table_rows.index(team(1))
        self.assertEqual(overlay.sparks[(row, fm_review.FORM_COLUMN)], (1, 1))      # Hull led after both matches
        canvas = app.sheets["Table"].MT
        lines = [i for i in canvas.find_withtag(fm_review.SheetOverlay.TAG) if canvas.type(i) == "line"]
        self.assertEqual(len(lines), len(overlay.sparks))
        self.assertEqual(len(canvas.coords(lines[0])), 4)                           # two points, so one segment
        self.assertEqual(canvas.itemcget(lines[0], "fill"), app.view_theme.muted)

    def test_a_spark_rises_when_the_team_climbs(self):
        app = self.app
        overlay = app.overlays["Table"]
        canvas = app.sheets["Table"].MT
        app.install_dataset(dataset())
        app.set_view("Table")
        app.update()
        row = 0
        overlay.show({(row, fm_review.FORM_COLUMN): "WWL"}, {}, app.view_theme.colours, ("#000000", "#000000"),
                     sparks={(row, fm_review.FORM_COLUMN): (9, 5, 2)}, spark_colour="#aaaaaa")
        app.update()
        line = next(i for i in canvas.find_withtag(fm_review.SheetOverlay.TAG) if canvas.type(i) == "line")
        ys = canvas.coords(line)[1::2]
        self.assertGreater(ys[0], ys[1])
        self.assertGreater(ys[1], ys[2])                                            # canvas y grows downwards

    def test_zone_edges_and_the_colour_key(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view("Table")
        app.update()
        self.assertEqual(app.zone_edges, {0: app.view_theme.zones[fd.ZONE_PROMOTION][0],
                                          1: app.view_theme.zones[fd.ZONE_PLAYOFF][0],
                                          3: app.view_theme.zones[fd.ZONE_RELEGATION][0]})
        self.assertEqual(app.zone_key_meanings, ["Promotion", "Play-offs", "Relegation"])
        self.assertNotIn("Pos colours", app.note_label.cget("text"))
        app.set_view("Results")
        self.assertEqual(app.zone_key_meanings, [])

    def test_goal_difference_bars(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view("Table")
        app.update()
        self.assertEqual(app.overlays["Table"].bars, {(0, 8): 0.3})     # Hull +3 on a scale of 10; 0 has none
        canvas = app.sheets["Table"].MT
        kinds = [canvas.type(i) for i in canvas.find_withtag(fm_review.SheetOverlay.TAG)]
        self.assertIn("rectangle", kinds)

    def wait_until(self, condition, seconds=3.0) -> bool:
        """Run the window's event loop until the condition holds: tksheet redraws on a short timer."""
        stop = time.monotonic() + seconds
        while not condition() and time.monotonic() < stop:
            self.app.update()
            time.sleep(0.01)
        return condition()

    def open_long_league(self):
        """A 46-team league, so that its table scrolls: odd-numbered clubs win at home, the rest lose."""
        with mock.patch.dict(test_fm_data.CLUBS, {n: (f"Club {n}", f"C{n}") for n in range(6, 47)}):
            fixtures = [fx(D(2026, 8, 1), n, n + 1, 1, 0, comp=102, md=1) for n in range(1, 47, 2)]
            self.app.install_dataset(fd.build_dataset(info(), fixtures, clubs=[club(n) for n in range(1, 47)]))
        self.app.set_view("Table")
        self.app.update()
        return self.app.sheets["Table"], self.app.overlays["Table"], len(self.app.table_rows) - 1

    def test_pills_follow_the_rows_on_screen_after_scrolling(self):
        sheet, overlay, last = self.open_long_league()
        self.assertNotIn(last, overlay.drawn_rows)               # the foot of the table starts off screen
        sheet.see(row=last, column=0)
        self.assertTrue(self.wait_until(lambda: last in overlay.drawn_rows), "the pills did not follow the scroll")
        start, end = sheet.visible_rows
        self.assertTrue(all(start <= r <= end for r in overlay.drawn_rows))
        self.assertNotIn(0, overlay.drawn_rows)                  # and the top is now off screen

    def test_a_theme_switch_keeps_the_scroll_position_and_repaints_the_pills(self):
        app = self.app
        sheet, overlay, last = self.open_long_league()
        sheet.see(row=last, column=0)
        self.assertTrue(self.wait_until(lambda: last in overlay.drawn_rows))
        where = sheet.get_yview()[0]
        self.assertGreater(where, 0.3)                           # it really is scrolled
        app.set_theme("High-Contrast")
        self.assertTrue(self.wait_until(lambda: last in overlay.drawn_rows), "the pills were not redrawn")
        self.assertAlmostEqual(sheet.get_yview()[0], where, places=3)
        canvas = sheet.MT
        fills = {canvas.itemcget(i, "fill") for i in canvas.find_withtag(fm_review.SheetOverlay.TAG)
                 if canvas.type(i) == "polygon"}
        self.assertEqual(fills, {"#f87171"})     # only losers are on screen at the foot: High-Contrast's loss red

    def wait_for_export(self):
        stop = time.monotonic() + 30
        while self.app._exporting and time.monotonic() < stop:
            self.app.update()
            time.sleep(0.02)
        self.assertFalse(self.app._exporting, "the export did not finish")

    def test_export_runs_in_the_background_and_offers_to_open_it(self):
        app = self.app
        app.install_dataset(dataset())
        folder = Path(self.folder.name) / "Box2Box"
        with mock.patch.object(fm_review, "export_folder", return_value=folder), \
                mock.patch.object(fm_review.messagebox, "askyesno", return_value=False) as offered:
            app.export(fm_review.fx.EXCEL)
            self.assertEqual(app.export_button.cget("state"), "disabled")
            app.export(fm_review.fx.HTML)          # ignored: one export at a time
            self.wait_for_export()
        files = sorted(p.name for p in folder.iterdir())
        self.assertEqual(files, ["Competition 101 2026 (2026-09-01).xlsx"])
        self.assertEqual(offered.call_count, 1)
        self.assertIn("Saved the Excel workbook", app.detail_label.cget("text"))
        self.assertEqual(app.export_button.cget("state"), "normal")

    def test_exports_use_the_windows_theme_and_club_colours(self):
        app = self.app
        app.install_dataset(dataset())                       # Hull City is followed, so its colours tint the view
        app.set_theme("Cyber Pitch")
        seen = []

        def fake_export(kind, request, folder):
            seen.append(request)
            return Path(self.folder.name) / "made.xlsx"

        with mock.patch.object(fm_review, "export_folder", return_value=Path(self.folder.name)), \
                mock.patch.object(fm_review.fx, "export", side_effect=fake_export), \
                mock.patch.object(fm_review.messagebox, "askyesno", return_value=False):
            app.export(fm_review.fx.EXCEL)
            self.wait_for_export()
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].theme, app.view_theme)
        self.assertEqual(seen[0].theme.name, "Cyber Pitch")
        self.assertEqual(seen[0].theme.focus, app.club_tint.focus)        # the club's colours went with it
        self.assertNotEqual(seen[0].theme.focus, palette.CYBER_PITCH.focus)

    def test_failed_export_is_reported(self):
        app = self.app
        app.install_dataset(dataset())
        with mock.patch.object(fm_review, "export_folder", return_value=Path(self.folder.name) / "Box2Box"), \
                mock.patch.object(fm_review.fx, "export", side_effect=fm_review.fx.ExportFailed("It is open in Excel.")), \
                mock.patch.object(fm_review.messagebox, "showerror") as shown:
            app.export(fm_review.fx.CSV)
            self.wait_for_export()
        self.assertEqual(shown.call_args.args[1], "It is open in Excel.")
        self.assertEqual(app.export_button.cget("state"), "normal")

    def test_failed_import_keeps_the_save_already_open(self):
        app = self.app
        first = dataset()
        app.install_dataset(first)
        with mock.patch.object(fm_review.messagebox, "showerror") as shown:
            app.handle_event(("failed", "The save looks damaged."))
        self.assertIs(app.dataset, first)
        self.assertIn("still shown", shown.call_args.args[1])
        self.assertEqual(app.comp_id, 101)

    def test_about_opens_from_its_button_before_any_save(self):
        app = self.app
        self.assertEqual(app.about_button.cget("state"), "normal")      # no save is open yet
        app.about_button.invoke()
        app.update()
        about = app.about_window
        self.assertEqual(about.title(), "About Box2Box")
        shown = texts_in(about)
        self.assertIn(f"Version {fm_review.VERSION}", shown)
        self.assertIn(COPYRIGHT, shown)
        self.assertIn("Permission is hereby refused", about.licence_box.get("1.0", "end"))   # LICENSE's terms
        app.about_button.invoke()                  # a second click brings the same window forward
        self.assertIs(app.about_window, about)
        about.close_button.invoke()
        app.update()
        self.assertFalse(about.winfo_exists())
        app.about_button.invoke()                  # and once closed, it opens again
        app.update()
        self.assertIsNot(app.about_window, about)
        self.assertTrue(app.about_window.winfo_exists())

    def test_status_bar_shows_the_copyright_until_a_save_is_open(self):
        self.assertIn(COPYRIGHT, self.app.status_label.cget("text"))

    def make_save(self, name="My Career (v02).fm"):
        path = Path(self.folder.name) / name
        path.write_bytes(b"x")
        return path

    def test_the_window_accepts_drops_when_the_library_is_there(self):
        self.assertTrue(self.app.drop_enabled)

    def test_dropping_one_save_opens_it_and_anything_else_is_refused(self):
        app, save, other = self.app, self.make_save(), self.make_save("notes.txt")
        with mock.patch.object(app, "open_save") as opened:
            action = app._on_file_drop(NS(data="{%s}" % save.as_posix(), action="copy"))   # braces round a path with spaces
        self.assertEqual((action, opened.call_args.args), ("copy", (save,)))
        with mock.patch.object(app, "open_save") as opened:
            action = app._on_file_drop(NS(data=other.as_posix(), action="copy"))      # tkdnd's format: forward slashes
        self.assertEqual((action, opened.call_count), ("refuse_drop", 0))
        self.assertIn("notes.txt is not a .fm save", app.detail_label.cget("text"))

    def test_a_drop_while_a_save_is_being_read_is_refused(self):
        app, save = self.app, self.make_save()
        app.loading_since, app._loading_file = time.monotonic(), "other.fm"
        with mock.patch.object(app, "open_save") as opened:
            action = app._on_file_drop(NS(data="{%s}" % save.as_posix(), action="copy"))
        app.loading_since = None
        self.assertEqual((action, opened.call_count), ("refuse_drop", 0))
        self.assertIn("Still reading other.fm", app.detail_label.cget("text"))

    def test_dragging_over_the_window_shows_a_hint_that_ends_with_the_drag(self):
        app = self.app
        self.assertEqual(app._on_drop_enter(NS(data="", action="copy")), "copy")
        self.assertEqual(app.status_label.cget("text"), fm_review.DROP_HINT)
        app._on_drop_leave(NS(data="", action="copy"))
        self.assertIn(COPYRIGHT, app.status_label.cget("text"))

    def test_the_window_opens_without_drop_support_when_the_library_is_missing_or_fails(self):
        for patcher in (mock.patch.object(fm_review, "TkinterDnD", None),
                        mock.patch.object(fm_review.TkinterDnD, "_require", side_effect=RuntimeError("no native library"))):
            self.app.destroy()
            with patcher:
                self.app = fm_review.FMReviewApp()          # tearDown closes the last one
                self.app.geometry("1300x800+-4000+0")
                self.app.update()
                self.assertFalse(self.app.drop_enabled)
                self.assertIn("Dropping a save onto the window is not available", self.app.detail_label.cget("text"))
                self.assertEqual(self.app.open_button.cget("state"), "normal")        # the window works as before

    def widen(self, width=1700):
        """A window wide enough for the view switch's counts to show (the test window is 1300 px wide)."""
        self.app.geometry(f"{width}x800+-4000+0")
        self.app.update()

    def view_button(self, label):
        """The view switch's button with this label."""
        return next(b for b in self.app.view_switch.winfo_children()
                    if isinstance(b, ctk.CTkButton) and b.cget("text") == label)

    def click_view(self, label):
        """Press the view switch's button with this label, as a person does."""
        self.view_button(label).invoke()

    def test_the_view_switch_counts_what_is_still_to_play_and_the_competitions(self):
        app = self.app
        self.assertEqual(list(app.view_labels.values()), list(fm_review.SWITCH_VIEWS))        # no save: plain names
        self.widen()
        app.install_dataset(dataset())
        self.assertEqual(list(app.view_labels.values()),
                         ["Results (2)", "Grid", "Table", "Analysis", "Competitions (4)"])
        self.assertEqual(app.view_switch.get(), "Results (2)")

    def test_the_table_label_names_a_followed_run_of_three_or_more(self):
        app = self.app
        self.widen()
        wins = [fx(D(2026, 8, 1 + 7 * i), 1, 2 + i, 1, 0, comp=105, md=i + 1) for i in range(3)]      # Hull win three
        app.install_dataset(fd.build_dataset(info(), wins, clubs=[club(n) for n in range(1, 6)]))
        self.assertEqual(app.view_labels["Table"], "Table (W3)")
        app.set_focus(None)
        self.assertEqual(app.view_labels["Table"], "Table")                                    # nobody followed
        unscored = fx(D(2026, 7, 25), 1, 5, played=True, comp=105)       # played, no score, same competition
        app.install_dataset(fd.build_dataset(info(), [unscored, *wins], clubs=[club(n) for n in range(1, 6)]))
        self.assertEqual(app.view_labels["Table"], "Table (W3+)")        # a missing score could make it longer

    def test_a_followed_team_with_no_results_adds_no_count_and_no_error(self):
        app = self.app
        app.install_dataset(dataset())
        app.select_competition(70)
        app.set_focus(999)                                       # a team the save cannot resolve
        self.assertEqual(app.view_labels["Table"], "Table")

    def test_clicking_a_label_with_a_count_opens_its_view(self):
        app = self.app
        self.widen()
        app.install_dataset(dataset())
        self.click_view("Competitions (4)")
        self.assertEqual((app.view, app.view_switch.get()), (fm_review.HUB, "Competitions (4)"))
        self.click_view("Results (2)")
        self.assertEqual((app.view, app.view_switch.get()), ("Results", "Results (2)"))

    def test_the_counts_give_way_when_the_window_is_too_narrow(self):
        # They add about 100 px to the controls row, so a window too narrow for the whole row shows plain names.
        app = self.app
        app.install_dataset(dataset())                           # the test window is 1300 px wide: too narrow
        self.assertEqual(list(app.view_labels.values()), list(fm_review.SWITCH_VIEWS))
        self.widen()
        self.assertTrue(self.wait_until(lambda: app.view_labels["Results"] == "Results (2)"), "no counts when wide")
        app.geometry("1300x800+-4000+0")
        self.assertTrue(self.wait_until(lambda: app.view_labels["Results"] == "Results"), "counts stayed when narrow")

    def test_the_controls_fit_the_room_the_counts_ask_for_at_their_longest(self):
        app = self.app
        self.widen()
        app.install_dataset(dataset())
        longest = {"Results": "9999", "Table": "W99+", fm_review.HUB: "9999"}
        with mock.patch.object(app, "_view_count", side_effect=lambda view: longest.get(view, "")):
            app.set_view("Table")                                # the widest controls: the Standings switch too
            app.update()
            self.assertEqual(app.view_labels["Competitions"], "Competitions (9999)")
            self.assertLessEqual(app.winfo_reqwidth(), app.px(fm_review.COUNTS_MIN_WIDTH))

    def test_changing_the_labels_keeps_the_switch_enabled_and_tinted(self):
        app = self.app
        self.widen()
        app.install_dataset(dataset())                           # Hull City followed: its colours tint the selection
        tint = app.club_tint
        app.set_view("Table")
        app.select_competition(60)                               # Results (2) becomes Results: the buttons are rebuilt
        self.assertEqual(app.view_labels["Results"], "Results")
        self.assertEqual(app.view_switch.cget("state"), "normal")
        self.assertEqual(self.view_button(app.view_switch.get()).cget("fg_color"), tint.selected[0])

    def test_the_main_window_wears_the_box2box_icon(self):
        self.app.destroy()
        with mock.patch.object(fm_review.FMReviewApp, "iconbitmap", autospec=True) as icon:
            self.app = fm_review.FMReviewApp()          # tearDown closes this one
            self.app.geometry("1300x800+-4000+0")
            self.app.update()
        icon.assert_any_call(self.app, str(fm_review.ICON_PATH))

    def test_the_about_and_details_windows_wear_the_box2box_icon(self):
        app = self.app
        app.install_dataset(dataset())
        with mock.patch.object(ctk.CTkToplevel, "iconbitmap", autospec=True) as icon:
            app.about_button.invoke()
            app.show_details()
            app.update()
        iconed = [c.args[0] for c in icon.call_args_list if c.args[1:] == (str(fm_review.ICON_PATH),)]
        self.assertIn(app.about_window, iconed)
        self.assertEqual(len(iconed), 2)              # About and the save details

    def test_a_missing_icon_is_not_an_error(self):
        with mock.patch.object(fm_review, "ICON_PATH", Path(self.folder.name) / "none.ico"):
            self.assertFalse(fm_review.apply_window_icon(self.app))

    def test_switching_theme_repaints_in_place(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view("Table")
        app.set_focus(team(3))                      # Sheffield United, fourth in the stored table
        before = (app.comp_id, app.season, app.focus, app.view)
        odd = dataclasses.replace(palette.MIDNIGHT_EMERALD, name="Test", panel="#102030",
                                  table=("#010203", "#fefefe"), switch_selected="#203040",
                                  focus=("#0f1e2d", "#ffffff"), club_colours=False)
        app.apply_theme(odd)
        app.update()
        self.assertEqual((app.comp_id, app.season, app.focus, app.view), before)
        self.assertEqual(app.status_bar.cget("fg_color"), "#102030")
        self.assertEqual(app.split_switch.cget("selected_color"), "#203040")
        table = app.sheets["Table"]
        self.assertEqual(table.ops.table_bg, "#010203")
        self.assertEqual(table.props(3, 1, "highlight").bg, "#0f1e2d")      # the view was redrawn

    def test_the_theme_is_kept_in_the_settings(self):
        self.app.set_theme("Midnight Emerald")
        saved = json.loads(fm_review.SETTINGS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(saved["theme"], "Midnight Emerald")
        labels = [self.app.theme_menu.entrycget(i, "label") for i in range(len(palette.THEMES))]
        self.assertEqual(labels, [t.name for t in palette.THEMES])

    def test_a_theme_can_change_before_a_save_is_open_and_with_about_showing(self):
        app = self.app
        app.about_button.invoke()
        app.update()
        odd = dataclasses.replace(palette.MIDNIGHT_EMERALD, name="Test", heading=("#0a0b0c", "#ffffff"))
        app.apply_theme(odd)
        app.update()
        self.assertEqual(app.about_window.band.cget("fg_color"), "#0a0b0c")

    def test_every_view_renders_in_every_theme(self):
        app = self.app
        app.install_dataset(dataset())
        for theme in palette.THEMES:
            app.set_theme(theme.name)
            for view in fm_review.VIEWS:
                app.set_view(view)
                for analysis in fm_review.ANALYSES if view == fm_review.ANALYSIS else ():
                    app._on_analysis(analysis)
                app.update()
            self.assertEqual(app.sheets["Table"].ops.table_bg, theme.table[0])
            self.assertEqual(app.settings["theme"], theme.name)

    def test_the_followed_club_tints_the_band_switch_and_highlight(self):
        app = self.app
        app.install_dataset(dataset())                       # Hull City followed
        tint = palette.club_tint(app.theme, club_colours.builtin_colours("Hull City"))
        self.assertEqual(app.top_bar.cget("fg_color"), tint.band[0])
        self.assertEqual(app.view_switch.cget("selected_color"), tint.selected[0])
        self.assertEqual(app.view_theme.focus, tint.focus)
        self.assertEqual(app.view_theme.colours, app.theme.colours)          # results keep their colours
        app.set_focus(None)
        self.assertEqual(app.top_bar.cget("fg_color"), app.theme.panel)
        self.assertEqual(app.view_switch.cget("selected_color"), app.theme.switch_selected)

    def test_the_unverified_build_notice_keeps_its_own_colours_on_a_club_band(self):
        # With a club followed, v1.3 turned the amber notice white on the club's band, which on a red club
        # read like an error. It must stay amber, on a small chip of the plain panel colour.
        app = self.app
        app.install_dataset(dataset())                      # an unverified build, Hull City followed: a tinted band
        self.assertIsNotNone(app.club_tint)
        self.assertEqual(app.verify_label.cget("text"), "UV")      # Mark, 18 Nov: two letters, small, muted
        theme = app.theme
        self.assertEqual(app.verify_label.cget("text_color"), theme.muted)
        self.assertEqual(app.verify_chip.cget("fg_color"), theme.panel)
        self.assertNotEqual(app.top_bar.cget("fg_color"), theme.panel)          # the band really is tinted
        for name in ("Cyber Pitch", "Deep Slate & Gold", "High-Contrast"):       # and so in every other theme
            app.set_theme(name)
            self.assertEqual(app.verify_label.cget("text_color"), app.theme.muted, name)
            self.assertEqual(app.verify_chip.cget("fg_color"), app.theme.panel, name)

    def test_the_uv_chip_explains_itself_in_a_tooltip(self):
        app = self.app
        app.install_dataset(dataset())
        tip = app._build_notice_tip()
        info = app.dataset.info
        for part in (info.build, "borrow", info.fmsave_version, "Unverified"):
            self.assertIn(part, tip)
        self.assertNotIn("⚠", tip)
        app.verify_label._label.event_generate("<Enter>", x=2, y=2)
        app.update()
        self.assertTrue(app.tooltip.is_shown)
        self.assertEqual(app.tooltip.text, tip)
        app.verify_label._label.event_generate("<Leave>")
        app.update()
        self.assertFalse(app.tooltip.is_shown)

    def test_the_unverified_build_notice_is_hidden_when_the_build_is_known(self):
        app = self.app
        ds = dataset()
        app.install_dataset(dataclasses.replace(ds, info=dataclasses.replace(ds.info, known_build=True)))
        self.assertEqual(app.verify_chip.grid_info(), {})                       # no empty chip left on the band
        app.install_dataset(dataset())
        self.assertNotEqual(app.verify_chip.grid_info(), {})

    def test_club_colour_edits_are_saved_and_win(self):
        app = self.app
        app.install_dataset(dataset())
        app.save_club_colours("Hull City", ("#123456", "#fedcba"))
        saved = json.loads(fm_review.SETTINGS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(saved["club_colours"], {"Hull City": ["#123456", "#fedcba"]})
        self.assertEqual(app.club_tint.colours, ("#123456", "#fedcba"))
        app.save_club_colours("Hull City", None)
        self.assertIsNone(app.club_tint)
        app.reset_club_colours("Hull City")
        self.assertEqual(app.club_tint.colours, club_colours.builtin_colours("Hull City"))

    def test_reserve_sides_wear_the_parent_clubs_colours_and_unknown_clubs_none(self):
        app = self.app
        app.install_dataset(dataset())
        app.select_competition(60)                           # the youth league: Hull City's second team
        self.assertEqual(app.focus, team(1, 1))
        self.assertEqual(app.club_tint.colours, club_colours.builtin_colours("Hull City"))
        app.select_competition(70)
        app.set_focus(999)                                   # a team the save cannot resolve
        self.assertIsNone(app.club_tint)

    def test_high_contrast_shows_no_club_colours(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_theme("High-Contrast")
        self.assertIsNone(app.club_tint)
        self.assertEqual(app.top_bar.cget("fg_color"), palette.HIGH_CONTRAST.panel)
        self.assertEqual(app.view_theme.focus, palette.HIGH_CONTRAST.focus)

    def test_the_club_colours_dialog_saves_and_resets(self):
        app = self.app
        app.install_dataset(dataset())
        with mock.patch.object(fm_review.colorchooser, "askcolor", return_value=((1, 2, 3), "#010203")):
            app.show_club_colours()
            app.club_dialog.main_swatch.invoke()
            app.club_dialog.save_button.invoke()
        self.assertEqual(app.club_tint.colours[0], "#010203")
        app.show_club_colours()
        app.club_dialog.builtin_button.invoke()
        self.assertEqual(app.club_tint.colours, club_colours.builtin_colours("Hull City"))

    def test_club_colours_menu_item_needs_a_followed_team(self):
        app = self.app
        app.install_dataset(dataset())
        item = app.theme_menu.index("Club colours…")
        self.assertEqual(app.theme_menu.entrycget(item, "state"), "normal")
        app.set_focus(None)
        self.assertEqual(app.theme_menu.entrycget(item, "state"), "disabled")

    def test_malformed_club_colour_settings_are_ignored(self):
        self.app.destroy()
        fm_review.SETTINGS_PATH.write_text('{"club_colours": "red"}', encoding="utf-8")
        self.app = fm_review.FMReviewApp()          # tearDown closes this one
        self.app.geometry("1300x800+-4000+0")
        self.app.install_dataset(dataset())
        self.assertEqual(self.app.club_tint.colours, club_colours.builtin_colours("Hull City"))

    def test_odd_theme_settings_open_in_midnight_emerald(self):
        self.app.destroy()
        fm_review.SETTINGS_PATH.write_text('{"theme": 3}', encoding="utf-8")
        self.app = fm_review.FMReviewApp()          # tearDown closes this one
        self.app.geometry("1300x800+-4000+0")
        self.assertIs(self.app.theme, palette.MIDNIGHT_EMERALD)

    # ----------------------------------------------------------------- the command palette

    def palette_app(self, extra=()):
        """A wide window with a save installed, and its palette. `extra` adds fixtures (a second league)."""
        app = self.app
        self.widen()
        app.install_dataset(dataset(extra=extra))
        app.names = {12: "Championship", 13: "League One"}
        app.update()
        return app, app.command_palette

    OTHER_LEAGUE = [fx(D(2026, 8, 8), 5, 4, 1, 0, comp=102, md=1)]       # Wrexham v Derby, a second league

    def test_ctrl_k_and_ctrl_p_open_the_palette_and_escape_closes_it_unchanged(self):
        app, pal = self.palette_app()
        for sequence in ("<Control-k>", "<Control-p>"):
            app.event_generate(sequence)
            app.update()
            self.assertTrue(pal.is_open, sequence)
            before = (app.comp_id, app.view, app.focus, app.season)
            pal.entry._entry.event_generate("<Escape>")
            app.update()
            self.assertFalse(pal.is_open, sequence)
            self.assertEqual((app.comp_id, app.view, app.focus, app.season), before)

    def test_a_view_is_chosen_by_typing_and_enter(self):
        app, pal = self.palette_app()
        app.open_palette()
        box = pal.entry._entry
        box.focus_force()                                    # a generated key only reaches the box that holds focus
        self.assertTrue(self.wait_until(lambda: app.focus_get() is box), "the search box never took focus")
        pal.set_query("table")
        self.assertEqual(pal.results[0].title, "Table")
        box.event_generate("<Return>")
        app.update()
        self.assertFalse(pal.is_open)
        self.assertEqual(app.view, "Table")

    def test_a_competition_is_opened_by_its_name(self):
        app, pal = self.palette_app(self.OTHER_LEAGUE)
        app.open_palette()
        pal.set_query("league one")
        self.assertEqual(pal.results[0].title, "League One")
        pal.run_selected()
        self.assertEqual(app.comp_id, 102)

    def test_a_club_from_another_league_opens_that_league_and_is_followed(self):
        app, pal = self.palette_app(self.OTHER_LEAGUE)
        app.open_palette()
        pal.set_query("wrexham")
        clubs = [(i.title, i.detail) for i in pal.results if i.kind == "Club"]
        self.assertEqual(clubs, [("Wrexham", "League One · 2 teams")])
        pal.run_selected()
        self.assertEqual(app.comp_id, 102)
        self.assertEqual(app.labels[app.focus], "Wrexham")

    def test_a_club_met_only_in_friendlies_is_not_offered(self):
        app, pal = self.palette_app()
        app.open_palette()
        pal.set_query("wrexham")
        self.assertEqual([i for i in pal.results if i.kind == "Club"], [])

    def test_the_open_competitions_teams_are_offered_whatever_it_is(self):
        app, pal = self.palette_app()
        app.select_competition(60)                           # a youth league: not a senior competition
        app.open_palette()
        pal.set_query("derby")
        self.assertEqual((pal.results[0].title, pal.results[0].detail), ("Derby County", app._competition_detail(app.dataset.by_id[60])))
        pal.run_selected()
        self.assertEqual((app.comp_id, app.labels[app.focus]), (60, "Derby County"))

    def test_following_a_club_that_the_competition_does_not_hold_says_so(self):
        app, pal = self.palette_app()
        app._follow_club_in(101, team(5), "Wrexham")
        self.assertIn("no matches", app.detail_label.cget("text"))

    def test_a_club_chosen_from_the_hub_leaves_it_for_the_last_competition_view(self):
        app, pal = self.palette_app(self.OTHER_LEAGUE)
        app.set_view("Table")
        app.set_view(fm_review.HUB)
        app.open_palette()
        pal.set_query("wrexham")
        pal.run_selected()
        self.assertEqual(app.view, "Table")

    def test_splits_switch_to_their_view_and_set_the_switch(self):
        app, pal = self.palette_app()
        app.open_palette()
        pal.set_query("table home")
        pal.run_selected()
        self.assertEqual((app.view, app.table_split, app.split_switch.get()), ("Table", fd.SPLIT_HOME, fd.SPLIT_HOME))
        app.open_palette()
        pal.set_query(f"results {fd.GROUP_BY_MATCHDAY}")
        pal.run_selected()
        self.assertEqual((app.view, app.group_by, app.group_switch.get()),
                         ("Results", fd.GROUP_BY_MATCHDAY, fd.GROUP_BY_MATCHDAY))
        app.open_palette()
        pal.set_query("analysis positions")
        pal.run_selected()
        self.assertEqual((app.view, app.analysis), (fm_review.ANALYSIS, "Positions"))

    def test_an_export_action_exports(self):
        app, pal = self.palette_app()
        app.open_palette()
        pal.set_query("excel")
        with mock.patch.object(app, "export") as export:
            pal.run_selected()
        export.assert_called_once_with(fm_review.fx.EXCEL)

    def test_a_theme_is_chosen_from_the_palette(self):
        app, pal = self.palette_app()
        app.open_palette()
        pal.set_query("cyber")
        pal.run_selected()
        self.assertEqual(app.theme.name, "Cyber Pitch")

    def test_without_a_save_only_what_applies_is_offered(self):
        app = self.app
        app.open_palette()
        pal = app.command_palette
        pal.set_query("open save")
        self.assertEqual(pal.visible_titles(), ["Open save…"])
        for absent in ("table", "excel", "details"):
            pal.set_query(absent)
            self.assertEqual(pal.results, [], absent)
        pal.set_query("about")
        self.assertEqual(pal.visible_titles(), ["About"])

    def test_a_query_with_nothing_to_match_offers_no_clubs(self):
        app, pal = self.palette_app(self.OTHER_LEAGUE)
        app.open_palette()
        for query in ("", "  ", " -- "):
            pal.set_query(query)
            self.assertTrue(pal.results)
            self.assertTrue({i.kind for i in pal.results} <= {"View", "Split", "Action"}, query)

    def test_the_palette_closes_when_a_save_loads(self):
        app, pal = self.palette_app()
        app.open_palette()
        app.install_dataset(dataset())
        self.assertFalse(pal.is_open)

    def test_a_theme_change_recolours_the_open_palette(self):
        app, pal = self.palette_app()
        app.open_palette()
        app.set_theme("Cyber Pitch")
        self.assertEqual(pal._rows[0][0].cget("bg"), app.theme.list_selected[0])
        self.assertEqual(pal.cget("fg_color"), app.theme.panel)

    def test_up_and_down_move_the_selection_and_wrap(self):
        app, pal = self.palette_app()
        app.open_palette()
        app.update()
        count = len(pal.results)
        self.assertGreater(count, 2)
        pal.entry._entry.event_generate("<Up>")
        self.assertEqual(pal.selected_index, count - 1)
        pal.entry._entry.event_generate("<Down>")
        pal.entry._entry.event_generate("<Down>")
        self.assertEqual(pal.selected_index, 1)

    def test_ctrl_k_in_the_team_box_opens_the_palette_and_keeps_the_text(self):
        app, pal = self.palette_app()
        app.team_box.focus_set()
        app.update()
        app.team_box._entry.event_generate("<Control-k>")
        app.update()
        self.assertTrue(pal.is_open)
        self.assertEqual(app.team_box.get(), "Hull City")

    def test_a_command_that_fails_is_reported_and_logged_not_raised(self):
        app, pal = self.palette_app()

        def boom():
            raise RuntimeError("no luck")

        pal.open([command_palette.PaletteItem(command_palette.VIEW, "Boom", action=boom)])
        pal.run_selected()
        self.assertIn("no luck", app.detail_label.cget("text"))
        self.assertIn("no luck", fm_review.ERROR_LOG.read_text(encoding="utf-8"))

    # ----------------------------------------------------------------- the right-click menu

    TWO_LEGS = [fx(D(2026, 9, 12), 4, 1, comp=101, md=4)]               # Derby v Hull: a second meeting

    def menu_app(self, focus=None):
        """A wide window on the Results view of the league, following `focus` (nobody by default)."""
        app = self.app
        self.widen()
        app.install_dataset(dataset(extra=self.TWO_LEGS))
        app.set_focus(focus)
        app.set_view("Results")
        app.update()
        return app

    @staticmethod
    def match_row(app):
        return next(i for i, r in enumerate(app.result_rows) if r.fixture is not None)

    def test_a_results_row_offers_follow_show_only_head_to_head_export_and_copy(self):
        app = self.menu_app()
        row = self.match_row(app)
        r = app.result_rows[row]
        menu = app._row_menu("Results", row, 2)
        labels = [e.label for e in menu]
        self.assertEqual(labels[:3], [f"Follow {r.home}", f"Follow {r.away}", f"Show only {r.home} v {r.away}"])
        head_to_head = next(e for e in menu if e.label.startswith("Head-to-head"))
        self.assertEqual(head_to_head.label, "Head-to-head")
        self.assertIsNotNone(head_to_head.command)
        export = next(e for e in menu if e.label == "Export")
        self.assertEqual([c.label for c in export.children],
                         ["Excel workbook (.xlsx)", "Web page (.html)", "CSV files (.csv)"])
        self.assertEqual(labels[-1], "Copy")

    def test_head_to_head_from_a_results_row_opens_the_inspector_on_the_pair(self):
        app = self.menu_app()
        row = self.match_row(app)
        r = app.result_rows[row]
        next(e for e in app._row_menu("Results", row, 2) if e.label.startswith("Head-to-head")).command()
        self.assertEqual(app._selection, ("pair", (r.home_id, r.away_id)))
        self.assertTrue(app.inspector.is_open)
        self.assertEqual(app.inspector.rendered_text()[0], "Head-to-head")

    def test_following_from_the_menu_follows_and_the_followed_club_is_not_offered_again(self):
        app = self.menu_app()
        row = self.match_row(app)
        home = app.result_rows[row].home_id
        next(e for e in app._row_menu("Results", row, 2) if e.label.startswith("Follow")).command()
        self.assertEqual(app.focus, home)
        row = self.match_row(app)                                     # now only the followed team's matches
        labels = [e.label for e in app._row_menu("Results", row, 2)]
        self.assertNotIn(f"Follow {app.labels[home]}", labels)

    def test_a_heading_row_gets_only_export_and_copy(self):
        app = self.menu_app()
        row = next(i for i, r in enumerate(app.result_rows) if r.is_heading)
        self.assertEqual([e.label for e in app._row_menu("Results", row, 0)], ["Export", "Copy"])

    def test_a_team_the_save_cannot_resolve_is_not_offered_to_follow(self):
        app = self.menu_app()
        app.select_competition(70)
        app.set_view("Results")
        row = self.match_row(app)
        labels = [e.label for e in app._row_menu("Results", row, 2)]
        self.assertIn("Follow Leeds United", labels)
        self.assertFalse([label for label in labels if "999" in label or label.startswith("Show only")])

    def test_a_table_row_offers_follow_unless_followed_a_head_to_head_with_the_followed_and_export(self):
        app = self.menu_app(focus=team(1))
        app.set_view("Table")
        app.update()
        followed = app.table_rows.index(team(1))
        other = next(i for i, t in enumerate(app.table_rows) if t not in (None, team(1)))
        self.assertNotIn("Follow Hull City", [e.label for e in app._row_menu("Table", followed, 0)])
        menu = app._row_menu("Table", other, 0)
        self.assertEqual(menu[0].label, f"Follow {app.labels[app.table_rows[other]]}")
        head_to_head = next(e for e in menu if e.label.startswith("Head-to-head"))
        self.assertEqual(head_to_head.label, "Head-to-head with Hull City")
        self.assertIsNotNone(head_to_head.command)
        self.assertEqual([e.label for e in menu][-2:], ["Export", "Copy"])

    def test_head_to_head_from_a_table_row_opens_the_inspector_on_the_followed_and_the_row_club(self):
        app = self.menu_app(focus=team(1))
        app.set_view("Table")
        app.update()
        other = next(i for i, t in enumerate(app.table_rows) if t not in (None, team(1)))
        row_club = app.table_rows[other]
        next(e for e in app._row_menu("Table", other, 0) if e.label.startswith("Head-to-head")).command()
        self.assertEqual(app._selection, ("pair", (team(1), row_club)))
        self.assertTrue(app.inspector.is_open)

    def test_a_table_row_with_no_followed_club_shows_a_greyed_head_to_head_with_a_reason(self):
        app = self.menu_app(focus=None)
        app.set_view("Table")
        app.update()
        row = next(i for i, t in enumerate(app.table_rows) if t is not None)
        head_to_head = next(e for e in app._row_menu("Table", row, 0) if e.label.startswith("Head-to-head"))
        self.assertEqual(head_to_head.label, "Head-to-head (follow another club first)")
        self.assertIsNone(head_to_head.command)

    def test_a_table_row_offers_show_only_the_followed_club_v_the_row_club(self):
        app = self.menu_app(focus=team(1))
        app.set_view("Table")
        app.update()
        other = next(i for i, t in enumerate(app.table_rows) if t not in (None, team(1)))
        row_club = app.table_rows[other]
        labels = [e.label for e in app._row_menu("Table", other, 0)]
        self.assertIn(f"Show only Hull City v {app.labels[row_club]}", labels)

    def test_show_only_from_a_table_row_filters_results_to_the_pair(self):
        app = self.menu_app(focus=team(1))
        app.set_view("Table")
        app.update()
        other = next(i for i, t in enumerate(app.table_rows) if t not in (None, team(1)))
        row_club = app.table_rows[other]
        next(e for e in app._row_menu("Table", other, 0) if e.label.startswith("Show only")).command()
        self.assertEqual(app.opponent_filter, (team(1), row_club))
        self.assertEqual(app.view, "Results")

    def test_a_table_row_offers_no_show_only_for_the_followed_club_or_with_no_followed_club(self):
        app = self.menu_app(focus=team(1))
        app.set_view("Table")
        app.update()
        followed = app.table_rows.index(team(1))
        self.assertFalse([e.label for e in app._row_menu("Table", followed, 0) if e.label.startswith("Show only")])
        app = self.menu_app(focus=None)
        app.set_view("Table")
        app.update()
        row = next(i for i, t in enumerate(app.table_rows) if t is not None)
        self.assertFalse([e.label for e in app._row_menu("Table", row, 0) if e.label.startswith("Show only")])

    def test_a_row_offers_to_copy_each_clubs_results_for_a_post(self):
        app = self.menu_app(focus=None)
        row = self.match_row(app)
        r = app.result_rows[row]
        labels = [e.label for e in app._row_menu("Results", row, 2)]
        self.assertIn(f"Copy {r.home}'s results", labels)
        self.assertIn(f"Copy {r.away}'s results", labels)

    def test_copying_a_clubs_results_from_a_row_copies_that_club_not_the_followed_one(self):
        app = self.menu_app(focus=team(1))
        app.names = {12: "Championship"}
        app.set_view("Table")
        app.update()
        row = next(i for i, t in enumerate(app.table_rows) if t not in (None, team(1)))
        label = app.labels[app.table_rows[row]]
        entry = next(e for e in app._row_menu("Table", row, 0) if e.label == f"Copy {label}'s results")
        with mock.patch.object(fm_review.clipboard, "copy", return_value=True) as copy:
            entry.command()
        self.assertTrue(copy.call_args.args[0].startswith(f"**{label}: "))
        self.assertEqual(app.detail_label.cget("text"), f"Copied {label}'s results for a post, as Markdown and as HTML.")
        self.assertEqual(app.focus, team(1))                        # copying never changes who is followed

    def test_a_club_with_no_played_match_has_a_greyed_copy_results_item(self):
        app = self.app
        self.widen()
        app.install_dataset(dataset(extra=[fx(D(2026, 9, 30), 5, 1, comp=101, md=9)]))   # team 5: nothing played yet
        app.set_focus(None)
        app.set_view("Results")
        app.update()
        row = next(i for i, r in enumerate(app.result_rows) if r.fixture is not None and team(5) in (r.home_id, r.away_id))
        entries = {e.label: e for e in app._row_menu("Results", row, 2) if e.label.endswith("'s results")}
        self.assertIsNone(entries[f"Copy {app.labels[team(5)]}'s results"].command)
        self.assertIsNotNone(entries[f"Copy {app.labels[team(1)]}'s results"].command)

    def test_after_head_to_head_the_next_sheet_selection_replaces_the_pair_in_the_drawer(self):
        app, drawer = self.inspector_app()
        app.install_dataset(dataset(extra=[fx(D(2026, 9, 12), 4, 1, comp=101, md=4)]))
        app._selection = ("pair", (team(1), team(4)))
        app.open_inspector()
        self.assertEqual(drawer.rendered_text()[0], "Head-to-head")
        self.select_match(1, 2)
        self.assertEqual(drawer.rendered_text()[0], "Hull City v Leeds United")

    def test_head_to_head_on_a_grid_cell_opens_the_inspector_on_the_home_and_away(self):
        app = self.menu_app()
        app.set_view("Grid")
        app.update()
        grid = app.grid_data
        # a cell: a (row, column) pair whose two team ids are both resolvable.
        row = next(i for i, t in enumerate(grid.team_ids) if t is not None)
        column = next(j for j, t in enumerate(grid.team_ids) if t is not None and j != row)
        menu = app._row_menu("Grid", row, column)
        head_to_head = next(e for e in menu if e.label.startswith("Head-to-head"))
        self.assertEqual(head_to_head.label, "Head-to-head")
        head_to_head.command()
        self.assertEqual(app._selection, ("pair", (grid.team_ids[row], grid.team_ids[column])))
        self.assertTrue(app.inspector.is_open)

    def test_export_is_greyed_while_an_export_is_running(self):
        app = self.menu_app()
        app._exporting = True
        export = next(e for e in app._row_menu("Results", self.match_row(app), 2) if e.label == "Export")
        self.assertEqual(export.children, ())

    def test_show_only_filters_results_to_the_two_clubs_and_clear_removes_it(self):
        app = self.menu_app()
        app.set_opponent_filter((team(1), team(4)))
        app.update()
        matches = [r for r in app.result_rows if r.fixture is not None]
        self.assertEqual(len(matches), 2)                             # both meetings, either way round
        self.assertTrue(all({r.home_id, r.away_id} == {team(1), team(4)} for r in matches))
        self.assertIn("Showing only Hull City v Derby County", app.note_label.cget("text"))
        self.assertTrue(app.filter_clear.winfo_ismapped())
        app.set_view("Table")
        app.update()
        self.assertFalse(app.filter_clear.winfo_ismapped())
        app.set_view("Results")
        app.filter_clear.invoke()
        app.update()
        self.assertIsNone(app.opponent_filter)
        self.assertGreater(len([r for r in app.result_rows if r.fixture is not None]), 2)
        self.assertFalse(app.filter_clear.winfo_ismapped())

    def test_the_filter_clears_when_the_competition_season_or_team_changes(self):
        app = self.menu_app()
        changes = (lambda: app.select_competition(101), lambda: app._on_season("2027"),
                   lambda: app.set_focus(team(1)))
        for change in changes:
            app.set_opponent_filter((team(1), team(4)))
            self.assertIsNotNone(app.opponent_filter)
            change()
            self.assertIsNone(app.opponent_filter)
            app.select_competition(101)

    def test_the_hub_keeps_the_sheets_own_menu_and_the_other_sheets_use_ours(self):
        app = self.menu_app()
        self.assertTrue(app.sheets[fm_review.HUB].MT.rc_popup_menus_enabled)
        for name in ("Results", "Grid", "Table", fm_review.ANALYSIS):
            self.assertFalse(app.sheets[name].MT.rc_popup_menus_enabled, name)

    def test_a_right_click_selects_the_row_under_the_pointer_and_opens_the_menu(self):
        app = self.menu_app()
        sheet = app.sheets["Results"]
        row = self.match_row(app)
        sheet.see(row=row)
        self.assertTrue(self.wait_until(lambda: sheet.MT.row_positions[row] >= 0))
        app.update()
        y = int(sheet.MT.row_positions[row] - sheet.MT.canvasy(0)) + 5
        with mock.patch.object(tk.Menu, "tk_popup") as popup:
            sheet.MT.event_generate("<Button-3>", x=120, y=y, rootx=300, rooty=300)
            app.update()
        popup.assert_called_once()
        self.assertEqual(sheet.get_currently_selected().row, row)

    def test_enter_on_a_club_opens_its_league_before_its_cups(self):
        cup = [fx(D(2026, 8, 20), 4, 5, 2, 0, comp=103, rnd=fm_review.fd.CompetitionRound.FINAL)]
        app, pal = self.palette_app(self.OTHER_LEAGUE + cup)
        app.open_palette()
        pal.set_query("wrexham")
        clubs = [i.detail for i in pal.results if i.kind == "Club"]
        self.assertEqual(clubs, ["League One · 2 teams", app._competition_detail(app.dataset.by_id[103])])
        pal.run_selected()
        self.assertEqual(app.comp_id, 102)

    # ----------------------------------------------------------------- the inspector drawer

    REPORT = match_stats(LEAGUE[0], 1.82, 0.45)                           # Hull 2-1 Leeds has a match report

    def inspector_app(self, reports=True, focus=team(1)):
        """A wide window on the league's Results, the drawer shut, following `focus`."""
        app = self.app
        self.widen()
        app.install_dataset(dataset(match_stats=self.REPORT if reports else None))
        app.names = {12: "Championship"}
        app.set_focus(focus)
        app.set_view("Results")
        app.update()
        return app, app.inspector

    def select(self, name, row, column=None):
        """Select a row (or a cell) on a sheet the way a click does, then let the window react."""
        sheet = self.app.sheets[name]
        if column is None:
            sheet.select_row(row, run_binding_func=False)
        else:
            sheet.select_cell(row, column, run_binding_func=False)
        self.app._on_sheet_select(name)
        self.app.update()

    def select_match(self, home, away):
        app = self.app
        row = next(i for i, r in enumerate(app.result_rows)
                   if r.fixture is not None and (r.fixture.home_team_id, r.fixture.away_team_id) == (team(home), team(away)))
        self.select("Results", row)

    def test_the_button_ctrl_i_the_palette_and_escape_open_and_close_the_drawer(self):
        app, drawer = self.inspector_app()
        self.assertFalse(drawer.is_open)
        app.inspector_button.invoke()
        self.assertTrue(drawer.is_open)
        app.inspector_button.invoke()
        self.assertFalse(drawer.is_open)
        app.event_generate("<Control-i>")
        app.update()
        self.assertTrue(drawer.is_open)
        app.event_generate("<Escape>")
        app.update()
        self.assertFalse(drawer.is_open)
        app.open_palette()
        app.command_palette.set_query("inspector")
        self.assertEqual(app.command_palette.visible_titles(), ["Show the inspector"])
        app.command_palette.run_selected()
        self.assertTrue(drawer.is_open)
        app.open_palette()
        app.command_palette.set_query("inspector")
        self.assertEqual(app.command_palette.visible_titles(), ["Hide the inspector"])

    def test_escape_in_the_palette_closes_only_the_palette(self):
        app, drawer = self.inspector_app()
        app.open_inspector()
        app.open_palette()
        app.update()
        app.command_palette.entry._entry.event_generate("<Escape>")
        app.update()
        self.assertFalse(app.command_palette.is_open)
        self.assertTrue(drawer.is_open)

    def test_a_match_with_a_report_shows_score_statistics_form_and_meetings(self):
        app, drawer = self.inspector_app()
        app.open_inspector()
        self.select_match(1, 2)
        text = drawer.rendered_text()
        self.assertEqual(text[0], "Hull City v Leeds United")
        self.assertIn("Hull City 2-1 Leeds United", text)
        self.assertIn("xG\t1.82\t0.45", text)
        self.assertIn("Shots\t10\t10", text)
        self.assertIn("Hull City: last 5", text)
        self.assertIn("Meetings (2)", text)
        meeting = next(w for w in drawer._body.winfo_children()
                       if isinstance(w, tk.Label) and w.cget("text") == "  08 Aug  Hull City 2-1 Leeds United")
        self.assertEqual(meeting.cget("bg"), app.theme.list_selected[0])         # the selected one is marked

    def test_a_played_match_with_no_report_says_so(self):
        app, drawer = self.inspector_app(focus=None)
        app.open_inspector()
        self.select_match(3, 4)
        self.assertIn("No match report stored for this match", drawer.rendered_text())
        self.assertFalse([t for t in drawer.rendered_text() if t.startswith("Shots")])

    def test_while_the_statistics_are_still_being_read_it_says_that_instead(self):
        app, drawer = self.inspector_app(reports=False)
        app.open_inspector()
        self.select_match(1, 2)
        self.assertIn("Match statistics are still being read.", drawer.rendered_text())
        app.install_expected_goals(dataset(match_stats=self.REPORT))             # the xG stage lands
        app.update()
        self.assertIn("xG\t1.82\t0.45", drawer.rendered_text())

    def test_a_match_still_to_play_shows_no_statistics(self):
        app, drawer = self.inspector_app()
        app.open_inspector()
        self.select_match(1, 3)                                                  # Hull v Sheffield United, unplayed
        text = drawer.rendered_text()
        self.assertIn("Not played yet.", text)
        self.assertFalse([t for t in text if t.startswith("Shots") or "report" in t])
        self.assertIn("  26 Sep  Hull City to play Sheffield United", text)

    def test_a_club_row_shows_form_run_record_and_the_next_match(self):
        app, drawer = self.inspector_app()
        app.set_view("Table")
        app.update()
        app.open_inspector()
        self.select("Table", app.table_rows.index(team(1)), 0)
        text = drawer.rendered_text()
        self.assertEqual(text[0], "Hull City")
        self.assertIn("Form", text)
        self.assertIn("W W", " ".join(text))
        self.assertIn("Played 2: won 2, drawn 0, lost 0 · goals 5-2", text)
        self.assertIn("Next: Sheffield United (home), Sat 26 Sep", text)

    def pill_points(self, name, row):
        """The centre of each form pill drawn on a sheet's row, left to right, in the canvas's widget coordinates."""
        sheet = self.app.sheets[name]
        canvas = sheet.MT
        top, bottom = canvas.row_positions[row], canvas.row_positions[row + 1]
        boxes = sorted(canvas.bbox(i) for i in canvas.find_withtag(fm_review.SheetOverlay.TAG)
                       if canvas.type(i) == "polygon" and top <= (canvas.bbox(i)[1] + canvas.bbox(i)[3]) / 2 <= bottom)
        return [(int((x1 + x2) / 2 - canvas.canvasx(0)), int((y1 + y2) / 2 - canvas.canvasy(0)))
                for x1, y1, x2, y2 in boxes]

    def test_hovering_a_table_pill_shows_that_match_in_words(self):
        app = self.app
        self.widen()
        app.install_dataset(dataset())
        app.set_view("Table")
        app.update()
        row = app.table_rows.index(team(1))                      # Hull City: WW
        x, y = self.pill_points("Table", row)[0]
        app.sheets["Table"].MT.event_generate("<Motion>", x=x, y=y)
        app.update()
        self.assertTrue(app.tooltip.is_shown)
        self.assertEqual(app.tooltip.text, "Won 2-1 v Leeds United, Sat 8 Aug")

    def test_a_table_pill_in_the_home_split_names_the_home_match(self):
        app = self.app
        self.widen()
        app.install_dataset(dataset())
        app._palette_split("Table", fd.SPLIT_HOME)
        app.update()
        row = app.table_rows.index(team(1))                      # Hull's home form: W, Leeds at home
        x, y = self.pill_points("Table", row)[0]
        app.sheets["Table"].MT.event_generate("<Motion>", x=x, y=y)
        app.update()
        self.assertEqual(app.tooltip.text, "Won 2-1 v Leeds United, Sat 8 Aug")

    def test_hovering_a_pill_in_the_analysis_form_panel_names_that_match(self):
        app = self.app
        self.widen()
        app.install_dataset(dataset())
        app._palette_split(fm_review.ANALYSIS, "Form")
        app.update()
        row = app.analysis_rows.index(team(1))
        points = self.pill_points(fm_review.ANALYSIS, row)
        self.assertEqual(len(points), 2)                          # Hull have played twice
        for (x, y), expected in zip(points, ("Won 2-1 v Leeds United, Sat 8 Aug", "Won 3-1 at Derby County, Sat 15 Aug")):
            app.sheets[fm_review.ANALYSIS].MT.event_generate("<Motion>", x=x, y=y)
            app.update()
            self.assertEqual(app.tooltip.text, expected)

    def test_moving_off_a_pill_or_out_of_the_sheet_hides_the_tooltip(self):
        app = self.app
        self.widen()
        app.install_dataset(dataset())
        app.set_view("Table")
        app.update()
        canvas = app.sheets["Table"].MT
        x, y = self.pill_points("Table", app.table_rows.index(team(1)))[0]
        canvas.event_generate("<Motion>", x=x, y=y)
        canvas.event_generate("<Motion>", x=3, y=y)            # the position column: no pill there
        app.update()
        self.assertFalse(app.tooltip.is_shown)
        canvas.event_generate("<Motion>", x=x, y=y)
        canvas.event_generate("<Leave>", x=x, y=y)
        app.update()
        self.assertFalse(app.tooltip.is_shown)

    def test_a_redraw_under_a_still_pointer_takes_the_tooltip_away(self):
        app = self.app
        self.widen()
        app.install_dataset(dataset())
        app.set_view("Table")
        app.update()
        x, y = self.pill_points("Table", app.table_rows.index(team(1)))[0]
        app.sheets["Table"].MT.event_generate("<Motion>", x=x, y=y)
        self.assertTrue(app.tooltip.is_shown)
        app.overlays["Table"].draw()                             # as after a scroll: the pill under it may change
        self.assertFalse(app.tooltip.is_shown)

    def test_a_theme_change_recolours_the_pill_tooltip(self):
        app = self.app
        app.set_theme("Cyber Pitch")
        self.assertEqual(str(app.tooltip._label.cget("bg")), app.theme.panel)

    def test_the_drawers_form_chips_carry_each_match_in_words(self):
        app, drawer = self.inspector_app()
        expected = ("Won 2-1 v Leeds United, Sat 8 Aug", "Won 3-1 at Derby County, Sat 15 Aug")
        club_chips = next(b for b in app._club_model(team(1)).blocks if isinstance(b, inspector.Chips))
        self.assertEqual(club_chips.tips, expected)
        match = next(f for f in app.fixtures if (f.home_team_id, f.away_team_id) == (team(1), team(2)))
        match_chips = next(b for b in app._match_model(match).blocks if isinstance(b, inspector.Chips))
        self.assertEqual(match_chips.tips, expected)

    def test_the_hub_shows_the_selected_competition(self):
        app, drawer = self.inspector_app()
        app.set_view(fm_review.HUB)
        app.update()
        app.open_inspector()
        self.select(fm_review.HUB, app.comp_row_ids.index(101))
        text = drawer.rendered_text()
        self.assertEqual(text[0], "Championship")
        self.assertEqual(text[1], "Competition 101")                              # named: the id goes in the subtitle
        self.assertIn("2 teams", text)                                           # the hub's own count, from the latest season

    def test_selecting_with_the_drawer_shut_does_not_open_it(self):
        app, drawer = self.inspector_app()
        self.select_match(1, 2)
        self.assertFalse(drawer.is_open)
        app.open_inspector()
        self.assertEqual(drawer.rendered_text()[0], "Hull City v Leeds United")      # but it was kept for later

    def test_opening_with_nothing_selected_shows_the_followed_club_or_asks(self):
        app, drawer = self.inspector_app()
        app.open_inspector()
        self.assertEqual(drawer.rendered_text()[0], "Hull City")
        app.close_inspector()
        app.set_focus(None)
        app.open_inspector()
        self.assertEqual(drawer.rendered_text(), ["Inspector", "Select a match or a club."])

    def test_the_drawer_follows_team_season_theme_and_save_changes(self):
        app, drawer = self.inspector_app()
        app.open_inspector()
        self.select_match(1, 2)
        app.set_focus(team(2))
        self.assertIn("Leeds United: last 5", drawer.rendered_text())
        app.set_theme("Cyber Pitch")
        self.assertEqual(drawer.cget("fg_color"), app.theme.panel)
        app._on_season("2027")
        app.update()
        self.assertNotEqual(drawer.rendered_text()[0], "Hull City v Leeds United")
        app.install_dataset(dataset())
        self.assertFalse(drawer.is_open)

    def test_a_heading_row_and_an_unresolved_team_do_not_break_it(self):
        app, drawer = self.inspector_app(focus=None)
        app.open_inspector()
        heading = next(i for i, r in enumerate(app.result_rows) if r.is_heading)
        self.select("Results", heading)
        self.assertTrue(drawer.rendered_text())
        app.select_competition(70)
        app.set_view("Results")
        app.update()
        row = next(i for i, r in enumerate(app.result_rows) if r.fixture is not None)
        self.select("Results", row)
        self.assertEqual(drawer.rendered_text()[0], "Leeds United v Team 999")

    def test_opening_the_drawer_leaves_keyboard_focus_on_the_sheet(self):
        app, drawer = self.inspector_app()
        sheet = app.sheets["Results"]
        sheet.MT.focus_set()
        app.update()
        app.open_inspector()
        app.update()
        self.assertIs(app.focus_get(), sheet.MT)

    # ----------------------------------------------------------------- v1.7 step 1: head-to-head in the drawer

    def test_a_pair_selection_shows_a_head_to_head_model_titled_from_the_two_clubs(self):
        app, drawer = self.inspector_app()
        app.install_dataset(dataset(extra=[fx(D(2026, 9, 12), 4, 1, comp=101, md=4)]))
        app._selection = ("pair", (team(1), team(4)))
        model = app._inspector_model()
        self.assertEqual(model.title, "Head-to-head")
        self.assertEqual(model.subtitle, "Hull City v Derby County")
        headings = [b for b in model.blocks if isinstance(b, inspector.Heading)]
        self.assertEqual(headings[0].text, "Meetings (2)")

    def test_the_head_to_head_model_groups_meetings_by_competition_and_season_and_marks_none(self):
        app, drawer = self.inspector_app()
        app.install_dataset(dataset(extra=[fx(D(2026, 9, 12), 4, 1, comp=101, md=4)]))
        app._selection = ("pair", (team(1), team(4)))
        model = app._inspector_model()
        lines = [b for b in model.blocks if isinstance(b, inspector.Line)]
        self.assertTrue(any(line.muted and "Championship" in line.text for line in lines))
        self.assertFalse(any(line.marked for line in lines))

    def test_a_pair_with_no_meetings_reads_no_meetings_in_this_save(self):
        app, drawer = self.inspector_app()
        # Add team 5 to the open competition's labels through a 1 v 5 fixture; (3, 5) still never meet.
        app.install_dataset(dataset(extra=[fx(D(2026, 10, 10), 1, 5, comp=101, md=5)]))
        app._selection = ("pair", (team(3), team(5)))
        model = app._inspector_model()
        lines = [b for b in model.blocks if isinstance(b, inspector.Line)]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].text, "No meetings in this save.")
        self.assertTrue(lines[0].muted)

    def test_a_pair_whose_clubs_are_no_longer_in_the_dataset_falls_back_to_the_generic_prompt(self):
        app, drawer = self.inspector_app()
        app._selection = ("pair", (team(1), 9999))        # one unknown id
        model = app._inspector_model()
        self.assertEqual((model.title, model.subtitle), ("Inspector", "Select a match or a club."))

    # ----------------------------------------------------------------- v1.5 step 2: copy for a post

    def post_app(self):
        app = self.app
        app.install_dataset(dataset())
        app.names = {12: "Championship"}
        app.update()
        return app

    def test_copying_the_table_for_a_post_puts_both_formats_on_the_clipboard_and_says_so(self):
        app = self.post_app()
        with mock.patch.object(fm_review.clipboard, "copy", return_value=True) as copy:
            app.copy_for_post("table")
        text, html = copy.call_args.args
        self.assertTrue(text.startswith("**Championship "))
        self.assertIn("<table>", html)
        self.assertEqual(app.detail_label.cget("text"), "Copied the table for a post, as Markdown and as HTML.")

    def test_when_the_windows_clipboard_fails_the_text_still_goes_through_tk(self):
        app = self.post_app()
        with mock.patch.object(fm_review.clipboard, "copy", side_effect=fm_review.clipboard.ClipboardError("busy")), \
                mock.patch.object(app, "clipboard_clear") as clear, mock.patch.object(app, "clipboard_append") as append:
            app.copy_for_post("table")
        clear.assert_called_once()
        self.assertTrue(append.call_args.args[0].startswith("**Championship "))
        self.assertIn("as Markdown only", app.detail_label.cget("text"))

    def test_a_post_that_cannot_be_made_says_why_instead_of_copying_nothing(self):
        app = self.post_app()
        app.set_focus(None)
        with mock.patch.object(fm_review.clipboard, "copy") as copy:
            app.copy_for_post("team")
        copy.assert_not_called()
        self.assertEqual(app.detail_label.cget("text"), "Nothing to copy: follow a club that has played this season to copy its results.")

    def test_the_export_menu_offers_copy_for_a_post_and_greys_what_cannot_apply(self):
        app = self.post_app()
        cascades = [app.export_menu.entrycget(i, "label") for i in range(app.export_menu.index("end") + 1)
                    if app.export_menu.type(i) == "cascade"]
        self.assertEqual(cascades, ["Copy for a post", "Yearbook (PDF)"])
        menu = app.post_menu
        labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)]
        self.assertEqual(labels, ["Table", "My club's results", "Recent results"])
        app._refresh_post_menu()
        self.assertEqual(str(menu.entrycget(1, "state")), "normal")
        app.set_focus(None)
        app._refresh_post_menu()
        self.assertEqual(str(menu.entrycget(1, "state")), "disabled")

    def test_the_palette_offers_the_copies_that_apply(self):
        app = self.post_app()
        pal = app.command_palette

        def offered():
            app.open_palette()
            pal.set_query("copy for a post")
            titles = pal.visible_titles()
            app.close_palette()
            return titles

        self.assertCountEqual(offered(), ["Copy for a post: Table", "Copy for a post: My club's results",
                                          "Copy for a post: Recent results"])     # the palette ranks by title
        app.set_focus(None)
        self.assertCountEqual(offered(), ["Copy for a post: Table", "Copy for a post: Recent results"])
        app._on_season("2027")                                    # nothing played in that season yet
        self.assertCountEqual(offered(), ["Copy for a post: Table"])

    def test_a_competition_too_large_for_a_post_says_so_and_is_greyed(self):
        app = self.post_app()
        with mock.patch.object(fm_review.fx, "POST_ROW_LIMIT", 3), \
                mock.patch.object(fm_review.clipboard, "copy") as copy:
            app._refresh_post_menu()
            self.assertEqual(str(app.post_menu.entrycget(0, "state")), "disabled")       # four teams: too many
            app.copy_for_post("table")
        copy.assert_not_called()
        self.assertEqual(app.detail_label.cget("text"),
                         "Nothing to copy: this competition has more teams than a post can hold (3).")

    def test_when_only_the_text_could_be_copied_it_says_so(self):
        app = self.post_app()
        with mock.patch.object(fm_review.clipboard, "copy", return_value=False):
            app.copy_for_post("table")
        self.assertEqual(app.detail_label.cget("text"),
                         "Copied the table for a post as Markdown only: the HTML version could not be written.")

    def test_closing_the_window_leaves_no_timer_behind(self):
        app = self.app
        app.install_dataset(dataset())
        app.open_palette()
        app.open_inspector()
        app.after(60_000, lambda: None)                     # stands in for any timer the window did not track
        app.update()
        pending = []

        def capture(window):                                # in place of Tk's own destroy, just look
            pending.extend(window.tk.splitlist(window.tk.call("after", "info")))

        with mock.patch.object(ctk.CTk, "destroy", capture):
            app.destroy()
        self.assertEqual(pending, [])

    def test_closing_the_window_with_a_child_widgets_timer_pending_closes_cleanly(self):
        other = fm_review.FMReviewApp()                       # a window of its own: this one is really destroyed
        other.geometry("1300x800+-4000+0")
        child = ctk.CTkTextbox(other)                         # a child widget whose own timer is pending at close
        child.after(60_000, lambda: None)
        other.update()
        other.destroy()                                       # must not raise "can't delete Tcl command"

    def test_the_window_cannot_be_made_narrower_than_the_controls_row_needs(self):
        app = self.app
        wanted = min(app.px(fm_review.MIN_WINDOW_WIDTH), app.winfo_screenwidth())
        self.assertEqual(app.wm_minsize()[0], wanted)
        self.assertGreaterEqual(fm_review.MIN_WINDOW_WIDTH, 1407)

    def test_a_refused_drops_reason_clears_itself_but_not_a_newer_message(self):
        app = self.app
        with mock.patch.object(fm_review, "DROP_NOTE_MS", 40):
            app._on_file_drop(NS(data="C:/nowhere/notes.txt"))
            self.assertIn("not a .fm save", app.detail_label.cget("text"))
            self.assertTrue(self.wait_until(lambda: app.detail_label.cget("text") == ""))
            app._on_file_drop(NS(data="C:/nowhere/notes.txt"))
            app.detail_label.configure(text="something newer")
            time.sleep(0.15)
            app.update()
            self.assertEqual(app.detail_label.cget("text"), "something newer")

    def test_the_right_click_menu_and_its_submenu_follow_the_theme(self):
        app = self.menu_app()
        app.set_theme("Cyber Pitch")
        menu = app._build_menu(app._row_menu("Results", self.match_row(app), 2))
        t = app.theme
        colours = lambda m, *names: tuple(str(m.cget(name)) for name in names)      # noqa: E731
        self.assertEqual(colours(menu, "bg", "fg"), (t.panel, t.text))
        self.assertEqual(colours(menu, "activebackground", "activeforeground"), tuple(t.list_selected))
        self.assertEqual(colours(menu, "disabledforeground"), (t.muted,))
        export = next(i for i in range(menu.index("end") + 1) if menu.type(i) == "cascade")
        self.assertEqual(colours(menu.nametowidget(menu.entrycget(export, "menu")), "bg"), (t.panel,))

    def test_an_unnamed_competition_is_described_by_its_clubs_in_the_palette(self):
        app, pal = self.palette_app()
        youth = app.dataset.by_id[60]
        clubs = ", ".join(youth.top_clubs[:2])
        self.assertEqual(app._competition_detail(youth), f"Competition 60: {clubs} · {youth.team_count} teams")
        self.assertEqual(app._competition_detail(app.dataset.by_id[101]), "Championship · 2 teams")

    # ----------------------------------------------------------------- v1.5 step 3: the Ties panel

    TIE = [fx(D(2026, 9, 2), 5, 4, 2, 0, comp=102, md=1), fx(D(2026, 9, 9), 4, 5, 1, 0, comp=102, md=1)]

    def ties_app(self, comp=102):
        app = self.app
        self.widen()
        app.install_dataset(dataset(extra=self.TIE))
        app.select_competition(comp)
        app._palette_split(fm_review.ANALYSIS, "Ties")
        app.update()
        return app

    def test_the_ties_panel_lists_each_tie_with_its_legs_and_aggregate(self):
        app = self.ties_app()
        data = app.sheets[fm_review.ANALYSIS].get_sheet_data()
        self.assertEqual(data, [["Round 1", "Wrexham v Derby County", "2-0", "0-1", "2-1", "Wrexham go through"]])

    def test_a_tie_of_the_followed_club_is_highlighted(self):
        app = self.ties_app()
        app.set_focus(team(5))                                           # Wrexham
        app.update()
        sheet = app.sheets[fm_review.ANALYSIS]
        self.assertEqual(sheet.props(0, 1, "highlight").bg, app.view_theme.focus[0])
        app.set_focus(team(1))                                           # a club not in the tie
        app.update()
        self.assertFalse(sheet.props(0, 1, "highlight"))

    def test_a_competition_without_ties_says_so(self):                  # a guard: arrived with the panel
        app = self.ties_app(comp=101)                                    # a league: no pair meets twice in a round
        self.assertIn("no two-legged ties", app.message_label.cget("text"))

    def test_a_tie_with_its_second_leg_still_to_play_shows_a_v_and_no_aggregate(self):
        app = self.app
        self.widen()
        pending = [fx(D(2026, 9, 2), 5, 4, 2, 0, comp=102, md=1), fx(D(2026, 9, 9), 4, 5, comp=102, md=1)]
        app.install_dataset(dataset(extra=pending))
        app.select_competition(102)
        app._palette_split(fm_review.ANALYSIS, "Ties")
        app.update()
        self.assertEqual(app.sheets[fm_review.ANALYSIS].get_sheet_data(),
                         [["Round 1", "Wrexham v Derby County", "2-0", "v", "", "Second leg to play"]])

    def test_the_analysis_switch_and_the_palette_offer_ties(self):
        app = self.ties_app()
        self.assertIn("Ties", app.analysis_switch.cget("values"))
        app.open_palette()
        app.command_palette.set_query("analysis ties")
        self.assertEqual(app.command_palette.visible_titles(), ["Analysis: Ties"])

    # ----------------------------------------------------------------- v1.6 step 1: the cup bracket

    def cup_fixtures(self):
        """Eight sides in a knockout cup (competition 106): four quarter-finals, two semi-finals, a final."""
        coded = test_fm_data.CodedValue
        rounds = test_fm_data.CompetitionRound
        qf, sf, final = (coded(rounds.QUARTER_FINAL, 16), coded(rounds.SEMI_FINAL, 17), coded(rounds.FINAL, 19))
        with mock.patch.dict(test_fm_data.CLUBS, {n: (f"Club {n}", f"C{n}") for n in range(6, 9)}):
            return [fx(D(2026, 9, 1), 1, 2, 1, 0, comp=106, md=1, rnd=qf), fx(D(2026, 9, 1), 3, 4, 0, 1, comp=106, md=1, rnd=qf),
                    fx(D(2026, 9, 1), 5, 6, 2, 0, comp=106, md=1, rnd=qf), fx(D(2026, 9, 1), 7, 8, 0, 3, comp=106, md=1, rnd=qf),
                    fx(D(2026, 10, 1), 1, 4, 1, 0, comp=106, md=2, rnd=sf), fx(D(2026, 10, 1), 5, 8, 0, 1, comp=106, md=2, rnd=sf),
                    fx(D(2026, 11, 1), 1, 8, 2, 1, comp=106, md=3, rnd=final)]

    def bracket_app(self, comp=106):
        app = self.app
        self.widen()
        app.install_dataset(dataset(extra=self.cup_fixtures()))
        app.select_competition(comp)
        app._palette_split(fm_review.ANALYSIS, "Bracket")
        app.update()
        return app

    def test_the_bracket_panel_replaces_the_sheet_with_the_cups_tree(self):
        app = self.bracket_app()
        self.assertTrue(app.bracket_view.winfo_ismapped())
        self.assertFalse(app.sheets[fm_review.ANALYSIS].winfo_ismapped())
        text = app.bracket_view.rendered_text()
        for heading in ("Quarter-final", "Semi-final", "Final"):
            self.assertIn(heading, text)

    def test_a_theme_change_recolours_the_bracket(self):
        app = self.bracket_app()
        app.set_theme("Cyber Pitch")
        app.update()
        self.assertEqual(str(app.bracket_view._canvas.cget("bg")), app.theme.table[0])
        self.assertTrue(app.bracket_view.winfo_ismapped())

    # Guards: these follow from the wiring above.
    def test_a_league_says_the_bracket_is_for_cups(self):
        app = self.bracket_app(comp=101)
        self.assertFalse(app.bracket_view.winfo_ismapped())
        self.assertIn("not one", app.message_label.cget("text"))

    def test_leaving_the_bracket_panel_brings_the_sheet_back(self):
        app = self.bracket_app()
        app._palette_split(fm_review.ANALYSIS, "Form")
        app.update()
        self.assertFalse(app.bracket_view.winfo_ismapped())
        self.assertTrue(app.sheets[fm_review.ANALYSIS].winfo_ismapped())

    def test_following_a_club_outlines_its_boxes_and_the_palette_offers_the_panel(self):
        app = self.bracket_app()
        app.set_focus(team(1))
        app.update()
        canvas = app.bracket_view._canvas
        outlined = [i for i in canvas.find_all() if canvas.type(i) == "rectangle"
                    and canvas.itemcget(i, "outline") == app.view_theme.focus[0]]
        self.assertEqual(len(outlined), 3)
        app.open_palette()
        app.command_palette.set_query("analysis bracket")
        self.assertEqual(app.command_palette.visible_titles(), ["Analysis: Bracket"])

    # ----------------------------------------------------------------- v2.0: banking each opened save

    def detail(self):
        return self.app.detail_label.cget("text")

    def test_an_opened_save_is_banked_after_it_is_shown_and_the_detail_bar_says_so(self):
        app = self.app
        data = dataset()
        app.handle_event(("loaded", data))
        self.assertIs(app.dataset, data)                                  # shown at once: banking never delays opening
        self.assertTrue(self.wait_until(lambda: self.detail().startswith("Banked:")), self.detail())
        with archive.Archive.open(fm_review.ARCHIVE_PATH) as book:
            self.assertEqual([r.file_name for r in book.imports()], ["x.fm"])

    def test_opening_the_same_save_again_says_it_is_already_banked(self):
        app = self.app
        app.handle_event(("loaded", dataset()))
        self.assertTrue(self.wait_until(lambda: self.detail().startswith("Banked:")))
        app.handle_event(("loaded", dataset()))
        self.assertTrue(self.wait_until(lambda: self.detail() == "Already banked."), self.detail())

    def with_reports(self, home=1.5, away=0.5):
        """The test save again, with a match report for its first played match."""
        first = next(f for f in dataset().fixtures[101] if f.played)
        return dataset(match_stats=test_fm_data.match_stats(first, home, away))

    def test_the_expected_goals_that_arrive_after_the_save_are_banked_with_it(self):
        app = self.app
        app.handle_event(("loaded", dataset()))
        self.assertTrue(self.wait_until(lambda: self.detail().startswith("Banked:")), self.detail())
        app.handle_event(("xg", self.with_reports()))
        self.assertTrue(self.wait_until(lambda: self.detail().startswith("Expected goals banked for 1 matches")), self.detail())
        with archive.Archive.open(fm_review.ARCHIVE_PATH) as book:
            self.assertEqual(list(book.expected_goals().values()), [(1.5, 0.5)])

    def test_the_expected_goals_wait_for_the_save_to_finish_banking_first(self):
        app = self.app
        real = archive.Archive.bank

        def slow(book, data):
            time.sleep(0.6)
            return real(book, data)

        with mock.patch.object(archive.Archive, "bank", slow):
            app.handle_event(("loaded", dataset()))
            app.handle_event(("xg", self.with_reports()))
            self.assertTrue(self.wait_until(lambda: self.detail().startswith("Expected goals banked"), 10), self.detail())
        with archive.Archive.open(fm_review.ARCHIVE_PATH) as book:
            self.assertEqual(len(book.expected_goals()), 1)

    def test_a_save_with_no_match_reports_adds_nothing_and_says_nothing(self):
        app = self.app
        app.handle_event(("loaded", dataset()))
        self.assertTrue(self.wait_until(lambda: self.detail().startswith("Banked:")))
        app.handle_event(("xg", dataset()))
        self.wait_until(lambda: False, 0.8)
        self.assertTrue(self.detail().startswith("Banked:"), self.detail())

    def test_a_save_that_could_not_be_banked_does_not_get_its_expected_goals_banked_either(self):
        app = self.app
        error = archive.WorldMismatch("These results do not match the archive, so this looks like a different playthrough.")
        with mock.patch.object(archive.Archive, "bank", side_effect=error):
            app.handle_event(("loaded", dataset()))
            self.assertTrue(self.wait_until(lambda: "different playthrough" in self.detail()))
            app.handle_event(("xg", self.with_reports()))
            self.wait_until(lambda: False, 0.8)
        self.assertIn("different playthrough", self.detail())
        with archive.Archive.open(fm_review.ARCHIVE_PATH) as book:
            self.assertEqual(book.expected_goals(), {})

    def test_a_failure_banking_the_expected_goals_is_logged_and_shown_and_the_save_stays_open(self):
        app = self.app
        app.handle_event(("loaded", dataset()))
        self.assertTrue(self.wait_until(lambda: self.detail().startswith("Banked:")))
        with mock.patch.object(archive.Archive, "bank_expected_goals", side_effect=RuntimeError("disk full")):
            data = self.with_reports()
            app.handle_event(("xg", data))
            self.assertTrue(self.wait_until(lambda: "could not be banked" in self.detail()), self.detail())
        self.assertIn("disk full", fm_review.ERROR_LOG.read_text(encoding="utf-8"))
        self.assertIs(app.dataset, data)

    def test_a_save_from_a_different_playthrough_says_so_and_stays_open(self):
        app = self.app
        error = archive.WorldMismatch("These results do not match the archive, so this looks like a different "
                                      "playthrough. Nothing was changed.")
        with mock.patch.object(archive.Archive, "bank", side_effect=error), \
                mock.patch.object(fm_review.messagebox, "showerror") as showerror:
            data = dataset()
            app.handle_event(("loaded", data))
            self.assertTrue(self.wait_until(lambda: "different playthrough" in self.detail()), self.detail())
        showerror.assert_not_called()
        self.assertIs(app.dataset, data)

    def test_a_banking_failure_is_logged_and_shown_and_the_open_save_is_unaffected(self):
        app = self.app
        with mock.patch.object(archive.Archive, "bank", side_effect=RuntimeError("disk full")):
            data = dataset()
            app.handle_event(("loaded", data))
            self.assertTrue(self.wait_until(lambda: "could not be banked" in self.detail()), self.detail())
        self.assertIn("disk full", fm_review.ERROR_LOG.read_text(encoding="utf-8"))
        self.assertIs(app.dataset, data)

    # ----------------------------------------------------------------- v2.0: export the Yearbook

    def bank_into_archive(self, data=None):
        with archive.Archive.open(fm_review.ARCHIVE_PATH) as book:
            book.bank(data or dataset())

    def yearbook_labels(self):
        app = self.app
        app._refresh_yearbook_menu()
        menu = app.yearbook_menu
        return [(menu.entrycget(i, "label"), str(menu.entrycget(i, "state"))) for i in range(menu.index("end") + 1)]

    def test_the_yearbook_menu_lists_the_banked_seasons_newest_first(self):
        self.bank_into_archive()
        self.assertEqual(self.yearbook_labels(), [("2027", "normal"), ("2026", "normal")])

    def test_with_nothing_banked_the_yearbook_menu_says_to_bank_a_save_first_and_creates_no_file(self):
        self.assertEqual(self.yearbook_labels(), [("Bank a save first", "disabled")])
        self.assertFalse(fm_review.ARCHIVE_PATH.exists())

    def test_a_locked_or_damaged_archive_leaves_the_yearbook_menu_empty_not_broken(self):
        self.bank_into_archive()
        with mock.patch.object(archive.Archive, "season_labels", side_effect=sqlite3.OperationalError("database is locked")):
            self.assertEqual(self.yearbook_labels(), [("Bank a save first", "disabled")])

    def test_choosing_a_season_builds_and_renders_that_volume_off_the_main_thread(self):
        app = self.app
        self.bank_into_archive()
        out = Path(self.folder.name) / "exports"
        seen = {}

        def fake_render(book, path):
            seen["book"], seen["path"] = book, Path(path)
            Path(path).write_bytes(b"%PDF-")

        with mock.patch.object(fm_review, "export_folder", return_value=out), \
                mock.patch.object(fm_review.yearbook_pdf, "render", side_effect=fake_render), \
                mock.patch.object(fm_review.messagebox, "askyesno", return_value=False):
            app.names = {12: "Championship"}
            app.export_yearbook(2026)
            self.assertTrue(app._exporting)
            self.assertTrue(self.wait_until(lambda: not app._exporting, 10))
        self.assertEqual(seen["book"].season_label, "2026")
        self.assertEqual(seen["path"], out / "Yearbooks" / "2026" / "Yearbook 2026 (in-game 1 Sep 2026).pdf")
        self.assertIn("Saved the 1 Sep 2026 edition.", self.detail())

    def test_the_yearbook_menu_offers_to_mark_the_followed_club_only_when_one_is_followed(self):
        app = self.app
        app.install_dataset(dataset())
        self.bank_into_archive()
        menu = app.yearbook_menu

        def labels():
            app._refresh_yearbook_menu()
            return [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) != "separator"]

        app.set_focus(None)
        self.assertEqual(labels(), ["2027", "2026"])
        app.set_focus(team(2))
        self.assertEqual(labels(), ["2027", "2026", "Mark Leeds United in bold"])
        self.assertFalse(app.mark_club_var.get())

    def test_the_followed_club_is_marked_in_the_book_only_when_the_tick_is_on(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_focus(team(2))
        self.assertIsNone(app._marked_club_uid())
        app.mark_club_var.set(True)
        self.assertEqual(app._marked_club_uid(), 2)
        app.set_focus(None)
        self.assertIsNone(app._marked_club_uid())

    def test_a_failure_building_the_yearbook_is_shown_and_logged(self):
        app = self.app
        self.bank_into_archive()
        with mock.patch.object(fm_review, "export_folder", return_value=Path(self.folder.name) / "exports"), \
                mock.patch.object(fm_review.yearbook_pdf, "render", side_effect=RuntimeError("out of paper")), \
                mock.patch.object(fm_review.messagebox, "showerror") as showerror:
            app.export_yearbook(2026)
            self.assertTrue(self.wait_until(lambda: not app._exporting, 10))
        self.assertIn("out of paper", showerror.call_args.args[1])
        self.assertIn("out of paper", fm_review.ERROR_LOG.read_text(encoding="utf-8"))

    def test_the_palette_offers_the_newest_volume_only_when_something_is_banked(self):
        app = self.app
        app.install_dataset(dataset())
        titles = lambda: [i.title for i in app._palette_items()]
        self.assertNotIn("Save Yearbook edition…", titles())
        self.bank_into_archive()
        self.assertIn("Save Yearbook edition…", titles())

    # ----------------------------------------------------------------- v2.5: editions and the read window

    def sample_book(self):
        cover = archive.BookCoverage(1, D(2026, 8, 9), D(2026, 8, 9), (), True)
        title = yearbook.TitlePage("2026/27", ("Built from 1 banked save.", "Season in progress."))
        lines = tuple(yearbook.TableLine(i, t, 3, 2, 1, 0, 5, 2, 3, 7, "WWD", "relegation" if i == 2 else "", "▲1", "2.33",
                                         t == "Leeds United") for i, t in enumerate(("Hull City", "Leeds United"), 1))
        week = yearbook.LeaguePage("Premier League", 1, "Matchweek 1 · Sat 8 – Mon 10 Aug",
                                   (yearbook.BookMatch("Sat 8", "Hull City", "Leeds United", "2-0"),), lines, D(2026, 8, 8))
        cup = yearbook.CupBlock("FA Cup", "Round 1", "", "Sat 1 Aug", (yearbook.BookMatch("", "A", "B", "1-0"),), D(2026, 8, 1))
        return yearbook.Yearbook("2026/27", cover, (title, cup, week))

    def sample_volume(self, season=2026):
        built = self.sample_book()
        if season != 2026:
            label = f"{season}/{(season + 1) % 100:02d}"
            title = yearbook.TitlePage(label, ("Built from 2 banked saves.",))
            built = yearbook.Yearbook(label, built.coverage, (title, *built.pages[1:]))
        return yearbook_read.volume(built, season, "test-archive", built.coverage)

    def open_reader(self, volume=None):
        volume = volume or self.sample_volume()
        self.app.show_yearbook_reader(volume)
        reader = self.app.yearbook_reader
        self.app.update()
        return reader, list(volume.pages)

    def test_the_reader_opens_on_the_title_page_and_steps_through_the_book_without_going_past_either_end(self):
        reader, pages = self.open_reader()
        self.assertEqual(reader.heading_label.cget("text"), "Football Yearbook 2026/27")
        self.assertIn("Page 1 of 3", reader.page_label.cget("text"))
        reader.previous()
        self.assertEqual(reader.index, 0)
        reader.next()
        reader.next()
        reader.next()
        self.assertEqual(reader.index, 2)
        self.assertIn("Page 3 of 3", reader.page_label.cget("text"))

    def test_a_table_page_shows_the_pdfs_columns_its_lines_and_its_footnote(self):
        reader, pages = self.open_reader()
        reader.show(2)
        self.assertEqual(list(reader.sheet.headers()), list(pages[2].columns))
        self.assertEqual([list(r) for r in reader.sheet.get_sheet_data()], [list(r) for r in pages[2].rows])
        self.assertIn("Sat 8   Hull City 2-0 Leeds United", reader.lines_box.get("1.0", "end"))
        self.assertIn("Table calculated from the results.", reader.notes_label.cget("text"))
        self.assertIn("± is the change in place", reader.notes_label.cget("text"))

    def trajectory_volume(self):
        built = self.sample_book()
        chart = yearbook.Trajectory("Premier League", 4, (
            yearbook.TrajectoryPoint(1, D(2026, 8, 8), 3, (yearbook.BookMatch("Sat 8", "Hull City", "Leeds United", "2-0"),)),
            yearbook.TrajectoryPoint(2, D(2026, 8, 15), None), yearbook.TrajectoryPoint(3, D(2026, 8, 22), 1)),
            (("relegation", 4, 4),))
        page = yearbook.TrajectoryPage("Leeds United", (chart,))
        built = yearbook.Yearbook("2026/27", built.coverage, (*built.pages, page))
        return yearbook_read.volume(built, 2026, "test-archive", built.coverage)

    def test_a_trajectory_page_draws_the_chart_and_a_hover_lists_results_without_a_cause(self):
        reader, pages = self.open_reader(self.trajectory_volume())
        reader.show(3)
        self.app.update()
        pane = reader.panes[0]
        self.assertTrue(pane.chart.winfo_ismapped())
        self.assertGreater(len(pane.chart.find_all()), 8)                      # line, points, bands, ticks
        point, x, y = pane.chart.current_layout.points[0]
        pane.chart.hover_at(x + 2, y + 1)
        self.assertEqual(pane.chart.hover_text, "Matchweek 1, to Sat 8 Aug: 3rd. Results that matchweek: Hull City 2-0 Leeds United.")
        pane.chart.hover_at(x + 300, y)
        self.assertEqual(pane.chart.hover_text, "")
        self.assertIn("Matchweek numbers are not calendar weeks", reader.notes_label.cget("text"))
        reader.show(2)
        self.app.update()
        self.assertFalse(pane.chart.winfo_ismapped())

    def test_a_page_without_a_table_hides_the_sheet(self):
        reader, _ = self.open_reader()
        self.assertFalse(reader.sheet.winfo_ismapped())
        reader.show(2)
        self.app.update()
        self.assertTrue(reader.sheet.winfo_ismapped())

    def test_choosing_a_competition_in_the_contents_jumps_to_its_first_page(self):
        reader, pages = self.open_reader()
        labels = list(reader.contents_list.get(0, "end"))
        self.assertEqual(labels, ["Title page", "FA Cup", "Premier League"])
        reader.contents_list.selection_clear(0, "end")
        reader.contents_list.selection_set(2)
        reader.contents_list.event_generate("<<ListboxSelect>>")
        self.app.update()
        self.assertEqual(reader.index, 2)
        reader.show(1)
        self.assertEqual(reader.contents_list.curselection(), (1,))          # the list follows the page

    def test_the_marked_club_is_highlighted_in_the_sheet(self):
        reader, _ = self.open_reader()
        reader.show(2)
        self.assertEqual(reader.marked_rows, (1,))

    def test_save_this_edition_saves_the_volume_being_read_and_closing_writes_nothing(self):
        with mock.patch.object(self.app, "save_reader_volume") as save:
            reader, _ = self.open_reader()
            reader.close_button.invoke()
            save.assert_not_called()
            volume = self.sample_volume()
            reader, _ = self.open_reader(volume)
            reader.save_button.invoke()
        save.assert_called_once_with(volume)

    def test_the_arrow_keys_and_escape_work_in_the_reader(self):
        reader, _ = self.open_reader()
        reader.focus_force()
        reader.event_generate("<Right>")
        self.app.update()
        self.assertEqual(reader.index, 1)
        reader.event_generate("<Left>")
        self.app.update()
        self.assertEqual(reader.index, 0)
        reader.event_generate("<Escape>")
        self.app.update()
        self.assertFalse(reader.winfo_exists())

    def test_a_theme_change_recolours_an_open_reader(self):
        reader, _ = self.open_reader()
        reader.show(2)
        other = palette.THEMES[1]
        self.app.set_theme(other.name)
        self.assertEqual(reader.cget("fg_color"), other.window)

    def test_a_second_request_loads_the_requested_volume_into_the_same_window(self):
        reader, _ = self.open_reader()
        reader.show(2)
        other = self.sample_volume(2025)
        self.app.show_yearbook_reader(other)
        self.app.update()
        self.assertIs(self.app.yearbook_reader, reader)
        self.assertIs(reader.volume, other)
        self.assertEqual(reader.title(), "Read the Yearbook 2025/26")
        self.assertEqual(reader.heading_label.cget("text"), "Football Yearbook 2025/26")
        self.assertEqual(list(reader.contents_list.get(0, "end")), [label for label, _ in other.contents])

    def test_reading_another_season_while_the_reader_is_open_shows_that_season(self):
        app = self.app
        self.bank_into_archive()
        app.names = {12: "Championship"}
        app.read_yearbook(2026)
        self.assertTrue(self.wait_until(lambda: app.yearbook_reader is not None and not app._exporting, 15))
        reader = app.yearbook_reader
        app.read_yearbook(2027)
        self.assertTrue(self.wait_until(lambda: reader.volume.season == 2027 and not app._exporting, 15))
        self.assertIs(app.yearbook_reader, reader)
        self.assertEqual(reader.heading_label.cget("text"), "Football Yearbook 2027")

    # ----------------------------------------------------------------- v2.8: bookmarks and the edition snapshot

    def test_closing_the_reader_bookmarks_its_page_and_reopening_the_volume_returns_to_it(self):
        reader, pages = self.open_reader()
        reader.show(2)
        reader.close_button.invoke()
        self.app.update()
        saved = json.loads(fm_review.SETTINGS_PATH.read_text(encoding="utf-8"))["yearbook_bookmarks"]
        self.assertEqual(saved, {"test-archive|2026": {"edition": "2026-08-09", "page_key": pages[2].page_key}})
        reader, _ = self.open_reader()
        self.assertEqual(reader.index, 2)

    def test_each_volume_keeps_its_own_bookmark_when_the_open_reader_changes_volume(self):
        reader, pages = self.open_reader()
        reader.show(2)
        self.app.show_yearbook_reader(self.sample_volume(2025))
        self.assertEqual(reader.index, 0)
        reader.show(1)
        self.app.show_yearbook_reader(self.sample_volume())
        self.assertEqual(reader.index, 2)

    def test_a_bookmark_in_a_shape_this_program_never_writes_opens_the_title_page(self):
        for value in ("junk", {"test-archive|2026": {"page_key": 7}}, {"test-archive|2026": {"page_key": "league/99/1"}}):
            self.app.settings["yearbook_bookmarks"] = value
            reader, _ = self.open_reader()
            self.assertEqual(reader.index, 0, value)
            reader.destroy()

    # ----------------------------------------------------------------- v2.8: reader spreads, strip and styling

    def wide_volume(self, cups=0, name="FA Cup"):
        """The sample book with a fourth page (an odd last page in a spread), or `cups` extra competitions."""
        built = self.sample_book()
        extra = [yearbook.LeaguePage("Premier League", 2, "Matchweek 2 · Sat 15 Aug", (), built.pages[2].table,
                                     D(2026, 8, 15))]
        extra += [yearbook.CupBlock(f"{name} {n}", "Final", "", "Sat 1 May", (yearbook.BookMatch("", "A", "B", "1-0"),),
                                    D(2027, 5, 1), competition_key=n) for n in range(cups)]
        built = yearbook.Yearbook(built.season_label, built.coverage, (*built.pages, *extra))
        return yearbook_read.volume(built, 2026, "test-archive", built.coverage)

    def open_wide(self, volume=None, width=1500):
        reader, pages = self.open_reader(volume or self.wide_volume())
        reader.geometry(f"{width}x800")
        self.wait_until(lambda: abs(reader.winfo_width() - width) < 40)
        return reader, pages

    def test_a_reader_spread_shows_two_pages_side_by_side_with_the_title_and_an_odd_last_page_alone(self):
        reader, pages = self.open_wide()
        reader.set_mode("spread")
        self.app.update()
        self.assertEqual(reader.shown, (0,))
        self.assertFalse(reader.panes[1].winfo_ismapped())
        reader.next()
        self.app.update()
        self.assertEqual(reader.shown, (1, 2))
        self.assertEqual([p.heading_label.cget("text") for p in reader.panes], [pages[1].heading, pages[2].heading])
        self.assertTrue(reader.panes[1].winfo_ismapped())
        self.assertEqual(reader.page_label.cget("text"), "Pages 2–3 of 4 · reader spread")
        reader.next()
        self.app.update()
        self.assertEqual(reader.shown, (3,))
        self.assertFalse(reader.panes[1].winfo_ismapped())
        self.assertEqual(reader.next_button.cget("state"), "disabled")
        reader.previous()
        self.assertEqual(reader.shown, (1, 2))

    def test_a_window_too_narrow_for_a_spread_shows_single_pages_and_says_so(self):
        reader, _ = self.open_wide(width=1000)
        reader.set_mode("spread")
        reader.show(1)
        self.app.update()
        self.assertEqual(reader.shown, (1,))
        self.assertIn("widen the window for a reader spread", reader.page_label.cget("text"))

    def test_narrowing_the_window_falls_back_to_single_pages_and_widening_it_restores_the_spread(self):
        reader, _ = self.open_wide()
        reader.set_mode("spread")
        reader.show(1)
        self.app.update()
        self.assertEqual(reader.shown, (1, 2))
        reader.geometry("1000x800")
        self.assertTrue(self.wait_until(lambda: reader.shown == (1,), 3))
        reader.geometry("1500x800")
        self.assertTrue(self.wait_until(lambda: reader.shown == (1, 2), 3))

    def test_the_reader_mode_is_remembered_for_the_next_reader(self):
        reader, _ = self.open_wide()
        reader.set_mode("spread")
        self.assertEqual(self.app.settings["yearbook_reader_mode"], "spread")
        reader.destroy()
        reader, _ = self.open_reader()
        self.assertEqual(reader.mode, "spread")
        self.app.settings["yearbook_reader_mode"] = ["junk"]
        reader.destroy()
        reader, _ = self.open_reader()
        self.assertEqual(reader.mode, "single")

    def test_home_and_end_go_to_the_first_and_last_page(self):
        reader, pages = self.open_wide()
        reader.focus_force()
        reader.event_generate("<End>")
        self.app.update()
        self.assertEqual(reader.index, len(pages) - 1)
        reader.event_generate("<Home>")
        self.app.update()
        self.assertEqual(reader.index, 0)

    def strip_texts(self, reader):
        return [tile.cget("text") for tile in reader.strip_tiles if tile.winfo_manager()]

    def test_the_chapter_strip_draws_only_a_bounded_window_of_chapters_and_jumps_to_one(self):
        volume = self.wide_volume(cups=20, name="The Extraordinarily Long Regional Cup")
        reader, pages = self.open_wide(volume)
        texts = self.strip_texts(reader)
        self.assertLessEqual(len(texts), yearbook_read.STRIP_SPAN + 2)
        self.assertEqual(len(reader.strip_tiles), yearbook_read.STRIP_SPAN + 2)       # never more tiles than that
        self.assertTrue(texts[-1].endswith("more ›"))
        self.assertTrue(all(len(t) <= yearbook_read.STRIP_CHARS for t in texts if "more" not in t))
        chapter = next(t for t in reader.strip_tiles if t.cget("text").startswith("FA Cup"))
        chapter.event_generate("<Button-1>")
        self.app.update()
        self.assertEqual(reader.index, dict(volume.contents)["FA Cup"])
        reader.show(len(pages) - 1)
        self.assertTrue(self.strip_texts(reader)[0].startswith("‹ "))

    def test_the_heading_face_is_the_first_serif_installed_or_the_plain_face_when_none_is(self):
        with mock.patch.object(yearbook_reader_ui.tkfont, "families", return_value=("Segoe UI", "Times New Roman")):
            self.assertEqual(yearbook_reader_ui.serif_family(self.app), "Times New Roman")
        with mock.patch.object(yearbook_reader_ui.tkfont, "families", return_value=("Cambria", "Georgia")):
            self.assertEqual(yearbook_reader_ui.serif_family(self.app), "Georgia")
        with mock.patch.object(yearbook_reader_ui.tkfont, "families", return_value=("Segoe UI",)):
            self.assertEqual(yearbook_reader_ui.serif_family(self.app), yearbook_reader_ui.FONT)

    def test_headings_are_set_in_a_serif_and_tables_keep_their_plain_font_and_colours(self):
        installed = [f for f in yearbook_reader_ui.SERIF_FAMILIES if f in tkfont.families(self.app)]
        if not installed:
            self.skipTest(f"none of {', '.join(yearbook_reader_ui.SERIF_FAMILIES)} is installed on this machine")
        reader, _ = self.open_wide()
        heading = reader.panes[0].heading_label.cget("font")
        self.assertEqual(heading.cget("family"), installed[0])
        reader.show(2)
        self.app.update()
        self.assertEqual(reader.sheet.ops.table_font[0], "Segoe UI")
        self.assertEqual(reader.sheet.ops.table_fg, self.app.theme.table[1])

    def moved_on(self):
        """The archive after a later save of the same playthrough: the 2026 volume now runs to 21 Sep."""
        later = dataset(extra=[fx(D(2026, 10, 3), 3, 4, md=9)])
        return dataclasses.replace(later, info=dataclasses.replace(later.info, game_date=D(2026, 9, 21), file_name="y.fm"))

    def open_banked_reader(self):
        app = self.app
        self.bank_into_archive()
        app.names = {12: "Championship"}
        app.read_yearbook(2026)
        self.assertTrue(self.wait_until(lambda: app.yearbook_reader is not None and not app._exporting, 15))
        return app.yearbook_reader

    def save_and_wait(self, volume, answer=None):
        out = Path(self.folder.name) / "exports"

        def fake_render(book, path):
            Path(path).write_bytes(b"%PDF-")

        with mock.patch.object(fm_review, "export_folder", return_value=out), \
                mock.patch.object(fm_review.yearbook_pdf, "render", side_effect=fake_render) as render, \
                mock.patch.object(fm_review.messagebox, "askyesno", return_value=False), \
                mock.patch.object(fm_review.messagebox, "askyesnocancel", return_value=answer) as ask:
            self.app.save_reader_volume(volume)
            self.assertTrue(self.wait_until(lambda: not self.app._exporting, 15))
        return render, ask

    def test_saving_from_the_reader_saves_exactly_the_book_being_read(self):
        reader = self.open_banked_reader()
        render, ask = self.save_and_wait(reader.volume)
        ask.assert_not_called()
        self.assertIs(render.call_args[0][0], reader.volume.book)
        self.assertEqual(render.call_args[0][1].name, "Yearbook 2026 (in-game 1 Sep 2026).pdf")

    def test_when_a_newer_save_was_banked_the_reader_names_both_editions_before_saving(self):
        reader = self.open_banked_reader()
        volume = reader.volume
        self.bank_into_archive(self.moved_on())
        render, ask = self.save_and_wait(volume, answer=None)              # Cancel
        render.assert_not_called()
        message = ask.call_args[0][1]
        self.assertIn("1 Sep 2026", message)
        self.assertIn("21 Sep 2026", message)
        self.assertIs(reader.volume, volume)

    def test_choosing_the_edition_being_read_saves_that_snapshot_under_its_own_date(self):
        reader = self.open_banked_reader()
        volume = reader.volume
        self.bank_into_archive(self.moved_on())
        render, _ = self.save_and_wait(volume, answer=False)               # No: keep the edition being read
        self.assertIs(render.call_args[0][0], volume.book)
        self.assertEqual(render.call_args[0][1].name, "Yearbook 2026 (in-game 1 Sep 2026).pdf")
        self.assertIs(reader.volume, volume)

    def test_choosing_to_refresh_loads_the_newer_edition_into_the_reader_then_saves_it(self):
        reader = self.open_banked_reader()
        volume = reader.volume
        self.bank_into_archive(self.moved_on())
        render, _ = self.save_and_wait(volume, answer=True)                # Yes: refresh to the newer edition
        self.assertIsNot(reader.volume, volume)
        self.assertEqual(reader.volume.edition, "2026-09-21")
        self.assertIs(render.call_args[0][0], reader.volume.book)
        self.assertEqual(render.call_args[0][1].name, "Yearbook 2026 (in-game 21 Sep 2026).pdf")

    def test_reading_builds_off_the_main_thread_then_opens_the_window_and_changes_nothing_on_disk(self):
        app = self.app
        self.bank_into_archive()
        out = Path(self.folder.name) / "exports"
        with mock.patch.object(fm_review, "export_folder", return_value=out):
            app.names = {12: "Championship"}
            app.read_yearbook(2026)
            self.assertTrue(app._exporting)
            self.assertTrue(self.wait_until(lambda: app.yearbook_reader is not None and not app._exporting, 15))
        self.assertIn("Football Yearbook 2026", app.yearbook_reader.heading_label.cget("text"))
        self.assertFalse(out.exists())

    def test_each_season_in_the_yearbook_menu_offers_save_read_and_its_saved_editions_newest_first(self):
        app = self.app
        self.bank_into_archive()
        out = Path(self.folder.name) / "exports"
        shelf = yearbook_editions.season_folder(out, "2026")
        shelf.mkdir(parents=True)
        for d in (D(2026, 8, 1), D(2026, 9, 1)):
            (shelf / yearbook_editions.edition_file_name("2026", d)).write_bytes(b"%PDF-")
        with mock.patch.object(fm_review, "export_folder", return_value=out):
            app._refresh_yearbook_menu()
            menu = app.yearbook_menu
            index = next(i for i in range(menu.index("end") + 1) if menu.type(i) == "cascade" and menu.entrycget(i, "label") == "2026")
            sub = menu.nametowidget(menu.entrycget(index, "menu"))
            labels = [sub.entrycget(i, "label") for i in range(sub.index("end") + 1) if sub.type(i) != "separator"]
        # the 1 Sep edition matches the banked save's in-game date, so it can be built again
        self.assertEqual(labels[:3], ["Save the latest edition", "Build it again", "Read before saving…"])
        self.assertEqual(labels[-2:], ["1 Sep 2026 edition", "1 Aug 2026 edition"])

    def test_choosing_a_saved_edition_opens_that_file_and_does_not_rebuild_it(self):
        app = self.app
        self.bank_into_archive()
        out = Path(self.folder.name) / "exports"
        shelf = yearbook_editions.season_folder(out, "2026")
        shelf.mkdir(parents=True)
        path = shelf / yearbook_editions.edition_file_name("2026", D(2026, 8, 1))
        path.write_bytes(b"%PDF-")
        with mock.patch.object(fm_review, "export_folder", return_value=out), \
                mock.patch.object(app, "_open_path") as opened, \
                mock.patch.object(fm_review.yearbook_pdf, "render") as render:
            app._refresh_yearbook_menu()
            menu = app.yearbook_menu
            index = next(i for i in range(menu.index("end") + 1) if menu.type(i) == "cascade" and menu.entrycget(i, "label") == "2026")
            sub = menu.nametowidget(menu.entrycget(index, "menu"))
            last = sub.index("end")
            sub.invoke(last)
        opened.assert_called_once_with(path)
        render.assert_not_called()

    def test_saving_the_same_coverage_twice_says_the_edition_is_already_saved_and_writes_nothing_more(self):
        app = self.app
        self.bank_into_archive()
        out = Path(self.folder.name) / "exports"

        def fake_render(book, path):
            Path(path).write_bytes(b"%PDF-")

        with mock.patch.object(fm_review, "export_folder", return_value=out), \
                mock.patch.object(fm_review.yearbook_pdf, "render", side_effect=fake_render) as render, \
                mock.patch.object(fm_review.messagebox, "askyesno", return_value=False):
            app.export_yearbook(2026)
            self.assertTrue(self.wait_until(lambda: not app._exporting, 10))
            first = self.detail()
            app.export_yearbook(2026)
            self.assertTrue(self.wait_until(lambda: not app._exporting, 10))
        self.assertIn("edition", first)
        self.assertEqual(self.detail(), "This edition is already saved.")
        self.assertEqual(render.call_count, 1)

    def test_the_palette_offers_to_save_an_edition_and_to_open_the_latest_one_only_when_one_exists(self):
        app = self.app
        app.install_dataset(dataset())
        titles = lambda: [i.title for i in app._palette_items()]
        self.assertNotIn("Save Yearbook edition…", titles())
        self.bank_into_archive()
        out = Path(self.folder.name) / "exports"
        with mock.patch.object(fm_review, "export_folder", return_value=out):
            self.assertIn("Save Yearbook edition…", titles())
            self.assertNotIn("Open latest Yearbook", titles())
            shelf = yearbook_editions.season_folder(out, "2027")
            shelf.mkdir(parents=True)
            (shelf / yearbook_editions.edition_file_name("2027", D(2027, 5, 1))).write_bytes(b"%PDF-")
            self.assertIn("Open latest Yearbook", titles())


class ScheduleHubWiringTests(unittest.TestCase):
    """Tests for the Schedule and Hub view wiring added in v2.7 stage 5."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        folder = Path(self.folder.name)
        patches = [
            mock.patch.object(fm_review, "SETTINGS_PATH", folder / "settings.json"),
            mock.patch.object(fm_review, "NAMES_PATH", folder / "names.csv"),
            mock.patch.object(fm_review, "ERROR_LOG", folder / "errors.log"),
            mock.patch.object(fm_review, "ARCHIVE_PATH", folder / "archive.sqlite"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        ctk.set_appearance_mode("dark")
        self.app = fm_review.FMReviewApp()
        self.app.geometry("1300x800+-4000+0")
        self.app.report_callback_exception = lambda *exc: (_ for _ in ()).throw(exc[1])
        self.app.update()

    def tearDown(self):
        stop = time.monotonic() + 0.3
        while time.monotonic() < stop:
            self.app.update()
            time.sleep(0.02)
        self.app.destroy()
        self.folder.cleanup()

    def wait_for(self, condition, seconds=10.0):
        stop = time.monotonic() + seconds
        while time.monotonic() < stop:
            self.app.update()
            if condition():
                return True
            time.sleep(0.02)
        return False

    def follow_hull(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_focus(team(1))
        self.assertTrue(self.wait_for(lambda: app._schedule_view._schedule is not None), "schedule never arrived")

    def _start_reading(self):
        """Leave the window as it is while a save's expected goals are still being read."""
        app = self.app
        app._reading_xg = True
        app.loading_since = time.monotonic()
        app.open_button.configure(state="disabled")
        app.reopen_button.configure(state="disabled")

    def test_a_schedule_finishing_mid_load_keeps_the_controls_locked(self):
        app = self.app
        self.follow_hull()
        snap = fd.manager_snapshot(app.dataset, app._followed_uid)
        self._start_reading()
        app.handle_event(("schedule_ready", (app._schedule_serial, app._schedule_view._schedule, snap, {}, None)))
        self.assertEqual(app.open_button.cget("state"), "disabled")
        self.assertEqual(app.reopen_button.cget("state"), "disabled")
        self.assertTrue(app._reading_xg)
        self.assertIsNotNone(app.loading_since)
        app.handle_event(("xg", app.dataset))            # the last outstanding work
        self.assertEqual(app.open_button.cget("state"), "normal")
        self.assertFalse(app._reading_xg)

    def test_a_schedule_from_an_older_selection_is_ignored_mid_load(self):
        app = self.app
        self.follow_hull()
        current = app._schedule_view._schedule
        snap = fd.manager_snapshot(app.dataset, app._followed_uid)
        self._start_reading()
        app.handle_event(("schedule_ready", (app._schedule_serial - 1, None, snap, {}, None)))
        self.assertIs(app._schedule_view._schedule, current)
        self.assertEqual(app.open_button.cget("state"), "disabled")

    def test_schedule_and_hub_appear_in_views(self):
        self.assertIn(fm_review.SCHEDULE, fm_review.VIEWS)
        self.assertIn(fm_review.MANAGER_HUB, fm_review.VIEWS)

    def test_schedule_and_hub_sit_beside_the_switch_not_on_it(self):
        app = self.app
        app.install_dataset(dataset())
        self.assertEqual(list(fm_review.SWITCH_VIEWS), ["Results", "Grid", "Table", "Analysis", "Competitions"])
        self.assertNotIn(fm_review.SCHEDULE, app.view_labels)
        app.schedule_button.invoke()
        self.assertEqual(app.view, fm_review.SCHEDULE)
        self.assertEqual(app.view_switch.get(), "")              # no competition view is selected
        app.hub_button.invoke()
        self.assertEqual(app.view, fm_review.MANAGER_HUB)

    def test_the_schedule_names_its_club_and_scope(self):
        app = self.app
        self.follow_hull()
        app.set_view(fm_review.SCHEDULE)
        text = app.coverage_label.cget("text")
        self.assertIn("Hull City", text)
        self.assertIn("every competition", text)

    def test_clearing_the_followed_club_empties_schedule_and_hub_at_once(self):
        app = self.app
        self.follow_hull()
        app._clear_followed_uid()
        self.assertIsNone(app._schedule_view._schedule)
        self.assertEqual(app._manager_hub_view._rows, [])
        app.set_view(fm_review.SCHEDULE)
        self.assertIn("No club followed", app.coverage_label.cget("text"))

    def test_a_new_save_empties_schedule_and_hub(self):
        app = self.app
        self.follow_hull()
        app.install_dataset(dataset())
        self.assertIsNone(app._schedule_view._schedule)
        self.assertEqual(app._manager_hub_view._rows, [])

    def test_install_dataset_clears_followed_uid(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_focus(team(1))               # team_id 100; club uid 1
        self.assertIsNotNone(app._followed_uid)
        app.install_dataset(dataset())       # new save
        self.assertIsNone(app._followed_uid)

    def test_set_focus_with_valid_team_sets_followed_uid(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_focus(team(1))               # team_id 100; club uid 1
        self.assertIsNotNone(app._followed_uid)
        self.assertEqual(app._followed_uid.club_uid, 1)

    def test_set_focus_none_does_not_clear_followed_uid(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_focus(team(1))
        self.assertIsNotNone(app._followed_uid)
        app.set_focus(None)
        self.assertIsNotNone(app._followed_uid, "browsing other competitions must not clear _followed_uid")

    def test_set_view_schedule_shows_schedule_view(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view(fm_review.SCHEDULE)
        app.update()
        self.assertTrue(app._schedule_view.winfo_ismapped())
        self.assertFalse(app._manager_hub_view.winfo_ismapped())

    def test_set_view_hub_shows_manager_hub_view(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view(fm_review.MANAGER_HUB)
        app.update()
        self.assertTrue(app._manager_hub_view.winfo_ismapped())
        self.assertFalse(app._schedule_view.winfo_ismapped())

    def test_schedule_and_hub_do_not_update_last_comp_view(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view("Results")
        app.set_view(fm_review.SCHEDULE)
        self.assertEqual(app.last_comp_view, "Results")
        app.set_view(fm_review.MANAGER_HUB)
        self.assertEqual(app.last_comp_view, "Results")

    def test_sync_view_controls_disables_season_and_team_for_schedule(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view(fm_review.SCHEDULE)
        app.update()
        self.assertEqual(app.season_menu.cget("state"), "disabled")
        self.assertEqual(app.team_box.cget("state"), "disabled")

    def test_sync_view_controls_disables_season_and_team_for_hub(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view(fm_review.MANAGER_HUB)
        app.update()
        self.assertEqual(app.season_menu.cget("state"), "disabled")
        self.assertEqual(app.team_box.cget("state"), "disabled")

    # ----------------------------------------------------------------- v2.9: roundels (made-up clubs and dates)

    INVENTED = {1: ("Northbridge Rovers", "Northbridge"), 2: ("Eastholm Athletic", "Eastholm"),
                3: ("Westford Town", "Westford"), 4: ("Southmere United", "Southmere"), 5: ("Kingsbay City", "Kingsbay")}
    INVENTED_COLOURS = {"Northbridge Rovers": ["#7a1f2b", "#f2c94c"], "Eastholm Athletic": ["#0b3d91", "#ffffff"]}

    def invented_dataset(self, fixtures, game_date=D(2099, 8, 20)):
        with mock.patch.dict(test_fm_data.CLUBS, self.INVENTED):
            built = [f(fx) for f in fixtures]
            return fd.build_dataset(dataclasses.replace(info(), game_date=game_date), built,
                                    clubs=[club(n) for n in range(1, 6)], competitions=[NS(id=101, database_id=12)])

    def invented_season(self):
        return self.invented_dataset([
            lambda fx: fx(D(2099, 8, 8), 1, 2, 2, 1, md=1), lambda fx: fx(D(2099, 8, 8), 3, 4, 1, 1, md=1),
            lambda fx: fx(D(2099, 8, 15), 3, 1, 0, 0, md=2), lambda fx: fx(D(2099, 8, 15), 2, 4, 2, 0, md=2),
            lambda fx: fx(D(2099, 8, 22), 1, 4, md=3), lambda fx: fx(D(2099, 8, 22), 2, 3, md=3),
        ])

    def follow_invented(self, data=None):
        app = self.app
        app.settings["club_colours"] = dict(self.INVENTED_COLOURS)
        app.install_dataset(data or self.invented_season())
        app.set_focus(team(1))
        self.assertTrue(self.wait_for(lambda: app._schedule_view._schedule is not None), "schedule never arrived")

    def disc_fill(self, canvas, tag):
        (item,) = canvas.find_withtag(tag)
        return canvas.itemcget(item, "fill")

    def test_the_fixture_gap_choice_is_remembered_in_the_settings(self):
        app = self.app
        self.assertFalse(app._schedule_view._show_gaps)                      # off by default
        app._schedule_view.set_show_gaps(True)
        self.assertIs(app.settings.get(fm_review.SCHEDULE_GAPS), True)
        saved = json.loads(fm_review.SETTINGS_PATH.read_text(encoding="utf-8"))
        self.assertIs(saved[fm_review.SCHEDULE_GAPS], True)
        app.settings[fm_review.SCHEDULE_GAPS] = True
        again = fm_review.FMReviewApp()
        self.addCleanup(again.destroy)
        self.assertTrue(again._schedule_view._show_gaps)

    def test_each_schedule_row_shows_its_opponents_roundel_or_the_neutral_one(self):
        app = self.app
        self.follow_invented()
        app.set_view(fm_review.SCHEDULE)
        app.update()
        view, theme = app._schedule_view, app.view_theme
        canvas = view._canvas
        opponents = [i.opponent_club for i in view._filtered]
        self.assertEqual(opponents, ["Eastholm Athletic", "Westford Town", "Southmere United"])
        self.assertEqual(self.disc_fill(canvas, "disc_0"), palette.roundel(theme, ("#0b3d91", "#ffffff"), "EA").disc)
        self.assertEqual(self.disc_fill(canvas, "disc_1"), palette.roundel(theme, None, "WT").disc)
        self.assertEqual(canvas.itemcget(canvas.find_withtag("initials_0")[0], "text"), "EA")

    def test_result_pills_keep_their_letters_venue_and_theme_colours_beside_the_roundels(self):
        app = self.app
        self.follow_invented()
        app.set_view(fm_review.SCHEDULE)
        app.update()
        canvas = app._schedule_view._canvas
        self.assertIsNotNone(app.club_tint)                       # the followed club tints the window...
        self.assertEqual(self.disc_fill(canvas, "pill_0"), app.theme.colours["W"][0])   # ...but never a result
        texts = [canvas.itemcget(i, "text") for i in canvas.find_withtag("row_0") if canvas.type(i) == "text"]
        self.assertIn("W", texts)
        self.assertTrue(any(t.startswith("H ") for t in texts), texts)

    def test_the_hub_shows_the_followed_clubs_roundel_and_the_next_opponents(self):
        app = self.app
        self.follow_invented()
        app.set_view(fm_review.MANAGER_HUB)
        app.update()
        hub = app._manager_hub_view
        self.assertEqual(hub.club_badge.roundel.disc, "#7a1f2b")
        self.assertEqual(hub.club_badge.roundel.initials, "NR")
        self.assertEqual(hub.next_badge.roundel, palette.roundel(app.view_theme, None, "SU"))

    def test_a_theme_change_repaints_the_roundels_in_that_theme(self):
        app = self.app
        self.follow_invented()
        app.set_view(fm_review.SCHEDULE)
        app.set_theme(palette.HIGH_CONTRAST.name)
        app.update()
        canvas = app._schedule_view._canvas
        (ring,) = canvas.find_withtag("ring_0")
        self.assertEqual(canvas.itemcget(ring, "outline"), palette.HIGH_CONTRAST.table[1])
        self.assertEqual(app._manager_hub_view.club_badge.roundel.rim, palette.HIGH_CONTRAST.table[1])

    # ----------------------------------------------------------------- v2.9: the Hub's matchday stepper

    def open_hub(self, data=None):
        app = self.app
        self.follow_invented(data)
        self.assertTrue(self.wait_for(lambda: app._manager_hub_view.season is not None), "the stepper never arrived")
        app.set_view(fm_review.MANAGER_HUB)
        app.update()
        return app._manager_hub_view

    def hub_values(self, hub):
        return {row.label: row.value for row in hub._rows}

    def meeting_season(self, played=True):
        return self.invented_dataset([
            lambda fx: fx(D(2099, 8, 8), 1, 4, 2 if played else None, 1 if played else None, md=1),
            lambda fx: fx(D(2099, 8, 8), 3, 2, 0 if played else None, 0 if played else None, md=1),
            lambda fx: fx(D(2099, 8, 15), 4, 1, md=2), lambda fx: fx(D(2099, 8, 15), 2, 3, md=2),
        ], game_date=D(2099, 8, 10))

    def test_the_hub_shows_the_previous_meeting_and_never_the_last_clubs_or_saves(self):
        app = self.app
        hub = self.open_hub(self.meeting_season())
        self.assertEqual(self.hub_values(hub)["Previous meeting"],
                         "8 Aug 2099 ┬À Competition 101 ┬À Northbridge Rovers 2-1 Southmere United")
        app.set_focus(test_fm_data.team(3))                              # another club: nothing of the first one's
        self.assertNotIn("Previous meeting", self.hub_values(hub))       # while it builds
        self.assertTrue(self.wait_for(lambda: "Previous meeting" in self.hub_values(hub)), "no hub for the new club")
        self.assertEqual(self.hub_values(hub)["Previous meeting"],
                         "8 Aug 2099 ┬À Competition 101 ┬À Westford Town 0-0 Eastholm Athletic")
        app.install_dataset(self.meeting_season(played=False))           # another save: the old result is gone
        self.assertNotIn("Previous meeting", self.hub_values(hub))
        app.set_focus(test_fm_data.team(1))
        self.assertTrue(self.wait_for(lambda: "Previous meeting" in self.hub_values(hub)), "no hub for the new save")
        self.assertEqual(self.hub_values(hub)["Previous meeting"], "No earlier meeting found in this save")

    def test_the_stepper_opens_at_the_saves_date_and_names_the_matchday_and_its_snapshot_date(self):
        hub = self.open_hub()
        self.assertEqual(hub.index, 2)                                      # 20 Aug: before matchday 3
        self.assertEqual(hub.step_label.cget("text"), "Matchday 3 · Before kick-off, Sat 22 Aug 15:00 (the save's date)")
        self.assertTrue(hub.stepper.winfo_ismapped())

    def test_previous_and_next_move_the_table_form_and_next_fixture_together(self):
        hub = self.open_hub()
        hub.previous_button.invoke()
        self.app.update()
        self.assertEqual(hub.index, 1)
        values = self.hub_values(hub)
        self.assertEqual(values["Position"], "1st of 4 · 3 pts from 1 played (calculated from the results)")
        self.assertEqual(values["Form"], "W (all competitions)")
        self.assertEqual(values["Next league match"], "Westford Town (away) · 15 Aug 2099")
        self.assertIn("Northbridge Rovers", [r[1] for r in hub.excerpt_rows() if r[-1]])
        self.assertEqual(hub.next_badge.roundel, palette.roundel(self.app.view_theme, None, "WT"))
        hub.next_button.invoke()
        self.assertEqual(hub.index, 2)
        self.assertEqual(hub.next_button.cget("state"), "disabled")
        hub.previous_button.invoke()
        hub.previous_button.invoke()
        self.assertEqual(hub.previous_button.cget("state"), "disabled")

    def test_dragging_the_slider_settles_once_and_never_recalculates_the_season(self):
        hub = self.open_hub()
        shown = []
        original = hub.show_step
        with mock.patch.object(fd, "calculate_standings", side_effect=AssertionError("recalculated")), \
                mock.patch.object(fd, "hub_season", side_effect=AssertionError("recalculated")), \
                mock.patch.object(hub, "show_step", side_effect=lambda i: (shown.append(i), original(i))):
            for value in (1.4, 0.2, 0.0, 0.6, 0.1):
                hub.slider.set(value)
                hub._on_slider(value)
            self.assertEqual(shown, [])                                       # nothing until the drag pauses
            self.assertTrue(self.wait_for(lambda: shown, 2))
            self.wait_for(lambda: False, 0.4)
        self.assertEqual(shown, [0])
        self.assertEqual(hub.index, 0)

    def test_today_returns_to_the_saves_own_date(self):
        hub = self.open_hub()
        hub.show_step(0)
        hub.today_button.invoke()
        self.assertEqual(hub.index, 2)

    def test_with_no_save_date_today_is_unavailable_and_says_why(self):
        hub = self.open_hub(self.invented_dataset([
            lambda fx: fx(D(2099, 8, 8), 1, 2, 2, 1, md=1), lambda fx: fx(D(2099, 8, 15), 3, 1, md=2)], game_date=None))
        self.assertEqual(hub.today_button.cget("state"), "disabled")
        self.assertIn("The save's date is unknown", hub.step_label.cget("text"))

    def test_following_another_club_or_opening_another_save_resets_the_stepper(self):
        app = self.app
        hub = self.open_hub()
        hub.show_step(0)
        app.set_focus(team(2))
        self.assertIsNone(hub.season)                                        # emptied at once, not left on the old club
        self.assertTrue(self.wait_for(lambda: hub.season is not None and hub.season.followed.club_uid == 2))
        self.assertEqual(hub.index, hub.season.today)
        app.install_dataset(self.invented_season())
        self.assertIsNone(hub.season)
        self.assertFalse(hub.stepper.winfo_ismapped())

    def _fg(self, button) -> str:
        c = button.cget("fg_color")
        return c if isinstance(c, str) else c[0]

    def test_schedule_button_shows_active_colour_when_schedule_view_is_open(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view(fm_review.SCHEDULE)
        app.update()
        self.assertEqual(self._fg(app.schedule_button), app.theme.accent[0])

    def test_hub_button_shows_active_colour_when_hub_view_is_open(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view(fm_review.MANAGER_HUB)
        app.update()
        self.assertEqual(self._fg(app.hub_button), app.theme.accent[0])

    def test_schedule_button_returns_to_quiet_when_another_view_is_open(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view(fm_review.SCHEDULE)
        app.set_view("Results")
        app.update()
        self.assertEqual(self._fg(app.schedule_button), app.theme.quiet[0])

    def test_hub_button_returns_to_quiet_when_another_view_is_open(self):
        app = self.app
        app.install_dataset(dataset())
        app.set_view(fm_review.MANAGER_HUB)
        app.set_view("Results")
        app.update()
        self.assertEqual(self._fg(app.hub_button), app.theme.quiet[0])


class PathsTests(unittest.TestCase):
    """Where settings and the error log live, depending on whether the app is frozen."""

    def test_app_dir_is_the_source_folder_when_not_frozen(self):
        self.assertEqual(
            fm_review._resolve_app_dir(
                frozen=False,
                executable=Path(r"X:\python.exe"),
                source=Path(r"C:\Box2Box\fm_review.py"),
            ),
            Path(r"C:\Box2Box"),
        )

    def test_app_dir_is_the_executable_folder_when_frozen(self):
        self.assertEqual(
            fm_review._resolve_app_dir(
                frozen=True,
                executable=Path(r"C:\Users\Me\Desktop\Box2Box\Box2Box.exe"),
                source=Path(r"C:\Users\Me\Desktop\Box2Box\_internal\fm_review.pyc"),
            ),
            Path(r"C:\Users\Me\Desktop\Box2Box"),
        )


class BundleDirTests(unittest.TestCase):
    """Where read-only bundled data (the icon, LICENSE) lives, apart from the files the app writes."""

    def test_bundle_dir_is_the_source_folder_when_not_frozen(self):
        self.assertEqual(
            fm_review._resolve_bundle_dir(frozen=False, meipass=None, source=Path(r"C:\Box2Box\fm_review.py")),
            Path(r"C:\Box2Box"),
        )

    def test_bundle_dir_is_the_pyinstaller_data_folder_when_frozen(self):
        self.assertEqual(
            fm_review._resolve_bundle_dir(
                frozen=True,
                meipass=r"C:\Users\Me\Desktop\Box2Box\_internal",
                source=Path(r"C:\Users\Me\Desktop\Box2Box\_internal\fm_review.pyc"),
            ),
            Path(r"C:\Users\Me\Desktop\Box2Box\_internal"),
        )

    def test_a_frozen_build_without_a_data_folder_falls_back_to_the_source_folder(self):
        self.assertEqual(
            fm_review._resolve_bundle_dir(frozen=True, meipass=None, source=Path(r"C:\app\fm_review.pyc")),
            Path(r"C:\app"),
        )

    def test_the_icon_and_licence_are_read_from_the_bundle_and_the_written_files_stay_beside_the_app(self):
        self.assertEqual(fm_review.ICON_PATH, fm_review.BUNDLE_DIR / "icon" / "football-64-sky-blue.ico")
        self.assertEqual(fm_review.LICENCE_PATH, fm_review.BUNDLE_DIR / "LICENSE")
        for written in (fm_review.SETTINGS_PATH, fm_review.ERROR_LOG, fm_review.ARCHIVE_PATH, fm_review.NAMES_PATH):
            self.assertEqual(written.parent, fm_review.APP_DIR)

    def test_in_a_frozen_one_file_build_the_written_files_sit_beside_the_exe_not_in_the_temporary_folder(self):
        exe = Path(r"C:\Users\Me\Box2Box.exe")
        temporary = r"C:\Users\Me\AppData\Local\Temp\_MEI12345"
        source = Path(temporary) / "fm_review.pyc"
        app = fm_review._resolve_app_dir(frozen=True, executable=exe, source=source)
        bundle = fm_review._resolve_bundle_dir(frozen=True, meipass=temporary, source=source)
        self.assertEqual((app, bundle), (Path(r"C:\Users\Me"), Path(temporary)))


class IconTests(unittest.TestCase):
    def test_the_icon_is_a_windows_icon(self):
        data = fm_review.ICON_PATH.read_bytes()
        self.assertEqual(data[:4], b"\x00\x00\x01\x00")              # an .ico header
        self.assertGreaterEqual(int.from_bytes(data[4:6], "little"), 1)

    @unittest.skipUnless(sys.platform == "win32", "the taskbar identity is a Windows setting")
    def test_the_taskbar_knows_box2box_by_its_own_name(self):
        self.assertTrue(fm_review.set_taskbar_identity())
        found = ctypes.c_wchar_p()
        ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(found))
        try:
            self.assertEqual(found.value, "hawkers63.Box2Box")
        finally:
            ctypes.windll.ole32.CoTaskMemFree(found)


class DropAcceptanceTests(unittest.TestCase):
    """What dropping files onto the window means, decided without a window."""

    def test_one_save_is_accepted_whatever_the_case_or_the_name(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("a.fm", "B.FM", "My Career (v02) [copy].fm", "Saison été.fm"):
                path = Path(folder) / name
                path.write_bytes(b"x")
                self.assertEqual(fm_review.accept_dropped_save([str(path)]), (path, ""), name)

    def test_anything_else_is_refused_with_its_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            save, other, directory = Path(folder) / "a.fm", Path(folder) / "notes.txt", Path(folder) / "dir.fm"
            save.write_bytes(b"x")
            other.write_bytes(b"x")
            directory.mkdir()
            for paths, message in (
                ([], "Drop one .fm save to open it."),
                ([str(save), str(save)], "Drop one .fm save at a time."),
                ([str(other)], "notes.txt is not a .fm save."),
                ([str(directory)], "dir.fm is a folder, not a .fm save."),
                ([str(Path(folder) / "gone.fm")], "gone.fm could not be found."),
            ):
                self.assertEqual(fm_review.accept_dropped_save(paths), (None, message), paths)


class AboutTextTests(unittest.TestCase):
    """The About screen's wording, checked without opening a window."""

    def test_about_shows_the_current_version(self):
        with mock.patch.object(fm_review, "VERSION", "9.8"):
            text = "\n".join(fm_review.about_text())
        self.assertIn("Version 9.8", text)

    def test_about_shows_the_copyright_line_of_the_licence(self):
        self.assertIn(COPYRIGHT, fm_review.about_text())
        licence = Path(fm_review.__file__).with_name("LICENSE").read_text(encoding="utf-8")
        self.assertEqual(licence.splitlines()[0], COPYRIGHT)        # the same wording as the licence

    def test_about_notice_points_to_the_licence(self):
        notice = fm_review.about_text().notice
        self.assertIn("proprietary", notice)
        self.assertIn("LICENSE", notice)

    def test_licence_terms_are_read_with_each_paragraph_on_one_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "LICENSE"
            path.write_text("The first paragraph,\nwrapped by hand.\n\nThe second.\n", encoding="utf-8")
            self.assertEqual(fm_review.licence_text(path), "The first paragraph, wrapped by hand.\n\nThe second.")

    def test_a_missing_licence_says_where_the_terms_are(self):
        with tempfile.TemporaryDirectory() as folder:
            text = fm_review.licence_text(Path(folder) / "LICENSE")
        self.assertIn("not found", text)
        self.assertIn("https://github.com/hawkers63/Box2Box", text)


if __name__ == "__main__":
    unittest.main()
