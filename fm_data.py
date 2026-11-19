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
import math
import os
import time
import warnings
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
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

# Tie-break codes a competition's rules list in order, as fmsave reads them (unconfirmed: the game
# names none of them). These three can be worked out from results, and following them reproduced
# every division-sized table stored in the saves checked on 15 November 2026: MLS and Brazil list
# wins first. Others, such as results between the level teams, cannot be worked out here.
TIE_BREAK_GOAL_DIFFERENCE, TIE_BREAK_GOALS_SCORED, TIE_BREAK_WINS = 0, 1, 2
DEFAULT_TIE_BREAKS = (TIE_BREAK_GOAL_DIFFERENCE, TIE_BREAK_GOALS_SCORED)
TIE_BREAK_NAMES = {TIE_BREAK_GOAL_DIFFERENCE: "goal difference", TIE_BREAK_GOALS_SCORED: "goals scored",
                   TIE_BREAK_WINS: "wins"}

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
    managed_manager_name: str | None = None      # the save's name for the human manager, when it gives one


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
    tie_breaks: Mapping[int, tuple[int, ...]] = field(default_factory=dict)
    club_nations: Mapping[int, int] = field(default_factory=dict)      # club uid -> nation id, where the save says
    expected_goals: Mapping[tuple, ExpectedGoals] = field(default_factory=dict)   # keyed on fixture_key
    match_reports: Mapping[tuple, MatchStats] = field(default_factory=dict)        # keyed on fixture_key
    xg_report: XgReport | None = None    # None until the match statistics have been read
    teams: Mapping[int, TeamIdentity] = field(default_factory=dict)    # every team the fixtures name
    grounds: Mapping[int, Ground] | None = None    # None until the stadium table has been read, or if it could not be
    ground_failure: str = ""

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

    @property
    def order(self) -> tuple[int, ...]:
        """Team ids in table order: the table that holds every team when there is one (a league's
        whole table beside its conferences), otherwise each table in turn."""
        tables = [tuple(r.team_id for r in rows) for _, rows in self.groups]
        every = {team_id for table in tables for team_id in table}
        for table in sorted(tables, key=len, reverse=True):
            if set(table) == every:
                return table
        return tuple(dict.fromkeys(team_id for table in tables for team_id in table))


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


# --------------------------------------------------------------------------- club identity

# Which of a club's teams a followed club covers. Slot 0 is the club's first team; every other slot (its
# reserve and youth sides) is "reserve". A team the save cannot resolve belongs to neither.
SCOPE_SENIOR = "senior"
SCOPE_RESERVE = "reserve"


@dataclass(frozen=True, slots=True)
class TeamIdentity:
    """One team as the fixtures name it. A team the save cannot resolve has no club, name or slot."""

    team_id: int
    club_uid: int | None
    club_name: str | None
    slot: int | None


@dataclass(frozen=True, slots=True)
class FollowedClub:
    """The club the user follows across every competition. Following is a choice made in this window: it does
    not change the save and does not say the club is managed (see ManagerSnapshot.managed)."""

    club_uid: int
    scope: str = SCOPE_SENIOR
    name: str = ""


def team_identities(fixtures: Iterable[Fixture]) -> dict[int, TeamIdentity]:
    """Every team in the fixtures with its club and slot. A team seen once unresolved and once resolved keeps
    the resolved identity."""
    found: dict[int, TeamIdentity] = {}
    for f in fixtures:
        for team_id, uid, name, slot in ((f.home_team_id, f.home_club_uid, f.home_club_name, f.home_team_slot),
                                         (f.away_team_id, f.away_club_uid, f.away_club_name, f.away_team_slot)):
            current = found.get(team_id)
            if current is None or (current.club_uid is None and uid is not None):
                found[team_id] = TeamIdentity(team_id, uid, name, slot)
    return found


def followed_team_ids(dataset: Dataset, followed: FollowedClub) -> frozenset[int]:
    """The teams of the followed club in the scope chosen: the first team alone, or every other team."""
    senior = followed.scope == SCOPE_SENIOR
    return frozenset(
        t.team_id for t in dataset.teams.values()
        if t.club_uid == followed.club_uid and t.slot is not None and (t.slot == 0) == senior)


def default_followed_club(dataset: Dataset) -> FollowedClub | None:
    """The managed club's first team, when the save has a managed club that plays in it; None for an observer
    save. Only a default: the user may follow any club, or none."""
    uid = dataset.info.managed_club_uid
    if uid is None:
        return None
    follow = FollowedClub(uid)
    ids = followed_team_ids(dataset, follow)
    if not ids:
        return None
    return replace(follow, name=dataset.teams[min(ids)].club_name or "")


@dataclass(frozen=True, slots=True)
class FixtureRef:
    """A stable name for one match, so a row, a selection or a bookmark can find it again after the list is
    sorted, filtered or rebuilt: competition, season, both teams and the date, plus the match's place among any
    others with the same five (a replay on the same day) in date and time order."""

    competition_id: int | None
    season: int | None
    home_team_id: int
    away_team_id: int
    date: dt.date | None
    ordinal: int = 0


def _ref_key(f: Fixture) -> tuple:
    return (f.competition_id, season_key(f), f.home_team_id, f.away_team_id, f.date)


def fixture_refs(fixtures: Iterable[Fixture]) -> list[FixtureRef]:
    """A reference for each fixture, in the order given. The ordinal depends on the matches' dates and times,
    not on the order of the list."""
    items = list(fixtures)
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, f in enumerate(items):
        groups[_ref_key(f)].append(i)
    ordinals = [0] * len(items)
    for indexes in groups.values():
        if len(indexes) > 1:
            for n, i in enumerate(sorted(indexes, key=lambda i: _when(items[i]))):
                ordinals[i] = n
    return [FixtureRef(*_ref_key(f), ordinals[i]) for i, f in enumerate(items)]


def resolve_fixture(dataset: Dataset, ref: FixtureRef) -> Fixture | None:
    """The fixture a reference names in this dataset, or None when it holds no such match."""
    found = sorted((f for f in dataset.fixtures.get(ref.competition_id, ()) if _ref_key(f) == _ref_key_of(ref)),
                   key=_when)
    return found[ref.ordinal] if ref.ordinal < len(found) else None


def _ref_key_of(ref: FixtureRef) -> tuple:
    return (ref.competition_id, ref.season, ref.home_team_id, ref.away_team_id, ref.date)


# --------------------------------------------------------------------------- venues

# How far a piece of match information can be trusted to be there: read and held, still being read, could not
# be had (not stored, not joined or not readable), or not recorded for this match at all.
STATE_KNOWN, STATE_PENDING, STATE_UNAVAILABLE, STATE_UNRECORDED = "known", "pending", "unavailable", "unrecorded"


@dataclass(frozen=True, slots=True)
class Ground:
    """A ground from the save's stadium table. Only a couple of hundred grounds store a name; the capacity is the
    ground's total (seated and standing), never the separate additional figure, and is None when the save holds
    none or zero."""

    uid: int
    name: str | None
    total_capacity: int | None


def ground_from_stadium(row) -> Ground:
    total = row.total_capacity
    return Ground(row.uid, row.name or None, total if isinstance(total, int) and total > 0 else None)


def with_grounds(dataset: Dataset, rows: Iterable | None, failure: str = "") -> Dataset:
    """The Dataset with the save's grounds. `rows` is None when the stadium table could not be read, and `failure`
    says why; nothing else in the Dataset changes."""
    if rows is None:
        return replace(dataset, grounds=None, ground_failure=failure or "not read")
    grounds = {g.uid: g for g in map(ground_from_stadium, rows)}
    return replace(dataset, grounds=grounds, ground_failure="")


@dataclass(frozen=True, slots=True)
class Venue:
    """What the save says about where a match was played. `neutral` keeps True, False and None (unknown) apart.
    The name is the fixture's own or the stadium table's, never worked out from a club; there is no attendance,
    occupancy or weather, because the save holds none."""

    neutral: bool | None
    stadium_uid: int | None
    name: str | None
    total_capacity: int | None
    capacity_state: str

    def lines(self) -> tuple[str, ...]:
        found = []
        if self.neutral is True:
            found.append("Neutral ground")
        elif self.neutral is None:
            found.append("Neutral ground: unknown")
        if self.name:
            found.append(self.name)
        else:
            found.append("Ground name not recorded" if self.stadium_uid is not None else "Ground not recorded")
        if self.capacity_state == STATE_KNOWN:
            found.append(f"Capacity {self.total_capacity:,}")
        elif self.capacity_state == STATE_PENDING:
            found.append("Capacity: still being read")
        elif self.capacity_state == STATE_UNAVAILABLE:
            found.append("Capacity unavailable")
        return tuple(found)


def venue_for(dataset: Dataset, f: Fixture) -> Venue:
    """The venue of a match from the fixture and the ground table."""
    uid = f.stadium_uid
    if uid is None:
        return Venue(f.is_neutral_venue, None, f.stadium_name or None, None, STATE_UNRECORDED)
    ground = dataset.grounds.get(uid) if dataset.grounds is not None else None
    if ground is not None and ground.total_capacity is not None:
        state = STATE_KNOWN
    elif dataset.grounds is None and not dataset.ground_failure and dataset.xg_report is None:
        state = STATE_PENDING
    else:
        state = STATE_UNAVAILABLE
    return Venue(f.is_neutral_venue, uid, f.stadium_name or (ground.name if ground else None) or None,
                 ground.total_capacity if ground else None, state)


# --------------------------------------------------------------------------- loading


def load_dataset(
    path: str | os.PathLike[str],
    progress: Callable[[str], None] = lambda _message: None,
    *,
    ready: Callable[[Dataset], None] | None = None,
) -> Dataset:
    """Read a save with fmsave and build a Dataset. The save is only read, never written.

    The match statistics behind expected goals are read last, because they take a while: with
    `ready`, the Dataset is handed over as soon as everything else is in, and the one returned
    adds expected goals. A failure to read them is noted and changes nothing else.

    Raises:
        ImportFailed: The save cannot be read, with a message for the user.
    """
    started = time.perf_counter()
    path = Path(path)
    notes: list[str] = []
    dataset: Dataset | None = None
    stats: list | None = None
    grounds: list | None = None
    failure = ""
    ground_failure = ""
    caller_error: Exception | None = None      # raised by `ready`: the caller's failure, never the save's
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
                progress("Organising fixtures")
                info = _import_info(path, save_info, managed, caught, notes, started)
                dataset = build_dataset(info, fixtures, clubs=clubs, competitions=competitions, tables=tables,
                                        rules=rules)
                if ready is not None:
                    try:
                        ready(dataset)
                    except Exception as exc:
                        caller_error = exc
                        raise
                progress("Reading match statistics (xG)")
                try:
                    stats = list(save.team_match_stats())
                except Exception as exc:  # the match reports can fail on their own on an unverified build
                    failure = f"{type(exc).__name__}: {exc}"
                progress("Reading grounds")
                try:
                    grounds = list(save.stadiums())
                except Exception as exc:  # the stadium table can fail on its own too; the save is still usable
                    ground_failure = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            if exc is caller_error:
                raise
            if dataset is None:
                failed = _import_failure(path, exc)
                if failed is None:
                    raise
                raise failed from exc
            failure = failure or f"{type(exc).__name__}: {exc}"     # the save was read: keep it

        if failure:
            stats = None
            notes.append(f"Match statistics (xG) could not be read ({failure})")
        if ground_failure:
            grounds = None
            notes.append(f"Grounds could not be read ({ground_failure})")
        info = _import_info(path, save_info, managed, caught, notes, started)
    return with_grounds(with_expected_goals(replace(dataset, info=info), stats, failure), grounds, ground_failure)


def _import_info(path: Path, save_info, managed: Sequence, caught: Sequence, notes: Sequence[str],
                 started: float) -> ImportInfo:
    reader_warnings = list(dict.fromkeys(f"{w.category.__name__}: {w.message}" for w in caught))
    return ImportInfo(
        path=str(path),
        file_name=path.name,
        game=save_info.game,
        build=save_info.build,
        known_build=save_info.known_build,
        game_date=save_info.game_date,
        fmsave_version=fmsave.__version__,
        imported_at=dt.datetime.now(),
        seconds=time.perf_counter() - started,
        warnings=tuple(reader_warnings + list(notes)),
        managed_club_uid=managed[0].club_uid if managed else None,
        managed_club_name=managed[0].club_name if managed else None,
        managed_manager_name=(getattr(managed[0], "manager_name", None) or None) if managed else None,
    )


def _import_failure(path: Path, exc: Exception) -> ImportFailed | None:
    """What to tell the user when a save cannot be read, or None for an unexpected error."""
    if isinstance(exc, FileNotFoundError):
        return ImportFailed(f"File not found: {path.name}")
    if isinstance(exc, fmsave.NotAFmSaveError):
        return ImportFailed(f"{path.name} is not a Football Manager save.")
    if isinstance(exc, fmsave.UnsupportedGameError):
        return ImportFailed(f"fmsave cannot read this save: {exc}")
    if isinstance(exc, fmsave.SaveChangedError):
        return ImportFailed("The save changed while it was being read. If Football Manager is saving, "
                            "wait for it to finish and try again.")
    if isinstance(exc, fmsave.CorruptSaveError):
        return ImportFailed("The save looks damaged or was still being written. Try again once the game "
                            "has finished saving.")
    if isinstance(exc, fmsave.FmsaveError):
        return ImportFailed(f"fmsave could not read this save ({type(exc).__name__}): {exc}")
    if isinstance(exc, OSError):
        return ImportFailed(f"Could not read {path.name}: {exc.strerror or exc}")
    return None


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
    match_stats: Iterable | None = None,
) -> Dataset:
    """Organise fmsave records into a Dataset. Pure: no file access. Without `match_stats` the
    Dataset has no expected goals yet; see with_expected_goals."""
    fixtures = list(fixtures)
    rules = list(rules)
    reputation: dict[int, int] = {}
    club_nations: dict[int, int] = {}
    managed_teams: set[int] = set()
    first_team_id: int | None = None
    for club in clubs:
        if club.reputation is not None:
            reputation[club.uid] = club.reputation
        if getattr(club, "nation_id", None) is not None:
            club_nations[club.uid] = club.nation_id
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

    dataset = Dataset(
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
        tie_breaks=link_tie_breaks(rules),
        club_nations=club_nations,
        teams=team_identities(fixtures),
    )
    return dataset if match_stats is None else with_expected_goals(dataset, match_stats)


def link_tie_breaks(rules: Iterable) -> dict[int, tuple[int, ...]]:
    """The tie-break codes each competition's rules list, in order, for the competitions whose
    linked rules blocks all list the same ones."""
    found: dict[int, set[tuple[int, ...]]] = defaultdict(set)
    for block in rules:
        if block.competition_id is None:
            continue
        unknown = getattr(block, "unknown", None) or {}
        found[block.competition_id].add(tuple(unknown[key] for key in sorted(unknown) if key.startswith("tie_break_")))
    return {cid: codes for cid, options in found.items() if len(options) == 1 and (codes := next(iter(options)))}


def tie_break_order(codes: Sequence[int] = ()) -> tuple[tuple[int, ...], str]:
    """How a table worked out from results separates teams level on points, and a phrase saying
    so: the leading tie-breaks the competition's rules list that results can settle, else goal
    difference and then goals scored."""
    usable: list[int] = []
    for code in codes:
        if code not in TIE_BREAK_NAMES:
            break
        usable.append(code)
    order = tuple(usable) or DEFAULT_TIE_BREAKS
    names = ", then ".join(TIE_BREAK_NAMES[code] for code in order)
    if usable:
        text = f"teams level on points are ordered by {names}, as the competition's rules list them"
        if len(usable) < len(codes):
            text += "; the game separates any still level by further rules"
    elif codes:
        text = (f"teams level on points are ordered by {names}, but the competition's rules separate them "
                "first by a rule this calculation cannot follow, so the game's order may differ")
    else:
        text = (f"teams level on points are ordered by {names}; the game may separate level teams "
                "differently (head-to-head)")
    return order, text


def _ranking(points: int, wins: int, goals_for: int, goals_against: int, order: Sequence[int]) -> tuple[int, ...]:
    """A sort key, best first, for a team's record under a tie-break order."""
    values = {TIE_BREAK_GOAL_DIFFERENCE: goals_for - goals_against, TIE_BREAK_GOALS_SCORED: goals_for,
              TIE_BREAK_WINS: wins}
    return (-points, *(-values[code] for code in order))


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


def team_club_names(fixtures: Iterable[Fixture]) -> dict[int, str]:
    """Each team's club name as the save spells it, so that a club's reserve and youth sides share
    it. Teams the save cannot resolve have no club name and are left out."""
    names: dict[int, str] = {}
    for f in fixtures:
        for team_id, name in ((f.home_team_id, f.home_club_name), (f.away_team_id, f.away_club_name)):
            if name and team_id not in names:
                names[team_id] = name
    return names


def team_club_uids(fixtures: Iterable[Fixture]) -> dict[int, int]:
    """Each team's club uid, so that a club's reserve and youth sides share it. Teams the save cannot resolve have
    no club uid and are left out."""
    uids: dict[int, int] = {}
    for f in fixtures:
        for team_id, uid in ((f.home_team_id, f.home_club_uid), (f.away_team_id, f.away_club_uid)):
            if uid is not None and team_id not in uids:
                uids[team_id] = uid
    return uids


def underlying_category(comp: CompetitionInfo, dataset: Dataset) -> str:
    """What a competition is by its fixtures alone: the hub files a competition the user manages in as Your
    Club, which says nothing about whether it is a league or a cup."""
    return competition_category(replace(comp, managed_fixtures=0), dataset)


@dataclass(frozen=True, slots=True)
class ClubEntry:
    """A team as a command palette offers it: its label and the competition it would be opened in."""

    team_id: int
    label: str
    competition_id: int
    category: str          # COMP_CAT_LEAGUE or COMP_CAT_CUP: the kind of competition it is listed under


def club_index(dataset: Dataset) -> tuple[ClubEntry, ...]:
    """The clubs of every senior league and cup competition, once for each competition they play in,
    from the competition's default season. Youth, reserve and friendly competitions are left out, so
    one friendlies competition's thousands of teams do not bury the real clubs. A competition the user
    manages is sorted by its fixtures like any other (a managed friendly is still a friendly), and a
    team the save cannot resolve has no club name and is left out. Ordered by competition, then label."""
    entries: list[ClubEntry] = []
    for comp in dataset.competitions:
        category = underlying_category(comp, dataset)
        if category not in (COMP_CAT_LEAGUE, COMP_CAT_CUP):
            continue
        seen: dict[int, tuple[str, int]] = {}
        for f in season_fixtures(dataset, comp.id, default_season(dataset, comp.id)):
            for team_id, name, slot in ((f.home_team_id, f.home_club_name, f.home_team_slot),
                                        (f.away_team_id, f.away_club_name, f.away_team_slot)):
                if name and team_id not in seen:
                    seen[team_id] = (name, slot or 0)
        entries.extend(ClubEntry(team_id, name if slot == 0 else f"{name} (team {slot + 1})", comp.id, category)
                       for team_id, (name, slot) in seen.items())
    entries.sort(key=lambda e: (e.competition_id, e.label.casefold(), e.team_id))
    return tuple(entries)


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
    tie_breaks = dataset.tie_breaks.get(competition_id, ())
    if split == SPLIT_HOME:
        rows = calculate_standings(fixtures, labels, home_only=True, tie_breaks=tie_breaks)
        note = "Home matches only. 3 points for a win, 1 for a draw."
        return Standings(False, note, (("", rows),))

    if split == SPLIT_AWAY:
        rows = calculate_standings(fixtures, labels, away_only=True, tie_breaks=tie_breaks)
        note = "Away matches only. 3 points for a win, 1 for a draw."
        return Standings(False, note, (("", rows),))

    if split == SPLIT_FORM:
        rows = calculate_standings(fixtures, labels, last_n=6, tie_breaks=tie_breaks)
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
        return Standings(True, note, tuple(groups), _zones_note(rules, {r.zone for _, rows in groups for r in rows}))

    rows = calculate_standings(fixtures, labels, forms, zones=True, rules=rules, tie_breaks=tie_breaks)
    note = (f"Calculated from the results: 3 points for a win, 1 for a draw; {tie_break_order(tie_breaks)[1]}. "
            "The game may also deduct points, which a calculated table cannot show.")
    missing = coverage(fixtures).unavailable
    if missing:
        note += f" {_plural(missing, 'played match', 'played matches')} with no recoverable score left out, so this table is incomplete."
    groups = (("", rows),)
    return Standings(False, note, groups, _zones_note(rules, {r.zone for _, rows in groups for r in rows}))


def _zones_note(rules: ZoneRules | None, zones: set[str]) -> str:
    """Where the coloured positions come from, or nothing when no position is coloured."""
    zones = {zone for zone in zones if zone}
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
    tie_breaks: Sequence[int] = (),
) -> tuple[StandingRow, ...]:
    """A table worked out from the results, level teams separated as `tie_breaks` (a competition's
    rules) list, else by goal difference and then goals scored; see tie_break_order. With
    zones=True each row gets its zone, from the competition's rules when given."""
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

    ranking = tie_break_order(tie_breaks)[0]
    order = sorted(
        totals,
        key=lambda tid: (*_ranking(points(totals[tid]), totals[tid][1], totals[tid][4], totals[tid][5], ranking),
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


def standings_as_of(
    fixtures: Sequence[Fixture],
    labels: Mapping[int, str],
    *,
    through: dt.date,
    tie_breaks: Sequence[int] = (),
    form_length: int = 6,
) -> tuple[StandingRow, ...]:
    """The table as it stood at the end of `through`, worked out from the results: a match played after that
    date does not count yet (so a postponed match leaves games in hand), but every club still appears. Level
    teams are separated as `tie_breaks` list; form is the last `form_length` results by then. Calculated, never
    the game's stored table."""
    by_then = [f if f.date is not None and f.date <= through else replace(f, played=False)
               for f in fixtures]
    return calculate_standings(by_then, labels, _forms(by_then, length=form_length), tie_breaks=tie_breaks)


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


# --------------------------------------------------------------------------- form and streaks

UNKNOWN_RESULT = "?"     # a match played with no recoverable score


@dataclass(frozen=True, slots=True)
class FormStep:
    """One played match seen from one team's side. A match played with no recoverable score has
    the outcome '?' and no goals or points: it never counts as a win, a draw or a defeat."""

    fixture: Fixture
    team_id: int
    opponent_id: int
    opponent: str
    home: bool                   # the team was the home side, even on a neutral ground
    goals_for: int | None
    goals_against: int | None

    @property
    def date(self) -> dt.date | None:
        return self.fixture.date

    @property
    def venue(self) -> str:
        """'H' or 'A', or 'N' for a match on a neutral ground."""
        return "N" if self.fixture.is_neutral_venue else "H" if self.home else "A"

    @property
    def outcome(self) -> str:
        if self.goals_for is None or self.goals_against is None:
            return UNKNOWN_RESULT
        if self.goals_for > self.goals_against:
            return "W"
        return "L" if self.goals_for < self.goals_against else "D"

    @property
    def points(self) -> int | None:
        return {"W": WIN_POINTS, "D": DRAW_POINTS, "L": 0}.get(self.outcome)

    @property
    def score(self) -> str:
        """The score from this team's side: '3-1' for an away win by three goals to one."""
        return "n/a" if self.outcome == UNKNOWN_RESULT else f"{self.goals_for}-{self.goals_against}"

    def describe(self) -> str:
        """'W 3-1 at Derby County', 'D 1-1 v Leeds United', with '(neutral ground)' where it was."""
        opponent = f"at {self.opponent}" if self.venue == "A" else f"v {self.opponent}"
        return f"{self.outcome} {self.score} {opponent}" + (" (neutral ground)" if self.venue == "N" else "")


def team_steps(fixtures: Iterable[Fixture], team_id: int, labels: Mapping[int, str]) -> tuple[FormStep, ...]:
    """Every played match of one team, oldest first, seen from the team's side."""
    return tuple(_step(f, team_id, labels) for f in sorted(fixtures, key=_when)
                 if f.played and team_id in (f.home_team_id, f.away_team_id))


def _step(f: Fixture, team_id: int, labels: Mapping[int, str]) -> FormStep:
    home = f.home_team_id == team_id
    opponent = f.away_team_id if home else f.home_team_id
    scored = has_score(f)
    return FormStep(
        fixture=f,
        team_id=team_id,
        opponent_id=opponent,
        opponent=labels.get(opponent, f"Team {opponent}"),
        home=home,
        goals_for=(f.home_goals if home else f.away_goals) if scored else None,
        goals_against=(f.away_goals if home else f.home_goals) if scored else None,
    )


@dataclass(frozen=True, slots=True)
class TeamTotals:
    """A team's record over some played matches. A match with no recoverable score counts as
    played and in nothing else, so the totals are then incomplete: minimums, not the record."""

    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    clean_sheets: int = 0
    failed_to_score: int = 0

    @property
    def scored(self) -> int:
        """Played matches with a score."""
        return self.won + self.drawn + self.lost

    @property
    def unavailable(self) -> int:
        return self.played - self.scored

    @property
    def incomplete(self) -> bool:
        return self.unavailable > 0

    @property
    def points(self) -> int:
        return self.won * WIN_POINTS + self.drawn * DRAW_POINTS

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    @property
    def ppg(self) -> float | None:
        """Points per game over the matches with a score, or None when there are none."""
        return self.points / self.scored if self.scored else None

    def ppg_text(self) -> str:
        """Points per game for a table cell: '1.75', with '*' when a missing score makes it a
        figure from only some matches, or '' with none to go on."""
        if self.ppg is None:
            return ""
        return f"{self.ppg:.2f}" + ("*" if self.incomplete else "")

    def describe_ppg(self) -> str:
        """'PPG 1.75 from 4 scored (1 n/a)': the figure and the matches behind it."""
        if not self.scored:
            return "No scored matches" + (f" ({self.unavailable} n/a)" if self.unavailable else "")
        text = f"PPG {self.ppg:.2f} from {self.scored} scored"
        return text + (f" ({self.unavailable} n/a)" if self.unavailable else "")


def team_totals(steps: Iterable[FormStep]) -> TeamTotals:
    played = won = drawn = lost = goals_for = goals_against = clean_sheets = failed_to_score = 0
    for step in steps:
        played += 1
        if step.outcome == UNKNOWN_RESULT:
            continue
        won += step.outcome == "W"
        drawn += step.outcome == "D"
        lost += step.outcome == "L"
        goals_for += step.goals_for
        goals_against += step.goals_against
        clean_sheets += step.goals_against == 0
        failed_to_score += step.goals_for == 0
    return TeamTotals(played, won, drawn, lost, goals_for, goals_against, clean_sheets, failed_to_score)


@dataclass(frozen=True, slots=True)
class FormStrip:
    """A team's last few played matches, oldest first. A match with no recoverable score stays in
    the strip as '?' and is left out of the points per game."""

    steps: tuple[FormStep, ...]

    @property
    def letters(self) -> str:
        return "".join(step.outcome for step in self.steps)

    @property
    def totals(self) -> TeamTotals:
        return team_totals(self.steps)

    def describe(self) -> str:
        return self.totals.describe_ppg()


def describe_form_step(step: FormStep) -> str:
    """One match of a form strip in words, for a tooltip: 'Won 1-0 v Leeds United, Sat 1 Aug'."""
    venue = "v" if step.home else "at"
    if step.outcome == UNKNOWN_RESULT:
        return f"Played, score not recoverable (n/a), {venue} {step.opponent}, {_short_date(step.date)}"
    verb = {"W": "Won", "D": "Drew", "L": "Lost"}[step.outcome]
    return f"{verb} {step.goals_for}-{step.goals_against} {venue} {step.opponent}, {_short_date(step.date)}"


def form_strip(steps: Sequence[FormStep], length: int = FORM_LENGTH) -> FormStrip:
    """The last `length` played matches of a team's steps."""
    return FormStrip(tuple(steps[-length:]) if length > 0 else ())


STREAK_WINNING = "winning"
STREAK_UNBEATEN = "unbeaten"
STREAK_WINLESS = "winless"
STREAK_LOSING = "losing"
STREAK_KINDS = (STREAK_WINNING, STREAK_UNBEATEN, STREAK_WINLESS, STREAK_LOSING)
_RUN_RESULTS = {STREAK_WINNING: "W", STREAK_UNBEATEN: "WD", STREAK_WINLESS: "DL", STREAK_LOSING: "L"}
_HEADLINE_ORDER = (STREAK_WINNING, STREAK_LOSING, STREAK_UNBEATEN, STREAK_WINLESS)   # strict runs win ties


@dataclass(frozen=True, slots=True)
class Streak:
    """A run of results of one kind in a row. `ceiling` is how long it would be if every match
    with no recoverable score next to it had continued it; when that is longer, the run is
    incomplete and its length is a minimum."""

    kind: str
    length: int
    ceiling: int
    first: dt.date | None = None
    last: dt.date | None = None

    @property
    def incomplete(self) -> bool:
        return self.ceiling > self.length

    def short(self) -> str:
        """The length for a table cell: '4', '4+' when it may be longer, '?' when not known, and
        '' for no run at all."""
        if self.length == 0:
            return "?" if self.incomplete else ""
        return f"{self.length}+" if self.incomplete else str(self.length)

    def describe(self) -> str:
        if self.length == 0 and self.incomplete:
            return "Not known (no recoverable score)"
        count = f"at least {self.length}" if self.incomplete else str(self.length)
        return {
            STREAK_WINNING: f"Won {count} in a row",
            STREAK_UNBEATEN: f"Unbeaten in {count}",
            STREAK_WINLESS: f"Without a win in {count}",
            STREAK_LOSING: f"Lost {count} in a row",
        }[self.kind]


@dataclass(frozen=True, slots=True)
class Streaks:
    """A team's current and longest runs of each kind, keyed on STREAK_KINDS."""

    current: Mapping[str, Streak]
    longest: Mapping[str, Streak]
    played: int = 0
    last_outcome: str = ""

    @property
    def headline(self) -> Streak | None:
        """The current run to name first: the longest, a winning or losing run before an unbeaten
        or winless one of the same length. None before the first match."""
        if not self.played:
            return None
        return max((self.current[kind] for kind in _HEADLINE_ORDER), key=lambda run: run.length)

    def describe_current(self) -> str:
        """The current run in words: 'Unbeaten in 3', or 'Won the last match' when it is one."""
        run = self.headline
        if run is None:
            return "No matches played"
        if run.length == 1:
            return {"W": "Won", "D": "Drew", "L": "Lost"}[self.last_outcome] + " the last match"
        return run.describe()


def streaks(steps: Sequence[FormStep]) -> Streaks:
    """Current and longest runs. A match with no recoverable score ends a run, and the run is
    marked incomplete, because the save may hide a result that continued it."""
    return Streaks(
        current={kind: _current_run(steps, kind) for kind in STREAK_KINDS},
        longest={kind: _longest_run(steps, kind) for kind in STREAK_KINDS},
        played=len(steps),
        last_outcome=steps[-1].outcome if steps else "",
    )


def _run_streak(steps: Sequence[FormStep], kind: str, start: int, length: int, ceiling: int) -> Streak:
    if not length:
        return Streak(kind, 0, ceiling)
    return Streak(kind, length, ceiling, steps[start].date, steps[start + length - 1].date)


def _current_run(steps: Sequence[FormStep], kind: str) -> Streak:
    """The run up to the latest match. A '?' stops it; the ceiling carries on through any
    further '?' and continuing results."""
    keep = _RUN_RESULTS[kind]
    index = len(steps) - 1
    while index >= 0 and steps[index].outcome in keep:
        index -= 1
    length = len(steps) - 1 - index
    ceiling = length
    while index >= 0 and (steps[index].outcome in keep or steps[index].outcome == UNKNOWN_RESULT):
        ceiling += 1
        index -= 1
    return _run_streak(steps, kind, len(steps) - length, length, ceiling)


def _longest_run(steps: Sequence[FormStep], kind: str) -> Streak:
    """The longest run, the latest of equal ones. Its ceiling is the longest run there would be
    if every '?' continued the runs around it."""
    keep = _RUN_RESULTS[kind]
    best_length = best_start = 0
    known = possible = 0          # the run ending here, and the run if every '?' continued it
    gap = False                   # a '?' sits inside `possible`
    longest_possible = 0
    for index, step in enumerate(steps):
        outcome = step.outcome
        known = known + 1 if outcome in keep else 0
        if known and known >= best_length:
            best_length, best_start = known, index - known + 1
        if outcome in keep or outcome == UNKNOWN_RESULT:
            possible += 1
            gap = gap or outcome == UNKNOWN_RESULT
            if gap:
                longest_possible = max(longest_possible, possible)
        else:
            possible, gap = 0, False
    return _run_streak(steps, kind, best_start, best_length, max(best_length, longest_possible))


@dataclass(frozen=True, slots=True)
class TeamForm:
    """One team's form in a competition and season: every played match, the latest few, its
    totals overall, at home and away, and its runs."""

    team_id: int
    team: str
    steps: tuple[FormStep, ...]
    strip: FormStrip
    totals: TeamTotals
    home: TeamTotals
    away: TeamTotals
    streaks: Streaks


@dataclass(frozen=True, slots=True)
class FormGuide:
    rows: tuple[TeamForm, ...]
    coverage: Coverage

    def describe(self) -> str:
        """The coverage sentence the window shows above the form."""
        cov = self.coverage
        if not cov.played:
            return "No matches played yet, so there is no form to show."
        if not cov.unavailable:
            return f"Form from {_plural(cov.scored, 'played match', 'played matches')}, every one with a score."
        return (f"Form from {_plural(cov.scored, 'scored match', 'scored matches')}. "
                f"{_plural(cov.unavailable, 'played match has', 'played matches have')} no recoverable "
                "score: shown as ?, left out of every total, and a run it touches reads “at least”.")


def form_guide(
    fixtures: Sequence[Fixture],
    labels: Mapping[int, str],
    *,
    order: Sequence[int] = (),
    length: int = FORM_LENGTH,
) -> FormGuide:
    """Every team's form. Teams in `order` (a table's order) come first, the rest in the order of
    a table calculated from the scored matches."""
    by_team: dict[int, list[FormStep]] = {team_id: [] for team_id in teams_in(fixtures)}
    for f in sorted(fixtures, key=_when):
        if f.played:
            by_team[f.home_team_id].append(_step(f, f.home_team_id, labels))
            by_team[f.away_team_id].append(_step(f, f.away_team_id, labels))
    rows = []
    for team_id, steps in by_team.items():
        rows.append(TeamForm(
            team_id=team_id,
            team=labels.get(team_id, f"Team {team_id}"),
            steps=tuple(steps),
            strip=form_strip(steps, length),
            totals=team_totals(steps),
            home=team_totals(step for step in steps if step.home),
            away=team_totals(step for step in steps if not step.home),
            streaks=streaks(steps),
        ))
    rank = {team_id: index for index, team_id in enumerate(order)}
    rows.sort(key=lambda r: (rank.get(r.team_id, len(rank)), -r.totals.points, -r.totals.goal_difference,
                             -r.totals.goals_for, r.team.casefold()))
    return FormGuide(tuple(rows), coverage(fixtures))


@dataclass(frozen=True, slots=True)
class SeasonRecord:
    """A record for a competition and season, shared by every team that holds it. An incomplete
    record could change if the save held the scores it lacks."""

    title: str
    value: str
    teams: tuple[str, ...]
    incomplete: bool = False

    def describe(self, names: int = 3) -> str:
        shown = list(self.teams[:names])
        if len(self.teams) > names:
            shown.append(f"{len(self.teams) - names} more")
        return f"{self.title}: {', '.join(shown)} ({self.value}{'*' if self.incomplete else ''})"


def season_records(guide: FormGuide) -> tuple[SeasonRecord, ...]:
    """Best attack, meanest defence, clean sheets, points per game and the longest runs. A record
    nobody has set yet (no clean sheet, no win) is left out."""
    scored = [r for r in guide.rows if r.totals.scored]
    if not scored:
        return ()
    gaps = any(r.totals.incomplete for r in guide.rows)
    records = []

    def total(title: str, value_of: Callable[[TeamForm], float], best: Callable, text: str = "{}") -> None:
        target = best(value_of(r) for r in scored)
        if best is max and not target:
            return
        holders = tuple(r.team for r in scored if value_of(r) == target)
        records.append(SeasonRecord(title, text.format(target), holders, gaps))

    total("Most goals", lambda r: r.totals.goals_for, max)
    total("Fewest conceded", lambda r: r.totals.goals_against, min)
    total("Most clean sheets", lambda r: r.totals.clean_sheets, max)
    total("Best points per game", lambda r: r.totals.ppg, max, "{:.2f}")
    for kind, title in ((STREAK_WINNING, "Longest winning run"), (STREAK_UNBEATEN, "Longest unbeaten run"),
                        (STREAK_WINLESS, "Longest run without a win"), (STREAK_LOSING, "Longest losing run")):
        runs = [(r.team, r.streaks.longest[kind]) for r in guide.rows]
        target = max(run.length for _, run in runs)
        if not target:
            continue
        holders = tuple(team for team, run in runs if run.length == target)
        # Unsettled if a missing score could make a run longer, or let another team share it.
        unsettled = any(run.ceiling > target or (run.ceiling == target and run.length < target) for _, run in runs)
        records.append(SeasonRecord(title, str(target), holders, unsettled))
    return tuple(records)


# --------------------------------------------------------------------------- positions by matchday


@dataclass(frozen=True, slots=True)
class PositionTrack:
    """One team's place in its group after each matchday of a PositionChart."""

    team_id: int
    team: str
    positions: tuple[int, ...]
    points: tuple[int, ...]
    played: tuple[int, ...]       # scored matches counted by then


@dataclass(frozen=True, slots=True)
class PositionGroup:
    title: str
    tracks: tuple[PositionTrack, ...]    # in the order after the last matchday
    zones: tuple[str, ...]               # the zone of each place, from first down


@dataclass(frozen=True, slots=True)
class PositionChart:
    """League positions after each matchday with a scored match, worked out from the results."""

    matchdays: tuple[int, ...]
    groups: tuple[PositionGroup, ...]
    unscored: int = 0                    # played matches left out: no recoverable score
    skipped: tuple[str, ...] = ()        # clubs left out: no played match has a score
    agreeing: int = 0                    # final places that match the game's stored tables...
    compared: int = 0                    # ...out of this many; 0 when the save stores none
    tie_breaks: tuple[int, ...] = ()     # the competition's tie-break codes, as its rules list them
    zones_note: str = ""                 # where the zone colours come from, as the table says it

    def describe(self) -> str:
        if not self.matchdays:
            return "No matchday has been played yet, so there are no positions to show."
        parts = ["Positions after each matchday, worked out from the results: 3 points for a win, 1 for a "
                 f"draw; {tie_break_order(self.tie_breaks)[1]}. A match played late counts towards its own "
                 "matchday."]
        if self.compared:
            text = (f"After matchday {self.matchdays[-1]} the order matches the game's table for "
                    f"{self.agreeing} of {self.compared} places")
            if self.agreeing < self.compared:
                text += "; the game's further tie-breaks and any points deductions account for the rest"
            parts.append(text + ".")
        else:
            parts.append("The save stores no table for this season to check the order against.")
        if self.unscored:
            parts.append(f"{_plural(self.unscored, 'played match', 'played matches')} with no recoverable "
                         "score left out.")
        if self.skipped:
            parts.append(f"{_plural(len(self.skipped), 'club')} left out because no match they have played has "
                         f"a score: {', '.join(self.skipped)}.")
        return " ".join(parts)


def positions_by_matchday(
    dataset: Dataset,
    competition_id: int,
    season: int | None,
    fixtures: Sequence[Fixture],
    labels: Mapping[int, str],
) -> PositionChart | None:
    """Each team's position after every matchday, from the results of that matchday and the ones
    before it, ranked as calculate_standings ranks them. Teams are ranked within each table the
    game stores for the season (a conference or zone, and the whole league), otherwise all
    together. None for a competition without matchdays, such as a cup."""
    league = [f for f in fixtures if f.round is None and f.round_index is not None]
    if not league:
        return None
    played = [f for f in league if f.played]
    scored = [f for f in played if has_score(f)]
    counted = teams_in(scored)
    skipped = teams_in(played) - counted
    stored = _stored_tables_for(dataset, competition_id, season, fixtures)
    if stored:
        groups = [(f"Table {n} of {len(stored)}" if len(stored) > 1 else "", [r.team_id for r in table.rows])
                  for n, table in enumerate(stored, start=1)]
    else:
        groups = [("", list(teams_in(league)))]
    groups = [(title, [t for t in members if t not in skipped]) for title, members in groups]

    by_matchday: dict[int, list[Fixture]] = defaultdict(list)
    for f in scored:
        by_matchday[f.round_index + 1].append(f)
    matchdays = tuple(sorted(by_matchday))
    tie_breaks = dataset.tie_breaks.get(competition_id, ())
    ranking = tie_break_order(tie_breaks)[0]
    totals: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0])   # points, wins, GF, GA, played
    history: list[dict[int, list[tuple[int, int, int]]]] = [defaultdict(list) for _ in groups]
    for matchday in matchdays:
        for f in by_matchday[matchday]:
            for team_id, goals_for, goals_against in ((f.home_team_id, f.home_goals, f.away_goals),
                                                      (f.away_team_id, f.away_goals, f.home_goals)):
                t = totals[team_id]
                t[0] += WIN_POINTS if goals_for > goals_against else DRAW_POINTS if goals_for == goals_against else 0
                t[1] += goals_for > goals_against
                t[2] += goals_for
                t[3] += goals_against
                t[4] += 1
        for index, (_, members) in enumerate(groups):
            ranked = sorted(members, key=lambda tid: (*_ranking(*totals[tid][:4], ranking),
                                                      labels.get(tid, "").casefold()))
            for position, team_id in enumerate(ranked, start=1):
                history[index][team_id].append((position, totals[team_id][0], totals[team_id][4]))

    rules = dataset.zone_rules.get(competition_id)
    chart_groups = []
    agreeing = compared = 0
    for index, (title, members) in enumerate(groups):
        tracks = sorted(
            (PositionTrack(team_id, labels.get(team_id, f"Team {team_id}"),
                           tuple(p for p, _, _ in steps), tuple(p for _, p, _ in steps),
                           tuple(n for _, _, n in steps))
             for team_id, steps in history[index].items()),
            key=lambda track: track.positions[-1])
        chart_groups.append(PositionGroup(
            title, tuple(tracks), tuple(zone_for_position(p, len(members), rules) for p in range(1, len(members) + 1))))
        if stored and matchdays:
            final = {track.team_id: track.positions[-1] for track in tracks}
            rows = [r for r in stored[index].rows if r.team_id in final]
            compared += len(rows)
            agreeing += sum(1 for r in rows if final[r.team_id] == r.position)
    return PositionChart(
        matchdays=matchdays,
        groups=tuple(chart_groups) if matchdays else (),
        unscored=len(played) - len(scored),
        skipped=tuple(sorted(labels.get(t, f"Team {t}") for t in skipped)),
        agreeing=agreeing,
        compared=compared,
        tie_breaks=tuple(tie_breaks),
        zones_note=_zones_note(rules, {zone for group in chart_groups for zone in group.zones}) if matchdays else "",
    )


def place_sparks(chart: PositionChart | None, last: int = 5) -> dict[int, tuple[int, ...]]:
    """Each team's league place after each of its last `last` scored matches, oldest first: the data behind
    the little line in the Table's Form cell. A matchday the team did not play adds no point, and a team
    with fewer than two matches has no spark. Empty without a chart."""
    sparks: dict[int, tuple[int, ...]] = {}
    for group in chart.groups if chart else ():
        for track in group.tracks:
            before = (0, *track.played)
            places = [place for place, now, was in zip(track.positions, track.played, before) if now > was]
            if len(places) >= 2:
                sparks[track.team_id] = tuple(places[-last:])
    return sparks


# --------------------------------------------------------------------------- season comparison


@dataclass(frozen=True, slots=True)
class SeasonColumn:
    """One season's column in a SeasonComparison: its label and completion state."""

    season: int
    label: str
    finished: bool
    note: str          # "final" or "in progress, X of Y"


@dataclass(frozen=True, slots=True)
class CompareCell:
    """One club's place in one season, as the stored or calculated standings show it."""

    position: int
    points: int
    zone: str = ""


@dataclass(frozen=True, slots=True)
class CompareRow:
    """One club's row in a SeasonComparison: a cell per column, newest first, None if absent."""

    team_id: int
    team: str
    cells: tuple[CompareCell | None, ...]
    delta: int | None = None     # previous season's position minus latest's; None if either absent


@dataclass(frozen=True, slots=True)
class SeasonComparison:
    """Side-by-side standings across the seasons a league has a usable snapshot for.

    Columns are ordered newest season first.
    """

    columns: tuple[SeasonColumn, ...]
    rows: tuple[CompareRow, ...] = ()


def _comparison_rows_for_season(
    dataset: Dataset, competition_id: int, season: int, labels: Mapping[int, str]
):
    """The rows of the group that lists every team for this season's standings, or () when the
    season has no usable snapshot."""
    fixtures = season_fixtures(dataset, competition_id, season)
    snapshot = standings(dataset, competition_id, season, fixtures, labels)
    if not snapshot.groups:
        return ()
    all_teams = {r.team_id for _, rows in snapshot.groups for r in rows}
    for _, rows in sorted(snapshot.groups, key=lambda g: len(g[1]), reverse=True):
        if {r.team_id for r in rows} == all_teams:
            return rows
    return ()


def season_comparison(
    dataset: Dataset,
    competition_id: int,
    labels: Mapping[int, str],
) -> SeasonComparison | None:
    """Side-by-side standings for a league across every season the save holds a usable snapshot
    for. Returns None until at least two seasons yield one."""
    competition = dataset.by_id.get(competition_id)
    if competition is None:
        return None
    columns: list[SeasonColumn] = []
    cells_by_team: dict[int, dict[int, CompareCell]] = defaultdict(dict)
    team_names: dict[int, str] = {}
    for season in sorted(competition.seasons, reverse=True):
        fixtures = season_fixtures(dataset, competition_id, season)
        league = [f for f in fixtures if f.round is None and f.round_index is not None]
        if not league:
            continue
        scored = sum(1 for f in league if f.played and has_score(f))
        if not scored:
            continue
        rows = _comparison_rows_for_season(dataset, competition_id, season, labels)
        if not rows:
            continue
        finished = scored == len(league)
        note = "final" if finished else f"in progress, {scored} of {len(league)}"
        columns.append(SeasonColumn(
            season=season,
            label=season_label(season, fixtures),
            finished=finished,
            note=note,
        ))
        for row in rows:
            cells_by_team[row.team_id][season] = CompareCell(
                position=row.position, points=row.points, zone=row.zone)
            team_names.setdefault(row.team_id, row.team)
    if len(columns) < 2:
        return None
    seasons = [column.season for column in columns]
    rows_out = tuple(
        _compare_row(
            team_id,
            team_names.get(team_id, labels.get(team_id, f"Team {team_id}")),
            tuple(cells_by_team[team_id].get(season) for season in seasons),
        )
        for team_id in cells_by_team
    )
    return SeasonComparison(columns=tuple(columns), rows=rows_out)


def _compare_row(team_id: int, team: str, cells: tuple[CompareCell | None, ...]) -> CompareRow:
    latest, previous = (cells[0], cells[1]) if len(cells) >= 2 else (None, None)
    delta = previous.position - latest.position if latest and previous else None
    return CompareRow(team_id=team_id, team=team, cells=cells, delta=delta)


# --------------------------------------------------------------------------- expected goals

XG_DEAD_ZONE = 0.25      # goals within this of expected goals are neither over nor under
XG_ABOVE, XG_BELOW = "above", "below"


@dataclass(frozen=True, slots=True)
class ExpectedGoals:
    """Both sides' expected goals in one match, from the match report the save kept."""

    home: float
    away: float
    home_non_penalty: float
    away_non_penalty: float

    def describe(self) -> str:
        return f"{self.home:.2f}-{self.away:.2f}"


@dataclass(frozen=True, slots=True)
class XgReport:
    """How the save's match statistics joined to its fixtures."""

    rows: int = 0
    matches: int = 0          # distinct matches the rows describe
    joined: int = 0           # matches joined to exactly one played fixture
    unmatched: int = 0        # matches that fit no played fixture in the save
    rejected: int = 0         # ambiguous, or not one home and one away row with readable values
    failed: str = ""          # why the statistics could not be read at all

    def describe(self) -> str:
        if self.failed:
            return f"Expected goals could not be read from this save ({self.failed})."
        text = (f"Expected goals: {self.rows:,} match statistics rows for {self.matches:,} matches, "
                f"{self.joined:,} of them joined to a played fixture")
        if self.unmatched:
            text += f"; {self.unmatched:,} fit no played fixture"
        if self.rejected:
            text += f"; {self.rejected:,} rejected as ambiguous or unreadable"
        return text + "."


@dataclass(frozen=True, slots=True)
class XgCoverage:
    played: int
    covered: int              # played matches with expected goals
    state: str = ""           # "", or "pending" before the statistics are read, or "failed"

    def describe(self) -> str:
        if self.state == "pending":
            return "Expected goals have not been read yet."
        if self.state == "failed":
            return "Expected goals could not be read from this save (see Save details & warnings)."
        if not self.played:
            return "No matches played yet, so no expected goals."
        text = f"Expected goals for {self.covered} of {self.played} played matches"
        if self.covered < self.played:
            text += f"; the save holds no usable match report for the other {self.played - self.covered}"
        return text + "."


@dataclass(frozen=True, slots=True)
class XgRow:
    """A team's expected goals over the matches that have them and a score, beside its goals in
    those same matches. With no such match the figures are None, never zero."""

    team_id: int
    team: str
    played: int
    covered: int
    xg_for: float | None
    xg_against: float | None
    goals_for: int | None
    goals_against: int | None

    @property
    def xg_difference(self) -> float | None:
        return None if self.xg_for is None else self.xg_for - self.xg_against

    @property
    def finishing(self) -> float | None:
        """Goals scored above (+) or below (-) expected goals."""
        return None if self.xg_for is None else self.goals_for - self.xg_for

    @property
    def prevention(self) -> float | None:
        """Goals conceded below (+) or above (-) the expected goals against: positive is good."""
        return None if self.xg_against is None else self.xg_against - self.goals_against


def fixture_key(f: Fixture) -> tuple:
    """How a match's statistics name it: competition, home team, away team and date."""
    return (f.competition_id, f.home_team_id, f.away_team_id, f.date)


def link_expected_goals(stats: Iterable, fixtures: Mapping[int, Sequence[Fixture]]) -> tuple[dict, XgReport]:
    """Join match statistics rows to fixtures on fmsave's key: competition, home team, away team
    and date. A match joins only when its key fits exactly one fixture, that fixture was played,
    and its rows are one home and one away row for those teams with readable expected goals.
    Anything else is counted, never guessed at or averaged."""
    candidates: dict[tuple, list[Fixture]] = defaultdict(list)
    for items in fixtures.values():
        for f in items:
            candidates[fixture_key(f)].append(f)
    by_match: dict[tuple, list] = defaultdict(list)
    rows = 0
    for row in stats:
        rows += 1
        by_match[(row.competition_id, row.home_team_id, row.away_team_id, row.date)].append(row)

    expected: dict[tuple, ExpectedGoals] = {}
    unmatched = rejected = 0
    for key, items in by_match.items():
        found = candidates.get(key, [])
        if len(found) > 1:
            rejected += 1
            continue
        if not found or not found[0].played:
            unmatched += 1
            continue
        home = [r for r in items if r.is_home and r.team_id == key[1]]
        away = [r for r in items if not r.is_home and r.team_id == key[2]]
        if len(items) != 2 or len(home) != 1 or len(away) != 1:
            rejected += 1
            continue
        values = (home[0].expected_goals, away[0].expected_goals,
                  home[0].non_penalty_expected_goals, away[0].non_penalty_expected_goals)
        if not all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in values):
            rejected += 1
            continue
        expected[key] = ExpectedGoals(*values)
    return expected, XgReport(rows, len(by_match), len(expected), unmatched, rejected)


def with_expected_goals(dataset: Dataset, stats: Iterable | None, failure: str = "") -> Dataset:
    """The Dataset with the save's match statistics joined to its fixtures. `stats` is None when
    they could not be read, and `failure` says why; nothing else in the Dataset changes."""
    if stats is None:
        return replace(dataset, expected_goals={}, match_reports={}, xg_report=XgReport(failed=failure or "not read"))
    rows = list(stats)
    expected, report = link_expected_goals(rows, dataset.fixtures)
    return replace(dataset, expected_goals=expected, match_reports=link_match_stats(rows, dataset.fixtures),
                   xg_report=report)


@dataclass(frozen=True, slots=True)
class SideStats:
    """One side's figures for a match, as the save's match report holds them. A figure the report does not
    hold, or holds unreadably, is None: it is never shown as 0."""

    shots: int | None = None
    shots_on_target: int | None = None
    possession_percent: float | None = None
    passes_attempted: int | None = None
    passes_completed: int | None = None
    corners: int | None = None
    fouls: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    expected_goals: float | None = None


@dataclass(frozen=True, slots=True)
class MatchStats:
    home: SideStats
    away: SideStats


@dataclass(frozen=True, slots=True)
class StatLine:
    """One row of the match statistics as text: a label and each side's figure."""

    label: str
    home: str
    away: str


def _clean(value) -> float | int | None:
    """The figure if it is a finite number of at least zero, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _side_stats(row) -> SideStats:
    return SideStats(
        shots=_clean(row.shots), shots_on_target=_clean(row.shots_on_target),
        possession_percent=_clean(row.possession_percent), passes_attempted=_clean(row.passes_attempted),
        passes_completed=_clean(row.passes_completed), corners=_clean(row.corners), fouls=_clean(row.fouls_made),
        yellow_cards=_clean(row.yellow_cards), red_cards=_clean(row.red_cards),
        expected_goals=_clean(row.expected_goals))


def link_match_stats(stats: Iterable, fixtures: Mapping[int, Sequence[Fixture]]) -> dict[tuple, MatchStats]:
    """Join match report rows to fixtures as link_expected_goals does: a match joins only when its key
    fits exactly one played fixture and its rows are one home and one away row for those teams. Unlike
    expected goals it does not need every figure to be readable; the ones that are not are None."""
    candidates: dict[tuple, list[Fixture]] = defaultdict(list)
    for items in fixtures.values():
        for f in items:
            candidates[fixture_key(f)].append(f)
    by_match: dict[tuple, list] = defaultdict(list)
    for row in stats:
        by_match[(row.competition_id, row.home_team_id, row.away_team_id, row.date)].append(row)
    reports: dict[tuple, MatchStats] = {}
    for key, items in by_match.items():
        found = candidates.get(key, [])
        if len(found) != 1 or not found[0].played or len(items) != 2:
            continue
        home = [r for r in items if r.is_home and r.team_id == key[1]]
        away = [r for r in items if not r.is_home and r.team_id == key[2]]
        if len(home) == 1 and len(away) == 1:
            reports[key] = MatchStats(_side_stats(home[0]), _side_stats(away[0]))
    return reports


def match_stats_for(dataset: Dataset, f: Fixture) -> MatchStats | None:
    """A match's statistics, or None when the save holds no usable report for it."""
    return dataset.match_reports.get(fixture_key(f))


def _count_text(value) -> str:
    return "—" if value is None else str(int(value))


def _passes_text(side: SideStats) -> str:
    attempted, completed = side.passes_attempted, side.passes_completed
    if attempted and completed is not None:
        return f"{int(completed)} of {int(attempted)} ({round(100 * completed / attempted)}%)"
    if completed:
        return str(int(completed))
    if attempted:
        return str(int(attempted))
    return "—"


def describe_match_stats(stats: MatchStats) -> tuple[StatLine, ...]:
    """The match statistics as rows of text, in the order the inspector shows them; '—' for a figure
    the save does not hold."""
    home, away = stats.home, stats.away

    def line(label: str, text) -> StatLine:
        return StatLine(label, text(home), text(away))

    return (
        line("xG", lambda s: "—" if s.expected_goals is None else f"{s.expected_goals:.2f}"),
        line("Shots", lambda s: _count_text(s.shots)),
        line("On target", lambda s: _count_text(s.shots_on_target)),
        line("Possession", lambda s: "—" if s.possession_percent is None else f"{round(s.possession_percent)}%"),
        line("Passes", _passes_text),
        line("Corners", lambda s: _count_text(s.corners)),
        line("Fouls", lambda s: _count_text(s.fouls)),
        line("Yellow cards", lambda s: _count_text(s.yellow_cards)),
        line("Red cards", lambda s: _count_text(s.red_cards)),
    )


@dataclass(frozen=True, slots=True)
class Tie:
    """Two meetings of the same pair in one round, home and away swapped. Side A is the first leg's home team."""

    round_index: int | None
    team_a: int
    team_b: int
    first: Fixture
    second: Fixture

    @property
    def aggregate(self) -> tuple[int, int] | None:
        """Goals (A, B) over both legs; None unless both were played with a recoverable score."""
        if not (has_score(self.first) and has_score(self.second)):
            return None
        return (self.first.home_goals + self.second.away_goals, self.first.away_goals + self.second.home_goals)


@dataclass(frozen=True, slots=True)
class CupTie:
    """A pairing in one round of a knockout competition: one match, a replay, or two legs. `winner` is the side
    that went through, or None when it cannot be told; `how` says on what evidence: 'score' (a single match or
    the replay), 'aggregate' (two legs) or 'next round' (the side appears in a later round)."""

    round_index: int
    team_a: int
    team_b: int
    fixtures: tuple[Fixture, ...]
    winner: int | None
    how: str


@dataclass(frozen=True, slots=True)
class CupRound:
    index: int
    name: str
    ties: tuple[CupTie, ...]
    knockout: bool = True          # False for a group or league phase, where a side plays more than twice


def cup_rounds(fixtures: Iterable[Fixture], labels: Mapping[int, str]) -> tuple[CupRound, ...]:
    """The fixtures as rounds of ties, in round-index order."""
    by_round: dict[int, dict[frozenset, list[Fixture]]] = defaultdict(lambda: defaultdict(list))
    for f in fixtures:
        if f.round_index is not None:
            by_round[f.round_index][frozenset((f.home_team_id, f.away_team_id))].append(f)
    appears_after: dict[int, set[int]] = {}          # round index -> teams playing in any later round
    seen: set[int] = set()
    for index in sorted(by_round, reverse=True):
        appears_after[index] = set(seen)
        for legs in by_round[index].values():
            for f in legs:
                seen.update((f.home_team_id, f.away_team_id))
    rounds = []
    for index in sorted(by_round):
        ties = []
        for legs in by_round[index].values():
            legs = sorted(legs, key=_when)
            winner, how = None, ""
            decider = legs[-1] if len(legs) == 1 or (len(legs) == 2 and is_replay(*legs)) else None
            if decider is not None and has_score(decider) and decider.home_goals != decider.away_goals:
                f = decider
                winner, how = (f.home_team_id if f.home_goals > f.away_goals else f.away_team_id), "score"
            if len(legs) == 2 and decider is None:                     # two legs: the aggregate decides
                goals = Tie(index, legs[0].home_team_id, legs[0].away_team_id, legs[0], legs[1]).aggregate
                if goals is not None and goals[0] != goals[1]:
                    winner = legs[0].home_team_id if goals[0] > goals[1] else legs[0].away_team_id
                    how = "aggregate"
            if winner is None:
                went_on = [t for t in (legs[0].home_team_id, legs[0].away_team_id) if t in appears_after[index]]
                if len(went_on) == 1:
                    winner, how = went_on[0], "next round"
            ties.append(CupTie(index, legs[0].home_team_id, legs[0].away_team_id, tuple(legs), winner, how))
        named = round_text(by_round[index][next(iter(by_round[index]))][0])
        if named and not named.startswith("Md "):
            name = named                                      # a name the save confirms
        elif len(ties) >= 2 and len(ties) & (len(ties) - 1) == 0:
            name = f"Last {2 * len(ties)}"                      # a power of two: named by how many sides are left
        else:
            name = f"Round {index + 1}"
        plays = Counter(t for legs in by_round[index].values() for f in legs for t in (f.home_team_id, f.away_team_id))
        rounds.append(CupRound(index, name, tuple(sorted(ties, key=lambda t: _when(t.fixtures[0]))),
                               knockout=max(plays.values()) <= 2))
    return tuple(rounds)


TREE_ROUNDS = 4          # the bracket draws at most this many rounds: the final back to the last 16


def bracket_split(rounds: Sequence[CupRound]) -> tuple[tuple[CupRound, ...], tuple[CupRound, ...]]:
    """(earlier rounds, the rounds to draw as a tree). The tree is the final, which must be a single tie, and
    the knockout rounds before it while each has twice the ties of the next, up to TREE_ROUNDS. A competition
    that does not end in a single final has no tree."""
    if not rounds or len(rounds[-1].ties) != 1 or not rounds[-1].knockout:
        return tuple(rounds), ()
    tree = [rounds[-1]]
    for earlier in reversed(rounds[:-1]):
        if len(tree) == TREE_ROUNDS or not earlier.knockout or len(earlier.ties) != 2 * len(tree[0].ties):
            break
        tree.insert(0, earlier)
    return tuple(rounds[:len(rounds) - len(tree)]), tuple(tree)


REPLAY_DAYS = 4          # a replay follows a drawn match within this many days; a second leg comes later


def is_replay(first: Fixture, second: Fixture) -> bool:
    """Whether a pair's second meeting in a round is a replay of a drawn first match rather than a second leg.
    Measured on a save with 26 replays (every one followed a draw within four days) and 214 second legs (none
    within four days of the first leg)."""
    drawn = first.played and has_score(first) and first.home_goals == first.away_goals
    if not (drawn and first.date and second.date):
        return False
    return (second.date - first.date).days <= REPLAY_DAYS


def two_legged_ties(fixtures: Iterable[Fixture], labels: Mapping[int, str]) -> tuple[Tie, ...]:
    """The ties among these fixtures, by round then date."""
    by_round: dict[int | None, dict[frozenset, list[Fixture]]] = defaultdict(lambda: defaultdict(list))
    for f in fixtures:
        by_round[f.round_index][frozenset((f.home_team_id, f.away_team_id))].append(f)
    ties = []
    for round_index, pairs in by_round.items():
        for legs in pairs.values():
            if len(legs) != 2:
                continue
            first, second = sorted(legs, key=_when)
            if is_replay(first, second):
                continue
            ties.append(Tie(round_index, first.home_team_id, first.away_team_id, first, second))
    return tuple(sorted(ties, key=lambda t: (t.round_index is None, t.round_index or 0, _when(t.first))))


def tie_round_text(tie: Tie) -> str:
    """A tie's round: its name where the save confirms one, otherwise 'Round N' from the stored round index."""
    name = round_text(tie.first)
    if name and not name.startswith("Md "):
        return name
    return f"Round {tie.round_index + 1}" if tie.round_index is not None else ""


def tie_outcome(tie: Tie, labels: Mapping[int, str]) -> str:
    """Where a tie stands, in words."""
    a, b = (labels.get(tie.team_a, f"Team {tie.team_a}"), labels.get(tie.team_b, f"Team {tie.team_b}"))
    for leg, name in ((tie.first, "First"), (tie.second, "Second")):
        if not leg.played:
            return f"{name} leg to play"
    goals = tie.aggregate
    if goals is None:
        return "Not known: a leg has no recoverable score (n/a)"
    if goals[0] == goals[1]:
        return "Level on aggregate (the save stores no away goals, extra time or penalties)"
    return f"{a if goals[0] > goals[1] else b} go through"


def meetings(fixtures: Iterable[Fixture], team_a: int, team_b: int) -> tuple[Fixture, ...]:
    """The matches between two teams, either way round, in date order."""
    pair = {team_a, team_b}
    return tuple(sorted((f for f in fixtures if {f.home_team_id, f.away_team_id} == pair), key=_when))


@dataclass(frozen=True, slots=True)
class MeetingGroup:
    """All matches between two teams in one competition and season, in date order."""

    competition_id: int
    season: int | None
    fixtures: tuple[Fixture, ...]


def all_meetings(dataset: Dataset, team_a: int, team_b: int) -> tuple[MeetingGroup, ...]:
    """Every match between two teams across all competitions and seasons in the save.

    Groups by (competition_id, season), sorted by season then competition id.
    """
    pair = {team_a, team_b}
    groups: dict[tuple[int, int | None], list[Fixture]] = defaultdict(list)
    for comp_id, fixtures in dataset.fixtures.items():
        for f in fixtures:
            if {f.home_team_id, f.away_team_id} == pair:
                groups[(comp_id, season_key(f))].append(f)
    result = []
    for (comp_id, season), group_fixtures in groups.items():
        group_fixtures.sort(key=_when)
        result.append(MeetingGroup(comp_id, season, tuple(group_fixtures)))
    result.sort(key=lambda g: (g.season is None, g.season or 0, g.competition_id))
    return tuple(result)


def next_match(fixtures: Iterable[Fixture], team_id: int) -> Fixture | None:
    """The team's earliest match still to play, or None."""
    coming = [f for f in fixtures if not f.played and team_id in (f.home_team_id, f.away_team_id)]
    return min(coming, key=_when) if coming else None


def xg_for(dataset: Dataset, f: Fixture) -> ExpectedGoals | None:
    """A match's expected goals, or None when the save holds no usable report for it."""
    return dataset.expected_goals.get(fixture_key(f))


def xg_coverage(dataset: Dataset, fixtures: Iterable[Fixture]) -> XgCoverage:
    report = dataset.xg_report
    state = "pending" if report is None else "failed" if report.failed else ""
    played = [f for f in fixtures if f.played]
    return XgCoverage(len(played), sum(1 for f in played if fixture_key(f) in dataset.expected_goals), state)


def xg_scoreline(f: Fixture, xg: ExpectedGoals, labels: Mapping[int, str]) -> str:
    """'Hull City [1.82] 2-1 [0.45] Leeds United': each side's expected goals beside the score."""
    home = labels.get(f.home_team_id, f"Team {f.home_team_id}")
    away = labels.get(f.away_team_id, f"Team {f.away_team_id}")
    return f"{home} [{xg.home:.2f}] {score_text(f)} [{xg.away:.2f}] {away}"


def xg_table(
    dataset: Dataset,
    fixtures: Sequence[Fixture],
    labels: Mapping[int, str],
    *,
    order: Sequence[int] = (),
) -> tuple[XgRow, ...]:
    """Every team's expected goals for and against, over the played matches that have them and a
    score. Teams in `order` come first, then the best expected-goal difference; teams with no
    report go last."""
    totals = {team_id: [0, 0, 0.0, 0.0, 0, 0] for team_id in teams_in(fixtures)}   # P, covered, xGF, xGA, GF, GA
    for f in fixtures:
        if not f.played:
            continue
        xg = xg_for(dataset, f)
        for team_id, home in ((f.home_team_id, True), (f.away_team_id, False)):
            t = totals[team_id]
            t[0] += 1
            if xg is None or not has_score(f):
                continue
            t[1] += 1
            t[2] += xg.home if home else xg.away
            t[3] += xg.away if home else xg.home
            t[4] += f.home_goals if home else f.away_goals
            t[5] += f.away_goals if home else f.home_goals
    rows = [XgRow(team_id, labels.get(team_id, f"Team {team_id}"), *t) if t[1] else
            XgRow(team_id, labels.get(team_id, f"Team {team_id}"), t[0], 0, None, None, None, None)
            for team_id, t in totals.items()]
    rank = {team_id: index for index, team_id in enumerate(order)}
    rows.sort(key=lambda r: (rank.get(r.team_id, len(rank)), r.covered == 0, -(r.xg_difference or 0.0),
                             r.team.casefold()))
    return tuple(rows)


def xg_tint(value: float, matches: int = 1) -> str:
    """XG_ABOVE or XG_BELOW when goals beat or fall short of expected goals by more than the dead
    zone a match, else ''. A season's difference is judged per match, so noise does not show."""
    per_match = value / max(matches, 1)
    if per_match > XG_DEAD_ZONE:
        return XG_ABOVE
    if per_match < -XG_DEAD_ZONE:
        return XG_BELOW
    return ""


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


# --------------------------------------------------------------------------- before a kick-off

# A match counts as over this long after it kicked off. The figure is only used to leave a result out until it
# was certainly in, so a table or a form strip never uses a match that may still have been on.
MATCH_LENGTH = dt.timedelta(hours=2)
FORM_LEAGUE, FORM_ALL = "league", "all"
_FORM_SCOPE_LABELS = {FORM_LEAGUE: "league only", FORM_ALL: "all competitions"}


@dataclass(frozen=True, slots=True)
class Cutoff:
    """The moment a piece of pre-match context is taken at: a match's kick-off. With no kick-off time stored the
    context is a prior-day snapshot (every result to the end of the day before); with no date, nothing is counted."""

    date: dt.date | None
    time: dt.time | None

    @property
    def exact(self) -> bool:
        return self.date is not None and self.time is not None

    def label(self) -> str:
        if self.date is None:
            return "Date not set: no earlier results can be counted"
        if self.time is not None:
            return f"Before kick-off, {_short_date(self.date)} {self.time:%H:%M}"
        eve = self.date - dt.timedelta(days=1)
        return f"Prior-day snapshot: results to the end of {_short_date(eve)} (no kick-off time stored)"


def cutoff_for(f: Fixture) -> Cutoff:
    return Cutoff(f.date, f.kick_off_time)


def played_before(fixtures: Iterable[Fixture], target: Fixture) -> tuple[Fixture, ...]:
    """The played matches that were certainly over before `target` kicked off, so nothing the match itself or
    anything after it decided is used. A match on an earlier day counts. A match on the same day counts only when
    both kick-off times are stored and it kicked off MATCH_LENGTH or more earlier; with no time on the target,
    only earlier days count (a prior-day snapshot). An undated match never counts, and nothing precedes an
    undated target."""
    if target.date is None:
        return ()
    start = dt.datetime.combine(target.date, target.kick_off_time) if target.kick_off_time is not None else None
    found: list[Fixture] = []
    for g in fixtures:
        if g is target or not g.played or g.date is None:
            continue
        if g.date < target.date:
            found.append(g)
        elif (start is not None and g.date == target.date and g.kick_off_time is not None
              and dt.datetime.combine(g.date, g.kick_off_time) + MATCH_LENGTH <= start):
            found.append(g)
    return tuple(found)


def standings_before(
    fixtures: Sequence[Fixture],
    labels: Mapping[int, str],
    target: Fixture,
    *,
    tie_breaks: Sequence[int] = (),
    form_length: int = 6,
) -> tuple[StandingRow, ...]:
    """The table as it stood before `target` kicked off, worked out from the results (see played_before). Every
    club still appears; a match not counted yet is a game in hand. Calculated, never the game's stored table."""
    fixtures = list(fixtures)
    counted = {id(g) for g in played_before(fixtures, target)}
    by_then = [g if id(g) in counted else replace(g, played=False) for g in fixtures]
    return calculate_standings(by_then, labels, _forms(by_then, length=form_length), tie_breaks=tie_breaks)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


@dataclass(frozen=True, slots=True)
class RankBefore:
    """A team's calculated place in a league before a match: not the game's stored table, so its tie-break and
    deduction caveats apply."""

    position: int
    of: int
    points: int
    played: int
    cutoff: Cutoff
    unscored: int          # matches counted that were played with no recoverable score, and so left out of the table

    def label(self) -> str:
        text = f"{_ordinal(self.position)} of {self.of}, calculated from results. {self.cutoff.label()}"
        if self.unscored:
            text += f". {_plural(self.unscored, 'match', 'matches')} played with no score left out"
        return text


def rank_before(
    fixtures: Sequence[Fixture],
    labels: Mapping[int, str],
    target: Fixture,
    team_id: int,
    *,
    tie_breaks: Sequence[int] = (),
) -> RankBefore | None:
    """The team's place in the league `fixtures` hold just before `target` kicked off, or None when the team is
    not in them (a cup-only side, or one the save cannot resolve)."""
    fixtures = list(fixtures)
    if team_id not in teams_in(fixtures):
        return None
    rows = standings_before(fixtures, labels, target, tie_breaks=tie_breaks)
    row = next(r for r in rows if r.team_id == team_id)
    unscored = sum(1 for g in played_before(fixtures, target) if not has_score(g))
    return RankBefore(row.position, len(rows), row.points, row.played, cutoff_for(target), unscored)


def club_steps(fixtures: Iterable[Fixture], team_ids: Iterable[int], labels: Mapping[int, str]) -> tuple[FormStep, ...]:
    """Every played match of a club's teams, oldest first, seen from the club's side. A match between two of its own
    teams has no single side and is left out."""
    ids = set(team_ids)
    steps = []
    for f in sorted(fixtures, key=_when):
        home, away = f.home_team_id in ids, f.away_team_id in ids
        if f.played and home != away:
            steps.append(_step(f, f.home_team_id if home else f.away_team_id, labels))
    return tuple(steps)


@dataclass(frozen=True, slots=True)
class FormBefore:
    """A club's last matches before a kick-off, with the scope it covers named: its league only, or every
    competition."""

    scope: str
    strip: FormStrip
    cutoff: Cutoff

    @property
    def scope_label(self) -> str:
        return _FORM_SCOPE_LABELS[self.scope]

    def label(self) -> str:
        return f"Form ({self.scope_label}). {self.cutoff.label()}"


def form_before(
    fixtures: Iterable[Fixture],
    team_ids: Iterable[int],
    target: Fixture,
    labels: Mapping[int, str],
    *,
    scope: str,
    length: int = FORM_LENGTH,
) -> FormBefore:
    """The club's last `length` matches among `fixtures` that were over before `target` kicked off. The caller
    chooses the fixtures and names the scope: one league's, or every competition's."""
    before = played_before(fixtures, target)
    return FormBefore(scope, form_strip(club_steps(before, team_ids, labels), length), cutoff_for(target))


# --------------------------------------------------------------------------- a club's schedule

# Where a match falls against the save's own date (never the computer's). "Overdue" is an unplayed match dated
# before the save's date: the save does not say whether it was postponed or simply not yet rearranged.
WHEN_PLAYED, WHEN_TODAY, WHEN_UPCOMING = "played", "today", "upcoming"
WHEN_OVERDUE, WHEN_UNDATED, WHEN_UNKNOWN = "overdue", "undated", "unknown"


def match_timing(f: Fixture, today: dt.date | None) -> tuple[str, int | None]:
    """(where the match falls, whole days from the save's date: positive to come, negative overdue)."""
    if f.played:
        return WHEN_PLAYED, None
    if f.date is None:
        return WHEN_UNDATED, None
    if today is None:
        return WHEN_UNKNOWN, None
    days = (f.date - today).days
    return (WHEN_TODAY if days == 0 else WHEN_UPCOMING if days > 0 else WHEN_OVERDUE), days


def countdown_text(when: str, days: int | None) -> str:
    """A match's place against the save's date, in words."""
    if when == WHEN_TODAY:
        return "Today"
    if when == WHEN_UPCOMING and days is not None:
        return "Tomorrow" if days == 1 else f"In {days} days"
    if when == WHEN_OVERDUE and days is not None:
        return (f"Overdue by {_plural(-days, 'day')}: not played in the save "
                "(postponed or not yet rearranged)")
    if when == WHEN_UNDATED:
        return "Date not set"
    if when == WHEN_UNKNOWN:
        return "The save's date is unknown"
    return ""


@dataclass(frozen=True, slots=True)
class ScheduleItem:
    """One match of a followed club, seen from the club's side. `venue` is H or A for the nominal home or away
    side, and N when the ground is known to be neutral; `neutral` keeps unknown (None) apart from False."""

    ref: FixtureRef
    fixture: Fixture
    competition_id: int | None
    team_id: int
    opponent_id: int
    opponent: str
    home: bool
    venue: str
    neutral: bool | None
    outcome: str | None        # W, D, L, or ? for a played match with no recoverable score; None until played
    score: str                 # from the club's side ("2-1"), "n/a" for a played match with no score, "" until played
    when: str
    days: int | None
    xg: ExpectedGoals | None
    xg_state: str              # known, pending or unavailable for a played match; "" for one not yet played
    opponent_club: str | None = None   # the opponent's club as the save names it; None when it cannot be resolved

    @property
    def played(self) -> bool:
        return self.fixture.played


@dataclass(frozen=True, slots=True)
class ScheduleCompetition:
    competition_id: int | None
    played: int
    total: int


@dataclass(frozen=True, slots=True)
class Schedule:
    """A followed club's matches in one season, across competitions, in date order with undated matches last."""

    club: FollowedClub
    season: int | None
    season_label: str
    today: dt.date | None
    items: tuple[ScheduleItem, ...]
    competitions: tuple[ScheduleCompetition, ...]      # in the order each first appears

    @property
    def first_upcoming(self) -> int | None:
        """Index of the first match today or still to come by the save's date, or None."""
        return next((i for i, item in enumerate(self.items) if item.when in (WHEN_TODAY, WHEN_UPCOMING)), None)

    def describe(self) -> str:
        played = [i for i in self.items if i.played]
        to_play = len(self.items) - len(played)
        parts = [_plural(len(self.items), "match", "matches"), f"{len(played)} played"]
        unscored = sum(1 for i in played if i.outcome == UNKNOWN_RESULT)
        if unscored:
            parts.append(f"{unscored} played with no recoverable score")
        text = f"{to_play} to play"
        notes = [f"{n} {name}" for name in (WHEN_OVERDUE, WHEN_UNDATED)
                 if (n := sum(1 for i in self.items if i.when == name))]
        if any(i.when == WHEN_UNKNOWN for i in self.items):
            notes.append("the save's date is unknown")
        parts.append(text + (f" ({', '.join(notes)})" if notes else ""))
        return " · ".join(parts)


def club_fixtures(dataset: Dataset, team_ids: Iterable[int]) -> tuple[Fixture, ...]:
    """Every fixture, in every competition and season, that one of the teams plays in."""
    ids = set(team_ids)
    return tuple(f for items in dataset.fixtures.values() for f in items
                 if f.home_team_id in ids or f.away_team_id in ids)


def club_season(fixtures: Iterable[Fixture]) -> int | None:
    """The latest season with a played match, else the first season still to come."""
    keys = [(f.played, season_key(f)) for f in fixtures if season_key(f) is not None]
    played = [k for was, k in keys if was]
    return max(played) if played else min((k for _, k in keys), default=None)


def xg_state_for(dataset: Dataset, f: Fixture) -> str:
    if not f.played:
        return ""
    report = dataset.xg_report
    if report is None:
        return STATE_PENDING
    if report.failed:
        return STATE_UNAVAILABLE
    return STATE_KNOWN if fixture_key(f) in dataset.expected_goals else STATE_UNAVAILABLE


def _side_name(name: str | None, slot: int | None, team_id: int) -> str:
    label = name or f"Team {team_id}"
    return f"{label} (team {slot + 1})" if name and slot else label


def _schedule_item(dataset: Dataset, f: Fixture, ref: FixtureRef, ids: frozenset[int],
                   today: dt.date | None) -> ScheduleItem:
    home = f.home_team_id in ids
    own, other = (f.home_team_id, f.away_team_id) if home else (f.away_team_id, f.home_team_id)
    opponent = (_side_name(f.away_club_name, f.away_team_slot, other) if home
                else _side_name(f.home_club_name, f.home_team_slot, other))
    if not f.played:
        outcome, score = None, ""
    elif not has_score(f):
        outcome, score = UNKNOWN_RESULT, "n/a"
    else:
        scored, conceded = (f.home_goals, f.away_goals) if home else (f.away_goals, f.home_goals)
        outcome = "W" if scored > conceded else "L" if scored < conceded else "D"
        score = f"{scored}-{conceded}"
    when, days = match_timing(f, today)
    state = xg_state_for(dataset, f)
    return ScheduleItem(
        ref=ref, fixture=f, competition_id=f.competition_id, team_id=own, opponent_id=other, opponent=opponent,
        home=home, venue="N" if f.is_neutral_venue else "H" if home else "A", neutral=f.is_neutral_venue,
        outcome=outcome, score=score, when=when, days=days,
        xg=dataset.expected_goals.get(fixture_key(f)) if state == STATE_KNOWN else None, xg_state=state,
        opponent_club=f.away_club_name if home else f.home_club_name)


def club_schedule(
    dataset: Dataset,
    followed: FollowedClub,
    season: int | None = None,
    *,
    competition_id: int | None = None,
    fixtures: Sequence[Fixture] | None = None,
) -> Schedule:
    """The followed club's matches for a season (by default its latest played one) across every competition, or
    in one competition. `fixtures` may hold club_fixtures' answer, so a window can compute it once per save and
    club. Countdowns use the save's date."""
    ids = followed_team_ids(dataset, followed)
    mine = club_fixtures(dataset, ids) if fixtures is None else tuple(fixtures)
    if season is None:
        season = club_season(mine)
    chosen = sorted((f for f in mine if season_key(f) == season),
                    key=lambda f: (_when(f), f.competition_id or 0))
    refs = fixture_refs(chosen)
    today = dataset.info.game_date
    items = tuple(_schedule_item(dataset, f, ref, ids, today) for f, ref in zip(chosen, refs)
                  if competition_id is None or f.competition_id == competition_id)
    counts: dict[int | None, list[int]] = {}
    for item in items:
        counts.setdefault(item.competition_id, [0, 0])
        counts[item.competition_id][1] += 1
        counts[item.competition_id][0] += item.played
    return Schedule(followed, season, season_label(season, chosen) if chosen else "No season", today, items,
                    tuple(ScheduleCompetition(cid, played, total) for cid, (played, total) in counts.items()))


# --------------------------------------------------------------------------- manager snapshot


FORM_MAX = 5


@dataclass(frozen=True, slots=True)
class ManagerSnapshot:
    """A concise summary of the followed club's current state, consumed by the club overview hub.

    Computed once from the dataset and followed-club choice; never recalculated in a Tk callback.
    Every field is None or empty rather than estimated when the data is not in the save.
    """

    followed: FollowedClub
    managed: bool
    manager_name: str | None
    next_item: ScheduleItem | None
    next_scope_label: str
    form: tuple[ScheduleItem, ...]
    rank_before_next: RankBefore | None


def manager_snapshot(dataset: Dataset, followed: FollowedClub, *, max_form: int = FORM_MAX) -> ManagerSnapshot:
    """Build a ManagerSnapshot for the followed club from an already-built dataset."""
    info = dataset.info
    managed = info.managed_club_uid is not None and info.managed_club_uid == followed.club_uid
    manager_name = info.managed_manager_name if managed else None

    ids = followed_team_ids(dataset, followed)
    all_fx = club_fixtures(dataset, ids)
    season = club_season(all_fx)
    today = info.game_date

    items = tuple(_schedule_item(dataset, f, ref, ids, today)
                  for f, ref in zip(
                      sorted((f for f in all_fx if season_key(f) == season),
                             key=lambda f: (_when(f), f.competition_id or 0)),
                      fixture_refs(sorted((f for f in all_fx if season_key(f) == season),
                                          key=lambda f: (_when(f), f.competition_id or 0)))))

    played = tuple(i for i in items if i.played)
    form = played[-max_form:]

    upcoming = [i for i in items if i.when in (WHEN_TODAY, WHEN_UPCOMING, WHEN_OVERDUE)]
    next_item = upcoming[0] if upcoming else None

    if next_item is not None:
        next_scope_label = (f"Competition {next_item.competition_id}"
                            if next_item.competition_id else "All competitions")
    else:
        next_scope_label = ""

    rank = None
    if next_item is not None and _is_league(next_item.fixture):
        league = [g for g in dataset.fixtures_for(next_item.competition_id) if season_key(g) == season]
        rank = rank_before(league, team_labels(league), next_item.fixture, next_item.team_id,
                           tie_breaks=dataset.tie_breaks.get(next_item.competition_id, ()))

    return ManagerSnapshot(followed=followed, managed=managed, manager_name=manager_name,
                           next_item=next_item, next_scope_label=next_scope_label,
                           form=form, rank_before_next=rank)


# --------------------------------------------------------------------------- the Hub's matchday stepper

HUB_EXCERPT = 2            # table rows shown above and below the followed club
END_OF_SEASON = "End of season"


@dataclass(frozen=True, slots=True)
class ExcerptRow:
    position: int
    team: str
    played: int
    goal_difference: int
    points: int
    club: bool             # the followed club's row


@dataclass(frozen=True, slots=True)
class HubTable:
    """The followed club's league place at one step, calculated from the results counted by then (not the game's
    stored table, so its tie-break and deduction caveats apply), with a few rows round it."""

    position: int
    of: int
    points: int
    played: int
    unscored: int          # matches counted that were played with no recoverable score, so left out of the table
    excerpt: tuple[ExcerptRow, ...]


@dataclass(frozen=True, slots=True)
class HubStep:
    """The Hub as it stood at one point of the followed club's season: just before one of its matches (its league
    matchday, keeping the matchday's number even when the match was moved), or after its last match. Every figure
    counts only matches that were over by then (see played_before)."""

    title: str                     # "Matchday 12", "Match 3" for a club with no league, or END_OF_SEASON
    date: dt.date                  # the day of the snapshot: the match's date, or the last match's
    cutoff: Cutoff | None          # None for the end of the season, when every match is counted
    fixture: ScheduleItem | None   # the match the step stands before; None at the end of the season
    table: HubTable | None         # None for a club with no league match this season
    form: FormStrip                # every competition

    @property
    def label(self) -> str:
        if self.cutoff is None:
            return f"{self.title} · every match played, the last on {_short_date(self.date)}"
        return f"{self.title} · {self.cutoff.label()}"


@dataclass(frozen=True, slots=True)
class HubSeason:
    """Every step of the followed club's season, worked out once (off the window's thread) so that moving the
    stepper only picks one. `today` is the step for the save's own date; None when that date is unknown."""

    followed: FollowedClub
    season: int | None
    league_id: int | None          # the league the table is from; None for a club with no league match
    steps: tuple[HubStep, ...]
    today: int | None
    undated: int                   # the club's matches with no date, which cannot be placed on the stepper


def _is_league(f: Fixture) -> bool:
    return f.round is None and f.round_index is not None


def _hub_table(league: Sequence[Fixture], labels: Mapping[int, str], counted: Sequence[Fixture], team_id: int,
               tie_breaks: Sequence[int]) -> HubTable:
    ids = {id(g) for g in counted}
    rows = calculate_standings([g if id(g) in ids else replace(g, played=False) for g in league], labels,
                               tie_breaks=tie_breaks)
    row = next(r for r in rows if r.team_id == team_id)
    lo = max(0, min(row.position - 1 - HUB_EXCERPT, len(rows) - (2 * HUB_EXCERPT + 1)))
    excerpt = tuple(ExcerptRow(r.position, r.team, r.played, r.goals_for - r.goals_against, r.points,
                               r.team_id == team_id) for r in rows[lo:lo + 2 * HUB_EXCERPT + 1])
    return HubTable(row.position, len(rows), row.points, row.played,
                    sum(1 for g in counted if not has_score(g)), excerpt)


def hub_season(dataset: Dataset, followed: FollowedClub, season: int | None = None) -> HubSeason:
    """The followed club's season as the Hub's stepper walks it. A club in a league steps through its league
    matchdays in the order they were played; a club with no league match steps through all its matches. Undated
    matches cannot be placed and are only counted. When every step is played, a last step shows the season's end."""
    ids = followed_team_ids(dataset, followed)
    mine = club_fixtures(dataset, ids)
    if season is None:
        season = club_season(mine)
    in_season = [f for f in mine if season_key(f) == season]
    leagues = Counter(f.competition_id for f in in_season if _is_league(f))
    league_id = min(leagues, key=lambda c: (-leagues[c], c)) if leagues else None
    pool = [f for f in in_season if league_id is None or (f.competition_id == league_id and _is_league(f))]
    dated = sorted((f for f in pool if f.date is not None), key=_when)
    league = [f for f in dataset.fixtures_for(league_id) if season_key(f) == season] if league_id is not None else []
    labels = team_labels(league or in_season)
    tie_breaks = dataset.tie_breaks.get(league_id, ()) if league_id is not None else ()
    team_id = next((t for t in teams_in(league) if t in ids), None)
    items = {id(i.fixture): i for i in club_schedule(dataset, followed, season).items}
    club_labels = team_labels(in_season)

    def table(counted: Sequence[Fixture]) -> HubTable | None:
        return _hub_table(league, labels, counted, team_id, tie_breaks) if team_id is not None else None

    steps = []
    for n, f in enumerate(dated, start=1):
        title = f"Matchday {f.round_index + 1}" if league_id is not None else f"Match {n}"
        steps.append(HubStep(title, f.date, cutoff_for(f), items.get(id(f)),
                             table(played_before(league, f)),
                             form_before(in_season, ids, f, club_labels, scope=FORM_ALL).strip))
    if dated and all(f.played for f in dated):
        last = max(f.date for f in dated)
        steps.append(HubStep(END_OF_SEASON, last, None, None,
                             table([g for g in league if g.played and g.date is not None]),
                             form_strip(club_steps([g for g in in_season if g.date is not None], ids, club_labels))))
    today = dataset.info.game_date
    now = None
    if today is not None and steps:
        now = next((i for i, s in enumerate(steps) if s.fixture is not None and
                    (s.date > today or (s.date == today and not s.fixture.played))), len(steps) - 1)
    return HubSeason(followed, season, league_id, tuple(steps), now, sum(1 for f in pool if f.date is None))


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
