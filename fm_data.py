# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Data layer for Box2Box.

Reads a Football Manager 26/27 save with fmsave and derives everything the viewer shows: the
competition list, seasons, a chronological results list, the fixture grid, league tables, their
promotion and relegation zones, and coverage counts. There is no UI code here, so it can run on a
worker thread and be tested without a window (see test_fm_data.py).

The raw fmsave records are kept unchanged and every display value is derived from them.
Nothing in this module writes to a save.
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import time
import warnings
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import fmsave
from fmsave import CompetitionRound, Fixture, LeagueTable

WIN_POINTS = 3
DRAW_POINTS = 1
FORM_LENGTH = 5
MAX_GRID_TEAMS = 60

GROUP_BY_WEEK = "Week"
GROUP_BY_MATCHDAY = "Matchday"
GROUP_BY_DATE = "Date"

# Result kinds, used to colour scores. A "scheduled" match has not been played yet; an
# "unavailable" one was played but fmsave recovered no unambiguous score for it.
HOME_WIN, DRAW, AWAY_WIN = "home_win", "draw", "away_win"
SCHEDULED, UNAVAILABLE, MIXED = "scheduled", "unavailable", "mixed"

# Standings split views
SPLIT_OVERALL = "Overall"
SPLIT_HOME = "Home"
SPLIT_AWAY = "Away"
SPLIT_FORM = "Form"
SPLITS = (SPLIT_OVERALL, SPLIT_HOME, SPLIT_AWAY, SPLIT_FORM)

# League qualification and relegation zones
ZONE_UCL = "ucl"
ZONE_PROMOTION = "promotion"
ZONE_PLAYOFF = "playoff"
ZONE_EUROPA = "europa"
ZONE_RELEGATION = "relegation"
ZONE_NONE = ""

# Tying a rules block the save stores without a competition to one by its calendar (see
# link_zone_rules). Shorter calendars fit too many competitions by chance.
RULES_MIN_DATED_ROUNDS = 10
RULES_MIN_DATE_SHARE = 0.9
RULES_TIE_MARGIN = 0.02
UNNUMBERED_ROUND = 256  # what fmsave reports for a round the save does not number

# Competition categories for the Competitions Viewer
COMP_CAT_YOURS = "Your Club"
COMP_CAT_LEAGUE = "League"
COMP_CAT_CUP = "Cup"
COMP_CAT_YOUTH = "Youth / Reserves"
COMP_CAT_FRIENDLY = "Friendlies"
COMP_CAT_OTHER = "Other"

ROUND_NAMES = {
    CompetitionRound.THIRD_ROUND: "Third round",
    CompetitionRound.FOURTH_ROUND: "Fourth round",
    CompetitionRound.QUARTER_FINAL: "Quarter-final",
    CompetitionRound.SEMI_FINAL: "Semi-final",
    CompetitionRound.FINAL: "Final",
}


class ImportFailed(Exception):
    """A save could not be read. The message is written for the person using the app."""


# --------------------------------------------------------------------------- records


@dataclass(frozen=True, slots=True)
class ImportInfo:
    """Where a dataset came from and how far it can be trusted."""

    path: str
    file_name: str
    game: str
    build: str
    known_build: bool
    game_date: dt.date | None
    fmsave_version: str
    imported_at: dt.datetime
    seconds: float
    warnings: tuple[str, ...]
    managed_club_uid: int | None
    managed_club_name: str | None


@dataclass(frozen=True, slots=True)
class CompetitionInfo:
    """Summary of one competition that holds fixtures in the save."""

    id: int
    database_id: int | None
    fixture_count: int
    played_count: int
    seasons: tuple[int, ...]
    team_count: int
    top_clubs: tuple[str, ...]
    search_text: str
    managed_fixtures: int
    managed_first_team: bool
    prominence: int

    @property
    def is_yours(self) -> bool:
        return self.managed_fixtures > 0


@dataclass(frozen=True, slots=True)
class ZoneRules:
    """A league's promotion, play-off and relegation places, from the save's own rules.

    Positions 1 to `promotion` go up (or straight through, in a group stage), the next `playoff`
    go into the play-offs and the last `relegation` go down. fmsave reads these from the game's
    rules database and counts them unconfirmed.
    """

    promotion: int
    playoff: int
    relegation: int
    matched_by_calendar: bool = False

    @property
    def total(self) -> int:
        return self.promotion + self.playoff + self.relegation

    @property
    def top_flight(self) -> bool:
        """Nobody goes up and somebody goes down: a top division."""
        return self.promotion == 0 and self.playoff == 0 and self.relegation > 0

    def describe(self) -> str:
        parts = [text for count, text in (
            (self.promotion, f"{self.promotion} promoted"),
            (self.playoff, f"{self.playoff} in the play-offs"),
            (self.relegation, f"{self.relegation} relegated"),
        ) if count]
        return ", ".join(parts) or "no promotion, play-offs or relegation"


@dataclass(frozen=True, slots=True)
class Dataset:
    """Everything read from one save, ready for the views. Built whole, never changed."""

    info: ImportInfo
    competitions: tuple[CompetitionInfo, ...]
    by_id: Mapping[int, CompetitionInfo]
    fixtures: Mapping[int, tuple[Fixture, ...]]
    stored_tables: Mapping[int, tuple[LeagueTable, ...]]
    managed_team_ids: frozenset[int]
    first_team_id: int | None
    fixture_total: int
    fixtures_without_competition: int
    zone_rules: Mapping[int, ZoneRules] = field(default_factory=dict)

    def fixtures_for(self, competition_id: int) -> tuple[Fixture, ...]:
        return self.fixtures.get(competition_id, ())


@dataclass(frozen=True, slots=True)
class Coverage:
    """How many fixtures a selection holds and how many of them have usable results."""

    fixtures: int
    played: int
    scored: int

    @property
    def unavailable(self) -> int:
        return self.played - self.scored

    @property
    def to_play(self) -> int:
        return self.fixtures - self.played

    def describe(self) -> str:
        parts = [_plural(self.fixtures, "fixture"), f"{self.played} played"]
        if self.unavailable:
            parts.append(f"{self.unavailable} played with no recoverable score")
        parts.append(f"{self.to_play} to play")
        return " · ".join(parts)


@dataclass(frozen=True, slots=True)
class TimelineRow:
    """One line of the results list: a group heading, or one match."""

    heading: str = ""
    date: str = ""
    time: str = ""
    home: str = ""
    score: str = ""
    away: str = ""
    round: str = ""
    kind: str = ""
    result: str = ""
    points: str = ""
    home_id: int | None = None
    away_id: int | None = None
    fixture: Fixture | None = None

    @property
    def is_heading(self) -> bool:
        return bool(self.heading)


@dataclass(frozen=True, slots=True)
class GridCell:
    text: str
    kind: str
    fixtures: tuple[Fixture, ...] = ()


@dataclass(frozen=True, slots=True)
class Grid:
    """Home teams down the side, away teams across the top, every meeting in its cell."""

    team_ids: tuple[int, ...]
    row_labels: tuple[str, ...]
    column_labels: tuple[str, ...]
    cells: tuple[tuple[GridCell, ...], ...]


@dataclass(frozen=True, slots=True)
class StandingRow:
    position: int
    team_id: int
    team: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    points: int
    form: str
    zone: str = ""

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


@dataclass(frozen=True, slots=True)
class Standings:
    stored: bool
    note: str
    groups: tuple[tuple[str, tuple[StandingRow, ...]], ...]
    zones_note: str = ""


@dataclass(frozen=True, slots=True)
class CompetitionSummaryRow:
    id: int
    database_id: int | None
    name: str
    category: str
    teams: int
    fixtures: int
    played: int
    scored: int
    progress: str
    seasons: int
    example_clubs: str


# --------------------------------------------------------------------------- loading


def load_dataset(
    path: str | os.PathLike[str], progress: Callable[[str], None] = lambda _message: None
) -> Dataset:
    """Read a save with fmsave and build a Dataset. The save is only read, never written.

    Raises:
        ImportFailed: The save cannot be read, with a message for the user.
    """
    started = time.perf_counter()
    path = Path(path)
    notes: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            progress("Opening the save")
            with fmsave.open(path) as save:
                save_info = save.info
                progress("Reading clubs")
                managed = _optional(notes, "Managed club", save.managed_clubs)
                clubs = _optional(notes, "Clubs", save.clubs)
                progress("Reading competitions")
                competitions = _optional(notes, "Competitions", save.competitions)
                progress("Reading fixtures and results")
                fixtures = list(save.fixtures())
                progress("Reading league tables")
                tables = _optional(notes, "League tables", save.league_tables)
                progress("Reading competition rules")
                rules = _optional(notes, "Competition rules", save.competition_rules)
        except FileNotFoundError as exc:
            raise ImportFailed(f"File not found: {path.name}") from exc
        except fmsave.NotAFmSaveError as exc:
            raise ImportFailed(f"{path.name} is not a Football Manager save.") from exc
        except fmsave.UnsupportedGameError as exc:
            raise ImportFailed(f"fmsave cannot read this save: {exc}") from exc
        except fmsave.SaveChangedError as exc:
            raise ImportFailed(
                "The save changed while it was being read. If Football Manager is saving, "
                "wait for it to finish and try again."
            ) from exc
        except fmsave.CorruptSaveError as exc:
            raise ImportFailed(
                "The save looks damaged or was still being written. Try again once the game "
                "has finished saving."
            ) from exc
        except fmsave.FmsaveError as exc:
            raise ImportFailed(f"fmsave could not read this save ({type(exc).__name__}): {exc}") from exc
        except OSError as exc:
            raise ImportFailed(f"Could not read {path.name}: {exc.strerror or exc}") from exc

    progress("Organising fixtures")
    reader_warnings = list(dict.fromkeys(f"{w.category.__name__}: {w.message}" for w in caught))
    info = ImportInfo(
        path=str(path),
        file_name=path.name,
        game=save_info.game,
        build=save_info.build,
        known_build=save_info.known_build,
        game_date=save_info.game_date,
        fmsave_version=fmsave.__version__,
        imported_at=dt.datetime.now(),
        seconds=time.perf_counter() - started,
        warnings=tuple(reader_warnings + notes),
        managed_club_uid=managed[0].club_uid if managed else None,
        managed_club_name=managed[0].club_name if managed else None,
    )
    return build_dataset(info, fixtures, clubs=clubs, competitions=competitions, tables=tables, rules=rules)


def _optional(notes: list[str], label: str, reader: Callable[[], Iterable]) -> list:
    """Run a reader the views can do without, noting a failure instead of stopping."""
    try:
        return list(reader())
    except Exception as exc:  # each reader can fail on its own on an unverified build
        notes.append(f"{label} could not be read ({type(exc).__name__}: {exc})")
        return []


def build_dataset(
    info: ImportInfo,
    fixtures: Iterable[Fixture],
    *,
    clubs: Iterable = (),
    competitions: Iterable = (),
    tables: Iterable[LeagueTable] = (),
    rules: Iterable = (),
) -> Dataset:
    """Organise fmsave records into a Dataset. Pure: no file access."""
    fixtures = list(fixtures)
    reputation: dict[int, int] = {}
    managed_teams: set[int] = set()
    first_team_id: int | None = None
    for club in clubs:
        if club.reputation is not None:
            reputation[club.uid] = club.reputation
        if club.uid == info.managed_club_uid:
            own = [team for team in club.teams if not team.is_affiliate]
            managed_teams = {team.team_id for team in own}
            if own:
                first_team_id = min(own, key=lambda team: team.slot).team_id
    if info.managed_club_uid is not None and not managed_teams:
        # No club table: fall back to the teams the fixtures say the club fields.
        for f in fixtures:
            for team_id, club_uid, slot in (
                (f.home_team_id, f.home_club_uid, f.home_team_slot),
                (f.away_team_id, f.away_club_uid, f.away_team_slot),
            ):
                if club_uid == info.managed_club_uid:
                    managed_teams.add(team_id)
                    if slot == 0:
                        first_team_id = team_id

    by_competition: dict[int, list[Fixture]] = defaultdict(list)
    without_competition = 0
    for f in fixtures:
        if f.competition_id is None:
            without_competition += 1
        else:
            by_competition[f.competition_id].append(f)
    ordered = {cid: tuple(sorted(items, key=_when)) for cid, items in by_competition.items()}

    database_ids = {c.id: c.database_id for c in competitions}
    infos = [
        _competition_info(cid, items, database_ids.get(cid), reputation, managed_teams, first_team_id)
        for cid, items in ordered.items()
    ]
    infos.sort(key=_competition_order)

    stored: dict[int, list[LeagueTable]] = defaultdict(list)
    for table in tables:
        if table.competition_id is not None:
            stored[table.competition_id].append(table)

    return Dataset(
        info=info,
        competitions=tuple(infos),
        by_id={c.id: c for c in infos},
        fixtures=ordered,
        stored_tables={cid: tuple(items) for cid, items in stored.items()},
        managed_team_ids=frozenset(managed_teams),
        first_team_id=first_team_id,
        fixture_total=len(fixtures),
        fixtures_without_competition=without_competition,
        zone_rules=link_zone_rules(rules, ordered),
    )


def link_zone_rules(rules: Iterable, fixtures: Mapping[int, Sequence[Fixture]]) -> dict[int, ZoneRules]:
    """Promotion, play-off and relegation places per competition, from the save's rules blocks.

    fmsave links a block to the competition whose league table the save stores right after it.
    Before a season starts the game has stored no table yet, so a block fmsave leaves unlinked is
    matched by its calendar instead: its rounds must fall on the days the competition's matchdays
    are played, round for round. Two divisions can share a calendar, so a block that fits several
    competitions equally well counts for each of them, and a competition is only given rules when
    every block that fits it agrees. Otherwise its zones are estimated from its size.
    """
    linked: dict[int, set[tuple[int, int, int]]] = defaultdict(set)
    unlinked = []
    for block in rules:
        places = (block.promotion_places, block.playoff_places, block.relegation_places)
        if any(value is None or value < 0 for value in places):
            continue
        if block.competition_id is not None:
            linked[block.competition_id].add(places)
        else:
            unlinked.append((block, places))

    calendars: dict[int, list[tuple[int, dict[int, dt.date]]]] = defaultdict(list)
    for competition_id, items in fixtures.items():
        if competition_id not in linked:
            for days in _matchday_calendars(items):
                calendars[len(days)].append((competition_id, days))

    fitted: dict[int, set[tuple[int, int, int]]] = defaultdict(set)
    for block, places in unlinked:
        rounds = [(r.number if r.number < UNNUMBERED_ROUND else index + 1, r.date)
                  for index, r in enumerate(block.rounds) if r.date is not None]
        if len(rounds) < RULES_MIN_DATED_ROUNDS:
            continue
        shares = []
        for competition_id, days in calendars.get(len(block.rounds), ()):
            share = sum(1 for number, day in rounds if days.get(number) == day) / len(rounds)
            if share >= RULES_MIN_DATE_SHARE:
                shares.append((share, competition_id))
        best = max((share for share, _ in shares), default=0.0)
        for share, competition_id in shares:
            if share >= best - RULES_TIE_MARGIN:
                fitted[competition_id].add(places)

    found = {cid: ZoneRules(*next(iter(options))) for cid, options in linked.items() if len(options) == 1}
    for competition_id, options in fitted.items():
        if len(options) == 1:
            found[competition_id] = ZoneRules(*next(iter(options)), matched_by_calendar=True)
    return found


def _matchday_calendars(fixtures: Iterable[Fixture]) -> list[dict[int, dt.date]]:
    """For each season of a league, the day most of each matchday's matches are played on."""
    days: dict[int | None, dict[int, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for f in fixtures:
        if f.round is None and f.round_index is not None and f.date is not None:
            days[season_key(f)][f.round_index + 1][f.date] += 1
    return [{matchday: count.most_common(1)[0][0] for matchday, count in season.items()}
            for season in days.values()]


def _competition_info(
    competition_id: int,
    fixtures: Sequence[Fixture],
    database_id: int | None,
    reputation: Mapping[int, int],
    managed_teams: set[int],
    first_team_id: int | None,
) -> CompetitionInfo:
    keys = sorted({k for f in fixtures if (k := season_key(f)) is not None})
    latest = [f for f in fixtures if season_key(f) == keys[-1]] if keys else list(fixtures)
    short_names: dict[int, str] = {}
    teams: set[int] = set()
    for f in latest:
        teams.update((f.home_team_id, f.away_team_id))
        for uid, short, full in (
            (f.home_club_uid, f.home_club_short_name, f.home_club_name),
            (f.away_club_uid, f.away_club_short_name, f.away_club_name),
        ):
            if uid is not None and uid not in short_names:
                short_names[uid] = short or full or ""
    # Search covers every season the save holds, so a club is found wherever it has played.
    words: set[str] = {str(competition_id)}
    for f in fixtures:
        words.update(name for name in (f.home_club_name, f.home_club_short_name,
                                       f.away_club_name, f.away_club_short_name) if name)
    ranked = sorted(short_names, key=lambda uid: (-reputation.get(uid, 0), short_names[uid]))
    involved = [f for f in fixtures if f.home_team_id in managed_teams or f.away_team_id in managed_teams]
    return CompetitionInfo(
        id=competition_id,
        database_id=database_id,
        fixture_count=len(fixtures),
        played_count=sum(1 for f in fixtures if f.played),
        seasons=tuple(keys),
        team_count=len(teams),
        top_clubs=tuple(short_names[uid] for uid in ranked[:3] if short_names[uid]),
        search_text=" ".join(sorted(words)).casefold(),
        managed_fixtures=len(involved),
        managed_first_team=first_team_id is not None
        and any(first_team_id in (f.home_team_id, f.away_team_id) for f in involved),
        prominence=max((reputation.get(uid, 0) for uid in short_names), default=0),
    )


def _competition_order(c: CompetitionInfo) -> tuple:
    """The managed club's first-team competitions, then its other teams', then the rest by
    the reputation of their best-known club."""
    if c.managed_first_team:
        return (0, -c.managed_fixtures, c.id)
    if c.is_yours:
        return (1, -c.managed_fixtures, c.id)
    return (2, -c.prominence, -c.fixture_count, c.id)


# --------------------------------------------------------------------------- seasons


def season_key(fixture: Fixture) -> int | None:
    """The season a fixture belongs to: its stored start year, or by a 1 July boundary when
    the record stores none, as some friendlies do."""
    if fixture.season_start_year is not None:
        return fixture.season_start_year
    if fixture.date is not None:
        return fixture.date.year if fixture.date.month >= 7 else fixture.date.year - 1
    return None


def season_label(season: int | None, fixtures: Iterable[Fixture]) -> str:
    """'2026/27' for a season that crosses the new year, '2026' for a calendar-year one."""
    if season is None:
        return "No season"
    crosses = any(
        f.date is not None and f.date.year > season for f in fixtures if season_key(f) == season
    )
    return f"{season}/{(season + 1) % 100:02d}" if crosses else str(season)


def season_options(dataset: Dataset, competition_id: int) -> list[tuple[int, str]]:
    """(season, label) pairs for a competition, newest first."""
    fixtures = dataset.fixtures_for(competition_id)
    comp = dataset.by_id[competition_id]
    return [(s, season_label(s, fixtures)) for s in reversed(comp.seasons)]


def latest_played_season(dataset: Dataset, competition_id: int) -> int | None:
    played = [k for f in dataset.fixtures_for(competition_id) if f.played and (k := season_key(f)) is not None]
    return max(played) if played else None


def default_season(dataset: Dataset, competition_id: int) -> int | None:
    """The latest season with a played match, or the first season still to come."""
    latest = latest_played_season(dataset, competition_id)
    if latest is not None:
        return latest
    seasons = dataset.by_id[competition_id].seasons
    return seasons[0] if seasons else None


def season_fixtures(dataset: Dataset, competition_id: int, season: int | None) -> tuple[Fixture, ...]:
    return tuple(f for f in dataset.fixtures_for(competition_id) if season_key(f) == season)


# --------------------------------------------------------------------------- matches


def has_score(f: Fixture) -> bool:
    return f.home_goals is not None and f.away_goals is not None


def result_kind(f: Fixture) -> str:
    if not f.played:
        return SCHEDULED
    if not has_score(f):
        return UNAVAILABLE
    if f.home_goals > f.away_goals:
        return HOME_WIN
    if f.home_goals < f.away_goals:
        return AWAY_WIN
    return DRAW


def outcome_for(f: Fixture, team_id: int) -> str | None:
    """'W', 'D' or 'L' for one side of a played match with a score, else None."""
    if not f.played or not has_score(f) or team_id not in (f.home_team_id, f.away_team_id):
        return None
    scored, conceded = (f.home_goals, f.away_goals) if team_id == f.home_team_id else (f.away_goals, f.home_goals)
    return "W" if scored > conceded else "L" if scored < conceded else "D"


def score_text(f: Fixture) -> str:
    kind = result_kind(f)
    if kind == SCHEDULED:
        return "v"
    if kind == UNAVAILABLE:
        return "n/a"
    return f"{f.home_goals}-{f.away_goals}"


def round_text(f: Fixture) -> str:
    """'Md 12' for a league matchday, a name for a cup round whose code is confirmed."""
    if f.round is None:
        return f"Md {f.round_index + 1}" if f.round_index is not None else ""
    return ROUND_NAMES.get(f.round.label, "")


def coverage(fixtures: Iterable[Fixture]) -> Coverage:
    total = played = scored = 0
    for f in fixtures:
        total += 1
        if f.played:
            played += 1
            scored += has_score(f)
    return Coverage(total, played, scored)


def teams_in(fixtures: Iterable[Fixture]) -> set[int]:
    teams: set[int] = set()
    for f in fixtures:
        teams.update((f.home_team_id, f.away_team_id))
    return teams


def team_labels(fixtures: Iterable[Fixture], *, short: bool = False) -> dict[int, str]:
    """Display names for every team in the fixtures.

    A club's first team shows the club name alone. When one club fields more than one team in
    the same fixtures, the others get their team slot added, because the save stores no
    "U21" or "B team" names of its own.
    """
    teams: dict[int, tuple[int | None, str | None, int | None]] = {}
    for f in fixtures:
        for team_id, uid, full, abbreviated, slot in (
            (f.home_team_id, f.home_club_uid, f.home_club_name, f.home_club_short_name, f.home_team_slot),
            (f.away_team_id, f.away_club_uid, f.away_club_name, f.away_club_short_name, f.away_team_slot),
        ):
            if team_id not in teams:
                name = (abbreviated or full) if short else (full or abbreviated)
                teams[team_id] = (uid, name, slot)
    per_club = Counter(uid for uid, _, _ in teams.values() if uid is not None)
    labels: dict[int, str] = {}
    for team_id, (uid, name, slot) in teams.items():
        label = name or f"Team {team_id}"
        if uid is not None and per_club[uid] > 1 and slot:
            label = f"{label} (team {slot + 1})"
        labels[team_id] = label
    repeated = Counter(labels.values())
    return {tid: (f"{label} #{tid}" if repeated[label] > 1 else label) for tid, label in labels.items()}


def describe_fixture(f: Fixture, labels: Mapping[int, str]) -> str:
    """One line about a match, for a details bar."""
    home = labels.get(f.home_team_id, f"Team {f.home_team_id}")
    away = labels.get(f.away_team_id, f"Team {f.away_team_id}")
    when = _long_date(f.date) if f.date else "date not set"
    if f.kick_off_time:
        when += f" {f.kick_off_time:%H:%M}"
    kind = result_kind(f)
    if kind == SCHEDULED:
        result = "not played yet"
    elif kind == UNAVAILABLE:
        result = "played, but no score could be recovered from the save"
    else:
        result = f"{home} {f.home_goals}-{f.away_goals} {away}"
    extra = [text for text in (round_text(f), "neutral ground" if f.is_neutral_venue else "") if text]
    return f"{home} v {away} · {when}" + "".join(f" · {e}" for e in extra) + f" · {result}"


# --------------------------------------------------------------------------- results list


def timeline(
    fixtures: Sequence[Fixture],
    labels: Mapping[int, str],
    *,
    group_by: str = GROUP_BY_WEEK,
    focus_team: int | None = None,
) -> list[TimelineRow]:
    """Matches in date order under group headings: calendar week (Monday start), matchday or
    day. With a focus team only its matches are listed, with its result and running points.

    A postponed league match appears on the date it is actually played, keeping its matchday
    label; grouped by matchday it stays with its matchday.
    """
    chosen = [f for f in fixtures if focus_team is None or focus_team in (f.home_team_id, f.away_team_id)]
    chosen.sort(key=lambda f: (_when(f), labels.get(f.home_team_id, "")))
    running = _running_points(chosen, focus_team) if focus_team is not None else {}

    groups: dict[str, list[Fixture]] = {}
    for f in chosen:
        groups.setdefault(_group_heading(f, group_by), []).append(f)
    # Week and day headings arrive in date order already. Matchdays are ordered by their
    # first match, which puts a postponed match's matchday where most of it was played.
    rows: list[TimelineRow] = []
    for heading, items in groups.items():
        played = sum(1 for f in items if f.played)
        detail = _plural(len(items), "match", "matches")
        if played and played < len(items):
            detail += f", {played} played"
        rows.append(TimelineRow(heading=f"{heading}   ·   {detail}"))
        for f in items:
            result, points = running.get(id(f), ("", ""))
            rows.append(
                TimelineRow(
                    date=_short_date(f.date),
                    time=f"{f.kick_off_time:%H:%M}" if f.kick_off_time else "",
                    home=labels.get(f.home_team_id, f"Team {f.home_team_id}"),
                    score=score_text(f),
                    away=labels.get(f.away_team_id, f"Team {f.away_team_id}"),
                    round=round_text(f),
                    kind=result_kind(f),
                    result=result,
                    points=points,
                    home_id=f.home_team_id,
                    away_id=f.away_team_id,
                    fixture=f,
                )
            )
    return rows


def _group_heading(f: Fixture, group_by: str) -> str:
    if group_by == GROUP_BY_MATCHDAY:
        if f.round is None:
            return f"Matchday {f.round_index + 1}" if f.round_index is not None else "No matchday"
        return ROUND_NAMES.get(f.round.label) or f"Round (code {f.round.raw})"
    if f.date is None:
        return "Date not set"
    if group_by == GROUP_BY_DATE:
        return _long_date(f.date)
    monday = f.date - dt.timedelta(days=f.date.weekday())
    return f"Week of {_long_date(monday, weekday=True)}"


def _running_points(fixtures: Sequence[Fixture], team_id: int) -> dict[int, tuple[str, str]]:
    """Result and running points per played match, keyed by id(fixture). Once a played match
    has no recoverable score, later totals carry a '*': they are minimums."""
    points, incomplete = 0, False
    out: dict[int, tuple[str, str]] = {}
    for f in fixtures:
        if not f.played:
            continue
        outcome = outcome_for(f, team_id)
        if outcome is None:
            incomplete = True
            out[id(f)] = ("?", f"{points}*")
            continue
        points += WIN_POINTS if outcome == "W" else DRAW_POINTS if outcome == "D" else 0
        out[id(f)] = (outcome, f"{points}*" if incomplete else str(points))
    return out


# --------------------------------------------------------------------------- fixture grid


def fixture_grid(
    fixtures: Sequence[Fixture],
    labels: Mapping[int, str],
    short_labels: Mapping[int, str],
    *,
    max_teams: int = MAX_GRID_TEAMS,
) -> Grid | None:
    """Home team rows against away team columns, or None when there are more teams than
    max_teams. Both axes hold every team in the fixtures, so a team that has only played away
    still gets its row. A cell keeps every meeting, in date order."""
    team_ids = sorted(teams_in(fixtures), key=lambda tid: labels.get(tid, "").casefold())
    if len(team_ids) > max_teams:
        return None
    meetings: dict[tuple[int, int], list[Fixture]] = defaultdict(list)
    for f in sorted(fixtures, key=_when):
        meetings[(f.home_team_id, f.away_team_id)].append(f)
    cells = []
    for home in team_ids:
        row = []
        for away in team_ids:
            items = meetings.get((home, away), [])
            if home == away:
                row.append(GridCell("", "self"))
            elif not items:
                row.append(GridCell("", ""))
            else:
                row.append(GridCell(" / ".join(_grid_text(f) for f in items), _cell_kind(items), tuple(items)))
        cells.append(tuple(row))
    return Grid(
        team_ids=tuple(team_ids),
        row_labels=tuple(labels.get(t, f"Team {t}") for t in team_ids),
        column_labels=tuple(short_labels.get(t, f"Team {t}") for t in team_ids),
        cells=tuple(cells),
    )


def _grid_text(f: Fixture) -> str:
    kind = result_kind(f)
    if kind == SCHEDULED:
        return f"{f.date.day} {f.date:%b}" if f.date else "tbc"
    if kind == UNAVAILABLE:
        return "n/a"
    return f"{f.home_goals}-{f.away_goals}"


def _cell_kind(items: Sequence[Fixture]) -> str:
    kinds = [result_kind(f) for f in items]
    if len(set(kinds)) == 1:
        return kinds[0]
    results = {k for k in kinds if k in (HOME_WIN, DRAW, AWAY_WIN)}
    if len(results) == 1 and UNAVAILABLE not in kinds:
        return results.pop()
    return MIXED


# --------------------------------------------------------------------------- tables


def zone_for_position(position: int, total_teams: int, rules: ZoneRules | None = None) -> str:
    """The zone a league position falls in: from the game's own rules when the save gives them,
    otherwise estimated from the number of teams.

    The rules hold no European places, so a 20-team top division still has its Champions League
    and Europa League places estimated.
    """
    if position < 1 or position > total_teams:
        return ZONE_NONE
    if rules is not None:
        if rules.total > total_teams:       # rules for some other shape of table
            return ZONE_NONE
        if position <= rules.promotion:
            return ZONE_PROMOTION
        if position <= rules.promotion + rules.playoff:
            return ZONE_PLAYOFF
        if position > total_teams - rules.relegation:
            return ZONE_RELEGATION
        if rules.top_flight and total_teams == 20:
            return ZONE_UCL if position <= 4 else ZONE_EUROPA if position <= 6 else ZONE_NONE
        return ZONE_NONE
    if total_teams <= 4:
        return ZONE_NONE
    if total_teams == 20:
        if 1 <= position <= 4:
            return ZONE_UCL
        if 5 <= position <= 6:
            return ZONE_EUROPA
        if position >= 18:
            return ZONE_RELEGATION
    elif total_teams == 24:
        if 1 <= position <= 2:
            return ZONE_PROMOTION
        if 3 <= position <= 6:
            return ZONE_PLAYOFF
        if position >= 21:
            return ZONE_RELEGATION
    elif total_teams >= 16:
        if position == 1:
            return ZONE_PROMOTION
        if 2 <= position <= 4:
            return ZONE_PLAYOFF
        if position >= total_teams - 2:
            return ZONE_RELEGATION
    elif total_teams >= 8:
        if position == 1:
            return ZONE_PROMOTION
        if position >= total_teams - 1:
            return ZONE_RELEGATION
    return ZONE_NONE


def standings(
    dataset: Dataset,
    competition_id: int,
    season: int | None,
    fixtures: Sequence[Fixture],
    labels: Mapping[int, str],
    *,
    split: str = SPLIT_OVERALL,
) -> Standings:
    """The game's own stored table when it covers this season and split is Overall,
    else calculated from the results (Overall, Home, Away, or Form).

    Only the Overall table is marked with zones: a position in a home, away or form table is not
    a league position.
    """
    if split == SPLIT_HOME:
        rows = calculate_standings(fixtures, labels, home_only=True)
        note = "Home matches only. 3 points for a win, 1 for a draw."
        return Standings(False, note, (("", rows),))

    if split == SPLIT_AWAY:
        rows = calculate_standings(fixtures, labels, away_only=True)
        note = "Away matches only. 3 points for a win, 1 for a draw."
        return Standings(False, note, (("", rows),))

    if split == SPLIT_FORM:
        rows = calculate_standings(fixtures, labels, last_n=6)
        note = "Form guide: last 6 played matches for each team. 3 points for a win, 1 for a draw."
        return Standings(False, note, (("", rows),))

    rules = dataset.zone_rules.get(competition_id)
    forms = _forms(fixtures)
    stored = _stored_tables_for(dataset, competition_id, season, fixtures)
    if stored:
        groups = []
        for number, table in enumerate(stored, start=1):
            total_teams = len(table.rows)
            rows = tuple(
                StandingRow(
                    position=r.position,
                    team_id=r.team_id,
                    team=labels.get(r.team_id) or r.club_name or f"Team {r.team_id}",
                    played=r.played,
                    won=r.won,
                    drawn=r.drawn,
                    lost=r.lost,
                    goals_for=r.goals_for,
                    goals_against=r.goals_against,
                    points=r.points,
                    form=forms.get(r.team_id, ""),
                    zone=zone_for_position(r.position, total_teams, rules),
                )
                for r in table.rows
            )
            groups.append((f"Table {number} of {len(stored)}" if len(stored) > 1 else "", rows))
        note = ("Table as stored by the game: its positions, tie-breaks and any points "
                "deductions. Form is worked out from the results.")
        return Standings(True, note, tuple(groups), _zones_note(rules, groups))

    rows = calculate_standings(fixtures, labels, forms, zones=True, rules=rules)
    note = ("Calculated from the results: 3 points for a win, 1 for a draw; teams level on points "
            "are ordered by goal difference, then goals scored. The game may separate level teams "
            "differently (head-to-head) or deduct points.")
    missing = coverage(fixtures).unavailable
    if missing:
        note += f" {_plural(missing, 'played match', 'played matches')} with no recoverable score left out, so this table is incomplete."
    groups = (("", rows),)
    return Standings(False, note, groups, _zones_note(rules, groups))


def _zones_note(rules: ZoneRules | None, groups: Sequence[tuple[str, Sequence[StandingRow]]]) -> str:
    """Where the coloured positions come from, or nothing when no position is coloured."""
    zones = {r.zone for _, rows in groups for r in rows if r.zone}
    if not zones:
        return ""
    if rules is None:
        return ("Zones are estimated from the number of teams: the save's rules for this "
                "competition could not be matched to it.")
    note = f"Zones follow the game's rules for this competition: {rules.describe()}."
    if zones & {ZONE_UCL, ZONE_EUROPA}:
        note += " European places are estimated."
    return note


def calculate_standings(
    fixtures: Sequence[Fixture],
    labels: Mapping[int, str],
    forms: Mapping[int, str] | None = None,
    *,
    home_only: bool = False,
    away_only: bool = False,
    last_n: int | None = None,
    zones: bool = False,
    rules: ZoneRules | None = None,
) -> tuple[StandingRow, ...]:
    """A table worked out from the results. With zones=True each row gets its zone, from the
    competition's rules when given."""
    forms = _forms(fixtures, home_only=home_only, away_only=away_only) if forms is None else forms
    totals = {tid: [0, 0, 0, 0, 0, 0] for tid in teams_in(fixtures)}  # P W D L GF GA

    if last_n is not None:
        team_matches: dict[int, list[Fixture]] = defaultdict(list)
        for f in sorted(fixtures, key=_when):
            if f.played and has_score(f):
                team_matches[f.home_team_id].append(f)
                team_matches[f.away_team_id].append(f)
        for tid in totals:
            recent = team_matches[tid][-last_n:]
            t = totals[tid]
            for f in recent:
                scored = f.home_goals if f.home_team_id == tid else f.away_goals
                conceded = f.away_goals if f.home_team_id == tid else f.home_goals
                t[0] += 1
                t[1 if scored > conceded else 2 if scored == conceded else 3] += 1
                t[4] += scored
                t[5] += conceded
    else:
        for f in fixtures:
            if not f.played or not has_score(f):
                continue
            if not away_only:
                t = totals[f.home_team_id]
                t[0] += 1
                t[1 if f.home_goals > f.away_goals else 2 if f.home_goals == f.away_goals else 3] += 1
                t[4] += f.home_goals
                t[5] += f.away_goals
            if not home_only:
                t = totals[f.away_team_id]
                t[0] += 1
                t[1 if f.away_goals > f.home_goals else 2 if f.away_goals == f.home_goals else 3] += 1
                t[4] += f.away_goals
                t[5] += f.home_goals

    def points(t: list[int]) -> int:
        return t[1] * WIN_POINTS + t[2] * DRAW_POINTS

    order = sorted(
        totals,
        key=lambda tid: (-points(totals[tid]), -(totals[tid][4] - totals[tid][5]), -totals[tid][4],
                         labels.get(tid, "").casefold()),
    )
    total_teams = len(order)
    return tuple(
        StandingRow(
            position=position,
            team_id=tid,
            team=labels.get(tid, f"Team {tid}"),
            played=totals[tid][0],
            won=totals[tid][1],
            drawn=totals[tid][2],
            lost=totals[tid][3],
            goals_for=totals[tid][4],
            goals_against=totals[tid][5],
            points=points(totals[tid]),
            form=forms.get(tid, ""),
            zone=zone_for_position(position, total_teams, rules) if zones else ZONE_NONE,
        )
        for position, tid in enumerate(order, start=1)
    )


def _stored_tables_for(
    dataset: Dataset, competition_id: int, season: int | None, fixtures: Sequence[Fixture]
) -> list[LeagueTable]:
    """Stored tables are live ones, so they belong to the competition's latest played season,
    and only tables whose clubs all appear in this season's fixtures are trusted."""
    tables = dataset.stored_tables.get(competition_id, ())
    if not tables or season is None or season != latest_played_season(dataset, competition_id):
        return []
    teams = teams_in(fixtures)
    return [t for t in tables if t.rows and {r.team_id for r in t.rows} <= teams]


def _forms(
    fixtures: Iterable[Fixture],
    *,
    home_only: bool = False,
    away_only: bool = False,
    length: int = FORM_LENGTH,
) -> dict[int, str]:
    results: dict[int, list[str]] = defaultdict(list)
    for f in sorted(fixtures, key=_when):
        if f.played and has_score(f):
            if not away_only:
                results[f.home_team_id].append(outcome_for(f, f.home_team_id))
            if not home_only:
                results[f.away_team_id].append(outcome_for(f, f.away_team_id))
    return {tid: "".join(items[-length:]) for tid, items in results.items()}


def competition_category(comp: CompetitionInfo, dataset: Dataset) -> str:
    """Sorts a competition for the Competitions view by what most of its fixtures look like,
    since the save stores no competition type.

    Friendlies store no season. In a youth or reserve competition both sides are usually a
    club's second or later team; a senior league that admits a few reserve sides is still a
    league. A team the save cannot resolve has no slot and counts as a first team.
    """
    if comp.is_yours:
        return COMP_CAT_YOURS
    fixtures = dataset.fixtures_for(comp.id)
    if not fixtures:
        return COMP_CAT_OTHER
    half = len(fixtures) / 2
    if sum(1 for f in fixtures if f.season_start_year is None) > half:
        return COMP_CAT_FRIENDLY
    if sum(1 for f in fixtures if (f.home_team_slot or 0) > 0 and (f.away_team_slot or 0) > 0) > half:
        return COMP_CAT_YOUTH
    if sum(1 for f in fixtures if f.round is not None) > half:
        return COMP_CAT_CUP
    return COMP_CAT_LEAGUE


def competitions_summary(dataset: Dataset, names: Mapping[int, str]) -> tuple[CompetitionSummaryRow, ...]:
    """Builds summary rows for all competitions in the dataset for the Competitions Viewer."""
    rows: list[CompetitionSummaryRow] = []
    for comp in dataset.competitions:
        pct = f"{(comp.played_count / comp.fixture_count * 100):.0f}%" if comp.fixture_count > 0 else "0%"
        rows.append(
            CompetitionSummaryRow(
                id=comp.id,
                database_id=comp.database_id,
                name=competition_title(comp, names),
                category=competition_category(comp, dataset),
                teams=comp.team_count,
                fixtures=comp.fixture_count,
                played=comp.played_count,
                scored=sum(1 for f in dataset.fixtures_for(comp.id) if f.played and has_score(f)),
                progress=pct,
                seasons=len(comp.seasons),
                example_clubs=", ".join(comp.top_clubs[:3]) if comp.top_clubs else "None",
            )
        )
    return tuple(rows)


# --------------------------------------------------------------------------- names


def load_competition_names(path: Path) -> dict[int, str]:
    """Names keyed on the competition's editor database id, from a 'database_id,name' CSV
    (the same format fmsave.open accepts). A missing file means no names yet.

    Raises:
        ValueError: The file is malformed; the message names the line.
    """
    if not path.exists():
        return {}
    return dict(fmsave.read_competition_names(path))


def save_competition_names(path: Path, names: Mapping[int, str]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["database_id", "name"])
        for database_id in sorted(names):
            writer.writerow([database_id, names[database_id]])
    os.replace(temporary, path)


def competition_title(comp: CompetitionInfo, names: Mapping[int, str]) -> str:
    if comp.database_id is not None and comp.database_id in names:
        return names[comp.database_id]
    return f"Competition {comp.id}"


def competition_list_label(comp: CompetitionInfo, names: Mapping[int, str]) -> str:
    """The name if one is set, otherwise the competition's best-known clubs."""
    if comp.database_id is not None and comp.database_id in names:
        return names[comp.database_id]
    clubs = ", ".join(comp.top_clubs) or "no clubs named"
    return f"[{comp.id}] {clubs}"


def competition_hint(comp: CompetitionInfo) -> str:
    clubs = ", ".join(comp.top_clubs)
    text = _plural(comp.team_count, "team")
    return f"{text} · {clubs}" if clubs else text


def matches_search(comp: CompetitionInfo, names: Mapping[int, str], text: str) -> bool:
    needle = text.strip().casefold()
    if not needle:
        return True
    return needle in comp.search_text or needle in competition_title(comp, names).casefold()


# --------------------------------------------------------------------------- helpers


def _when(f: Fixture) -> tuple:
    return (f.date is None, f.date or dt.date.min, f.kick_off_time is None, f.kick_off_time or dt.time.min)


def _short_date(day: dt.date | None) -> str:
    return f"{day:%a} {day.day} {day:%b}" if day else ""


def _long_date(day: dt.date, *, weekday: bool = True) -> str:
    text = f"{day.day} {day:%B %Y}"
    return f"{day:%A} {text}" if weekday else text


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"
