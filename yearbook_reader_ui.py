# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""The Yearbook reading window: the page model from yearbook_read, shown page by page before an edition is saved.
It only reads pages; building and saving happen on the main window's workers, never on this thread.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk
from tksheet import Sheet

import palette
import yearbook_read

FONT = "Segoe UI"


class YearbookReader(ctk.CTkToplevel):
    """The Yearbook, read page by page before it is saved: each page's lines and table as the PDF will print them,
    a list of the competitions to jump to, Previous and Next. It only reads the page model; saving goes through the
    same worker as the menu, never on this thread."""

    WIDTH, HEIGHT = 1140, 760

    def __init__(self, master: ctk.CTk, volume: yearbook_read.Volume,
                 on_save: Callable[[yearbook_read.Volume], object],
                 on_leave: Callable[[yearbook_read.Volume, str], object] = lambda volume, page_key: None,
                 start: int = 0) -> None:
        super().__init__(master)
        self.on_save, self.on_leave = on_save, on_leave
        self._left = False
        self.volume = volume
        self.pages: list[yearbook_read.ReadPage] = []
        self.contents: list[tuple[str, int]] = []
        self.index = 0
        self.marked_rows: tuple[int, ...] = ()
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.minsize(760, 480)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.contents_list = tk.Listbox(self, width=30, exportselection=False, activestyle="none", borderwidth=0,
                                        highlightthickness=0, font=(FONT, 11))
        self.contents_list.grid(row=0, column=0, sticky="ns", padx=(14, 6), pady=(14, 6))
        self.contents_list.bind("<<ListboxSelect>>", self._on_contents)

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=0, column=1, sticky="nsew", padx=(6, 14), pady=(14, 6))
        self.body.columnconfigure(0, weight=1)
        self.heading_label = ctk.CTkLabel(self.body, text="", font=ctk.CTkFont(FONT, 18, "bold"), anchor="w",
                                          justify="left", wraplength=self.WIDTH - 340)
        self.heading_label.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.lines_box = ctk.CTkTextbox(self.body, wrap="word", font=ctk.CTkFont(FONT, 12), height=120)
        self.lines_box.grid(row=1, column=0, sticky="nsew")
        self.sheet = Sheet(self.body, theme="dark blue", show_row_index=False, show_top_left=False, table_wrap="",
                           header_wrap="", allow_cell_overflow=True, font=(FONT, 10, "normal"),
                           header_font=(FONT, 10, "bold"), outline_thickness=0, default_row_height=24)
        self.sheet.enable_bindings("single_select", "column_width_resize", "copy", "arrowkeys")
        self.sheet.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        self.notes_label = ctk.CTkLabel(self.body, text="", font=ctk.CTkFont(FONT, 11), anchor="w", justify="left",
                                        wraplength=self.WIDTH - 340)
        self.notes_label.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 14))
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

        for key, step in (("<Right>", 1), ("<Left>", -1), ("<Next>", 1), ("<Prior>", -1)):
            self.bind(key, lambda _e, s=step: self.step(s))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.apply_theme(master.theme)
        self.load(volume, start)
        self.transient(master)
        self.after(100, self.bring_forward)

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
        super().destroy()

    def apply_theme(self, theme: palette.Theme) -> None:
        self.configure(fg_color=theme.window)
        self.contents_list.configure(bg=theme.competition_list[0], fg=theme.competition_list[1],
                                     selectbackground=theme.list_selected[0], selectforeground=theme.list_selected[1])
        self.heading_label.configure(text_color=theme.heading[1])
        for label in (self.notes_label, self.page_label):
            label.configure(text_color=theme.muted)
        self.lines_box.configure(fg_color=theme.table[0], text_color=theme.table[1])
        for button in (self.previous_button, self.next_button, self.save_button, self.close_button):
            button.configure(fg_color=theme.accent[0], hover_color=theme.accent_hover, text_color=theme.accent[1])
        self.sheet.set_options(frame_bg=theme.table[0], table_bg=theme.table[0], table_fg=theme.table[1],
                               table_grid_fg=theme.grid_line, header_bg=theme.sheet_heading[0],
                               header_fg=theme.sheet_heading[1], table_selected_cells_bg=theme.selection[0],
                               table_selected_cells_border_fg=theme.selection[1])
        self._theme = theme
        self._mark_rows()

    def _mark_rows(self) -> None:
        self.sheet.dehighlight_all()
        if self.marked_rows:
            self.sheet.highlight_rows(list(self.marked_rows), bg=self._theme.focus[0], fg=self._theme.focus[1])

    def show(self, index: int) -> None:
        self.index = max(0, min(index, len(self.pages) - 1))
        page = self.pages[self.index]
        self.heading_label.configure(text=page.heading)
        self.lines_box.configure(state="normal")
        self.lines_box.delete("1.0", "end")
        self.lines_box.insert("1.0", "\n".join(page.lines))
        self.lines_box.configure(state="disabled")
        has_table = bool(page.columns)
        if has_table:
            self.sheet.set_sheet_data([list(r) for r in page.rows], reset_col_positions=True, reset_row_positions=True)
            self.sheet.headers(list(page.columns))
            self.sheet.set_all_column_widths()
            self.marked_rows = page.marked_rows
            self._mark_rows()
            self.sheet.grid()
            self.body.rowconfigure(1, weight=0)
            self.body.rowconfigure(2, weight=1)
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
            self.body.rowconfigure(1, weight=1)
            self.body.rowconfigure(2, weight=0)
        self.notes_label.configure(text="\n".join(page.notes))
        self.page_label.configure(text=f"Page {self.index + 1} of {len(self.pages)}")
        self.previous_button.configure(state="normal" if self.index else "disabled")
        self.next_button.configure(state="normal" if self.index < len(self.pages) - 1 else "disabled")
        here = max((k for k, (_, start) in enumerate(self.contents) if start <= self.index), default=None)
        self.contents_list.selection_clear(0, "end")
        if here is not None:
            self.contents_list.selection_set(here)

    def step(self, by: int) -> None:
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
