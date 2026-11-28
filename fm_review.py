# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Box2Box: browse the fixtures, results, grids, and league tables in a Football Manager 26/27 save.

Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.

    .venv\\Scripts\\python fm_review.py ["path\\to\\save.fm"]

The save is read by fmsave and never changed. Reading one takes around half a minute, on a
background thread, so the window stays responsive.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import re
import sqlite3
import sys
import threading
import time
import tkinter as tk
import traceback
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox
from tkinter import font as tkfont
from typing import NamedTuple

import customtkinter as ctk
from tksheet import Sheet, rounded_box_coords

try:        # an optional extra: without it, a save cannot be dropped onto the window, and nothing else changes
    from tkinterdnd2 import COPY, DND_FILES, REFUSE_DROP, TkinterDnD
except ImportError:
    COPY, DND_FILES, REFUSE_DROP, TkinterDnD = "copy", "DND_Files", "refuse_drop", None

import archive
import bracket
import clipboard
import club_colours
import command_palette
import fm_data as fd
import fm_export as fx
import inspector
import palette
import tooltip
import yearbook
import yearbook_editions
import yearbook_pdf
import yearbook_read
from yearbook_reader_ui import YearbookReader
import fm_manager_hub as fmh
import fm_schedule_view as fsv

APP_TITLE = "Box2Box"
VERSION = "2.15"


def _resolve_app_dir(*, frozen: bool, executable: Path, source: Path) -> Path:
    """Where Box2Box reads and writes its own files (settings, error log, archive, competition names).

    In a frozen PyInstaller build, `__file__` points to the extracted `_internal` cache rather
    than the installation folder, so we read `sys.executable` instead — the `.exe` beside which
    settings and the log must live.
    """
    return executable.resolve().parent if frozen else source.resolve().parent


def _resolve_bundle_dir(*, frozen: bool, meipass: str | None, source: Path) -> Path:
    """Where the read-only data bundled with the app (the icon, LICENSE, fonts) lives. PyInstaller unpacks it to
    `sys._MEIPASS` (the `_internal` folder of a one-folder build, a temporary folder for a one-file build), which is
    not where the app's own writable files go."""
    return Path(meipass) if frozen and meipass else source.resolve().parent


APP_DIR = _resolve_app_dir(
    frozen=getattr(sys, "frozen", False),
    executable=Path(sys.executable),
    source=Path(__file__),
)
BUNDLE_DIR = _resolve_bundle_dir(
    frozen=getattr(sys, "frozen", False),
    meipass=getattr(sys, "_MEIPASS", None),
    source=Path(__file__),
)
NAMES_PATH = APP_DIR / "competition_names.csv"
SETTINGS_PATH = APP_DIR / "box2box_settings.json"
LEGACY_SETTINGS_PATH = APP_DIR / "fm_review_settings.json"
ERROR_LOG = APP_DIR / "box2box_errors.log"
ARCHIVE_PATH = APP_DIR / "box2box_archive.sqlite"
HISTORY_LINES = 10          # seasons listed in the club inspector's History block
BOOKMARKS = "yearbook_bookmarks"          # the settings key for the reading window's bookmarks
READER_MODE = "yearbook_reader_mode"      # single pages or reader spreads        # every opened save is banked here (archive.py)
SCHEDULE_GAPS = "schedule_fixture_gap"       # the settings key for the Schedule's Fixture gap option
LICENCE_PATH = BUNDLE_DIR / "LICENSE"
ICON_PATH = BUNDLE_DIR / "icon" / "football-64-sky-blue.ico"
APP_ID = "hawkers63.Box2Box"         # the taskbar's name for Box2Box, so it shows its own icon

# Word for word the first line of LICENSE.
COPYRIGHT = "Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved."
REPOSITORY = "https://github.com/hawkers63/Box2Box"

ALL_TEAMS = "All teams"
EXPORT_LABEL = "Export ▾"
WHOLE_SAVE_LABEL = "Whole save workbook (.xlsx)"
COUNTRY_NAMES = "country_names"       # settings key: {nation database id as text: the user's name for it}
HUB = "Competitions"
ANALYSIS = "Analysis"
SCHEDULE = "Schedule"
MANAGER_HUB = "Hub"
VIEWS = ("Results", "Grid", "Table", ANALYSIS, SCHEDULE, MANAGER_HUB, HUB)
SWITCH_VIEWS = tuple(v for v in VIEWS if v not in (SCHEDULE, MANAGER_HUB))   # club views have header buttons
NO_CLUB_FOLLOWED = "No club followed: follow one from a right-click, the palette or Theme ▾ → Follow club…"
ANALYSES = ("Form", "Positions", "xG", "Ties", "Bracket")
POSITIONS_MODES = ("Matchday chart", "Season vs season")
GROUPINGS = (fd.GROUP_BY_WEEK, fd.GROUP_BY_MATCHDAY, fd.GROUP_BY_DATE)
MAX_TEAM_CHOICES = 120
RESULTS_XG_COLUMN = 4
GD_COLUMN, FORM_COLUMN = 8, 10            # in the Table view
SPARK_ROW_LIMIT = 100                      # a Table longer than this skips the place sparks: they cost a full replay
RUN_LETTERS = {fd.STREAK_WINNING: "W", fd.STREAK_UNBEATEN: "U", fd.STREAK_WINLESS: "N", fd.STREAK_LOSING: "L"}
RUN_NAMED_FROM = 3                        # the Table tab names a followed team's run once it is this long
CLUB_OPEN_PRIORITY = 10_000                 # the palette ranks the open competition's own teams first,
CLUB_LEAGUE_PRIORITY = 1_000                # then a club's leagues, then its cups, each by prominence
MIN_WINDOW_WIDTH = 1050                   # line 1 of the controls (season, team, view switch) fits in this (px at 100%);
#                                           the view's own switch wraps to line 2. Capped at the screen
CONTROLS_SPARE = 8                        # the controls unwrap only with this many px to spare, so they never flicker
DROP_NOTE_MS = 8000                       # a refused drop's reason stays this long on the detail line
COUNTS_MIN_WIDTH = 1540                   # the switch shows counts only in a window at least this wide (px at 100%);
#                                           the controls need 1532 with the longest counts, as a test measures

FONT = "Segoe UI"
THEME_LABEL = "Theme ▾"
DROP_HINT = "Drop a .fm save to open it"

# Every colour belongs to a theme in palette.py, shared with the exports.

GRID_LEGEND = ("Rows are home teams, columns away teams. Green: home win · amber: draw · "
               "red: away win · blue: mixed results · n/a: score unrecovered · grey date: still to play. "
               "Click a cell for details, a team name to follow that team.")


def documents_folder() -> Path:
    if sys.platform == "win32":
        buffer = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0 and buffer.value:
            return Path(buffer.value)
    return Path.home() / "Documents"


def export_folder() -> Path:
    """Where exports are saved: Documents\\Box2Box."""
    return documents_folder() / APP_TITLE


def apply_window_icon(window: tk.Wm) -> bool:
    """Give a window the Box2Box icon. A missing or unreadable icon leaves Windows' own, quietly."""
    if not ICON_PATH.is_file():
        return False
    try:
        window.iconbitmap(str(ICON_PATH))
    except tk.TclError:
        return False
    return True


def set_taskbar_identity() -> bool:
    """Tell Windows this process is Box2Box rather than Python, so that its taskbar button shows the
    window's own icon. True when Windows accepted it."""
    if sys.platform != "win32":
        return False
    try:
        return ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID) == 0
    except (AttributeError, OSError):
        return False


def default_save_folder() -> Path:
    documents = documents_folder()
    for name in ("Football Manager 27", "Football Manager 2027", "Football Manager 26", "Football Manager 2026"):
        games = documents / "Sports Interactive" / name / "games"
        if games.is_dir():
            return games
    return documents


def accept_dropped_save(paths: Sequence[str]) -> tuple[Path | None, str]:
    """The save to open from what was dropped onto the window, with an empty reason; or None and why
    not. Exactly one existing file ending in .fm (in any case) is a save."""
    if not paths:
        return None, "Drop one .fm save to open it."
    if len(paths) > 1:
        return None, "Drop one .fm save at a time."
    path = Path(paths[0])
    if path.is_dir():
        return None, f"{path.name} is a folder, not a .fm save."
    if path.suffix.lower() != ".fm":
        return None, f"{path.name} is not a .fm save."
    if not path.is_file():
        return None, f"{path.name} could not be found."
    return path, ""


# ----------------------------------------------------------------- About

class AboutText(NamedTuple):
    """What the About window says, from the top down."""

    name: str
    version: str
    summary: str
    copyright: str
    notice: str


def about_text() -> AboutText:
    return AboutText(
        name=APP_TITLE,
        version=f"Version {VERSION}",
        summary="A Windows desktop viewer for the fixtures, results, grids and league tables in a Football "
                "Manager 27 (or 26) save. Saves are read with fmsave and are never modified.",
        copyright=COPYRIGHT,
        notice=f"{APP_TITLE} is proprietary software. Copying, distribution, modification, reverse engineering, "
               "sublicencing and commercial exploitation are prohibited without prior written consent. "
               "See LICENSE, below, for the full terms.",
    )


def licence_text(path: Path) -> str:
    """The licence's terms with each paragraph on one line, so that a text box can wrap them to its
    own width; or, if the file cannot be read, where else the terms can be found."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:            # missing, locked, or not text
        problem = "was not found" if isinstance(exc, FileNotFoundError) else "could not be read"
        return f"The LICENSE file {problem} in {path.parent}. The full terms are published at {REPOSITORY}."
    return "\n\n".join(" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip())


class AboutWindow(ctk.CTkToplevel):
    """The name, version, copyright and licence: a band in the theme's heading colours over a
    stripe of the win, draw and loss colours."""

    WIDTH, HEIGHT = 600, 600
    PAD = 28

    def __init__(self, master: ctk.CTk) -> None:
        super().__init__(master)
        apply_window_icon(self)
        text = about_text()
        self.title(f"About {APP_TITLE}")
        self.transient(master)

        self.band = ctk.CTkFrame(self, corner_radius=0)
        self.band.pack(fill="x")
        self.name_label = ctk.CTkLabel(self.band, text=text.name, font=ctk.CTkFont(FONT, 28, "bold"), anchor="w")
        self.name_label.pack(fill="x", padx=self.PAD, pady=(18, 0))
        self.version_label = ctk.CTkLabel(self.band, text=text.version, font=ctk.CTkFont(FONT, 13), anchor="w")
        self.version_label.pack(fill="x", padx=self.PAD, pady=(0, 16))
        stripe = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0, height=6)
        stripe.pack(fill="x")
        self.stripes = []
        for _ in "WDL":
            part = ctk.CTkFrame(stripe, corner_radius=0, width=1, height=6)
            part.pack(side="left", fill="x", expand=True)
            self.stripes.append(part)

        # Packed before the body so that a short screen squeezes the licence box, not the button.
        self.close_button = ctk.CTkButton(self, text="Close", width=100, command=self.destroy)
        self.close_button.pack(side="bottom", anchor="e", padx=self.PAD, pady=16)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=self.PAD, pady=(18, 0))
        self.body_labels = []
        for line, size, weight in ((text.summary, 13, "normal"), (text.copyright, 13, "bold"),
                                   (text.notice, 12, "normal")):
            label = ctk.CTkLabel(body, text=line, font=ctk.CTkFont(FONT, size, weight),
                                 wraplength=self.WIDTH - 2 * self.PAD, justify="left", anchor="w")
            label.pack(fill="x", pady=(0, 12))
            self.body_labels.append(label)
        self.licence_label = ctk.CTkLabel(body, text="LICENSE", font=ctk.CTkFont(FONT, 11, "bold"), anchor="w")
        self.licence_label.pack(fill="x")
        self.licence_box = ctk.CTkTextbox(body, wrap="word", height=120, font=ctk.CTkFont(FONT, 12))
        self.licence_box.pack(fill="both", expand=True, pady=(4, 0))
        self.licence_box.insert("1.0", licence_text(LICENCE_PATH))
        self.licence_box.configure(state="disabled")
        self.apply_theme(master.theme)

        self.bind("<Escape>", lambda _e: self.destroy())
        self._place_over(master)
        self.after(100, self.bring_forward)

    def apply_theme(self, theme: palette.Theme) -> None:
        self.configure(fg_color=theme.window)
        self.band.configure(fg_color=theme.heading[0])
        self.name_label.configure(text_color=theme.heading[1])
        self.version_label.configure(text_color=theme.muted)
        for part, result in zip(self.stripes, "WDL"):
            part.configure(fg_color=theme.colours[result][0])
        summary, copyright_line, notice = self.body_labels
        summary.configure(text_color=theme.text)
        copyright_line.configure(text_color=theme.text)
        notice.configure(text_color=theme.muted)
        self.licence_label.configure(text_color=theme.heading[1])
        self.licence_box.configure(fg_color=theme.table[0], text_color=theme.table[1])
        self.close_button.configure(fg_color=theme.accent[0], hover_color=theme.accent_hover,
                                    text_color=theme.accent[1])

    def _place_over(self, master: tk.Misc) -> None:
        """Centre the window over the main one, no taller than most of the screen."""
        scale = ctk.ScalingTracker.get_window_scaling(self)
        height = min(self.HEIGHT, int(self.winfo_screenheight() / scale * 0.85))
        x = master.winfo_rootx() + (master.winfo_width() - round(self.WIDTH * scale)) // 2
        y = max(0, master.winfo_rooty() + (master.winfo_height() - round(height * scale)) // 2)
        self.geometry(f"{self.WIDTH}x{height}+{x}+{y}")
        self.minsize(self.WIDTH, height)

    def bring_forward(self) -> None:
        self.lift()
        self.focus_force()


class MenuEntry(NamedTuple):
    """One line of a sheet's right-click menu. A command of None is greyed; `children` make a submenu;
    MENU_SEPARATOR is a rule."""

    label: str
    command: Callable[[], object] | None = None
    children: tuple[MenuEntry, ...] = ()


MENU_SEPARATOR = MenuEntry("")


class SheetOverlay:
    """Rounded form pills and goal-difference bars painted over a sheet's cells. tksheet redraws only
    what is on screen, so after each of its redraws the overlay paints the rows on screen too, which
    keeps even a 5,000-team sheet quick. The cells keep their own text underneath, for copying."""

    TAG = "b2b-overlay"

    def __init__(self, sheet: Sheet, px: Callable[[float], int]) -> None:
        self.sheet, self.px = sheet, px
        self.pills: dict[tuple[int, int], str] = {}
        self.bars: dict[tuple[int, int], float] = {}
        self.sparks: dict[tuple[int, int], tuple[int, ...]] = {}
        self._spark_colour = ""
        self.drawn_rows: set[int] = set()        # the rows the last draw painted
        self._by_row: dict[int, list[tuple[int, str | float | tuple[int, ...]]]] = {}
        self._colours: Mapping[str, tuple[str | None, str | None]] = {}
        self._bar_colours = ("", "")
        self._font = (FONT, 9, "bold")
        self._hits: list[tuple[float, float, float, float, int, int, int]] = []   # each pill: box, row, column, index
        # Hovering a pill: on_hover(row, column, index, x_root, y_root); leaving every pill: on_leave().
        self.on_hover: Callable[[int, int, int, int, int], None] | None = None
        self.on_leave: Callable[[], None] | None = None
        sheet.bind("<<SheetRedrawn>>", self.draw, add=True)
        sheet.MT.bind("<Motion>", self._on_motion, add="+")
        sheet.MT.bind("<Leave>", lambda _e: self._left(), add="+")

    def pill_at(self, x: float, y: float) -> tuple[int, int, int] | None:
        """The (row, column, index in its cell) of the pill at a point on the canvas, or None."""
        return next(((row, column, index) for x1, y1, x2, y2, row, column, index in self._hits
                     if x1 <= x <= x2 and y1 <= y <= y2), None)

    def _on_motion(self, event) -> None:
        canvas = self.sheet.MT
        hit = self.pill_at(canvas.canvasx(event.x), canvas.canvasy(event.y))
        if hit is None:
            self._left()
        elif self.on_hover is not None:
            self.on_hover(*hit, event.x_root, event.y_root)

    def _left(self) -> None:
        if self.on_leave is not None:
            self.on_leave()

    def show(self, pills: Mapping[tuple[int, int], str], bars: Mapping[tuple[int, int], float],
             colours: Mapping[str, tuple[str | None, str | None]], bar_colours: tuple[str, str],
             sparks: Mapping[tuple[int, int], tuple[int, ...]] | None = None, spark_colour: str = "") -> None:
        """Pills: (row, column) → its letters, oldest first. Bars: (row, column) → a value from -1 to 1,
        drawn right in bar_colours[0] when positive and left in bar_colours[1] when negative. Sparks:
        (row, column) → league places, oldest first, drawn as a line under that cell's pills."""
        self.pills, self.bars, self.sparks = dict(pills), dict(bars), dict(sparks or {})
        self._colours, self._bar_colours, self._spark_colour = colours, bar_colours, spark_colour
        by_row: dict[int, list[tuple[int, str | float | tuple[int, ...]]]] = defaultdict(list)
        for (row, column), value in [*self.pills.items(), *self.bars.items(), *self.sparks.items()]:
            by_row[row].append((column, value))
        self._by_row = by_row
        self.draw()

    def clear(self) -> None:
        self.show({}, {}, self._colours, self._bar_colours)

    def draw(self, _event=None) -> None:
        canvas = self.sheet.MT
        canvas.delete(self.TAG)
        self.drawn_rows = set()
        self._hits = []
        self._left()                        # the pill under a still pointer may now be another match
        if not self._by_row:
            return
        start, end = self.sheet.visible_rows
        # Cell boxes from the positions themselves: get_cell_coords gives 0 for row or column 0.
        rows, columns = canvas.row_positions, canvas.col_positions
        for row in range(start, min(end + 1, len(rows) - 1)):
            for column, value in self._by_row.get(row, ()):
                if column + 1 >= len(columns):
                    continue
                box = (columns[column], rows[row], columns[column + 1], rows[row + 1])
                if isinstance(value, str):
                    self._pills(canvas, box, value, row, column)
                elif isinstance(value, tuple):
                    self._spark(canvas, box, value, len(self.pills.get((row, column), "")))
                else:
                    self._bar(canvas, box, value)
                self.drawn_rows.add(row)
        canvas.tag_raise(self.TAG)

    def _pills(self, canvas: tk.Canvas, box: tuple[float, ...], letters: str, row: int, column: int) -> None:
        x1, y1, x2, y2 = box
        width, height, gap = self.px(18), self.px(16), self.px(4)
        left = x1 + ((x2 - x1) - (len(letters) * (width + gap) - gap)) / 2
        top = (y1 + y2 - height) / 2 - (self.px(2) if (row, column) in self.sparks else 0)   # room for the spark
        for index, letter in enumerate(letters):
            self._hits.append((left, top, left + width, top + height, row, column, index))
            background, text = self._colours.get(letter, (None, None))
            canvas.create_polygon(rounded_box_coords(left, top, left + width, top + height, radius=height // 2),
                                  smooth=True, fill=background or "", outline="", tags=self.TAG)
            if background:
                highlight, shadow = palette.pill_edges(background)
                rim = (left + 1, top + 1, left + width - 1, top + height - 1)
                canvas.create_arc(*rim, start=20, extent=140, style="arc", outline=highlight, width=1, tags=self.TAG)
                canvas.create_arc(*rim, start=200, extent=140, style="arc", outline=shadow, width=1, tags=self.TAG)
            canvas.create_text(left + width / 2, top + height / 2, text=letter, fill=text or "#ffffff",
                               font=self._font, tags=self.TAG)
            left += width + gap

    def _spark(self, canvas: tk.Canvas, box: tuple[float, ...], places: tuple[int, ...], pill_count: int) -> None:
        """A thin line of league places under the pills, one point below each of the last pills; a better
        place sits higher. Its height covers at least three places, so one step never looks like a plunge."""
        x1, _y1, x2, y2 = box
        width, gap = self.px(18), self.px(4)
        points = min(len(places), pill_count)
        if points < 2:
            return
        places = places[-points:]
        left = x1 + ((x2 - x1) - (pill_count * (width + gap) - gap)) / 2
        xs = [left + (pill_count - points + i) * (width + gap) + width / 2 for i in range(points)]
        low, high = min(places), max(places)
        span, middle = max(high - low, 3), (low + high) / 2
        band_middle, band_height = y2 - self.px(3), self.px(4)
        coords = []
        for x, place in zip(xs, places):
            coords += [x, band_middle + (place - middle) / span * band_height]
        canvas.create_line(*coords, fill=self._spark_colour, width=1, tags=self.TAG)

    def _bar(self, canvas: tk.Canvas, box: tuple[float, ...], value: float) -> None:
        x1, _y1, x2, y2 = box
        middle = (x1 + x2) / 2
        reach = ((x2 - x1) / 2 - self.px(4)) * min(abs(value), 1.0)
        bottom = y2 - 2
        left, right = (middle, middle + reach) if value > 0 else (middle - reach, middle)
        colour = self._bar_colours[0] if value > 0 else self._bar_colours[1]
        canvas.create_rectangle(left, bottom - self.px(3), right, bottom, fill=colour, outline="", tags=self.TAG)


class ClubColoursDialog(ctk.CTkToplevel):
    """The followed club's two colours: a preview of the title band they make, a swatch for each that
    opens Windows' colour picker, and Save, Use the built-in colours, No club colours and Cancel."""

    def __init__(self, master: FMReviewApp, club: str, colours: tuple[str, str] | None) -> None:
        super().__init__(master)
        apply_window_icon(self)
        self.app, self.club = master, club
        builtin = club_colours.builtin_colours(club)
        self.colours: tuple[str, str] = colours or builtin or (master.theme.switch_selected, "#ffffff")
        theme = master.theme
        self.title(f"Club colours: {club}")
        self.transient(master)
        self.resizable(False, False)
        self.configure(fg_color=theme.window)

        self.preview = ctk.CTkFrame(self, corner_radius=0)
        self.preview.pack(fill="x")
        self.preview_label = ctk.CTkLabel(self.preview, text=club, font=ctk.CTkFont(FONT, 18, "bold"), anchor="w")
        self.preview_label.pack(fill="x", padx=24, pady=(16, 14))
        stripe = ctk.CTkFrame(self, corner_radius=0, height=4, fg_color="transparent")
        stripe.pack(fill="x")
        self.preview_stripe = [ctk.CTkFrame(stripe, corner_radius=0, width=1, height=4) for _ in range(12)]
        for part in self.preview_stripe:
            part.pack(side="left", fill="x", expand=True)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="x", padx=24, pady=(16, 8))
        self.swatches = []
        for row, label in enumerate(("Main colour", "Second colour")):
            ctk.CTkLabel(body, text=label, text_color=theme.text).grid(row=row, column=0, sticky="w", pady=4)
            swatch = ctk.CTkButton(body, text="", width=90, height=28, border_width=1, border_color=theme.muted,
                                   command=lambda index=row: self._pick(index))
            swatch.grid(row=row, column=1, padx=(16, 0), pady=4, sticky="w")
            self.swatches.append(swatch)
        self.main_swatch, self.second_swatch = self.swatches
        note = ("They colour the title band, the selected view and the followed team's highlight. Results, "
                "zones and headings keep their own colours.")
        if not theme.club_colours:
            note += f" {theme.name} shows no club colours."
        ctk.CTkLabel(body, text=note, text_color=theme.muted, wraplength=400, justify="left").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=(8, 18))
        accent = dict(fg_color=theme.accent[0], hover_color=theme.accent_hover, text_color=theme.accent[1])
        quiet = dict(fg_color=theme.quiet[0], hover_color=theme.quiet_hover, text_color=theme.quiet[1])
        self.save_button = ctk.CTkButton(buttons, text="Save", width=80, command=self._save, **accent)
        self.builtin_button = ctk.CTkButton(buttons, text="Use the built-in colours", width=170,
                                            command=self._builtin, state="normal" if builtin else "disabled", **quiet)
        self.none_button = ctk.CTkButton(buttons, text="No club colours", width=120, command=self._none, **quiet)
        self.cancel_button = ctk.CTkButton(buttons, text="Cancel", width=80, command=self.destroy, **quiet)
        for button in (self.cancel_button, self.save_button):
            button.pack(side="right", padx=(8, 0))
        for button in (self.builtin_button, self.none_button):
            button.pack(side="left", padx=(0, 8))

        self._show()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.geometry(f"+{master.winfo_rootx() + 160}+{master.winfo_rooty() + 90}")
        self.after(100, self.lift)

    def _show(self) -> None:
        """Paint the swatches and preview the band the colours make (in Midnight Emerald's way when
        the theme takes no club colours)."""
        theme = self.app.theme if self.app.theme.club_colours else palette.MIDNIGHT_EMERALD
        tint = palette.club_tint(theme, self.colours)
        self.preview.configure(fg_color=tint.band[0])
        self.preview_label.configure(text_color=tint.band[1])
        for i, part in enumerate(self.preview_stripe):
            part.configure(fg_color=self.colours[i % 2])
        for swatch, colour in zip(self.swatches, self.colours):
            swatch.configure(fg_color=colour, hover_color=colour)

    def _pick(self, index: int) -> None:
        chosen = colorchooser.askcolor(color=self.colours[index], parent=self,
                                       title=("Main colour" if index == 0 else "Second colour") + f": {self.club}")
        if chosen and chosen[1]:
            colours = list(self.colours)
            colours[index] = chosen[1].lower()
            self.colours = (colours[0], colours[1])
            self._show()

    def _save(self) -> None:
        self.app.save_club_colours(self.club, self.colours)
        self.destroy()

    def _builtin(self) -> None:
        self.app.reset_club_colours(self.club)
        self.destroy()

    def _none(self) -> None:
        self.app.save_club_colours(self.club, None)
        self.destroy()


if TkinterDnD is not None:
    class _Root(ctk.CTk, TkinterDnD.DnDWrapper):
        """CustomTkinter's window, with tkinterdnd2's drag-and-drop methods."""
else:
    class _Root(ctk.CTk):
        """CustomTkinter's window (tkinterdnd2 is not installed)."""


class FMReviewApp(_Root):
    """The main window: competitions on the left, the selected season's views on the right."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} {VERSION}")
        apply_window_icon(self)
        self.events: queue.Queue = queue.Queue()
        self.dataset: fd.Dataset | None = None
        self.names: dict[int, str] = {}
        self.settings = self._read_settings()
        self.country_key: int | str | None = None        # the Country menu's choice; None is every country
        self._country_options: tuple[fd.CountryOption, ...] = ()
        self.theme = palette.theme_by_name(self.settings.get("theme"))
        self.view_theme = self.theme              # the colours the views paint with: theme and club
        self.club_tint: palette.ClubTint | None = None
        self.club_names: dict[int, str] = {}      # each team's club, for its colours
        self.club_dialog: ClubColoursDialog | None = None
        self._themed: list[tuple[str, object]] = []      # (role, widget), for apply_theme
        self._shown: str | None = None            # the sheet on screen, if any
        self.loading_since: float | None = None
        self.loading_step = ""
        self._loading_file = ""                   # the save being read, for the drop refusal's wording
        self._reading_xg = False          # the save is open and its expected goals are on their way
        self._exporting = False
        self.about_window: AboutWindow | None = None
        self.yearbook_reader: YearbookReader | None = None

        self._reset_history()                  # the club inspector's History block (archive read lazily, off the UI thread)

        self.comp_id: int | None = None
        self.season: int | None = None
        self.focus: int | None = None
        self.view = VIEWS[0]
        self.last_comp_view = VIEWS[0]     # the view a competition opens in from the hub
        self.view_labels = {view: view for view in SWITCH_VIEWS}     # each view's label on the switch, with its count
        self._club_scope = NO_CLUB_FOLLOWED                          # what the Schedule and Hub cover
        self.group_by = fd.GROUP_BY_WEEK
        self.table_split = fd.SPLIT_OVERALL
        self.analysis = ANALYSES[0]
        self.positions_mode = POSITIONS_MODES[0]
        self.fixtures: tuple = ()
        self.labels: dict[int, str] = {}
        self.short_labels: dict[int, str] = {}
        self.list_rows: list[int | None] = []
        self.season_by_label: dict[str, int | None] = {}
        self.team_by_label: dict[str, int] = {}
        self.result_rows: list[fd.TimelineRow] = []
        self.grid_data: fd.Grid | None = None
        self.table_rows: list[int | None] = []
        self.analysis_rows: list[int | None] = []    # the team on each row of the Analysis sheet
        self.comp_row_ids: list[int] = []
        self._list_job: str | None = None
        self._search_job: str | None = None
        self._resize_job: str | None = None       # the view switch's counts follow the window's width
        self._drop_note_job: str | None = None    # clears a refused drop's reason after a while
        self._dataset_serial = 0                  # bumped per installed save
        self._schedule_serial = 0                 # bumped when followed club or save changes
        self._roundel_book: dict = {}             # theme name -> club name -> palette.Roundel, for the club views
        self._followed_uid: fd.FollowedClub | None = None   # persists across competition changes; resets on new save
        self._club_cache: tuple[int, tuple[fd.ClubEntry, ...]] | None = None    # the palette's clubs, per save
        self.opponent_filter: tuple[int, int] | None = None   # Results shows only matches between these two teams
        self._selection: tuple | None = None      # what the inspector describes: ("match", Fixture), ("club", id), ("hub", id)
        self._hub_key: tuple | None = None        # what the Competitions sheet was last filled from
        self._hub_summary = ""
        self._hub_categories: list[str] = []      # the hub's category on each row, for painting

        self.scale = ctk.ScalingTracker.get_window_scaling(self)
        screen_width = int(self.winfo_screenwidth() / self.scale)
        minimum = min(MIN_WINDOW_WIDTH, screen_width)       # never wider than a small screen
        width = max(min(1560, int(screen_width * 0.92)), minimum)
        height = min(940, int(self.winfo_screenheight() / self.scale * 0.85))
        self.geometry(f"{width}x{height}")
        self.minsize(minimum, 620)
        self.cell_font = tkfont.Font(family=FONT, size=10)

        self._load_names()
        self._build()
        self._enable_file_drop()
        self._poll_job: str | None = self.after(100, self._poll)

    def destroy(self) -> None:
        for job in (self._poll_job, self._list_job, self._search_job, self._resize_job, self._drop_note_job):
            if job:
                self.after_cancel(job)
        self._poll_job = None
        # Every other timer too (the palette's, the drawer's, CustomTkinter's own): none may fire on a dead window.
        # Tcl's own `after cancel`, not tkinter's after_cancel: that also deletes the timer's command, which a
        # child widget still lists as its own and would try to delete again as it is destroyed.
        for job in self.tk.splitlist(self.tk.call("after", "info")):
            self.tk.call("after", "cancel", job)
        super().destroy()

    # ----------------------------------------------------------------- layout

    def _role(self, role: str, widget):
        """Remember a widget's part in the theme, so that apply_theme can re-colour it."""
        self._themed.append((role, widget))
        return widget

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        role = self._role

        top = self.top_bar = role("panel", ctk.CTkFrame(self, corner_radius=0, height=56))
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.grid_columnconfigure(3, weight=1)
        self.open_button = role("button", ctk.CTkButton(top, text="Open save…", width=120, command=self.choose_save))
        self.open_button.grid(row=0, column=0, padx=(14, 10), pady=12)
        self.save_label = role("text", ctk.CTkLabel(top, text="No save open", font=ctk.CTkFont(FONT, 15, "bold")))
        self.save_label.grid(row=0, column=1, padx=(0, 12), sticky="w")
        self.meta_label = role("muted", ctk.CTkLabel(top, text=""))
        self.meta_label.grid(row=0, column=2, sticky="w")
        # The unverified-build notice is amber on a small chip of the plain panel colour, so that a club's
        # tint on the band never takes its colour: the one colour on the band that carries meaning.
        self.verify_chip = role("chip", ctk.CTkFrame(top, width=0, height=0, corner_radius=6))
        self.verify_chip.grid(row=0, column=3, padx=12, sticky="w")
        self.verify_label = role("muted", ctk.CTkLabel(self.verify_chip, text="", cursor="hand2",
                                                       font=ctk.CTkFont(FONT, 11)))
        self.verify_label.pack(padx=6, pady=0)
        for widget in (self.verify_chip, self.verify_label):
            widget.bind("<Button-1>", lambda _e: self.show_details())
            widget.bind("<Enter>", self._show_build_tip)
            widget.bind("<Leave>", lambda _e: self.tooltip.hide())
        self.verify_chip.grid_remove()
        self.progress = role("progress", ctk.CTkProgressBar(top, mode="indeterminate", width=180))
        self.progress.grid(row=0, column=4, padx=14)
        self.progress.grid_remove()
        self.theme_button = role("quiet", ctk.CTkButton(top, text=THEME_LABEL, width=90,
                                                        command=self._show_theme_menu))
        self.theme_button.grid(row=0, column=5, padx=(0, 8), pady=12)
        self.theme_name = tk.StringVar(self, value=self.theme.name)
        self.theme_menu = tk.Menu(self, tearoff=False)
        for theme in palette.THEMES:
            self.theme_menu.add_radiobutton(label=theme.name, variable=self.theme_name, value=theme.name,
                                            command=lambda name=theme.name: self.set_theme(name))
        self.theme_menu.add_separator()
        self.theme_menu.add_command(label="Follow club…", command=self._show_palette_key)
        self._follow_menu_item = self.theme_menu.index("end")
        self.theme_menu.add_command(label="Club colours…", command=self.show_club_colours)
        self._club_menu_item = self.theme_menu.index("end")
        # The followed club's two colours along the foot of the title band, shown while it has some.
        self.stripe = ctk.CTkFrame(top, corner_radius=0, height=4, fg_color="transparent")
        self.stripe_parts = [ctk.CTkFrame(self.stripe, corner_radius=0, width=1, height=4) for _ in range(12)]
        for part in self.stripe_parts:
            part.pack(side="left", fill="x", expand=True)
        self.about_button = role("quiet", ctk.CTkButton(top, text="About", width=80, command=self.show_about))
        self.about_button.grid(row=0, column=6, padx=(0, 14), pady=12)

        side = role("panel", ctk.CTkFrame(self, width=340, corner_radius=0))
        side.grid(row=1, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_rowconfigure(3, weight=1)
        side.grid_columnconfigure(0, weight=1)
        role("text", ctk.CTkLabel(side, text="Competitions", font=ctk.CTkFont(FONT, 14, "bold"))).grid(
            row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        self.search_entry = role("entry", ctk.CTkEntry(side, placeholder_text="Search competitions or clubs"))
        self.search_entry.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="ew")
        self.search_entry.bind("<KeyRelease>", lambda _e: self._schedule_search())
        self.country_menu = role("option", ctk.CTkOptionMenu(side, values=[fd.COUNTRY_ALL], dynamic_resizing=False,
                                                             command=self._on_country))
        self.country_menu.grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="ew")
        self.comp_list = role("list", tk.Listbox(side, activestyle="none", exportselection=False,
                                                 highlightthickness=0, borderwidth=0, font=(FONT, 10)))
        self.comp_list.grid(row=3, column=0, padx=(12, 0), pady=(0, 12), sticky="nsew")
        list_scroll = ctk.CTkScrollbar(side, command=self.comp_list.yview)     # its greys suit every theme
        list_scroll.grid(row=3, column=1, padx=(0, 6), pady=(0, 12), sticky="ns")
        self.comp_list.configure(yscrollcommand=list_scroll.set)
        self.comp_list.bind("<<ListboxSelect>>", lambda _e: self._schedule_list_select())

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=1, sticky="nsew", padx=14, pady=(10, 6))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        self.title_label = role("text", ctk.CTkLabel(header, text=APP_TITLE, font=ctk.CTkFont(FONT, 22, "bold"),
                                                     anchor="w"))
        self.title_label.grid(row=0, column=0, sticky="w")
        self.rename_button = role("quiet", ctk.CTkButton(header, text="Name this competition…", width=170,
                                                         command=self.rename_competition))
        self.rename_button.grid(row=0, column=1, rowspan=2, sticky="e")
        self.export_button = role("button", ctk.CTkButton(header, text=EXPORT_LABEL, width=100,
                                                          command=self._show_export_menu))
        self.export_button.grid(row=0, column=2, rowspan=2, padx=(8, 0), sticky="e")
        self.inspector_button = role("quiet", ctk.CTkButton(header, text="Inspector", width=90,
                                                            command=self.toggle_inspector))
        self.inspector_button.grid(row=0, column=3, rowspan=2, padx=(8, 0), sticky="e")
        self.schedule_button = role("quiet", ctk.CTkButton(header, text=SCHEDULE, width=90,
                                                           command=lambda: self.set_view(SCHEDULE)))
        self.schedule_button.grid(row=0, column=4, rowspan=2, padx=(8, 0), sticky="e")
        self.hub_button = role("quiet", ctk.CTkButton(header, text=MANAGER_HUB, width=60,
                                                      command=lambda: self.set_view(MANAGER_HUB)))
        self.hub_button.grid(row=0, column=5, rowspan=2, padx=(8, 0), sticky="e")
        self.export_menu = tk.Menu(self, tearoff=False, postcommand=self._refresh_export_menu)
        for kind, label in ((fx.EXCEL, "Excel workbook (.xlsx)"), (fx.HTML, "Web page (.html)"),
                            (fx.CSV, "CSV files (.csv)")):
            self.export_menu.add_command(label=label, command=lambda k=kind: self.export(k))
        self.export_menu.add_command(label=WHOLE_SAVE_LABEL, command=self.export_whole_save)
        self.post_menu = tk.Menu(self.export_menu, tearoff=False, postcommand=self._refresh_post_menu)
        for kind, label in (("table", "Table"), ("team", "My club's results"), ("recent", "Recent results")):
            self.post_menu.add_command(label=label, command=lambda k=kind: self.copy_for_post(k))
        self.export_menu.add_cascade(label="Copy for a post", menu=self.post_menu)
        self.yearbook_menu = tk.Menu(self.export_menu, tearoff=False, postcommand=self._refresh_yearbook_menu)
        self.mark_club_var = tk.BooleanVar(value=False)         # off unless asked for, every time the app starts
        self.export_menu.add_cascade(label="Yearbook (PDF)", menu=self.yearbook_menu)
        self.export_menu.add_separator()
        self.export_menu.add_command(label="Open the export folder", command=self.open_export_folder)
        self.hint_label = role("muted", ctk.CTkLabel(header, text="", anchor="w"))
        self.hint_label.grid(row=1, column=0, sticky="w")

        controls = self.controls = ctk.CTkFrame(main, fg_color="transparent")
        controls.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        # Line 1 (season, team, view switch) and the view's own switches sit side by side, or one above the other
        # when the window is too narrow for both: see _layout_controls.
        line_one = self.controls_line_one = ctk.CTkFrame(controls, fg_color="transparent")
        own = self.controls_own = ctk.CTkFrame(controls, fg_color="transparent")
        self.controls_wrapped = False
        self._controls_shape: tuple[bool, bool] | None = None
        role("text", ctk.CTkLabel(line_one, text="Season")).pack(side="left", padx=(0, 6))
        self.season_menu = role("option", ctk.CTkOptionMenu(line_one, values=["–"], width=110,
                                                            command=self._on_season))
        self.season_menu.pack(side="left", padx=(0, 16))
        role("text", ctk.CTkLabel(line_one, text="Team")).pack(side="left", padx=(0, 6))
        self.team_box = role("combo", ctk.CTkComboBox(line_one, values=[ALL_TEAMS], width=250, command=self._on_team))
        self.team_box.pack(side="left", padx=(0, 16))
        self.team_box.bind("<Return>", self._on_team_typed)
        self.view_switch = role("switch", ctk.CTkSegmentedButton(line_one, values=list(SWITCH_VIEWS),
                                                                 command=self._on_view_label))
        self.view_switch.set(self.view)
        self.view_switch.pack(side="left", padx=(0, 16))
        self.group_label = role("text", ctk.CTkLabel(own, text="Group by"))
        self.group_label.pack(side="left", padx=(0, 6))
        self.group_switch = role("switch", ctk.CTkSegmentedButton(own, values=list(GROUPINGS),
                                                                  command=self._on_group))
        self.group_switch.set(self.group_by)
        self.group_switch.pack(side="left")

        self.split_label = role("text", ctk.CTkLabel(own, text="Standings"))
        self.split_switch = role("switch", ctk.CTkSegmentedButton(own, values=list(fd.SPLITS),
                                                                  command=self._on_table_split))
        self.split_switch.set(self.table_split)
        self.analysis_label = role("text", ctk.CTkLabel(own, text="Show"))
        self.analysis_switch = role("switch", ctk.CTkSegmentedButton(own, values=list(ANALYSES),
                                                                     command=self._on_analysis))
        self.analysis_switch.set(self.analysis)
        # Shown only when Analysis > Positions has a comparison to offer (>=2 seasons with a snapshot).
        self.positions_mode_switch = role("switch", ctk.CTkSegmentedButton(
            own, values=list(POSITIONS_MODES), command=self._on_positions_mode))
        self.positions_mode_switch.set(self.positions_mode)
        self._layout_controls()

        self.coverage_label = role("text", ctk.CTkLabel(main, text="", anchor="w", justify="left"))
        self.coverage_label.grid(row=2, column=0, sticky="ew")
        self.note_label = role("muted", ctk.CTkLabel(main, text="", anchor="w", justify="left", wraplength=1100))
        self.note_label.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        self.filter_clear = role("quiet", ctk.CTkButton(main, text="Clear", width=70, height=24,
                                                        command=lambda: self.set_opponent_filter(None)))
        self.filter_clear.grid(row=3, column=0, sticky="ne", pady=(0, 6))
        self.filter_clear.grid_remove()

        content = role("content", ctk.CTkFrame(main, corner_radius=6))
        content.grid(row=4, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)
        self.sheets = {
            "Results": self._make_sheet(content, show_row_index=False, own_menu=True),
            "Grid": self._make_sheet(content, own_menu=True, align="center"),
            # A row index a few pixels wide, coloured with each row's zone: the zone edge.
            "Table": self._make_sheet(content, own_menu=True, show_row_index=True,
                                      show_default_index_for_empty=False, default_row_index=None),
            ANALYSIS: self._make_sheet(content, own_menu=True, show_row_index=False),
            HUB: self._make_sheet(content, show_row_index=False),
        }
        for name, sheet in self.sheets.items():
            sheet.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
            sheet.bind("<<SheetSelect>>", lambda _e, n=name: self._on_sheet_select(n))
            if name != HUB:     # the hub keeps tksheet's own menu; the others get one that knows the club
                for part in (sheet.MT, sheet.RI):
                    part.bind("<Button-3>", lambda e, n=name: self._show_row_menu(n, e), add="+")
            sheet.grid_remove()
        self.sheets[HUB].bind("<Double-Button-1>", lambda _e: self._open_from_hub())
        self.overlays = {name: SheetOverlay(self.sheets[name], self.px) for name in ("Table", ANALYSIS)}
        self.bracket_view = bracket.BracketView(content, px=self.px, font=(FONT, 10), theme=self.theme)
        self.bracket_view.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self.bracket_view.grid_remove()                                  # the Analysis view's Bracket panel shows it
        self._schedule_view = fsv.ScheduleView(content, fg_color="transparent",
                                               show_gaps=self.settings.get(SCHEDULE_GAPS) is True,
                                               on_gaps_changed=self._remember_schedule_gaps,
                                               on_select=lambda item: self._on_schedule_select(item),
                                               on_inspect=lambda item: self._on_schedule_inspect(item),
                                               on_right_click=lambda event, item: self._on_schedule_right_click(event, item))
        self._schedule_view.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._schedule_view.grid_remove()
        self._manager_hub_view = fmh.ManagerHubView(content, fg_color="transparent")
        self._manager_hub_view.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._manager_hub_view.grid_remove()
        self.tooltip = tooltip.Tooltip(self, theme=self.theme)        # over the form pills
        for name, overlay in self.overlays.items():
            overlay.on_hover = lambda row, column, index, x, y, n=name: self._on_pill_hover(n, row, column, index, x, y)
            overlay.on_leave = self.tooltip.hide
        self.inspector = inspector.Inspector(content, px=self.px, font=(FONT, 10), theme=self.theme,
                                             on_close=self._inspector_closed)
        self.message = role("content", ctk.CTkFrame(content))
        self.message.grid(row=0, column=0, sticky="nsew")
        self.message_label = role("text", ctk.CTkLabel(self.message, text="", font=ctk.CTkFont(FONT, 15),
                                                       wraplength=700))
        self.message_label.pack(expand=True, pady=(0, 10))
        self.reopen_button = role("button", ctk.CTkButton(self.message, text="", width=300, command=self._reopen_last))

        # The colour key: a chip and a meaning for each zone the Table or Positions view shows.
        self.zone_key = ctk.CTkFrame(main, fg_color="transparent")
        self.zone_key.grid(row=5, column=0, sticky="w", pady=(6, 0))
        self.zone_key.grid_remove()
        self.zone_key_meanings: list[str] = []
        self.zone_edges: dict[int, str] = {}         # the Table's row → its zone colour

        self.detail_label = role("muted", ctk.CTkLabel(main, text="", anchor="w"))
        self.detail_label.grid(row=6, column=0, sticky="ew", pady=(4, 0))

        status = self.status_bar = role("panel", ctk.CTkFrame(self, corner_radius=0, height=30))
        status.grid(row=2, column=0, columnspan=2, sticky="ew")
        status.grid_columnconfigure(0, weight=1)
        self.status_label = role("muted", ctk.CTkLabel(status, text="", anchor="w"))
        self.status_label.grid(row=0, column=0, padx=14, sticky="ew")
        self.details_button = role("quiet", ctk.CTkButton(status, text="Save details & warnings", width=170,
                                                          height=24, command=self.show_details))
        self.details_button.grid(row=0, column=1, padx=10, pady=3)

        self._recolour()
        self._update_club_tint()
        self._set_controls_state("disabled")
        self._show_welcome()
        self._refresh_status()
        self.bind("<Configure>", self._on_resize, add="+")
        self.command_palette = command_palette.CommandPalette(self, px=self.px, font=(FONT, 11), on_error=self._palette_failed,
                                                              theme=self.theme)
        for key in ("<Control-i>", "<Control-I>"):
            self.bind(key, self._on_inspector_key)
        self.bind("<Escape>", self._on_escape, add="+")
        for key in ("<Control-k>", "<Control-K>", "<Control-p>", "<Control-P>"):
            self.bind(key, self._on_palette_key)
            # In a text box Ctrl+K would also delete to the end of the line: open the palette instead of that.
            self.team_box.bind(key, self._on_palette_key, add=True)
            self.search_entry.bind(key, self._on_palette_key, add=True)
        for key in ("<Control-S>",):
            self.bind(key, lambda _e: self.set_view(SCHEDULE))
        for key in ("<Control-H>",):
            self.bind(key, lambda _e: self.set_view(MANAGER_HUB))

    def _make_sheet(self, parent, own_menu: bool = False, **options) -> Sheet:
        """A sheet in the shared style; its colours come from the theme (see _recolour). With `own_menu`
        the sheet keeps tksheet's right-click selection but not its menu: see _show_row_menu."""
        with_index = options.get("show_row_index", True)
        sheet = Sheet(
            parent, theme="dark blue", show_top_left=with_index, row_index_align="w",
            table_wrap="", index_wrap="", header_wrap="", allow_cell_overflow=True,
            font=(FONT, 10, "normal"), header_font=(FONT, 10, "bold"), index_font=(FONT, 10, "normal"),
            outline_thickness=0, default_row_height=self.px(24), **options,
        )
        sheet.enable_bindings("single_select", "row_select", "column_select", "column_width_resize",
                              "arrowkeys", "copy", "rc_select" if own_menu else "right_click_popup_menu")
        if not own_menu:
            sheet.enable_bindings("rc_select")
        return sheet

    # ----------------------------------------------------------------- themes

    def _recolour(self) -> None:
        """Paint every widget in the current theme's colours."""
        t = self.theme
        styles = {
            "panel": dict(fg_color=t.panel),
            "content": dict(fg_color=t.table[0]),
            "text": dict(text_color=t.text),
            "muted": dict(text_color=t.muted),
            "warning": dict(text_color=t.warning),
            "chip": dict(fg_color=t.panel),
            "button": dict(fg_color=t.accent[0], hover_color=t.accent_hover, text_color=t.accent[1]),
            "quiet": dict(fg_color=t.quiet[0], hover_color=t.quiet_hover, text_color=t.quiet[1]),
            "switch": dict(fg_color=t.switch[0], unselected_color=t.switch[0], unselected_hover_color=t.switch_hover,
                           selected_color=t.switch_selected, selected_hover_color=t.switch_selected_hover,
                           text_color=t.switch[1]),
            "option": dict(fg_color=t.accent[0], button_color=t.accent_hover, text_color=t.accent[1]),
            "combo": dict(fg_color=t.field[0], border_color=t.field[1], button_color=t.field[1], text_color=t.text),
            "entry": dict(fg_color=t.field[0], border_color=t.field[1], text_color=t.text),
            "progress": dict(progress_color=t.accent[0]),
            "list": dict(bg=t.competition_list[0], fg=t.competition_list[1], selectbackground=t.list_selected[0],
                         selectforeground=t.list_selected[1]),
        }
        self.configure(fg_color=t.window)
        for role, widget in self._themed:
            widget.configure(**styles[role])
        if getattr(self, "command_palette", None) is not None:
            self.command_palette.restyle(t)
        if getattr(self, "inspector", None) is not None:
            self.inspector.restyle(t)
        if getattr(self, "tooltip", None) is not None:
            self.tooltip.restyle(t)
        if getattr(self, "bracket_view", None) is not None:
            self.bracket_view.use_theme(t)
        selected = t.selection[0]
        border = t.selection[1]
        for name, sheet in self.sheets.items():
            sheet.set_options(
                frame_bg=t.table[0], table_bg=t.table[0], table_fg=t.table[1], table_grid_fg=t.grid_line,
                header_bg=t.sheet_heading[0], header_fg=t.sheet_heading[1],
                # The Table's index is its zone edge, so it sits in the table's own colour.
                index_bg=t.table[0] if name == "Table" else t.sheet_heading[0],
                index_fg=t.sheet_heading[1], top_left_bg=t.sheet_heading[0],
                table_selected_cells_bg=selected, table_selected_cells_border_fg=border,
                table_selected_rows_bg=selected, table_selected_rows_border_fg=border,
                table_selected_columns_bg=selected, table_selected_columns_border_fg=border,
            )

    def apply_theme(self, theme: palette.Theme) -> None:
        """Re-colour the window in a theme and redraw what is on screen where it stands: nothing is
        reloaded, and the competition, season, followed team, view and scroll position stay."""
        self.theme = theme
        self.theme_name.set(theme.name)
        self._recolour()
        self._update_header_buttons()
        self._update_club_tint()
        self._retheme_club_views()
        self._fill_competition_list()
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.apply_theme(theme)
        if self.yearbook_reader is not None and self.yearbook_reader.winfo_exists():
            self.yearbook_reader.apply_theme(theme)
        shown = self.sheets.get(self._shown) if self._shown else None
        where = (shown.get_xview()[0], shown.get_yview()[0]) if shown is not None else None
        if self._hub_key is not None:
            self._paint_hub()
        self.render()
        if shown is not None and self.sheets.get(self._shown) is shown:
            shown.set_xview(where[0])
            shown.set_yview(where[1])

    def set_theme(self, name: str) -> None:
        """Switch to the named theme and remember it for next time."""
        self.apply_theme(palette.theme_by_name(name))
        self.settings["theme"] = self.theme.name
        self._write_settings()

    # ----------------------------------------------------------------- club colours

    def _followed_club(self) -> str | None:
        """The followed club's name: the one followed across competitions, else the highlighted team's club."""
        if self._followed_uid is not None and self._followed_uid.name:
            return self._followed_uid.name
        return self.club_names.get(self.focus) if self.focus is not None else None

    def _update_club_tint(self) -> None:
        """Work the followed club's colours into the window: the title band, the view switch's
        selected button and the followed team's highlight. Results, zones and headings keep theirs."""
        colours = club_colours.colours_for(self._followed_club(), self.settings.get("club_colours"))
        self.club_tint = palette.club_tint(self.theme, colours)
        self.view_theme = palette.with_club(self.theme, self.club_tint)
        t, tint = self.theme, self.club_tint
        if tint is None:
            band, text, muted = t.panel, t.text, t.muted
            selected, hover = t.switch_selected, t.switch_selected_hover
            self.stripe.place_forget()
        else:
            (band, text), muted = tint.band, tint.band_muted
            selected, hover = tint.selected
            for i, part in enumerate(self.stripe_parts):
                part.configure(fg_color=tint.colours[i % 2])
            self.stripe.place(relx=0, rely=1.0, relwidth=1.0, anchor="sw")
        self.top_bar.configure(fg_color=band)
        self.save_label.configure(text_color=text)
        self.meta_label.configure(text_color=muted)
        self.view_switch.configure(selected_color=selected, selected_hover_color=hover)
        self.theme_menu.entryconfigure(self._club_menu_item,
                                       state="normal" if self._followed_club() else "disabled")

    def _club_edits_without(self, club: str) -> dict:
        """Mark's colour edits, less any for this club under any spelling."""
        edits = self.settings.get("club_colours")
        key = club_colours.normalise(club)
        return {name: value for name, value in (edits.items() if isinstance(edits, dict) else ())
                if not (isinstance(name, str) and club_colours.normalise(name) == key)}

    def save_club_colours(self, club: str, colours: tuple[str, str] | None) -> None:
        """Keep a club's colours in the settings, or None for no club colours, and show them."""
        edits = self._club_edits_without(club)
        edits[club] = list(colours) if colours is not None else None
        self.settings["club_colours"] = edits
        self._write_settings()
        self._update_club_tint()
        self._rebuild_roundels()
        self.render()

    def reset_club_colours(self, club: str) -> None:
        """Forget Mark's edit for a club, so that the built-in colours apply again."""
        self.settings["club_colours"] = self._club_edits_without(club)
        self._write_settings()
        self._update_club_tint()
        self._rebuild_roundels()
        self.render()

    def show_club_colours(self) -> None:
        """Open the colours dialog for the followed team's club."""
        club = self._followed_club()
        if club is None:
            return
        if self.club_dialog is not None and self.club_dialog.winfo_exists():
            self.club_dialog.destroy()
        colours = club_colours.colours_for(club, self.settings.get("club_colours"))
        self.club_dialog = ClubColoursDialog(self, club, colours)

    def _show_theme_menu(self) -> None:
        self._popup(self.theme_menu, self.theme_button)

    @staticmethod
    def _popup(menu: tk.Menu, button: ctk.CTkButton) -> None:
        """Open a menu under its button."""
        try:
            menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        finally:
            menu.grab_release()

    def px(self, value: float) -> int:
        return int(round(value * self.scale))

    def _text_width(self, texts, minimum: int = 40, padding: int = 22) -> int:
        widest = max((self.cell_font.measure(str(t)) for t in texts), default=0)
        return max(self.px(minimum), widest + self.px(padding))

    # ----------------------------------------------------------------- loading

    def choose_save(self) -> None:
        last = self.settings.get("last_save")
        start = Path(last).parent if last and Path(last).parent.is_dir() else default_save_folder()
        path = filedialog.askopenfilename(
            parent=self, title="Open a Football Manager save", initialdir=str(start),
            filetypes=[("Football Manager saves", "*.fm"), ("All files", "*.*")],
        )
        if path:
            self.open_save(path)

    def open_save(self, path: str | Path) -> None:
        if self.loading_since is not None:
            return
        path = Path(path)
        self.loading_since = time.monotonic()
        self.loading_step = "Opening the save"
        self.open_button.configure(state="disabled")
        self.reopen_button.configure(state="disabled")
        self.progress.grid()
        self.progress.start()
        self._loading_file = path.name
        if self.dataset is None:
            self._show_message(f"Reading {path.name}…\n\nThis usually takes about half a minute.")
        threading.Thread(target=self._load_worker, args=(path,), daemon=True).start()

    def _load_worker(self, path: Path) -> None:
        """Read a save: the views get it as soon as it is in ("loaded"), and the same save with its
        expected goals about 12 s later ("xg")."""
        try:
            dataset = fd.load_dataset(path, progress=lambda step: self.events.put(("progress", step)),
                                      ready=lambda first: self.events.put(("loaded", first)))
            self.events.put(("xg", dataset))
        except fd.ImportFailed as exc:
            self.events.put(("failed", str(exc)))
        except Exception as exc:  # report anything unexpected rather than dying silently
            self._log_error(traceback.format_exc())
            self.events.put(("failed", f"Unexpected error while reading the save:\n{type(exc).__name__}: {exc}"))

    def _start_banking(self, dataset: fd.Dataset) -> None:
        """Bank the save just opened into the archive on a worker thread. Opening is never delayed, and a failure
        here never touches the save that is open."""
        self._bank_thread = threading.Thread(target=self._bank_worker, args=(dataset,), daemon=True)
        self._bank_thread.start()

    def _bank_worker(self, dataset: fd.Dataset) -> None:
        try:
            with archive.Archive.open(ARCHIVE_PATH) as book:
                report = book.bank(dataset)
            self.events.put(("banked", report))
        except archive.ArchiveError as exc:          # includes a different playthrough: its message is plain words
            self.events.put(("bank_failed", str(exc)))
        except Exception as exc:
            self._log_error(traceback.format_exc())
            self.events.put(("bank_failed", f"This save could not be banked into the archive "
                                            f"({type(exc).__name__}: {exc}). It is still open."))

    def _reset_history(self, banked: bool = False) -> None:
        """Forget the archive read for the History block. `banked` is true once this save has been banked."""
        self._history_serial = getattr(self, "_history_serial", 0) + 1    # a read still in flight is then ignored
        self._history_banked = banked
        self._history_failed = False
        self._history_loading = False
        self._history_unreadable = False
        self._history_cache: fd.Dataset | None = None
        self._history_rows: dict[tuple, tuple[fd.HistoryRow, ...]] = {}

    def _history_worker(self, serial: int) -> None:
        """Read the archive into a Dataset, away from the UI thread."""
        try:
            with archive.Archive.open(ARCHIVE_PATH) as book:
                data = book.dataset()
            self.events.put(("history_loaded", (serial, data)))
        except Exception:
            self._log_error(traceback.format_exc())
            self.events.put(("history_loaded", (serial, None)))

    def _history_blocks(self, team_id: int) -> list:
        """The History heading and lines for a club, or nothing until this save has banked. The archive is only
        ever opened to read, and only when its file exists."""
        if self._history_failed:
            return [inspector.Heading("History"),
                    inspector.Line("History is unavailable: this save was not banked.", muted=True)]
        if not self._history_banked:
            return []
        heading = inspector.Heading("History")
        if not ARCHIVE_PATH.exists():
            return [heading, inspector.Line("No archive yet: seasons appear here once saves are banked.", muted=True)]
        if self._history_unreadable:
            return [heading, inspector.Line("History is unavailable: the archive could not be read.", muted=True)]
        identity = self.dataset.teams.get(team_id) if self.dataset else None
        if identity is None or identity.club_uid is None:
            return []
        if self._history_cache is None:
            if not self._history_loading:
                self._history_loading = True
                threading.Thread(target=self._history_worker, args=(self._history_serial,), daemon=True).start()
            return [heading, inspector.Line("Loading history...", muted=True)]
        exclude = self.season if self.comp_id in self.dataset.by_id else None
        key = (identity.club_uid, exclude)
        if key not in self._history_rows:
            self._history_rows[key] = fd.club_history(self._history_cache, identity.club_uid, self.names, exclude)
        rows = self._history_rows[key]
        if not rows:
            return [heading, inspector.Line("No earlier seasons in the archive.", muted=True)]
        blocks: list = [heading] + [inspector.Line(r.text()) for r in rows[:HISTORY_LINES]]
        if len(rows) > HISTORY_LINES:
            blocks.append(inspector.Line(f"and {len(rows) - HISTORY_LINES} earlier seasons", muted=True))
        if any(r.incomplete for r in rows[:HISTORY_LINES]):
            blocks.append(inspector.Line("A match with no recoverable score counts as played only, so these "
                                         "totals are minimums.", muted=True))
        return blocks

    def _start_xg_banking(self, dataset: fd.Dataset) -> None:
        """Bank the expected goals that arrive a few seconds after the save, once the save itself has been banked.
        Nothing happens for a save whose match reports could not be read."""
        if not dataset.expected_goals:
            return
        self._bank_thread = threading.Thread(target=self._xg_bank_worker,
                                             args=(dataset, getattr(self, "_bank_thread", None)), daemon=True)
        self._bank_thread.start()

    def _xg_bank_worker(self, dataset: fd.Dataset, banking: threading.Thread | None) -> None:
        if banking is not None:
            banking.join()
        try:
            with archive.Archive.open(ARCHIVE_PATH) as book:
                report = book.bank_expected_goals(dataset)
            if report is not None:                    # None: the save itself was not banked, so there is nothing to add to
                self.events.put(("banked", report))
        except archive.ArchiveError as exc:
            self.events.put(("bank_failed", str(exc)))
        except Exception as exc:
            self._log_error(traceback.format_exc())
            self.events.put(("bank_failed", f"The expected goals could not be banked into the archive "
                                            f"({type(exc).__name__}: {exc}). The save is still open."))

    def _poll(self) -> None:
        try:
            while True:
                self.handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        if self.loading_since is not None:
            seconds = time.monotonic() - self.loading_since
            if self._reading_xg:
                text = (f"{self._loading_file} is open. Reading its match statistics for expected goals…  "
                        f"{seconds:.0f} s")
            else:
                text = (f"Reading {self._loading_file}: {self.loading_step}…  {seconds:.0f} s "
                        "(a save usually takes about half a minute)")
            self.status_label.configure(text=text)
        self._poll_job = self.after(150, self._poll)

    def handle_event(self, event: tuple) -> None:
        kind, payload = event
        if kind == "progress":
            self.loading_step = payload
            return
        if kind in ("exported", "export_failed"):
            self._finish_export(kind, payload)
            return
        if kind == "yearbook_ready":
            self._exporting = False
            self.export_button.configure(state="normal" if self.dataset else "disabled", text=EXPORT_LABEL)
            self.detail_label.configure(text="")
            self.show_yearbook_reader(payload)
            return
        if kind == "roundels_ready":
            serial, book = payload
            if serial == self._schedule_serial:
                self._roundel_book = book
                self._retheme_club_views()
            return
        if kind == "schedule_ready":
            # Background work for the open save, not the end of a load: it never touches the loading
            # controls, and a result from an older save or selection is dropped.
            serial, sched, snap, book, season = payload
            if serial == self._schedule_serial:
                self.install_schedule_views(sched, snap, book, season)
            return
        if kind == "yearbook_moved_on":
            self._exporting = False
            self.export_button.configure(state="normal" if self.dataset else "disabled", text=EXPORT_LABEL)
            self.detail_label.configure(text="")
            self._choose_edition(*payload)
            return
        if kind == "yearbook_refreshed":
            volume, plan = payload
            self.show_yearbook_reader(volume)
            self._finish_export("exported", ("yearbook", plan))
            return
        if kind == "banked":
            self.detail_label.configure(text=payload.describe())
            self._reset_history(banked=True)             # the archive just changed: read it afresh when next needed
            self._refresh_inspector()
            return
        if kind == "bank_failed":
            self.detail_label.configure(text=payload)
            if not self._history_banked:                 # a later failure (the expected goals) does not unbank the save
                self._history_failed = True
                self._refresh_inspector()
            return
        if kind == "history_loaded":
            serial, data = payload
            if serial == self._history_serial:
                self._history_loading = False
                self._history_cache = data
                self._history_unreadable = data is None
                self._refresh_inspector()
            return
        if kind == "loaded":
            # The save is in and can be browsed; its expected goals follow from the same worker,
            # and another save cannot be opened until they have.
            self._reading_xg = True
            self.open_button.configure(state="disabled")
            self.reopen_button.configure(state="disabled")
            self.install_dataset(payload)
            self._start_banking(payload)
            return
        self.loading_since = None
        self._reading_xg = False
        self.progress.stop()
        self.progress.grid_remove()
        self.open_button.configure(state="normal")
        self.reopen_button.configure(state="normal")
        if kind == "xg":
            self.install_expected_goals(payload)
            self._start_xg_banking(payload)
        else:
            # A failed import leaves whatever was open before untouched.
            kept = "\n\nThe save that was already open is still shown." if self.dataset else ""
            self._refresh_status()
            if self.dataset is None:
                self._show_welcome()
            messagebox.showerror("Could not open the save", f"{payload}{kept}", parent=self)

    def install_dataset(self, dataset: fd.Dataset) -> None:
        self.close_palette()                       # its items describe the save that was open
        self.close_inspector()
        self._reset_history()                      # banking of this save has not been reported yet
        self._selection = None
        self.dataset = dataset
        self._dataset_serial += 1
        self.country_key = None                    # the choice is not kept from one save to the next
        self._refresh_country_menu()
        self._followed_uid = None
        self._schedule_serial += 1
        self._schedule_view.clear()                # the install below renders, so no render here
        self._manager_hub_view.clear(NO_CLUB_FOLLOWED)
        self._club_scope = NO_CLUB_FOLLOWED
        default = fd.default_followed_club(dataset)       # a managed save follows its club; an observer save no one
        if default is not None:
            self._set_followed_uid(default)
        self.settings["last_save"] = dataset.info.path
        self._write_settings()
        info = dataset.info
        self.save_label.configure(text=info.file_name)
        meta = [f"{info.game} build {info.build}"]
        if info.game_date:
            meta.append(f"in-game date {info.game_date.day} {info.game_date:%B %Y}")
        if info.managed_club_name:
            meta.append(info.managed_club_name)
        self.meta_label.configure(text="  ·  ".join(meta))
        self._set_build_notice("" if info.known_build else "UV")
        self._refresh_status()
        self._set_controls_state("normal")
        self._sync_view_controls()
        self.comp_id = None
        self._fill_competition_list()
        if dataset.competitions:
            self.select_competition(dataset.competitions[0].id)
        else:
            self._show_message("This save holds no fixtures that could be read.")

    def _build_notice_tip(self) -> str:
        """What the "UV" chip stands for, in words (the click opens the full details)."""
        info = self.dataset.info
        return (f"Unverified build: {info.game} {info.build} is not one fmsave {info.fmsave_version} has layouts "
                "for yet, so it borrows the nearest known ones. Values are unconfirmed until fmsave "
                "supports the build. Click for details.")

    def _show_build_tip(self, event) -> None:
        if self.dataset is not None:
            self.tooltip.show(self._build_notice_tip(), event.x_root, event.y_root)

    def _set_build_notice(self, text: str) -> None:
        """Show the unverified-build notice on its chip, or hide the chip when the build is known."""
        self.verify_label.configure(text=text)
        if text:
            self.verify_chip.grid()
        else:
            self.verify_chip.grid_remove()

    def install_expected_goals(self, dataset: fd.Dataset) -> None:
        """Swap in the open save with its expected goals, leaving the view where it is."""
        if self.dataset is None or self.dataset.info.path != dataset.info.path:
            self.install_dataset(dataset)
            return
        self.dataset = dataset
        self._refresh_status()
        self._refresh_inspector()                  # the statistics it was waiting for may have arrived
        if self._followed_uid is not None:         # the Schedule and Hub gain the arrived xG and grounds
            self._set_followed_uid(self._followed_uid, refresh=True)
        if self.comp_id is None or self.view == HUB or not self.fixtures:
            return
        if self.view == "Results":
            sheet = self.sheets["Results"]
            self._fill_results_xg(sheet)
            sheet.refresh()
            self.note_label.configure(text=self._results_note())
        elif self.view == ANALYSIS and self.analysis == "xG":
            self.render()

    # ----------------------------------------------------------------- dropping a save onto the window

    def _enable_file_drop(self) -> None:
        """Let a .fm save be dropped onto the window. tkinterdnd2 is an optional extra: without it, or if
        its native part cannot load, the window works as before and says so."""
        self.drop_enabled = False
        try:
            if TkinterDnD is None:
                raise ImportError("the tkinterdnd2 package is not installed")
            TkinterDnD._require(self)                    # loads the native tkdnd library into this window's Tcl
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<DropEnter>>", self._on_drop_enter)
            self.dnd_bind("<<DropLeave>>", self._on_drop_leave)
            self.dnd_bind("<<Drop>>", self._on_file_drop)
        except Exception as exc:  # an optional extra must never stop the window opening
            self.detail_label.configure(
                text=f"Dropping a save onto the window is not available ({exc}); Open save… still works.")
            return
        self.drop_enabled = True

    def _on_drop_enter(self, event) -> str:
        self.status_label.configure(text=DROP_HINT)
        return event.action

    def _on_drop_leave(self, _event) -> None:
        self._refresh_status()

    def _on_file_drop(self, event) -> str:
        """A drop: open it when it is one .fm save, otherwise say why not. Returns the action tkdnd needs."""
        self._refresh_status()                           # the drag-over hint ends with the drop
        if self.loading_since is not None:
            self._note_drop(f"Still reading {self._loading_file}; drop again when it has finished.")
            return REFUSE_DROP
        path, why = accept_dropped_save(self.tk.splitlist(event.data))
        if path is None:
            self._note_drop(why)
            return REFUSE_DROP
        self.open_save(path)
        return COPY

    def _note_drop(self, text: str) -> None:
        """Say why a drop was refused, on the detail line, and take it away again after DROP_NOTE_MS (unless
        something newer has replaced it by then)."""
        self.detail_label.configure(text=text)
        if self._drop_note_job:
            self.after_cancel(self._drop_note_job)
        self._drop_note_job = self.after(DROP_NOTE_MS, lambda: self._clear_drop_note(text))

    def _clear_drop_note(self, text: str) -> None:
        self._drop_note_job = None
        if self.detail_label.cget("text") == text:
            self.detail_label.configure(text="")

    def _refresh_status(self) -> None:
        if not self.dataset:
            self.status_label.configure(text=f"{APP_TITLE} {VERSION}  ·  {COPYRIGHT}")
            return
        ds, info = self.dataset, self.dataset.info
        count = len(info.warnings)
        self.status_label.configure(
            text=f"Read {info.file_name} in {info.seconds:.0f} s · {ds.fixture_total:,} fixtures in "
                 f"{len(ds.competitions)} competitions · fmsave {info.fmsave_version} · "
                 f"{count} reader warning{'s' if count != 1 else ''} · the save is only read, never changed")

    def _reopen_last(self) -> None:
        last = self.settings.get("last_save")
        if last:
            self.open_save(last)

    # ----------------------------------------------------------------- competitions

    def _schedule_search(self) -> None:
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(200, self._fill_competition_list)

    def _fill_competition_list(self) -> None:
        self._search_job = None
        ds = self.dataset
        if not ds:
            return
        text = self.search_entry.get()
        kept = fd.competitions_in_country(ds, self.country_key)
        shown = [c for c in ds.competitions if (kept is None or c.id in kept) and fd.matches_search(c, self.names, text)]
        yours = [c for c in shown if c.is_yours]
        others = [c for c in shown if not c.is_yours]
        box = self.comp_list
        box.delete(0, "end")
        self.list_rows = []

        def heading(text: str) -> None:
            box.insert("end", text)
            section = self.theme.section
            box.itemconfig("end", fg=section, selectbackground=self.theme.competition_list[0], selectforeground=section)
            self.list_rows.append(None)

        def entry(comp: fd.CompetitionInfo) -> None:
            box.insert("end", f"   {fd.competition_list_label(comp, self.names)}  ({comp.team_count})")
            self.list_rows.append(comp.id)

        if yours:
            heading(f"YOUR CLUB · {ds.info.managed_club_name}")
            for comp in yours:
                entry(comp)
        if others:
            heading("OTHER COMPETITIONS")
            for comp in others:
                entry(comp)
        if not yours and not others:
            heading("No competition or club matches the search" if self.country_key is None
                    else "No competition in this country matches the search")
        self._mark_current_in_list()

    def _mark_current_in_list(self) -> None:
        box = self.comp_list
        box.selection_clear(0, "end")
        if self.comp_id in self.list_rows:
            index = self.list_rows.index(self.comp_id)
            box.selection_set(index)
            box.see(index)

    def _schedule_list_select(self) -> None:
        if self._list_job:
            self.after_cancel(self._list_job)
        self._list_job = self.after(120, self._on_list_select)

    def _on_list_select(self) -> None:
        self._list_job = None
        chosen = self.comp_list.curselection()
        if not chosen or not self.dataset:
            return
        comp_id = self.list_rows[chosen[0]]
        if comp_id is None:
            self._mark_current_in_list()       # headings are not selectable
            return
        if comp_id != self.comp_id:
            self.select_competition(comp_id)
        if self.view == HUB:
            # Picking a competition in the list means "show me it", so leave the hub for the
            # view the competitions were last browsed in.
            self.set_view(self.last_comp_view)

    def select_competition(self, comp_id: int, season: int | None = None) -> None:
        ds = self.dataset
        self.comp_id = comp_id
        options = fd.season_options(ds, comp_id)
        self.season_by_label = {label: key for key, label in options}
        self.season_menu.configure(values=[label for _, label in options] or ["–"])
        if season not in {key for key, _ in options}:
            season = fd.default_season(ds, comp_id)
        self.season_menu.set(next((label for key, label in options if key == season), "–"))
        self._mark_current_in_list()
        self._apply_season(season, keep_focus=False)

    def _apply_season(self, season: int | None, *, keep_focus: bool) -> None:
        ds = self.dataset
        self.season = season
        self.opponent_filter = None
        self._selection = None
        self.fixtures = fd.season_fixtures(ds, self.comp_id, season)
        self.labels = fd.team_labels(self.fixtures)
        self.short_labels = fd.team_labels(self.fixtures, short=True)
        self.club_names = fd.team_club_names(self.fixtures)
        ordered = sorted(self.labels.items(), key=lambda item: item[1].casefold())
        self.team_by_label = {label: team_id for team_id, label in ordered}
        if len(ordered) <= MAX_TEAM_CHOICES:
            choices = [label for _, label in ordered]
        else:
            choices = [self.labels[t] for t in ds.managed_team_ids if t in self.labels]
        self.team_box.configure(values=[ALL_TEAMS] + choices)
        if not (keep_focus and self.focus in self.labels):
            mine = [t for t in ds.managed_team_ids if t in self.labels]
            self.focus = ds.first_team_id if ds.first_team_id in self.labels else (mine[0] if mine else None)
        self._show_followed_team()
        self._update_club_tint()
        self._update_header()
        self.render()

    def _update_header(self) -> None:
        comp = self.dataset.by_id[self.comp_id]
        self.title_label.configure(text=fd.competition_title(comp, self.names))
        ids = f"competition id {comp.id}" + (f" · database id {comp.database_id}" if comp.database_id is not None else "")
        self.hint_label.configure(text=f"{fd.competition_hint(comp)}  ·  {ids}")

    def _country_names(self) -> dict[int, str]:
        return fd.country_names_from_settings(self.settings.get(COUNTRY_NAMES))

    def _refresh_country_menu(self) -> None:
        """Rebuild the Country menu's entries for the open save and the names given, keeping the choice if it
        is still on offer."""
        ds = self.dataset
        options = fd.country_options(ds, self._country_names()) if ds else ()
        self._country_options = options
        if self.country_key not in {o.key for o in options}:
            self.country_key = None
        labels = [o.label for o in options] or [fd.COUNTRY_ALL]
        self.country_menu.configure(values=labels, state="normal" if len(options) > 1 else "disabled")
        self.country_menu.set(next((o.label for o in options if o.key == self.country_key), fd.COUNTRY_ALL))

    def _on_country(self, label: str) -> None:
        option = next((o for o in self._country_options if o.label == label), None)
        if option is None or not self.dataset:
            return
        self.country_key = option.key
        self._fill_competition_list()
        if self.view == HUB:
            self.render()

    def name_country(self) -> None:
        """Give the selected nation a name, kept in the settings and used for every save."""
        if not self.dataset or not isinstance(self.country_key, int):
            return
        names = self._country_names()
        current = names.get(self.country_key, "")
        prompt = (f"Name for country {self.country_key}\n\n"
                  + (f"Currently: {current}\n" if current else "")
                  + "Leave empty to remove the name. Names apply to every save.")
        dialog = ctk.CTkInputDialog(title="Name this country", text=prompt)
        apply_window_icon(dialog)
        answer = dialog.get_input()
        if answer is None:
            return
        answer = answer.strip()
        if answer:
            names[self.country_key] = answer
        else:
            names.pop(self.country_key, None)
        self.settings[COUNTRY_NAMES] = fd.country_names_for_settings(names)
        self._write_settings()
        self._refresh_country_menu()
        self._hub_key = None                       # the hub filters by the menu, so refill it
        if self.view == HUB:
            self.render()

    def rename_competition(self) -> None:
        if not self.dataset or self.comp_id is None:
            return
        comp = self.dataset.by_id[self.comp_id]
        if comp.database_id is None:
            messagebox.showinfo("Can't name this competition",
                                "The save doesn't link this competition to the game's database, so a "
                                "name can't be kept for it.", parent=self)
            return
        current = self.names.get(comp.database_id, "")
        prompt = (f"Name for competition {comp.id}\n({fd.competition_hint(comp)})\n\n"
                  + (f"Currently: {current}\n" if current else "")
                  + "Leave empty to remove the name. Names are kept in competition_names.csv "
                    "and apply to every save.")
        dialog = ctk.CTkInputDialog(title="Name this competition", text=prompt)
        apply_window_icon(dialog)
        answer = dialog.get_input()
        if answer is None:
            return
        answer = answer.strip()
        if answer:
            self.names[comp.database_id] = answer
        else:
            self.names.pop(comp.database_id, None)
        try:
            fd.save_competition_names(NAMES_PATH, self.names)
        except OSError as exc:
            messagebox.showerror("Could not save the name", str(exc), parent=self)
        self._fill_competition_list()
        self._update_header()
        if self.view == HUB:
            self.render()                      # the hub lists the names too

    # ----------------------------------------------------------------- controls

    def _on_season(self, label: str) -> None:
        if label in self.season_by_label:
            self._apply_season(self.season_by_label[label], keep_focus=True)

    def _on_team(self, label: str) -> None:
        self.set_focus(self.team_by_label.get(label))

    def _on_team_typed(self, _event=None) -> None:
        text = self.team_box.get().strip().casefold()
        if not text or text == ALL_TEAMS.casefold():
            self.set_focus(None)
            return
        exact = [t for label, t in self.team_by_label.items() if label.casefold() == text]
        partial = [t for label, t in self.team_by_label.items() if text in label.casefold()]
        found = exact or partial
        if len(found) == 1:
            self.set_focus(found[0])
        else:
            self.detail_label.configure(
                text=f"No team in this season matches “{text}”." if not found else
                f"{len(found)} teams match “{text}”: type more of the name.")
            self._show_followed_team()

    def set_focus(self, team_id: int | None) -> None:
        self.opponent_filter = None
        self.focus = team_id if team_id in self.labels else None
        if team_id is not None and self.dataset:
            new_uid = self._followed_club_for(team_id)
            if new_uid is not None and new_uid != self._followed_uid:
                self._set_followed_uid(new_uid)
        self._show_followed_team()
        self._update_club_tint()
        self.render()

    def _show_followed_team(self) -> None:
        """Put the followed team's name in the team box. The box ignores set() while it is disabled,
        as it is in the hub, so it is enabled for the moment that takes."""
        disabled = self.team_box.cget("state") == "disabled"
        if disabled:
            self.team_box.configure(state="normal")
        self.team_box.set(self.labels[self.focus] if self.focus is not None else ALL_TEAMS)
        if disabled:
            self.team_box.configure(state="disabled")

    def _followed_club_for(self, team_id: int) -> fd.FollowedClub | None:
        """The club a team belongs to, in the scope that team is in (a reserve team follows the reserve side)."""
        identity = self.dataset.teams.get(team_id) if self.dataset else None
        if identity is None or identity.club_uid is None:
            return None
        return fd.FollowedClub(club_uid=identity.club_uid, scope=fd.SCOPE_RESERVE if identity.slot else fd.SCOPE_SENIOR,
                               name=identity.club_name or self.labels.get(team_id, ""))

    def _set_followed_uid(self, club: fd.FollowedClub | None, *, refresh: bool = False) -> None:
        """Update the followed club and start a background worker to build schedule/snapshot data. A `refresh`
        builds the same club again (new data arrived), so the Hub keeps showing what it has meanwhile."""
        self._followed_uid = club
        self._schedule_serial += 1
        serial = self._schedule_serial
        ds = self.dataset
        if ds is None or club is None:
            return
        self._update_club_tint()
        if not refresh:
            self._manager_hub_view.clear(f"Building {club.name or 'the club'}'s overview…")   # never the old club's
        edits = self._club_colour_edits()

        def _worker():
            sched = fd.club_schedule(ds, club)
            snap = fd.manager_snapshot(ds, club)
            season = fd.hub_season(ds, club)          # every step of the stepper, worked out once here
            self.events.put(("schedule_ready", (serial, sched, snap, self._roundel_book_for(sched, edits), season)))

        import threading
        threading.Thread(target=_worker, daemon=True).start()

    def _clear_followed_uid(self) -> None:
        """Remove the followed club and empty the Schedule and Hub at once."""
        self._followed_uid = None
        self._schedule_serial += 1
        self._update_club_tint()
        self._empty_club_views()
        if self.view not in (SCHEDULE, MANAGER_HUB) and self.dataset is not None and self.comp_id is not None:
            self.render()                           # the club's colours leave the sheets too

    def _empty_club_views(self) -> None:
        self._schedule_view.clear()
        self._manager_hub_view.clear(NO_CLUB_FOLLOWED)
        self._club_scope = NO_CLUB_FOLLOWED
        if self.view in (SCHEDULE, MANAGER_HUB):
            self.render()

    def _club_colour_edits(self) -> dict:
        edits = self.settings.get("club_colours")
        return dict(edits) if isinstance(edits, dict) else {}

    @staticmethod
    def _roundel_book_for(sched: fd.Schedule, edits: dict) -> dict:
        """Every theme's roundel for the followed club and each opponent (worker thread)."""
        return palette.roundel_book([sched.club.name, *(i.opponent_club for i in sched.items)],
                                    lambda name: club_colours.colours_for(name, edits), club_colours.initials)

    def _club_roundels(self) -> dict:
        return self._roundel_book.get(self.view_theme.name, {})

    def _retheme_club_views(self) -> None:
        """Repaint the Schedule and Hub in the window's colours: their roundels were worked out for every theme."""
        self._schedule_view.set_theme(self.view_theme, self._club_roundels())
        self._manager_hub_view.set_theme(self.view_theme, self._club_roundels())

    def _rebuild_roundels(self) -> None:
        """Work the roundels out again after a club's colours were edited, off the main thread."""
        sched, serial, edits = self._schedule_view._schedule, self._schedule_serial, self._club_colour_edits()
        if sched is None:
            return
        threading.Thread(target=lambda: self.events.put(
            ("roundels_ready", (serial, self._roundel_book_for(sched, edits)))), daemon=True).start()

    def install_schedule_views(self, sched: fd.Schedule, snap: fd.ManagerSnapshot, book: dict | None = None,
                               season: fd.HubSeason | None = None) -> None:
        """Install schedule and snapshot data into the custom views (main thread only). The Hub's stepper starts
        again at the save's own date."""
        theme = self.view_theme
        self._roundel_book = book or {}
        names = self._competition_names()
        self._schedule_view.install_schedule(sched, theme, self._club_roundels(), names)
        self._manager_hub_view.install_snapshot(snap, theme, names, self._club_roundels(), season)
        self._club_scope = f"{sched.club.name}: every competition, {sched.season_label} season · {sched.describe()}"
        if self.view in (SCHEDULE, MANAGER_HUB):
            self.render()

    def _competition_names(self) -> dict[int, str]:
        """Each competition's display name by competition id (self.names is keyed on the database id)."""
        if self.dataset is None:
            return {}
        return {cid: fd.competition_title(comp, self.names) for cid, comp in self.dataset.by_id.items()}

    def _on_schedule_select(self, item: fd.ScheduleItem) -> None:
        """A Schedule row was selected: the open Inspector follows it."""
        self._selection = ("match", item.fixture)
        self._refresh_inspector()

    def _on_schedule_inspect(self, item: fd.ScheduleItem) -> None:
        self._selection = ("match", item.fixture)
        self.open_inspector()

    def _follow_team(self, team_id: int) -> None:
        if team_id in self.labels:
            self.set_focus(team_id)
            return
        club = self._followed_club_for(team_id)
        if club is not None and club != self._followed_uid:
            self._set_followed_uid(club)

    def _schedule_menu(self, item: fd.ScheduleItem) -> list[MenuEntry]:
        """What a right-click on a Schedule row offers; the opponent entries need a club the save can resolve."""
        entries = [MenuEntry("Inspect match", lambda: self._on_schedule_inspect(item))]
        identity = self.dataset.teams.get(item.opponent_id) if self.dataset else None
        resolved = identity is not None and identity.club_uid is not None
        if resolved:
            entries.append(MenuEntry(f"Head-to-head with {item.opponent}",
                                     lambda: self._open_head_to_head(item.team_id, item.opponent_id)))
        entries.append(MenuEntry(f"Filter schedule to {item.opponent}",
                                 lambda: self._schedule_view.apply_search(item.opponent)))
        if resolved:
            entries.append(MenuEntry(f"Follow {item.opponent}", lambda: self._follow_team(item.opponent_id)))
        entries += [MENU_SEPARATOR, MenuEntry("Copy match line", lambda: self._copy_text(self._schedule_view.line_for(item)))]
        return entries

    def _copy_text(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)

    def _on_schedule_right_click(self, event, item: fd.ScheduleItem) -> None:
        menu = self._build_menu(self._schedule_menu(item))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _show_palette_key(self) -> None:
        """Open the command palette (the user can then search and follow a club)."""
        self._on_palette_key()

    def _view_count(self, view: str) -> str:
        """The count shown beside a view's name on the switch, or ''. Cheap: one coverage count, or one team's
        results. The followed team's run is named once it is RUN_NAMED_FROM long, with a + when a match with
        no recoverable score could make it longer."""
        if not self.dataset:
            return ""
        if view == HUB:
            return str(len(self.dataset.competitions))
        if self.comp_id is None:
            return ""
        if view == "Results":
            to_play = fd.coverage(self.fixtures).to_play
            return str(to_play) if to_play else ""
        if view == "Table" and self.focus is not None:
            run = fd.streaks(fd.team_steps(self.fixtures, self.focus, self.labels)).headline
            if run is not None and run.length >= RUN_NAMED_FROM:
                return RUN_LETTERS[run.kind] + run.short()
        return ""

    def _on_resize(self, event) -> None:
        """The window's width changed: once it has settled, show or hide the counts to match."""
        if event.widget is self:
            if self._resize_job:
                self.after_cancel(self._resize_job)
            self._resize_job = self.after(120, self._after_resize)

    def _after_resize(self) -> None:
        self._resize_job = None
        self._refresh_view_labels()
        self._layout_controls()

    def _layout_controls(self) -> None:
        """Lay the controls out on one line, or put the view's own switches on a second line under Season when
        the two do not fit side by side. The decision uses requested widths against the row's own width, which
        wrapping does not change; it wraps when they do not fit and unwraps only with CONTROLS_SPARE to spare."""
        line_one, own = self.controls_line_one, self.controls_own
        has_own = bool(own.pack_slaves())
        if not has_own:
            wrapped = False
        else:
            self.controls.update_idletasks()
            available = self.controls.winfo_width()
            wrapped = self.controls_wrapped
            if available > 1:
                needed = line_one.winfo_reqwidth() + own.winfo_reqwidth()
                if needed > available:
                    wrapped = True
                elif needed + self.px(CONTROLS_SPARE) <= available:
                    wrapped = False
        if (wrapped, has_own) == self._controls_shape:
            return
        self._controls_shape = (wrapped, has_own)
        self.controls_wrapped = wrapped
        line_one.pack_forget()
        own.pack_forget()
        side = "top" if wrapped else "left"
        line_one.pack(side=side, anchor="w")
        if has_own:
            own.pack(side=side, anchor="w", pady=(6, 0) if wrapped else 0)

    def _refresh_view_labels(self) -> None:
        """Put each view's count on the switch, if the window is wide enough for them: they must never squeeze
        the controls beside them. The buttons are rebuilt only when a label has changed."""
        room = self.winfo_width() >= self.px(COUNTS_MIN_WIDTH)
        labels = {}
        for view in SWITCH_VIEWS:
            count = self._view_count(view) if room else ""
            labels[view] = f"{view} ({count})" if count else view
        if labels != self.view_labels:
            self.view_labels = labels
            self.view_switch.configure(values=list(labels.values()))
        self.view_switch.set(self.view_labels.get(self.view, ""))

    def _on_view_label(self, label: str) -> None:
        """A press on the switch: its label stands for a view."""
        self.set_view(next(view for view, text in self.view_labels.items() if text == label))

    def set_view(self, view: str) -> None:
        self.view = view
        if view not in (HUB, SCHEDULE, MANAGER_HUB):
            self.last_comp_view = view
        self._sync_view_controls()
        self.render()                          # which also selects the view's label on the switch

    def _sync_view_controls(self) -> None:
        """Show the grouping or standings switch the view uses, and enable the season and team
        pickers only where they apply: the hub covers every competition at once."""
        for widget in (self.group_label, self.group_switch, self.split_label, self.split_switch,
                       self.analysis_label, self.analysis_switch, self.positions_mode_switch):
            widget.pack_forget()
        if self.view == "Results":
            self.group_label.pack(side="left", padx=(0, 6))
            self.group_switch.pack(side="left")
        elif self.view == "Table":
            self.split_label.pack(side="left", padx=(0, 6))
            self.split_switch.pack(side="left")
        elif self.view == ANALYSIS:
            self.analysis_label.pack(side="left", padx=(0, 6))
            self.analysis_switch.pack(side="left")
        state = "normal" if self.dataset and self.view not in (HUB, SCHEDULE, MANAGER_HUB) else "disabled"
        for widget in (self.season_menu, self.team_box, self.group_switch, self.split_switch,
                       self.analysis_switch, self.positions_mode_switch):
            widget.configure(state=state)
        self._layout_controls()
        self._update_header_buttons()

    def _update_header_buttons(self) -> None:
        """Mark the Schedule or Hub button as active when its view is open."""
        t = self.theme
        for button, view in ((self.schedule_button, SCHEDULE), (self.hub_button, MANAGER_HUB)):
            active = self.view == view
            button.configure(
                fg_color=t.accent[0] if active else t.quiet[0],
                hover_color=t.accent_hover if active else t.quiet_hover,
                text_color=t.accent[1] if active else t.quiet[1],
            )

    def _on_table_split(self, value: str) -> None:
        self.table_split = value
        self.render()

    def _on_analysis(self, value: str) -> None:
        self.analysis = value
        self.analysis_switch.set(value)
        self.render()

    def _on_positions_mode(self, value: str) -> None:
        self.positions_mode = value
        self.positions_mode_switch.set(value)
        self.render()

    def _on_group(self, value: str) -> None:
        self.group_by = value
        self.render()

    def _set_controls_state(self, state: str) -> None:
        for widget in (self.season_menu, self.team_box, self.view_switch, self.group_switch, self.split_switch,
                       self.analysis_switch, self.rename_button, self.details_button, self.search_entry,
                       self.inspector_button, self.schedule_button, self.hub_button):
            widget.configure(state=state)
        self.export_button.configure(state="disabled" if self._exporting else state)
        if state == "normal" and len(self._country_options) < 2:
            self.country_menu.configure(state="disabled")       # no nations to choose between

    # ----------------------------------------------------------------- exports

    def _show_export_menu(self) -> None:
        self._popup(self.export_menu, self.export_button)

    # Each "Copy for a post" item: what it copies and how it is built.
    POSTS = {"table": ("the table", fx.post_table), "team": ("your club's results", fx.post_team_results),
             "recent": ("the recent results", fx.post_recent_results)}

    def _post_missing(self, kind: str) -> str:
        """Why a "Copy for a post" item has nothing to copy just now."""
        if kind == "table":
            return f"this competition has more teams than a post can hold ({fx.POST_ROW_LIMIT})"
        if kind == "team":
            return "follow a club that has played this season to copy its results"
        return ("no match this season has been played yet, or the latest round is too large "
                f"for a post (more than {fx.POST_ROW_LIMIT} matches)")

    def _post_applies(self, kind: str) -> bool:
        """Whether a "Copy for a post" item has something to copy just now."""
        if not self.dataset or self.comp_id is None:
            return False
        if kind == "team":
            return self._has_played(self.focus)
        if kind == "recent":
            return any(f.played for f in self.fixtures)
        return len(self.labels) <= fx.POST_ROW_LIMIT

    def _has_played(self, team_id: int | None) -> bool:
        """Whether this club has a played match in the competition and season on show."""
        return team_id is not None and any(
            f.played and team_id in (f.home_team_id, f.away_team_id) for f in self.fixtures)

    def _refresh_post_menu(self) -> None:
        for index, kind in enumerate(("table", "team", "recent")):
            self.post_menu.entryconfigure(index, state="normal" if self._post_applies(kind) else "disabled")

    def copy_for_post(self, kind: str, club: int | None = None) -> None:
        """Copy the competition and season as shown for a forum post: Markdown and HTML on one copy.
        `club` stands in for the followed club (a right-click on another club's row) without following it."""
        if not self.dataset or self.comp_id is None:
            return
        what, build = self.POSTS[kind]
        if club is not None and club in self.labels:
            what = f"{self.labels[club]}'s results"
        request = fx.ExportRequest(self.dataset, self.comp_id, self.season, names=dict(self.names),
                                   focus=self.focus if club is None else club, group_by=self.group_by,
                                   theme=self.view_theme)
        post = build(fx.snapshot(request))
        if post is None:
            self.detail_label.configure(text=f"Nothing to copy: {self._post_missing(kind)}.")
            return
        try:
            both = clipboard.copy(post.markdown, post.html)
        except clipboard.ClipboardError:          # Tk's own clipboard still takes the text
            self.clipboard_clear()
            self.clipboard_append(post.markdown)
            both = False
        if both:
            self.detail_label.configure(text=f"Copied {what} for a post, as Markdown and as HTML.")
        else:
            self.detail_label.configure(
                text=f"Copied {what} for a post as Markdown only: the HTML version could not be written.")

    def export(self, kind: str) -> None:
        """Export the selected competition and season, as shown, on a background thread."""
        if not self.dataset or self.comp_id is None or self._exporting:
            return
        request = fx.ExportRequest(self.dataset, self.comp_id, self.season, names=dict(self.names),
                                   focus=self.focus, group_by=self.group_by, theme=self.view_theme)
        self._exporting = True
        self.export_button.configure(state="disabled", text="Exporting…")
        self.detail_label.configure(text=f"Exporting the {fx.KINDS[kind]}…")
        threading.Thread(target=self._export_worker, args=(kind, request, export_folder()), daemon=True).start()

    def _refresh_export_menu(self) -> None:
        """The whole-save workbook needs only a save, not a competition, and waits for a running export."""
        menu = self.export_menu
        index = next(i for i in range(menu.index("end") + 1)
                     if menu.type(i) == "command" and menu.entrycget(i, "label") == WHOLE_SAVE_LABEL)
        menu.entryconfigure(index, state="normal" if self.dataset and not self._exporting else "disabled")

    def export_whole_save(self) -> None:
        """Export every competition with a played match to one workbook, on a background thread."""
        if not self.dataset or self._exporting:
            return
        request = fx.SaveExportRequest(self.dataset, names=dict(self.names), focus=self.focus,
                                       group_by=self.group_by, theme=self.view_theme)
        self._exporting = True
        self.export_button.configure(state="disabled", text="Exporting…")
        self.detail_label.configure(text=f"Exporting the {fx.KINDS[fx.WHOLE_SAVE]}…")
        threading.Thread(target=self._export_worker, args=(fx.WHOLE_SAVE, request, export_folder()),
                         daemon=True).start()

    def _export_worker(self, kind: str, request, folder: Path) -> None:
        try:
            if kind == fx.WHOLE_SAVE:
                path = fx.export_save(request, folder)
            else:
                path = fx.export(kind, request, folder)
            self.events.put(("exported", (kind, path)))
        except fx.ExportFailed as exc:
            self.events.put(("export_failed", str(exc)))
        except Exception as exc:  # report anything unexpected rather than dying silently
            self._log_error(traceback.format_exc())
            self.events.put(("export_failed", f"Unexpected error while exporting:\n{type(exc).__name__}: {exc}"))

    def _finish_export(self, kind: str, payload) -> None:
        self._exporting = False
        self.export_button.configure(state="normal" if self.dataset else "disabled", text=EXPORT_LABEL)
        if kind == "export_failed":
            self.detail_label.configure(text="")
            messagebox.showerror("Could not export", payload, parent=self)
            return
        if payload[0] == "yearbook":
            _, plan = payload
            self.detail_label.configure(text=plan.message)
            if plan.action != "already" and messagebox.askyesno(
                    "Yearbook saved", f"{plan.message}\n\n{plan.path.name}\n\nin {plan.path.parent}.\n\nOpen it now?",
                    parent=self):
                self._open_path(plan.path)
            return
        export_kind, path = payload
        what = fx.KINDS[export_kind]
        self.detail_label.configure(text=f"Saved the {what} {path.name} in {path.parent}")
        if messagebox.askyesno("Export saved", f"Saved the {what}\n\n{path.name}\n\nin {path.parent}.\n\nOpen it now?",
                               parent=self):
            self._open_path(path)

    # ----------------------------------------------------------------- the Yearbook (PDF)

    @staticmethod
    def _banked_seasons() -> list[tuple[int, str]]:
        """(season, label) for each season in the archive, newest first; empty when nothing has been banked.
        Never creates the archive file."""
        if not ARCHIVE_PATH.exists():
            return []
        try:
            with archive.Archive.open(ARCHIVE_PATH) as book:
                return book.season_labels()
        except (archive.ArchiveError, sqlite3.Error):        # a locked or damaged file: no menu, not a broken one
            return []

    def _refresh_yearbook_menu(self) -> None:
        menu = self.yearbook_menu
        menu.delete(0, "end")
        for child in menu.winfo_children():                  # the previous season submenus
            child.destroy()
        seasons = self._banked_seasons()
        if not seasons or self._exporting:
            menu.add_command(label="Bank a save first" if not seasons else "Another export is under way",
                             state="disabled")
            return
        last_dates = self._banked_last_dates()
        for season, label in seasons:
            sub = tk.Menu(menu, tearoff=False)
            sub.add_command(label="Save the latest edition", command=lambda sn=season: self.export_yearbook(sn))
            editions = yearbook_editions.list_editions(export_folder(), label)
            if any(e.date == last_dates.get(season) for e in editions):
                sub.add_command(label="Build it again", command=lambda sn=season: self.export_yearbook(sn, rebuild=True))
            sub.add_command(label="Read before saving…", command=lambda sn=season: self.read_yearbook(sn))
            if editions:
                sub.add_separator()
            for edition in editions:
                sub.add_command(label=f"{edition.date_label} edition", command=lambda p=edition.path: self._open_path(p))
            menu.add_cascade(label=label, menu=sub)
        if self._followed_club():
            menu.add_separator()
            menu.add_checkbutton(label=f"Mark {self._followed_club()} in bold", variable=self.mark_club_var)

    @staticmethod
    def _banked_last_dates() -> dict[int, object]:
        """Each banked season's last in-game date (what an edition's file is named from)."""
        try:
            with archive.Archive.open(ARCHIVE_PATH) as book:
                return {season: book.coverage(season).last_date for season, _ in book.season_labels()}
        except (archive.ArchiveError, sqlite3.Error):
            return {}

    def export_yearbook(self, season: int, rebuild: bool = False) -> None:
        """Save one season's Yearbook as an edition from the archive, on a background thread."""
        if self._exporting:
            return
        self._exporting = True
        self.export_button.configure(state="disabled", text="Exporting…")
        self.detail_label.configure(text="Building the Yearbook…")
        threading.Thread(target=self._yearbook_worker, args=(season, dict(self.names), export_folder(),
                                                             self._marked_club_uid(), rebuild), daemon=True).start()

    def _marked_club_uid(self) -> int | None:
        """The followed club's uid when the Yearbook menu's tick is on, else None."""
        if not self.mark_club_var.get():
            return None
        if self._followed_uid is not None:
            return self._followed_uid.club_uid
        if self.focus is None:
            return None
        return fd.team_club_uids(self.fixtures).get(self.focus)

    def _yearbook_worker(self, season: int, names: dict[int, str], folder: Path, marked: int | None = None,
                         rebuild: bool = False) -> None:
        try:
            with archive.Archive.open(ARCHIVE_PATH) as book:
                plan = yearbook_editions.save_edition(book, season, names, folder, rebuild, marked)
            self.events.put(("exported", ("yearbook", plan)))
        except archive.ArchiveError as exc:
            self.events.put(("export_failed", str(exc)))
        except Exception as exc:  # report anything unexpected rather than dying silently
            self._log_error(traceback.format_exc())
            self.events.put(("export_failed", f"Unexpected error while building the Yearbook:\n{type(exc).__name__}: {exc}"))

    def read_yearbook(self, season: int) -> None:
        """Build one season's Yearbook on a background thread and open it in the reading window. Nothing is saved."""
        if self._exporting:
            return
        self._exporting = True
        self.export_button.configure(state="disabled", text="Reading…")
        self.detail_label.configure(text="Building the Yearbook…")
        threading.Thread(target=self._read_worker, args=(season, dict(self.names), self._marked_club_uid()),
                         daemon=True).start()

    @staticmethod
    def _build_volume(book: archive.Archive, season: int, names: dict[int, str],
                      marked: int | None) -> yearbook_read.Volume:
        built = yearbook.build_yearbook(book, season, names, marked)
        return yearbook_read.volume(built, season, book.identity(), built.coverage)

    def _yearbook_job(self, job: Callable[[], None]) -> None:
        """Run a Yearbook job on this worker thread, reporting failures as the exports do."""
        try:
            job()
        except archive.ArchiveError as exc:
            self.events.put(("export_failed", str(exc)))
        except Exception as exc:
            self._log_error(traceback.format_exc())
            self.events.put(("export_failed", f"Unexpected error while building the Yearbook:\n{type(exc).__name__}: {exc}"))

    def _read_worker(self, season: int, names: dict[int, str], marked: int | None) -> None:
        def job() -> None:
            with archive.Archive.open(ARCHIVE_PATH) as book:
                volume = self._build_volume(book, season, names, marked)
            self.events.put(("yearbook_ready", volume))
        self._yearbook_job(job)

    def show_yearbook_reader(self, volume: yearbook_read.Volume) -> None:
        """Show a volume in the reading window at its bookmarked page: in the open window when there is one (the
        volume shown before is bookmarked first), else in a new one."""
        reader = self.yearbook_reader if self.yearbook_reader is not None and self.yearbook_reader.winfo_exists() else None
        if reader is not None:
            reader.leave()
        bookmark = yearbook_read.read_bookmark(self.settings.get(BOOKMARKS), volume.archive_id, volume.season)
        start = yearbook_read.page_index(volume.pages, bookmark) or 0
        if reader is not None:
            reader.load(volume, start)
            reader.bring_forward()
            return
        self.yearbook_reader = YearbookReader(self, volume, lambda v: self.save_reader_volume(v), self._bookmark_page,
                                              start, self.settings.get(READER_MODE), self._remember_reader_mode)
        apply_window_icon(self.yearbook_reader)

    def _remember_schedule_gaps(self, show: bool) -> None:
        self.settings[SCHEDULE_GAPS] = show
        self._write_settings()

    def _remember_reader_mode(self, mode: str) -> None:
        self.settings[READER_MODE] = mode
        self._write_settings()

    def _bookmark_page(self, volume: yearbook_read.Volume, page_key: str) -> None:
        self.settings[BOOKMARKS] = yearbook_read.with_bookmark(self.settings.get(BOOKMARKS), volume.archive_id,
                                                               volume.season, volume.edition, page_key)
        self._write_settings()

    def _start_yearbook_job(self, text: str, target: Callable, *args) -> bool:
        if self._exporting:
            return False
        self._exporting = True
        self.export_button.configure(state="disabled", text="Exporting…")
        self.detail_label.configure(text=text)
        threading.Thread(target=target, args=args, daemon=True).start()
        return True

    def save_reader_volume(self, volume: yearbook_read.Volume) -> None:
        """Save the book in the reading window. When the archive still holds the snapshot it was built from, that
        book is saved as it stands; when a newer save has been banked since, both editions are named and the user
        chooses (handled in "yearbook_moved_on")."""
        self._start_yearbook_job("Checking the archive…", self._snapshot_worker, volume, export_folder())

    def _snapshot_worker(self, volume: yearbook_read.Volume, folder: Path) -> None:
        def job() -> None:
            current = None
            if ARCHIVE_PATH.exists():
                with archive.Archive.open(ARCHIVE_PATH) as book:
                    if book.identity() == volume.archive_id:
                        current = book.coverage(volume.season)
            if current is not None and volume.matches(current):
                self.events.put(("exported", ("yearbook", yearbook_editions.save_built(volume.book, folder))))
            else:
                self.events.put(("yearbook_moved_on", (volume, current)))
        self._yearbook_job(job)

    def _save_snapshot_worker(self, volume: yearbook_read.Volume, folder: Path) -> None:
        self._yearbook_job(lambda: self.events.put(
            ("exported", ("yearbook", yearbook_editions.save_built(volume.book, folder)))))

    def _refresh_worker(self, season: int, names: dict[int, str], marked: int | None, folder: Path) -> None:
        def job() -> None:
            with archive.Archive.open(ARCHIVE_PATH) as book:
                volume = self._build_volume(book, season, names, marked)
            self.events.put(("yearbook_refreshed", (volume, yearbook_editions.save_built(volume.book, folder))))
        self._yearbook_job(job)

    def _choose_edition(self, volume: yearbook_read.Volume, current: archive.BookCoverage | None) -> None:
        """The archive has moved on since the book being read was built: name both editions and save the one chosen."""
        parent = self.yearbook_reader if self.yearbook_reader is not None and self.yearbook_reader.winfo_exists() else self
        reading = volume.edition_label
        if current is not None and current.last_date is not None:
            newer = yearbook_editions.date_text(current.last_date)
            answer = messagebox.askyesnocancel(
                "A newer save has been banked",
                f"The book you are reading is the {reading} edition. Since it was built, the archive has banked a "
                f"newer save, and the {volume.season_label} Yearbook would now be the {newer} edition.\n\n"
                f"Yes: refresh the reader to the {newer} edition and save that.\n"
                f"No: save the {reading} edition you are reading.\n"
                f"Cancel: save nothing.", parent=parent)
        else:
            answer = False if messagebox.askyesno(
                "The archive has changed",
                f"The archive no longer holds the saves this book was built from.\n\n"
                f"Save the {reading} edition you are reading?", parent=parent) else None
        if answer is None:
            return
        if answer:
            self._start_yearbook_job("Building the newer edition…", self._refresh_worker, volume.season,
                                     dict(self.names), self._marked_club_uid(), export_folder())
        else:
            self._start_yearbook_job("Saving the edition you are reading…", self._save_snapshot_worker, volume,
                                     export_folder())

    def open_export_folder(self) -> None:
        folder = export_folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Could not open the export folder", f"{folder}\n\n{exc.strerror or exc}", parent=self)
            return
        self._open_path(folder)

    def _open_path(self, path: Path) -> None:
        """Open a file in its usual program, or a folder in Explorer."""
        try:
            os.startfile(path)
        except (AttributeError, OSError) as exc:     # AttributeError: not on Windows
            messagebox.showerror("Could not open it", f"{path}\n\n{getattr(exc, 'strerror', None) or exc}",
                                 parent=self)

    # ----------------------------------------------------------------- rendering

    def render(self) -> None:
        self._refresh_view_labels()            # the counts follow the competition, season, team and save
        self._refresh_inspector()
        self._show_filter_button()
        self._show_zone_key()                  # the Table and Positions views put it back
        if not self.dataset:
            return
        if self.view == HUB:
            self._render_competitions()
            return
        if self.view in (SCHEDULE, MANAGER_HUB):
            self._show_custom_view(self._schedule_view if self.view == SCHEDULE else self._manager_hub_view)
            self.coverage_label.configure(text=self._club_scope)
            self.note_label.configure(text="")
            self.detail_label.configure(text="")
            return
        if self.comp_id is None:
            return
        text = fd.coverage(self.fixtures).describe()
        if self.focus is not None:
            mine = fd.coverage(f for f in self.fixtures if self.focus in (f.home_team_id, f.away_team_id))
            text += f"     |     {self.labels[self.focus]}: {mine.describe()}"
        self.coverage_label.configure(text=text)
        self.detail_label.configure(text="")
        if not self.fixtures:
            self.note_label.configure(text="")
            self._show_message("No fixtures for this season.")
            return
        {"Results": self._render_results, "Grid": self._render_grid, "Table": self._render_table,
         ANALYSIS: self._render_analysis}[self.view]()

    def _show_sheet(self, name: str) -> Sheet:
        self.message.grid_remove()
        self.bracket_view.grid_remove()
        self._schedule_view.grid_remove()
        self._manager_hub_view.grid_remove()
        self._shown = name
        for key, sheet in self.sheets.items():
            if key == name:
                sheet.grid()
            else:
                sheet.grid_remove()
        return self.sheets[name]

    def _show_message(self, text: str) -> None:
        self._shown = None
        self.bracket_view.grid_remove()
        self._schedule_view.grid_remove()
        self._manager_hub_view.grid_remove()
        for sheet in self.sheets.values():
            sheet.grid_remove()
        self.message_label.configure(text=text)
        self.reopen_button.pack_forget()
        self.message.grid()

    def _show_custom_view(self, widget) -> None:
        """Show one of the custom (non-sheet) views, hiding everything else."""
        self.message.grid_remove()
        self.bracket_view.grid_remove()
        for sheet in self.sheets.values():
            sheet.grid_remove()
        for w in (self._schedule_view, self._manager_hub_view):
            if w is widget:
                w.grid()
            else:
                w.grid_remove()

    def _show_welcome(self) -> None:
        self._show_message("Open a Football Manager 27 save to browse its fixtures and results.\n\n"
                           "Saves are in Documents\\Sports Interactive\\Football Manager 27\\games. "
                           "The save is only read, never changed.")
        last = self.settings.get("last_save")
        if last and Path(last).is_file():
            self.reopen_button.configure(text=f"Open {Path(last).name}")
            self.reopen_button.pack(pady=(0, 40))

    def _show_zone_key(self, zones: Iterable[str] = ()) -> None:
        """The colour key under the sheet: a chip and its meaning for each zone shown, or nothing."""
        for child in self.zone_key.winfo_children():
            child.destroy()
        theme, shown = self.view_theme, set(zones)
        self.zone_key_meanings = []
        for zone, _word, meaning in palette.ZONE_LEGEND:
            if zone in shown and zone in theme.zones:
                chip = ctk.CTkFrame(self.zone_key, width=14, height=14, corner_radius=3, fg_color=theme.zones[zone][0])
                chip.pack(side="left", padx=(14 if self.zone_key_meanings else 0, 6))
                label = meaning[0].upper() + meaning[1:]
                ctk.CTkLabel(self.zone_key, text=label, text_color=theme.text).pack(side="left")
                self.zone_key_meanings.append(label)
        if self.zone_key_meanings:
            self.zone_key.grid()
        else:
            self.zone_key.grid_remove()

    @staticmethod
    def _paint(sheet: Sheet, row: int, column: int, colours, canvas: str = "table") -> None:
        bg, fg = colours
        options = {k: v for k, v in (("bg", bg), ("fg", fg)) if v is not None}
        if options:
            sheet.highlight_cells(row=row, column=column, canvas=canvas, redraw=False, **options)

    def _render_results(self) -> None:
        pair = self.opponent_filter
        if pair is None:
            focus, fixtures = self.focus, self.fixtures
        else:      # only the matches between the two clubs, whoever is followed
            focus = None
            fixtures = tuple(f for f in self.fixtures if {f.home_team_id, f.away_team_id} == set(pair))
        rows = fd.timeline(fixtures, self.labels, group_by=self.group_by, focus_team=focus)
        self.result_rows = rows
        headers = ["Date", "KO", "Home", "Score", "xG", "Away", "Round"] + (["Res", "Pts"] if focus is not None else [])
        blank = [""] * (len(headers) - 1)
        data = [[r.heading, *blank] if r.is_heading else
                [r.date, r.time, r.home, r.score, "", r.away, r.round]
                + ([r.result, r.points] if focus is not None else [])
                for r in rows]
        sheet = self._show_sheet("Results")
        sheet.set_sheet_data(data, reset_col_positions=True, reset_row_positions=True, redraw=False,
                             reset_highlights=True)
        sheet.headers(headers, redraw=False)
        names = [r.home for r in rows] + [r.away for r in rows]
        team_width = self._text_width(names, minimum=180)
        widths = [self.px(110), self.px(56), team_width, self.px(64), self.px(86), team_width, self.px(100),
                  self.px(46), self.px(54)]
        sheet.set_column_widths(widths[:len(headers)])
        sheet.align_columns([1, 3, 4, 6, 7, 8][: 4 if focus is None else 6], align="center", align_header=True,
                            redraw=False)
        theme = self.view_theme
        first_unplayed = None
        for i, r in enumerate(rows):
            if r.is_heading:
                sheet.highlight_rows(i, bg=theme.heading[0], fg=theme.heading[1], redraw=False, end_of_screen=True)
                continue
            if first_unplayed is None and r.kind == fd.SCHEDULED:
                first_unplayed = i
            if focus is not None and r.result:
                self._paint(sheet, i, 3, theme.colours[r.result])
                self._paint(sheet, i, 7, theme.colours[r.result])
            elif r.kind in (fd.UNAVAILABLE, fd.SCHEDULED):
                self._paint(sheet, i, 3, theme.colours[r.kind])
            if focus is not None:
                self._paint(sheet, i, 2 if r.home_id == focus else 5, (None, theme.link))
        self._fill_results_xg(sheet)
        sheet.refresh()
        # Open on the most recent results: just before the first match still to play.
        target = len(rows) - 1 if first_unplayed is None else max(0, first_unplayed - 6)
        sheet.set_yview(target / max(len(rows), 1) if target > 0 else 0.0)
        self.note_label.configure(text=self._results_note())
        self._show_filter_button()

    def _show_filter_button(self) -> None:
        """The Clear button sits at the right of the note while Results is filtered, and nowhere else."""
        if self.view == "Results" and self.opponent_filter is not None:
            self.filter_clear.grid()
        else:
            self.filter_clear.grid_remove()

    def _fill_results_xg(self, sheet: Sheet) -> None:
        """The Results sheet's xG column. For the team you follow, the cell is green or red where it
        scored more or fewer goals than its expected goals, beyond the dead zone."""
        for i, r in enumerate(self.result_rows):
            xg = fd.xg_for(self.dataset, r.fixture) if r.fixture is not None else None
            if xg is None:
                continue
            sheet.set_cell_data(i, RESULTS_XG_COLUMN, xg.describe(), redraw=False)
            f = r.fixture
            if self.focus in (r.home_id, r.away_id) and fd.has_score(f):
                home = r.home_id == self.focus
                tint = fd.xg_tint((f.home_goals - xg.home) if home else (f.away_goals - xg.away))
                if tint:
                    self._paint(sheet, i, RESULTS_XG_COLUMN, self.view_theme.colours["W" if tint == fd.XG_ABOVE else "L"])

    def _results_note(self) -> str:
        note = []
        if self.opponent_filter is not None:
            home, away = (self.labels.get(t, f"Team {t}") for t in self.opponent_filter)
            note.append(f"Showing only {home} v {away} this season.   ")
        if self.focus is not None and self.opponent_filter is None:
            note.append("Res and Pts are for the team you follow; points count 3 for a win and 1 for a draw."
                        " * = a played match has no recoverable score, so the total is a minimum.")
        note.append("“n/a” = played, but no score could be recovered from the save. Click a match for details.")
        note.append(fd.xg_coverage(self.dataset, self.fixtures).describe())
        if self.focus is not None:
            note.append(f"xG is green where the team you follow scored more than {fd.XG_DEAD_ZONE} goals above "
                        "its expected goals, red where it scored that much below.")
        return " ".join(note)

    def _render_grid(self) -> None:
        teams = fd.teams_in(self.fixtures)
        grid = fd.fixture_grid(self.fixtures, self.labels, self.short_labels)
        self.grid_data = grid
        if grid is None:
            self.note_label.configure(text="")
            self._show_message(f"This season has {len(teams):,} teams, too many for a grid "
                               f"(the limit is {fd.MAX_GRID_TEAMS}). Use Results instead, and pick a team to follow.")
            return
        sheet = self._show_sheet("Grid")
        sheet.set_sheet_data([[cell.text for cell in row] for row in grid.cells], reset_col_positions=True,
                             reset_row_positions=True, redraw=False, reset_highlights=True)
        sheet.headers(list(grid.column_labels), redraw=False)
        sheet.row_index(list(grid.row_labels), redraw=False)
        sheet.set_index_width(self._text_width(grid.row_labels, minimum=150), redraw=False)
        widths = []
        for column, label in enumerate(grid.column_labels):
            texts = [label] + [row[column].text for row in grid.cells]
            widths.append(self._text_width(texts, minimum=56, padding=16))
        sheet.set_column_widths(widths)

        focus_idx = grid.team_ids.index(self.focus) if self.focus in grid.team_ids else None
        colours, focus_colours = self.view_theme.colours, self.view_theme.focus

        for r, row in enumerate(grid.cells):
            for c, cell in enumerate(row):
                if cell.kind == "self":
                    self._paint(sheet, r, c, colours["self"])
                elif focus_idx is not None and r == focus_idx:
                    # Followed team at home: Home Win is a win (W), Away Win is a loss (L)
                    if cell.kind == fd.HOME_WIN:
                        self._paint(sheet, r, c, colours["W"])
                    elif cell.kind == fd.DRAW:
                        self._paint(sheet, r, c, colours["D"])
                    elif cell.kind == fd.AWAY_WIN:
                        self._paint(sheet, r, c, colours["L"])
                    elif cell.kind in colours:
                        self._paint(sheet, r, c, colours[cell.kind])
                elif focus_idx is not None and c == focus_idx:
                    # Followed team away: Away Win is a win (W), Home Win is a loss (L)
                    if cell.kind == fd.AWAY_WIN:
                        self._paint(sheet, r, c, colours["W"])
                    elif cell.kind == fd.DRAW:
                        self._paint(sheet, r, c, colours["D"])
                    elif cell.kind == fd.HOME_WIN:
                        self._paint(sheet, r, c, colours["L"])
                    elif cell.kind in colours:
                        self._paint(sheet, r, c, colours[cell.kind])
                elif cell.kind in colours:
                    self._paint(sheet, r, c, colours[cell.kind])

        if focus_idx is not None:
            self._paint(sheet, focus_idx, 0, focus_colours, canvas="index")
            sheet.highlight_cells(column=focus_idx, canvas="header", bg=focus_colours[0], fg=focus_colours[1],
                                  redraw=False)
            team_name = self.labels.get(self.focus, "Followed team")
            self.note_label.configure(
                text=f"Followed team perspective ({team_name}): row & column show results from their viewpoint "
                     f"(Green: win · Amber: draw · Red: loss). Other cells show Home Win (green) / Draw (amber) / Away Win (red)."
            )
        else:
            self.note_label.configure(text=GRID_LEGEND)
        sheet.refresh()

    def _render_table(self) -> None:
        result = fd.standings(self.dataset, self.comp_id, self.season, self.fixtures, self.labels, split=self.table_split)
        theme = self.view_theme
        headers = ["Pos", "Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts", "Form"]
        data, self.table_rows, headings, focus_rows, zone_cells = [], [], [], [], []
        pills: dict[tuple[int, int], str] = {}
        differences: dict[int, int] = {}              # row → goal difference
        for title, rows in result.groups:
            if title:
                headings.append(len(data))
                data.append([title] + [""] * (len(headers) - 1))
                self.table_rows.append(None)
            for r in rows:
                row_idx = len(data)
                if r.team_id == self.focus:
                    focus_rows.append(row_idx)
                if r.zone and r.zone in theme.zones:
                    zone_cells.append((row_idx, 0, theme.zones[r.zone]))
                gd = r.goal_difference
                data.append([r.position, r.team, r.played, r.won, r.drawn, r.lost, r.goals_for, r.goals_against,
                             f"{gd:+d}" if gd else "0", r.points, "  ".join(r.form)])
                self.table_rows.append(r.team_id)
                differences[row_idx] = gd
                if r.form:
                    pills[(row_idx, FORM_COLUMN)] = r.form
        sheet = self._show_sheet("Table")
        sheet.set_sheet_data(data, reset_col_positions=True, reset_row_positions=True, redraw=False,
                             reset_highlights=True)
        sheet.headers(headers, redraw=False)
        sheet.row_index([""] * len(data), redraw=False)
        sheet.set_index_width(self.px(5), redraw=False)
        team_width = self._text_width([row[1] for row in data], minimum=200)
        sheet.set_column_widths([self.px(46), team_width] + [self.px(44)] * 7 + [self.px(50), self.px(130)])
        sheet.align_columns([0] + list(range(2, 11)), align="center", align_header=True, redraw=False)
        for i in headings:
            sheet.highlight_rows(i, bg=theme.heading[0], fg=theme.heading[1], redraw=False, end_of_screen=True)
        for i in focus_rows:
            sheet.highlight_rows(i, bg=theme.focus[0], fg=theme.focus[1], highlight_index=False, redraw=False,
                                 end_of_screen=False)
        self.zone_edges = {}
        for row_idx, col_idx, colours in zone_cells:
            self._paint(sheet, row_idx, col_idx, colours)
            self.zone_edges[row_idx] = colours[0]
            sheet.highlight_cells(row=row_idx, canvas="index", bg=colours[0], redraw=False)
        # The form letters stay in their cells for copying, written in the cell's own colour, under the pills.
        for row_idx, _column in pills:
            hidden = theme.focus[0] if row_idx in focus_rows else theme.table[0]
            sheet.highlight_cells(row=row_idx, column=FORM_COLUMN, bg=hidden if row_idx in focus_rows else None,
                                  fg=hidden, redraw=False)
        scale = max([10, *(abs(gd) for gd in differences.values())])
        bars = {(row_idx, GD_COLUMN): gd / scale for row_idx, gd in differences.items() if gd}
        sparks = {}
        if len(self.table_rows) <= SPARK_ROW_LIMIT:
            spark_places = fd.place_sparks(fd.positions_by_matchday(
                self.dataset, self.comp_id, self.season, self.fixtures, self.labels))
            sparks = {(row_idx, FORM_COLUMN): spark_places[team_id] for row_idx, team_id in enumerate(self.table_rows)
                      if team_id in spark_places}
        self.overlays["Table"].show(pills, bars, theme.colours, (theme.colours["W"][0], theme.colours["L"][0]),
                                    sparks=sparks, spark_colour=theme.muted)
        sheet.refresh()
        zones = {r.zone for _, rows in result.groups for r in rows if r.zone}
        note = [result.note]
        if zones:
            note.append(result.zones_note)
        note.append("Click a team to follow it.")
        self.note_label.configure(text=" ".join(part for part in note if part))
        self._show_zone_key(zones)

    def _render_analysis(self) -> None:
        self.overlays[ANALYSIS].clear()          # the Form panel draws its pills again
        if self.analysis != "Positions":
            self.positions_mode_switch.pack_forget()
            self._layout_controls()
        {"Form": self._render_form, "Positions": self._render_positions, "xG": self._render_xg,
         "Ties": self._render_ties, "Bracket": self._render_bracket}[self.analysis]()

    def _table_order(self) -> tuple[int, ...]:
        """Teams in the order of this season's table: the game's own where it stores one."""
        return fd.standings(self.dataset, self.comp_id, self.season, self.fixtures, self.labels).order

    def _fill_analysis(self, headers: list[str], data: list[list], widths: list[int], centred: list[int]) -> Sheet:
        sheet = self._show_sheet(ANALYSIS)
        sheet.set_sheet_data(data, reset_col_positions=True, reset_row_positions=True, redraw=False,
                             reset_highlights=True)
        sheet.headers(headers, redraw=False)
        sheet.set_column_widths(widths)
        sheet.align_columns(centred, align="center", align_header=True, redraw=False)
        return sheet

    def _render_form(self) -> None:
        guide = fd.form_guide(self.fixtures, self.labels, order=self._table_order())
        length = fd.FORM_LENGTH
        strip_headers = [" "] * length       # a space: tksheet shows a column letter for an empty header
        strip_headers[length // 2] = "Form"
        headers = (["Team"] + strip_headers + ["Current run", "PPG", "P", "W", "D", "L", "GF", "GA", "CS", "FTS",
                                               "Wins", "Unbeaten", "No win", "Defeats"])
        data, self.analysis_rows = [], []
        for r in guide.rows:
            t, longest = r.totals, r.streaks.longest
            letters = [""] * (length - len(r.strip.steps)) + [step.outcome for step in r.strip.steps]
            data.append([r.team, *letters, r.streaks.describe_current() if r.steps else "", t.ppg_text(),
                         t.played, t.won, t.drawn, t.lost, t.goals_for, t.goals_against, t.clean_sheets,
                         t.failed_to_score, *(longest[kind].short() for kind in fd.STREAK_KINDS)])
            self.analysis_rows.append(r.team_id)
        run = length + 1
        widths = ([self._text_width([row[0] for row in data], minimum=180)] + [self.px(36)] * length
                  + [self._text_width([row[run] for row in data], minimum=120), self.px(54)] + [self.px(40)] * 8
                  + [self.px(66)] * 4)
        sheet = self._fill_analysis(headers, data, widths, [c for c in range(1, len(headers)) if c != run])
        theme = self.view_theme
        pills: dict[tuple[int, int], str] = {}
        for i, r in enumerate(guide.rows):
            followed = r.team_id == self.focus
            if followed:
                sheet.highlight_rows(i, bg=theme.focus[0], fg=theme.focus[1], redraw=False, end_of_screen=False)
            # Each letter stays in its cell for copying, written in the cell's own colour, under its pill.
            hidden = theme.focus[0] if followed else theme.table[0]
            for column, letter in enumerate(data[i][1:run], start=1):
                if letter:
                    pills[(i, column)] = letter
                    sheet.highlight_cells(row=i, column=column, bg=hidden if followed else None, fg=hidden,
                                          redraw=False)
        self.overlays[ANALYSIS].show(pills, {}, theme.colours, (theme.colours["W"][0], theme.colours["L"][0]))
        sheet.refresh()
        note = [guide.describe(),
                "Form: the last five matches, oldest first. PPG: points per game. CS: clean sheets. FTS: failed to "
                "score. Wins, Unbeaten, No win and Defeats: each team's longest run this season; + = it may be "
                "longer and ? = not known, because a match next to it has no recoverable score. * = the figure "
                "leaves out a match with no recoverable score. Click a team to follow it."]
        records = fd.season_records(guide)
        if records:
            text = "Records: " + "  ·  ".join(record.describe() for record in records)
            if any(record.incomplete for record in records):
                text += ".  * = a missing score could change this record."
            note.append(text)
        self.note_label.configure(text="\n".join(note))
        followed = next((r for r in guide.rows if r.team_id == self.focus and r.strip.steps), None)
        if followed:
            self.detail_label.configure(
                text=f"{followed.team}, last {len(followed.strip.steps)}: "
                     + "  ·  ".join(step.describe() for step in followed.strip.steps)
                     + f"  ·  {followed.strip.describe()}")

    def _render_positions(self) -> None:
        comparison = fd.season_comparison(self.dataset, self.comp_id, self.labels)
        if comparison is not None:
            self.positions_mode_switch.pack(side="left", padx=(12, 0))
            self._layout_controls()
        if comparison is not None and self.positions_mode == "Season vs season":
            self._render_season_comparison(comparison)
            return
        self._render_matchday_chart()

    def _render_matchday_chart(self) -> None:
        chart = fd.positions_by_matchday(self.dataset, self.comp_id, self.season, self.fixtures, self.labels)
        if chart is None or not chart.matchdays:
            self.note_label.configure(text="")
            self._show_message(chart.describe() if chart else
                               "This competition has no matchdays (it is a cup or a set of friendlies), so "
                               "there are no league positions to chart.")
            return
        theme = self.view_theme
        headers = ["Team"] + [str(matchday) for matchday in chart.matchdays]
        blank = [""] * len(chart.matchdays)
        data, self.analysis_rows, headings, followed, zone_cells = [], [], [], [], []
        for group in chart.groups:
            if group.title:
                headings.append(len(data))
                data.append([group.title, *blank])
                self.analysis_rows.append(None)
            for track in group.tracks:
                row_idx = len(data)
                if track.team_id == self.focus:
                    followed.append(row_idx)
                for column, position in enumerate(track.positions, start=1):
                    zone = group.zones[position - 1] if position <= len(group.zones) else ""
                    if zone in theme.zones:
                        zone_cells.append((row_idx, column, theme.zones[zone]))
                data.append([track.team, *track.positions])
                self.analysis_rows.append(track.team_id)
        widths = [self._text_width([row[0] for row in data], minimum=180)] + [self.px(34)] * len(chart.matchdays)
        sheet = self._fill_analysis(headers, data, widths, list(range(1, len(headers))))
        for i in headings:
            sheet.highlight_rows(i, bg=theme.heading[0], fg=theme.heading[1], redraw=False, end_of_screen=True)
        for i in followed:
            sheet.highlight_rows(i, bg=theme.focus[0], fg=theme.focus[1], redraw=False, end_of_screen=False)
        for row_idx, column, colours in zone_cells:
            self._paint(sheet, row_idx, column, colours)
        sheet.refresh()
        note = [chart.describe(), "Columns are matchdays; each cell is the team's place after it."]
        zones = {zone for group in chart.groups for zone in group.zones if zone}
        if zones:
            note.append(chart.zones_note)
        note.append("Click a team to follow it.")
        self.note_label.configure(text=" ".join(part for part in note if part))
        self._show_zone_key(zones)

    def _render_season_comparison(self, comparison: fd.SeasonComparison) -> None:
        headers = ["Team"]
        for column in comparison.columns:
            headers.extend([f"{column.label} Pos", f"{column.label} Pts"])
        headers.append("Δ Pos")
        theme = self.view_theme
        data, self.analysis_rows, zone_cells = [], [], []
        for row in comparison.rows:
            row_idx = len(data)
            cells: list = [row.team]
            for n, cell in enumerate(row.cells):
                if cell is None:
                    cells.extend(["—", "—"])
                else:
                    cells.extend([cell.position, cell.points])
                    if cell.zone and cell.zone in theme.zones:
                        zone_cells.append((row_idx, 1 + n * 2, theme.zones[cell.zone]))
            if row.delta is None:
                cells.append("—")
            else:
                cells.append(f"{row.delta:+d}" if row.delta else "0")
            data.append(cells)
            self.analysis_rows.append(row.team_id)
        widths = ([self._text_width([row[0] for row in data], minimum=200)]
                  + [self.px(70), self.px(50)] * len(comparison.columns)
                  + [self.px(60)])
        sheet = self._fill_analysis(headers, data, widths, list(range(1, len(headers))))
        for row_idx, team_id in enumerate(self.analysis_rows):
            if team_id == self.focus:
                sheet.highlight_rows(row_idx, bg=theme.focus[0], fg=theme.focus[1],
                                     redraw=False, end_of_screen=False)
        for row_idx, column, colours in zone_cells:
            self._paint(sheet, row_idx, column, colours)
        sheet.refresh()
        notes = ["Each season side by side: the latest on the left, then earlier seasons; "
                 "Δ Pos is the previous season's position minus the latest's."]
        notes.extend(f"{column.label}: {column.note}." for column in comparison.columns)
        notes.append("Click a team to follow it.")
        self.note_label.configure(text=" ".join(notes))
        self._show_zone_key(())

    def _render_xg(self) -> None:
        cov = fd.xg_coverage(self.dataset, self.fixtures)
        if cov.state or not cov.covered:
            self.note_label.configure(text="")
            self._show_message(cov.describe())
            return
        rows = fd.xg_table(self.dataset, self.fixtures, self.labels, order=self._table_order())
        headers = ["Team", "Reports", "xG", "xGA", "xGD", "GF", "GA", "Goals − xG", "xGA − GA"]
        data, self.analysis_rows = [], []
        for r in rows:
            if r.covered:
                data.append([r.team, f"{r.covered} of {r.played}", f"{r.xg_for:.2f}", f"{r.xg_against:.2f}",
                             f"{r.xg_difference:+.2f}", r.goals_for, r.goals_against, f"{r.finishing:+.2f}",
                             f"{r.prevention:+.2f}"])
            else:
                data.append([r.team, f"0 of {r.played}", "", "", "", "", "", "", ""])
            self.analysis_rows.append(r.team_id)
        widths = [self._text_width([row[0] for row in data], minimum=180), self.px(70)] + [self.px(60)] * 5 \
            + [self.px(90)] * 2
        sheet = self._fill_analysis(headers, data, widths, list(range(1, len(headers))))
        theme = self.view_theme
        for i, r in enumerate(rows):
            if r.team_id == self.focus:
                sheet.highlight_rows(i, bg=theme.focus[0], fg=theme.focus[1], redraw=False, end_of_screen=False)
            for column, value in ((7, r.finishing), (8, r.prevention)):
                tint = fd.xg_tint(value, matches=r.covered) if value is not None else ""
                if tint:
                    self._paint(sheet, i, column, theme.colours["W" if tint == fd.XG_ABOVE else "L"])
        sheet.refresh()
        self.note_label.configure(text=(
            f"{cov.describe()} xG and goals here come from the same matches: those with a match report and a "
            "score. Goals − xG: scored more (+) or fewer (−) than expected. xGA − GA: conceded fewer (+) or more "
            f"(−) than expected. Green or red where that averages more than {fd.XG_DEAD_ZONE} a match either way. "
            "Click a team to follow it."))

    def _render_bracket(self) -> None:
        comp = self.dataset.by_id[self.comp_id]
        if fd.underlying_category(comp, self.dataset) != fd.COMP_CAT_CUP:
            self.note_label.configure(text="")
            self._show_message("The bracket is for knockout cups; this competition is not one.")
            return
        rounds = fd.cup_rounds(self.fixtures, self.labels)
        if not rounds:
            self.note_label.configure(text="")
            self._show_message("This cup has no rounds this season.")
            return
        self.analysis_rows = []
        self.message.grid_remove()
        for sheet in self.sheets.values():
            sheet.grid_remove()
        self._shown = None
        self.bracket_view.grid()
        self.bracket_view.use_theme(self.view_theme)                     # with the followed club's tint, as the sheets
        self.bracket_view.show(rounds, self.labels, self.focus)
        self.note_label.configure(text="")

    def _render_ties(self) -> None:
        ties = fd.two_legged_ties(self.fixtures, self.labels)
        self.analysis_rows = []
        if not ties:
            self.note_label.configure(text="")
            self._show_message("This competition has no two-legged ties.")
            return
        name = lambda t: self.labels.get(t, f"Team {t}")      # noqa: E731
        data = []
        for tie in ties:
            first, second = tie.first, tie.second
            leg = lambda f, a_home: (f"{f.home_goals if a_home else f.away_goals}-"      # noqa: E731
                                     f"{f.away_goals if a_home else f.home_goals}" if fd.has_score(f)
                                     else ("n/a" if f.played else "v"))
            goals = tie.aggregate
            data.append([fd.tie_round_text(tie), f"{name(tie.team_a)} v {name(tie.team_b)}", leg(first, True),
                         leg(second, False), f"{goals[0]}-{goals[1]}" if goals else "", fd.tie_outcome(tie, self.labels)])
            self.analysis_rows.append(None)
        widths = [self.px(90), self._text_width([row[1] for row in data], minimum=240), self.px(70), self.px(70),
                  self.px(90), self._text_width([row[5] for row in data], minimum=200)]
        sheet = self._fill_analysis(["Round", "Tie", "Leg 1", "Leg 2", "Aggregate", "Outcome"], data, widths,
                                    [0, 2, 3, 4])
        theme = self.view_theme
        for i, tie in enumerate(ties):
            if self.focus in (tie.team_a, tie.team_b):
                sheet.highlight_rows(i, bg=theme.focus[0], fg=theme.focus[1], redraw=False, end_of_screen=False)
        sheet.refresh()
        self.note_label.configure(text=(
            "Both legs and the aggregate read the first-named side first. The save stores no away goals, extra time "
            "or penalties, so a level aggregate is not decided here."))

    def _render_competitions(self) -> None:
        """Fill the hub once per save and set of names; after that only the highlighted row moves,
        so picking a competition keeps the hub's scroll position."""
        ds = self.dataset
        if not ds:
            return
        sheet = self._show_sheet(HUB)
        key = (self._dataset_serial, tuple(sorted(self.names.items())), self.country_key)
        if key != self._hub_key:
            kept = fd.competitions_in_country(ds, self.country_key)
            summaries = fd.competitions_summary(ds, self.names)
            self._fill_hub(sheet, summaries if kept is None else tuple(s for s in summaries if s.id in kept))
            self._hub_key = key
        self.coverage_label.configure(text=self._hub_summary)
        self.note_label.configure(
            text="Click a competition to select it; double-click it, or pick it in the list on the left, "
                 f"to open it in the {self.last_comp_view} view.")
        self._mark_current_in_hub()

    def _fill_hub(self, sheet: Sheet, summaries: tuple[fd.CompetitionSummaryRow, ...]) -> None:
        ds = self.dataset
        self._hub_summary = f"{len(summaries)} competitions · {ds.fixture_total:,} fixtures in the save"
        headers = ["Category", "ID", "Competition Name", "Teams", "Fixtures", "Played", "Progress", "Seasons", "Example Clubs"]
        data = []
        self.comp_row_ids = []
        for s in summaries:
            data.append([s.category, s.id, s.name, s.teams, s.fixtures, s.played, s.progress, s.seasons, s.example_clubs])
            self.comp_row_ids.append(s.id)
        sheet.set_sheet_data(data, reset_col_positions=True, reset_row_positions=True, redraw=False, reset_highlights=True)
        sheet.headers(headers, redraw=False)
        sheet.set_column_widths([
            self.px(110), self.px(50), self.px(240), self.px(60), self.px(65),
            self.px(65), self.px(75), self.px(65), self.px(300)
        ])
        sheet.align_columns([1, 3, 4, 5, 6, 7], align="center", align_header=True, redraw=False)
        self._hub_categories = [s.category for s in summaries]
        self._paint_hub()

    def _paint_hub(self) -> None:
        """Colour the hub's category cells and your club's rows; a new theme repaints them in place."""
        sheet, theme = self.sheets[HUB], self.view_theme
        sheet.dehighlight_all(redraw=False)
        for i, category in enumerate(self._hub_categories):
            if category == fd.COMP_CAT_YOURS:
                sheet.highlight_rows(i, bg=theme.yours_row[0], fg=theme.yours_row[1], redraw=False, end_of_screen=False)
            if category in theme.categories:
                self._paint(sheet, i, 0, theme.categories[category])
        sheet.refresh()

    def _mark_current_in_hub(self) -> None:
        """Highlight the selected competition's row without firing the hub's own select event."""
        if self.comp_id not in self.comp_row_ids:
            return
        row = self.comp_row_ids.index(self.comp_id)
        sheet = self.sheets[HUB]
        sheet.select_row(row, redraw=False, run_binding_func=False)
        sheet.see(row=row, column=0, keep_xscroll=True)
        comp = self.dataset.by_id[self.comp_id]
        self.detail_label.configure(
            text=f"Selected: {fd.competition_title(comp, self.names)} (ID {comp.id}) · {fd.competition_hint(comp)}")

    def _open_from_hub(self) -> None:
        selected = self.sheets[HUB].get_currently_selected()
        if self.view == HUB and self.comp_id is not None and selected and selected.type_ != "columns":
            self.set_view(self.last_comp_view)

    # ----------------------------------------------------------------- clicks in the views

    def _on_sheet_select(self, name: str) -> None:
        selected = self.sheets[name].get_currently_selected()
        if not selected or selected.row is None:
            return
        if selected.type_ == "columns" and name != "Grid":
            return      # a column header means nothing outside the grid, where it is a team
        row, column = selected.row, selected.column
        if name == "Results" and 0 <= row < len(self.result_rows):
            item = self.result_rows[row]
            if item.fixture is not None:
                self._selection = ("match", item.fixture)
                text = fd.describe_fixture(item.fixture, self.labels)
                xg = fd.xg_for(self.dataset, item.fixture)
                if xg is not None:
                    text += f" · xG: {fd.xg_scoreline(item.fixture, xg, self.labels)}"
                self.detail_label.configure(text=text)
        elif name == "Grid" and self.grid_data is not None:
            grid = self.grid_data
            if selected.type_ == "rows" and 0 <= row < len(grid.team_ids):
                self._selection = ("club", grid.team_ids[row])
                self.set_focus(grid.team_ids[row])
            elif selected.type_ == "columns" and column is not None and 0 <= column < len(grid.team_ids):
                self._selection = ("club", grid.team_ids[column])
                self.set_focus(grid.team_ids[column])
            elif 0 <= row < len(grid.cells) and column is not None and 0 <= column < len(grid.team_ids):
                cell = grid.cells[row][column]
                if cell.fixtures:
                    self._selection = ("match", cell.fixtures[0])
                home, away = grid.row_labels[row], grid.row_labels[column]
                if cell.fixtures:
                    text = "   |   ".join(fd.describe_fixture(f, self.labels) for f in cell.fixtures)
                elif row == column:
                    text = ""
                else:
                    text = f"{home} v {away}: no fixture between them at {home}'s ground this season."
                self.detail_label.configure(text=text)
        elif name == "Table" and 0 <= row < len(self.table_rows) and self.table_rows[row] is not None:
            self._selection = ("club", self.table_rows[row])
            if self.table_rows[row] != self.focus:
                self.set_focus(self.table_rows[row])
        elif name == ANALYSIS and 0 <= row < len(self.analysis_rows) and self.analysis_rows[row] is not None:
            self._selection = ("club", self.analysis_rows[row])
            if self.analysis_rows[row] != self.focus:
                self.set_focus(self.analysis_rows[row])
        elif name == HUB and self.view == HUB and 0 <= row < len(self.comp_row_ids):
            if self.comp_row_ids[row] != self.comp_id:
                self.select_competition(self.comp_row_ids[row])
            self._selection = ("hub", self.comp_row_ids[row])
        self._refresh_inspector()

    # ----------------------------------------------------------------- the command palette

    def open_palette(self) -> None:
        """Open the command palette over the window, with items for the save and view as they are now."""
        self.command_palette.open(self._palette_items())

    def close_palette(self) -> None:
        self.command_palette.close()

    def _on_palette_key(self, _event=None) -> str:
        self.open_palette()
        return "break"

    def _palette_failed(self, exc: Exception) -> None:
        self._log_error(traceback.format_exc())
        self.detail_label.configure(text=f"That command failed: {exc}")

    def _club_entries(self) -> tuple[fd.ClubEntry, ...]:
        """The clubs the palette offers, worked out once for each installed save."""
        if self._club_cache is None or self._club_cache[0] != self._dataset_serial:
            self._club_cache = (self._dataset_serial, fd.club_index(self.dataset))
        return self._club_cache[1]

    def _palette_items(self) -> list[command_palette.PaletteItem]:
        """Everything the palette can do just now. What cannot apply (no save, an export under way) is
        left out rather than greyed."""
        cp = command_palette
        items: list[cp.PaletteItem] = []

        def add(kind, title, action, detail="", priority=0):
            items.append(cp.PaletteItem(kind, title, detail, action, priority))

        ds = self.dataset
        ready = ds is not None and self.comp_id is not None
        if ds is not None:
            for view in VIEWS:
                add(cp.VIEW, view, lambda v=view: self.set_view(v))
        if ready:
            for split in fd.SPLITS:
                add(cp.SPLIT, f"Table: {split}", lambda s=split: self._palette_split("Table", s))
            for grouping in GROUPINGS:
                add(cp.SPLIT, f"Results by {grouping}", lambda g=grouping: self._palette_split("Results", g))
            for analysis in ANALYSES:
                add(cp.SPLIT, f"Analysis: {analysis}", lambda a=analysis: self._palette_split(ANALYSIS, a))
            if not self._exporting:
                for kind, label in ((fx.EXCEL, "Excel workbook"), (fx.HTML, "web page"), (fx.CSV, "CSV files")):
                    add(cp.ACTION, f"Export as {label}", lambda k=kind: self.export(k))
            add(cp.ACTION, "Name this competition…", self.rename_competition)
            if isinstance(self.country_key, int):
                add(cp.ACTION, "Name this country…", self.name_country)
            for kind, label in (("table", "Table"), ("team", "My club's results"), ("recent", "Recent results")):
                if self._post_applies(kind):
                    add(cp.ACTION, f"Copy for a post: {label}", lambda k=kind: self.copy_for_post(k))
        if ds is not None and not self._exporting:
            add(cp.ACTION, "Export the whole save as a workbook", lambda: self.export_whole_save(),
                "every competition with a played match")
        if not self._exporting:
            seasons = self._banked_seasons()
            if seasons:
                add(cp.ACTION, "Save Yearbook edition…", lambda sn=seasons[0][0]: self.export_yearbook(sn),
                    f"the {seasons[0][1]} volume, from the archive")
                latest = yearbook_editions.list_editions(export_folder(), seasons[0][1])
                if latest:
                    add(cp.ACTION, "Open latest Yearbook", lambda p=latest[0].path: self._open_path(p),
                        f"the {seasons[0][1]} volume, {latest[0].date_label} edition")
        add(cp.ACTION, "Open the export folder", self.open_export_folder)
        if self.loading_since is None:
            add(cp.ACTION, "Open save…", self.choose_save)
        if ds is not None:
            add(cp.ACTION, "Save details & warnings", self.show_details)
            add(cp.ACTION, "Hide the inspector" if self.inspector.is_open else "Show the inspector",
                self.toggle_inspector)
        add(cp.ACTION, "About", self.show_about)
        for theme in palette.THEMES:
            add(cp.ACTION, f"Theme: {theme.name}", lambda n=theme.name: self.set_theme(n))
        if self._followed_club():
            add(cp.ACTION, "Club colours…", self.show_club_colours)
        if self.focus is not None:
            add(cp.ACTION, "Clear followed team", lambda: self.set_focus(None))
        if self._followed_uid is not None:
            add(cp.ACTION, f"Schedule: {self._followed_uid.name}", lambda: self.set_view(SCHEDULE))
            add(cp.ACTION, f"Hub: {self._followed_uid.name}", lambda: self.set_view(MANAGER_HUB))
            add(cp.ACTION, "Clear followed club", self._clear_followed_uid)
        if ds is not None:
            for comp in ds.competitions:
                add(cp.COMPETITION, fd.competition_list_label(comp, self.names),
                    lambda c=comp.id: self.select_competition(c), f"{comp.team_count} teams",
                    1 if comp.id == self.comp_id else 0)
            shown: set[tuple[int, int]] = set()
            if self.comp_id is not None:
                open_detail = self._competition_detail(ds.by_id[self.comp_id])
                for team_id, label in self.labels.items():          # the open competition's own teams, any kind
                    shown.add((team_id, self.comp_id))
                    add(cp.CLUB, label, lambda c=self.comp_id, t=team_id, n=label: self._follow_club_in(c, t, n),
                        open_detail, CLUB_OPEN_PRIORITY)
            order = {comp.id: place for place, comp in enumerate(ds.competitions)}   # most prominent first
            for entry in self._club_entries():
                if (entry.team_id, entry.competition_id) not in shown:
                    # A club's league outranks its cups, and the more prominent competition outranks another,
                    # so Enter on a club name opens its main league.
                    league = CLUB_LEAGUE_PRIORITY if entry.category == fd.COMP_CAT_LEAGUE else 0
                    priority = league + len(order) - order[entry.competition_id]
                    add(cp.CLUB, entry.label,
                        lambda e=entry: self._follow_club_in(e.competition_id, e.team_id, e.label),
                        self._competition_detail(ds.by_id[entry.competition_id]), priority)
        return items

    def _competition_detail(self, comp: fd.CompetitionInfo) -> str:
        """Which competition a palette row is in: its name (or id) and size, so two of a club's rows differ."""
        size = f"{comp.team_count} teams"
        if comp.database_id is not None and comp.database_id in self.names:
            return f"{self.names[comp.database_id]} · {size}"
        clubs = ", ".join(comp.top_clubs[:2])      # unnamed: its best-known clubs say more than its id
        return f"Competition {comp.id}: {clubs} · {size}" if clubs else f"Competition {comp.id} · {size}"

    def _palette_split(self, view: str, value: str) -> None:
        """Go to a view and set the switch it uses (the table's split, results' grouping or analysis panel)."""
        self.set_view(view)
        if view == "Table":
            self.split_switch.set(value)
            self._on_table_split(value)
        elif view == "Results":
            self.group_switch.set(value)
            self._on_group(value)
        else:
            self._on_analysis(value)

    def _follow_club_in(self, comp_id: int, team_id: int, name: str) -> None:
        """Open a club in the competition it was listed under and follow it. From the hub the last
        competition view opens, so the club is seen."""
        if comp_id != self.comp_id:
            if self.view == HUB:
                self.set_view(self.last_comp_view)
            self.select_competition(comp_id)
        self.set_focus(team_id)
        if self.focus != team_id:
            self.detail_label.configure(text=f"{name} has no matches in this competition and season.")

    # ----------------------------------------------------------------- tooltips on the form pills

    def _on_pill_hover(self, name: str, row: int, column: int, index: int, x_root: int, y_root: int) -> None:
        text = self._pill_tip(name, row, column, index)
        if text:
            self.tooltip.show(text, x_root, y_root)
        else:
            self.tooltip.hide()

    def _pill_tip(self, name: str, row: int, column: int, index: int) -> str | None:
        """The match behind one form pill, in words; None when it cannot be told for certain."""
        if name == "Table" and 0 <= row < len(self.table_rows) and self.table_rows[row] is not None:
            letters = self.overlays["Table"].pills.get((row, column), "")
            # The Table's form leaves out matches with no recoverable score, as its letters do.
            # The Home and Away splits' form covers home or away matches only.
            venue = {fd.SPLIT_HOME: True, fd.SPLIT_AWAY: False}.get(self.table_split)
            steps = [s for s in fd.team_steps(self.fixtures, self.table_rows[row], self.labels)
                     if s.outcome != fd.UNKNOWN_RESULT and venue in (None, s.home)][-len(letters):] if letters else []
            if "".join(s.outcome for s in steps) == letters and index < len(steps):
                return fd.describe_form_step(steps[index])
        elif name == ANALYSIS and 0 <= row < len(self.analysis_rows) and self.analysis_rows[row] is not None:
            # The Form panel draws one letter per cell, oldest first, '?' included.
            pills = self.overlays[ANALYSIS].pills
            columns = sorted(c for (r, c) in pills if r == row)
            strip = fd.form_strip(fd.team_steps(self.fixtures, self.analysis_rows[row], self.labels))
            if "".join(pills[(row, c)] for c in columns) == strip.letters and column in columns:
                return fd.describe_form_step(strip.steps[columns.index(column)])
        return None

    # ----------------------------------------------------------------- the inspector drawer

    def toggle_inspector(self) -> None:
        if self.inspector.is_open:
            self.close_inspector()
        else:
            self.open_inspector()

    def open_inspector(self) -> None:
        """Show the drawer over the right of the sheet, describing the selection. It never takes focus."""
        self.inspector.show(self._inspector_model_safely())
        self.inspector.open()

    def close_inspector(self) -> None:
        self.inspector.close()

    def _inspector_closed(self) -> None:
        pass

    def _on_inspector_key(self, _event=None) -> str:
        self.toggle_inspector()
        return "break"

    def _on_escape(self, _event=None) -> None:
        if self.inspector.is_open and not self.command_palette.is_open:
            self.close_inspector()

    def _refresh_inspector(self) -> None:
        """Redraw the open drawer for the current selection and data; a shut drawer costs nothing."""
        if self.inspector.is_open:
            self.inspector.show(self._inspector_model_safely())

    def _inspector_model_safely(self) -> inspector.InspectorModel:
        """The drawer must never break the window: a failure is logged and the drawer says so."""
        try:
            return self._inspector_model()
        except Exception:
            self._log_error(traceback.format_exc())
            return inspector.InspectorModel("Inspector", "This could not be shown; the error was logged.")

    def _inspector_model(self) -> inspector.InspectorModel:
        if not self.dataset:
            return inspector.InspectorModel("Inspector", "Open a save first.")
        selection = self._selection
        if self.view == HUB:
            selection = ("hub", self.comp_id) if self.comp_id is not None else None
        elif selection is not None and (selection[0] == "hub" or (
                selection[0] == "match" and self.view != SCHEDULE and selection[1] not in self.fixtures)):
            selection = None             # (the Schedule holds matches of every competition)
        if selection is None and self.focus is not None:
            selection = ("club", self.focus)
        if selection is not None:
            kind, value = selection
            if kind == "match":
                return self._match_model(value)
            if kind == "club" and value in self.labels:
                return self._club_model(value)
            if kind == "hub" and value in self.dataset.by_id:
                return self._hub_model(value)
            if kind == "pair" and all(t in self.labels or t in self.dataset.teams for t in value):
                return self._head_to_head_model(*value)
        return inspector.InspectorModel("Inspector", "Select a match or a club.")

    def _team_name(self, team_id: int) -> str:
        """The team's label in the open competition, else its club from the save (a match from another competition)."""
        if team_id in self.labels:
            return self.labels[team_id]
        identity = self.dataset.teams.get(team_id) if self.dataset else None
        if identity is not None and identity.club_name:
            return f"{identity.club_name} (team {identity.slot + 1})" if identity.slot else identity.club_name
        return f"Team {team_id}"

    @staticmethod
    def _day(f: fd.Fixture, fmt: str = "%a {d} %b") -> str:
        return f.date.strftime(fmt.replace("{d}", str(f.date.day))) if f.date else "—"

    @staticmethod
    def _form_chips(steps) -> inspector.Chips:
        """A team's last five as chips, its current run beside them, and each match in words for the tooltips."""
        strip = fd.form_strip(steps)
        return inspector.Chips(strip.letters, fd.streaks(steps).describe_current(),
                               tuple(fd.describe_form_step(step) for step in strip.steps))

    def _form_blocks(self, team_id: int, fixtures=None, labels=None) -> list:
        """The team's last five results as chips, with its current run in words (by default in the open
        competition and season)."""
        steps = fd.team_steps(self.fixtures if fixtures is None else fixtures, team_id,
                              self.labels if labels is None else labels)
        if not steps:
            return [inspector.Heading(f"{self._team_name(team_id)}: last 5"),
                    inspector.Line("No matches played yet.", muted=True)]
        return [inspector.Heading(f"{self._team_name(team_id)}: last 5"),
                self._form_chips(steps)]

    def _match_model(self, f: fd.Fixture) -> inspector.InspectorModel:
        ds = self.dataset
        home, away = self._team_name(f.home_team_id), self._team_name(f.away_team_id)
        kind = fd.result_kind(f)
        when = []
        if f.date:
            when.append(self._day(f, "%a {d} %b %Y"))
        if f.kick_off_time:
            when.append(f.kick_off_time.strftime("%H:%M"))
        if fd.round_text(f):
            when.append(fd.round_text(f))
        when.append({fd.SCHEDULED: "To play", fd.UNAVAILABLE: "Played, score not recoverable (n/a)"}.get(kind, "Played"))
        blocks: list = []
        if kind == fd.SCHEDULED:
            blocks.append(inspector.Line("Not played yet.", muted=True))
        else:
            blocks.append(inspector.Line(f"{home} {fd.score_text(f)} {away}"))
            stats = fd.match_stats_for(ds, f)
            if stats is not None:
                blocks += [inspector.Heading("Statistics"),
                           inspector.Stats(home, away, fd.describe_match_stats(stats))]
            elif ds.xg_report is None:
                blocks.append(inspector.Line("Match statistics are still being read.", muted=True))
            elif ds.xg_report.failed:
                blocks.append(inspector.Line("Match statistics could not be read from this save.", muted=True))
            else:
                blocks.append(inspector.Line("No match report stored for this match", muted=True))
        # The ground as the save records it: name, neutral flag and total capacity, or why each is missing.
        blocks.append(inspector.Heading("Venue"))
        blocks += [inspector.Line(line) for line in fd.venue_for(ds, f).lines()]
        form_team = self.focus if self.focus in (f.home_team_id, f.away_team_id) else f.home_team_id
        if f in self.fixtures or f.competition_id is None:
            blocks += self._form_blocks(form_team)
        else:                                       # a match picked from the Schedule: its own competition and season
            own = fd.season_fixtures(ds, f.competition_id, fd.season_key(f))
            blocks += self._form_blocks(form_team, own, fd.team_labels(own))
        all_groups = fd.all_meetings(self.dataset, f.home_team_id, f.away_team_id)
        total = sum(len(g.fixtures) for g in all_groups)
        blocks.append(inspector.Heading(f"Meetings ({total})"))
        for group in all_groups:
            comp_info = self.dataset.by_id.get(group.competition_id)
            comp_name = fd.competition_title(comp_info, self.names) if comp_info else f"Competition {group.competition_id}"
            season_lbl = fd.season_label(group.season, group.fixtures)
            blocks.append(inspector.Line(f"{comp_name}  {season_lbl}", muted=True))
            for meeting in group.fixtures:
                score = "to play" if fd.result_kind(meeting) == fd.SCHEDULED else fd.score_text(meeting)
                blocks.append(inspector.Line(
                    f"  {self._day(meeting, '%d %b')}  {self._team_name(meeting.home_team_id)} {score} "
                    f"{self._team_name(meeting.away_team_id)}", marked=meeting == f))
        return inspector.InspectorModel(f"{home} v {away}", " · ".join(when), tuple(blocks))

    def _head_to_head_model(self, a_id: int, b_id: int) -> inspector.InspectorModel:
        """Every meeting between two clubs across every competition and season the save holds."""
        a, b = self._team_name(a_id), self._team_name(b_id)
        groups = fd.all_meetings(self.dataset, a_id, b_id)
        blocks: list = []
        total = sum(len(g.fixtures) for g in groups)
        if not total:
            blocks.append(inspector.Line("No meetings in this save.", muted=True))
        else:
            blocks.append(inspector.Heading(f"Meetings ({total})"))
            for group in groups:
                comp_info = self.dataset.by_id.get(group.competition_id)
                comp_name = fd.competition_title(comp_info, self.names) if comp_info else f"Competition {group.competition_id}"
                season_lbl = fd.season_label(group.season, group.fixtures)
                blocks.append(inspector.Line(f"{comp_name}  {season_lbl}", muted=True))
                for meeting in group.fixtures:
                    score = "to play" if fd.result_kind(meeting) == fd.SCHEDULED else fd.score_text(meeting)
                    blocks.append(inspector.Line(
                        f"  {self._day(meeting, '%d %b')}  {self._team_name(meeting.home_team_id)} {score} "
                        f"{self._team_name(meeting.away_team_id)}"))
        return inspector.InspectorModel("Head-to-head", f"{a} v {b}", tuple(blocks))

    def _club_model(self, team_id: int) -> inspector.InspectorModel:
        ds = self.dataset
        name = self.labels[team_id]
        steps = fd.team_steps(self.fixtures, team_id, self.labels)
        blocks: list = [inspector.Heading("Form")]
        if steps:
            blocks.append(self._form_chips(steps))
            totals = fd.team_totals(steps)
            blocks.append(inspector.Heading("Season so far"))
            blocks.append(inspector.Line(f"Played {totals.played}: won {totals.won}, drawn {totals.drawn}, "
                                         f"lost {totals.lost} · goals {totals.goals_for}-{totals.goals_against}"))
            blocks.append(inspector.Line(totals.describe_ppg()))
            if totals.unavailable:
                blocks.append(inspector.Line("A match with no recoverable score counts as played only, so these "
                                             "totals are minimums.", muted=True))
        else:
            blocks.append(inspector.Line("No matches played yet.", muted=True))
        coming = fd.next_match(self.fixtures, team_id)
        if coming is not None:
            home = coming.home_team_id == team_id
            opponent = self._team_name(coming.away_team_id if home else coming.home_team_id)
            blocks.append(inspector.Line(f"Next: {opponent} ({'home' if home else 'away'}), {self._day(coming)}"))
        row = next((r for r in fd.xg_table(ds, self.fixtures, self.labels) if r.team_id == team_id), None)
        if row is not None and row.covered:
            blocks.append(inspector.Line(f"Expected goals: {row.xg_for:.1f} for, {row.xg_against:.1f} against, over "
                                         f"{row.covered} match{'es' if row.covered != 1 else ''} with a report"))
        blocks += self._history_blocks(team_id)
        subtitle = fd.competition_title(ds.by_id[self.comp_id], self.names) if self.comp_id in ds.by_id else ""
        return inspector.InspectorModel(name, subtitle, tuple(blocks))

    def _hub_model(self, comp_id: int) -> inspector.InspectorModel:
        ds = self.dataset
        comp = ds.by_id[comp_id]
        plural = lambda n, word: f"{n} {word}{'' if n == 1 else 's'}"      # noqa: E731
        blocks = (
            inspector.Line(fd.competition_category(comp, ds)),
            inspector.Line(plural(comp.team_count, "team")),
            inspector.Line(f"{plural(len(comp.seasons), 'season')} in the save"),
            inspector.Line(f"{plural(comp.fixture_count, 'fixture')}, {comp.played_count} played"),
            inspector.Line(", ".join(comp.top_clubs) or "No clubs named", muted=True),
        )
        title = fd.competition_title(comp, self.names)
        return inspector.InspectorModel(title, "" if title == f"Competition {comp.id}" else f"Competition {comp.id}",
                                        blocks)

    # ----------------------------------------------------------------- the right-click menu

    def set_opponent_filter(self, pair: tuple[int, int] | None) -> None:
        """Show only the matches between two teams in Results, or (None) all again."""
        self.opponent_filter = pair
        if pair is not None and self.view != "Results":
            self.set_view("Results")
        else:
            self.render()

    def _row_clubs(self, name: str, row: int, column: int | None) -> list[tuple[int, str]]:
        """The clubs a right-click on this row (and column, in the grid) can act on: (team id, label)
        for each team the save can resolve to a club."""
        ids: list[int | None] = []
        if name == "Results" and 0 <= row < len(self.result_rows):
            item = self.result_rows[row]
            ids = [item.home_id, item.away_id] if item.fixture is not None else []
        elif name == "Table" and 0 <= row < len(self.table_rows):
            ids = [self.table_rows[row]]
        elif name == ANALYSIS and 0 <= row < len(self.analysis_rows):
            ids = [self.analysis_rows[row]]
        elif name == "Grid" and self.grid_data is not None and 0 <= row < len(self.grid_data.team_ids):
            ids = [self.grid_data.team_ids[row]]
            if column is not None and 0 <= column < len(self.grid_data.team_ids):
                ids.append(self.grid_data.team_ids[column])
        clubs: list[tuple[int, str]] = []
        for team_id in ids:
            if team_id is not None and team_id in self.club_names and team_id in self.labels \
                    and all(team_id != known for known, _ in clubs):
                clubs.append((team_id, self.labels[team_id]))
        return clubs

    def _head_to_head_entry(self, clubs: list[tuple[int, str]]) -> MenuEntry:
        """A right-click head-to-head item: active on two clubs; active with "Head-to-head with {focus}"
        when a different club is followed; greyed with its reason otherwise."""
        if len(clubs) == 2:
            (a_id, _), (b_id, _) = clubs
            return MenuEntry("Head-to-head", lambda pair=(a_id, b_id): self._open_head_to_head(*pair))
        row_id, _ = clubs[0]
        if self.focus is not None and self.focus != row_id and self.focus in self.labels:
            focus_label = self.labels[self.focus]
            return MenuEntry(f"Head-to-head with {focus_label}",
                             lambda pair=(self.focus, row_id): self._open_head_to_head(*pair))
        return MenuEntry("Head-to-head (follow another club first)", None)

    def _open_head_to_head(self, a_id: int, b_id: int) -> None:
        """Pin the pair as the inspector's selection and show the drawer."""
        self._selection = ("pair", (a_id, b_id))
        self.open_inspector()

    def _row_menu(self, name: str, row: int, column: int | None = None) -> list[MenuEntry]:
        """What a right-click on a row offers: follow each club on it (but not the one already followed),
        for a match show only the two clubs' meetings, a head-to-head that waits for the archive, export
        and copy. A row with no club offers only the last two."""
        clubs = self._row_clubs(name, row, column)
        entries = [MenuEntry(f"Follow {label}", lambda t=team_id: self.set_focus(t))
                   for team_id, label in clubs if team_id != self.focus]
        if name == "Results" and len(clubs) == 2:
            (home_id, home), (away_id, away) = clubs
            entries.append(MenuEntry(f"Show only {home} v {away}",
                                     lambda pair=(home_id, away_id): self.set_opponent_filter(pair)))
        if name == "Table" and len(clubs) == 1 and self.focus is not None and self.focus != clubs[0][0] \
                and self.focus in self.labels:
            row_id, row_label = clubs[0]
            entries.append(MenuEntry(f"Show only {self.labels[self.focus]} v {row_label}",
                                     lambda pair=(self.focus, row_id): self.set_opponent_filter(pair)))
        if clubs:
            entries += [MENU_SEPARATOR, self._head_to_head_entry(clubs)]
            entries += [MenuEntry(f"Copy {label}'s results",
                                  (lambda t=team_id: self.copy_for_post("team", t)) if self._has_played(team_id) else None)
                        for team_id, label in clubs]
            entries.append(MENU_SEPARATOR)
        kinds = ((fx.EXCEL, "Excel workbook (.xlsx)"), (fx.HTML, "Web page (.html)"), (fx.CSV, "CSV files (.csv)"))
        children = () if self._exporting or self.comp_id is None else tuple(
            MenuEntry(label, lambda k=kind: self.export(k)) for kind, label in kinds)
        entries.append(MenuEntry("Export", None, children))
        entries.append(MenuEntry("Copy", self.sheets[name].copy))
        return entries

    def _show_row_menu(self, name: str, event) -> None:
        """Right-click on a sheet: tksheet has already selected the row; offer what _row_menu lists."""
        sheet = self.sheets[name]
        row = sheet.identify_row(event, allow_end=False)
        if row is None:
            return
        column = sheet.identify_column(event, allow_end=False)
        menu = self._build_menu(self._row_menu(name, row, column))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _build_menu(self, entries: Sequence[MenuEntry]) -> tk.Menu:
        t = self.theme                                        # plain theme colours: no club tint on a menu
        menu = tk.Menu(self, tearoff=False, bg=t.panel, fg=t.text, activebackground=t.list_selected[0],
                       activeforeground=t.list_selected[1], disabledforeground=t.muted, bd=0)
        for entry in entries:
            if entry is MENU_SEPARATOR:
                menu.add_separator()
            elif entry.children:
                menu.add_cascade(label=entry.label, menu=self._build_menu(entry.children))
            else:
                menu.add_command(label=entry.label, command=entry.command,
                                 state="normal" if entry.command else "disabled")
        return menu

    # ----------------------------------------------------------------- details and About windows

    def show_details(self) -> None:
        if not self.dataset:
            return
        ds, info = self.dataset, self.dataset.info
        lines = [
            f"Save:            {info.file_name}",
            f"Folder:          {Path(info.path).parent}",
            f"Game and build:  {info.game} {info.build}",
        ]
        if info.known_build:
            lines.append("                 fmsave has layouts registered for this build.")
        else:
            lines += [
                "                 fmsave has no layouts registered for this build yet, so it borrows the",
                "                 nearest known ones. Its checks passed, but every value counts as",
                "                 unconfirmed until this build is verified against the game. Compare a few",
                "                 results and tables with the game when you can.",
            ]
        lines += [
            f"In-game date:    {info.game_date:%d %B %Y}" if info.game_date else "In-game date:    unknown",
            f"Managed club:    {info.managed_club_name or 'not found'}",
            f"Read with:       fmsave {info.fmsave_version} in {info.seconds:.1f} s at {info.imported_at:%H:%M}",
            f"Fixtures:        {ds.fixture_total:,} in {len(ds.competitions)} competitions"
            + (f" ({ds.fixtures_without_competition:,} with no competition, not shown)" if ds.fixtures_without_competition else ""),
            f"Stored tables:   {sum(len(t) for t in ds.stored_tables.values())} live league tables",
            "Expected goals:  " + (ds.xg_report.describe() if ds.xg_report else "still being read from the save"),
            f"Names file:      {NAMES_PATH} ({len(self.names)} names)",
            "",
            "fmsave only reads the save. It never changes it.",
            "",
            f"Reader warnings ({len(info.warnings)}):",
        ]
        lines += [f"  • {w}" for w in info.warnings] or ["  none"]
        window = ctk.CTkToplevel(self)
        apply_window_icon(window)
        window.title("Save details & warnings")
        window.geometry("860x480")
        window.transient(self)
        box = ctk.CTkTextbox(window, wrap="word", font=ctk.CTkFont("Consolas", 12))
        box.pack(fill="both", expand=True, padx=12, pady=12)
        box.insert("1.0", "\n".join(lines))
        box.configure(state="disabled")
        window.after(100, window.lift)

    def show_about(self) -> None:
        """Open the About window, or bring it forward if it is already open."""
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.bring_forward()
            return
        self.about_window = AboutWindow(self)

    # ----------------------------------------------------------------- files

    def _load_names(self) -> None:
        try:
            self.names = fd.load_competition_names(NAMES_PATH)
        except (OSError, ValueError) as exc:
            self.names = {}
            self.after(500, lambda: messagebox.showwarning(
                "Competition names not loaded", f"{NAMES_PATH.name} could not be read:\n{exc}", parent=self))

    def _read_settings(self) -> dict:
        for p in (SETTINGS_PATH, LEGACY_SETTINGS_PATH):
            try:
                if p.is_file():
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):      # [], null or a string: as unreadable as broken JSON
                        continue
                    if p == LEGACY_SETTINGS_PATH and not SETTINGS_PATH.exists():
                        self.settings = data
                        self._write_settings()
                    return data
            except (OSError, ValueError):
                pass
        return {}

    def _write_settings(self) -> None:
        try:
            SETTINGS_PATH.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _log_error(text: str) -> None:
        try:
            with ERROR_LOG.open("a", encoding="utf-8") as handle:
                handle.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')}\n{text}\n")
        except OSError:
            pass

    def report_callback_exception(self, exc, value, tb) -> None:
        text = "".join(traceback.format_exception(exc, value, tb))
        self._log_error(text)
        messagebox.showerror("Something went wrong",
                             f"{exc.__name__}: {value}\n\nDetails were written to {ERROR_LOG.name}.", parent=self)


Box2BoxApp = FMReviewApp


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse the fixtures and results in a Football Manager save.")
    parser.add_argument("save", nargs="?", help="a .fm save to open straight away")
    args = parser.parse_args()
    set_taskbar_identity()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = Box2BoxApp()
    if args.save:
        app.after(300, lambda: app.open_save(args.save))
    app.mainloop()


if __name__ == "__main__":
    main()
