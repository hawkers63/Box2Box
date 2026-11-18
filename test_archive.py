# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Tests for archive: the local fixture archive that every opened save is banked into.

Run:  .venv\\Scripts\\python -m unittest test_archive -v
"""

import contextlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

import archive


class ArchiveFileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "archive.sqlite"

    def connect(self):
        """A connection to the file that commits on success and is closed afterwards."""
        return contextlib.closing(sqlite3.connect(self.path))

    def version(self) -> int:
        with self.connect() as db:
            return db.execute("SELECT schema_version FROM meta").fetchone()[0]

    def test_opening_a_new_path_creates_the_file_at_the_current_schema(self):
        with archive.Archive.open(self.path):
            pass
        self.assertTrue(self.path.exists())
        self.assertEqual(self.version(), archive.SCHEMA_VERSION)

    def test_reopening_keeps_the_schema_and_the_data(self):
        with archive.Archive.open(self.path):
            pass
        with self.connect() as db:
            db.execute("INSERT INTO clubs (uid, name, short_name, nation_id) VALUES (1, 'Hull City', 'Hull', 5)")
            db.commit()
        with archive.Archive.open(self.path):
            pass
        self.assertEqual(self.version(), archive.SCHEMA_VERSION)
        with self.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM clubs").fetchone()[0], 1)

    def test_a_newer_schema_is_refused_and_left_alone(self):
        with archive.Archive.open(self.path):
            pass
        with self.connect() as db:
            db.execute("UPDATE meta SET schema_version = 99")
            db.commit()
        with self.assertRaises(archive.ArchiveError) as caught:
            archive.Archive.open(self.path)
        self.assertIn("newer", str(caught.exception))
        self.assertEqual(self.version(), 99)


if __name__ == "__main__":
    unittest.main()
