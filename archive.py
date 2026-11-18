# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""The local fixture archive: every save Box2Box opens is banked here, so a season's results outlive the
saves that held them. One SQLite file next to the app, one transaction per import. No UI code.

The Yearbook reads only this archive (see notes/design_v2.0_yearbook.md).
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NamedTuple

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE meta (schema_version INTEGER NOT NULL);
CREATE TABLE imports (
    id INTEGER PRIMARY KEY, file_name TEXT, build TEXT, game_date TEXT, fmsave_version TEXT, imported_at TEXT,
    added INTEGER, updated INTEGER, unchanged INTEGER, conflicts INTEGER, skipped_unresolved INTEGER, warnings TEXT);
CREATE TABLE clubs (uid INTEGER PRIMARY KEY, name TEXT, short_name TEXT, nation_id INTEGER);
CREATE TABLE competitions (
    key INTEGER PRIMARY KEY, database_id INTEGER, tie_breaks TEXT, nation INTEGER, continental INTEGER);
CREATE TABLE fixtures (
    competition_key INTEGER NOT NULL, season INTEGER NOT NULL, home_uid INTEGER NOT NULL,
    away_uid INTEGER NOT NULL, meeting INTEGER NOT NULL,
    date TEXT, kick_off TEXT, home_goals INTEGER, away_goals INTEGER, played INTEGER NOT NULL,
    round_index INTEGER, round_label TEXT, round_raw INTEGER, home_name TEXT, away_name TEXT, source_date TEXT,
    PRIMARY KEY (competition_key, season, home_uid, away_uid, meeting));
CREATE TABLE conflicts (
    competition_key INTEGER, season INTEGER, home_uid INTEGER, away_uid INTEGER, meeting INTEGER,
    kept_home INTEGER, kept_away INTEGER, other_home INTEGER, other_away INTEGER, import_id INTEGER);
"""


class ArchiveError(Exception):
    """The archive could not be opened or written; the message says why in plain words."""


class WorldMismatch(ArchiveError):
    """A save whose results disagree with the archive's: a different playthrough."""


FixtureKey = tuple[int, int, int, int, int]   # competition key, season, home club uid, away club uid, meeting


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

    @property
    def scored(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None


class MergeResult(NamedTuple):
    fixture: ArchivedFixture
    outcome: str          # "added", "updated", "unchanged" or "conflict"


def _rank(f: ArchivedFixture) -> tuple:
    """A total order over everything a fixture holds, so that merging cannot depend on argument order: a played
    fixture beats an unplayed one, one with a score beats one without, then the later source save wins, and any
    remaining tie falls to the larger value of each field in turn."""
    none = lambda value, low: low if value is None else value
    return (f.played, f.scored, none(f.source_date, dt.date.min), none(f.date, dt.date.min),
            none(f.home_goals, -1), none(f.away_goals, -1), none(f.kick_off, dt.time.min),
            none(f.round_index, -1), f.round_label or "", none(f.round_raw, -1), f.home_name, f.away_name)


def merge_fixture(old: ArchivedFixture | None, new: ArchivedFixture) -> MergeResult:
    """Merge a fixture from a save into the archive's copy. A played result is never replaced by "not played"
    or by a missing score; otherwise the later save wins (see _rank). Two played, scored results that differ are
    a conflict: the later save is kept and the caller records both."""
    if old is None:
        return MergeResult(new, "added")
    winner = max(old, new, key=_rank)
    both_played = old.played and new.played and old.scored and new.scored
    if both_played and (old.home_goals, old.away_goals) != (new.home_goals, new.away_goals):
        return MergeResult(winner, "conflict")
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


_COLUMNS = ("competition_key", "season", "home_uid", "away_uid", "meeting", "date", "kick_off", "home_goals",
            "away_goals", "played", "round_index", "round_label", "round_raw", "home_name", "away_name", "source_date")


def _iso(value: dt.date | dt.time | None) -> str | None:
    return None if value is None else value.isoformat()


def _row(f: ArchivedFixture) -> tuple:
    return (*f.key, _iso(f.date), _iso(f.kick_off), f.home_goals, f.away_goals, int(f.played), f.round_index,
            f.round_label, f.round_raw, f.home_name, f.away_name, _iso(f.source_date))


def _fixture(row: Sequence) -> ArchivedFixture:
    return ArchivedFixture(
        key=tuple(row[:5]), date=dt.date.fromisoformat(row[5]) if row[5] else None,
        kick_off=dt.time.fromisoformat(row[6]) if row[6] else None, home_goals=row[7], away_goals=row[8],
        played=bool(row[9]), round_index=row[10], round_label=row[11], round_raw=row[12], home_name=row[13],
        away_name=row[14], source_date=dt.date.fromisoformat(row[15]) if row[15] else None)


class Archive:
    """An open archive file. Use as a context manager, or call close()."""

    def __init__(self, db: sqlite3.Connection, path: Path) -> None:
        self._db, self.path = db, path

    @classmethod
    def open(cls, path: Path) -> Archive:
        """Open the archive at `path`, creating it at the current schema if it does not exist. A file written
        by a newer Box2Box is refused and left untouched."""
        path = Path(path)
        try:
            db = sqlite3.connect(path)
            has_meta = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'meta'").fetchone()
            if not has_meta:
                with db:
                    db.executescript(_SCHEMA)
                    db.execute("INSERT INTO meta (schema_version) VALUES (?)", (SCHEMA_VERSION,))
            else:
                found = db.execute("SELECT schema_version FROM meta").fetchone()[0]
                if found > SCHEMA_VERSION:
                    db.close()
                    raise ArchiveError(f"This archive was written by a newer Box2Box (schema {found}); "
                                       f"this version understands schema {SCHEMA_VERSION}. Nothing was changed.")
        except sqlite3.Error as exc:
            raise ArchiveError(f"The archive at {path} could not be opened: {exc}") from exc
        return cls(db, path)

    def _archived(self, dataset) -> tuple[list[ArchivedFixture], int]:
        """The save's identifiable fixtures as archive records, and how many it could not identify."""
        everything = [f for fixtures in dataset.fixtures.values() for f in fixtures]
        database_ids = {c.id: c.database_id for c in dataset.competitions}
        keys = fixture_keys(everything, lambda f: competition_key(f.competition_id, database_ids.get(f.competition_id)))
        records, skipped = [], 0
        for f, key in zip(everything, keys):
            if key is None:
                skipped += 1
                continue
            label = getattr(getattr(f, "round", None), "label", None)
            raw = getattr(getattr(f, "round", None), "raw", None)
            records.append(ArchivedFixture(
                key=key, date=f.date, kick_off=f.kick_off_time, home_goals=f.home_goals, away_goals=f.away_goals,
                played=bool(f.played), round_index=f.round_index, round_label=label, round_raw=raw,
                home_name=f.home_club_name or "", away_name=f.away_club_name or "", source_date=dataset.info.game_date))
        return records, skipped

    def _stored(self, key: FixtureKey) -> ArchivedFixture | None:
        row = self._db.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM fixtures WHERE competition_key = ? AND season = ? AND home_uid = ? "
            "AND away_uid = ? AND meeting = ?", key).fetchone()
        return _fixture(row) if row else None

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
                if result.outcome == "conflict":
                    loser = f if result.fixture == old else old
                    self._db.execute("INSERT INTO conflicts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                     (*f.key, result.fixture.home_goals, result.fixture.away_goals,
                                      loser.home_goals, loser.away_goals, import_id))
                if result.fixture != old:
                    self._db.execute(
                        f"INSERT OR REPLACE INTO fixtures ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * 16)})",
                        _row(result.fixture))
            for f in records:
                for uid, name in ((f.key[2], f.home_name), (f.key[3], f.away_name)):
                    self._db.execute("INSERT OR IGNORE INTO clubs (uid, name) VALUES (?, ?)", (uid, name))
            for uid, nation in dataset.club_nations.items():
                self._db.execute("UPDATE clubs SET nation_id = ? WHERE uid = ? AND nation_id IS NULL", (nation, uid))
            self._db.execute(
                "UPDATE imports SET added = ?, updated = ?, unchanged = ?, conflicts = ?, skipped_unresolved = ? "
                "WHERE id = ?", (counts["added"], counts["updated"], counts["unchanged"], counts["conflict"], skipped,
                                 import_id))
        return BankReport(counts["added"], counts["updated"], counts["unchanged"], counts["conflict"], skipped, False)

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
