# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Smoke test for the Box2Box window with a small made-up dataset, and its About screen.

Run:  .venv\\Scripts\\python -m unittest -v
"""

import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import customtkinter as ctk

import fm_data as fd
import fm_review
from test_fm_data import LEAGUE, D, club, fx, info, row, team, unresolved_away

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


def dataset() -> fd.Dataset:
    fixtures = LEAGUE + [
        fx(D(2027, 8, 7), 1, 2, season=2027, md=1),                          # next season, unplayed
        fx(D(2026, 7, 20), 1, 5, 2, 2, comp=131, season=None),               # a friendly
        fx(D(2026, 8, 10), 1, 4, 1, 0, comp=60, home_slot=1, away_slot=1),   # youth league
        unresolved_away(fx(D(2026, 8, 9), 2, 3, 1, 0, comp=70, md=1)),       # a team the save can't resolve
    ]
    stored = NS(competition_id=101, rows=(row(1, 1, 2, 2, 0, 0, 5, 2, 6), row(4, 2), row(2, 3), row(3, 4)))
    rules = [NS(competition_id=101, promotion_places=1, playoff_places=1, relegation_places=1, rounds=())]
    return fd.build_dataset(info(), fixtures, clubs=[club(1, slots=(0, 1)), club(2), club(3), club(4), club(5)],
                            competitions=[NS(id=101, database_id=12)], tables=[stored], rules=rules)


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
        self.assertIn("cyan = play-offs", note)
        app.set_focus(team(3))
        table = app.sheets["Table"]
        table.select_column(3, redraw=False, run_binding_func=False)
        app._on_sheet_select("Table")
        self.assertEqual(app.focus, team(3))               # a header click used to follow the leaders
        table.select_cell(1, 1, redraw=False, run_binding_func=False)
        app._on_sheet_select("Table")
        self.assertEqual(app.focus, team(4))               # Derby are second in the stored table
        app._on_table_split(fd.SPLIT_HOME)
        self.assertNotIn("Pos colours", app.note_label.cget("text"))

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
