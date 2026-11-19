# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""The Yearbook reading window: the page model from yearbook_read, shown one page at a time or as reader spreads
(two pages of this window side by side, never two printed pages of the PDF) before an edition is saved. It only
reads pages; building and saving happen on the main window's workers, never on this thread.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import font as tkfont

import customtkinter as ctk
from tksheet import Sheet

import palette
import yearbook_read
from yearbook_read import SINGLE, SPREAD

FONT = "Segoe UI"
SERIF_FAMILIES = ("Georgia", "Cambria", "Times New Roman")    # headings only: tables keep the plain face
SPREAD_MIN_WIDTH = 1300        # narrower than this, a reader spread falls back to single pages
SIDEBAR = 340                  # the contents list and the margins beside the pages
MODES = {"Single page": SINGLE, "Reader spread": SPREAD}


def serif_family(root: tk.Misc) -> str:
    available = set(tkfont.families(root))
    return next((f for f in SERIF_FAMILIES if f in available), FONT)


class PagePane(ctk.CTkFrame):
    """One page: its heading, the lines the PDF prints, the table of the same columns and the footnotes."""

    def __init__(self, master: tk.Misc, serif: str) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=6, border_width=0)
        self.columnconfigure(0, weight=1)
        self.serif = serif
        self.marked_rows: tuple[int, ...] = ()
        self.heading_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(serif, 19, "bold"), anchor="w",
                                          justify="left")
        self.heading_label.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 8))
        self.lines_box = ctk.CTkTextbox(self, wrap="word", font=ctk.CTkFont(FONT, 12), height=120)
        self.lines_box.grid(row=1, column=0, sticky="nsew", padx=10)
        self.sheet = Sheet(self, theme="dark blue", show_row_index=False, show_top_left=False, table_wrap="",
                           header_wrap="", allow_cell_overflow=True, font=(FONT, 10, "normal"),
                           header_font=(FONT, 10, "bold"), outline_thickness=0, default_row_height=24)
        self.sheet.enable_bindings("single_select", "column_width_resize", "copy", "arrowkeys")
        self.sheet.grid(row=2, column=0, sticky="nsew", padx=10, pady=(8, 0))
        self.notes_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(FONT, 11), anchor="w", justify="left")
        self.notes_label.grid(row=3, column=0, sticky="ew", padx=10, pady=(8, 8))
        self._theme: palette.Theme | None = None
        self._kind = ""

    def apply_theme(self, theme: palette.Theme) -> None:
        self._theme = theme
        self.heading_label.configure(text_color=theme.heading[1])
        self.notes_label.configure(text_color=theme.muted)
        self.lines_box.configure(fg_color=theme.table[0], text_color=theme.table[1])
        self.sheet.set_options(frame_bg=theme.table[0], table_bg=theme.table[0], table_fg=theme.table[1],
                               table_grid_fg=theme.grid_line, header_bg=theme.sheet_heading[0],
                               header_fg=theme.sheet_heading[1], table_selected_cells_bg=theme.selection[0],
                               table_selected_cells_border_fg=theme.selection[1])
        self._finish()
        self._mark_rows()

    def _finish(self) -> None:
        """The cover's restrained finish: a hairline frame in the accent colour around the title page, nothing over
        the text. Other pages have none."""
        if self._theme is None:
            return
        cover = self._kind == "title"
        self.configure(border_width=1 if cover else 0, border_color=self._theme.accent[0])
        self.heading_label.configure(font=ctk.CTkFont(self.serif, 26 if cover else 19, "bold"))

    def _mark_rows(self) -> None:
        self.sheet.dehighlight_all()
        if self.marked_rows and self._theme is not None:
            self.sheet.highlight_rows(list(self.marked_rows), bg=self._theme.focus[0], fg=self._theme.focus[1])

    def set_wrap(self, width: int) -> None:
        for label in (self.heading_label, self.notes_label):
            label.configure(wraplength=max(width - 30, 200))

    def show_page(self, page: yearbook_read.ReadPage) -> None:
        self._kind = page.kind
        self._finish()
        self.heading_label.configure(text=page.heading)
        self.lines_box.configure(state="normal")
        self.lines_box.delete("1.0", "end")
        self.lines_box.insert("1.0", "\n".join(page.lines))
        self.lines_box.configure(state="disabled")
        if page.columns:
            self.sheet.set_sheet_data([list(r) for r in page.rows], reset_col_positions=True, reset_row_positions=True)
            self.sheet.headers(list(page.columns))
            self.sheet.set_all_column_widths()
            self.marked_rows = page.marked_rows
            self._mark_rows()
            self.sheet.grid()
            self.rowconfigure(1, weight=0)
            self.rowconfigure(2, weight=1)
            self.lines_box.configure(height=min(max(len(page.lines), 1) * 20 + 16, 230) if page.lines else 0)
            self.lines_box.grid_configure(sticky="ew")
            if not page.lines:
                self.lines_box.grid_remove()
            else:
                self.lines_box.grid()
        else:
            self.marked_rows = ()
            self.sheet.grid_remove()
            self.lines_box.grid()
            self.lines_box.grid_configure(sticky="nsew")
            self.rowconfigure(1, weight=1)
            self.rowconfigure(2, weight=0)
        self.notes_label.configure(text="\n".join(page.notes))


class YearbookReader(ctk.CTkToplevel):
    """The Yearbook, read before it is saved: each page's lines and table as the PDF will print them, a list of the
    competitions to jump to, a strip of the chapters near the page, Previous and Next, and single pages or reader
    spreads. It only reads the page model; saving goes through the main window's workers, never on this thread."""

    WIDTH, HEIGHT = 1140, 760

    def __init__(self, master: ctk.CTk, volume: yearbook_read.Volume,
                 on_save: Callable[[yearbook_read.Volume], object],
                 on_leave: Callable[[yearbook_read.Volume, str], object] = lambda volume, page_key: None,
                 start: int = 0, mode: str = SINGLE, on_mode: Callable[[str], object] = lambda mode: None) -> None:
        super().__init__(master)
        self.on_save, self.on_leave, self.on_mode = on_save, on_leave, on_mode
        self.mode = yearbook_read.reader_mode(mode)
        self._left = False
        self._layout_job: str | None = None
        self.volume = volume
        self.pages: list[yearbook_read.ReadPage] = []
        self.contents: list[tuple[str, int]] = []
        self.index = 0
        self.shown: tuple[int, ...] = (0,)
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.minsize(760, 480)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        serif = serif_family(self)

        self.strip = ctk.CTkFrame(self, fg_color="transparent")
        self.strip.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 0))
        self.strip_tiles = [tk.Label(self.strip, text="", font=(FONT, 10), padx=8, pady=3, cursor="hand2", borderwidth=0)
                            for _ in range(yearbook_read.STRIP_SPAN + 2)]
        self._strip_targets: list[int] = [0] * len(self.strip_tiles)
        for n, tile in enumerate(self.strip_tiles):
            tile.bind("<Button-1>", lambda _e, n=n: self.show(self._strip_targets[n]))

        self.contents_list = tk.Listbox(self, width=30, exportselection=False, activestyle="none", borderwidth=0,
                                        highlightthickness=0, font=(FONT, 11))
        self.contents_list.grid(row=1, column=0, sticky="ns", padx=(14, 6), pady=(10, 6))
        self.contents_list.bind("<<ListboxSelect>>", self._on_contents)

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=1, sticky="nsew", padx=(6, 14), pady=(10, 6))
        self.body.rowconfigure(0, weight=1)
        self.body.columnconfigure(0, weight=1, uniform="page")
        self.body.columnconfigure(2, weight=1, uniform="page")
        self.panes = [PagePane(self.body, serif), PagePane(self.body, serif)]
        self.panes[0].grid(row=0, column=0, sticky="nsew")
        self.gutter = ctk.CTkFrame(self.body, width=6, corner_radius=0)       # the shadow down the middle of a spread
        self.panes[1].grid(row=0, column=2, sticky="nsew")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 14))
        self.previous_button = ctk.CTkButton(bar, text="Previous", width=90, command=self.previous)
        self.previous_button.pack(side="left")
        self.page_label = ctk.CTkLabel(bar, text="", width=130)
        self.page_label.pack(side="left", padx=8)
        self.next_button = ctk.CTkButton(bar, text="Next", width=90, command=self.next)
        self.next_button.pack(side="left")
        self.close_button = ctk.CTkButton(bar, text="Close", width=90, command=self.destroy)
        self.close_button.pack(side="right")
        self.save_button = ctk.CTkButton(bar, text="Save this edition", width=150, command=self.save)
        self.save_button.pack(side="right", padx=8)
        self.mode_switch = ctk.CTkSegmentedButton(bar, values=list(MODES),
                                                  command=lambda label: self.set_mode(MODES[label]))
        self.mode_switch.pack(side="right", padx=8)

        for key, step in (("<Right>", 1), ("<Left>", -1), ("<Next>", 1), ("<Prior>", -1)):
            self.bind(key, lambda _e, s=step: self.step(s))
        self.bind("<Home>", lambda _e: self.show(0))
        self.bind("<End>", lambda _e: self.show(len(self.pages) - 1))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Configure>", self._on_resize)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.apply_theme(master.theme)
        self.load(volume, start)
        self.transient(master)
        self.after(100, self.bring_forward)

    # The first page pane, by the names the single-page reader used.
    heading_label = property(lambda self: self.panes[0].heading_label)
    lines_box = property(lambda self: self.panes[0].lines_box)
    sheet = property(lambda self: self.panes[0].sheet)
    notes_label = property(lambda self: self.panes[0].notes_label)
    marked_rows = property(lambda self: self.panes[0].marked_rows)

    def load(self, volume: yearbook_read.Volume, start: int = 0) -> None:
        """Show a volume in this window, at page `start`. Call leave() first to bookmark the volume shown before."""
        self.volume, self.pages, self.contents = volume, list(volume.pages), list(volume.contents)
        self._left = False
        self.title(f"Read the Yearbook {volume.season_label}")
        self.contents_list.delete(0, "end")
        for label, _ in self.contents:
            self.contents_list.insert("end", label)
        self.show(start)

    def leave(self) -> None:
        """Hand the page being read to on_leave, once, so the volume can reopen there."""
        if not self._left and self.pages:
            self._left = True
            self.on_leave(self.volume, self.pages[self.index].page_key)

    def destroy(self) -> None:
        self.leave()
        if self._layout_job is not None:
            self.after_cancel(self._layout_job)
            self._layout_job = None
        super().destroy()

    def apply_theme(self, theme: palette.Theme) -> None:
        self._theme = theme
        self.configure(fg_color=theme.window)
        self.contents_list.configure(bg=theme.competition_list[0], fg=theme.competition_list[1],
                                     selectbackground=theme.list_selected[0], selectforeground=theme.list_selected[1])
        self.page_label.configure(text_color=theme.muted)
        for button in (self.previous_button, self.next_button, self.save_button, self.close_button):
            button.configure(fg_color=theme.accent[0], hover_color=theme.accent_hover, text_color=theme.accent[1])
        self.mode_switch.configure(fg_color=theme.switch[0], unselected_color=theme.switch[0],
                                   unselected_hover_color=theme.switch_hover, selected_color=theme.switch_selected,
                                   selected_hover_color=theme.switch_selected_hover, text_color=theme.switch[1])
        self.gutter.configure(fg_color=theme.grid_line)
        for pane in self.panes:
            pane.apply_theme(theme)
        if self.pages:
            self._paint_strip()

    # ----------------------------------------------------------------- spreads

    def spread_on(self) -> bool:
        """Whether pages are shown as reader spreads: chosen, and the window is wide enough for two pages."""
        return self.mode == SPREAD and self.winfo_width() >= SPREAD_MIN_WIDTH

    def set_mode(self, mode: str) -> None:
        self.mode = yearbook_read.reader_mode(mode)
        self.on_mode(self.mode)
        self.show(self.index)

    def _on_resize(self, event) -> None:
        if event.widget is not self:
            return
        if self._layout_job is not None:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(120, self._relayout)

    def _relayout(self) -> None:
        self._layout_job = None
        if self.mode == SPREAD:                      # the window may now be too narrow for a spread, or wide enough
            self.show(self.index)
        else:
            self._set_wraps()

    def _set_wraps(self) -> None:
        width = max(self.winfo_width(), self.WIDTH) - SIDEBAR
        for pane in self.panes:
            pane.set_wrap(width // len(self.shown))

    def show(self, index: int) -> None:
        count = len(self.pages)
        index = max(0, min(index, count - 1))
        self.shown = yearbook_read.spread_at(index, count) if self.spread_on() else (index,)
        self.index = self.shown[0]
        self.panes[0].show_page(self.pages[self.shown[0]])
        if len(self.shown) == 2:
            self.panes[1].show_page(self.pages[self.shown[1]])
            self.gutter.grid(row=0, column=1, sticky="ns", padx=10)
            self.panes[1].grid()
            self.body.columnconfigure(2, weight=1, uniform="page")
        else:
            self.gutter.grid_remove()
            self.panes[1].grid_remove()
            self.body.columnconfigure(2, weight=0, uniform="")
        self._set_wraps()
        label = yearbook_read.spread_label(self.shown, count)
        if self.mode == SPREAD and not self.spread_on():
            label += " · widen the window for a reader spread"
        self.page_label.configure(text=label)
        self.mode_switch.set(next(k for k, v in MODES.items() if v == self.mode))
        self.previous_button.configure(state="normal" if self.shown[0] else "disabled")
        self.next_button.configure(state="normal" if self.shown[-1] < count - 1 else "disabled")
        here = self._chapter()
        self.contents_list.selection_clear(0, "end")
        if here is not None:
            self.contents_list.selection_set(here)
        self._paint_strip()

    def _chapter(self) -> int | None:
        return max((k for k, (_, start) in enumerate(self.contents) if start <= self.index), default=None)

    def _paint_strip(self) -> None:
        """The strip draws only the chapters near the page (yearbook_read.strip_window), with a tile for those
        before and after it: the same few tiles whatever the length of the book."""
        here = self._chapter() or 0
        start, stop = yearbook_read.strip_window(len(self.contents), here)
        tiles = []
        if start > 0:
            tiles.append((f"‹ {start} more", self.contents[start - 1][1], False))
        tiles += [(yearbook_read.strip_text(label), page, k == here)
                  for k, (label, page) in enumerate(self.contents[start:stop], start)]
        if stop < len(self.contents):
            tiles.append((f"{len(self.contents) - stop} more ›", self.contents[stop][1], False))
        t = self._theme
        for n, tile in enumerate(self.strip_tiles):
            if n < len(tiles):
                text, page, current = tiles[n]
                self._strip_targets[n] = page
                colours = t.list_selected if current else t.competition_list
                tile.configure(text=text, bg=colours[0], fg=colours[1])
                tile.pack(side="left", padx=(0, 4))
            else:
                tile.pack_forget()

    # ----------------------------------------------------------------- moving about

    def step(self, by: int) -> None:
        if self.spread_on():
            self.show(self.shown[-1] + 1 if by > 0 else self.shown[0] - 1)
        else:
            self.show(self.index + by)

    def next(self) -> None:
        self.step(1)

    def previous(self) -> None:
        self.step(-1)

    def _on_contents(self, _event) -> None:
        chosen = self.contents_list.curselection()
        if chosen:
            self.show(self.contents[chosen[0]][1])

    def save(self) -> None:
        self.on_save(self.volume)

    def bring_forward(self) -> None:
        self.lift()
        self.focus_force()
