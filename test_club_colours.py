# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for club_colours: the built-in club colours, how names are matched, and Mark's edits.

Run:  .venv\\Scripts\\python -m unittest -v
"""

import unittest

import club_colours


class ClubColourTests(unittest.TestCase):
    def test_names_match_after_folding_and_nothing_fuzzier(self):
        n = club_colours.normalise
        self.assertEqual(n("AFC Bournemouth"), n("Bournemouth"))
        self.assertEqual(n("Brighton & Hove Albion"), n("Brighton and Hove Albion"))
        self.assertEqual(n("Atlético Madrid"), n("atletico madrid"))
        self.assertEqual(n("Bayern München"), n("Bayern Munchen"))
        self.assertNotEqual(n("Hull City"), n("Hull"))
        self.assertNotEqual(n("Sheffield United"), n("Sheffield Wednesday"))

    def test_every_entry_is_two_colours(self):
        for name, colours in club_colours.CLUB_COLOURS.items():
            self.assertEqual(len(colours), 2, name)
            for colour in colours:
                self.assertRegex(colour, r"^#[0-9a-f]{6}$", name)

    def test_no_two_spellings_of_a_club_disagree(self):
        seen = {}
        for name, colours in club_colours.CLUB_COLOURS.items():
            key = club_colours.normalise(name)
            self.assertEqual(seen.setdefault(key, colours), colours, name)

    def test_known_and_unknown_clubs(self):
        self.assertEqual(club_colours.builtin_colours("Hull City"), ("#f5a12d", "#000000"))
        self.assertEqual(club_colours.builtin_colours("hull city"), ("#f5a12d", "#000000"))
        self.assertIsNone(club_colours.builtin_colours("Nowhere Rovers"))
        self.assertIsNone(club_colours.builtin_colours(None))

    def test_edits_win_and_malformed_edits_are_ignored(self):
        builtin = club_colours.builtin_colours("Hull City")
        self.assertEqual(club_colours.colours_for("Hull City", {"Hull City": ["#123456", "#abcdef"]}),
                         ("#123456", "#abcdef"))
        self.assertIsNone(club_colours.colours_for("Hull City", {"hull city": None}))
        for odd in ("red", ["#123456"], ["#12345", "#abcdef"], 7, [None, "#abcdef"]):
            self.assertEqual(club_colours.colours_for("Hull City", {"Hull City": odd}), builtin, odd)
        self.assertEqual(club_colours.colours_for("Hull City", "not a dict"), builtin)
        self.assertEqual(club_colours.colours_for("Leeds United", {"Hull City": None}),
                         club_colours.builtin_colours("Leeds United"))
        self.assertIsNone(club_colours.colours_for(None, {}))


if __name__ == "__main__":
    unittest.main()


class InitialsTests(unittest.TestCase):
    def test_two_words_give_their_first_letters(self):
        self.assertEqual(club_colours.initials("Northbridge Rovers"), "NR")

    def test_one_word_gives_its_first_two_letters(self):
        self.assertEqual(club_colours.initials("Ashcombe"), "AS")

    def test_club_words_team_numbers_and_accents_are_set_aside(self):
        self.assertEqual(club_colours.initials("FC Westford Town"), "WT")
        self.assertEqual(club_colours.initials("Westford Town (team 2)"), "WT")
        self.assertEqual(club_colours.initials("Atlético Eastholm"), "AE")
        self.assertEqual(club_colours.initials("Kingsbay City 1902"), "KC")

    def test_no_name_gives_no_initials(self):
        for name in (None, "", "   ", "FC", "(team 2)"):
            self.assertEqual(club_colours.initials(name), "", name)
