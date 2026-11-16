# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Smoke test for the Box2Box window with a small made-up dataset, and its About screen.

Run:  .venv\\Scripts\\python -m unittest -v
"""

import ctypes
import dataclasses
import json
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import customtkinter as ctk

import club_colours
import command_palette
import fm_data as fd
import fm_review
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
        self.assertEqual(list(app.view_labels.values()), list(fm_review.VIEWS))        # no save: plain names
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
        self.assertEqual(list(app.view_labels.values()), list(fm_review.VIEWS))
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
        self.assertIn("Unverified build", app.verify_label.cget("text"))
        theme = app.theme
        self.assertEqual(app.verify_label.cget("text_color"), theme.warning)
        self.assertEqual(app.verify_chip.cget("fg_color"), theme.panel)
        self.assertNotEqual(app.top_bar.cget("fg_color"), theme.panel)          # the band really is tinted
        for name in ("Cyber Pitch", "Deep Slate & Gold", "High-Contrast"):       # and so in every other theme
            app.set_theme(name)
            self.assertEqual(app.verify_label.cget("text_color"), app.theme.warning, name)
            self.assertEqual(app.verify_chip.cget("fg_color"), app.theme.panel, name)

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
        app.update()                                         # focus moves to the box before keys are sent
        pal.set_query("table")
        self.assertEqual(pal.results[0].title, "Table")
        pal.entry._entry.event_generate("<Return>")
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
        self.assertEqual((pal.results[0].title, pal.results[0].detail), ("Derby County", "Competition 60 · 2 teams"))
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
        self.assertIsNone(head_to_head.command)                       # greyed until v2.0
        export = next(e for e in menu if e.label == "Export")
        self.assertEqual([c.label for c in export.children],
                         ["Excel workbook (.xlsx)", "Web page (.html)", "CSV files (.csv)"])
        self.assertEqual(labels[-1], "Copy")

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

    def test_a_table_row_offers_follow_unless_followed_a_greyed_head_to_head_and_export(self):
        app = self.menu_app(focus=team(1))
        app.set_view("Table")
        app.update()
        followed = app.table_rows.index(team(1))
        other = next(i for i, t in enumerate(app.table_rows) if t not in (None, team(1)))
        self.assertNotIn("Follow Hull City", [e.label for e in app._row_menu("Table", followed, 0)])
        menu = app._row_menu("Table", other, 0)
        self.assertEqual(menu[0].label, f"Follow {app.labels[app.table_rows[other]]}")
        self.assertIsNone(next(e for e in menu if e.label.startswith("Head-to-head")).command)
        self.assertEqual([e.label for e in menu][-2:], ["Export", "Copy"])

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
        self.assertEqual(clubs, ["League One · 2 teams", "Competition 103 · 2 teams"])
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
        self.assertIn("Meetings this season", text)
        meeting = next(w for w in drawer._body.winfo_children()
                       if isinstance(w, tk.Label) and w.cget("text") == "08 Aug  Hull City 2-1 Leeds United")
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
        self.assertIn("26 Sep  Hull City to play Sheffield United", text)

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
