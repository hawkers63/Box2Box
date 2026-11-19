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

    def test_result_pill_text_reads_on_fill_in_every_theme(self):
        """W, D, L, ? pill text must meet WCAG AA (4.5:1) against their fill in every theme."""
        PILL_KEYS = ("W", "D", "L", "?")
        for theme in palette.THEMES:
            for key in PILL_KEYS:
                fill, text = theme.colours[key]
                if fill and text:
                    self.assertGreaterEqual(
                        palette.contrast_ratio(fill, text), 4.5,
                        f"{theme.name} key={key!r} fill={fill} text={text}"
                    )

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

    def test_the_warning_colour_reads_on_the_panel_in_every_theme(self):
        # The unverified-build notice sits on a chip of the panel colour, so it must read there.
        for theme in palette.THEMES:
            self.assertGreaterEqual(palette.contrast_ratio(theme.warning, theme.panel), 4.5, theme.name)

    def test_contrast_follows_wcag(self):
        self.assertAlmostEqual(palette.contrast_ratio("#000000", "#ffffff"), 21.0, places=2)
        self.assertAlmostEqual(palette.contrast_ratio("#777777", "#ffffff"), 4.48, places=2)
        self.assertEqual(palette.contrast_ratio("#123456", "#abcdef"), palette.contrast_ratio("#abcdef", "#123456"))


class TintTests(unittest.TestCase):
    RED = ("#ee2737", "#ffffff")

    def test_the_tint_changes_the_focus_and_nothing_that_carries_meaning(self):
        me = palette.MIDNIGHT_EMERALD
        themed = palette.with_club(me, palette.club_tint(me, self.RED))
        self.assertEqual((themed.colours, themed.zones, themed.heading), (me.colours, me.zones, me.heading))
        self.assertNotEqual(themed.focus, me.focus)
        self.assertGreaterEqual(palette.contrast_ratio(themed.focus[0], palette.LOSS_BG), 1.5)   # not a defeat

    def test_the_more_colourful_colour_is_shown(self):
        me = palette.MIDNIGHT_EMERALD
        self.assertEqual(palette.club_tint(me, ("#ffffff", "#1d428a")).shown, "#1d428a")
        self.assertEqual(palette.club_tint(me, ("#f5a12d", "#000000")).shown, "#f5a12d")

    def test_a_black_and_white_club_shows_the_colour_that_stands_out(self):
        # On a dark theme black would vanish into the table, so white is shown.
        self.assertEqual(palette.club_tint(palette.MIDNIGHT_EMERALD, ("#000000", "#ffffff")).shown, "#ffffff")
        self.assertEqual(palette.club_tint(palette.CYBER_PITCH, ("#241f20", "#ffffff")).shown, "#ffffff")

    def test_the_tint_stands_apart_from_what_surrounds_it(self):
        for theme in palette.THEMES[:3]:
            for colours in (("#001d5e", "#ffffff"), ("#000000", "#ffffff"), ("#132257", "#ffffff"), self.RED):
                t = palette.club_tint(theme, colours)
                for tinted, surface in ((t.focus[0], theme.table[0]), (t.band[0], theme.panel),
                                        (t.selected[0], theme.switch[0])):
                    self.assertGreaterEqual(palette.contrast_ratio(tinted, surface), 1.4, (theme.name, colours))

    def test_every_tinted_pair_reads_at_4_5(self):
        for theme in palette.THEMES[:3]:
            for colours in (self.RED, ("#f5a12d", "#000000"), ("#ffffff", "#1d428a"), ("#fde100", "#000000")):
                t = palette.club_tint(theme, colours)
                for background, text in (t.band, (t.band[0], t.band_muted),
                                         (t.selected[0], theme.switch[1]), t.focus, (theme.table[0], t.link)):
                    self.assertGreaterEqual(palette.contrast_ratio(background, text), 4.5, (theme.name, colours))

    def test_high_contrast_and_no_colours_give_no_tint(self):
        self.assertIsNone(palette.club_tint(palette.HIGH_CONTRAST, self.RED))
        self.assertIsNone(palette.club_tint(palette.MIDNIGHT_EMERALD, None))
        self.assertIs(palette.with_club(palette.MIDNIGHT_EMERALD, None), palette.MIDNIGHT_EMERALD)

    def test_ink_on_white_picks_the_pair_colour_that_reads_on_a_white_sheet(self):
        self.assertEqual(palette.ink_on_white(palette.FOCUS), "#1e40af")                  # today's blue, unchanged
        self.assertEqual(palette.ink_on_white(palette.HIGH_CONTRAST.focus), "#000000")    # white on black: its text
        self.assertEqual(palette.ink_on_white(("#ffffff", "#ffffff")), "#000000")         # neither reads: black
        me = palette.MIDNIGHT_EMERALD
        for colours in (self.RED, ("#ffffff", "#1d428a"), ("#f5a12d", "#000000"), ("#000000", "#ffffff")):
            tinted = palette.club_tint(me, colours)
            self.assertGreaterEqual(palette.contrast_ratio(palette.ink_on_white(tinted.focus), "#ffffff"), 4.5)

    def test_a_pill_bevel_is_a_lighter_top_edge_and_a_darker_bottom_edge_in_every_theme(self):
        for theme in palette.THEMES:
            for letter, (background, _text) in theme.colours.items():
                if background is None:
                    continue
                highlight, shadow = palette.pill_edges(background)
                self.assertGreater(palette.luminance(highlight), palette.luminance(background), (theme.name, letter))
                self.assertLess(palette.luminance(shadow), palette.luminance(background), (theme.name, letter))

    def test_a_pill_bevel_is_faint(self):
        highlight, shadow = palette.pill_edges("#2e7d32")
        self.assertLess(palette.contrast_ratio(highlight, "#2e7d32"), 2.0)
        self.assertLess(palette.contrast_ratio(shadow, "#2e7d32"), 2.0)

    def test_blend_and_readable_text(self):
        self.assertEqual(palette.blend("#000000", "#ffffff", 0), "#000000")
        self.assertEqual(palette.blend("#000000", "#ffffff", 1), "#ffffff")
        self.assertEqual(palette.blend("#000000", "#ff8000", 0.5), "#804000")
        self.assertEqual(palette.readable_text("#ffff00"), "#000000")
        self.assertEqual(palette.readable_text("#1b1b1b"), "#ffffff")


if __name__ == "__main__":
    unittest.main()


class RoundelTests(unittest.TestCase):
    """Procedural roundels: identity aids drawn from a club's two colours, never crests."""

    CLUB = ("#7a1f2b", "#f2c94c")          # made-up claret and gold

    def test_a_club_with_colours_gets_its_main_colour_inside_and_its_second_round_it(self):
        r = palette.roundel(palette.MIDNIGHT_EMERALD, self.CLUB, "NR")
        self.assertEqual((r.disc, r.ring, r.initials, r.known), ("#7a1f2b", "#f2c94c", "NR", True))

    def test_a_club_without_colours_gets_a_neutral_roundel_marked_as_unknown(self):
        for theme in palette.THEMES:
            r = palette.roundel(theme, None, "EA")
            self.assertFalse(r.known, theme.name)
            self.assertEqual(r.initials, "EA")
            for colour in (r.disc, r.ring):
                self.assertLess(palette._chroma(colour), 40, f"{theme.name}: a neutral roundel is grey, not a colour")

    def test_the_same_club_always_gets_the_same_roundel(self):
        for theme in palette.THEMES:
            self.assertEqual(palette.roundel(theme, self.CLUB, "NR"), palette.roundel(theme, self.CLUB, "NR"))
            self.assertEqual(palette.roundel(theme, None, "NR"), palette.roundel(theme, None, "NR"))

    def test_initials_read_at_4_5_to_1_on_the_disc_in_every_theme(self):
        for theme in palette.THEMES:
            for colours in (self.CLUB, ("#ffffff", "#ffffff"), ("#000000", "#000000"), ("#ffd700", "#0000ff"),
                            ("#777777", "#888888"), None):
                r = palette.roundel(theme, colours, "WT")
                self.assertGreaterEqual(palette.contrast_ratio(r.text, r.disc), palette.READABLE, (theme.name, colours))

    def test_the_rim_stands_apart_from_the_surface_it_sits_on(self):
        for theme in palette.THEMES:
            for surface in (theme.table[0], theme.window):
                for colours in (self.CLUB, ("#1b1b1b", "#1b1b1b"), ("#000000", "#000000"), None):
                    r = palette.roundel(theme, colours, "WT", surface=surface)
                    self.assertGreaterEqual(palette.contrast_ratio(r.rim, surface), palette.NON_TEXT,
                                            (theme.name, surface, colours))

    def test_a_ring_too_close_to_its_disc_is_moved_apart_so_both_colours_show(self):
        r = palette.roundel(palette.MIDNIGHT_EMERALD, ("#ffffff", "#fefefe"), "WT")
        self.assertGreaterEqual(palette.contrast_ratio(r.ring, r.disc), palette.DISTINCT)

    def test_high_contrast_keeps_the_club_colours_but_rims_them_in_its_own_text_colour(self):
        r = palette.roundel(palette.HIGH_CONTRAST, self.CLUB, "NR")
        self.assertEqual((r.disc, r.ring, r.rim), ("#7a1f2b", "#f2c94c", palette.HIGH_CONTRAST.table[1]))

    def test_a_roundel_never_changes_result_or_zone_colours(self):
        before = {t.name: (dict(t.colours), dict(t.zones)) for t in palette.THEMES}
        for theme in palette.THEMES:
            palette.roundel(theme, self.CLUB, "NR")
        self.assertEqual(before, {t.name: (dict(t.colours), dict(t.zones)) for t in palette.THEMES})
