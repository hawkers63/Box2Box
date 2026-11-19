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

# ---------------------------------------------------------------------------
# Pure model

class HubRow(NamedTuple):
    """A single display row for the manager hub."""
    label: str
    value: str
    muted: bool = False


def hub_rows(snapshot: fd.ManagerSnapshot, competition_names: dict[int, str] | None = None) -> list[HubRow]:
    """Return ordered display rows from a ManagerSnapshot.

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

    # League position
    if snapshot.rank_before_next is not None:
        rb = snapshot.rank_before_next
        pos_text = f"{rb.rank}"
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
        """Club overview panel driven by ManagerSnapshot.

        Call install_snapshot(snapshot, theme, competition_names) from the
        main thread to show a new snapshot.  Stale worker results must not
        call this after a new save has been opened: the caller guards the
        sequence number.
        """

        ROW_HEIGHT = 28
        LABEL_WIDTH = 110

        def __init__(self, master, **kw):
            super().__init__(master, **kw)
            self._snapshot: fd.ManagerSnapshot | None = None
            self._theme: pal.Theme = pal.MIDNIGHT_EMERALD
            self._competition_names: dict[int, str] = {}
            self._rows: list[HubRow] = []
            self._widgets: list[tuple] = []
            self._build_ui()

        def _build_ui(self) -> None:
            self.grid_columnconfigure(0, weight=1)
            self._header = ctk.CTkLabel(self, text="Club overview",
                                        font=("Segoe UI", 13, "bold"), anchor="w")
            self._header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
            self._content = ctk.CTkFrame(self, fg_color="transparent")
            self._content.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
            self._content.grid_columnconfigure(1, weight=1)

        # ---- public API (call on main thread only) ---------------------

        def install_snapshot(self, snapshot: fd.ManagerSnapshot, theme: pal.Theme,
                              competition_names: dict[int, str] | None = None) -> None:
            self._snapshot = snapshot
            self._theme = theme
            self._competition_names = competition_names or {}
            self._rows = hub_rows(snapshot, self._competition_names)
            self._repaint()

        def set_theme(self, theme: pal.Theme) -> None:
            self._theme = theme
            self._repaint()

        # ---- internal rendering ----------------------------------------

        def _repaint(self) -> None:
            for w in self._content.winfo_children():
                w.destroy()
            if not self._rows:
                ctk.CTkLabel(self._content, text="No save loaded.", anchor="w").grid(
                    row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=4)
                return
            theme = self._theme
            for i, row in enumerate(self._rows):
                label_fg = theme.muted if row.muted else theme.table[1]
                if row.label:
                    lbl = ctk.CTkLabel(self._content, text=row.label,
                                       width=self.LABEL_WIDTH, anchor="w",
                                       text_color=theme.muted,
                                       font=("Segoe UI", 9))
                    lbl.grid(row=i, column=0, sticky="w", padx=(8, 4), pady=1)
                val = ctk.CTkLabel(self._content, text=row.value,
                                   anchor="w", text_color=label_fg,
                                   font=("Segoe UI", 9, "bold" if not row.muted and row.label else "normal"))
                val.grid(row=i, column=1, sticky="ew", padx=(0, 8), pady=1)
