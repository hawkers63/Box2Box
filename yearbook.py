# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""The Yearbook's page model: one season, built from the archive, as a plain list of pages. No UI code and no
PDF: yearbook_pdf draws what this describes. See notes/design_v2.0_yearbook.md.

Honesty rules: a match with no recoverable score reads "n/a"; a match still to play is not a result and is left
out; a calculated table says it is calculated; nothing the save does not hold (extra time, penalties) is printed.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import archive as arch
import fm_data as fd

# What each zone is called under a table. The save's rules hold promotion, play-off and relegation places; the
# European places of a 20-team top division are estimated (see fm_data.zone_for_position).
ZONE_NAMES = {fd.ZONE_PROMOTION: "Promotion", fd.ZONE_UCL: "Champions League places (estimated)",
              fd.ZONE_EUROPA: "Europa League places (estimated)", fd.ZONE_PLAYOFF: "Play-offs",
              fd.ZONE_RELEGATION: "Relegation"}                 # from the top of a table down
LEAGUE_PHASE_SHOWN = 16                 # a league phase's table shows this many places (the top 16 of a 36-club table)
SAME_FIELD = 0.75                       # this share of a round's clubs playing the next round too: a league phase, not a knockout
MAX_NAME_LENGTH = 24                    # a club name longer than this is printed as the game's short name, if it has one
# Competitions that never appear in the book, even when named: the U18 Premier League and the U18 Professional
# Development League (database ids). Youth competitions are not part of the season the book records.
EXCLUDED_DATABASE_IDS = frozenset({95041306, 95041309})
HOME_LEAGUE_NAME = "premier league"     # the competition whose nation is the book's home nation
# The footnote for a "*": the save stores no shootout, extra-time or 90-minute score, so all that is known is that
# the match or the aggregate was level and one side still went through.
LEVEL_TIE_FOOTNOTE = "* went through a level tie, decided in extra time or on penalties"


@dataclass(frozen=True, slots=True)
class BookMatch:
    date_text: str
    home: str
    away: str
    score: str
    note: str = ""
    advanced: str = ""             # "home" or "away": the side that went through a level tie, marked with "*"


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
    zone: str = ""                 # promotion, play-off, relegation or a European place; "" for none
    movement: str = ""             # places since the previous printed table: "▲2", "▼1", "•", "–" or "in"; "" for none
    ppg: str = ""                  # points per scored match, "1.85"; "*" when a match with no score was left out
    marked: bool = False           # the club the reader asked to have marked
    xg_for: str = ""               # a final table only: expected goals for and against, "" where no report was kept
    xg_against: str = ""
    xg_over: str = ""              # goals scored minus xG, only when every match of every club has a report


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
    table_note: str = ""           # "Top 16 of 36 shown" when a league phase's table is cut


@dataclass(frozen=True, slots=True)
class CupBlock:
    """One day of one cup or continental round (one leg of it, when it has two): the matches, with the aggregate
    on a second leg and, for a level tie, who advanced when the save shows it."""

    competition: str
    round_name: str
    leg: str                       # "1st leg", "2nd leg", "Replay" or ""
    date_text: str
    matches: tuple[BookMatch, ...]
    when: dt.date
    table: tuple[TableLine, ...] = ()      # a league phase: the table after the last day of a matchday
    table_note: str = ""                   # "Top 16 of 36 shown" when the table is cut

    @property
    def heading(self) -> str:
        title = ", ".join(part for part in (self.competition, self.round_name, self.leg) if part)
        return f"{title} · {self.date_text}"

    @property
    def footnote(self) -> str:
        """What a "*" in this block means; empty when no side in it is marked."""
        return LEVEL_TIE_FOOTNOTE if any(m.advanced for m in self.matches) else ""


@dataclass(frozen=True, slots=True)
class TitlePage:
    season_label: str
    coverage_lines: tuple[str, ...]
    when: dt.date = dt.date.min


@dataclass(frozen=True, slots=True)
class FinalTablesPage:
    """The final table of each league whose every match is played: (competition, lines). `splits` holds, for the
    same leagues, (competition, overall, home, away): the home and away records in the overall table's order."""

    tables: tuple[tuple[str, tuple[TableLine, ...]], ...]
    when: dt.date = dt.date.max
    splits: tuple[tuple[str, tuple[TableLine, ...], tuple[TableLine, ...], tuple[TableLine, ...]], ...] = ()
    strips: tuple[tuple[str, tuple[str, ...]], ...] = ()      # (competition, the "From the results" lines)
    xg_notes: tuple[tuple[str, str], ...] = ()                # (competition, what the xG columns are and how far they reach)


@dataclass(frozen=True, slots=True)
class PlacesRow:
    """One club's place after each matchweek (None where it had not yet played), and its latest place."""

    team: str
    places: tuple[int | None, ...]
    zone: str = ""                 # the zone of the latest place
    marked: bool = False
    now: int = 0


@dataclass(frozen=True, slots=True)
class PlacesPage:
    """How they stood: for one league, every club's place after every matchweek, in the order of the latest table.
    Built from the weekly tables already in the book, never from a second sort."""

    competition: str
    matchweeks: tuple[int, ...]
    rows: tuple[PlacesRow, ...]
    when: dt.date = dt.date.max


@dataclass(frozen=True, slots=True)
class Move:
    """A club's climb or drop between two matchweeks."""

    team: str
    from_place: int
    from_week: int
    to_place: int
    to_week: int


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
        if comp.database_id not in EXCLUDED_DATABASE_IDS and name and name.strip().casefold() == HOME_LEAGUE_NAME:
            return comp.nation
    return None


def _display_names(fixtures: Sequence) -> dict[int, str]:
    """Each club's name as printed: the full name, or the game's short name when the full one is long (so it cannot
    run into the score) and a shorter one exists."""
    full, short = fd.team_labels(fixtures), fd.team_labels(fixtures, short=True)
    return {team: short[team] if len(name) > MAX_NAME_LENGTH and 0 < len(short.get(team, "")) < len(name) else name
            for team, name in full.items()}


def zones_from_matchweek(rounds: int) -> int:
    """The first matchweek whose table shows zones: the last 11 matches of a season of up to 38, the last 10 of a
    longer one (a 20-club league from match 27, a 24-club league from match 36). Earlier, a zone says little."""
    return rounds - (11 if rounds <= 38 else 10)


def zone_legend(table: Sequence[TableLine]) -> str:
    """The zones present in a table, named, as one line; empty when it shows none."""
    present = {t.zone for t in table if t.zone}
    return " · ".join(name for zone, name in ZONE_NAMES.items() if zone in present)


def _ppg(row, unscored: int) -> str:
    """Points per scored match (the rule of fd.TeamTotals.ppg_text): a match with no score is not counted, and
    a "*" says one was left out. Empty when the club has no scored match."""
    return f"{row.points / row.played:.2f}" + ("*" if unscored else "") if row.played else ""


def _movement(row, previous: Mapping[int, tuple[int, int]], shown: int | None) -> str:
    """How a club's place changed since the previous table: "–" when it had not played then, "in" when it came
    into a cut table from outside the cut."""
    before = previous.get(row.team_id)
    if before is None or before[1] == 0:
        return "–"
    place = before[0]
    if shown and place > shown >= row.position:
        return "in"
    return f"▲{place - row.position}" if place > row.position else f"▼{row.position - place}" if place < row.position else "•"


def table_note(lines: Sequence[TableLine]) -> str:
    """The small note under a table: it is calculated, and what any shading, movement or star means."""
    legend = zone_legend(lines)
    note = "Table calculated from the results." + (f" Shaded: {legend}." if legend else "")
    if any(t.movement for t in lines):
        note += " ± is the change in place since the previous table."
    if any(t.ppg.endswith("*") for t in lines):
        note += " * a match with no score is left out of PPG."
    return note


def final_note(lines: Sequence[TableLine], xg_note: str = "") -> str:
    """The note under a final table: how it was calculated, and what its expected-goals columns are."""
    return table_note(lines) + (f" {xg_note}" if xg_note else "")


def cut_table_note(cut: str, lines: Sequence[TableLine]) -> str:
    """A table's note with, in front, how a cut table was cut ("Top 16 of 36 shown")."""
    return (f"{cut}. " if cut else "") + table_note(lines)


def standings_head(lines: Sequence[TableLine]) -> tuple[str, ...]:
    """The columns of a weekly or final table; movement, PPG and expected goals only where a line carries them."""
    return (("±",) if any(t.movement for t in lines) else ()) +         ("#", "Team", "P", "W", "D", "L", "F", "A", "GD", "Pts") +         (("PPG",) if any(t.ppg for t in lines) else ()) +         (("xG", "xGA") if any(t.xg_for for t in lines) else ()) +         (("G-xG",) if any(t.xg_over for t in lines) else ()) + ("Last six",)


def standings_values(t: TableLine, lines: Sequence[TableLine]) -> tuple[str, ...]:
    """One line of a table as text, in the order of standings_head."""
    return (((t.movement,) if any(x.movement for x in lines) else ()) +
            (str(t.pos), t.team, str(t.played), str(t.won), str(t.drawn), str(t.lost), str(t.goals_for),
             str(t.goals_against), f"{t.goal_difference:+d}" if t.goal_difference else "0", str(t.points)) +
            ((t.ppg,) if any(x.ppg for x in lines) else ()) +
            ((t.xg_for, t.xg_against) if any(x.xg_for for x in lines) else ()) +
            ((t.xg_over,) if any(x.xg_over for x in lines) else ()) + (t.form,))


RECORD_HEAD = ("#", "Team", "P", "W", "D", "L", "F", "A", "Pts")
SPLITS_NOTE = "Home and away records are calculated from the results, in the order of the overall table."


def record_values(t: TableLine) -> tuple[str, ...]:
    return (str(t.pos), t.team, str(t.played), str(t.won), str(t.drawn), str(t.lost), str(t.goals_for),
            str(t.goals_against), str(t.points))


def places_note(page: PlacesPage) -> str:
    legend = " · ".join(name for zone, name in ZONE_NAMES.items() if any(r.zone == zone for r in page.rows))
    return ("Place after each matchweek, calculated from the results; a blank means the club had not yet played. "
            "Now is the latest place." + (f" Shaded: {legend}." if legend else ""))


def side_label(match: BookMatch, side: str) -> str:
    """A side's name as printed: with "*" after it when it went through a level tie."""
    return getattr(match, side) + ("*" if match.advanced == side else "")


def _table(rows, rules: fd.ZoneRules | None = None, previous: Mapping[int, tuple[int, int]] | None = None,
           unscored: Mapping[int, int] | None = None, marked: int | None = None,
           shown: int | None = None) -> tuple[TableLine, ...]:
    """A table's lines; with the competition's rules, each line carries its zone. With `previous` (club: place and
    played at the previous printed table; empty for the first) each carries its movement, and with `unscored`
    (club: matches played with no score) its points per game."""
    return tuple(TableLine(r.position, r.team, r.played, r.won, r.drawn, r.lost, r.goals_for, r.goals_against,
                           r.goal_difference, r.points, r.form,
                           fd.zone_for_position(r.position, len(rows), rules) if rules is not None else "",
                           _movement(r, previous, shown) if previous is not None else "",
                           _ppg(r, unscored.get(r.team_id, 0)) if unscored is not None else "",
                           marked is not None and r.team_id == marked)
                 for r in rows)


def with_expected_goals(lines: Sequence[TableLine], rows: Sequence, league: Sequence,
                        xg: Mapping[tuple, tuple[float, float]]) -> tuple[tuple[TableLine, ...], str]:
    """A final table's lines with expected goals for and against, and the note that explains them. Only matches that
    were played with a score and have a report count, so the totals sit beside the same goals as the table. A league
    with no report at all is returned unchanged with no note: no column of blanks, no 0.00. A club with some reports
    shows the total of those it has, and the note says how many matches that is of how many. Goals minus xG is added
    only when every match of every club has a report."""
    scored = [f for f in league if f.played and fd.has_score(f)]
    reported = [f for f in scored if fd.fixture_key(f) in xg]
    if not reported:
        return tuple(lines), ""
    totals: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0, 0, 0])      # xG for, xG against, covered, played
    for f in scored:
        figures = xg.get(fd.fixture_key(f))
        for team, mine, theirs in ((f.home_team_id, 0, 1), (f.away_team_id, 1, 0)):
            totals[team][3] += 1
            if figures is not None:
                totals[team][0] += figures[mine]
                totals[team][1] += figures[theirs]
                totals[team][2] += 1
    complete = all(t[2] == t[3] for t in totals.values())
    out = []
    for line, row in zip(lines, rows):
        for_, against, covered, _ = totals[row.team_id]
        if not covered:
            out.append(line)
            continue
        out.append(dataclasses.replace(line, xg_for=f"{for_:.2f}", xg_against=f"{against:.2f}",
                                       xg_over=f"{line.goals_for - for_:+.2f}" if complete else ""))
    note = "xG and xGA are expected goals for and against, from the match reports."
    if complete:
        note += " G-xG is goals scored minus xG."
    else:
        note += f" Expected goals for {len(reported)} of {len(scored)} played matches."
    return tuple(out), note


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def places_page(name: str, pages: Sequence[LeaguePage]) -> PlacesPage | None:
    """The places grid of one league from its weekly pages: None unless it has tables for two matchweeks or more.
    A club that had played nothing at a table is blank there."""
    weeks = sorted((p for p in pages if p.table and not p.rescheduled), key=lambda p: p.matchweek)
    if len(weeks) < 2:
        return None
    by_week = [{t.team: t.pos for t in p.table if t.played} for p in weeks]
    rows = tuple(PlacesRow(t.team, tuple(w.get(t.team) for w in by_week), t.zone, t.marked, t.pos)
                 for t in weeks[-1].table)
    return PlacesPage(name, tuple(p.matchweek for p in weeks), rows)


def biggest_moves(page: PlacesPage) -> tuple[tuple[Move, ...], tuple[Move, ...], int]:
    """(biggest rises, biggest falls, clubs left out) over the weeks. A rise is a climb from a lower place in one
    matchweek to a higher one in a later matchweek, a fall the reverse; the largest wins, then the shorter span.
    Every club level on both is returned, once each and by name, with its own earliest such move. A club with a
    blank week is left out, and counted."""
    best: dict[str, tuple[tuple[int, int], dict[str, Move]]] = {}
    left_out = 0
    for row in page.rows:
        if any(p is None for p in row.places):
            left_out += 1
            continue
        for i, a in enumerate(row.places):
            for j in range(i + 1, len(row.places)):
                b = row.places[j]
                for kind, gain in (("rise", a - b), ("fall", b - a)):
                    if gain <= 0:
                        continue
                    key = (-gain, j - i)
                    current = best.get(kind)
                    if current is None or key < current[0]:
                        current = best[kind] = (key, {})
                    if key == current[0] and row.team not in current[1]:
                        current[1][row.team] = Move(row.team, a, page.matchweeks[i], b, page.matchweeks[j])
    ordered = {kind: tuple(sorted(found[1].values(), key=lambda m: m.team)) if (found := best.get(kind)) else ()
               for kind in ("rise", "fall")}
    return ordered["rise"], ordered["fall"], left_out


def describe_moves(title: str, moves: Sequence[Move]) -> str:
    """One strip line for a biggest rise or fall, naming every club that shares it."""

    def one(move: Move) -> str:
        return (f"{move.team}, from {ordinal(move.from_place)} after matchweek {move.from_week} "
                f"to {ordinal(move.to_place)} after matchweek {move.to_week}")

    if len(moves) == 1:
        return f"{title}: {one(moves[0])}"
    return f"{title}, shared by {len(moves)} clubs: " + "; ".join(one(m) for m in moves)


def _names(teams: Sequence[str]) -> str:
    teams = sorted(teams)
    return teams[0] if len(teams) == 1 else ", ".join(teams[:-1]) + " and " + teams[-1]


def results_strip(overall: Sequence[TableLine], league: Sequence, rows: Sequence, labels: Mapping[int, str],
                  places: PlacesPage | None) -> tuple[str, ...]:
    """The "From the results" lines for a league whose every match is played: figures taken from the final table,
    the places grid and the scored results only. No player, manager or award: the save holds none."""
    lines: list[str] = []

    def leaders(title: str, values: Mapping[str, int], best, fmt="{}") -> None:
        if not values:
            return
        top = best(values.values())
        if top == 0 and best is max and title != "Best goal difference":
            return
        lines.append(f"{title}: {_names([t for t, v in values.items() if v == top])} ({fmt.format(top)})")

    leaders("Most wins", {t.team: t.won for t in overall}, max)
    leaders("Best goal difference", {t.team: t.goal_difference for t in overall}, max, "{:+d}")
    leaders("Fewest goals against", {t.team: t.goals_against for t in overall}, min)
    leaders("Most draws", {t.team: t.drawn for t in overall}, max)
    left_out = 0
    if places is not None:
        rise, fall, left_out = biggest_moves(places)
        for title, moves in (("Biggest rise", rise), ("Biggest fall", fall)):
            if moves:
                lines.append(describe_moves(title, moves))
    runs = {r.team: fd.streaks(fd.team_steps(league, r.team_id, labels)) for r in rows}
    leaders("Longest winning run", {t: s.longest[fd.STREAK_WINNING].length for t, s in runs.items()}, max)
    leaders("Longest unbeaten run", {t: s.longest[fd.STREAK_UNBEATEN].length for t, s in runs.items()}, max)
    if left_out:
        lines.append("Clubs that had not played in every matchweek are left out of the rise and the fall.")
    if any(f.played and not fd.has_score(f) for f in league):
        lines.append("A match with no score is not part of a run.")
    return tuple(lines)


def _unscored(fixtures: Sequence, through: dt.date) -> dict[int, int]:
    """Matches played by `through` that have no recoverable score, per club."""
    counts: dict[int, int] = defaultdict(int)
    for f in fixtures:
        if f.played and f.date and f.date <= through and not fd.has_score(f):
            counts[f.home_team_id] += 1
            counts[f.away_team_id] += 1
    return counts


def _split_lines(overall: Sequence[TableLine], rows: Sequence, order: Sequence) -> tuple[TableLine, ...]:
    """A home (or away) record for each club, in the overall table's order and with its overall place and zone."""
    by_team = {r.team_id: r for r in rows}
    lines = []
    for line, o in zip(overall, order):
        r = by_team[o.team_id]
        lines.append(dataclasses.replace(line, played=r.played, won=r.won, drawn=r.drawn, lost=r.lost,
                                         goals_for=r.goals_for, goals_against=r.goals_against,
                                         goal_difference=r.goal_difference, points=r.points, form="", movement="",
                                         ppg=""))
    return tuple(lines)


def _league_pages(name: str, league: Sequence, labels: Mapping[int, str], tie_breaks: Sequence[int],
                  rules: fd.ZoneRules | None = None, unit: str = "Matchweek",
                  shown: int | None = None, marked: int | None = None) -> list[LeaguePage]:
    """The matchweek pages of one league, and a block for each day a postponed match was played. Zones are shown
    from zones_from_matchweek on. `unit` is "Matchday" for a continental league phase, whose table is cut to
    the top `shown` places."""
    rounds: dict[int, list] = {}
    for f in league:
        rounds.setdefault(f.round_index, []).append(f)
    starts = {ri: min(f.date for f in group if f.date) for ri, group in rounds.items() if any(f.date for f in group)}
    # The season's length is what most clubs play: the fixture list can hold extra rounds (play-offs) beyond it.
    played_by: dict[int, int] = defaultdict(int)
    for f in league:
        played_by[f.home_team_id] += 1
        played_by[f.away_team_id] += 1
    zones_from = zones_from_matchweek(statistics.median_low(played_by.values()) if played_by else 0)

    def rescheduled(f) -> bool:
        later = [d for ri, d in starts.items() if ri > f.round_index]
        return bool(later) and f.date > min(later)

    def line(f, month_of: dt.date) -> BookMatch:
        return BookMatch(_day_in(f.date, month_of), labels.get(f.home_team_id, ""), labels.get(f.away_team_id, ""),
                         _score(f))

    pages: list[LeaguePage] = []
    previous: dict[int, tuple[int, int]] = {}            # place and games played at the previous printed table
    for ri in sorted(rounds):
        played = sorted((f for f in rounds[ri] if f.played and f.date),
                        key=lambda f: (f.date, f.kick_off_time or dt.time.min, labels.get(f.home_team_id, "")))
        on_time = [f for f in played if not rescheduled(f)]
        if on_time:
            first, last = on_time[0].date, max(f.date for f in on_time)
            table = fd.standings_as_of(league, labels, through=last, tie_breaks=tie_breaks)
            lines = _table(table, rules if ri + 1 >= zones_from else None, previous, _unscored(league, last), marked,
                           shown)
            previous = {r.team_id: (r.position, r.played) for r in table}
            cut = lines[:shown] if shown else lines
            pages.append(LeaguePage(name, ri + 1, f"{unit} {ri + 1} · {_span(first, last)}",
                                    tuple(line(f, first) for f in on_time), cut, first,
                                    table_note=f"Top {len(cut)} of {len(lines)} shown" if len(cut) < len(lines) else ""))
        for day in sorted({f.date for f in played if rescheduled(f)}):
            moved = [f for f in played if rescheduled(f) and f.date == day]
            pages.append(LeaguePage(name, ri + 1, f"{unit} {ri + 1}, rescheduled · {_span(day, day)}",
                                    tuple(line(f, day) for f in moved), (), day, rescheduled=True))
    return pages


def _tie_note(tie: fd.CupTie, two_legged: bool) -> tuple[str, str]:
    """(note, advanced) for a tie's deciding match. The note is the aggregate for two legs, or "(level)" for a
    level tie nobody is known to have won. `advanced` is "home" or "away" for the side that went through a level
    tie, only when `tie.winner` is evidenced (the side plays in a later round). The save stores no extra time or
    penalties, so neither is ever printed."""
    last = tie.fixtures[-1]
    went_through = tie.winner is not None and tie.how == "next round"
    side = ("home" if tie.winner == last.home_team_id else "away") if went_through else ""
    if two_legged:
        goals = fd.Tie(tie.round_index, tie.team_a, tie.team_b, tie.fixtures[0], last).aggregate
        if goals is None:
            return "", ""
        home, away = goals[1], goals[0]                           # the second leg's home side first
        if home != away:
            return f"({home}-{away} agg)", ""
        return (f"({home}-{away} agg)", side) if side else (f"({home}-{away} agg, level)", "")
    if fd.has_score(last) and last.home_goals == last.away_goals:
        return ("", side) if side else ("(level)", "")
    return "", ""


def _one_pool(fixtures: Sequence) -> bool:
    """Whether every club in these fixtures is linked to every other through the matches played (one league
    table), as opposed to separate groups."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for f in fixtures:
        parent[find(f.home_team_id)] = find(f.away_team_id)
    return len({find(t) for t in list(parent)}) == 1


ROUND_GAP_DAYS = 3       # matches more than this many days apart, with no pair in common, are different rounds


def _separate_rounds(fixtures: Sequence) -> list:
    """Some competitions (the qualifying rounds of the European cups) reuse a round index for several separate
    rounds. Split such an index into rounds by date: fixtures more than ROUND_GAP_DAYS apart belong to different
    rounds unless a pair meets in both (two legs, however far apart). Legs and consecutive rounds are both a week apart,
    so only a pair tells them apart. Rounds are then renumbered in date order.
    Fixtures are returned unchanged when no round index holds more than one round."""
    by_index: dict[int, list[int]] = defaultdict(list)
    for position, f in enumerate(fixtures):
        by_index[f.round_index].append(position)
    clusters: list[tuple[dt.date, int, list[int]]] = []
    for index, positions in by_index.items():
        positions.sort(key=lambda i: fixtures[i].date or dt.date.min)
        parent = {i: i for i in positions}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        seen: dict[frozenset, int] = {}
        previous = None
        for i in positions:
            f = fixtures[i]
            pair = frozenset((f.home_team_id, f.away_team_id))
            if previous is not None and (f.date is None or fixtures[previous].date is None
                                         or (f.date - fixtures[previous].date).days <= ROUND_GAP_DAYS):
                parent[find(i)] = find(previous)
            if pair in seen:
                parent[find(i)] = find(seen[pair])
            seen[pair], previous = i, i
        groups: dict[int, list[int]] = defaultdict(list)
        for i in positions:
            groups[find(i)].append(i)
        for members in groups.values():
            clusters.append((min(fixtures[i].date or dt.date.min for i in members), index, members))
    if len(clusters) == len(by_index):
        return list(fixtures)
    renumbered = list(fixtures)
    for number, (_, _, members) in enumerate(sorted(clusters, key=lambda c: (c[0], c[1]))):
        for i in members:
            renumbered[i] = dataclasses.replace(fixtures[i], round_index=number)
    return renumbered


def _field_runs(fixtures: Sequence) -> list[list[int]]:
    """Runs of consecutive round indexes whose rounds are played by nearly the same clubs (at least SAME_FIELD of
    the larger field). A knockout halves its field each round, so a run is two legs of one round (length 2) or a
    league phase or group stage (length 3 or more)."""
    field: dict[int, set[int]] = defaultdict(set)
    for f in fixtures:
        field[f.round_index].update((f.home_team_id, f.away_team_id))
    order = sorted(field)
    runs: list[list[int]] = [[order[0]]] if order else []
    for before, after in zip(order, order[1:]):
        same = len(field[before] & field[after]) / max(len(field[before]), len(field[after])) >= SAME_FIELD
        if same:
            runs[-1].append(after)
        else:
            runs.append([after])
    return runs


def _with_legs_together(fixtures: Sequence, runs: list[list[int]]) -> list:
    """Some two-legged ties store their second leg in the next round index. For a run of exactly two rounds, bring
    each pair's second-round meeting into the first round so the pair reads as one tie of two legs."""
    moves: dict[tuple[int, frozenset], int] = {}
    for run in runs:
        if len(run) == 2:
            first = {frozenset((f.home_team_id, f.away_team_id)) for f in fixtures if f.round_index == run[0]}
            for f in fixtures:
                pair = frozenset((f.home_team_id, f.away_team_id))
                if f.round_index == run[1] and pair in first:
                    moves[(run[1], pair)] = run[0]
    return [dataclasses.replace(f, round_index=moves[(f.round_index, frozenset((f.home_team_id, f.away_team_id)))])
            if (f.round_index, frozenset((f.home_team_id, f.away_team_id))) in moves else f for f in fixtures]


def _cup_blocks(name: str, cup_fixtures: Sequence, labels: Mapping[int, str],
                tie_breaks: Sequence[int] = (), one_match: bool = False) -> list[CupBlock]:
    """The blocks of a cup or continental competition: a block for each round, leg and day with a played match.
    A league phase (one pool of clubs playing matchday after matchday) also gets its table, cut to the top places,
    after the last day of each matchday."""
    grouped: dict[tuple, list[BookMatch]] = {}
    names: dict[tuple, str] = {}
    matchdays = 0
    league_phase: set[int] = set()
    league_fixtures: list = []
    cup_fixtures = _separate_rounds(cup_fixtures)
    runs = _field_runs(cup_fixtures)
    league_rounds = {index for run in runs if len(run) >= 3 for index in run}      # a league phase or group stage
    cup_fixtures = _with_legs_together(cup_fixtures, runs)
    for rnd in fd.cup_rounds(cup_fixtures, labels):
        # A group stage looks like knockout rounds to cup_rounds (a side plays once a round); the same clubs playing
        # three or more rounds running tells it apart.
        knockout = rnd.knockout and rnd.index not in league_rounds
        if not knockout:
            matchdays += 1
            league_phase.add(rnd.index)
            league_fixtures += [f for t in rnd.ties for f in t.fixtures]
        round_name = rnd.name if knockout else f"Matchday {matchdays}"
        if one_match:
            round_name = ""                       # a competition that is a single match: its name says it all
        for tie in rnd.ties:
            legs = tie.fixtures
            two_legged = knockout and len(legs) == 2 and not fd.is_replay(*legs)
            for n, f in enumerate(legs):
                if not f.played or not f.date:
                    continue
                leg = ""
                if knockout and len(legs) == 2:
                    leg = ("1st leg", "2nd leg")[n] if two_legged else ("Replay" if n == 1 else "")
                deciding = knockout and n == len(legs) - 1
                note, advanced = _tie_note(tie, two_legged) if deciding else ("", "")
                key = (f.date, rnd.index, leg)
                names[key] = round_name
                grouped.setdefault(key, []).append(
                    BookMatch("", labels.get(f.home_team_id, ""), labels.get(f.away_team_id, ""), _score(f), note,
                              advanced))
    last_day = {key[1]: max(k[0] for k in grouped if k[1] == key[1]) for key in grouped if key[1] in league_phase}
    pooled = bool(league_fixtures) and _one_pool(league_fixtures)
    blocks = []
    for key, matches in sorted(grouped.items()):
        table, note = (), ""
        if pooled and key[1] in league_phase and key[0] == last_day[key[1]]:
            rows = fd.standings_as_of(league_fixtures, labels, through=key[0], tie_breaks=tie_breaks)
            table = _table(rows[:LEAGUE_PHASE_SHOWN])
            note = f"Top {len(table)} of {len(rows)} shown" if len(rows) > len(table) else ""
        blocks.append(CupBlock(name, names[key], key[2], f"{_day(key[0])} {key[0]:%b}",
                               tuple(sorted(matches, key=lambda m: (m.home, m.away))), key[0], table, note))
    return blocks


def _title_lines(coverage: arch.BookCoverage, included: Sequence[str], home: int | None) -> tuple[str, ...]:
    lines = []
    if coverage.saves:
        first = f"{coverage.first_date.day} {coverage.first_date:%B %Y}"
        last = f"{coverage.last_date.day} {coverage.last_date:%B %Y}"
        lines.append(f"Built from {coverage.saves} banked save{'s' if coverage.saves != 1 else ''}, in-game "
                     f"{first if first == last else f'{first} to {last}'}.")
    else:
        lines.append("No banked save falls inside this season's dates.")
    for first, last in coverage.gaps:
        lines.append(f"No save was banked between {first.day} {first:%b} and {last.day} {last:%b}, so anything the "
                     "game dropped in that stretch is missing.")
    lines.append("Season in progress." if coverage.in_progress else "Season complete.")
    lines.append("Competitions: " + (", ".join(included) if included else "none named") + ".")
    if home is None:
        lines.append("No competition is named Premier League, so every named league is included.")
    lines.append("Only competitions you have named appear; use Name this competition to add one. Tables are "
                 "calculated from the results.")
    return tuple(lines)


def _page_key(page, order: Mapping[str, int]) -> tuple:
    """Pages run by date; on one day a competition's matchweek or round follows the competition order."""
    if isinstance(page, LeaguePage):
        return (page.when, order.get(page.competition, 0), page.matchweek * 2 + page.rescheduled, "")
    if isinstance(page, CupBlock):
        return (page.when, order.get(page.competition, 0), 10 ** 6, page.round_name + page.leg)
    return (page.when, 0, 0, "")


def build_yearbook(book: arch.Archive, season: int, names: Mapping[int, str], marked_club: int | None = None) -> Yearbook:
    """The Yearbook for one season, from everything the archive holds. `marked_club` is a club uid to mark."""
    return yearbook_from(book.dataset(), book.competitions(), book.coverage(season), season, names, marked_club,
                         book.expected_goals())


def yearbook_from(dataset: fd.Dataset, competitions: Sequence[arch.ArchivedCompetition], coverage: arch.BookCoverage,
                  season: int, names: Mapping[int, str], marked_club: int | None = None,
                  expected_goals: Mapping[tuple, tuple[float, float]] | None = None) -> Yearbook:
    """The page model for one season. Only competitions the user has named are in the book, and (when the
    home nation is known) only those of that nation plus the continental ones. A title page opens it, the pages
    run by date, and the final tables close it once a league is fully played."""
    home = home_nation(competitions, names)
    pages: list = []
    order: dict[str, int] = {}
    included: list[str] = []
    finals: list[tuple[str, tuple[TableLine, ...]]] = []
    splits: list[tuple] = []
    strips: list[tuple[str, tuple[str, ...]]] = []
    xg_notes: list[tuple[str, str]] = []
    grids: list[PlacesPage] = []
    unplayed = False
    for comp in sorted(competitions, key=lambda c: c.key):
        name = names.get(comp.database_id)
        if not name or comp.database_id in EXCLUDED_DATABASE_IDS or (home is not None and not comp.continental and comp.nation != home):
            continue
        fixtures = fd.season_fixtures(dataset, comp.key, season)
        labels = _display_names(fixtures)
        league = [f for f in fixtures if f.round is None and f.round_index is not None]
        cup = [f for f in fixtures if f.round is not None and f.round_index is not None]
        one_match = False
        if len(league) == 1:                                  # a one-match competition (the Community Shield)
            cup, league, one_match = league, [], True
        rules = dataset.zone_rules.get(comp.key)
        # Cup rounds inside a league are its play-offs.
        cup_name = f"{name} play-offs" if league and cup and not comp.continental else name
        built = (_league_pages(name, league, labels, comp.tie_breaks, rules, "Matchday" if comp.continental else "Matchweek",
                       LEAGUE_PHASE_SHOWN if comp.continental else None, marked_club) if league else []) + \
            (_cup_blocks(cup_name, cup, labels, comp.tie_breaks, one_match) if cup else [])
        if not built:
            continue
        order[name] = order[cup_name] = len(included)                           # a play-offs block sorts with its league
        included.append(name)
        unplayed = unplayed or any(not f.played for f in league + cup)
        pages += built
        grid = None if comp.continental or not league else places_page(name, [p for p in built if isinstance(p, LeaguePage)])
        if grid:
            grids.append(grid)
        if league and all(f.played for f in league):
            last = max(f.date for f in league if f.date)
            rows = fd.standings_as_of(league, labels, through=last, tie_breaks=comp.tie_breaks)
            overall = _table(rows, rules, unscored=_unscored(league, last), marked=marked_club)
            overall, xg_note = with_expected_goals(overall, rows, league, expected_goals or {})
            if xg_note:
                xg_notes.append((name, xg_note))
            finals.append((name, overall))
            splits.append((name, overall,
                           _split_lines(overall, fd.calculate_standings(league, labels, home_only=True), rows),
                           _split_lines(overall, fd.calculate_standings(league, labels, away_only=True), rows)))
            strips.append((name, results_strip(overall, league, rows, labels, grid)))
    pages.sort(key=lambda p: _page_key(p, order))
    label = fd.season_label(season, [f for fixtures in dataset.fixtures.values() for f in fixtures])
    coverage = dataclasses.replace(coverage, in_progress=unplayed)         # judged on the competitions in the book
    head = [TitlePage(label, _title_lines(coverage, included, home))]
    tail = grids + ([FinalTablesPage(tuple(finals), splits=tuple(splits), strips=tuple(strips),
                                                    xg_notes=tuple(xg_notes))] if finals else [])
    return Yearbook(label, coverage, tuple(head + pages + tail))
