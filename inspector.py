"""The inspector drawer: what it can show (a content model) and the overlay that shows it.

The window builds an InspectorModel from the match, club or competition selected; the Inspector widget
only draws one. The widget uses plain Tk labels, which are cheap to rebuild on every selection, and
never takes keyboard focus, so the sheet behind it keeps its keys.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass

import customtkinter as ctk

import fm_data as fd
import palette
import tooltip

WIDTH = 320            # px at 100 percent


@dataclass(frozen=True, slots=True)
class Heading:
    text: str


@dataclass(frozen=True, slots=True)
class Line:
    """A line of text. `muted` is a quiet remark; `marked` picks the line out (the selected match)."""

    text: str
    muted: bool = False
    marked: bool = False


@dataclass(frozen=True, slots=True)
class Stats:
    """Rows of figures for the two sides of a match."""

    home_name: str
    away_name: str
    rows: tuple[fd.StatLine, ...]


@dataclass(frozen=True, slots=True)
class Chips:
    """A form strip: W, D, L and ? chips, oldest first, with a note beside them."""

    letters: str
    note: str = ""
    tips: tuple[str, ...] = ()        # each chip's match in words, shown on hover; may be shorter or empty


@dataclass(frozen=True, slots=True)
class InspectorModel:
    title: str
    subtitle: str = ""
    blocks: tuple = ()


class Inspector(ctk.CTkFrame):
    """A drawer placed over the right edge of its parent, shut until opened."""

    def __init__(self, parent, *, px: Callable[[float], int], font: tuple, theme: palette.Theme,
                 on_close: Callable[[], None]) -> None:
        super().__init__(parent, width=px(WIDTH), corner_radius=px(8), border_width=1)
        self.pack_propagate(False)
        self._px, self._font, self._theme, self._on_close = px, font, theme, on_close
        self._bold = (font[0], font[1], "bold")
        self._model: InspectorModel | None = None
        self._texts: list[str] = []
        self.is_open = False
        self._header = tk.Frame(self, bd=0, highlightthickness=0)
        self._header.pack(fill="x", padx=px(10), pady=(px(10), 0))
        self._title = tk.Label(self._header, text="", anchor="w", justify="left", font=(font[0], font[1] + 2, "bold"),
                               wraplength=px(WIDTH - 70), bd=0)
        self._title.pack(side="left", fill="x", expand=True)
        self._close = tk.Label(self._header, text="×", font=font, bd=0, cursor="hand2")
        self._close.pack(side="right")
        self._close.bind("<Button-1>", lambda _e: self.close())
        self._subtitle = tk.Label(self, text="", anchor="w", justify="left", font=font, wraplength=px(WIDTH - 30), bd=0)
        self._subtitle.pack(fill="x", padx=px(10), pady=(px(2), px(6)))
        # The body sits in a canvas so that content taller than the drawer can scroll.
        self._viewport = tk.Canvas(self, bd=0, highlightthickness=0)
        self._viewport.pack(fill="both", expand=True, padx=px(10), pady=(0, px(8)))
        self._body = tk.Frame(self._viewport, bd=0, highlightthickness=0)
        self._window = self._viewport.create_window(0, 0, window=self._body, anchor="nw")
        self._body.bind("<Configure>", lambda _e: self._viewport.configure(scrollregion=self._viewport.bbox("all")))
        self._viewport.bind("<Configure>", lambda e: self._viewport.itemconfigure(self._window, width=e.width))
        self._viewport.bind("<MouseWheel>", self._on_wheel)
        # Windows sends the wheel to the widget under the pointer: every line in the body carries this tag.
        self._wheel_tag = f"InspectorWheel{id(self)}"
        self.bind_class(self._wheel_tag, "<MouseWheel>", self._on_wheel)
        self._paint_frame()
        self.tooltip = tooltip.Tooltip(self.winfo_toplevel(), theme=theme)

    # ----------------------------------------------------------------- showing and hiding

    def open(self) -> None:
        """Place the drawer over its parent's right edge. It does not take focus."""
        self.is_open = True
        self.place(relx=1.0, rely=0.0, anchor="ne", relheight=1.0, x=-self._px(4), y=self._px(2))
        self.lift()

    def close(self) -> None:
        was_open = self.is_open
        self.is_open = False
        self.tooltip.hide()
        self.place_forget()
        if was_open:
            self._on_close()

    def _on_wheel(self, event) -> str:
        self._viewport.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    # ----------------------------------------------------------------- content

    def rendered_text(self) -> list[str]:
        """Every piece of text the drawer shows, in order (for tests)."""
        return list(self._texts)

    def restyle(self, theme: palette.Theme) -> None:
        self._theme = theme
        self._paint_frame()
        self.tooltip.restyle(theme)
        if self._model is not None:
            self.show(self._model)

    def _paint_frame(self) -> None:
        t = self._theme
        self.configure(fg_color=t.panel, border_color=t.field[1])
        for widget in (self._header, self._viewport, self._body):
            widget.configure(bg=t.panel)
        self._title.configure(bg=t.panel, fg=t.text)
        self._close.configure(bg=t.panel, fg=t.muted)
        self._subtitle.configure(bg=t.panel, fg=t.muted)

    def show(self, model: InspectorModel) -> None:
        """Draw a model, replacing whatever was shown. A new model starts at the top; the same model drawn
        again (a theme change, a re-render) keeps its scroll position."""
        where = self._viewport.yview()[0] if model == self._model else 0.0
        self.tooltip.hide()                  # its chip is about to go, and a destroyed chip sends no <Leave>
        self._model = model
        for child in self._body.winfo_children():
            child.destroy()
        self._texts = [model.title, model.subtitle] if model.subtitle else [model.title]
        self._title.configure(text=model.title)
        self._subtitle.configure(text=model.subtitle)
        if model.subtitle:
            self._subtitle.pack(fill="x", padx=self._px(10), pady=(self._px(2), self._px(6)), before=self._viewport)
        else:
            self._subtitle.pack_forget()
        for block in model.blocks:
            if isinstance(block, Heading):
                self._add_heading(block)
            elif isinstance(block, Line):
                self._add_line(block)
            elif isinstance(block, Stats):
                self._add_stats(block)
            elif isinstance(block, Chips):
                self._add_chips(block)
        widgets = list(self._body.winfo_children())
        while widgets:
            widget = widgets.pop()
            widget.bindtags((self._wheel_tag, *widget.bindtags()))
            widgets.extend(widget.winfo_children())
        self._viewport.yview_moveto(where)

    def _label(self, parent, text: str, *, fg: str, bg: str, bold: bool = False, anchor: str = "w",
               justify: str = "left", **options):
        return tk.Label(parent, text=text, fg=fg, bg=bg, anchor=anchor, justify=justify, bd=0,
                        font=self._bold if bold else self._font, **options)

    def _add_heading(self, block: Heading) -> None:
        t = self._theme
        self._texts.append(block.text)
        self._label(self._body, block.text, fg=t.heading[1] if t.heading else t.text, bg=t.panel, bold=True).pack(
            fill="x", pady=(self._px(10), self._px(2)))

    def _add_line(self, block: Line) -> None:
        t = self._theme
        self._texts.append(block.text)
        fg, bg = (t.list_selected[1], t.list_selected[0]) if block.marked else (
            (t.muted, t.panel) if block.muted else (t.text, t.panel))
        self._label(self._body, block.text, fg=fg, bg=bg, wraplength=self._px(WIDTH - 40)).pack(
            fill="x", pady=(0, self._px(1)))

    def _add_stats(self, block: Stats) -> None:
        t = self._theme
        table = tk.Frame(self._body, bg=t.panel, bd=0, highlightthickness=0)
        table.pack(fill="x", pady=(self._px(4), 0))
        table.grid_columnconfigure(0, weight=1)
        for column, name in ((1, block.home_name), (2, block.away_name)):
            self._texts.append(name)
            self._label(table, name, fg=t.text, bg=t.panel, bold=True, anchor="e", justify="right",
                        wraplength=self._px(92)).grid(row=0, column=column, sticky="e", padx=(self._px(8), 0))
        for row, line in enumerate(block.rows, start=1):
            self._texts.append(f"{line.label}\t{line.home}\t{line.away}")
            self._label(table, line.label, fg=t.muted, bg=t.panel).grid(row=row, column=0, sticky="w")
            for column, value in ((1, line.home), (2, line.away)):
                self._label(table, value, fg=t.text, bg=t.panel, anchor="e").grid(
                    row=row, column=column, sticky="e", padx=(self._px(8), 0))

    def _add_chips(self, block: Chips) -> None:
        t = self._theme
        strip = tk.Frame(self._body, bg=t.panel, bd=0, highlightthickness=0)
        strip.pack(fill="x", pady=(self._px(2), self._px(2)))
        self._texts.append(" ".join(block.letters))
        for index, letter in enumerate(block.letters):
            fill, ink = t.colours.get(letter, (t.field[0], t.text))
            chip = tk.Label(strip, text=letter, width=2, font=self._bold, bg=fill, fg=ink or t.text, bd=0)
            chip.pack(side="left", padx=(0, self._px(3)))
            if index < len(block.tips):
                chip.bind("<Enter>", lambda e, tip=block.tips[index]: self.tooltip.show(tip, e.x_root, e.y_root))
                chip.bind("<Leave>", lambda _e: self.tooltip.hide())
        if block.note:
            self._texts.append(block.note)
            self._label(strip, block.note, fg=t.muted, bg=t.panel).pack(side="left", padx=(self._px(6), 0))
