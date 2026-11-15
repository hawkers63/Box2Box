# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for palette: the colour themes, how readable they are, and the followed club's colours.

Run:  .venv\\Scripts\\python -m unittest -v
"""

import unittest

import palette


class ThemeTests(unittest.TestCase):
    def test_midnight_emerald_is_todays_palette(self):
        me = palette.MIDNIGHT_EMERALD
        self.assertEqual((dict(me.colours), dict(me.zones), me.heading, me.focus),
                         (palette.COLOURS, palette.ZONE_COLOURS, palette.HEADING, palette.FOCUS))
        self.assertEqual((me.table, me.accent, me.section, me.link),
                         (("#1b1b1b", "#E3E3E3"), ("#1F6AA5", "#DCE4EE"), "#d8b44a", "#60a5fa"))

    def test_unknown_missing_or_odd_names_give_midnight_emerald(self):
        for name in (None, "", "Neon Dreams", 3, ["Cyber Pitch"]):
            self.assertIs(palette.theme_by_name(name), palette.MIDNIGHT_EMERALD)
        self.assertIs(palette.theme_by_name("Midnight Emerald"), palette.MIDNIGHT_EMERALD)

    def test_every_theme_covers_every_result_and_zone(self):
        for theme in palette.THEMES:
            self.assertEqual(set(theme.colours), set(palette.COLOURS), theme.name)
            self.assertEqual(set(theme.zones), set(palette.ZONE_COLOURS), theme.name)
            self.assertEqual(set(theme.categories), set(palette.MIDNIGHT_EMERALD.categories), theme.name)

    def test_the_four_themes_in_order(self):
        self.assertEqual([t.name for t in palette.THEMES],
                         ["Midnight Emerald", "Cyber Pitch", "Deep Slate & Gold", "High-Contrast"])
        self.assertIs(palette.theme_by_name("High-Contrast"), palette.HIGH_CONTRAST)

    def test_high_contrast_pairs_all_read_at_4_5(self):
        hc = palette.HIGH_CONTRAST
        pairs = [p for p in hc.colours.values() if p[1]] + list(hc.zones.values()) + list(hc.categories.values())
        pairs += [hc.heading, hc.focus, hc.yours_row, hc.table, hc.sheet_heading, hc.accent, hc.quiet,
                  hc.competition_list, hc.list_selected, (hc.switch[0], hc.switch[1]),
                  (hc.switch_selected, hc.switch[1]), (hc.table[0], hc.link), (hc.panel, hc.text),
                  (hc.panel, hc.muted), (hc.panel, hc.warning), (hc.competition_list[0], hc.section)]
        for background, text in pairs:
            self.assertGreaterEqual(palette.contrast_ratio(background, text), 4.5, (background, text))
        self.assertFalse(hc.club_colours)

    def test_controls_read_at_4_5_in_the_new_themes(self):
        for theme in (palette.CYBER_PITCH, palette.DEEP_SLATE_GOLD, palette.HIGH_CONTRAST):
            for background, text in (theme.accent, theme.quiet, theme.switch, (theme.switch_selected, theme.switch[1])):
                self.assertGreaterEqual(palette.contrast_ratio(background, text), 4.5, (theme.name, background))

    def test_contrast_follows_wcag(self):
        self.assertAlmostEqual(palette.contrast_ratio("#000000", "#ffffff"), 21.0, places=2)
        self.assertAlmostEqual(palette.contrast_ratio("#777777", "#ffffff"), 4.48, places=2)
        self.assertEqual(palette.contrast_ratio("#123456", "#abcdef"), palette.contrast_ratio("#abcdef", "#123456"))


if __name__ == "__main__":
    unittest.main()
