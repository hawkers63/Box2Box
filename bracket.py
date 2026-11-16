"""The cup bracket: where each tie's box goes in the tree (pure geometry), and the canvas that draws it.

The layout has no Tk in it, so it is tested on its own. A tie sits between the two ties that fed it: the last
round's ties are placed first and each earlier round follows from them.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import fm_data as fd
import palette


@dataclass(frozen=True, slots=True)
class Box:
    tie: fd.CupTie
    column: int
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class TreeLayout:
    boxes: tuple[Box, ...]
    links: tuple[tuple[tuple[int, int], ...], ...]      # polylines from a tie to the tie it fed
    headings: tuple[tuple[int, str], ...]               # (centre x, round name) for each column
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class TieText:
    """What a tie's box says: each side's name and its goals in each meeting, and which side went through."""

    a_name: str
    a_goals: str
    b_name: str
    b_goals: str
    winner: str | None           # "a", "b" or None when it cannot be told
    inferred: bool = False       # the winner is only known from the next round (a drawn match; the save does not
    #                              store extra time or penalties)


def describe_tie(tie: fd.CupTie, labels) -> TieText:
    name = lambda team: labels.get(team, f"Team {team}")      # noqa: E731

    def goals(team: int) -> str:
        parts = []
        for f in tie.fixtures:
            if not fd.has_score(f):
                parts.append("n/a" if f.played else "")
            else:
                parts.append(str(f.home_goals if f.home_team_id == team else f.away_goals))
        return " · ".join(parts)

    winner = "a" if tie.winner == tie.team_a else "b" if tie.winner == tie.team_b else None
    return TieText(name(tie.team_a), goals(tie.team_a), name(tie.team_b), goals(tie.team_b), winner,
                   tie.how == "next round")


def layout_tree(rounds: Sequence[fd.CupRound], *, box: tuple[int, int] = (200, 48),
                gap: tuple[int, int] = (28, 12), heading: int = 24) -> TreeLayout:
    """Boxes, links and headings for rounds that halve down to a final, earliest round first."""
    width, height = box
    gap_x, gap_y = gap
    if not rounds:
        return TreeLayout((), (), (), 0, 0)
    # Order each round so that the two ties feeding a later tie are neighbours, working back from the final.
    ordered = [list(rounds[-1].ties)]
    for earlier in reversed(rounds[:-1]):
        by_team = {t: tie for tie in earlier.ties for t in (tie.team_a, tie.team_b)}
        row, used = [], set()
        for later in ordered[0]:
            for team in (later.team_a, later.team_b):
                feeder = by_team.get(team)
                if feeder is not None and id(feeder) not in used:
                    used.add(id(feeder))
                    row.append(feeder)
        row += [tie for tie in earlier.ties if id(tie) not in used]            # any left over, in the save's order
        ordered.insert(0, row)
    ys: list[list[int]] = [[heading + i * (height + gap_y) for i in range(len(ordered[0]))]]
    for column in range(1, len(ordered)):
        previous, row = ordered[column - 1], []
        by_team = {t: i for i, tie in enumerate(previous) for t in (tie.team_a, tie.team_b)}
        for later in ordered[column]:
            centres = [ys[column - 1][by_team[t]] + height // 2 for t in (later.team_a, later.team_b) if t in by_team]
            row.append((sum(centres) // len(centres)) - height // 2 if centres else heading)
        ys.append(row)
    boxes, links = [], []
    for column, ties in enumerate(ordered):
        x = column * (width + gap_x)
        for tie, y in zip(ties, ys[column]):
            boxes.append(Box(tie, column, x, y, width, height))
    for column in range(1, len(ordered)):
        later_at = {t: (ordered[column][i], ys[column][i]) for i in range(len(ordered[column]))
                    for t in (ordered[column][i].team_a, ordered[column][i].team_b)}
        x_out = (column - 1) * (width + gap_x) + width
        for tie, y in zip(ordered[column - 1], ys[column - 1]):
            target = next((later_at[t] for t in (tie.team_a, tie.team_b) if t in later_at), None)
            if target is not None:
                start, end = y + height // 2, target[1] + height // 2
                links.append(((x_out, start), (x_out + gap_x // 2, start), (x_out + gap_x // 2, end),
                              (x_out + gap_x, end)))
    return TreeLayout(tuple(boxes), tuple(links), tuple((c * (width + gap_x) + width // 2, r.name)
                                                       for c, r in enumerate(rounds)),
                      len(ordered) * (width + gap_x) - gap_x, heading + len(ordered[0]) * (height + gap_y) - gap_y)


INFERRED_NOTE = ("* A drawn match: the save does not store extra time or penalties, so the winner is the side "
                 "that plays in the next round.")


NO_TREE_NOTE = ("No bracket: this competition does not end in a single final that the rounds before it halve down "
                "to. Its rounds are listed below.")


class BracketView(tk.Frame):
    """A scrollable canvas: the tree of the last rounds, then the earlier rounds as a list."""

    BOX = (210, 50)
    GAP = (30, 12)

    def __init__(self, parent, *, px: Callable[[float], int], font: tuple, theme: palette.Theme) -> None:
        super().__init__(parent, bd=0, highlightthickness=0)
        self._px, self._font, self._theme = px, font, theme
        self._bold = (font[0], font[1], "bold")
        self._canvas = tk.Canvas(self, bd=0, highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<MouseWheel>", lambda e: self._canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self._canvas.bind("<Shift-MouseWheel>", lambda e: self._canvas.xview_scroll(-1 if e.delta > 0 else 1, "units"))
        self._texts: list[str] = []
        self._rounds: tuple = ()
        self._shown: tuple | None = None            # what was last drawn, to draw it again in a new theme

    def use_theme(self, theme: palette.Theme) -> None:
        """Take a theme (the window's, with the followed club's tint) for the next drawing."""
        self._theme = theme

    def restyle(self, theme: palette.Theme) -> None:
        self._theme = theme
        if self._shown is not None:
            self.show(*self._shown)
        else:
            self._canvas.configure(bg=theme.table[0])

    def rendered_text(self) -> list[str]:
        """Every piece of text drawn, in the order it was drawn (for tests)."""
        return list(self._texts)

    def _text(self, x: float, y: float, text: str, *, anchor: str = "w", bold: bool = False, muted: bool = False):
        t = self._theme
        self._texts.append(text)
        return self._canvas.create_text(x, y, text=text, anchor=anchor, font=self._bold if bold else self._font,
                                        fill=t.muted if muted else t.text)

    def show(self, rounds: Sequence[fd.CupRound], labels: Mapping[int, str], focus: int | None) -> None:
        canvas, t = self._canvas, self._theme
        self._shown = (rounds, labels, focus)
        same_cup = tuple(rounds) == self._rounds
        where = (canvas.xview()[0], canvas.yview()[0]) if same_cup else (0.0, 0.0)
        self._rounds = tuple(rounds)
        canvas.delete("all")
        self._texts = []
        canvas.configure(bg=t.table[0])
        self.configure(bg=t.table[0])
        earlier, tree = fd.bracket_split(rounds)
        px = self._px
        layout = layout_tree(tree, box=(px(self.BOX[0]), px(self.BOX[1])), gap=(px(self.GAP[0]), px(self.GAP[1])),
                             heading=px(28))
        margin = px(12)
        top = 0
        if not tree:
            self._text(margin, px(14), NO_TREE_NOTE, muted=True)
            top = px(30)
        for x, name in layout.headings:
            self._text(margin + x, top + px(14), name, anchor="center", bold=True)
        for link in layout.links:
            canvas.create_line(*[v + margin + (top if i % 2 else 0) for point in link for i, v in enumerate(point)],
                               fill=t.muted, width=1, tags="link")
        for box in layout.boxes:
            left, box_top = margin + box.x, top + margin + box.y
            mine = focus is not None and focus in (box.tie.team_a, box.tie.team_b)
            canvas.create_rectangle(left, box_top, left + box.width, box_top + box.height, fill=t.panel,
                                    outline=t.focus[0] if mine else t.field[1], width=2 if mine else 1)
            text = describe_tie(box.tie, labels)
            for row, (name, goals, side) in enumerate(((text.a_name, text.a_goals, "a"), (text.b_name, text.b_goals, "b"))):
                y = box_top + box.height * (0.28 + 0.44 * row)
                won = text.winner == side
                self._text(left + px(8), y, f"{name} *" if won and text.inferred else name, bold=won)
                self._text(left + box.width - px(8), y, goals, anchor="e", bold=won)
        bottom = top + margin + layout.height
        if any(describe_tie(box.tie, labels).inferred for box in layout.boxes):
            self._text(margin, bottom + px(14), INFERRED_NOTE, muted=True)
            bottom += px(30)
        width = margin * 2 + layout.width
        if earlier:
            bottom += px(10)
            self._text(margin, bottom + px(12), "Earlier rounds" if tree else "Rounds", bold=True)
            bottom += px(34)
            for cup_round in earlier:
                self._text(margin, bottom + px(10), cup_round.name, bold=True, muted=True)
                bottom += px(24)
                if not cup_round.knockout:
                    matches = sum(len(tie.fixtures) for tie in cup_round.ties)
                    self._text(margin + px(12), bottom + px(9),
                               f"Group or league phase: {matches} matches (listed in Results, not drawn as ties)",
                               muted=True)
                    bottom += px(28)
                    continue
                for tie in cup_round.ties:
                    text = describe_tie(tie, labels)
                    self._text(margin + px(240), bottom + px(9), f"{text.a_name} {text.a_goals}", anchor="e",
                               bold=text.winner == "a")
                    self._text(margin + px(250), bottom + px(9), f"{text.b_goals} {text.b_name}",
                               bold=text.winner == "b")
                    bottom += px(20)
                bottom += px(8)
            width = max(width, margin * 2 + px(500))
        canvas.configure(scrollregion=(0, 0, width, bottom + margin))
        canvas.xview_moveto(where[0])
        canvas.yview_moveto(where[1])
