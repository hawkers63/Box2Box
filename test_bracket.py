"""Tests for the cup bracket's layout (pure geometry, no window)."""

from __future__ import annotations

import unittest
from unittest import mock

import bracket
import fm_data as fd
import palette
from test_fm_data import CLUBS, D, fx, team as fd_team


def palette_focus():
    return palette.MIDNIGHT_EMERALD.focus[0]


def cup_rounds(fixtures):
    return fd.cup_rounds(fixtures, fd.team_labels(fixtures))


def matches(md, n, rnd=None):                                  # n different pairs in round md
    return [fx(D(2026, 9, 1 + md), 2 * i + 1, 2 * i + 2, 1, 0, comp=151, md=md, rnd=rnd) for i in range(n)]


class LayoutTests(unittest.TestCase):
    BOX, GAP, HEAD = (200, 48), (28, 12), 24

    @staticmethod
    def eight_team_cup():
        return [fx(D(2026, 9, 1), 1, 2, 1, 0, comp=151, md=1), fx(D(2026, 9, 1), 3, 4, 0, 1, comp=151, md=1),
                fx(D(2026, 9, 1), 5, 6, 2, 0, comp=151, md=1), fx(D(2026, 9, 1), 7, 8, 0, 3, comp=151, md=1),
                fx(D(2026, 10, 1), 1, 4, 1, 0, comp=151, md=2), fx(D(2026, 10, 1), 5, 8, 0, 1, comp=151, md=2),
                fx(D(2026, 11, 1), 1, 8, 2, 1, comp=151, md=3)]

    def layout(self, build):
        with mock.patch.dict(CLUBS, {n: (f"Club {n}", f"C{n}") for n in range(6, 9)}):
            _, tree = fd.bracket_split(cup_rounds(build()))
        return bracket.layout_tree(tree, box=self.BOX, gap=self.GAP, heading=self.HEAD)

    def test_each_tie_sits_between_the_two_ties_that_fed_it(self):
        layout = self.layout(self.eight_team_cup)
        columns = {}
        for box in layout.boxes:
            columns.setdefault(box.column, []).append(box)
        self.assertEqual({c: len(b) for c, b in columns.items()}, {0: 4, 1: 2, 2: 1})
        self.assertEqual([b.y for b in columns[0]], [24, 84, 144, 204])          # stacked below the headings
        self.assertEqual([b.y for b in columns[1]], [54, 174])                   # centred between their feeders
        self.assertEqual([b.y for b in columns[2]], [114])
        self.assertEqual([b.x for b in (columns[0][0], columns[1][0], columns[2][0])], [0, 228, 456])

    def test_the_feeders_stay_neighbours_however_the_save_orders_the_first_round(self):
        def shuffled():
            cup = self.eight_team_cup()
            first = [f for f in cup if f.round_index == 0]
            rest = [f for f in cup if f.round_index != 0]
            return [first[2], first[0], first[3], first[1]] + rest        # ties 5v6, 1v2, 7v8, 3v4 in the save's order
        layout = self.layout(shuffled)
        order = [(b.tie.team_a // 100, b.tie.team_b // 100) for b in layout.boxes if b.column == 0]
        # Clubs 1v2 and 3v4 fed the semi-final 1v4, and 5v6 and 7v8 the other: each pair of feeders is adjacent.
        self.assertEqual([set(order[:2]), set(order[2:])], [{(1, 2), (3, 4)}, {(5, 6), (7, 8)}])
        self.assertEqual([b.y for b in layout.boxes if b.column == 2], [114])

    def test_each_tie_but_the_final_has_an_elbow_link_to_the_tie_it_fed(self):
        layout = self.layout(self.eight_team_cup)
        self.assertEqual(len(layout.links), 6)                                  # four first-round ties and two semi-finals
        # The first first-round box (y 24, centre 48) feeds the first semi-final (y 54, centre 78): out of its right
        # edge (x 200), halfway across the gap (x 214), up or down to the centre, then into the left edge (x 228).
        self.assertIn(((200, 48), (214, 48), (214, 78), (228, 78)), layout.links)


class TieTextTests(unittest.TestCase):
    def tie(self, fixtures, index=0):
        rounds = cup_rounds(fixtures)
        return rounds[index].ties[0], fd.team_labels(fixtures)

    def test_a_single_match_shows_each_sides_goals_and_the_winner(self):
        tie, labels = self.tie([fx(D(2026, 9, 1), 1, 2, 2, 0, comp=151, md=1), fx(D(2026, 10, 1), 1, 3, 1, 0, comp=151, md=2)])
        text = bracket.describe_tie(tie, labels)
        self.assertEqual((text.a_name, text.a_goals, text.b_name, text.b_goals, text.winner),
                         ("Hull City", "2", "Leeds United", "0", "a"))

    def test_two_legs_show_each_sides_goals_in_each_leg_whoever_was_at_home(self):
        legs = [fx(D(2026, 9, 1), 1, 2, 3, 0, comp=151, md=1), fx(D(2026, 9, 8), 2, 1, 1, 0, comp=151, md=1),
                fx(D(2026, 10, 1), 1, 3, 1, 0, comp=151, md=2)]
        tie, labels = self.tie(legs)
        text = bracket.describe_tie(tie, labels)
        self.assertEqual((text.a_goals, text.b_goals, text.winner), ("3 · 0", "0 · 1", "a"))

    def test_a_winner_found_only_in_the_next_round_is_marked_as_inferred(self):
        drawn = [fx(D(2026, 9, 1), 1, 2, 1, 1, comp=151, md=1), fx(D(2026, 10, 1), 2, 3, 1, 0, comp=151, md=2)]
        tie, labels = self.tie(drawn)
        text = bracket.describe_tie(tie, labels)
        self.assertEqual((text.winner, text.inferred), ("b", True))
        decided = [fx(D(2026, 9, 1), 1, 2, 2, 1, comp=151, md=1), fx(D(2026, 10, 1), 1, 3, 1, 0, comp=151, md=2)]
        self.assertFalse(bracket.describe_tie(*self.tie(decided)).inferred)

    def test_an_unplayed_or_unscored_meeting_shows_nothing_or_n_a_and_no_winner(self):
        unplayed = bracket.describe_tie(*self.tie([fx(D(2026, 9, 1), 1, 2, comp=151, md=1)]))
        unscored = bracket.describe_tie(*self.tie([fx(D(2026, 9, 1), 1, 2, None, None, played=True, comp=151, md=1)]))
        self.assertEqual((unplayed.a_goals, unplayed.winner), ("", None))
        self.assertEqual((unscored.a_goals, unscored.winner), ("n/a", None))


class BracketViewTests(unittest.TestCase):
    """The canvas that draws the tree and lists the earlier rounds."""

    def setUp(self):
        import customtkinter as ctk
        import palette
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.geometry("1000x600+-4000+0")
        self.view = bracket.BracketView(self.root, px=lambda v: int(v), font=("Segoe UI", 10),
                                        theme=palette.MIDNIGHT_EMERALD)
        self.view.pack(fill="both", expand=True)
        self.root.update()

    def tearDown(self):
        import time
        stop = time.monotonic() + 0.3
        while time.monotonic() < stop:
            self.root.update()
            time.sleep(0.02)
        self.root.destroy()

    def show(self, build, focus=None):
        with mock.patch.dict(CLUBS, {n: (f"Club {n}", f"C{n}") for n in range(6, 17)}):
            fixtures = build()
            self.view.show(cup_rounds(fixtures), fd.team_labels(fixtures), focus)
        self.root.update()

    def test_the_tree_draws_every_tie_with_its_goals_and_the_round_headings(self):
        self.show(LayoutTests.eight_team_cup)
        text = self.view.rendered_text()
        for heading in ("Last 8", "Last 4", "Round 3"):                 # unnamed rounds, named from their size
            self.assertIn(heading, text)
        self.assertIn("Hull City", text)
        self.assertEqual(text.count("Hull City"), 3)                    # in the first round, the semi-final and the final

    def test_each_tie_but_the_final_is_linked_to_the_tie_it_fed(self):
        self.show(LayoutTests.eight_team_cup)
        self.assertEqual(len(self.view._canvas.find_withtag("link")), 6)

    def drawn_first_round(self):
        # Hull and Leeds draw; Leeds are the side in the next round, so they went through.
        return [fx(D(2026, 9, 1), 1, 2, 1, 1, comp=151, md=1), fx(D(2026, 9, 1), 3, 4, 2, 0, comp=151, md=1),
                fx(D(2026, 10, 1), 2, 3, 1, 0, comp=151, md=2)]

    def test_a_winner_known_only_from_the_next_round_is_starred_and_the_star_is_explained(self):
        self.show(self.drawn_first_round)
        text = self.view.rendered_text()
        self.assertIn("Leeds United *", text)
        self.assertNotIn("Hull City *", text)
        self.assertTrue(any(t.startswith("* ") and "extra time or penalties" in t for t in text))

    def test_a_cup_with_no_inferred_winner_has_no_legend(self):
        self.show(LayoutTests.eight_team_cup)
        self.assertFalse(any("extra time or penalties" in t for t in self.view.rendered_text()))

    def test_the_rounds_before_the_tree_are_listed_below_it(self):
        self.show(lambda: matches(1, 5) + matches(2, 4) + matches(3, 2) + matches(4, 1))     # 5 does not halve into 4
        text = self.view.rendered_text()
        self.assertIn("Earlier rounds", text)
        listed = next(i for i, t in enumerate(text) if "Club 10" in t)              # the first round's teams are listed
        self.assertLess(text.index("Earlier rounds"), listed)
        self.assertEqual(text.count("Round 1"), 1)

    def test_a_competition_that_does_not_end_in_a_single_final_says_so_and_lists_every_round(self):
        self.show(lambda: matches(1, 4) + matches(2, 3))                  # ends in three ties: no one final
        text = self.view.rendered_text()
        self.assertEqual(text[0], bracket.NO_TREE_NOTE)
        self.assertIn("Rounds", text)
        self.assertNotIn("Earlier rounds", text)
        self.assertEqual([t for t in text if t.startswith("Round ") or t.startswith("Last ")], ["Last 8", "Round 2"])

    def test_a_group_phase_is_counted_not_drawn_as_ties(self):
        def group_then_final():
            group = [fx(D(2026, 9, 1), 1, 2, 1, 0, comp=664, md=1), fx(D(2026, 9, 8), 1, 3, 0, 0, comp=664, md=1),
                     fx(D(2026, 9, 15), 1, 4, 2, 1, comp=664, md=1), fx(D(2026, 9, 1), 3, 4, 1, 1, comp=664, md=1)]
            return group + [fx(D(2026, 10, 1), 1, 3, 1, 0, comp=664, md=2)]
        self.show(group_then_final)
        text = self.view.rendered_text()
        self.assertIn("Group or league phase: 4 matches (listed in Results, not drawn as ties)", text)

    def outlined_in_focus(self):
        canvas, focus = self.view._canvas, palette_focus()
        return [i for i in canvas.find_all() if canvas.type(i) == "rectangle" and canvas.itemcget(i, "outline") == focus]

    def test_the_followed_clubs_boxes_are_outlined_in_the_focus_colour(self):
        self.show(LayoutTests.eight_team_cup, focus=fd_team(1))
        self.assertEqual(len(self.outlined_in_focus()), 3)                # its first-round tie, the semi-final, the final
        self.show(LayoutTests.eight_team_cup, focus=None)
        self.assertEqual(len(self.outlined_in_focus()), 0)

    def test_a_long_bracket_scrolls_with_the_wheel_and_a_new_one_starts_at_the_top(self):
        self.root.geometry("1000x300+-4000+0")
        self.show(lambda: matches(1, 5) + matches(2, 4) + matches(3, 2) + matches(4, 1))
        canvas = self.view._canvas
        self.assertEqual(canvas.yview()[0], 0.0)
        canvas.event_generate("<MouseWheel>", delta=-120, x=10, y=10)
        self.root.update()
        self.assertGreater(canvas.yview()[0], 0.0)
        self.show(lambda: matches(1, 7) + matches(2, 4) + matches(3, 2) + matches(4, 1))     # a different cup
        self.assertEqual(canvas.yview()[0], 0.0)

    def test_a_short_bracket_does_not_scroll(self):                      # a guard
        self.root.geometry("1000x900+-4000+0")
        self.show(LayoutTests.eight_team_cup)
        self.view._canvas.event_generate("<MouseWheel>", delta=-120, x=10, y=10)
        self.root.update()
        self.assertEqual(self.view._canvas.yview()[0], 0.0)

    def test_redrawing_the_same_cup_keeps_the_scroll_position(self):
        self.root.geometry("1000x300+-4000+0")
        build = lambda: matches(1, 5) + matches(2, 4) + matches(3, 2) + matches(4, 1)      # noqa: E731
        self.show(build)
        self.view._canvas.yview_moveto(0.5)
        where = self.view._canvas.yview()[0]
        self.show(build, focus=fd_team(1))                       # the same cup, a different club followed
        self.assertAlmostEqual(self.view._canvas.yview()[0], where, places=3)

    def test_a_new_theme_recolours_the_bracket_and_keeps_what_it_shows(self):
        self.show(LayoutTests.eight_team_cup)
        before = self.view.rendered_text()
        theme = palette.theme_by_name("Cyber Pitch")
        self.view.restyle(theme)
        self.assertEqual(self.view.rendered_text(), before)
        self.assertEqual(str(self.view._canvas.cget("bg")), theme.table[0])
