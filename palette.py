# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Box2Box's colours, shared by the window and the exports so that both look the same.

Each entry is a (background, text) pair of hex colours; None means "leave as it is". A Theme holds
every colour under one name; Midnight Emerald is the original look, and the module constants below
are its own. No UI code here, so the exports can use it without loading a window toolkit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import fm_data as fd

WIN_BG = "#059669"       # emerald
DRAW_BG = "#d97706"      # warm amber
LOSS_BG = "#dc2626"      # crimson
MIXED_BG = "#2563eb"     # electric blue
NA_COLOURS = ("#4c1d95", "#e9d5ff")   # purple: played, but the save holds no score

# Result kinds (fm_data) and a followed team's W/D/L/? results.
COLOURS: dict[str, tuple[str | None, str | None]] = {
    fd.HOME_WIN: (WIN_BG, "#ffffff"),
    fd.DRAW: (DRAW_BG, "#ffffff"),
    fd.AWAY_WIN: (LOSS_BG, "#ffffff"),
    fd.UNAVAILABLE: NA_COLOURS,
    fd.MIXED: (MIXED_BG, "#ffffff"),
    fd.SCHEDULED: ("#182230", "#94a3b8"),
    "self": ("#0a0f18", None),
    "W": (WIN_BG, "#ffffff"),
    "D": (DRAW_BG, "#ffffff"),
    "L": (LOSS_BG, "#ffffff"),
    "?": NA_COLOURS,
}

ZONE_COLOURS: dict[str, tuple[str, str]] = {
    fd.ZONE_UCL: ("#1d4ed8", "#ffffff"),
    fd.ZONE_PROMOTION: ("#059669", "#ffffff"),
    fd.ZONE_PLAYOFF: ("#0284c7", "#ffffff"),
    fd.ZONE_EUROPA: ("#ea580c", "#ffffff"),
    fd.ZONE_RELEGATION: ("#dc2626", "#ffffff"),
}

# How a legend names each zone colour, in table order: (zone, colour word, meaning).
ZONE_LEGEND = (
    (fd.ZONE_PROMOTION, "green", "promotion"),
    (fd.ZONE_UCL, "blue", "Champions League"),
    (fd.ZONE_EUROPA, "orange", "Europa League"),
    (fd.ZONE_PLAYOFF, "cyan", "play-offs"),
    (fd.ZONE_RELEGATION, "red", "relegation"),
)

HEADING = ("#111e2e", "#38bdf8")     # group headings: weeks, rounds, tables
FOCUS = ("#1e40af", "#ffffff")       # the followed team


def zone_legend(zones: set[str]) -> str:
    """'green = promotion · cyan = play-offs · red = relegation' for the zones shown, or ''."""
    return " · ".join(f"{colour} = {meaning}" for zone, colour, meaning in ZONE_LEGEND if zone in zones)


# --------------------------------------------------------------------------- themes


@dataclass(frozen=True, slots=True)
class Theme:
    """Every colour the window and the exports use, under one name. Pairs are (background, text)
    unless said otherwise."""

    name: str
    # Surfaces and text
    window: str                       # behind everything
    panel: str                        # the top bar, the competitions panel and the status bar
    table: tuple[str, str]            # the sheets' cells
    sheet_heading: tuple[str, str]    # the sheets' column headings and row labels
    grid_line: str
    selection: tuple[str, str]        # a selected cell or row: (fill, border)
    text: str                         # labels and controls
    muted: str                        # secondary labels: hints, notes, the status bar
    competition_list: tuple[str, str]
    list_selected: tuple[str, str]
    section: str                      # the competition list's headings
    link: str                         # the followed team's name in Results
    warning: str                      # the unverified-build warning
    # Controls
    accent: tuple[str, str]           # buttons, the season menu, the progress bar: (colour, text)
    accent_hover: str
    quiet: tuple[str, str]            # the grey buttons: About, Name this competition…, details
    quiet_hover: str
    field: tuple[str, str]            # the search box and the team box: (fill, border)
    switch: tuple[str, str]           # segmented switches: (track and unselected segments, text)
    switch_hover: str
    switch_selected: str
    switch_selected_hover: str
    # Content, shared with the exports
    colours: Mapping[str, tuple[str | None, str | None]]
    zones: Mapping[str, tuple[str, str]]
    heading: tuple[str, str]          # group headings: weeks, rounds, tables
    focus: tuple[str, str]            # the followed team
    categories: Mapping[str, tuple[str, str]]   # the Competitions hub's category cells
    yours_row: tuple[str, str]        # the hub's rows for your club's competitions
    page_muted: str                   # the web page export's grey text
    page_field: tuple[str, str]       # the web page export's search box: (fill, border)
    club_colours: bool = True         # whether the followed club's colours may tint the window


# The original look: CustomTkinter's dark "blue" controls and the colours above.
MIDNIGHT_EMERALD = Theme(
    name="Midnight Emerald",
    window="#242424", panel="#2b2b2b", table=("#1b1b1b", "#E3E3E3"), sheet_heading=("#151515", "#94EBEB"),
    grid_line="#2b2b2b", selection=("#404040", "#94EBEB"), text="#DCE4EE", muted="#b3b3b3",
    competition_list=("#1d1d1d", "#e3e3e3"), list_selected=("#1f538d", "#ffffff"), section="#d8b44a",
    link="#60a5fa", warning="#fb923c",
    accent=("#1F6AA5", "#DCE4EE"), accent_hover="#144870", quiet=("#4d4d4d", "#DCE4EE"), quiet_hover="#595959",
    field=("#343638", "#565B5E"), switch=("#4a4a4a", "#DCE4EE"), switch_hover="#696969",
    switch_selected="#1F6AA5", switch_selected_hover="#144870",
    colours=COLOURS, zones=ZONE_COLOURS, heading=HEADING, focus=FOCUS,
    categories={
        fd.COMP_CAT_YOURS: ("#1e3a8a", "#dbeafe"),
        fd.COMP_CAT_CUP: ("#312e81", "#e0e7ff"),
        fd.COMP_CAT_YOUTH: ("#1f2937", "#9ca3af"),
        fd.COMP_CAT_LEAGUE: ("#064e3b", "#a7f3d0"),
    },
    yours_row=("#132338", "#93c5fd"),
    page_muted="#a3a3a3", page_field=("#262626", "#3f3f3f"),
)

THEMES: tuple[Theme, ...] = (MIDNIGHT_EMERALD,)


def theme_by_name(name: object) -> Theme:
    """The theme of that name; Midnight Emerald for a missing, unknown or odd one."""
    return next((theme for theme in THEMES if isinstance(name, str) and theme.name == name), MIDNIGHT_EMERALD)


# --------------------------------------------------------------------------- readability


def luminance(colour: str) -> float:
    """WCAG 2 relative luminance of a '#rrggbb' colour: 0 for black, 1 for white."""
    def linear(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    red, green, blue = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG 2 contrast ratio of two colours, from 1 (none) to 21 (black on white). Text needs 4.5."""
    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)
