# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Schedule view: a followed club's fixtures across all competitions, with filters.

Pure helpers (ScheduleFilter, apply_filter, schedule_line, elide) are at the top and have no UI code.
ScheduleView is a CTkFrame embedded by fm_review.py; it draws on a Canvas only the band of rows in view, with a
small buffer, so a long season never creates thousands of canvas items. Heavy work (club_schedule, etc.) is done
on worker threads before install_schedule is called on the main thread.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from typing import Callable, Mapping, Sequence

import fm_data as fd
import palette as pal
import roundel_ui

VENUE_WORDS = {"H": "home", "A": "away", "N": "neutral"}
ELLIPSIS = "…"


def competition_name(competition_id: int | None, names: Mapping[int, str] | None = None) -> str:
    """A competition's display name: the one given, else "Competition <id>", as the save stores no names."""
    if competition_id is not None and names and names.get(competition_id):
        return names[competition_id]
    return f"Competition {competition_id}" if competition_id is not None else "Competition unknown"


def schedule_line(item: fd.ScheduleItem, competition_names: Mapping[int, str] | None = None) -> str:
    """One match as a plain line for the clipboard: date, competition, opponent and venue, then the score and outcome,
    or where the match falls against the save's own date."""
    date = item.fixture.date.strftime("%d %b %Y").lstrip("0") if item.fixture.date else "Date not set"
    if item.played:
        status = item.score if item.outcome in (None, fd.UNKNOWN_RESULT) else f"{item.score} {item.outcome}"
    else:
        status = "To play" if item.when == fd.WHEN_UNDATED else fd.countdown_text(item.when, item.days) or "To play"
    return " · ".join((date, competition_name(item.competition_id, competition_names),
                       f"{item.opponent} ({VENUE_WORDS.get(item.venue, item.venue)})", status))


def elide(text: str, width: float, measure: Callable[[str], float]) -> str:
    """The text when it fits `width` (as `measure` sizes it), else its longest start that fits with an ellipsis,
    else nothing."""
    if measure(text) <= width:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if measure(text[:middle].rstrip() + ELLIPSIS) <= width:
            low = middle
        else:
            high = middle - 1
    return text[:low].rstrip() + ELLIPSIS if low else ""


# ---------------------------------------------------------------------------
# Pure filter model

@dataclass(frozen=True, slots=True)
class ScheduleFilter:
    """The active filter state.  Every field is optional and None means 'show all'."""

    competition_id: int | None = None
    venue: str | None = None           # "H", "A" or "N"
    month: int | None = None           # 1–12
    result: str | None = None          # "W", "D", "L", "?", or None for all
    search: str = ""                   # free-text substring, case-insensitive

    @property
    def active(self) -> bool:
        return any((self.competition_id is not None, self.venue is not None,
                    self.month is not None, self.result is not None, bool(self.search)))

    def describe(self, competition_names: Mapping[int, str] | None = None) -> str:
        """A short human-readable summary of what is active, for the filter-status chip."""
        parts = []
        if self.competition_id is not None:
            parts.append(competition_name(self.competition_id, competition_names))
        if self.venue is not None:
            parts.append(VENUE_WORDS.get(self.venue, self.venue))
        if self.month is not None:
            parts.append(dt.date(2000, self.month, 1).strftime("%B"))
        if self.result is not None:
            parts.append({"W": "wins", "D": "draws", "L": "losses", "?": "unscored"}.get(self.result, self.result))
        if self.search:
            parts.append(f'"{self.search}"')
        return " · ".join(parts) if parts else ""


def apply_filter(items: Sequence[fd.ScheduleItem], f: ScheduleFilter) -> tuple[fd.ScheduleItem, ...]:
    """Return the subset of items that match every active filter criterion."""
    result = []
    search_lower = f.search.lower()
    for item in items:
        if f.competition_id is not None and item.competition_id != f.competition_id:
            continue
        if f.venue is not None and item.venue != f.venue:
            continue
        if f.month is not None:
            if item.fixture.date is None or item.fixture.date.month != f.month:
                continue
        if f.result is not None:
            if not item.played or item.outcome != f.result:
                continue
        if search_lower:
            if search_lower not in item.opponent.lower():
                continue
        result.append(item)
    return tuple(result)


# ---------------------------------------------------------------------------
# Widget

try:
    import customtkinter as ctk
    _CTK_AVAILABLE = True
except ImportError:
    _CTK_AVAILABLE = False


if _CTK_AVAILABLE:
    import tkinter as tk
    from tkinter import font as tkfont

    class ScheduleView(ctk.CTkFrame):
        """A Canvas-backed view of a followed club's matches with live filters.

        Call install_schedule(schedule, theme) from the main thread to show a new schedule. Only the band of rows in
        view, and BUFFER rows either side (never more than PAGE_SIZE), is drawn, and drawn again as it scrolls;
        selecting a row recolours it in place. The rows take keyboard focus: Up, Down, Home and End move the
        selection, Return inspects it and Ctrl+C copies it as one line.
        """

        ROW_HEIGHT = 34
        COMPACT_ROW_HEIGHT = 26     # compact rows also leave out the competition
        ROUNDEL = 22                # the opponent's roundel, in pixels across
        PAGE_SIZE = 50              # the most rows drawn at once
        BUFFER = 4                  # rows drawn beyond each edge of the view
        MARGIN = 8                  # the right-hand edge
        SPACING = 12                # between the opponent, the gap and the result
        DATE_WIDTH = 84
        COMPETITION_WIDTH = 112
        OPPONENT_MIN = 110          # the opponent keeps this much before the countdown and the gap take their share
        SCORE_PILL, OUTCOME_PILL, PILL_GAP = 52, 24, 4
        FONT = ("Segoe UI", 9)
        BOLD = ("Segoe UI", 9, "bold")
        ALL_COMPETITIONS, ALL_MONTHS = "All competitions", "All months"
        VENUES = {"All venues": None, "Home": "H", "Away": "A", "Neutral": "N"}
        RESULTS = {"All results": None, "Wins": "W", "Draws": "D", "Losses": "L", "Unscored": fd.UNKNOWN_RESULT}

        def __init__(self, master, *, on_select=None, on_inspect=None, on_right_click=None,
                     compact: bool = False, show_gaps: bool = False, on_gaps_changed=None, **kw):
            super().__init__(master, **kw)
            self._schedule: fd.Schedule | None = None
            self._filter = ScheduleFilter()
            self._filtered: tuple[fd.ScheduleItem, ...] = ()
            self._theme: pal.Theme = pal.MIDNIGHT_EMERALD
            self._roundels: dict[str | None, pal.Roundel] = {}
            self._competition_names: dict[int, str] = {}
            self._competition_choices: dict[str, int | None] = {self.ALL_COMPETITIONS: None}
            self._month_choices: dict[str, int | None] = {self.ALL_MONTHS: None}
            self._compact = compact
            self._on_select = on_select             # (item) → None, so the open Inspector follows the selection
            self._on_inspect = on_inspect           # (item) → None
            self._on_right_click = on_right_click   # (event, item) → None
            self._selected_index: int | None = None
            self._band: tuple[int, int] | None = None   # the rows drawn: the first, and one past the last
            self._show_gaps = show_gaps
            self._on_gaps_changed = on_gaps_changed     # (bool) → None, so the window can remember the choice
            self._build_ui()

        def _build_ui(self) -> None:
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=1)
            self._font = tkfont.Font(root=self, font=self.FONT)        # sizes the text the rows draw

            # -- the filter ribbon: four menus and a search box, then the summary, the options and Clear filters
            bar = ctk.CTkFrame(self, fg_color="transparent")
            bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
            bar.grid_columnconfigure(4, weight=1)
            self._competition_menu = ctk.CTkOptionMenu(bar, values=[self.ALL_COMPETITIONS], width=150,
                                                       dynamic_resizing=False, command=self._on_competition_chosen)
            self._venue_menu = ctk.CTkOptionMenu(bar, values=list(self.VENUES), width=100, dynamic_resizing=False,
                                                 command=self._on_venue_chosen)
            self._month_menu = ctk.CTkOptionMenu(bar, values=[self.ALL_MONTHS], width=110, dynamic_resizing=False,
                                                 command=self._on_month_chosen)
            self._result_menu = ctk.CTkOptionMenu(bar, values=list(self.RESULTS), width=100, dynamic_resizing=False,
                                                  command=self._on_result_chosen)
            self._search_entry = ctk.CTkEntry(bar, placeholder_text="Search opponent…", width=120)
            self._search_entry.bind("<KeyRelease>", self._on_search_typed)
            controls = (self._competition_menu, self._venue_menu, self._month_menu, self._result_menu,
                        self._search_entry)
            for column, widget in enumerate(controls):
                widget.grid(row=0, column=column, sticky="ew" if widget is self._search_entry else "w",
                            padx=(0, 6), pady=(0, 2))
            status = ctk.CTkFrame(bar, fg_color="transparent")
            status.grid(row=1, column=0, columnspan=len(controls), sticky="ew")
            self._filter_label = ctk.CTkLabel(status, text="", anchor="w")
            self._filter_label.pack(side="left", padx=4)
            self._reset_btn = ctk.CTkButton(status, text="Clear filters", width=100, command=self._reset_filter)
            self._compact_box = ctk.CTkCheckBox(status, text="Compact", command=self._compact_box_changed,
                                                checkbox_width=18, checkbox_height=18)
            if self._compact:
                self._compact_box.select()
            self._compact_box.pack(side="right", padx=8)
            self._gap_box = ctk.CTkCheckBox(status, text="Fixture gap", command=self._gap_box_changed,
                                            checkbox_width=18, checkbox_height=18)
            if self._show_gaps:
                self._gap_box.select()
            self._gap_box.pack(side="right", padx=8)

            # -- canvas + scrollbar
            frame = ctk.CTkFrame(self, fg_color="transparent")
            frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)
            self._canvas = tk.Canvas(frame, highlightthickness=0, bd=0, takefocus=1, bg=self._theme.table[0])
            self._scrollbar = ctk.CTkScrollbar(frame, command=self._yview)
            self._canvas.configure(yscrollcommand=self._scrollbar.set)
            self._canvas.grid(row=0, column=0, sticky="nsew")
            self._scrollbar.grid(row=0, column=1, sticky="ns")

            canvas = self._canvas
            canvas.bind("<Configure>", self._on_canvas_resize)
            canvas.bind("<MouseWheel>", self._on_mousewheel)
            canvas.bind("<Button-1>", self._on_click)
            canvas.bind("<Button-3>", self._on_right)
            canvas.bind("<Double-Button-1>", self._on_double_click)
            canvas.bind("<Up>", lambda _event: self._move_selection(-1))
            canvas.bind("<Down>", lambda _event: self._move_selection(1))
            canvas.bind("<Home>", lambda _event: self._select_and_show(0))
            canvas.bind("<End>", lambda _event: self._select_and_show(len(self._filtered) - 1))
            canvas.bind("<Return>", self._on_return)
            canvas.bind("<Control-c>", self._copy_selected)

        # ---- public API (call on main thread only) ---------------------

        @property
        def row_height(self) -> int:
            return self.COMPACT_ROW_HEIGHT if self._compact else self.ROW_HEIGHT

        def install_schedule(self, schedule: fd.Schedule, theme: pal.Theme,
                             roundels: dict[str | None, pal.Roundel] | None = None,
                             competition_names: Mapping[int, str] | None = None) -> None:
            """Show a schedule. `roundels` maps each opponent's club name (None: unresolved) to its roundel in this
            theme, worked out off the main thread (palette.roundel_book); `competition_names` maps competition ids to
            the names the rows, the competition menu and the filter summary show."""
            # The same club's same season again (late expected goals, say) keeps the user's filter.
            same = (self._schedule is not None and self._schedule.club == schedule.club
                    and self._schedule.season == schedule.season)
            kept = self._filter if same else ScheduleFilter()
            self._schedule = schedule
            self._theme = theme
            self._roundels = roundels or {}
            self._competition_names = dict(competition_names or {})
            self._fill_choices()
            if kept.competition_id not in self._competition_choices.values():
                kept = replace(kept, competition_id=None)
            if kept.month not in self._month_choices.values():
                kept = replace(kept, month=None)
            self._filter = kept
            self._theme_controls()
            self._sync_controls()
            self._rebuild()

        def set_show_gaps(self, show: bool) -> None:
            """Show or hide the interval since the club's previous fixture on each dated row."""
            if show:
                self._gap_box.select()
            else:
                self._gap_box.deselect()
            self._gap_box_changed()

        def _gap_box_changed(self) -> None:
            self._show_gaps = bool(self._gap_box.get())
            if self._on_gaps_changed:
                self._on_gaps_changed(self._show_gaps)
            self._repaint()

        def set_compact(self, compact: bool) -> None:
            """Compact rows are COMPACT_ROW_HEIGHT high rather than ROW_HEIGHT and leave out the competition."""
            self._compact = compact
            if compact:
                self._compact_box.select()
            else:
                self._compact_box.deselect()
            self._repaint()
            if self._selected_index is not None:
                self._see(self._selected_index)

        def _compact_box_changed(self) -> None:
            self.set_compact(bool(self._compact_box.get()))

        def clear(self) -> None:
            self._schedule = None
            self._filter = ScheduleFilter()
            self._fill_choices()
            self._sync_controls()
            self._rebuild()

        def set_filter(self, f: ScheduleFilter) -> None:
            self._filter = f
            self._sync_controls()
            self._rebuild()

        def set_theme(self, theme: pal.Theme, roundels: dict[str | None, pal.Roundel] | None = None) -> None:
            self._theme = theme
            if roundels is not None:
                self._roundels = roundels
            self._theme_controls()
            self._repaint()

        def jump_to_upcoming(self) -> None:
            if self._schedule is None:
                return
            idx = next((i for i, it in enumerate(self._filtered)
                        if it.when in (fd.WHEN_TODAY, fd.WHEN_UPCOMING)), None)
            if idx is not None:
                self._scroll_to_row(idx)

        def line_for(self, item: fd.ScheduleItem) -> str:
            """The match as one plain line, as Ctrl+C copies it."""
            return schedule_line(item, self._competition_names)

        # ---- filter control --------------------------------------------

        def apply_competition_filter(self, competition_id: int | None) -> None:
            self.set_filter(replace(self._filter, competition_id=competition_id))

        def apply_venue_filter(self, venue: str | None) -> None:
            self.set_filter(replace(self._filter, venue=venue))

        def apply_month_filter(self, month: int | None) -> None:
            self.set_filter(replace(self._filter, month=month))

        def apply_result_filter(self, result: str | None) -> None:
            self.set_filter(replace(self._filter, result=result))

        def apply_search(self, text: str) -> None:
            self.set_filter(replace(self._filter, search=text))

        def _reset_filter(self) -> None:
            self.set_filter(ScheduleFilter())

        def _on_competition_chosen(self, label: str) -> None:
            self.apply_competition_filter(self._competition_choices.get(label))

        def _on_venue_chosen(self, label: str) -> None:
            self.apply_venue_filter(self.VENUES.get(label))

        def _on_month_chosen(self, label: str) -> None:
            self.apply_month_filter(self._month_choices.get(label))

        def _on_result_chosen(self, label: str) -> None:
            self.apply_result_filter(self.RESULTS.get(label))

        def _on_search_typed(self, _event=None) -> None:
            text = self._search_entry.get()
            if text != self._filter.search:
                self.apply_search(text)

        def _fill_choices(self) -> None:
            """The competition and month menus offer only what the schedule holds, in its own order."""
            self._competition_choices = {self.ALL_COMPETITIONS: None}
            self._month_choices = {self.ALL_MONTHS: None}
            if self._schedule is not None:
                for c in self._schedule.competitions:
                    label = competition_name(c.competition_id, self._competition_names)
                    if label in self._competition_choices:              # two competitions of one name stay apart
                        label = f"{label} ({c.competition_id})"
                    self._competition_choices[label] = c.competition_id
                for item in self._schedule.items:
                    if item.fixture.date is not None:
                        self._month_choices.setdefault(item.fixture.date.strftime("%B"), item.fixture.date.month)
            self._competition_menu.configure(values=list(self._competition_choices))
            self._month_menu.configure(values=list(self._month_choices))

        @staticmethod
        def _label_for(choices: Mapping[str, object], value: object) -> str:
            return next((label for label, v in choices.items() if v == value), next(iter(choices)))

        def _sync_controls(self) -> None:
            """Show the filter in the controls, however it was set: a menu, Clear filters or the window."""
            f = self._filter
            self._competition_menu.set(self._label_for(self._competition_choices, f.competition_id))
            self._venue_menu.set(self._label_for(self.VENUES, f.venue))
            self._month_menu.set(self._label_for(self._month_choices, f.month))
            self._result_menu.set(self._label_for(self.RESULTS, f.result))
            if self._search_entry.get() != f.search:
                self._search_entry.delete(0, "end")
                if f.search:
                    self._search_entry.insert(0, f.search)

        def _theme_controls(self) -> None:
            t = self._theme
            for menu in (self._competition_menu, self._venue_menu, self._month_menu, self._result_menu):
                menu.configure(fg_color=t.quiet[0], button_color=t.quiet[0], button_hover_color=t.quiet_hover,
                               text_color=t.quiet[1], dropdown_fg_color=t.panel, dropdown_text_color=t.text,
                               dropdown_hover_color=t.selection[0])
            self._search_entry.configure(fg_color=t.field[0], border_color=t.field[1], text_color=t.text,
                                         placeholder_text_color=t.muted)
            for box in (self._gap_box, self._compact_box):
                box.configure(text_color=t.text, fg_color=t.accent[0], hover_color=t.accent_hover,
                              border_color=t.muted, checkmark_color=t.accent[1])
            self._reset_btn.configure(fg_color=t.quiet[0], hover_color=t.quiet_hover, text_color=t.quiet[1])
            self._filter_label.configure(text_color=t.text)

        # ---- internal rendering ----------------------------------------

        def _rebuild(self) -> None:
            if self._schedule is None:
                self._filtered = ()
            else:
                self._filtered = apply_filter(self._schedule.items, self._filter)
            self._selected_index = None
            if self._filter.active:
                total = len(self._schedule.items) if self._schedule else 0
                self._filter_label.configure(text=f"Filtered: {len(self._filtered)} of {total} · "
                                                  f"{self._filter.describe(self._competition_names)}")
                if not self._reset_btn.winfo_manager():
                    self._reset_btn.pack(side="right", padx=4, before=self._compact_box)
            else:
                self._filter_label.configure(text="")
                self._reset_btn.pack_forget()
            self._canvas.yview_moveto(0)
            self._repaint()
            self.after_idle(self.jump_to_upcoming)

        def _repaint(self) -> None:
            """Draw afresh the rows in view: after a new schedule, filter, theme, width or row height."""
            theme, canvas = self._theme, self._canvas
            canvas.configure(bg=theme.table[0])
            canvas.delete("all")
            self._band = None
            if not self._filtered:
                canvas.create_text(10, 10, anchor="nw", text="No matches to show.", fill=theme.muted, font=self.FONT)
                canvas.configure(scrollregion=(0, 0, 1, max(40, canvas.winfo_height())))
                return
            canvas.configure(scrollregion=(0, 0, self._width(), len(self._filtered) * self.row_height))
            self._render_band()

        def _render_band(self) -> None:
            """Draw the rows in view and BUFFER either side, never more than PAGE_SIZE, unless they are drawn."""
            if not self._filtered:
                return
            band = self._visible_band()
            if band == self._band:
                return
            self._canvas.delete("row")
            self._band = band
            width = self._width()
            for i in range(*band):
                self._draw_row(i, self._filtered[i], width)

        def _visible_band(self) -> tuple[int, int]:
            h = self.row_height
            top = self._canvas.canvasy(0)
            bottom = top + max(self._canvas.winfo_height(), h)
            first = max(0, int(top // h) - self.BUFFER)
            last = min(len(self._filtered), int(bottom // h) + 1 + self.BUFFER, first + self.PAGE_SIZE)
            return first, last

        def _width(self) -> int:
            width = self._canvas.winfo_width()
            return width if width > 50 else 400

        def _fit(self, text: str, width: float) -> str:
            return elide(text, width, self._font.measure)

        def _row_fill(self, i: int) -> str:
            t = self._theme
            if i == self._selected_index:
                return t.selection[0]
            return t.table[0] if i % 2 == 0 else t.window

        def _opponent_fill(self, i: int) -> str:
            """The followed club's home matches take the link colour, but a selected row takes the table's own text
            colour, as the link does not read at 4.5:1 on the selection in every theme."""
            t = self._theme
            if i == self._selected_index:
                return t.table[1]
            return t.link if self._filtered[i].home else t.table[1]

        def _draw_row(self, i: int, item: fd.ScheduleItem, width: int) -> None:
            canvas, t, h = self._canvas, self._theme, self.row_height
            y0, y1 = i * h, (i + 1) * h
            mid = y0 + h // 2
            row = ("row", f"row_{i}")
            canvas.create_rectangle(0, y0, width, y1, fill=self._row_fill(i), outline="", tags=(*row, f"bg_{i}"))
            date_text = item.fixture.date.strftime("%d %b %Y").lstrip("0") if item.fixture.date else "—"
            canvas.create_text(6, mid, anchor="w", text=date_text, fill=t.table[1], font=self.FONT, tags=row)
            x = 6 + self.DATE_WIDTH
            if not self._compact:
                name = competition_name(item.competition_id, self._competition_names)
                canvas.create_text(x, mid, anchor="w", text=self._fit(name, self.COMPETITION_WIDTH - self.SPACING),
                                   fill=t.muted, font=self.FONT, tags=(*row, f"comp_{i}"))
                x += self.COMPETITION_WIDTH
            # opponent, after a roundel in their colours (an identity aid, not a crest)
            badge = self._roundels.get(item.opponent_club)
            if badge is not None:
                roundel_ui.draw_roundel(canvas, x + self.ROUNDEL // 2, mid, self.ROUNDEL, badge, (*row, "roundel"), i)
                x += self.ROUNDEL + 6
            # Share out what is left: the opponent keeps OPPONENT_MIN, the countdown and then the gap take what they
            # need, and the opponent has the rest. Each text is cut short with an ellipsis to fit its share, so the
            # opponent, the gap and the result never meet, however narrow the window.
            right = width - self.MARGIN
            gap = self._schedule.gaps.get(item.ref) if self._show_gaps and self._schedule else None
            gap_text = gap.text() if gap is not None else ""
            status_text = "" if item.played else fd.countdown_text(item.when, item.days)
            pills = self.SCORE_PILL + self.PILL_GAP + self.OUTCOME_PILL if item.played else 0
            opponent = f"{item.venue}  {item.opponent}"
            free = right - x - pills - self.SPACING - (self.SPACING if gap_text else 0)
            opponent_w = min(self._font.measure(opponent), self.OPPONENT_MIN, max(free, 0))
            free -= opponent_w
            status_w = max(0, min(self._font.measure(status_text), free)) if status_text else 0
            free -= status_w
            gap_w = max(0, min(self._font.measure(gap_text), free)) if gap_text else 0
            free -= gap_w
            opponent_w += max(free, 0)
            status_left = right - (pills or status_w)
            canvas.create_text(x, mid, anchor="w", text=self._fit(opponent, opponent_w), fill=self._opponent_fill(i),
                               font=self.FONT, tags=(*row, f"opp_{i}"))
            if gap_w:      # right-aligned, ending before the result, so the two never meet
                canvas.create_text(status_left - self.SPACING, mid, anchor="e", text=self._fit(gap_text, gap_w),
                                   fill=t.muted, font=self.FONT, tags=(*row, f"gap_{i}"))
            if item.played:
                outcome = item.outcome or fd.UNKNOWN_RESULT
                fill, ink = t.colours.get(outcome, t.colours[fd.UNKNOWN_RESULT])
                self._pill(status_left, status_left + self.SCORE_PILL, i, fill, ink, item.score, "pill", "score")
                self._pill(right - self.OUTCOME_PILL, right, i, fill, ink, outcome, "outcome", "letter")
            elif status_w:
                canvas.create_text(right, mid, anchor="e", text=self._fit(status_text, status_w), fill=t.muted,
                                   font=self.FONT, tags=(*row, f"status_{i}"))

        def _pill(self, x0: float, x1: float, i: int, fill: str, ink: str, text: str, kind: str, text_kind: str) -> None:
            """A result pill in its own colour, with a faint lighter top rim and darker bottom rim, and its text in the
            matching ink: the text never sits on the row itself (in High-Contrast it would vanish into the black)."""
            canvas, h = self._canvas, self.row_height
            top, bottom = i * h + 4, (i + 1) * h - 4
            row = ("row", f"row_{i}")
            canvas.create_rectangle(x0, top, x1, bottom, fill=fill, outline="", tags=(*row, f"{kind}_{i}"))
            light, dark = pal.pill_edges(fill)
            canvas.create_line(x0 + 1, top, x1 - 1, top, fill=light, tags=(*row, f"rim_{i}"))
            canvas.create_line(x0 + 1, bottom - 1, x1 - 1, bottom - 1, fill=dark, tags=(*row, f"rim_{i}"))
            canvas.create_text((x0 + x1) / 2, (top + bottom) / 2, text=text, fill=ink, font=self.BOLD,
                               tags=(*row, f"{text_kind}_{i}"))

        # ---- selection and scrolling -----------------------------------

        def _set_selection(self, index: int | None) -> None:
            """Move the selection, recolouring only the two rows concerned rather than drawing every row again."""
            previous, self._selected_index = self._selected_index, index
            for i in {previous, index} - {None}:
                for item_id in self._canvas.find_withtag(f"bg_{i}"):
                    self._canvas.itemconfigure(item_id, fill=self._row_fill(i))
                for item_id in self._canvas.find_withtag(f"opp_{i}"):
                    self._canvas.itemconfigure(item_id, fill=self._opponent_fill(i))

        def _select_and_show(self, index: int) -> str:
            if 0 <= index < len(self._filtered):
                self._set_selection(index)
                self._see(index)
                if self._on_select:
                    self._on_select(self._filtered[index])
            return "break"

        def _move_selection(self, step: int) -> str:
            if not self._filtered:
                return "break"
            if self._selected_index is None:              # start from the first row in view
                target = int(self._canvas.canvasy(0) // self.row_height)
            else:
                target = self._selected_index + step
            return self._select_and_show(max(0, min(len(self._filtered) - 1, target)))

        def _see(self, index: int) -> None:
            """Scroll as little as needed to bring a row into view, then draw the rows in view."""
            h = self.row_height
            total = max(len(self._filtered) * h, 1)
            top, height = self._canvas.canvasy(0), self._canvas.winfo_height()
            if index * h < top:
                self._canvas.yview_moveto(index * h / total)
            elif (index + 1) * h > top + height:
                self._canvas.yview_moveto(max(0.0, ((index + 1) * h - height) / total))
            self._render_band()

        def _scroll_to_row(self, index: int) -> None:
            total = max(len(self._filtered), 1)
            frac = index / total
            self._canvas.yview_moveto(max(0.0, frac - 0.1))
            self._render_band()

        def _row_at(self, event) -> int | None:
            idx = int(self._canvas.canvasy(event.y) // self.row_height)
            if 0 <= idx < len(self._filtered):
                return idx
            return None

        def _yview(self, *args) -> None:
            """The scrollbar's command: scroll, then draw the rows now in view."""
            self._canvas.yview(*args)
            self._render_band()

        def _on_canvas_resize(self, event) -> None:
            self._repaint()

        def _on_mousewheel(self, event) -> None:
            self._canvas.yview_scroll(int(-event.delta / 120), "units")
            self._render_band()

        def _on_click(self, event) -> None:
            self._canvas.focus_set()          # so the arrow keys, Return and Ctrl+C reach the rows
            idx = self._row_at(event)
            if idx is None:
                self._set_selection(None)
            else:
                self._select_and_show(idx)

        def _on_double_click(self, event) -> None:
            idx = self._row_at(event)
            if idx is not None and self._on_inspect:
                self._on_inspect(self._filtered[idx])

        def _on_right(self, event) -> None:
            idx = self._row_at(event)
            if idx is not None:
                self._select_and_show(idx)
                if self._on_right_click:
                    self._on_right_click(event, self._filtered[idx])

        def _on_return(self, _event=None) -> str:
            if self._selected_index is not None and self._on_inspect:
                self._on_inspect(self._filtered[self._selected_index])
            return "break"

        def _copy_selected(self, _event=None) -> str:
            if self._selected_index is not None:
                self.clipboard_clear()
                self.clipboard_append(self.line_for(self._filtered[self._selected_index]))
            return "break"
