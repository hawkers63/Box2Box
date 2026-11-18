# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""The local fixture archive: every save Box2Box opens is banked here, so a season's results outlive the
saves that held them. One SQLite file next to the app, one transaction per import. No UI code.

The Yearbook reads only this archive (see notes/design_v2.0_yearbook.md).
"""

from __future__ import annotations

import datetime as dt
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

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Archive:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
