"""Tests for the small tooltip shown over form pills and chips."""

from __future__ import annotations

import time
import unittest

import customtkinter as ctk

import palette
import tooltip


class TooltipTests(unittest.TestCase):
    def setUp(self):
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.geometry("600x400+-4000+0")
        self.tip = tooltip.Tooltip(self.root, theme=palette.MIDNIGHT_EMERALD)
        self.root.update()

    def tearDown(self):
        stop = time.monotonic() + 0.3
        while time.monotonic() < stop:
            self.root.update()
            time.sleep(0.02)
        self.root.destroy()

    def test_show_puts_the_text_in_a_borderless_window_near_the_pointer(self):
        self.tip.show("Won 1-0 v Leeds United, Sat 1 Aug", -3900, 100)
        self.root.update()
        self.assertTrue(self.tip.is_shown)
        self.assertEqual(self.tip.text, "Won 1-0 v Leeds United, Sat 1 Aug")
        self.assertTrue(self.tip.window.overrideredirect())
        self.assertGreater(self.tip.window.winfo_rootx(), -3900)          # offset from the pointer, not under it

    def test_showing_it_leaves_the_keyboard_where_it_was(self):
        entry = ctk.CTkEntry(self.root)
        entry.pack()
        entry.focus_set()
        self.root.update()
        self.tip.show("Won 1-0 v Leeds United, Sat 1 Aug", -3900, 100)
        self.root.update()
        self.assertIs(self.root.focus_get(), entry._entry)

    def test_a_new_theme_recolours_it(self):
        theme = palette.theme_by_name("Cyber Pitch")
        self.tip.restyle(theme)
        self.assertEqual((str(self.tip._label.cget("bg")), str(self.tip._label.cget("fg"))), (theme.panel, theme.text))

    def test_hide_takes_it_away(self):
        self.tip.show("Lost 0-1 at Sheffield United, Sat 8 Aug", -3900, 100)
        self.root.update()
        self.tip.hide()
        self.root.update()
        self.assertFalse(self.tip.is_shown)
        self.assertFalse(self.tip.window.winfo_viewable())


if __name__ == "__main__":
    unittest.main()
