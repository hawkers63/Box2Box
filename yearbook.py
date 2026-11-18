# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""The Yearbook's page model: one season, built from the archive, as a plain list of pages. No UI code and no
PDF: yearbook_pdf draws what this describes. See notes/design_v2.0_yearbook.md.

Honesty rules: a match with no recoverable score reads "n/a"; a match still to play is not a result and is left
out; a calculated table says it is calculated; nothing the save does not hold (extra time, penalties) is printed.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import archive as arch
import fm_data as fd

HOME_LEAGUE_NAME = "premier league"     # the competition whose nation is the book's home nation


@dataclass(frozen=True, slots=True)
class BookMatch:
    date_text: str
    home: str
    away: str
    score: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class TableLine:
    pos: int
    team: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    form: str


@dataclass(frozen=True, slots=True)
class LeaguePage:
    """One league matchweek (or the matches of it played late, `rescheduled`), with the table after it."""

    competition: str
    matchweek: int
    heading: str
    matches: tuple[BookMatch, ...]
    table: tuple[TableLine, ...]
    when: dt.date
    rescheduled: bool = False


@dataclass(frozen=True, slots=True)
class Yearbook:
    season_label: str
    coverage: arch.BookCoverage
    pages: tuple


def _day(d: dt.date) -> str:
    return f"{d:%a} {d.day}"


def _day_in(d: dt.date, month_of: dt.date) -> str:
    """A day as 'Sat 8', with its month added when it is not in the same month as `month_of`."""
    return _day(d) if (d.year, d.month) == (month_of.year, month_of.month) else f"{_day(d)} {d:%b}"


def _span(first: dt.date, last: dt.date) -> str:
    if first == last:
        return f"{_day(first)} {first:%b}"
    if (first.year, first.month) == (last.year, last.month):
        return f"{_day(first)} – {_day(last)} {last:%b}"
    return f"{_day(first)} {first:%b} – {_day(last)} {last:%b}"


def _score(f) -> str:
    return f"{f.home_goals}-{f.away_goals}" if fd.has_score(f) else "n/a"


def home_nation(competitions: Sequence[arch.ArchivedCompetition], names: Mapping[int, str]) -> int | None:
    """The book's home nation: the nation of the competition named "Premier League" in the user's names.
    None when no competition has that name (then every named league is included)."""
    for comp in competitions:
        name = names.get(comp.database_id)
        if name and name.strip().casefold() == HOME_LEAGUE_NAME:
            return comp.nation
    return None


def _table(rows) -> tuple[TableLine, ...]:
    return tuple(TableLine(r.position, r.team, r.played, r.won, r.drawn, r.lost, r.goals_for, r.goals_against,
                           r.goal_difference, r.points, r.form) for r in rows)


def _league_pages(name: str, league: Sequence, labels: Mapping[int, str], tie_breaks: Sequence[int]) -> list[LeaguePage]:
    """The matchweek pages of one league, and a block for each day a postponed match was played."""
    rounds: dict[int, list] = {}
    for f in league:
        rounds.setdefault(f.round_index, []).append(f)
    starts = {ri: min(f.date for f in group if f.date) for ri, group in rounds.items() if any(f.date for f in group)}

    def rescheduled(f) -> bool:
        later = [d for ri, d in starts.items() if ri > f.round_index]
        return bool(later) and f.date > min(later)

    def line(f, month_of: dt.date) -> BookMatch:
        return BookMatch(_day_in(f.date, month_of), labels.get(f.home_team_id, ""), labels.get(f.away_team_id, ""),
                         _score(f))

    pages: list[LeaguePage] = []
    for ri in sorted(rounds):
        played = sorted((f for f in rounds[ri] if f.played and f.date),
                        key=lambda f: (f.date, f.kick_off_time or dt.time.min, labels.get(f.home_team_id, "")))
        on_time = [f for f in played if not rescheduled(f)]
        if on_time:
            first, last = on_time[0].date, max(f.date for f in on_time)
            table = fd.standings_as_of(league, labels, through=last, tie_breaks=tie_breaks)
            pages.append(LeaguePage(name, ri + 1, f"Matchweek {ri + 1} · {_span(first, last)}",
                                    tuple(line(f, first) for f in on_time), _table(table), first))
        for day in sorted({f.date for f in played if rescheduled(f)}):
            moved = [f for f in played if rescheduled(f) and f.date == day]
            pages.append(LeaguePage(name, ri + 1, f"Matchweek {ri + 1}, rescheduled · {_span(day, day)}",
                                    tuple(line(f, day) for f in moved), (), day, rescheduled=True))
    return pages


def build_yearbook(book: arch.Archive, season: int, names: Mapping[int, str]) -> Yearbook:
    """The Yearbook for one season, from everything the archive holds."""
    return yearbook_from(book.dataset(), book.competitions(), book.coverage(season), season, names)


def yearbook_from(dataset: fd.Dataset, competitions: Sequence[arch.ArchivedCompetition], coverage: arch.BookCoverage,
                  season: int, names: Mapping[int, str]) -> Yearbook:
    """The page model for one season. Only competitions the user has named are in the book, and (when the
    home nation is known) only those of that nation; the continental ones are added by the cup blocks."""
    home = home_nation(competitions, names)
    pages: list = []
    order: dict[str, int] = {}
    for comp in sorted(competitions, key=lambda c: c.key):
        name = names.get(comp.database_id)
        if not name or comp.continental or (home is not None and comp.nation != home):
            continue
        fixtures = fd.season_fixtures(dataset, comp.key, season)
        league = [f for f in fixtures if f.round is None and f.round_index is not None]
        if not league:
            continue
        order[name] = len(order)
        pages += _league_pages(name, league, fd.team_labels(fixtures), comp.tie_breaks)
    pages.sort(key=lambda p: (p.when, order.get(p.competition, 0), p.matchweek, p.rescheduled))
    every = [f for fixtures in dataset.fixtures.values() for f in fixtures]
    return Yearbook(fd.season_label(season, every), coverage, tuple(pages))
