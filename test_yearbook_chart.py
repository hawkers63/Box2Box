# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for yearbook_chart: the trajectory chart's geometry, shared by the reader's canvas and the PDF.

Run:  .venv\\Scripts\\python -m unittest test_yearbook_chart -v
"""

import datetime as dt
import unittest

import yearbook as yb
import yearbook_chart as yc

D = dt.date


def point(week, day, place, *results):
    return yb.TrajectoryPoint(week, D(2026, 8, day), place, tuple(results))


CHART = yb.Trajectory("Premier League", 20, (point(1, 8, 5), point(2, 15, None), point(3, 22, 1), point(5, 29, 20)),
                      (("promotion", 1, 2), ("relegation", 18, 20)))


class LayoutTests(unittest.TestCase):
    def layout(self, chart=CHART):
        return yc.layout(chart, 600, 300)

    def test_first_place_is_the_top_and_last_the_bottom_of_the_plot(self):
        lay = self.layout()
        ys = {p.matchweek: y for p, _, y in lay.points}
        self.assertEqual(ys[3], lay.top)
        self.assertEqual(ys[5], lay.bottom)
        self.assertTrue(lay.top < ys[1] < lay.bottom)

    def test_x_follows_the_date_not_the_matchweek_number(self):
        xs = {p.matchweek: x for p, x, _ in self.layout().points}
        self.assertAlmostEqual((xs[3] - xs[1]) / (xs[5] - xs[3]), 14 / 7)     # 8 -> 22 Aug against 22 -> 29 Aug
        self.assertEqual(min(xs.values()), self.layout().left)
        self.assertEqual(max(xs.values()), self.layout().right)

    def test_a_blank_place_is_a_gap_with_no_point_and_the_lines_do_not_join_over_it(self):
        lay = self.layout()
        self.assertEqual([p.matchweek for p, _, _ in lay.points], [1, 3, 5])
        self.assertEqual(len(lay.segments), 3)                                    # each point alone: 2 and 4 are missing
        self.assertEqual(lay.gap_xs, (lay.left + (lay.right - lay.left) * 7 / 21,))

    def test_zone_bands_are_estimated_and_cover_their_places(self):
        lay = self.layout()
        names = [(z.zone, z.label) for z in lay.zones]
        self.assertEqual(names, [("promotion", "Promotion (estimated)"), ("relegation", "Relegation (estimated)")])
        top = lay.zones[0]
        self.assertEqual(top.top, lay.top)                                       # first place's band starts at the top edge
        self.assertLess(top.top, top.bottom)

    def test_one_day_only_puts_the_points_in_the_middle_not_a_divide_by_zero(self):
        chart = yb.Trajectory("L", 4, (point(1, 8, 2), point(2, 8, 3)))
        lay = yc.layout(chart, 400, 200)
        self.assertEqual({round(x) for _, x, _ in lay.points}, {round((lay.left + lay.right) / 2)})

    def test_hover_finds_the_nearest_point_within_reach_and_nothing_far_away(self):
        lay = self.layout()
        p, x, y = lay.points[1]
        self.assertIs(lay.nearest(x + 3, y - 2), p)
        self.assertIsNone(lay.nearest(x + 200, y))


class TextTests(unittest.TestCase):
    def test_hover_text_lists_the_results_and_claims_no_cause(self):
        m = yb.BookMatch("Sat 8", "Hull City", "Leeds United", "2-0")
        text = yc.point_text(point(1, 8, 5, m))
        self.assertEqual(text, "Matchweek 1, to Sat 8 Aug: 5th. Results that matchweek: Hull City 2-0 Leeds United.")
        for word in ("because", "caused", "after beating", "thanks"):
            self.assertNotIn(word, text)

    def test_a_blank_place_says_the_club_had_not_played(self):
        self.assertEqual(yc.point_text(point(2, 15, None)), "Matchweek 2, to Sat 15 Aug: no place, the club had not yet played.")

    def test_a_matchweek_with_no_result_for_the_club_says_so_without_inventing_one(self):
        self.assertEqual(yc.point_text(point(4, 22, 3)), "Matchweek 4, to Sat 22 Aug: 3rd. No result for the club is printed on that matchweek's page.")
