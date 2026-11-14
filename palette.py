"""Box2Box's colours, shared by the window and the exports so that both look the same.

Each entry is a (background, text) pair of hex colours; None means "leave as it is".
No UI code here, so the exports can use it without loading a window toolkit.
"""

from __future__ import annotations

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
