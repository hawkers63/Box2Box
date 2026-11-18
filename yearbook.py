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
MAX_NAME_LENGTH = 24                    # a club name longer than this is printed as the game's short name, if it has one
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
class CupBlock:
    """One day of one cup or continental round (one leg of it, when it has two): the matches, with the aggregate
    on a second leg and, for a level tie, who advanced when the save shows it."""

    competition: str
    round_name: str
    leg: str                       # "1st leg", "2nd leg", "Replay" or ""
    date_text: str
    matches: tuple[BookMatch, ...]
    when: dt.date

    @property
    def heading(self) -> str:
        return f"{self.competition}, {self.round_name}{', ' + self.leg if self.leg else ''} · {self.date_text}"

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
    """The final table of each league whose every match is played: (competition, lines)."""

    tables: tuple[tuple[str, tuple[TableLine, ...]], ...]
    when: dt.date = dt.date.max


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


def _table(rows, rules: fd.ZoneRules | None = None) -> tuple[TableLine, ...]:
    """A table's lines; with the competition's rules, each line carries its zone."""
    return tuple(TableLine(r.position, r.team, r.played, r.won, r.drawn, r.lost, r.goals_for, r.goals_against,
                           r.goal_difference, r.points, r.form,
                           fd.zone_for_position(r.position, len(rows), rules) if rules is not None else "")
                 for r in rows)


def _league_pages(name: str, league: Sequence, labels: Mapping[int, str], tie_breaks: Sequence[int],
                  rules: fd.ZoneRules | None = None) -> list[LeaguePage]:
    """The matchweek pages of one league, and a block for each day a postponed match was played. Zones are shown
    from zones_from_matchweek on."""
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
    for ri in sorted(rounds):
        played = sorted((f for f in rounds[ri] if f.played and f.date),
                        key=lambda f: (f.date, f.kick_off_time or dt.time.min, labels.get(f.home_team_id, "")))
        on_time = [f for f in played if not rescheduled(f)]
        if on_time:
            first, last = on_time[0].date, max(f.date for f in on_time)
            table = fd.standings_as_of(league, labels, through=last, tie_breaks=tie_breaks)
            pages.append(LeaguePage(name, ri + 1, f"Matchweek {ri + 1} · {_span(first, last)}",
                                    tuple(line(f, first) for f in on_time),
                                    _table(table, rules if ri + 1 >= zones_from else None), first))
        for day in sorted({f.date for f in played if rescheduled(f)}):
            moved = [f for f in played if rescheduled(f) and f.date == day]
            pages.append(LeaguePage(name, ri + 1, f"Matchweek {ri + 1}, rescheduled · {_span(day, day)}",
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


def _cup_blocks(name: str, cup_fixtures: Sequence, labels: Mapping[int, str]) -> list[CupBlock]:
    """The blocks of a cup or continental competition: a block for each round, leg and day with a played match."""
    grouped: dict[tuple, list[BookMatch]] = {}
    names: dict[tuple, str] = {}
    matchdays = 0
    rounds_of: dict[frozenset, set[int]] = defaultdict(set)
    for f in cup_fixtures:
        rounds_of[frozenset((f.home_team_id, f.away_team_id))].add(f.round_index)
    for rnd in fd.cup_rounds(cup_fixtures, labels):
        # A group stage looks like knockout rounds to cup_rounds (a side plays once a round), but its pairs meet
        # again in another round; a knockout tie's legs and replay share one round.
        knockout = rnd.knockout and not any(len(rounds_of[frozenset((t.team_a, t.team_b))]) > 1 for t in rnd.ties)
        if not knockout:
            matchdays += 1
        round_name = rnd.name if knockout else f"Matchday {matchdays}"
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
    return [CupBlock(name, names[key], key[2], f"{_day(key[0])} {key[0]:%b}",
                     tuple(sorted(matches, key=lambda m: (m.home, m.away))), key[0])
            for key, matches in sorted(grouped.items())]


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


def build_yearbook(book: arch.Archive, season: int, names: Mapping[int, str]) -> Yearbook:
    """The Yearbook for one season, from everything the archive holds."""
    return yearbook_from(book.dataset(), book.competitions(), book.coverage(season), season, names)


def yearbook_from(dataset: fd.Dataset, competitions: Sequence[arch.ArchivedCompetition], coverage: arch.BookCoverage,
                  season: int, names: Mapping[int, str]) -> Yearbook:
    """The page model for one season. Only competitions the user has named are in the book, and (when the
    home nation is known) only those of that nation plus the continental ones. A title page opens it, the pages
    run by date, and the final tables close it once a league is fully played."""
    home = home_nation(competitions, names)
    pages: list = []
    order: dict[str, int] = {}
    finals: list[tuple[str, tuple[TableLine, ...]]] = []
    unplayed = False
    for comp in sorted(competitions, key=lambda c: c.key):
        name = names.get(comp.database_id)
        if not name or (home is not None and not comp.continental and comp.nation != home):
            continue
        fixtures = fd.season_fixtures(dataset, comp.key, season)
        labels = _display_names(fixtures)
        league = [f for f in fixtures if f.round is None and f.round_index is not None]
        cup = [f for f in fixtures if f.round is not None and f.round_index is not None]
        rules = dataset.zone_rules.get(comp.key)
        built = (_league_pages(name, league, labels, comp.tie_breaks, rules) if league else []) + \
            (_cup_blocks(name, cup, labels) if cup else [])
        if not built:
            continue
        order[name] = len(order)
        unplayed = unplayed or any(not f.played for f in league + cup)
        pages += built
        if league and all(f.played for f in league):
            last = max(f.date for f in league if f.date)
            finals.append((name, _table(fd.standings_as_of(league, labels, through=last, tie_breaks=comp.tie_breaks),
                                        rules)))
    pages.sort(key=lambda p: _page_key(p, order))
    label = fd.season_label(season, [f for fixtures in dataset.fixtures.values() for f in fixtures])
    coverage = dataclasses.replace(coverage, in_progress=unplayed)         # judged on the competitions in the book
    head = [TitlePage(label, _title_lines(coverage, list(order), home))]
    tail = [FinalTablesPage(tuple(finals))] if finals else []
    return Yearbook(label, coverage, tuple(head + pages + tail))
