"""Tests for the cup bracket's layout (pure geometry, no window)."""

from __future__ import annotations

import unittest
from unittest import mock

import bracket
import fm_data as fd
from test_fm_data import CLUBS, D, fx


def cup_rounds(fixtures):
    return fd.cup_rounds(fixtures, fd.team_labels(fixtures))


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
