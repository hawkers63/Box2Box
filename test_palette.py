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

    def test_contrast_follows_wcag(self):
        self.assertAlmostEqual(palette.contrast_ratio("#000000", "#ffffff"), 21.0, places=2)
        self.assertAlmostEqual(palette.contrast_ratio("#777777", "#ffffff"), 4.48, places=2)
        self.assertEqual(palette.contrast_ratio("#123456", "#abcdef"), palette.contrast_ratio("#abcdef", "#123456"))


if __name__ == "__main__":
    unittest.main()
