# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""The local fixture archive: every save Box2Box opens is banked here, so a season's results outlive the
saves that held them. One SQLite file next to the app, one transaction per import. No UI code.

The Yearbook reads only this archive (see notes/design_v2.0_yearbook.md).
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Sequence
import dataclasses
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace as NS
from typing import NamedTuple

SCHEMA_VERSION = 3          # 2: competitions.zone_rules; 3: fixtures.home_xg and away_xg, conflicts.kind

_SCHEMA = """
CREATE TABLE meta (schema_version INTEGER NOT NULL);
CREATE TABLE imports (
    id INTEGER PRIMARY KEY, file_name TEXT, build TEXT, game_date TEXT, fmsave_version TEXT, imported_at TEXT,
    added INTEGER, updated INTEGER, unchanged INTEGER, conflicts INTEGER, skipped_unresolved INTEGER, warnings TEXT);
CREATE TABLE clubs (uid INTEGER PRIMARY KEY, name TEXT, short_name TEXT, nation_id INTEGER);
CREATE TABLE competitions (
    key INTEGER PRIMARY KEY, database_id INTEGER, tie_breaks TEXT, nation INTEGER, continental INTEGER,
    source_date TEXT, zone_rules TEXT);
CREATE TABLE fixtures (
    competition_key INTEGER NOT NULL, season INTEGER NOT NULL, home_uid INTEGER NOT NULL,
    away_uid INTEGER NOT NULL, meeting INTEGER NOT NULL,
    date TEXT, kick_off TEXT, home_goals INTEGER, away_goals INTEGER, played INTEGER NOT NULL,
    round_index INTEGER, round_label TEXT, round_raw INTEGER, home_name TEXT, away_name TEXT, source_date TEXT,
    home_xg REAL, away_xg REAL,
    PRIMARY KEY (competition_key, season, home_uid, away_uid, meeting));
CREATE TABLE conflicts (
    competition_key INTEGER, season INTEGER, home_uid INTEGER, away_uid INTEGER, meeting INTEGER,
    kept_home INTEGER, kept_away INTEGER, other_home INTEGER, other_away INTEGER, import_id INTEGER,
    kind TEXT NOT NULL DEFAULT 'score');
"""


class ArchiveError(Exception):
    """The archive could not be opened or written; the message says why in plain words."""


class WorldMismatch(ArchiveError):
    """A save whose results disagree with the archive's: a different playthrough."""


FixtureKey = tuple[int, int, int, int, int]   # competition key, season, home club uid, away club uid, meeting
ARCHIVE_KEY = "archive_key"     # where a fixture from Archive.dataset() carries its FixtureKey, in its `unknown`


def archived_key(fixture) -> FixtureKey | None:
    """The archive's key of a fixture from Archive.dataset(); None for a fixture read from a save."""
    return (getattr(fixture, "unknown", None) or {}).get(ARCHIVE_KEY)


def competition_key(competition_id: int, database_id: int | None) -> int:
    """A competition's identity across saves: its database id, or (for the rare competition without one) a
    negative stand-in from the save's own id. Spike on two real saves: database ids are stable."""
    return database_id if database_id is not None else -(competition_id + 1)


def fixture_keys(fixtures: Sequence, key_of_competition: Callable[[object], int | None]) -> list[FixtureKey | None]:
    """A key for each fixture, in input order; None for one the archive cannot identify (no competition, no
    season, or a team the save cannot resolve to a club). `meeting` numbers a pair's meetings in one
    competition and season by round, then date, so a postponed match keeps its key when its date moves."""
    from fm_data import season_key
    groups: dict[tuple, list[int]] = defaultdict(list)
    keys: list[FixtureKey | None] = [None] * len(fixtures)
    for index, f in enumerate(fixtures):
        competition, season = key_of_competition(f), season_key(f)
        if competition is None or season is None or f.home_club_uid is None or f.away_club_uid is None:
            continue
        groups[(competition, season, f.home_club_uid, f.away_club_uid)].append(index)
    for group, indexes in groups.items():
        ordered = sorted(indexes, key=lambda i: (-1 if fixtures[i].round_index is None else fixtures[i].round_index,
                                                 fixtures[i].date or dt.date.min))
        for meeting, index in enumerate(ordered):
            keys[index] = (*group, meeting)
    return keys


@dataclass(frozen=True, slots=True)
class ArchivedFixture:
    """One fixture as the archive holds it. `source_date` is the in-game date of the save it came from."""

    key: FixtureKey
    date: dt.date | None
    kick_off: dt.time | None
    home_goals: int | None
    away_goals: int | None
    played: bool
    round_index: int | None
    round_label: str | None
    round_raw: int | None
    home_name: str
    away_name: str
    source_date: dt.date | None
    home_xg: float | None = None          # expected goals from the save's match report; None when it held none
    away_xg: float | None = None

    @property
    def scored(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None

    @property
    def has_xg(self) -> bool:
        return self.home_xg is not None and self.away_xg is not None


class MergeResult(NamedTuple):
    fixture: ArchivedFixture
    outcome: str          # "added", "updated", "unchanged" or "conflict"
    kinds: tuple[str, ...] = ()           # what conflicted: "score" and/or "xg"
    loser: ArchivedFixture | None = None  # the copy that was not kept, when something conflicted


def _rank(f: ArchivedFixture) -> tuple:
    """A total order over everything a fixture holds, so that merging cannot depend on argument order: a played
    fixture beats an unplayed one, one with a score beats one without, then the later source save wins, and any
    remaining tie falls to the larger value of each field in turn."""
    none = lambda value, low: low if value is None else value
    return (f.played, f.scored, none(f.source_date, dt.date.min), none(f.date, dt.date.min),
            none(f.home_goals, -1), none(f.away_goals, -1), none(f.kick_off, dt.time.min),
            none(f.round_index, -1), f.round_label or "", none(f.round_raw, -1), f.home_name, f.away_name,
            none(f.home_xg, -1), none(f.away_xg, -1))


XG_PLACES = 4
XG_TOLERANCE = 1e-4          # figures this close are the same figure: the save stores them as 32-bit floats


def merge_fixture(old: ArchivedFixture | None, new: ArchivedFixture) -> MergeResult:
    """Merge a fixture from a save into the archive's copy. A played result is never replaced by "not played"
    or by a missing score; otherwise the later save wins (see _rank). Two played, scored results that differ are
    a conflict: the later save is kept and the caller records both. Expected goals are merged on their own: a
    missing figure is filled from either copy and never replaces a stored one, and two different figures are a
    conflict too."""
    if old is None:
        return MergeResult(new, "added")
    winner = max(old, new, key=_rank)
    other = new if winner is old else old
    kinds = []
    both_played = old.played and new.played and old.scored and new.scored
    if both_played and (old.home_goals, old.away_goals) != (new.home_goals, new.away_goals):
        kinds.append("score")
    if winner.has_xg:
        figures = (winner.home_xg, winner.away_xg)
        if other.has_xg and not (math.isclose(winner.home_xg, other.home_xg, abs_tol=XG_TOLERANCE)
                                 and math.isclose(winner.away_xg, other.away_xg, abs_tol=XG_TOLERANCE)):
            kinds.append("xg")
    else:
        figures = (other.home_xg, other.away_xg) if other.has_xg else (None, None)
    figures = tuple(None if v is None else round(v, XG_PLACES) for v in figures)
    winner = replace(winner, home_xg=figures[0], away_xg=figures[1])
    if kinds:
        return MergeResult(winner, "conflict", tuple(kinds), other)
    same = replace(winner, source_date=None) == replace(old, source_date=None)
    return MergeResult(winner, "unchanged" if same else "updated")


# A save whose played, scored results disagree with the archive's on more than this share of at least
# WORLD_MIN_OVERLAP overlapping fixtures is a different playthrough (see notes/design_v2.0_yearbook.md).
WORLD_MAX_DISAGREEMENT = 0.05
WORLD_MIN_OVERLAP = 20


@dataclass(frozen=True, slots=True)
class BankReport:
    """What banking one save changed."""

    added: int
    updated: int
    unchanged: int
    conflicts: int
    skipped_unresolved: int
    already_banked: bool

    def describe(self) -> str:
        if self.already_banked:
            return "Already banked."
        text = f"Banked: {self.added} new fixtures, {self.updated} updated, {self.conflicts} conflicts."
        if self.skipped_unresolved:
            text += f" {self.skipped_unresolved} skipped (no club the save could resolve)."
        return text


@dataclass(frozen=True, slots=True)
class XgBankReport:
    """What adding a save's expected goals to the archive changed."""

    filled: int          # fixtures that gained figures
    unchanged: int       # fixtures whose figures were already there
    conflicts: int
    missing: int         # matches the archive does not hold (nothing is added)

    def describe(self) -> str:
        if not self.filled and not self.conflicts:
            return "Expected goals were already banked."
        text = f"Expected goals banked for {self.filled:,} matches."
        if self.conflicts:
            text += f" {self.conflicts} differed from figures already stored."
        return text


@dataclass(frozen=True, slots=True)
class ImportRecord:
    """One banked save, as the archive remembers it."""

    file_name: str
    build: str
    game_date: dt.date | None
    fmsave_version: str
    imported_at: dt.datetime
    added: int
    updated: int
    unchanged: int
    conflicts: int
    skipped_unresolved: int
    warnings: tuple[str, ...]


NATION_SHARE = 0.6     # a competition belongs to a nation when this share of its clubs (with a known nation) do


@dataclass(frozen=True, slots=True)
class ArchivedCompetition:
    """A competition the archive holds. `nation` is inferred from its clubs; `continental` means it mixes nations."""

    key: int
    database_id: int | None
    nation: int | None
    continental: bool
    tie_breaks: tuple[int, ...]
    seasons: tuple[int, ...]
    zones: tuple[int, int, int] | None = None      # (promotion, play-off, relegation) places, from the game's rules


def infer_nation(club_uids: set[int], club_nations: dict[int, int]) -> tuple[int | None, bool]:
    """(nation, continental) for a competition's clubs: the nation of at least NATION_SHARE of those whose
    nation is known; continental when they come from several nations with no such majority."""
    known = [club_nations[uid] for uid in club_uids if uid in club_nations]
    if not known:
        return None, False
    nation = max(set(known), key=lambda n: (known.count(n), n))
    if known.count(nation) / len(known) >= NATION_SHARE:
        return nation, False
    return None, True


GAP_DAYS = 14          # more than this many days between banked saves inside a season is a gap in the record


@dataclass(frozen=True, slots=True)
class BookCoverage:
    """How well the archive covers one season: which saves, their in-game span and the gaps between them."""

    saves: int
    first_date: dt.date | None
    last_date: dt.date | None
    gaps: tuple[tuple[dt.date, dt.date], ...]
    in_progress: bool


_COLUMNS = ("competition_key", "season", "home_uid", "away_uid", "meeting", "date", "kick_off", "home_goals",
            "away_goals", "played", "round_index", "round_label", "round_raw", "home_name", "away_name", "source_date",
            "home_xg", "away_xg")


def _iso(value: dt.date | dt.time | None) -> str | None:
    return None if value is None else value.isoformat()


def _readable_xg(expected) -> tuple[float, float] | None:
    """A match's expected goals as a pair to store, or None unless both are finite numbers of zero or more."""
    if expected is None:
        return None
    pair = (expected.home, expected.away)
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 for v in pair):
        return round(float(pair[0]), XG_PLACES), round(float(pair[1]), XG_PLACES)
    return None


def _row(f: ArchivedFixture) -> tuple:
    return (*f.key, _iso(f.date), _iso(f.kick_off), f.home_goals, f.away_goals, int(f.played), f.round_index,
            f.round_label, f.round_raw, f.home_name, f.away_name, _iso(f.source_date), f.home_xg, f.away_xg)


def _fixture(row: Sequence) -> ArchivedFixture:
    return ArchivedFixture(
        key=tuple(row[:5]), date=dt.date.fromisoformat(row[5]) if row[5] else None,
        kick_off=dt.time.fromisoformat(row[6]) if row[6] else None, home_goals=row[7], away_goals=row[8],
        played=bool(row[9]), round_index=row[10], round_label=row[11], round_raw=row[12], home_name=row[13],
        away_name=row[14], source_date=dt.date.fromisoformat(row[15]) if row[15] else None,
        home_xg=row[16] if len(row) > 16 else None, away_xg=row[17] if len(row) > 17 else None)


class Archive:
    """An open archive file. Use as a context manager, or call close()."""

    def __init__(self, db: sqlite3.Connection, path: Path) -> None:
        self._db, self.path = db, path

    @classmethod
    def open(cls, path: Path) -> Archive:
        """Open the archive at `path`, creating it at the current schema if it does not exist. A file written
        by a newer Box2Box is refused and left untouched."""
        path = Path(path)
        db = None
        try:
            db = sqlite3.connect(path)
            has_meta = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'meta'").fetchone()
            if not has_meta:
                with db:
                    db.executescript(_SCHEMA)
                    db.execute("INSERT INTO meta (schema_version) VALUES (?)", (SCHEMA_VERSION,))
            else:
                found = db.execute("SELECT schema_version FROM meta").fetchone()[0]
                if found < SCHEMA_VERSION:
                    with db:                                  # older archives are upgraded in place, keeping their data
                        if found < 2:
                            db.execute("ALTER TABLE competitions ADD COLUMN zone_rules TEXT")
                        if found < 3:                             # expected goals, filled in when a save with reports is banked
                            db.execute("ALTER TABLE fixtures ADD COLUMN home_xg REAL")
                            db.execute("ALTER TABLE fixtures ADD COLUMN away_xg REAL")
                            db.execute("ALTER TABLE conflicts ADD COLUMN kind TEXT NOT NULL DEFAULT 'score'")
                        db.execute("UPDATE meta SET schema_version = ?", (SCHEMA_VERSION,))
                if found > SCHEMA_VERSION:
                    db.close()
                    raise ArchiveError(f"This archive was written by a newer Box2Box (schema {found}); "
                                       f"this version understands schema {SCHEMA_VERSION}. Nothing was changed.")
        except sqlite3.Error as exc:
            if db is not None:
                db.close()
            raise ArchiveError(f"The archive at {path} could not be opened: {exc}") from exc
        return cls(db, path)

    def _archived(self, dataset) -> tuple[list[ArchivedFixture], int]:
        """The save's identifiable fixtures as archive records, and how many it could not identify."""
        from fm_data import fixture_key
        everything = [f for fixtures in dataset.fixtures.values() for f in fixtures]
        database_ids = {c.id: c.database_id for c in dataset.competitions}
        keys = fixture_keys(everything, lambda f: competition_key(f.competition_id, database_ids.get(f.competition_id)))
        records, skipped = [], 0
        for f, key in zip(everything, keys):
            if key is None:
                skipped += 1
                continue
            label = getattr(getattr(f, "round", None), "label", None)
            label = getattr(label, "name", label)             # an enum member is stored by its name
            raw = getattr(getattr(f, "round", None), "raw", None)
            figures = _readable_xg(dataset.expected_goals.get(fixture_key(f))) if f.played else None
            records.append(ArchivedFixture(
                key=key, date=f.date, kick_off=f.kick_off_time, home_goals=f.home_goals, away_goals=f.away_goals,
                played=bool(f.played), round_index=f.round_index, round_label=label, round_raw=raw,
                home_name=f.home_club_name or "", away_name=f.away_club_name or "", source_date=dataset.info.game_date,
                home_xg=figures[0] if figures else None, away_xg=figures[1] if figures else None))
        return records, skipped

    def _fill_short_names(self, dataset) -> None:
        """Record the game's short club names where the archive has none yet (first writer wins, so the order saves
        arrive in never matters). Runs inside the caller's transaction."""
        for fixtures in dataset.fixtures.values():
            for f in fixtures:
                for uid, short in ((f.home_club_uid, f.home_club_short_name), (f.away_club_uid, f.away_club_short_name)):
                    if uid is not None and short:
                        self._db.execute("UPDATE clubs SET short_name = ? WHERE uid = ? AND short_name IS NULL",
                                         (short, uid))

    def _fill_zone_rules(self, dataset) -> None:
        """Record zone rules for competitions whose rules the archive does not hold yet (an archive upgraded from
        schema 1). Never overwrites rules already there. Runs inside the caller's transaction."""
        for comp in dataset.competitions:
            rules = dataset.zone_rules.get(comp.id)
            if rules:
                self._db.execute("UPDATE competitions SET zone_rules = ? WHERE key = ? AND (zone_rules IS NULL OR zone_rules = '')",
                                 (json.dumps([rules.promotion, rules.playoff, rules.relegation]),
                                  competition_key(comp.id, comp.database_id)))

    def _stored(self, key: FixtureKey) -> ArchivedFixture | None:
        row = self._db.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM fixtures WHERE competition_key = ? AND season = ? AND home_uid = ? "
            "AND away_uid = ? AND meeting = ?", key).fetchone()
        return _fixture(row) if row else None

    def _record_conflicts(self, key: FixtureKey, result: MergeResult, import_id: int) -> None:
        """Write one row for each kind of disagreement a merge found: the kept values and the ones set aside."""
        for kind in result.kinds:
            kept, other = result.fixture, result.loser
            pair = ((kept.home_goals, kept.away_goals, other.home_goals, other.away_goals) if kind == "score"
                    else (kept.home_xg, kept.away_xg, other.home_xg, other.away_xg))
            self._db.execute("INSERT INTO conflicts (competition_key, season, home_uid, away_uid, meeting, kept_home, "
                             "kept_away, other_home, other_away, import_id, kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (*key, *pair, import_id, kind))

    def _check_world(self, records: Sequence[ArchivedFixture]) -> None:
        """Refuse a save whose played results disagree with the archive's beyond WORLD_MAX_DISAGREEMENT."""
        overlap = disagree = 0
        for f in records:
            old = self._stored(f.key)
            if old and old.played and f.played and old.scored and f.scored:
                overlap += 1
                disagree += (old.home_goals, old.away_goals) != (f.home_goals, f.away_goals)
        if overlap >= WORLD_MIN_OVERLAP and disagree / overlap > WORLD_MAX_DISAGREEMENT:
            raise WorldMismatch("These results do not match the archive, so this looks like a different "
                                "playthrough. Nothing was changed.")

    def bank(self, dataset) -> BankReport:
        """Merge a save's fixtures into the archive in one transaction. Banking the same save (file and in-game
        date) again changes nothing. A save that looks like a different playthrough raises WorldMismatch; any
        failure rolls the whole import back."""
        info = dataset.info
        game_date = _iso(info.game_date)
        if self._db.execute("SELECT 1 FROM imports WHERE file_name = ? AND game_date IS ?",
                            (info.file_name, game_date)).fetchone():
            with self._db:                          # an archive banked before short names or zone rules were kept
                self._fill_short_names(dataset)
                self._fill_zone_rules(dataset)
            return BankReport(0, 0, 0, 0, 0, True)
        records, skipped = self._archived(dataset)
        self._check_world(records)
        counts = {"added": 0, "updated": 0, "unchanged": 0, "conflict": 0}
        with self._db:
            import_id = self._db.execute(
                "INSERT INTO imports (file_name, build, game_date, fmsave_version, imported_at, warnings) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (info.file_name, info.build, game_date, info.fmsave_version, info.imported_at.isoformat(),
                 json.dumps(list(info.warnings)))).lastrowid
            for f in records:
                old = self._stored(f.key)
                result = merge_fixture(old, f)
                counts[result.outcome] += 1
                self._record_conflicts(f.key, result, import_id)
                if result.fixture != old:
                    self._db.execute(
                        f"INSERT OR REPLACE INTO fixtures ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))})",
                        _row(result.fixture))
            self._bank_competitions(dataset, records)
            for f in records:
                for uid, name in ((f.key[2], f.home_name), (f.key[3], f.away_name)):
                    self._db.execute("INSERT OR IGNORE INTO clubs (uid, name) VALUES (?, ?)", (uid, name))
            self._fill_short_names(dataset)
            for uid, nation in dataset.club_nations.items():
                self._db.execute("UPDATE clubs SET nation_id = ? WHERE uid = ? AND nation_id IS NULL", (nation, uid))
            self._db.execute(
                "UPDATE imports SET added = ?, updated = ?, unchanged = ?, conflicts = ?, skipped_unresolved = ? "
                "WHERE id = ?", (counts["added"], counts["updated"], counts["unchanged"], counts["conflict"], skipped,
                                 import_id))
        return BankReport(counts["added"], counts["updated"], counts["unchanged"], counts["conflict"], skipped, False)

    def bank_expected_goals(self, dataset) -> XgBankReport | None:
        """Add the expected goals a save's match reports hold to fixtures already banked from that save, once its
        statistics have been read (they arrive a few seconds after the save opens). Only fixtures already in the
        archive are touched, none is added, and nothing happens when this save was never banked (None). A missing
        figure is filled, a stored one is never replaced by a missing one, and a different figure is a conflict."""
        info = dataset.info
        row = self._db.execute("SELECT id FROM imports WHERE file_name = ? AND game_date IS ?",
                               (info.file_name, _iso(info.game_date))).fetchone()
        if row is None:
            return None
        records, _ = self._archived(dataset)
        filled = unchanged = conflicts = missing = 0
        with self._db:
            for f in records:
                if not f.has_xg:
                    continue
                old = self._stored(f.key)
                if old is None:
                    missing += 1
                    continue
                result = merge_fixture(old, f)
                self._record_conflicts(f.key, result, row[0])
                conflicts += result.outcome == "conflict"
                if result.fixture != old:
                    self._db.execute(f"INSERT OR REPLACE INTO fixtures ({', '.join(_COLUMNS)}) "
                                     f"VALUES ({', '.join('?' * len(_COLUMNS))})", _row(result.fixture))
                    filled += old.home_xg is None
                else:
                    unchanged += 1
        return XgBankReport(filled, unchanged, conflicts, missing)

    def expected_goals(self) -> dict[tuple, tuple[float, float]]:
        """The expected goals the archive holds, keyed as the save's own statistics name a match (competition key, home
        club, away club, date), so a book can join them to its fixtures. A key that more than one fixture shares is
        ambiguous and gives nothing."""
        rows = self._db.execute("SELECT competition_key, home_uid, away_uid, date, home_xg, away_xg FROM fixtures "
                                "WHERE date IS NOT NULL").fetchall()
        shared: dict[tuple, int] = defaultdict(int)
        for r in rows:
            shared[r[:4]] += 1
        return {(r[0], r[1], r[2], dt.date.fromisoformat(r[3])): (r[4], r[5]) for r in rows
                if r[4] is not None and r[5] is not None and shared[r[:4]] == 1}

    def seasons(self) -> list[int]:
        """Every season with a fixture in the archive, newest first."""
        return [r[0] for r in self._db.execute("SELECT DISTINCT season FROM fixtures ORDER BY season DESC")]

    def season_labels(self) -> list[tuple[int, str]]:
        """(season, label) for every season, newest first: "2026/27" when it crosses the new year, else "2026"
        (the same rule as fm_data.season_label, answered without loading the archive)."""
        rows = self._db.execute("SELECT season, MAX(date) FROM fixtures GROUP BY season ORDER BY season DESC")
        return [(season, f"{season}/{(season + 1) % 100:02d}" if latest and int(latest[:4]) > season else str(season))
                for season, latest in rows]

    def coverage(self, season: int) -> BookCoverage:
        """The banked saves that fall inside a season's span of play, and the gaps between them."""
        span = self._db.execute("SELECT MIN(date), MAX(date), MAX(1 - played) FROM fixtures WHERE season = ?",
                                (season,)).fetchone()
        if span[0] is None:
            return BookCoverage(0, None, None, (), False)
        dates = sorted({r[0] for r in self._db.execute(
            "SELECT game_date FROM imports WHERE game_date BETWEEN ? AND ?", (span[0], span[1]))})
        days = [dt.date.fromisoformat(d) for d in dates]
        gaps = tuple((a, b) for a, b in zip(days, days[1:]) if (b - a).days > GAP_DAYS)
        return BookCoverage(len(days), days[0] if days else None, days[-1] if days else None, gaps, bool(span[2]))

    def dataset(self):
        """The whole archive as an fm_data.Dataset, so the existing table, cup and label helpers run on it
        unchanged. A competition's id here is its archive key; a club's team id is its club uid."""
        import fm_data as fd
        from fmsave import CodedValue, CompetitionRound, Fixture
        columns = ", ".join(_COLUMNS)
        short = {uid: name for uid, name in self._db.execute("SELECT uid, short_name FROM clubs") if name}
        fixtures = []
        for row in self._db.execute(f"SELECT {columns} FROM fixtures ORDER BY competition_key, season, date"):
            f = _fixture(row)
            round_ = None if f.round_label is None and f.round_raw is None else CodedValue(
                CompetitionRound[f.round_label] if f.round_label else CompetitionRound.UNKNOWN, f.round_raw)
            key = f.key
            fixtures.append(Fixture(
                stage_id=0, competition_id=key[0], competition_name=None, round=round_, round_index=f.round_index,
                date=f.date, kick_off_time=f.kick_off, season_start_year=key[1],
                home_team_id=key[2], home_club_uid=key[2], home_club_name=f.home_name,
                home_club_short_name=short.get(key[2], f.home_name),
                home_team_slot=0, away_team_id=key[3], away_club_uid=key[3], away_club_name=f.away_name,
                away_club_short_name=short.get(key[3], f.away_name), away_team_slot=0, home_goals=f.home_goals, away_goals=f.away_goals,
                played=f.played, is_neutral_venue=False, stadium_uid=None, stadium_name=None, referee_id=None,
                match_rules_template=(), unknown={ARCHIVE_KEY: key}))
        known = self.competitions()
        clubs = [NS(uid=r[0], reputation=None, teams=(), nation_id=r[1])
                 for r in self._db.execute("SELECT uid, nation_id FROM clubs")]
        imports = self.imports()
        last = imports[-1] if imports else None
        info = fd.ImportInfo(
            path=str(self.path), file_name=self.path.name, game="Archive", build="archive", known_build=True,
            game_date=last.game_date if last else None, fmsave_version="", imported_at=dt.datetime.now(),
            seconds=0.0, warnings=(), managed_club_uid=None, managed_club_name=None)
        dataset = fd.build_dataset(info, fixtures, clubs=clubs,
                                   competitions=[NS(id=c.key, database_id=c.database_id if c.key >= 0 else None)
                                                 for c in known])
        return dataclasses.replace(
            dataset, tie_breaks={c.key: c.tie_breaks for c in known if c.tie_breaks},
            zone_rules={c.key: fd.ZoneRules(*c.zones) for c in known if c.zones})

    def _bank_competitions(self, dataset, records: Sequence[ArchivedFixture]) -> None:
        """Keep each competition's metadata from the newest save (ties go to the larger value, so the order saves
        arrive in never matters)."""
        clubs_in: dict[int, set[int]] = defaultdict(set)
        for f in records:
            clubs_in[f.key[0]].update((f.key[2], f.key[3]))
        for comp in dataset.competitions:
            key = competition_key(comp.id, comp.database_id)
            nation, continental = infer_nation(clubs_in.get(key, set()), dict(dataset.club_nations))
            codes = json.dumps(list(dataset.tie_breaks.get(comp.id, ())))
            rules = dataset.zone_rules.get(comp.id)
            zones = json.dumps([rules.promotion, rules.playoff, rules.relegation]) if rules else ""
            new = (_iso(dataset.info.game_date) or "", -1 if nation is None else nation, int(continental), codes, zones)
            row = self._db.execute("SELECT source_date, nation, continental, tie_breaks, zone_rules FROM competitions "
                                   "WHERE key = ?", (key,)).fetchone()
            if row and (row[0] or "", -1 if row[1] is None else row[1], row[2], row[3], row[4] or "") >= new:
                continue
            self._db.execute("INSERT OR REPLACE INTO competitions (key, database_id, tie_breaks, nation, continental, "
                             "source_date, zone_rules) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (key, comp.database_id, codes, nation, int(continental), _iso(dataset.info.game_date),
                              zones))

    def competitions(self) -> list[ArchivedCompetition]:
        """Every competition the archive holds, in key order."""
        rows = self._db.execute("SELECT key, database_id, tie_breaks, nation, continental, zone_rules FROM competitions "
                                "ORDER BY key").fetchall()
        return [ArchivedCompetition(
            key=r[0], database_id=r[1], nation=r[3], continental=bool(r[4]), tie_breaks=tuple(json.loads(r[2])),
            zones=tuple(json.loads(r[5])) if r[5] else None,
            seasons=tuple(x[0] for x in self._db.execute(
                "SELECT DISTINCT season FROM fixtures WHERE competition_key = ? ORDER BY season", (r[0],))))
            for r in rows]

    def imports(self) -> list[ImportRecord]:
        """Every banked save, oldest first."""
        rows = self._db.execute(
            "SELECT file_name, build, game_date, fmsave_version, imported_at, added, updated, unchanged, conflicts, "
            "skipped_unresolved, warnings FROM imports ORDER BY id").fetchall()
        return [ImportRecord(r[0], r[1], dt.date.fromisoformat(r[2]) if r[2] else None, r[3],
                             dt.datetime.fromisoformat(r[4]), r[5], r[6], r[7], r[8], r[9], tuple(json.loads(r[10])))
                for r in rows]

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Archive:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
