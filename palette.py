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

# A cooler night pitch: near-black surfaces, electric cyan, the same result colours.
CYBER_PITCH = Theme(
    name="Cyber Pitch",
    window="#05080d", panel="#0a1018", table=("#070b11", "#e2f3ff"), sheet_heading=("#0b1622", "#67e8f9"),
    grid_line="#13202d", selection=("#0e3a4a", "#22d3ee"), text="#d6f3ff", muted="#8aa4b8",
    competition_list=("#080d14", "#d6f3ff"), list_selected=("#0e7490", "#ffffff"), section="#22d3ee",
    link="#22d3ee", warning="#fb923c",
    accent=("#0e7490", "#ffffff"), accent_hover="#155e75", quiet=("#16222f", "#d6f3ff"), quiet_hover="#1f3142",
    field=("#0c141e", "#1f3a4d"), switch=("#111c28", "#d6f3ff"), switch_hover="#1b2a3a",
    switch_selected="#0e7490", switch_selected_hover="#155e75",
    colours={**COLOURS, fd.SCHEDULED: ("#0c1520", "#7d93a8"), "self": ("#03060a", None)},
    zones=ZONE_COLOURS, heading=("#062330", "#22d3ee"), focus=("#0b4f61", "#ecfeff"),
    categories={
        fd.COMP_CAT_YOURS: ("#0c3b4d", "#cffafe"),
        fd.COMP_CAT_CUP: ("#2a2560", "#e0e7ff"),
        fd.COMP_CAT_YOUTH: ("#141c26", "#94a3b8"),
        fd.COMP_CAT_LEAGUE: ("#053d33", "#a7f3d0"),
    },
    yours_row=("#08202b", "#67e8f9"),
    page_muted="#8aa4b8", page_field=("#0c141e", "#1f3a4d"),
)

# Broadcast slate: slate surfaces, gold headings and controls, the same result colours.
DEEP_SLATE_GOLD = Theme(
    name="Deep Slate & Gold",
    window="#0b1220", panel="#141d2e", table=("#101826", "#e2e8f0"), sheet_heading=("#0c1422", "#d8b44a"),
    grid_line="#1f2a3c", selection=("#2a3550", "#d8b44a"), text="#e2e8f0", muted="#94a3b8",
    competition_list=("#0f1727", "#e2e8f0"), list_selected=("#7a5f14", "#ffffff"), section="#d8b44a",
    link="#e7c66b", warning="#fb923c",
    accent=("#d8b44a", "#1a1405"), accent_hover="#c29d36", quiet=("#24324a", "#e2e8f0"), quiet_hover="#2e3e5a",
    field=("#0f1726", "#33415a"), switch=("#1e293b", "#e2e8f0"), switch_hover="#2b3a52",
    switch_selected="#7a5f14", switch_selected_hover="#8c6d18",
    colours={**COLOURS, fd.SCHEDULED: ("#1a2436", "#94a3b8"), "self": ("#0a101b", None)},
    zones=ZONE_COLOURS, heading=("#1b2537", "#d8b44a"), focus=("#5a4712", "#fff7dc"),
    categories={
        fd.COMP_CAT_YOURS: ("#4a3a10", "#fde68a"),
        fd.COMP_CAT_CUP: ("#2e2a5c", "#e0e7ff"),
        fd.COMP_CAT_YOUTH: ("#1c2433", "#9ca3af"),
        fd.COMP_CAT_LEAGUE: ("#073b30", "#a7f3d0"),
    },
    yours_row=("#1d2533", "#e7c66b"),
    page_muted="#94a3b8", page_field=("#0f1726", "#33415a"),
)

# White on black with yellow accents. Result, zone and category colours are a step lighter with black
# text, so every coloured cell reads at 4.5:1 or better; club colours are left out.
_HC_WIN, _HC_DRAW, _HC_LOSS, _HC_NA = ("#34d399", "#000000"), ("#fbbf24", "#000000"), ("#f87171", "#000000"), \
    ("#c4b5fd", "#000000")
HIGH_CONTRAST = Theme(
    name="High-Contrast",
    window="#000000", panel="#000000", table=("#000000", "#ffffff"), sheet_heading=("#1a1a1a", "#ffff00"),
    grid_line="#808080", selection=("#003a70", "#00ffff"), text="#ffffff", muted="#e0e0e0",
    competition_list=("#000000", "#ffffff"), list_selected=("#ffff00", "#000000"), section="#ffff00",
    link="#7dd3fc", warning="#ffb000",
    accent=("#ffff00", "#000000"), accent_hover="#e0e000", quiet=("#ffffff", "#000000"), quiet_hover="#d9d9d9",
    field=("#000000", "#ffffff"), switch=("#d9d9d9", "#000000"), switch_hover="#bfbfbf",
    switch_selected="#ffff00", switch_selected_hover="#e0e000",
    colours={
        fd.HOME_WIN: _HC_WIN, fd.DRAW: _HC_DRAW, fd.AWAY_WIN: _HC_LOSS, fd.UNAVAILABLE: _HC_NA,
        fd.MIXED: ("#60a5fa", "#000000"), fd.SCHEDULED: ("#262626", "#ffffff"), "self": ("#404040", None),
        "W": _HC_WIN, "D": _HC_DRAW, "L": _HC_LOSS, "?": _HC_NA,
    },
    zones={
        fd.ZONE_UCL: ("#93c5fd", "#000000"),
        fd.ZONE_PROMOTION: ("#34d399", "#000000"),
        fd.ZONE_PLAYOFF: ("#67e8f9", "#000000"),
        fd.ZONE_EUROPA: ("#fdba74", "#000000"),
        fd.ZONE_RELEGATION: ("#f87171", "#000000"),
    },
    heading=("#262626", "#ffff00"), focus=("#ffffff", "#000000"),
    categories={
        fd.COMP_CAT_YOURS: ("#ffff00", "#000000"),
        fd.COMP_CAT_CUP: ("#c4b5fd", "#000000"),
        fd.COMP_CAT_YOUTH: ("#404040", "#ffffff"),
        fd.COMP_CAT_LEAGUE: ("#34d399", "#000000"),
    },
    yours_row=("#000000", "#ffff00"),
    page_muted="#e0e0e0", page_field=("#000000", "#ffffff"),
    club_colours=False,
)

THEMES: tuple[Theme, ...] = (MIDNIGHT_EMERALD, CYBER_PITCH, DEEP_SLATE_GOLD, HIGH_CONTRAST)


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
