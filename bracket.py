"""The cup bracket: where each tie's box goes in the tree (pure geometry), and the canvas that draws it.

The layout has no Tk in it, so it is tested on its own. A tie sits between the two ties that fed it: the last
round's ties are placed first and each earlier round follows from them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import fm_data as fd


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
