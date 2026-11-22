# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Schedule view: a followed club's fixtures across all competitions, with filters.

Pure helpers (ScheduleFilter, apply_filter) are at the top and have no UI code.
ScheduleView is a CTkFrame embedded by fm_review.py; it uses a Canvas viewport so
only visible rows are rendered.  Heavy work (club_schedule, etc.) is done on
worker threads before install_schedule is called on the main thread.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, replace
from typing import Sequence

import fm_data as fd
import palette as pal
import roundel_ui

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

    def describe(self) -> str:
        """A short human-readable summary of what is active, for the filter-status chip."""
        parts = []
        if self.competition_id is not None:
            parts.append(f"comp {self.competition_id}")
        if self.venue is not None:
            parts.append({"H": "home", "A": "away", "N": "neutral"}.get(self.venue, self.venue))
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
    class ScheduleView(ctk.CTkFrame):
        """A Canvas-backed view of a followed club's matches with live filters.

        Call install_schedule(schedule) from the main thread to show a new schedule.
        The canvas renders only the visible row band; rows are recycled on scroll.
        """

        ROW_HEIGHT = 32
        ROUNDEL = 22            # the opponent's roundel, in pixels across
        PAGE_SIZE = 50          # max rows rendered at once; neighbouring pages pre-fetched lazily

        def __init__(self, master, *, on_inspect=None, on_right_click=None,
                     compact: bool = False, show_gaps: bool = False, on_gaps_changed=None, **kw):
            super().__init__(master, **kw)
            self._schedule: fd.Schedule | None = None
            self._filter = ScheduleFilter()
            self._filtered: tuple[fd.ScheduleItem, ...] = ()
            self._theme: pal.Theme = pal.MIDNIGHT_EMERALD
            self._roundels: dict[str | None, pal.Roundel] = {}
            self._compact = compact
            self._on_inspect = on_inspect           # (item) → None
            self._on_right_click = on_right_click   # (event, item) → None
            self._selected_index: int | None = None
            self._show_gaps = show_gaps
            self._on_gaps_changed = on_gaps_changed     # (bool) ÔåÆ None, so the window can remember the choice
            self._build_ui()

        def _build_ui(self) -> None:
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=1)

            # -- filter bar
            bar = ctk.CTkFrame(self, fg_color="transparent")
            bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
            self._filter_label = ctk.CTkLabel(bar, text="", anchor="w")
            self._filter_label.pack(side="left", padx=4)
            self._reset_btn = ctk.CTkButton(bar, text="Clear filters", width=100,
                                            command=self._reset_filter)
            self._reset_btn.pack(side="right", padx=4)
            self._reset_btn.pack_forget()   # hidden when no filter is active
            self._gap_box = ctk.CTkCheckBox(bar, text="Fixture gap", command=self._gap_box_changed,
                                            checkbox_width=18, checkbox_height=18)
            if self._show_gaps:
                self._gap_box.select()
            self._gap_box.pack(side="right", padx=8)

            # -- canvas + scrollbar
            frame = ctk.CTkFrame(self, fg_color="transparent")
            frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)

            import tkinter as tk
            self._canvas = tk.Canvas(frame, highlightthickness=0, bd=0)
            self._scrollbar = ctk.CTkScrollbar(frame, command=self._canvas.yview)
            self._canvas.configure(yscrollcommand=self._scrollbar.set)
            self._canvas.grid(row=0, column=0, sticky="nsew")
            self._scrollbar.grid(row=0, column=1, sticky="ns")

            self._canvas.bind("<Configure>", self._on_canvas_resize)
            self._canvas.bind("<MouseWheel>", self._on_mousewheel)
            self._canvas.bind("<Button-1>", self._on_click)
            self._canvas.bind("<Button-3>", self._on_right)
            self._canvas.bind("<Double-Button-1>", self._on_double_click)

        # ---- public API (call on main thread only) ---------------------

        def install_schedule(self, schedule: fd.Schedule, theme: pal.Theme,
                             roundels: dict[str | None, pal.Roundel] | None = None) -> None:
            """Show a schedule. `roundels` maps each opponent's club name (None: unresolved) to its roundel in this
            theme, worked out off the main thread (palette.roundel_book)."""
            self._schedule = schedule
            self._theme = theme
            self._roundels = roundels or {}
            self._filter = ScheduleFilter()
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

        def clear(self) -> None:
            self._schedule = None
            self._filter = ScheduleFilter()
            self._rebuild()

        def set_filter(self, f: ScheduleFilter) -> None:
            self._filter = f
            self._rebuild()

        def set_theme(self, theme: pal.Theme, roundels: dict[str | None, pal.Roundel] | None = None) -> None:
            self._theme = theme
            if roundels is not None:
                self._roundels = roundels
            self._repaint()

        def set_compact(self, compact: bool) -> None:
            self._compact = compact
            self._repaint()

        def jump_to_upcoming(self) -> None:
            if self._schedule is None:
                return
            idx = next((i for i, it in enumerate(self._filtered)
                        if it.when in (fd.WHEN_TODAY, fd.WHEN_UPCOMING)), None)
            if idx is not None:
                self._scroll_to_row(idx)

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

        # ---- internal rendering ----------------------------------------

        def _rebuild(self) -> None:
            if self._schedule is None:
                self._filtered = ()
            else:
                self._filtered = apply_filter(self._schedule.items, self._filter)
            self._selected_index = None
            desc = self._filter.describe()
            if self._filter.active:
                n = len(self._filtered)
                total = len(self._schedule.items) if self._schedule else 0
                self._filter_label.configure(text=f"Filtered: {n} of {total} · {desc}")
                self._reset_btn.pack(side="right", padx=4)
            else:
                self._filter_label.configure(text="")
                self._reset_btn.pack_forget()
            self._repaint()
            self.after_idle(self.jump_to_upcoming)

        def _repaint(self) -> None:
            self._canvas.delete("all")
            if not self._filtered:
                self._canvas.create_text(10, 10, anchor="nw", text="No matches to show.", fill="#808080")
                self._canvas.configure(scrollregion=(0, 0, 1, max(40, self.winfo_height())))
                return
            h = self.ROW_HEIGHT
            total_h = len(self._filtered) * h
            w = max(self._canvas.winfo_width(), 400)
            self._canvas.configure(scrollregion=(0, 0, w, total_h))
            theme = self._theme
            for i, item in enumerate(self._filtered):
                y0 = i * h
                y1 = y0 + h
                # row background
                bg = theme.table[0] if i % 2 == 0 else theme.window
                self._canvas.create_rectangle(0, y0, w, y1, fill=bg, outline="", tags=f"row_{i}")
                if self._selected_index == i:
                    self._canvas.create_rectangle(0, y0, w, y1,
                                                  fill=theme.selection[0], outline="", tags=f"row_{i}")
                # date/competition
                date_text = item.fixture.date.strftime("%d %b %Y").lstrip("0") if item.fixture.date else "—"
                self._canvas.create_text(6, y0 + h // 2, anchor="w", text=date_text,
                                         fill=theme.table[1], font=("Segoe UI", 9), tags=f"row_{i}")
                # opponent, after a roundel in their colours (an identity aid, not a crest)
                opp_x = 90
                badge = self._roundels.get(item.opponent_club)
                if badge is not None:
                    roundel_ui.draw_roundel(self._canvas, opp_x + self.ROUNDEL // 2, y0 + h // 2, self.ROUNDEL,
                                            badge, (f"row_{i}", "roundel"), i)
                    opp_x += self.ROUNDEL + 6
                self._canvas.create_text(opp_x, y0 + h // 2, anchor="w",
                                         text=f"{item.venue}  {item.opponent}",
                                         fill=theme.link if item.home else theme.table[1],
                                         font=("Segoe UI", 9), tags=f"row_{i}")
                # score / status
                score_x = w - 80
                gap = self._schedule.gaps.get(item.ref) if self._show_gaps and self._schedule else None
                if gap is not None:      # right-aligned, ending before the score pill, so the two never meet
                    self._canvas.create_text(score_x - 14, y0 + h // 2, anchor="e", text=gap.text(),
                                             fill=theme.muted, font=("Segoe UI", 9), tags=f"row_{i}")
                if item.played:
                    score_text = item.score
                    result_pair = theme.colours.get(item.outcome or "?", (None, theme.table[1]))
                    score_fg = result_pair[1] or theme.table[1]
                    if result_pair[0]:
                        self._canvas.create_rectangle(score_x - 2, y0 + 4, score_x + 56, y1 - 4,
                                                      fill=result_pair[0], outline="", tags=(f"row_{i}", f"pill_{i}"))
                    self._canvas.create_text(score_x, y0 + h // 2, anchor="w", text=score_text,
                                             fill=score_fg, font=("Segoe UI", 9, "bold"), tags=f"row_{i}")
                    # outcome letter
                    out_fg = result_pair[1] or theme.table[1]
                    self._canvas.create_text(score_x + 60, y0 + h // 2, anchor="w",
                                             text=item.outcome or "?",
                                             fill=out_fg, font=("Segoe UI", 9), tags=f"row_{i}")
                else:
                    when_text = fd.countdown_text(item.when, item.days)
                    self._canvas.create_text(score_x, y0 + h // 2, anchor="w",
                                             text=when_text, fill=theme.muted,
                                             font=("Segoe UI", 9), tags=f"row_{i}")

        def _scroll_to_row(self, index: int) -> None:
            total = max(len(self._filtered), 1)
            frac = index / total
            self._canvas.yview_moveto(max(0.0, frac - 0.1))

        def _row_at(self, event) -> int | None:
            y = self._canvas.canvasy(event.y)
            idx = int(y // self.ROW_HEIGHT)
            if 0 <= idx < len(self._filtered):
                return idx
            return None

        def _on_canvas_resize(self, event) -> None:
            self._repaint()

        def _on_mousewheel(self, event) -> None:
            self._canvas.yview_scroll(int(-event.delta / 120), "units")

        def _on_click(self, event) -> None:
            idx = self._row_at(event)
            self._selected_index = idx
            self._repaint()

        def _on_double_click(self, event) -> None:
            idx = self._row_at(event)
            if idx is not None and self._on_inspect:
                self._on_inspect(self._filtered[idx])

        def _on_right(self, event) -> None:
            idx = self._row_at(event)
            if idx is not None:
                self._selected_index = idx
                self._repaint()
                if self._on_right_click:
                    self._on_right_click(event, self._filtered[idx])
