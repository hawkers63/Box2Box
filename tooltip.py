"""A small tooltip: a borderless window with one line of text, shown beside the pointer.

Used over the form pills on the sheets and the chips in the inspector drawer. It never takes focus.
"""

from __future__ import annotations

import tkinter as tk

import palette

OFFSET = 14          # px from the pointer, so the tooltip never sits under it


class Tooltip:
    def __init__(self, root: tk.Misc, *, theme: palette.Theme) -> None:
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self._label = tk.Label(self.window, text="", bd=0, padx=8, pady=4,
                               bg=theme.panel, fg=theme.text)
        self._label.pack()
        self.is_shown = False

    @property
    def text(self) -> str:
        return self._label.cget("text")

    def show(self, text: str, x_root: int, y_root: int) -> None:
        """Show the text just below and to the right of the pointer at (x_root, y_root)."""
        self._label.configure(text=text)
        self.window.geometry(f"+{x_root + OFFSET}+{y_root + OFFSET}")
        self.window.deiconify()
        self.is_shown = True

    def restyle(self, theme: palette.Theme) -> None:
        self._label.configure(bg=theme.panel, fg=theme.text)

    def hide(self) -> None:
        self.window.withdraw()
        self.is_shown = False
