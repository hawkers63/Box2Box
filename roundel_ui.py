# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Draws a club's procedural roundel (palette.Roundel) on a Tk canvas: a ring in the club's second colour, a disc
in its main colour and its initials. An identity aid only, never a crest. The colours are worked out in palette;
this module only draws them.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence

import palette

FONT = "Segoe UI"
DISC = 0.64                 # the disc's share of the roundel's width
MIN_INITIALS = 18           # smaller than this the initials would not fit the disc, so none are drawn


def draw_roundel(canvas: tk.Canvas, cx: float, cy: float, diameter: int, roundel: palette.Roundel,
                 tags: Sequence[str] = (), n: int | str = "") -> None:
    """The roundel centred on (cx, cy). Its items carry `tags` plus ring_{n}, disc_{n} and initials_{n}."""
    r, d = diameter / 2, diameter * DISC / 2
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=roundel.ring, outline=roundel.rim, width=1,
                       tags=(*tags, f"ring_{n}"))
    canvas.create_oval(cx - d, cy - d, cx + d, cy + d, fill=roundel.disc, outline="", tags=(*tags, f"disc_{n}"))
    if roundel.initials and diameter >= MIN_INITIALS:
        canvas.create_text(cx, cy, text=roundel.initials, fill=roundel.text,
                           font=(FONT, -max(7, round(diameter * 0.27)), "bold"), tags=(*tags, f"initials_{n}"))


class RoundelBadge(tk.Canvas):
    """One roundel as a widget, for a header or a card. show(None) leaves it empty."""

    def __init__(self, master: tk.Misc, diameter: int, background: str = "#000000") -> None:
        super().__init__(master, width=diameter + 2, height=diameter + 2, highlightthickness=0, bd=0, bg=background)
        self.diameter = diameter
        self.roundel: palette.Roundel | None = None

    def show(self, roundel: palette.Roundel | None, background: str) -> None:
        self.roundel = roundel
        self.configure(bg=background)
        self.delete("all")
        if roundel is not None:
            middle = self.diameter / 2 + 1
            draw_roundel(self, middle, middle, self.diameter, roundel, ("roundel",))
