"""Tests for the command palette's matching and ranking (no window)."""

from __future__ import annotations

import unittest

import command_palette as cp


def item(kind, title, *, priority=0, detail=""):
    return cp.PaletteItem(kind, title, detail=detail, priority=priority)


def titles(found):
    return [i.title for i in found]


class FoldTests(unittest.TestCase):
    def test_case_accents_and_punctuation_fold_away(self):
        self.assertEqual(cp.fold("  Córdoba C.F. "), "cordoba c f")

    def test_words_that_club_names_drop_are_kept(self):
        self.assertEqual(cp.fold("Sheffield United"), "sheffield united")


class SearchTests(unittest.TestCase):
    ITEMS = [
        item(cp.CLUB, "Sheffield United", detail="Championship"),
        item(cp.CLUB, "Sheffield Wednesday", detail="Championship"),
        item(cp.CLUB, "Córdoba", detail="Segunda"),
        item(cp.COMPETITION, "Championship"),
        item(cp.VIEW, "Table"),
        item(cp.SPLIT, "Home"),
        item(cp.ACTION, "Export as Excel"),
        item(cp.CLUB, "Hull City"),
    ]

    def test_an_empty_query_offers_views_splits_and_actions_only(self):
        for query in ("", "   ", " -- "):
            self.assertEqual(titles(cp.search(self.ITEMS, query)), ["Table", "Home", "Export as Excel"], query)

    def test_a_word_start_matches(self):
        self.assertEqual(titles(cp.search(self.ITEMS, "sheff")), ["Sheffield United", "Sheffield Wednesday"])

    def test_every_query_word_must_match(self):
        self.assertEqual(titles(cp.search(self.ITEMS, "sheff wed")), ["Sheffield Wednesday"])

    def test_utd_finds_united_by_its_letters(self):
        self.assertEqual(titles(cp.search(self.ITEMS, "utd")), ["Sheffield United"])
        self.assertEqual(titles(cp.search(self.ITEMS, "shef utd")), ["Sheffield United"])

    def test_a_substring_matches_but_ranks_below_a_word_start(self):
        items = [item(cp.CLUB, "Hatfield Town"), item(cp.CLUB, "Fieldhouse")]
        self.assertEqual(titles(cp.search(items, "field")), ["Fieldhouse", "Hatfield Town"])

    def test_accents_and_case_fold(self):
        self.assertEqual(titles(cp.search(self.ITEMS, "CORDOBA")), ["Córdoba"])
        self.assertEqual(titles(cp.search([item(cp.CLUB, "Cordoba")], "córdoba")), ["Cordoba"])

    def test_the_exact_title_comes_first(self):
        items = [item(cp.CLUB, "Hull City Women"), item(cp.CLUB, "Hull City")]
        self.assertEqual(titles(cp.search(items, "hull city")), ["Hull City", "Hull City Women"])

    def test_higher_priority_wins_within_a_tier_then_kind_then_title(self):
        items = [item(cp.COMPETITION, "Table cup"), item(cp.CLUB, "Table Town"), item(cp.VIEW, "Table"),
                 item(cp.CLUB, "Table Rovers", priority=1)]
        self.assertEqual(titles(cp.search(items, "tab")),
                         ["Table Rovers", "Table", "Table Town", "Table cup"])

    def test_the_result_is_capped(self):
        many = [item(cp.CLUB, f"Town {n:02}") for n in range(30)]
        self.assertEqual(len(cp.search(many, "town")), cp.RESULT_LIMIT)
        self.assertEqual(len(cp.search(many, "town", limit=5)), 5)

    def test_nothing_matching_gives_nothing(self):
        self.assertEqual(cp.search(self.ITEMS, "zzz"), [])


if __name__ == "__main__":
    unittest.main()
