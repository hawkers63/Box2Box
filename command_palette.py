"""The command palette: what it offers, how a typed query finds it and how results are ranked.

The matching is pure and has no window code, so it is tested on its own. The overlay that shows it
(CommandPalette) is at the foot of this module and is built by the main window.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import customtkinter as ctk

import palette as colour_themes

COMPETITION, CLUB, VIEW, SPLIT, ACTION = "Competition", "Club", "View", "Split", "Action"
RESULT_LIMIT = 12                                   # results shown at once
_KIND_ORDER = {kind: order for order, kind in enumerate((VIEW, SPLIT, ACTION, CLUB, COMPETITION))}
_OFFERED_WITHOUT_A_QUERY = (VIEW, SPLIT, ACTION)    # five thousand clubs are not a menu


@dataclass(frozen=True, slots=True)
class PaletteItem:
    """One thing the palette can do. `priority` lifts an item within its tier (the open competition's
    own clubs); `detail` is a second line shown beside the title, such as a club's competition."""

    kind: str
    title: str
    detail: str = ""
    action: Callable[[], None] | None = None
    priority: int = 0


def fold(text: str) -> str:
    """Text folded for matching: accents, case and punctuation gone, words separated by one space.
    Unlike the club-colour matching it keeps every word ('FC' and 'United' included)."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", plain.casefold()).split())


def _letters_of(query_word: str, title_word: str) -> bool:
    """True when the query word is the title word's first letter followed by some of its later letters
    in order: 'utd' in 'united'."""
    if not query_word or query_word[0] != title_word[:1]:
        return False
    rest = iter(title_word[1:])
    return all(letter in rest for letter in query_word[1:])


def _tier(query: str, words: list[str], title: str) -> int | None:
    """0 the exact title, 1 every query word starts a title word, 2 every query word starts a title word
    or abbreviates one ('utd'), 3 the query occurs inside the title; None for no match."""
    if title == query:
        return 0
    title_words = title.split()
    if all(any(t.startswith(q) for t in title_words) for q in words):
        return 1
    if all(any(t.startswith(q) or _letters_of(q, t) for t in title_words) for q in words):
        return 2
    if query in title:
        return 3
    return None


def search(items: Sequence[PaletteItem], query: str, limit: int = RESULT_LIMIT) -> list[PaletteItem]:
    """The items a query finds, best first and at most `limit`. A query with nothing to match (empty,
    spaces, punctuation) offers views, splits and actions in the order given. Within a tier a higher
    priority comes first, then views, splits, actions, clubs, competitions, then the title."""
    folded = fold(query)
    if not folded:
        return [i for i in items if i.kind in _OFFERED_WITHOUT_A_QUERY][:limit]
    words = folded.split()
    ranked = []
    for entry in items:
        title = fold(entry.title)
        tier = _tier(folded, words, title)
        if tier is not None:
            ranked.append(((tier, -entry.priority, _KIND_ORDER.get(entry.kind, len(_KIND_ORDER)), title), entry))
    ranked.sort(key=lambda pair: pair[0])
    return [entry for _, entry in ranked[:limit]]


class CommandPalette(ctk.CTkFrame):
    """The overlay: a search box over a short list of results, placed over the top of the window.

    Up and Down move, Enter runs the selected item, Escape closes. The window gives it the items each
    time it opens (`open`), so they always describe the save and view as they are then."""

    def __init__(self, parent, *, px: Callable[[float], int], on_error: Callable[[Exception], None],
                 theme: colour_themes.Theme) -> None:
        super().__init__(parent, corner_radius=px(10), border_width=1, width=px(620))
        self.pack_propagate(False)                # the width is fixed; _paint sets the height to fit the rows
        self._px = px
        self._on_error = on_error
        self._theme = theme
        self._items: list[PaletteItem] = []
        self.results: list[PaletteItem] = []
        self.selected_index = 0
        self.is_open = False
        self._came_from = None
        self._query = ctk.StringVar(self)
        self.entry = ctk.CTkEntry(self, textvariable=self._query, height=px(34),
                                  placeholder_text="Type to find a competition, club, view or action")
        self.entry.pack(fill="x", padx=px(10), pady=(px(10), px(6)))
        self._rows = []
        for index in range(RESULT_LIMIT):
            row = ctk.CTkFrame(self, corner_radius=px(6), height=px(30))
            row.pack_propagate(False)
            title = ctk.CTkLabel(row, text="", anchor="w")
            detail = ctk.CTkLabel(row, text="", anchor="w")
            tag = ctk.CTkLabel(row, text="", anchor="e")
            tag.pack(side="right", padx=(px(8), px(10)))
            title.pack(side="left", padx=(px(10), 0))
            detail.pack(side="left", padx=(px(8), 0), fill="x", expand=True)
            for widget in (row, title, detail, tag):
                widget.bind("<Button-1>", lambda _e, i=index: self._click(i))
            self._rows.append((row, title, detail, tag))
        self._empty = ctk.CTkLabel(self, text="Nothing matches.", anchor="w")
        self._query.trace_add("write", lambda *_: self._refresh())
        for key, step in (("<Up>", -1), ("<Down>", 1)):
            self.entry.bind(key, lambda _e, s=step: self._move(s))
        self.entry.bind("<Return>", lambda _e: self._run_and_break())
        self.entry.bind("<Escape>", lambda _e: self._close_and_break())
        for key in ("<Control-k>", "<Control-K>", "<Control-p>", "<Control-P>"):
            self.entry.bind(key, lambda _e: "break")         # already open; Ctrl+K must not delete the query
        self.restyle(theme)

    # ----------------------------------------------------------------- showing and hiding

    def open(self, items: list[PaletteItem]) -> None:
        """Show the palette over the window with these items and an empty query."""
        self._items = items
        if not self.is_open:
            self._came_from = self.winfo_toplevel().focus_get()
        self.is_open = True
        self._query.set("")
        self.selected_index = 0
        self._refresh()
        self.place(relx=0.5, y=self._px(70), anchor="n")
        self.lift()
        self.entry.focus_set()

    def close(self) -> None:
        """Hide the palette and give focus back to where it was."""
        if not self.is_open:
            return
        self.is_open = False
        self.place_forget()
        target, self._came_from = self._came_from, None
        try:
            if target is not None and target.winfo_exists():
                target.focus_set()
        except Exception:        # a widget destroyed in the meantime: focus simply stays put
            pass

    def _close_and_break(self) -> str:
        self.close()
        return "break"

    # ----------------------------------------------------------------- results

    def _refresh(self) -> None:
        self.results = search(self._items, self._query.get())
        self.selected_index = 0
        self._paint()

    def visible_titles(self) -> list[str]:
        return [item.title for item in self.results]

    def set_query(self, text: str) -> None:
        self._query.set(text)

    def _move(self, step: int) -> str:
        if self.results:
            self.selected_index = (self.selected_index + step) % len(self.results)
            self._paint()
        return "break"

    def _click(self, index: int) -> None:
        if index < len(self.results):
            self.selected_index = index
            self.run_selected()

    def _run_and_break(self) -> str:
        self.run_selected()
        return "break"

    def run_selected(self) -> None:
        """Close the palette and run the selected item; a failure is reported, never raised."""
        if not self.results:
            return
        item = self.results[self.selected_index]
        self.close()
        if item.action is not None:
            try:
                item.action()
            except Exception as exc:  # the palette must never take the window down
                self._on_error(exc)

    # ----------------------------------------------------------------- colours

    def restyle(self, theme: colour_themes.Theme) -> None:
        self._theme = theme
        self.configure(fg_color=theme.panel, border_color=theme.field[1])
        self.entry.configure(fg_color=theme.field[0], border_color=theme.field[1], text_color=theme.text)
        self._empty.configure(text_color=theme.muted)
        self._paint()

    def _paint(self) -> None:
        theme = self._theme
        for index, (row, title, detail, tag) in enumerate(self._rows):
            if index >= len(self.results):
                row.pack_forget()
                continue
            item = self.results[index]
            selected = index == self.selected_index
            fill = theme.list_selected[0] if selected else theme.panel
            main = theme.list_selected[1] if selected else theme.text
            quiet = theme.list_selected[1] if selected else theme.muted
            row.configure(fg_color=fill)
            title.configure(text=item.title, text_color=main, fg_color=fill)
            detail.configure(text=item.detail, text_color=quiet, fg_color=fill)
            tag.configure(text=item.kind, text_color=quiet, fg_color=fill)
            row.pack(fill="x", padx=self._px(10), pady=(0, self._px(2)))
        nothing = not self.results and bool(self._query.get().strip())
        if nothing:
            self._empty.pack(fill="x", padx=self._px(14), pady=(0, self._px(8)))
        else:
            self._empty.pack_forget()
        px = self._px
        self.configure(height=px(60) + len(self.results) * px(32) + (px(30) if nothing else 0))
