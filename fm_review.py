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
import sys
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox
from tkinter import font as tkfont
from typing import NamedTuple

import customtkinter as ctk
from tksheet import Sheet

import fm_data as fd
import fm_export as fx
from palette import COLOURS, DRAW_BG, FOCUS, HEADING, LOSS_BG, WIN_BG, ZONE_COLOURS, zone_legend

APP_TITLE = "Box2Box"
VERSION = "1.1"
APP_DIR = Path(__file__).resolve().parent
NAMES_PATH = APP_DIR / "competition_names.csv"
SETTINGS_PATH = APP_DIR / "box2box_settings.json"
LEGACY_SETTINGS_PATH = APP_DIR / "fm_review_settings.json"
ERROR_LOG = APP_DIR / "box2box_errors.log"
LICENCE_PATH = APP_DIR / "LICENSE"

# Word for word the first line of LICENSE.
COPYRIGHT = "Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved."
REPOSITORY = "https://github.com/hawkers63/Box2Box"

ALL_TEAMS = "All teams"
EXPORT_LABEL = "Export ▾"
HUB = "Competitions"
VIEWS = ("Results", "Grid", "Table", HUB)
GROUPINGS = (fd.GROUP_BY_WEEK, fd.GROUP_BY_MATCHDAY, fd.GROUP_BY_DATE)
MAX_TEAM_CHOICES = 120

FONT = "Segoe UI"
LIST_BG, LIST_FG = "#1d1d1d", "#e3e3e3"
SECTION_FG = "#d8b44a"
TABLE_BG = "#1b1b1b"

# Result, zone, heading and followed-team colours live in palette.py, shared with the exports.
FOCUS_TEXT = "#60a5fa"
WARNING_TEXT = "#fb923c"

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


def default_save_folder() -> Path:
    documents = documents_folder()
    for name in ("Football Manager 27", "Football Manager 2027", "Football Manager 26", "Football Manager 2026"):
        games = documents / "Sports Interactive" / name / "games"
        if games.is_dir():
            return games
    return documents


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
    """The name, version, copyright and licence: a band in the palette's heading colours over a
    stripe of the win, draw and loss colours."""

    WIDTH, HEIGHT = 600, 600
    PAD = 28

    def __init__(self, master: ctk.CTk) -> None:
        super().__init__(master)
        text = about_text()
        self.title(f"About {APP_TITLE}")
        self.transient(master)

        band = ctk.CTkFrame(self, fg_color=HEADING[0], corner_radius=0)
        band.pack(fill="x")
        ctk.CTkLabel(band, text=text.name, text_color=HEADING[1], font=ctk.CTkFont(FONT, 28, "bold"),
                     anchor="w").pack(fill="x", padx=self.PAD, pady=(18, 0))
        ctk.CTkLabel(band, text=text.version, text_color="gray75", font=ctk.CTkFont(FONT, 13),
                     anchor="w").pack(fill="x", padx=self.PAD, pady=(0, 16))
        stripe = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0, height=6)
        stripe.pack(fill="x")
        for colour in (WIN_BG, DRAW_BG, LOSS_BG):
            ctk.CTkFrame(stripe, fg_color=colour, corner_radius=0, width=1, height=6).pack(
                side="left", fill="x", expand=True)

        # Packed before the body so that a short screen squeezes the licence box, not the button.
        self.close_button = ctk.CTkButton(self, text="Close", width=100, command=self.destroy)
        self.close_button.pack(side="bottom", anchor="e", padx=self.PAD, pady=16)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=self.PAD, pady=(18, 0))
        for line, size, weight, colour in ((text.summary, 13, "normal", "gray80"),
                                            (text.copyright, 13, "bold", "#ffffff"),
                                            (text.notice, 12, "normal", "gray70")):
            ctk.CTkLabel(body, text=line, text_color=colour, font=ctk.CTkFont(FONT, size, weight),
                         wraplength=self.WIDTH - 2 * self.PAD, justify="left", anchor="w").pack(
                fill="x", pady=(0, 12))
        ctk.CTkLabel(body, text="LICENSE", text_color=HEADING[1], font=ctk.CTkFont(FONT, 11, "bold"),
                     anchor="w").pack(fill="x")
        self.licence_box = ctk.CTkTextbox(body, wrap="word", height=120, fg_color=TABLE_BG,
                                          font=ctk.CTkFont(FONT, 12))
        self.licence_box.pack(fill="both", expand=True, pady=(4, 0))
        self.licence_box.insert("1.0", licence_text(LICENCE_PATH))
        self.licence_box.configure(state="disabled")

        self.bind("<Escape>", lambda _e: self.destroy())
        self._place_over(master)
        self.after(100, self.bring_forward)

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


class FMReviewApp(ctk.CTk):
    """The main window: competitions on the left, the selected season's views on the right."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} {VERSION}")
        self.events: queue.Queue = queue.Queue()
        self.dataset: fd.Dataset | None = None
        self.names: dict[int, str] = {}
        self.settings = self._read_settings()
        self.loading_since: float | None = None
        self.loading_step = ""
        self._exporting = False
        self.about_window: AboutWindow | None = None

        self.comp_id: int | None = None
        self.season: int | None = None
        self.focus: int | None = None
        self.view = VIEWS[0]
        self.last_comp_view = VIEWS[0]     # the view a competition opens in from the hub
        self.group_by = fd.GROUP_BY_WEEK
        self.table_split = fd.SPLIT_OVERALL
        self.fixtures: tuple = ()
        self.labels: dict[int, str] = {}
        self.short_labels: dict[int, str] = {}
        self.list_rows: list[int | None] = []
        self.season_by_label: dict[str, int | None] = {}
        self.team_by_label: dict[str, int] = {}
        self.result_rows: list[fd.TimelineRow] = []
        self.grid_data: fd.Grid | None = None
        self.table_rows: list[int | None] = []
        self.comp_row_ids: list[int] = []
        self._list_job: str | None = None
        self._search_job: str | None = None
        self._dataset_serial = 0                  # bumped per installed save
        self._hub_key: tuple | None = None        # what the Competitions sheet was last filled from
        self._hub_summary = ""

        self.scale = ctk.ScalingTracker.get_window_scaling(self)
        width = min(1560, int(self.winfo_screenwidth() / self.scale * 0.92))
        height = min(940, int(self.winfo_screenheight() / self.scale * 0.85))
        self.geometry(f"{width}x{height}")
        self.minsize(1050, 620)
        self.cell_font = tkfont.Font(family=FONT, size=10)

        self._load_names()
        self._build()
        self._poll_job: str | None = self.after(100, self._poll)

    def destroy(self) -> None:
        for job in (self._poll_job, self._list_job, self._search_job):
            if job:
                self.after_cancel(job)
        self._poll_job = None
        super().destroy()

    # ----------------------------------------------------------------- layout

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, corner_radius=0, height=56)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.grid_columnconfigure(3, weight=1)
        self.open_button = ctk.CTkButton(top, text="Open save…", width=120, command=self.choose_save)
        self.open_button.grid(row=0, column=0, padx=(14, 10), pady=12)
        self.save_label = ctk.CTkLabel(top, text="No save open", font=ctk.CTkFont(FONT, 15, "bold"))
        self.save_label.grid(row=0, column=1, padx=(0, 12), sticky="w")
        self.meta_label = ctk.CTkLabel(top, text="", text_color="gray70")
        self.meta_label.grid(row=0, column=2, sticky="w")
        self.verify_label = ctk.CTkLabel(top, text="", text_color=WARNING_TEXT, cursor="hand2")
        self.verify_label.grid(row=0, column=3, padx=12, sticky="w")
        self.verify_label.bind("<Button-1>", lambda _e: self.show_details())
        self.progress = ctk.CTkProgressBar(top, mode="indeterminate", width=180)
        self.progress.grid(row=0, column=4, padx=14)
        self.progress.grid_remove()
        self.about_button = ctk.CTkButton(top, text="About", width=80, fg_color="gray30", hover_color="gray35",
                                          command=self.show_about)
        self.about_button.grid(row=0, column=5, padx=(0, 14), pady=12)

        side = ctk.CTkFrame(self, width=340, corner_radius=0)
        side.grid(row=1, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_rowconfigure(2, weight=1)
        side.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(side, text="Competitions", font=ctk.CTkFont(FONT, 14, "bold")).grid(
            row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        self.search_entry = ctk.CTkEntry(side, placeholder_text="Search competitions or clubs")
        self.search_entry.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="ew")
        self.search_entry.bind("<KeyRelease>", lambda _e: self._schedule_search())
        self.comp_list = tk.Listbox(
            side, activestyle="none", exportselection=False, bg=LIST_BG, fg=LIST_FG,
            selectbackground="#1f538d", selectforeground="#ffffff", highlightthickness=0,
            borderwidth=0, font=(FONT, 10),
        )
        self.comp_list.grid(row=2, column=0, padx=(12, 0), pady=(0, 12), sticky="nsew")
        list_scroll = ctk.CTkScrollbar(side, command=self.comp_list.yview)
        list_scroll.grid(row=2, column=1, padx=(0, 6), pady=(0, 12), sticky="ns")
        self.comp_list.configure(yscrollcommand=list_scroll.set)
        self.comp_list.bind("<<ListboxSelect>>", lambda _e: self._schedule_list_select())

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=1, sticky="nsew", padx=14, pady=(10, 6))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(header, text=APP_TITLE, font=ctk.CTkFont(FONT, 22, "bold"), anchor="w")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.rename_button = ctk.CTkButton(header, text="Name this competition…", width=170,
                                           fg_color="gray30", hover_color="gray35", command=self.rename_competition)
        self.rename_button.grid(row=0, column=1, rowspan=2, sticky="e")
        self.export_button = ctk.CTkButton(header, text=EXPORT_LABEL, width=100, command=self._show_export_menu)
        self.export_button.grid(row=0, column=2, rowspan=2, padx=(8, 0), sticky="e")
        self.export_menu = tk.Menu(self, tearoff=False)
        for kind, label in ((fx.EXCEL, "Excel workbook (.xlsx)"), (fx.HTML, "Web page (.html)"),
                            (fx.CSV, "CSV files (.csv)")):
            self.export_menu.add_command(label=label, command=lambda k=kind: self.export(k))
        self.export_menu.add_separator()
        self.export_menu.add_command(label="Open the export folder", command=self.open_export_folder)
        self.hint_label = ctk.CTkLabel(header, text="", text_color="gray70", anchor="w")
        self.hint_label.grid(row=1, column=0, sticky="w")

        controls = ctk.CTkFrame(main, fg_color="transparent")
        controls.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        ctk.CTkLabel(controls, text="Season").pack(side="left", padx=(0, 6))
        self.season_menu = ctk.CTkOptionMenu(controls, values=["–"], width=110, command=self._on_season)
        self.season_menu.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(controls, text="Team").pack(side="left", padx=(0, 6))
        self.team_box = ctk.CTkComboBox(controls, values=[ALL_TEAMS], width=250, command=self._on_team)
        self.team_box.pack(side="left", padx=(0, 16))
        self.team_box.bind("<Return>", self._on_team_typed)
        self.view_switch = ctk.CTkSegmentedButton(controls, values=list(VIEWS), command=self.set_view)
        self.view_switch.set(self.view)
        self.view_switch.pack(side="left", padx=(0, 16))
        self.group_label = ctk.CTkLabel(controls, text="Group by")
        self.group_label.pack(side="left", padx=(0, 6))
        self.group_switch = ctk.CTkSegmentedButton(controls, values=list(GROUPINGS), command=self._on_group)
        self.group_switch.set(self.group_by)
        self.group_switch.pack(side="left")

        self.split_label = ctk.CTkLabel(controls, text="Standings")
        self.split_switch = ctk.CTkSegmentedButton(controls, values=list(fd.SPLITS), command=self._on_table_split)
        self.split_switch.set(self.table_split)

        self.coverage_label = ctk.CTkLabel(main, text="", anchor="w", justify="left")
        self.coverage_label.grid(row=2, column=0, sticky="ew")
        self.note_label = ctk.CTkLabel(main, text="", anchor="w", justify="left", text_color="gray65",
                                       wraplength=1100)
        self.note_label.grid(row=3, column=0, sticky="ew", pady=(0, 6))

        content = ctk.CTkFrame(main, fg_color=TABLE_BG, corner_radius=6)
        content.grid(row=4, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)
        self.sheets = {
            "Results": self._make_sheet(content, show_row_index=False),
            "Grid": self._make_sheet(content, align="center"),
            "Table": self._make_sheet(content, show_row_index=False),
            HUB: self._make_sheet(content, show_row_index=False),
        }
        for name, sheet in self.sheets.items():
            sheet.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
            sheet.bind("<<SheetSelect>>", lambda _e, n=name: self._on_sheet_select(n))
            sheet.grid_remove()
        self.sheets[HUB].bind("<Double-Button-1>", lambda _e: self._open_from_hub())
        self.message = ctk.CTkFrame(content, fg_color=TABLE_BG)
        self.message.grid(row=0, column=0, sticky="nsew")
        self.message_label = ctk.CTkLabel(self.message, text="", font=ctk.CTkFont(FONT, 15), wraplength=700)
        self.message_label.pack(expand=True, pady=(0, 10))
        self.reopen_button = ctk.CTkButton(self.message, text="", width=300, command=self._reopen_last)

        self.detail_label = ctk.CTkLabel(main, text="", anchor="w", text_color="gray75")
        self.detail_label.grid(row=5, column=0, sticky="ew", pady=(4, 0))

        status = ctk.CTkFrame(self, corner_radius=0, height=30)
        status.grid(row=2, column=0, columnspan=2, sticky="ew")
        status.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(status, text="", anchor="w", text_color="gray70")
        self.status_label.grid(row=0, column=0, padx=14, sticky="ew")
        self.details_button = ctk.CTkButton(status, text="Save details & warnings", width=170, height=24,
                                            fg_color="gray30", hover_color="gray35", command=self.show_details)
        self.details_button.grid(row=0, column=1, padx=10, pady=3)

        self._set_controls_state("disabled")
        self._show_welcome()
        self._refresh_status()

    def _make_sheet(self, parent, **options) -> Sheet:
        with_index = options.get("show_row_index", True)
        sheet = Sheet(
            parent, theme="dark blue", show_top_left=with_index, row_index_align="w",
            table_wrap="", index_wrap="", header_wrap="", allow_cell_overflow=True,
            font=(FONT, 10, "normal"), header_font=(FONT, 10, "bold"), index_font=(FONT, 10, "normal"),
            frame_bg=TABLE_BG, table_bg=TABLE_BG, index_bg="#151515", header_bg="#151515",
            top_left_bg="#151515", table_grid_fg="#2b2b2b", outline_thickness=0,
            default_row_height=self.px(24), **options,
        )
        sheet.enable_bindings("single_select", "row_select", "column_select", "column_width_resize",
                              "arrowkeys", "copy", "right_click_popup_menu", "rc_select")
        return sheet

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
        try:
            dataset = fd.load_dataset(path, progress=lambda step: self.events.put(("progress", step)))
            self.events.put(("loaded", dataset))
        except fd.ImportFailed as exc:
            self.events.put(("failed", str(exc)))
        except Exception as exc:  # report anything unexpected rather than dying silently
            self._log_error(traceback.format_exc())
            self.events.put(("failed", f"Unexpected error while reading the save:\n{type(exc).__name__}: {exc}"))

    def _poll(self) -> None:
        try:
            while True:
                self.handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        if self.loading_since is not None:
            seconds = time.monotonic() - self.loading_since
            self.status_label.configure(
                text=f"Reading {self._loading_file}: {self.loading_step}…  {seconds:.0f} s "
                     "(a save usually takes about half a minute)")
        self._poll_job = self.after(150, self._poll)

    def handle_event(self, event: tuple) -> None:
        kind, payload = event
        if kind == "progress":
            self.loading_step = payload
            return
        if kind in ("exported", "export_failed"):
            self._finish_export(kind, payload)
            return
        self.loading_since = None
        self.progress.stop()
        self.progress.grid_remove()
        self.open_button.configure(state="normal")
        self.reopen_button.configure(state="normal")
        if kind == "loaded":
            self.install_dataset(payload)
        else:
            # A failed import leaves whatever was open before untouched.
            kept = "\n\nThe save that was already open is still shown." if self.dataset else ""
            self._refresh_status()
            if self.dataset is None:
                self._show_welcome()
            messagebox.showerror("Could not open the save", f"{payload}{kept}", parent=self)

    def install_dataset(self, dataset: fd.Dataset) -> None:
        self.dataset = dataset
        self._dataset_serial += 1
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
        self.verify_label.configure(
            text="" if info.known_build else "⚠ Unverified build: values unconfirmed (details)")
        self._refresh_status()
        self._set_controls_state("normal")
        self._sync_view_controls()
        self.comp_id = None
        self._fill_competition_list()
        if dataset.competitions:
            self.select_competition(dataset.competitions[0].id)
        else:
            self._show_message("This save holds no fixtures that could be read.")

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
        yours = [c for c in ds.competitions if c.is_yours and fd.matches_search(c, self.names, text)]
        others = [c for c in ds.competitions if not c.is_yours and fd.matches_search(c, self.names, text)]
        box = self.comp_list
        box.delete(0, "end")
        self.list_rows = []

        def heading(text: str) -> None:
            box.insert("end", text)
            box.itemconfig("end", fg=SECTION_FG, selectbackground=LIST_BG, selectforeground=SECTION_FG)
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
            heading("No competition or club matches the search")
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
        self.fixtures = fd.season_fixtures(ds, self.comp_id, season)
        self.labels = fd.team_labels(self.fixtures)
        self.short_labels = fd.team_labels(self.fixtures, short=True)
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
        self.team_box.set(self.labels[self.focus] if self.focus is not None else ALL_TEAMS)
        self._update_header()
        self.render()

    def _update_header(self) -> None:
        comp = self.dataset.by_id[self.comp_id]
        self.title_label.configure(text=fd.competition_title(comp, self.names))
        ids = f"competition id {comp.id}" + (f" · database id {comp.database_id}" if comp.database_id is not None else "")
        self.hint_label.configure(text=f"{fd.competition_hint(comp)}  ·  {ids}")

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
        answer = ctk.CTkInputDialog(title="Name this competition", text=prompt).get_input()
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
            self.team_box.set(self.labels[self.focus] if self.focus is not None else ALL_TEAMS)

    def set_focus(self, team_id: int | None) -> None:
        self.focus = team_id if team_id in self.labels else None
        self.team_box.set(self.labels[self.focus] if self.focus is not None else ALL_TEAMS)
        self.render()

    def set_view(self, view: str) -> None:
        self.view = view
        if view != HUB:
            self.last_comp_view = view
        self.view_switch.set(view)
        self._sync_view_controls()
        self.render()

    def _sync_view_controls(self) -> None:
        """Show the grouping or standings switch the view uses, and enable the season and team
        pickers only where they apply: the hub covers every competition at once."""
        for widget in (self.group_label, self.group_switch, self.split_label, self.split_switch):
            widget.pack_forget()
        if self.view == "Results":
            self.group_label.pack(side="left", padx=(0, 6))
            self.group_switch.pack(side="left")
        elif self.view == "Table":
            self.split_label.pack(side="left", padx=(0, 6))
            self.split_switch.pack(side="left")
        state = "normal" if self.dataset and self.view != HUB else "disabled"
        for widget in (self.season_menu, self.team_box, self.group_switch, self.split_switch):
            widget.configure(state=state)

    def _on_table_split(self, value: str) -> None:
        self.table_split = value
        self.render()

    def _on_group(self, value: str) -> None:
        self.group_by = value
        self.render()

    def _set_controls_state(self, state: str) -> None:
        for widget in (self.season_menu, self.team_box, self.view_switch, self.group_switch,
                       self.split_switch, self.rename_button, self.details_button, self.search_entry):
            widget.configure(state=state)
        self.export_button.configure(state="disabled" if self._exporting else state)

    # ----------------------------------------------------------------- exports

    def _show_export_menu(self) -> None:
        button = self.export_button
        try:
            self.export_menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        finally:
            self.export_menu.grab_release()

    def export(self, kind: str) -> None:
        """Export the selected competition and season, as shown, on a background thread."""
        if not self.dataset or self.comp_id is None or self._exporting:
            return
        request = fx.ExportRequest(self.dataset, self.comp_id, self.season, names=dict(self.names),
                                   focus=self.focus, group_by=self.group_by)
        self._exporting = True
        self.export_button.configure(state="disabled", text="Exporting…")
        self.detail_label.configure(text=f"Exporting the {fx.KINDS[kind]}…")
        threading.Thread(target=self._export_worker, args=(kind, request, export_folder()), daemon=True).start()

    def _export_worker(self, kind: str, request: fx.ExportRequest, folder: Path) -> None:
        try:
            self.events.put(("exported", (kind, fx.export(kind, request, folder))))
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
        export_kind, path = payload
        what = fx.KINDS[export_kind]
        self.detail_label.configure(text=f"Saved the {what} {path.name} in {path.parent}")
        if messagebox.askyesno("Export saved", f"Saved the {what}\n\n{path.name}\n\nin {path.parent}.\n\nOpen it now?",
                               parent=self):
            self._open_path(path)

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
        if not self.dataset:
            return
        if self.view == HUB:
            self._render_competitions()
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
        {"Results": self._render_results, "Grid": self._render_grid, "Table": self._render_table}[self.view]()

    def _show_sheet(self, name: str) -> Sheet:
        self.message.grid_remove()
        for key, sheet in self.sheets.items():
            if key == name:
                sheet.grid()
            else:
                sheet.grid_remove()
        return self.sheets[name]

    def _show_message(self, text: str) -> None:
        for sheet in self.sheets.values():
            sheet.grid_remove()
        self.message_label.configure(text=text)
        self.reopen_button.pack_forget()
        self.message.grid()

    def _show_welcome(self) -> None:
        self._show_message("Open a Football Manager 27 save to browse its fixtures and results.\n\n"
                           "Saves are in Documents\\Sports Interactive\\Football Manager 27\\games. "
                           "The save is only read, never changed.")
        last = self.settings.get("last_save")
        if last and Path(last).is_file():
            self.reopen_button.configure(text=f"Open {Path(last).name}")
            self.reopen_button.pack(pady=(0, 40))

    @staticmethod
    def _paint(sheet: Sheet, row: int, column: int, colours, canvas: str = "table") -> None:
        bg, fg = colours
        options = {k: v for k, v in (("bg", bg), ("fg", fg)) if v is not None}
        if options:
            sheet.highlight_cells(row=row, column=column, canvas=canvas, redraw=False, **options)

    def _render_results(self) -> None:
        focus = self.focus
        rows = fd.timeline(self.fixtures, self.labels, group_by=self.group_by, focus_team=focus)
        self.result_rows = rows
        headers = ["Date", "KO", "Home", "Score", "Away", "Round"] + (["Res", "Pts"] if focus is not None else [])
        blank = [""] * (len(headers) - 1)
        data = [[r.heading, *blank] if r.is_heading else
                [r.date, r.time, r.home, r.score, r.away, r.round] + ([r.result, r.points] if focus is not None else [])
                for r in rows]
        sheet = self._show_sheet("Results")
        sheet.set_sheet_data(data, reset_col_positions=True, reset_row_positions=True, redraw=False,
                             reset_highlights=True)
        sheet.headers(headers, redraw=False)
        names = [r.home for r in rows] + [r.away for r in rows]
        team_width = self._text_width(names, minimum=180)
        widths = [self.px(110), self.px(56), team_width, self.px(64), team_width, self.px(100), self.px(46), self.px(54)]
        sheet.set_column_widths(widths[:len(headers)])
        sheet.align_columns([1, 3, 5, 6, 7][: 3 if focus is None else 5], align="center", align_header=True, redraw=False)
        first_unplayed = None
        for i, r in enumerate(rows):
            if r.is_heading:
                sheet.highlight_rows(i, bg=HEADING[0], fg=HEADING[1], redraw=False, end_of_screen=True)
                continue
            if first_unplayed is None and r.kind == fd.SCHEDULED:
                first_unplayed = i
            if focus is not None and r.result:
                self._paint(sheet, i, 3, COLOURS[r.result])
                self._paint(sheet, i, 6, COLOURS[r.result])
            elif r.kind in (fd.UNAVAILABLE, fd.SCHEDULED):
                self._paint(sheet, i, 3, COLOURS[r.kind])
            if focus is not None:
                self._paint(sheet, i, 2 if r.home_id == focus else 4, (None, FOCUS_TEXT))
        sheet.refresh()
        # Open on the most recent results: just before the first match still to play.
        target = len(rows) - 1 if first_unplayed is None else max(0, first_unplayed - 6)
        sheet.set_yview(target / max(len(rows), 1) if target > 0 else 0.0)
        note = []
        if focus is not None:
            note.append("Res and Pts are for the team you follow; points count 3 for a win and 1 for a draw."
                        " * = a played match has no recoverable score, so the total is a minimum.")
        note.append("“n/a” = played, but no score could be recovered from the save. Click a match for details.")
        self.note_label.configure(text=" ".join(note))

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

        for r, row in enumerate(grid.cells):
            for c, cell in enumerate(row):
                if cell.kind == "self":
                    self._paint(sheet, r, c, COLOURS["self"])
                elif focus_idx is not None and r == focus_idx:
                    # Followed team at home: Home Win is a win (W), Away Win is a loss (L)
                    if cell.kind == fd.HOME_WIN:
                        self._paint(sheet, r, c, COLOURS["W"])
                    elif cell.kind == fd.DRAW:
                        self._paint(sheet, r, c, COLOURS["D"])
                    elif cell.kind == fd.AWAY_WIN:
                        self._paint(sheet, r, c, COLOURS["L"])
                    elif cell.kind in COLOURS:
                        self._paint(sheet, r, c, COLOURS[cell.kind])
                elif focus_idx is not None and c == focus_idx:
                    # Followed team away: Away Win is a win (W), Home Win is a loss (L)
                    if cell.kind == fd.AWAY_WIN:
                        self._paint(sheet, r, c, COLOURS["W"])
                    elif cell.kind == fd.DRAW:
                        self._paint(sheet, r, c, COLOURS["D"])
                    elif cell.kind == fd.HOME_WIN:
                        self._paint(sheet, r, c, COLOURS["L"])
                    elif cell.kind in COLOURS:
                        self._paint(sheet, r, c, COLOURS[cell.kind])
                elif cell.kind in COLOURS:
                    self._paint(sheet, r, c, COLOURS[cell.kind])

        if focus_idx is not None:
            self._paint(sheet, focus_idx, 0, FOCUS, canvas="index")
            sheet.highlight_cells(column=focus_idx, canvas="header", bg=FOCUS[0], fg=FOCUS[1], redraw=False)
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
        headers = ["Pos", "Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts", "Form"]
        data, self.table_rows, headings, focus_rows, zone_cells = [], [], [], [], []
        for title, rows in result.groups:
            if title:
                headings.append(len(data))
                data.append([title] + [""] * (len(headers) - 1))
                self.table_rows.append(None)
            for r in rows:
                row_idx = len(data)
                if r.team_id == self.focus:
                    focus_rows.append(row_idx)
                if r.zone and r.zone in ZONE_COLOURS:
                    zone_cells.append((row_idx, 0, ZONE_COLOURS[r.zone]))
                gd = r.goal_difference
                data.append([r.position, r.team, r.played, r.won, r.drawn, r.lost, r.goals_for, r.goals_against,
                             f"{gd:+d}" if gd else "0", r.points, "  ".join(r.form)])
                self.table_rows.append(r.team_id)
        sheet = self._show_sheet("Table")
        sheet.set_sheet_data(data, reset_col_positions=True, reset_row_positions=True, redraw=False,
                             reset_highlights=True)
        sheet.headers(headers, redraw=False)
        team_width = self._text_width([row[1] for row in data], minimum=200)
        sheet.set_column_widths([self.px(46), team_width] + [self.px(44)] * 7 + [self.px(50), self.px(130)])
        sheet.align_columns([0] + list(range(2, 11)), align="center", align_header=True, redraw=False)
        for i in headings:
            sheet.highlight_rows(i, bg=HEADING[0], fg=HEADING[1], redraw=False, end_of_screen=True)
        for i in focus_rows:
            sheet.highlight_rows(i, bg=FOCUS[0], fg=FOCUS[1], redraw=False, end_of_screen=False)
        for row_idx, col_idx, colours in zone_cells:
            self._paint(sheet, row_idx, col_idx, colours)
        sheet.refresh()
        note = [result.note]
        legend = zone_legend({r.zone for _, rows in result.groups for r in rows})
        if legend:
            note.append(result.zones_note)
            note.append(f"Pos colours: {legend}.")
        note.append("Click a team to follow it.")
        self.note_label.configure(text=" ".join(part for part in note if part))

    def _render_competitions(self) -> None:
        """Fill the hub once per save and set of names; after that only the highlighted row moves,
        so picking a competition keeps the hub's scroll position."""
        ds = self.dataset
        if not ds:
            return
        sheet = self._show_sheet(HUB)
        key = (self._dataset_serial, tuple(sorted(self.names.items())))
        if key != self._hub_key:
            self._fill_hub(sheet, fd.competitions_summary(ds, self.names))
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
        for i, s in enumerate(summaries):
            if s.category == fd.COMP_CAT_YOURS:
                sheet.highlight_rows(i, bg="#132338", fg="#93c5fd", redraw=False, end_of_screen=False)
                self._paint(sheet, i, 0, ("#1e3a8a", "#dbeafe"))
            elif s.category == fd.COMP_CAT_CUP:
                self._paint(sheet, i, 0, ("#312e81", "#e0e7ff"))
            elif s.category == fd.COMP_CAT_YOUTH:
                self._paint(sheet, i, 0, ("#1f2937", "#9ca3af"))
            elif s.category == fd.COMP_CAT_LEAGUE:
                self._paint(sheet, i, 0, ("#064e3b", "#a7f3d0"))
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
                self.detail_label.configure(text=fd.describe_fixture(item.fixture, self.labels))
        elif name == "Grid" and self.grid_data is not None:
            grid = self.grid_data
            if selected.type_ == "rows" and 0 <= row < len(grid.team_ids):
                self.set_focus(grid.team_ids[row])
            elif selected.type_ == "columns" and column is not None and 0 <= column < len(grid.team_ids):
                self.set_focus(grid.team_ids[column])
            elif 0 <= row < len(grid.cells) and column is not None and 0 <= column < len(grid.team_ids):
                cell = grid.cells[row][column]
                home, away = grid.row_labels[row], grid.row_labels[column]
                if cell.fixtures:
                    text = "   |   ".join(fd.describe_fixture(f, self.labels) for f in cell.fixtures)
                elif row == column:
                    text = ""
                else:
                    text = f"{home} v {away}: no fixture between them at {home}'s ground this season."
                self.detail_label.configure(text=text)
        elif name == "Table" and 0 <= row < len(self.table_rows) and self.table_rows[row] is not None:
            if self.table_rows[row] != self.focus:
                self.set_focus(self.table_rows[row])
        elif name == HUB and self.view == HUB and 0 <= row < len(self.comp_row_ids):
            if self.comp_row_ids[row] != self.comp_id:
                self.select_competition(self.comp_row_ids[row])

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
            f"Names file:      {NAMES_PATH} ({len(self.names)} names)",
            "",
            "fmsave only reads the save. It never changes it.",
            "",
            f"Reader warnings ({len(info.warnings)}):",
        ]
        lines += [f"  • {w}" for w in info.warnings] or ["  none"]
        window = ctk.CTkToplevel(self)
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
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = Box2BoxApp()
    if args.save:
        app.after(300, lambda: app.open_save(args.save))
    app.mainloop()


if __name__ == "__main__":
    main()
