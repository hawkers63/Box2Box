# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Manager hub view: a club overview panel driven by ManagerSnapshot.

Pure helpers (hub_rows) are at the top and have no UI code.
ManagerHubView is a CTkFrame embedded by fm_review.py as the "Hub" view.
Heavy work (manager_snapshot, club_schedule) is done on worker threads
before install_snapshot is called on the main thread.
"""

from __future__ import annotations

from typing import NamedTuple

import fm_data as fd
import palette as pal
import roundel_ui

# ---------------------------------------------------------------------------
# Pure model

class HubRow(NamedTuple):
    """A single display row for the manager hub."""
    label: str
    value: str
    muted: bool = False


def _fixture_text(item: fd.ScheduleItem) -> str:
    """Opponent, venue and date: never the score, so a step before a match cannot give its result away."""
    venue_word = {"H": "home", "A": "away", "N": "neutral"}.get(item.venue, item.venue)
    date_text = item.fixture.date.strftime("%d %b %Y").lstrip("0") if item.fixture.date else "date unknown"
    return f"{item.opponent} ({venue_word}) · {date_text}"


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def step_rows(snapshot: fd.ManagerSnapshot, step: fd.HubStep, competition_names: dict[int, str], *,
              today: bool = False, league: bool = True) -> list[HubRow]:
    """The rows for one step of the matchday stepper: what was known just before that match (or at the season's
    end), and, at the save's own date, the next match in any competition with its countdown."""
    rows = [HubRow("Snapshot", step.label)]
    table = step.table
    if table is None:
        rows.append(HubRow("Position", "No league rank: no league match this season", muted=True))
    elif table.played == 0:
        rows.append(HubRow("Position", "No league match played yet", muted=True))
    else:
        text = f"{_ordinal(table.position)} of {table.of} · {table.points} pts from {table.played} played " \
               "(calculated from the results)"
        if table.unscored:
            text += f". {table.unscored} match{'es' if table.unscored != 1 else ''} played with no score left out"
        rows.append(HubRow("Position", text))
    letters = step.form.letters
    rows.append(HubRow("Form", f"{letters} (all competitions)") if letters else HubRow("Form", "—", muted=True))
    label = "Next league match" if league else "Next match"
    if step.fixture is None:
        rows.append(HubRow(label, "Season complete", muted=True))
    else:
        rows.append(HubRow(label, _fixture_text(step.fixture)))
    nxt = snapshot.next_item
    if today and nxt is not None and (step.fixture is None or nxt.fixture is not step.fixture.fixture):
        rows.append(HubRow("Next (any competition)", _fixture_text(nxt)))
        rows.append(HubRow("Competition", competition_names.get(nxt.competition_id or 0, snapshot.next_scope_label),
                           muted=True))
    if today and nxt is not None:
        countdown = fd.countdown_text(nxt.when, nxt.days)
        if countdown:
            rows.append(HubRow("", countdown, muted=True))
    return rows


def hub_rows(snapshot: fd.ManagerSnapshot, competition_names: dict[int, str] | None = None, *,
             step: fd.HubStep | None = None, today: bool = False, league: bool = True) -> list[HubRow]:
    """Return ordered display rows from a ManagerSnapshot, or, with `step`, from one step of the matchday stepper.

    competition_names maps competition_id → display name, may be None.
    """
    if competition_names is None:
        competition_names = {}

    rows: list[HubRow] = []

    # Followed club
    rows.append(HubRow("Club", snapshot.followed.name))

    # Managed / observer
    if snapshot.managed:
        rows.append(HubRow("Role", f"Manager{' — ' + snapshot.manager_name if snapshot.manager_name else ''}"))
    else:
        rows.append(HubRow("Role", "Observer save", muted=True))

    if step is not None:
        return rows + step_rows(snapshot, step, competition_names, today=today, league=league)

    # League position
    if snapshot.rank_before_next is not None:
        rb = snapshot.rank_before_next
        pos_text = f"{rb.position}"
        if rb.points is not None:
            pos_text += f" ({rb.points} pts)"
        rows.append(HubRow("Position", pos_text))

    # Recent form
    if snapshot.form:
        outcomes = "".join(i.outcome or "?" for i in snapshot.form)
        rows.append(HubRow("Form", outcomes))
    else:
        rows.append(HubRow("Form", "—", muted=True))

    # Next fixture
    if snapshot.next_item is not None:
        ni = snapshot.next_item
        comp_name = competition_names.get(ni.competition_id or 0, snapshot.next_scope_label)
        venue_word = {"H": "home", "A": "away", "N": "neutral"}.get(ni.venue, ni.venue)
        date_text = ni.fixture.date.strftime("%d %b %Y").lstrip("0") if ni.fixture.date else "date unknown"
        rows.append(HubRow("Next", f"{ni.opponent} ({venue_word}) · {date_text}"))
        rows.append(HubRow("Competition", comp_name, muted=True))
        countdown = fd.countdown_text(ni.when, ni.days)
        if countdown:
            rows.append(HubRow("", countdown, muted=True))
    else:
        rows.append(HubRow("Next", "No upcoming fixtures", muted=True))

    return rows


# ---------------------------------------------------------------------------
# Widget

try:
    import customtkinter as ctk
    _CTK_AVAILABLE = True
except ImportError:
    _CTK_AVAILABLE = False


if _CTK_AVAILABLE:
    class ManagerHubView(ctk.CTkFrame):
        """Club overview panel driven by ManagerSnapshot, with a matchday stepper over a fd.HubSeason.

        Call install_snapshot(snapshot, theme, competition_names, roundels, season) from the main thread to show a
        new snapshot. Stale worker results must not call this after a new save has been opened: the caller guards
        the sequence number. Every step of the season was worked out before it arrived, so moving the stepper only
        picks one; slider drags are debounced.
        """

        ROW_HEIGHT = 28
        LABEL_WIDTH = 130
        CLUB_ROUNDEL = 40           # the followed club's roundel in the header
        NEXT_ROUNDEL = 24           # the next opponent's roundel on the Next row
        DEBOUNCE_MS = 150           # a slider drag settles this long after it pauses
        EXCERPT_WIDTHS = (28, 0, 30, 36, 36)     # the table excerpt's columns: #, Team (fills), P, GD, Pts
        NEXT_LABELS = ("Next", "Next league match", "Next match")

        def __init__(self, master, **kw):
            super().__init__(master, **kw)
            self._snapshot: fd.ManagerSnapshot | None = None
            self._theme: pal.Theme = pal.MIDNIGHT_EMERALD
            self._competition_names: dict[int, str] = {}
            self._roundels: dict[str | None, pal.Roundel] = {}
            self._rows: list[HubRow] = []
            self._empty_text = "No save loaded."
            self.season: fd.HubSeason | None = None
            self.index = 0
            self._slider_job: str | None = None
            self._build_ui()

        def _build_ui(self) -> None:
            self.grid_columnconfigure(0, weight=1)
            top = ctk.CTkFrame(self, fg_color="transparent")
            top.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
            self.club_badge = roundel_ui.RoundelBadge(top, self.CLUB_ROUNDEL)
            self.club_badge.pack(side="left", padx=(0, 10))
            self._header = ctk.CTkLabel(top, text="Club overview", font=("Segoe UI", 13, "bold"), anchor="w")
            self._header.pack(side="left")

            self.stepper = ctk.CTkFrame(self, fg_color="transparent")
            self.stepper.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 4))
            self.stepper.grid_columnconfigure(1, weight=1)
            self.previous_button = ctk.CTkButton(self.stepper, text="‹ Previous", width=90,
                                                 command=lambda: self.show_step(self.index - 1))
            self.previous_button.grid(row=0, column=0, padx=(0, 6))
            self.slider = ctk.CTkSlider(self.stepper, from_=0, to=1, command=self._on_slider)
            self.slider.grid(row=0, column=1, sticky="ew", padx=6)
            self.next_button = ctk.CTkButton(self.stepper, text="Next ›", width=90,
                                             command=lambda: self.show_step(self.index + 1))
            self.next_button.grid(row=0, column=2, padx=6)
            self.today_button = ctk.CTkButton(self.stepper, text="Today", width=70, command=self.show_today)
            self.today_button.grid(row=0, column=3, padx=(6, 0))
            self.step_label = ctk.CTkLabel(self.stepper, text="", anchor="w", font=("Segoe UI", 10))
            self.step_label.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 0))
            self.stepper.grid_remove()

            self._content = ctk.CTkFrame(self, fg_color="transparent")
            self._content.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
            self._content.grid_columnconfigure(2, weight=1)
            self.excerpt = ctk.CTkFrame(self, fg_color="transparent")
            self.excerpt.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 10))
            self.next_badge = roundel_ui.RoundelBadge(self, self.NEXT_ROUNDEL)

        # ---- public API (call on main thread only) ---------------------

        def install_snapshot(self, snapshot: fd.ManagerSnapshot, theme: pal.Theme,
                              competition_names: dict[int, str] | None = None,
                              roundels: dict[str | None, pal.Roundel] | None = None,
                              season: fd.HubSeason | None = None) -> None:
            """Show a snapshot, and the stepper at the save's own date when `season` has steps. `roundels` maps
            club names to their roundels in this theme (palette.roundel_book); both were worked out off the main
            thread."""
            self._snapshot = snapshot
            self._theme = theme
            self._competition_names = competition_names or {}
            self._roundels = roundels or {}
            self._cancel_slider()
            self.season = season if season is not None and season.steps else None
            if self.season is None:
                self.stepper.grid_remove()
                self._rows = hub_rows(snapshot, self._competition_names)
                self._repaint()
                return
            count = len(self.season.steps)
            self.slider.configure(from_=0, to=max(count - 1, 1), number_of_steps=max(count - 1, 1),
                                  state="normal" if count > 1 else "disabled")
            self.stepper.grid()
            self.show_step(self.season.today if self.season.today is not None else 0)

        def clear(self, text: str) -> None:
            self._snapshot = None
            self._rows = []
            self._empty_text = text
            self._cancel_slider()
            self.season = None
            self.stepper.grid_remove()
            self._repaint()

        def set_theme(self, theme: pal.Theme, roundels: dict[str | None, pal.Roundel] | None = None) -> None:
            self._theme = theme
            if roundels is not None:
                self._roundels = roundels
            self._repaint()

        # ---- the stepper -----------------------------------------------

        def show_step(self, index: int) -> None:
            """Show one step of the season: its snapshot was worked out in advance, so this only picks it."""
            if self.season is None or self._snapshot is None:
                return
            steps = self.season.steps
            self.index = max(0, min(index, len(steps) - 1))
            step = steps[self.index]
            today = self.index == self.season.today
            self._rows = hub_rows(self._snapshot, self._competition_names, step=step, today=today,
                                  league=self.season.league_id is not None)
            text = step.label
            if today:
                text += " (the save's date)"
            elif self.season.today is None:
                text += " · The save's date is unknown, so Today is unavailable"
            if self.season.undated:
                text += f" · {self.season.undated} undated match{'es' if self.season.undated != 1 else ''} " \
                        "not on the stepper"
            self.step_label.configure(text=text)
            self.slider.set(self.index)
            self.previous_button.configure(state="normal" if self.index > 0 else "disabled")
            self.next_button.configure(state="normal" if self.index < len(steps) - 1 else "disabled")
            self.today_button.configure(state="normal" if self.season.today is not None else "disabled")
            self._repaint()

        def show_today(self) -> None:
            if self.season is not None and self.season.today is not None:
                self.show_step(self.season.today)

        def _on_slider(self, value: float) -> None:
            self._cancel_slider()
            self._slider_job = self.after(self.DEBOUNCE_MS, self._settle_slider)

        def _settle_slider(self) -> None:
            self._slider_job = None
            index = round(self.slider.get())
            if index != self.index:
                self.show_step(index)

        def _cancel_slider(self) -> None:
            if self._slider_job is not None:
                self.after_cancel(self._slider_job)
                self._slider_job = None

        def destroy(self) -> None:
            self._cancel_slider()
            super().destroy()

        def excerpt_rows(self) -> list[tuple]:
            """The table excerpt shown: (position, team, played, goal difference, points, the followed club)."""
            step = self._step()
            if step is None or step.table is None or step.table.played == 0:
                return []
            return [(r.position, r.team, r.played, r.goal_difference, r.points, r.club) for r in step.table.excerpt]

        def _step(self) -> fd.HubStep | None:
            return self.season.steps[self.index] if self.season is not None else None

        # ---- internal rendering ----------------------------------------

        def _repaint(self) -> None:
            for w in (*self._content.winfo_children(), *self.excerpt.winfo_children()):
                w.destroy()
            theme = self._theme
            snap = self._snapshot
            step = self._step()
            self._header.configure(text=snap.followed.name if snap is not None else "Club overview",
                                   text_color=theme.text)
            self.step_label.configure(text_color=theme.muted)
            for button in (self.previous_button, self.next_button, self.today_button):
                button.configure(fg_color=theme.accent[0], hover_color=theme.accent_hover, text_color=theme.accent[1])
            self.slider.configure(button_color=theme.accent[0], button_hover_color=theme.accent_hover,
                                  progress_color=theme.accent[0])
            self.club_badge.show(self._roundels.get(snap.followed.name) if snap is not None else None, theme.window)
            if step is not None:
                next_item = step.fixture
            else:
                next_item = snap.next_item if snap is not None else None
            self.next_badge.grid_forget()
            self.next_badge.show(self._roundels.get(next_item.opponent_club) if next_item is not None else None,
                                 theme.window)
            if not self._rows:
                ctk.CTkLabel(self._content, text=self._empty_text, anchor="w").grid(
                    row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=4)
                return
            badge_row = next((i for i, row in enumerate(self._rows) if row.label in self.NEXT_LABELS), None)
            for i, row in enumerate(self._rows):
                label_fg = theme.muted if row.muted else theme.table[1]
                if row.label:
                    ctk.CTkLabel(self._content, text=row.label, width=self.LABEL_WIDTH, anchor="w",
                                 text_color=theme.muted, font=("Segoe UI", 9)).grid(
                        row=i, column=0, sticky="w", padx=(8, 4), pady=1)
                ctk.CTkLabel(self._content, text=row.value, anchor="w", justify="left", text_color=label_fg,
                             font=("Segoe UI", 9, "bold" if not row.muted and row.label else "normal")).grid(
                    row=i, column=2, sticky="ew", padx=(0, 8), pady=1)
                if i == badge_row and self.next_badge.roundel is not None:
                    self.next_badge.tk.call("raise", self.next_badge._w)     # Canvas.lift raises items
                    self.next_badge.grid(in_=self._content, row=i, column=1, padx=(0, 6))
            self._paint_excerpt(theme)

        def _paint_excerpt(self, theme: pal.Theme) -> None:
            rows = self.excerpt_rows()
            if not rows:
                return
            self.excerpt.grid_columnconfigure(0, weight=1)
            lines = [(("#", "Team", "P", "GD", "Pts"), "transparent", theme.muted, True)]
            for pos, team, played, gd, pts, club in rows:
                bg, fg = theme.focus if club else (theme.table[0], theme.table[1])
                lines.append(((pos, team, played, f"{gd:+d}" if gd else "0", pts), bg, fg, club))
            for r, (values, bg, fg, bold) in enumerate(lines):
                band = ctk.CTkFrame(self.excerpt, fg_color=bg, corner_radius=0, height=22)
                band.grid(row=r, column=0, sticky="ew")
                band.grid_columnconfigure(1, weight=1)
                for c, value in enumerate(values):
                    ctk.CTkLabel(band, text=str(value), text_color=fg, width=self.EXCERPT_WIDTHS[c], height=22,
                                 font=("Segoe UI", 9, "bold" if bold else "normal"),
                                 anchor="w" if c == 1 else "e").grid(row=0, column=c, sticky="ew",
                                                                     padx=(10 if c == 1 else 0, 8 if c else 4))
