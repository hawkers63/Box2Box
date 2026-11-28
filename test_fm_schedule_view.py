# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for fm_schedule_view: the pure filter logic (ScheduleFilter, apply_filter) and the view itself, with
made-up clubs and dates.

Run:  .venv\\Scripts\\python -m unittest test_fm_schedule_view -v
"""

import datetime as dt
import re
import unittest
from dataclasses import replace
from unittest import mock
from unittest.mock import MagicMock

import customtkinter as ctk

import fm_data as fd
import palette
from fm_schedule_view import ScheduleFilter, ScheduleView, apply_filter, elide, schedule_line
from test_fm_data import CLUBS, D, club, fx
from test_fm_identity import CUP_ROUND, INVENTED, NORTHBRIDGE, gap_season, invented_fx
from test_fm_identity import dataset as identity_dataset


def _fixture(date=None, competition_id=1, home_id=100, away_id=200):
    f = MagicMock()
    f.date = date
    f.competition_id = competition_id
    f.home_club_id = home_id
    f.away_club_id = away_id
    return f


def _item(*, competition_id=1, venue="H", opponent="Chelsea", outcome="W",
          played=True, date=None, when=fd.WHEN_PLAYED, days=None):
    item = MagicMock(spec=fd.ScheduleItem)
    item.competition_id = competition_id
    item.venue = venue
    item.opponent = opponent
    item.outcome = outcome if played else None
    item.played = played
    item.score = "2-1" if played else ""
    item.when = when
    item.days = days
    # fixture with date for month filtering
    f = MagicMock()
    f.date = date
    item.fixture = f
    return item


class ScheduleFilterTests(unittest.TestCase):
    def test_empty_filter_is_not_active(self):
        self.assertFalse(ScheduleFilter().active)

    def test_competition_id_makes_filter_active(self):
        self.assertTrue(ScheduleFilter(competition_id=5).active)

    def test_venue_makes_filter_active(self):
        self.assertTrue(ScheduleFilter(venue="H").active)

    def test_month_makes_filter_active(self):
        self.assertTrue(ScheduleFilter(month=8).active)

    def test_result_makes_filter_active(self):
        self.assertTrue(ScheduleFilter(result="W").active)

    def test_search_makes_filter_active(self):
        self.assertTrue(ScheduleFilter(search="city").active)

    def test_describe_empty_gives_empty_string(self):
        self.assertEqual(ScheduleFilter().describe(), "")

    def test_describe_includes_venue_name(self):
        self.assertIn("home", ScheduleFilter(venue="H").describe())
        self.assertIn("away", ScheduleFilter(venue="A").describe())
        self.assertIn("neutral", ScheduleFilter(venue="N").describe())

    def test_describe_includes_month_name(self):
        self.assertIn("August", ScheduleFilter(month=8).describe())

    def test_describe_includes_result_word(self):
        self.assertIn("wins", ScheduleFilter(result="W").describe())
        self.assertIn("draws", ScheduleFilter(result="D").describe())

    def test_describe_includes_search_quoted(self):
        d = ScheduleFilter(search="city").describe()
        self.assertIn("city", d)

    def test_describe_combines_active_parts(self):
        d = ScheduleFilter(venue="H", result="W").describe()
        self.assertIn("home", d)
        self.assertIn("wins", d)

    def test_describe_names_the_competition_when_it_is_known(self):
        self.assertEqual(ScheduleFilter(competition_id=102).describe({102: "Invented Cup"}), "Invented Cup")
        self.assertEqual(ScheduleFilter(competition_id=102).describe(), "Competition 102")

    def test_filter_is_frozen(self):
        f = ScheduleFilter()
        with self.assertRaises((AttributeError, TypeError)):
            f.venue = "H"


class ApplyFilterTests(unittest.TestCase):
    def setUp(self):
        self.items = (
            _item(competition_id=1, venue="H", opponent="Chelsea",   outcome="W", played=True,  date=dt.date(2027, 8, 10)),
            _item(competition_id=1, venue="A", opponent="Arsenal",   outcome="L", played=True,  date=dt.date(2027, 9, 5)),
            _item(competition_id=2, venue="H", opponent="Spurs",     outcome="D", played=True,  date=dt.date(2027, 8, 20)),
            _item(competition_id=1, venue="H", opponent="City",      outcome=None,played=False, date=dt.date(2027, 10, 1), when=fd.WHEN_UPCOMING),
        )

    def test_no_filter_returns_all(self):
        self.assertEqual(apply_filter(self.items, ScheduleFilter()), self.items)

    def test_competition_filter_keeps_matching(self):
        result = apply_filter(self.items, ScheduleFilter(competition_id=2))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].opponent, "Spurs")

    def test_venue_filter_home(self):
        result = apply_filter(self.items, ScheduleFilter(venue="H"))
        self.assertTrue(all(i.venue == "H" for i in result))
        self.assertEqual(len(result), 3)

    def test_venue_filter_away(self):
        result = apply_filter(self.items, ScheduleFilter(venue="A"))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].opponent, "Arsenal")

    def test_month_filter_august(self):
        result = apply_filter(self.items, ScheduleFilter(month=8))
        self.assertEqual(len(result), 2)
        self.assertTrue(all(i.fixture.date.month == 8 for i in result))

    def test_month_filter_excludes_undated(self):
        items = self.items + (_item(date=None, played=False, when=fd.WHEN_UNDATED),)
        result = apply_filter(items, ScheduleFilter(month=8))
        # undated item excluded
        self.assertTrue(all(i.fixture.date is not None for i in result))

    def test_result_filter_wins(self):
        result = apply_filter(self.items, ScheduleFilter(result="W"))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].opponent, "Chelsea")

    def test_result_filter_excludes_unplayed(self):
        result = apply_filter(self.items, ScheduleFilter(result="W"))
        self.assertTrue(all(i.played for i in result))

    def test_search_case_insensitive(self):
        result = apply_filter(self.items, ScheduleFilter(search="CHELSEA"))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].opponent, "Chelsea")

    def test_search_partial_match(self):
        result = apply_filter(self.items, ScheduleFilter(search="en"))
        # Arsenal and Chelsea both contain "en"
        self.assertGreaterEqual(len(result), 1)
        self.assertTrue(all("en" in i.opponent.lower() for i in result))

    def test_search_no_match_returns_empty(self):
        result = apply_filter(self.items, ScheduleFilter(search="xxxxxxx"))
        self.assertEqual(result, ())

    def test_filters_combine_as_and(self):
        result = apply_filter(self.items, ScheduleFilter(competition_id=1, venue="H"))
        # comp=1 AND home: Chelsea (W) and City (upcoming)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(i.competition_id == 1 and i.venue == "H" for i in result))

    def test_result_tuple(self):
        result = apply_filter(self.items, ScheduleFilter())
        self.assertIsInstance(result, tuple)


class TextHelperTests(unittest.TestCase):
    def test_elide_keeps_what_fits_and_ends_what_does_not_with_an_ellipsis(self):
        self.assertEqual(elide("Westford Town", 20, len), "Westford Town")
        self.assertEqual(elide("Westford Town", 9, len), "Westford…")
        self.assertEqual(elide("Westford Town", 0, len), "")

    def test_a_schedule_line_says_when_where_whom_and_how_it_ended(self):
        played = _item(opponent="Westford Town", venue="A", outcome="D", date=dt.date(2099, 8, 15), competition_id=101)
        played.score = "0-0"
        self.assertEqual(schedule_line(played, {101: "Invented League"}),
                         "15 Aug 2099 · Invented League · Westford Town (away) · 0-0 D")
        to_come = _item(opponent="Southmere United", played=False, date=dt.date(2099, 9, 4), when=fd.WHEN_UPCOMING,
                        days=3, competition_id=102)
        self.assertEqual(schedule_line(to_come), "4 Sep 2099 · Competition 102 · Southmere United (home) · In 3 days")


class ScheduleGapViewTests(unittest.TestCase):
    """The Fixture gap option: off by default, drawn from the whole season whatever the filter hides."""

    def setUp(self):
        self.root = ctk.CTk()
        self.root.geometry("1410x600+-4000+0")
        self.changes = []
        self.view = ScheduleView(self.root, on_gaps_changed=self.changes.append)
        self.view.pack(fill="both", expand=True)
        self.schedule = fd.club_schedule(gap_season(), NORTHBRIDGE)
        self.view.install_schedule(self.schedule, palette.MIDNIGHT_EMERALD)
        self.root.update()
        self.addCleanup(self.root.destroy)

    def texts(self, row):
        canvas = self.view._canvas
        return [canvas.itemcget(i, "text") for i in canvas.find_withtag(f"row_{row}") if canvas.type(i) == "text"]

    def test_no_gap_is_shown_until_the_option_is_turned_on(self):
        self.assertFalse(any("since" in t for row in range(3) for t in self.texts(row)))

    def test_turning_it_on_shows_the_gap_on_each_row_and_tells_the_window(self):
        self.view.set_show_gaps(True)
        self.root.update()
        self.assertIn("2 days since cup fixture", self.texts(2))
        self.assertEqual(self.changes, [True])

    def test_a_league_only_filter_still_counts_the_midweek_cup_tie(self):
        self.view.set_show_gaps(True)
        self.view.apply_competition_filter(101)
        self.root.update()
        self.assertEqual(len(self.view._filtered), 2)
        self.assertIn("2 days since cup fixture", self.texts(1))

    def test_the_opponent_the_gap_and_the_score_do_not_overlap_at_the_minimum_width(self):
        self.view.set_show_gaps(True)
        self.root.update()
        canvas = self.view._canvas
        boxes = {canvas.itemcget(i, "text"): canvas.bbox(i) for i in canvas.find_withtag("row_2")
                 if canvas.type(i) == "text"}
        opponent, gap, score = boxes["A  Westford Town"], boxes["2 days since cup fixture"], boxes["0-0"]
        self.assertLess(opponent[2], gap[0])
        self.assertLess(gap[2], score[0])


# --------------------------------------------------------------------------- 2.16: the view itself

NAMES = {101: "Invented League", 102: "Invented Cup"}
LONG = "Westford Town Wanderers Athletic and Recreation Football Club"


def month_season():
    """gap_season and a September defeat away at Kingsbay City, all played by the save's date."""
    return gap_season(extra=[invented_fx(D(2099, 9, 5), 5, 1, 2, 1, md=3)], game_date=D(2099, 9, 10))


def long_name_season():
    """A long-named opponent met two days after a played cup tie, then two days after one still to come."""
    with mock.patch.dict(CLUBS, {**INVENTED, 3: (LONG, "Westford")}):
        return identity_dataset([
            fx(D(2099, 8, 1), 1, 2, 1, 0, md=1),
            fx(D(2099, 8, 6), 1, 4, 2, 1, comp=102, rnd=CUP_ROUND),
            fx(D(2099, 8, 8), 3, 1, 0, 0, md=2),
            fx(D(2099, 8, 13), 1, 4, comp=102, rnd=CUP_ROUND),
            fx(D(2099, 8, 15), 3, 1, md=3),
        ], game_date=D(2099, 8, 10), clubs=[club(n) for n in range(1, 6)])


def long_season(n=200):
    """n matches for club 1, one a day, none played yet."""
    with mock.patch.dict(CLUBS, INVENTED):
        return identity_dataset([fx(D(2099, 8, 1) + dt.timedelta(days=i), 1, 2 + i % 4, md=i + 1) for i in range(n)],
                                game_date=D(2099, 7, 1), clubs=[club(n) for n in range(1, 6)])


class ViewCase(unittest.TestCase):
    """A ScheduleView in an off-screen window, reporting what it selects and inspects."""

    def setUp(self):
        self.root = ctk.CTk()
        self.root.geometry("1410x600+-4000+0")
        self.selected, self.inspected = [], []
        self.view = ScheduleView(self.root, on_select=self.selected.append, on_inspect=self.inspected.append)
        self.view.pack(fill="both", expand=True)
        self.addCleanup(self.root.destroy)

    def install(self, ds, theme=palette.MIDNIGHT_EMERALD):
        schedule = fd.club_schedule(ds, NORTHBRIDGE)
        self.view.install_schedule(schedule, theme, competition_names=NAMES)
        self.root.update()
        return schedule

    def tagged(self, tag):
        (item,) = self.view._canvas.find_withtag(tag)
        return item

    def texts(self, row):
        canvas = self.view._canvas
        return [canvas.itemcget(i, "text") for i in canvas.find_withtag(f"row_{row}") if canvas.type(i) == "text"]

    def drawn_rows(self):
        canvas = self.view._canvas
        return {int(t[4:]) for i in canvas.find_all() for t in canvas.gettags(i) if re.fullmatch(r"row_\d+", t)}

    def key(self, sequence):
        self.view._canvas.event_generate(sequence)
        self.root.update()


class ScheduleContrastTests(ViewCase):
    def test_the_canvas_takes_the_table_colour_in_every_theme(self):
        self.install(gap_season())
        for theme in palette.THEMES:
            self.view.set_theme(theme)
            self.assertEqual(self.view._canvas.cget("bg"), theme.table[0], theme.name)

    def test_each_outcome_letter_sits_on_its_own_readable_pill_in_high_contrast(self):
        hc = palette.HIGH_CONTRAST
        schedule = self.install(month_season(), hc)
        canvas = self.view._canvas
        for i, item in enumerate(schedule.items):
            pill, letter = self.tagged(f"outcome_{i}"), self.tagged(f"letter_{i}")
            fill, ink = canvas.itemcget(pill, "fill"), canvas.itemcget(letter, "fill")
            self.assertEqual((canvas.itemcget(letter, "text"), fill), (item.outcome, hc.colours[item.outcome][0]))
            self.assertGreaterEqual(palette.contrast_ratio(fill, ink), palette.READABLE, i)
            px0, py0, px1, py1 = canvas.bbox(pill)
            lx0, ly0, lx1, ly1 = canvas.bbox(letter)
            self.assertTrue(px0 <= lx0 and lx1 <= px1 and py0 < (ly0 + ly1) / 2 < py1, (i, (px0, py0, px1, py1)))

    def test_each_pill_has_a_light_top_rim_and_a_dark_bottom_rim(self):
        hc = palette.HIGH_CONTRAST
        self.install(month_season(), hc)
        rims = {self.view._canvas.itemcget(i, "fill") for i in self.view._canvas.find_withtag("rim_0")}
        self.assertTrue(set(palette.pill_edges(hc.colours["W"][0])) <= rims, rims)

    def test_a_selected_rows_opponent_reads_on_the_selection_in_every_theme(self):
        schedule = self.install(gap_season())
        home = next(i for i, item in enumerate(schedule.items) if item.home)
        themes = list(palette.THEMES) + [palette.with_club(t, palette.club_tint(t, ("#ee2737", "#ffffff")))
                                         for t in palette.THEMES if t.club_colours]
        canvas = self.view._canvas
        canvas.event_generate("<Button-1>", x=400, y=int((home + 0.5) * self.view.row_height))
        for theme in themes:
            self.view.set_theme(theme)
            self.root.update()
            fill = canvas.itemcget(self.tagged(f"opp_{home}"), "fill")
            self.assertEqual(canvas.itemcget(self.tagged(f"bg_{home}"), "fill"), theme.selection[0])
            self.assertGreaterEqual(palette.contrast_ratio(fill, theme.selection[0]), palette.READABLE, theme.name)

    def test_the_empty_message_is_muted(self):
        canvas = self.view._canvas
        for theme in (palette.MIDNIGHT_EMERALD, palette.HIGH_CONTRAST):
            self.view.set_theme(theme)
            self.view.clear()
            (message,) = canvas.find_all()
            self.assertEqual((canvas.itemcget(message, "text"), canvas.itemcget(message, "fill")),
                             ("No matches to show.", theme.muted))


class ScheduleFilterRibbonTests(ViewCase):
    def setUp(self):
        super().setUp()
        self.items = self.install(month_season()).items

    def choose(self, menu, label):
        self.assertIn(label, menu.cget("values"))
        menu.set(label)
        menu.cget("command")(label)
        self.root.update()

    def opponents(self):
        return [i.opponent for i in self.view._filtered]

    def test_the_competition_menu_names_each_competition_and_filters_to_it(self):
        menu = self.view._competition_menu
        self.assertEqual(list(menu.cget("values")), ["All competitions", "Invented League", "Invented Cup"])
        self.choose(menu, "Invented Cup")
        self.assertEqual({i.competition_id for i in self.view._filtered}, {102})
        self.assertEqual(self.view._filter_label.cget("text"), "Filtered: 1 of 4 · Invented Cup")

    def test_the_venue_menu_filters_home_away_and_neutral(self):
        self.assertEqual(list(self.view._venue_menu.cget("values")), ["All venues", "Home", "Away", "Neutral"])
        self.choose(self.view._venue_menu, "Away")
        self.assertEqual(self.opponents(), ["Westford Town", "Kingsbay City"])

    def test_the_month_menu_offers_the_months_the_schedule_holds(self):
        self.assertEqual(list(self.view._month_menu.cget("values")), ["All months", "August", "September"])
        self.choose(self.view._month_menu, "September")
        self.assertEqual(self.opponents(), ["Kingsbay City"])

    def test_the_result_menu_filters_by_outcome(self):
        self.assertEqual(list(self.view._result_menu.cget("values")),
                         ["All results", "Wins", "Draws", "Losses", "Unscored"])
        self.choose(self.view._result_menu, "Wins")
        self.assertEqual(self.opponents(), ["Eastholm Athletic", "Southmere United"])

    def test_typing_in_the_search_box_filters_by_opponent_as_you_type(self):
        entry = self.view._search_entry
        entry._entry.focus_force()
        self.root.update()
        entry.insert(0, "west")
        entry._entry.event_generate("<KeyRelease>", keysym="t")
        self.root.update()
        self.assertEqual(self.opponents(), ["Westford Town"])
        self.assertEqual(self.view._filter_label.cget("text"), 'Filtered: 1 of 4 · "west"')

    def test_clear_filters_resets_the_filter_and_every_control(self):
        view = self.view
        self.choose(view._competition_menu, "Invented League")
        self.choose(view._venue_menu, "Away")
        self.choose(view._month_menu, "September")
        self.choose(view._result_menu, "Losses")
        view.apply_search("king")
        self.assertEqual(self.opponents(), ["Kingsbay City"])
        view._reset_btn.invoke()
        self.root.update()
        self.assertEqual(view._filter, ScheduleFilter())
        self.assertEqual([m.get() for m in (view._competition_menu, view._venue_menu, view._month_menu,
                                            view._result_menu)],
                         ["All competitions", "All venues", "All months", "All results"])
        self.assertEqual(view._search_entry.get(), "")
        self.assertEqual(len(view._filtered), len(self.items))
        self.assertEqual(view._filter_label.cget("text"), "")

    def test_a_filter_set_by_the_window_shows_in_the_controls(self):
        self.view.apply_search("Kingsbay City")
        self.assertEqual(self.view._search_entry.get(), "Kingsbay City")
        self.assertEqual(self.opponents(), ["Kingsbay City"])

    def test_each_row_names_its_competition(self):
        self.assertIn("Invented League", self.texts(0))
        self.assertIn("Invented Cup", self.texts(1))


class ScheduleNarrowWidthTests(ViewCase):
    def test_nothing_overlaps_at_the_minimum_window_width(self):
        canvas = self.view._canvas
        canvas.grid_configure(sticky="ns")              # the 1,050 px window leaves the canvas about 680 px
        canvas.configure(width=680)
        self.view.set_show_gaps(True)
        self.install(long_name_season())
        self.assertEqual(canvas.winfo_width(), 680)

        def box(name, row):
            return canvas.bbox(self.tagged(f"{name}_{row}"))

        comp, opponent, gap, pill, outcome = (box(n, 2) for n in ("comp", "opp", "gap", "pill", "outcome"))
        self.assertLess(comp[2], opponent[0])
        self.assertLess(opponent[2], gap[0])
        self.assertLess(gap[2], pill[0])
        self.assertLessEqual(pill[2], outcome[0])
        self.assertLessEqual(outcome[2], 680)
        opponent, gap, status = (box(n, 4) for n in ("opp", "gap", "status"))
        self.assertLess(opponent[2], gap[0])
        self.assertLess(gap[2], status[0])
        self.assertLessEqual(status[2], 680)
        self.assertTrue(canvas.itemcget(self.tagged("opp_4"), "text").endswith("…"))
        self.assertTrue(canvas.itemcget(self.tagged("gap_4"), "text").startswith("2 days"))


class ScheduleViewportTests(ViewCase):
    def test_only_the_visible_band_of_a_long_schedule_is_drawn(self):
        schedule = self.install(long_season(200))
        self.assertEqual(len(schedule.items), 200)
        self.assertLessEqual(len(self.drawn_rows()), ScheduleView.PAGE_SIZE)
        self.view._scrollbar.cget("command")("moveto", 1.0)        # as dragging the scrollbar does
        self.root.update()
        rows = self.drawn_rows()
        self.assertIn(199, rows)
        self.assertLessEqual(len(rows), ScheduleView.PAGE_SIZE)

    def test_end_draws_and_selects_the_last_match_of_a_long_schedule(self):
        self.install(long_season(200))
        self.view._canvas.focus_force()
        self.root.update()
        self.key("<End>")
        self.assertEqual(self.view._selected_index, 199)
        self.assertIn(199, self.drawn_rows())
        self.assertLessEqual(len(self.drawn_rows()), ScheduleView.PAGE_SIZE)


class ScheduleKeyboardTests(ViewCase):
    def setUp(self):
        super().setUp()
        self.items = self.install(month_season()).items
        self.view._canvas.focus_force()
        self.root.update()

    def refs(self, found):
        return [i.ref for i in found]

    def test_down_and_up_move_the_selection_and_tell_the_window(self):
        self.key("<Down>")
        self.key("<Down>")
        self.key("<Up>")
        self.assertEqual(self.view._selected_index, 0)
        self.assertEqual(self.refs(self.selected), [self.items[k].ref for k in (0, 1, 0)])

    def test_home_and_end_jump_to_the_first_and_last_match(self):
        self.key("<End>")
        self.assertEqual(self.view._selected_index, 3)
        self.key("<Home>")
        self.assertEqual(self.view._selected_index, 0)

    def test_return_inspects_the_selected_match(self):
        self.key("<Down>")
        self.key("<Down>")
        self.key("<Return>")
        self.assertEqual(self.refs(self.inspected), [self.items[1].ref])

    def test_ctrl_c_copies_the_selected_match_as_one_line(self):
        self.key("<End>")
        with mock.patch.object(self.view, "clipboard_clear"), mock.patch.object(self.view, "clipboard_append") as add:
            self.key("<Control-c>")
        add.assert_called_once_with("5 Sep 2099 · Invented League · Kingsbay City (away) · 1-2 L")

    def test_a_click_selects_the_row_and_tells_the_window(self):
        self.view._canvas.event_generate("<Button-1>", x=400, y=int(1.5 * self.view.row_height))
        self.root.update()
        self.assertEqual(self.view._selected_index, 1)
        self.assertEqual(self.refs(self.selected), [self.items[1].ref])

    def test_the_selection_is_recoloured_in_place_without_redrawing_the_rows(self):
        canvas = self.view._canvas
        before = set(canvas.find_all())
        self.key("<Down>")
        self.assertEqual(set(canvas.find_all()), before)
        self.assertEqual(canvas.itemcget(self.tagged("bg_0"), "fill"), palette.MIDNIGHT_EMERALD.selection[0])


class ScheduleCompactTests(ViewCase):
    def test_compact_rows_are_shorter_and_leave_out_the_competition(self):
        self.install(month_season())
        self.assertEqual((ScheduleView.ROW_HEIGHT, ScheduleView.COMPACT_ROW_HEIGHT), (34, 26))
        self.assertEqual(self.view.row_height, 34)
        self.assertIn("Invented League", self.texts(0))
        self.view._compact_box.toggle()                       # the Compact checkbox
        self.root.update()
        self.assertEqual(self.view.row_height, 26)
        self.assertEqual(self.view._canvas.coords(self.tagged("bg_1"))[1], 26)
        self.assertNotIn("Invented League", self.texts(0))


if __name__ == "__main__":
    unittest.main()
