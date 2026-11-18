# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""The local fixture archive: every save Box2Box opens is banked here, so a season's results outlive the
saves that held them. One SQLite file next to the app, one transaction per import. No UI code.

The Yearbook reads only this archive (see notes/design_v2.0_yearbook.md).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

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
