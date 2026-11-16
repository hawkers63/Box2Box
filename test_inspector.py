"""Tests for the inspector drawer widget (its content model is drawn; building it is the window's job)."""

from __future__ import annotations

import time
import unittest

import customtkinter as ctk

import fm_data as fd
import inspector
import palette

ROWS = (fd.StatLine("xG", "1.82", "0.45"), fd.StatLine("Shots", "14", "—"))
MODEL = inspector.InspectorModel(
    "Hull City v Leeds United", "Sat 15 Aug · 15:00",
    (inspector.Line("Hull City 2-1 Leeds United"),
     inspector.Heading("Statistics"),
     inspector.Stats("Hull City", "Leeds United", ROWS),
     inspector.Heading("Hull City: last 5"),
     inspector.Chips("WWD?L", "Unbeaten in 3"),
     inspector.Line("No match report stored for this match", muted=True),
     inspector.Line("15 Aug  Hull City 2-1 Leeds United", marked=True)))


class InspectorTests(unittest.TestCase):
    def setUp(self):
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.geometry("900x700+-4000+0")
        self.closed = []
        self.drawer = inspector.Inspector(self.root, px=lambda v: int(v), font=("Segoe UI", 10),
                                          theme=palette.MIDNIGHT_EMERALD, on_close=lambda: self.closed.append(1))
        self.root.update()

    def tearDown(self):
        stop = time.monotonic() + 0.3
        while time.monotonic() < stop:
            self.root.update()
            time.sleep(0.02)
        self.root.destroy()

    def test_it_draws_every_piece_of_the_model_in_order(self):
        self.drawer.show(MODEL)
        self.assertEqual(self.drawer.rendered_text(), [
            "Hull City v Leeds United", "Sat 15 Aug · 15:00", "Hull City 2-1 Leeds United", "Statistics",
            "Hull City", "Leeds United", "xG\t1.82\t0.45", "Shots\t14\t—", "Hull City: last 5", "W W D ? L",
            "Unbeaten in 3", "No match report stored for this match", "15 Aug  Hull City 2-1 Leeds United"])

    def test_chips_take_the_themes_result_colours_including_unknown(self):
        self.drawer.show(MODEL)
        self.root.update()
        chips = [w for w in self.drawer._body.winfo_children()[-3].winfo_children() if w.cget("text") in "WDL?"]
        self.assertEqual([c.cget("text") for c in chips], list("WWD?L"))
        for chip in chips:
            self.assertEqual(chip.cget("bg"), palette.MIDNIGHT_EMERALD.colours[chip.cget("text")][0])

    def test_a_marked_line_uses_the_selection_colours(self):
        self.drawer.show(MODEL)
        marked = self.drawer._body.winfo_children()[-1]
        self.assertEqual((marked.cget("bg"), marked.cget("fg")), tuple(palette.MIDNIGHT_EMERALD.list_selected))

    def test_showing_again_replaces_the_content_and_leaks_nothing(self):
        self.drawer.show(MODEL)
        count = len(self.drawer._body.winfo_children())
        self.drawer.show(inspector.InspectorModel("Another", "", (inspector.Line("only this"),)))
        self.assertEqual(self.drawer.rendered_text(), ["Another", "only this"])
        self.assertEqual(len(self.drawer._body.winfo_children()), 1)
        self.drawer.show(MODEL)
        self.assertEqual(len(self.drawer._body.winfo_children()), count)

    def test_a_new_theme_recolours_without_changing_the_text(self):
        self.drawer.show(MODEL)
        before = self.drawer.rendered_text()
        theme = palette.theme_by_name("Cyber Pitch")
        self.drawer.restyle(theme)
        self.assertEqual(self.drawer.rendered_text(), before)
        self.assertEqual(self.drawer.cget("fg_color"), theme.panel)
        self.assertEqual(self.drawer._title.cget("fg"), theme.text)

    def test_open_places_it_and_close_removes_it_and_says_so(self):
        self.drawer.show(MODEL)
        self.drawer.open()
        self.root.update()
        self.assertTrue(self.drawer.is_open and self.drawer.winfo_ismapped())
        self.drawer.close()
        self.root.update()
        self.assertFalse(self.drawer.winfo_ismapped())
        self.assertEqual(self.closed, [1])
        self.drawer.close()                                          # closing a shut drawer says nothing more
        self.assertEqual(self.closed, [1])

    def test_the_close_mark_closes_it(self):
        self.drawer.open()
        self.root.update()
        self.drawer._close.event_generate("<Button-1>")
        self.root.update()
        self.assertFalse(self.drawer.is_open)

    def test_opening_does_not_take_keyboard_focus(self):
        other = ctk.CTkEntry(self.root)
        other.pack()
        other.focus_set()
        self.root.update()
        self.drawer.show(MODEL)
        self.drawer.open()
        self.root.update()
        self.assertIs(self.root.focus_get(), other._entry)

    def long_model(self, lines=60):
        return inspector.InspectorModel("Long", "", tuple(inspector.Line(f"line {n}") for n in range(lines)))

    def test_a_model_taller_than_the_drawer_scrolls_with_the_wheel(self):
        self.root.geometry("900x300+-4000+0")
        self.drawer.open()
        self.drawer.show(self.long_model())
        self.root.update()
        view = self.drawer._viewport
        self.assertEqual(view.yview()[0], 0.0)
        view.event_generate("<MouseWheel>", delta=-120, x=10, y=10)
        self.root.update()
        self.assertGreater(view.yview()[0], 0.0)

    def test_the_wheel_over_a_line_scrolls_the_drawer_too(self):
        self.root.geometry("900x300+-4000+0")
        self.drawer.open()
        self.drawer.show(self.long_model())
        self.root.update()
        self.drawer._body.winfo_children()[3].event_generate("<MouseWheel>", delta=-120, x=5, y=5)
        self.root.update()
        self.assertGreater(self.drawer._viewport.yview()[0], 0.0)

    def test_a_new_model_starts_at_the_top(self):
        self.root.geometry("900x300+-4000+0")
        self.drawer.open()
        self.drawer.show(self.long_model())
        self.root.update()
        self.drawer._viewport.yview_moveto(0.5)
        self.drawer.show(self.long_model(70))
        self.root.update()
        self.assertEqual(self.drawer._viewport.yview()[0], 0.0)

    def test_redrawing_the_same_model_keeps_the_scroll_position(self):
        self.root.geometry("900x300+-4000+0")
        self.drawer.open()
        self.drawer.show(self.long_model())
        self.root.update()
        self.drawer._viewport.yview_moveto(0.5)
        where = self.drawer._viewport.yview()[0]
        self.drawer.restyle(palette.theme_by_name("Cyber Pitch"))      # redraws the same model
        self.drawer.show(self.long_model())                              # an equal model, as a re-render sends
        self.root.update()
        self.assertAlmostEqual(self.drawer._viewport.yview()[0], where, places=3)

    def test_a_short_model_does_not_scroll(self):
        self.root.geometry("900x700+-4000+0")
        self.drawer.open()
        self.drawer.show(self.long_model(3))
        self.root.update()
        self.drawer._viewport.event_generate("<MouseWheel>", delta=-120, x=10, y=10)
        self.root.update()
        self.assertEqual(self.drawer._viewport.yview()[0], 0.0)

    def test_the_close_mark_is_a_solid_cross(self):
        self.assertEqual(self.drawer._close.cget("text"), "×")

    def test_a_model_with_no_subtitle_shows_none(self):
        self.drawer.show(inspector.InspectorModel("Title only"))
        self.assertEqual(self.drawer.rendered_text(), ["Title only"])


if __name__ == "__main__":
    unittest.main()
