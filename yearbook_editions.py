# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Where a season's Yearbook editions live, and when saving one writes a file. No UI code.

One folder a season under `Yearbooks`, one file an edition, named from the archive's last in-game date for that
volume (the date the title page prints), never from the clock. The folder is the shelf: there is no index.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import archive as arch
import yearbook
import yearbook_pdf

FOLDER_NAME = "Yearbooks"
UNKNOWN_DATE = "date unknown"
_FILE = re.compile(r"^Yearbook .+ \(in-game (\d{1,2} [A-Z][a-z]{2} \d{4})\)\.pdf$")


def date_text(d: dt.date) -> str:
    return f"{d.day} {d:%b %Y}"


def season_folder(root: Path, label: str) -> Path:
    return Path(root) / FOLDER_NAME / label.replace("/", "-")


def edition_file_name(label: str, last_date: dt.date | None) -> str:
    return f"Yearbook {label.replace('/', '-')} (in-game {date_text(last_date) if last_date else UNKNOWN_DATE}).pdf"


@dataclass(frozen=True, slots=True)
class Edition:
    date: dt.date | None
    path: Path

    @property
    def date_label(self) -> str:
        return date_text(self.date) if self.date else UNKNOWN_DATE


def list_editions(root: Path, label: str) -> list[Edition]:
    """The editions saved for a season, newest first; an edition with no known date comes last."""
    folder = season_folder(root, label)
    found = []
    if folder.is_dir():
        for path in folder.iterdir():
            match = _FILE.match(path.name)
            if match and path.is_file():
                found.append(Edition(dt.datetime.strptime(match.group(1), "%d %b %Y").date(), path))
            elif path.is_file() and path.name.endswith(f"(in-game {UNKNOWN_DATE}).pdf"):
                found.append(Edition(None, path))
    return sorted(found, key=lambda e: (e.date is not None, e.date or dt.date.min), reverse=True)


@dataclass(frozen=True, slots=True)
class SavePlan:
    """What saving an edition will do: "new" writes a file, "replace" rewrites the one for this date, "already"
    writes nothing because that edition is saved."""

    action: str
    path: Path
    message: str


def plan_edition(root: Path, label: str, last_date: dt.date | None, rebuild: bool = False) -> SavePlan:
    path = season_folder(root, label) / edition_file_name(label, last_date)
    shown = date_text(last_date) if last_date else UNKNOWN_DATE
    if path.is_file():
        if rebuild:
            return SavePlan("replace", path, f"Updated the {shown} edition.")
        return SavePlan("already", path, "This edition is already saved.")
    others = [e for e in list_editions(root, label) if e.path != path]
    if others:
        return SavePlan("new", path, f"Saved a new edition, {shown}. The {others[0].date_label} edition is unchanged.")
    return SavePlan("new", path, f"Saved the {shown} edition.")


def save_edition(book: arch.Archive, season: int, names: Mapping[int, str], root: Path, rebuild: bool = False,
                 marked_club: int | None = None) -> SavePlan:
    """Save the season's Yearbook as an edition: nothing is built when that edition already exists (unless
    `rebuild`). The PDF is written under a temporary name and moved into place, so a failure leaves every edition
    as it was."""
    label = dict(book.season_labels())[season]
    plan = plan_edition(root, label, book.coverage(season).last_date, rebuild)
    if plan.action == "already":
        return plan
    built = yearbook.build_yearbook(book, season, names, marked_club)
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    yearbook_pdf.render(built, plan.path)
    return plan
