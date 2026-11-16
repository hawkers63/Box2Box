# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Exports for Box2Box: one competition and season to an Excel workbook, a web page or CSV files.

The user chose one export per competition and season, saved in Documents\\Box2Box (14 Nov 2026).
Every export says where its data came from and how complete it is: the save, its in-game date,
the coverage counts, whether the zones are the game's or estimated, and any reader warnings.

Everything here is pure apart from the final writes, so it runs on a worker thread and is tested
without a window (see test_fm_export.py). Each file is written under a temporary name and then
moved into place, so a failed export never leaves half a file behind, and a file that is open in
Excel is left as it was.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from fmsave import Fixture
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

import fm_data as fd
import palette
from palette import ZONE_LEGEND, zone_legend

EXCEL, HTML, CSV = "xlsx", "html", "csv"
KINDS = {EXCEL: "Excel workbook", HTML: "web page", CSV: "CSV files"}

EN_DASH = "–"   # CSV scores use it: Excel reads "2-1" in a CSV as the 2nd of January
UNVERIFIED = ("Unverified build: fmsave reads this save with the nearest known layouts, so treat "
              "every value as unconfirmed until it has been checked against the game.")
GROUPING_NOTES = {
    fd.GROUP_BY_WEEK: "Grouped by calendar week, starting on Monday.",
    fd.GROUP_BY_MATCHDAY: "Grouped by matchday or cup round.",
    fd.GROUP_BY_DATE: "Grouped by date.",
}
GRID_NOTE = ("Rows are home teams, columns away teams. Green: home win · amber: draw · red: away win · "
             "blue: mixed results · purple n/a: played, but no score could be recovered · "
             "grey date: still to play.")
NA_NOTE = "n/a = played, but no score could be recovered from the save."


class ExportFailed(Exception):
    """An export could not be written. The message is written for the person using the app."""


@dataclass(frozen=True, slots=True)
class ExportRequest:
    """What to export: one competition and season of a loaded save, as the app shows it."""

    dataset: fd.Dataset
    competition_id: int
    season: int | None
    names: Mapping[int, str] = field(default_factory=dict)
    focus: int | None = None
    group_by: str = fd.GROUP_BY_WEEK
    exported_at: dt.datetime | None = None      # None means now
    theme: palette.Theme = palette.MIDNIGHT_EMERALD     # the colours of the window it was made in


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Everything an export shows, worked out once from a request."""

    title: str
    season_label: str
    stem: str
    source_line: str
    group_by: str
    fixtures: tuple[Fixture, ...]
    labels: Mapping[int, str]
    coverage: fd.Coverage
    standings: fd.Standings
    grid: fd.Grid | None
    team_count: int
    results: tuple[fd.TimelineRow, ...]
    focus: int | None
    focus_label: str
    focus_coverage: fd.Coverage | None
    focus_results: tuple[fd.TimelineRow, ...]
    details: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]
    unverified: bool
    theme: palette.Theme


# --------------------------------------------------------------------------- shaping


def snapshot(request: ExportRequest) -> Snapshot:
    ds, competition_id, season = request.dataset, request.competition_id, request.season
    comp = ds.by_id[competition_id]
    info = ds.info
    fixtures = fd.season_fixtures(ds, competition_id, season)
    labels = fd.team_labels(fixtures)
    title = fd.competition_title(comp, request.names)
    season_text = fd.season_label(season, fixtures)
    cover = fd.coverage(fixtures)
    table = fd.standings(ds, competition_id, season, fixtures, labels)
    focus = request.focus if request.focus in labels else None
    focus_label = labels[focus] if focus is not None else ""
    exported = request.exported_at or dt.datetime.now()

    source = [info.file_name]
    if info.game_date:
        source.append(f"in-game date {_long_date(info.game_date)}")
    source.append(f"{info.game} build {info.build}" + ("" if info.known_build else " (unverified build)"))
    ids = f"competition id {comp.id}" + (f", database id {comp.database_id}" if comp.database_id is not None else "")
    details = [
        ("Competition", f"{title} ({ids})"),
        ("Season", season_text),
        ("Save", info.file_name),
        ("In-game date", _long_date(info.game_date) if info.game_date else "unknown"),
        ("Game and build", f"{info.game} {info.build}"),
        ("Managed club", info.managed_club_name or "not found"),
        ("Followed team", focus_label or "none"),
        ("Fixtures", cover.describe()),
        ("Table", table.note),
        ("Zones", table.zones_note or "none shown"),
        ("Read with", f"fmsave {info.fmsave_version}"),
        ("Exported", f"{_long_date(exported.date())} at {exported:%H:%M} by Box2Box, which only reads "
                     "saves and never changes them"),
    ]
    if not info.known_build:
        details.insert(5, ("Build check", UNVERIFIED))
    return Snapshot(
        title=title,
        season_label=season_text,
        stem=file_stem(title, season_text, info.game_date),
        source_line=" · ".join(source),
        group_by=request.group_by,
        fixtures=fixtures,
        labels=labels,
        coverage=cover,
        standings=table,
        grid=fd.fixture_grid(fixtures, labels, fd.team_labels(fixtures, short=True)),
        team_count=len(fd.teams_in(fixtures)),
        results=tuple(fd.timeline(fixtures, labels, group_by=request.group_by)),
        focus=focus,
        focus_label=focus_label,
        focus_coverage=(fd.coverage(f for f in fixtures if focus in (f.home_team_id, f.away_team_id))
                        if focus is not None else None),
        focus_results=(tuple(fd.timeline(fixtures, labels, group_by=request.group_by, focus_team=focus))
                       if focus is not None else ()),
        details=tuple(details),
        warnings=tuple(info.warnings),
        unverified=not info.known_build,
        theme=request.theme,
    )


_UNSAFE_IN_NAMES = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def file_stem(title: str, season_text: str, game_date: dt.date | None) -> str:
    """'Championship 2026-27 (2026-07-16)': safe as a Windows file name, and different for each
    in-game date, so exporting a later save of the same season keeps the earlier export."""
    stem = f"{title} {season_text}".replace("/", "-")
    if game_date:
        stem += f" ({game_date:%Y-%m-%d})"
    stem = re.sub(r"\s+", " ", _UNSAFE_IN_NAMES.sub("-", stem)).strip().rstrip(". ")
    return stem[:150] or "Box2Box export"


def zone_meaning(zone: str) -> str:
    return next((meaning for z, _, meaning in ZONE_LEGEND if z == zone), "")


def table_legend(snap: Snapshot) -> str:
    legend = zone_legend({r.zone for _, rows in snap.standings.groups for r in rows})
    return f"Pos colours: {legend}." if legend else ""


# --------------------------------------------------------------------------- writing


def export(kind: str, request: ExportRequest, folder: Path) -> Path:
    """Write one export into folder and return where it went: a file, or for CSV a folder.

    Raises:
        ExportFailed: The export could not be written, with a message for the user.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown export kind {kind!r}")
    snap = snapshot(request)
    _make_folder(folder)
    if kind == EXCEL:
        target = folder / f"{snap.stem}.xlsx"
        book = workbook(snap)
        _write_safely(target, lambda temporary: book.save(temporary))
    elif kind == HTML:
        target = folder / f"{snap.stem}.html"
        page = web_page(snap)
        _write_safely(target, lambda temporary: temporary.write_text(page, encoding="utf-8"))
    else:
        target = folder / snap.stem
        _make_folder(target)
        for name, rows in csv_tables(snap).items():
            _write_safely(target / f"{name}.csv", lambda temporary, rows=rows: _write_csv(temporary, rows))
    return target


def _make_folder(folder: Path) -> None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportFailed(f"Could not create the folder {folder}: {exc.strerror or exc}") from exc


def _write_safely(target: Path, write: Callable[[Path], object]) -> None:
    temporary = target.with_name(f"{target.stem}.partial{target.suffix}")
    try:
        write(temporary)
        os.replace(temporary, target)
    except PermissionError as exc:
        raise ExportFailed(f"{target.name} is open in another program, probably Excel. "
                           "Close it and export again.") from exc
    except OSError as exc:
        raise ExportFailed(f"Could not write {target.name}: {exc.strerror or exc}") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _write_csv(path: Path, rows: Iterable[Sequence[object]]) -> None:
    # A byte-order mark makes Excel read the file as UTF-8, so names such as Kroměříž survive.
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerows(rows)


# --------------------------------------------------------------------------- CSV


def csv_tables(snap: Snapshot) -> dict[str, list[list[object]]]:
    """The rows of each CSV file, by file name: Results, Table, Grid and About."""
    labels = snap.labels
    results: list[list[object]] = [["Date", "Kick-off", "Round", "Home", "Away", "Home goals", "Away goals",
                                    "Score", "Status", "Neutral ground", "Home team id", "Away team id"]]
    for f in sorted(snap.fixtures, key=lambda f: (_when(f), labels.get(f.home_team_id, ""))):
        kind = fd.result_kind(f)
        results.append([
            f.date.isoformat() if f.date else "",
            f"{f.kick_off_time:%H:%M}" if f.kick_off_time else "",
            fd.round_text(f),
            labels.get(f.home_team_id, f"Team {f.home_team_id}"),
            labels.get(f.away_team_id, f"Team {f.away_team_id}"),
            f.home_goals if fd.has_score(f) else "",
            f.away_goals if fd.has_score(f) else "",
            _csv_score(f),
            {fd.SCHEDULED: "To play", fd.UNAVAILABLE: "Played, score not recovered"}.get(kind, "Played"),
            {True: "Yes", False: "No"}.get(f.is_neutral_venue, ""),
            f.home_team_id,
            f.away_team_id,
        ])

    grouped = len(snap.standings.groups) > 1
    table: list[list[object]] = [(["Group"] if grouped else [])
                                 + ["Pos", "Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts", "Form", "Zone"]]
    for title, rows in snap.standings.groups:
        for r in rows:
            table.append(([title] if grouped else []) + [
                r.position, r.team, r.played, r.won, r.drawn, r.lost, r.goals_for, r.goals_against,
                r.goal_difference, r.points, r.form, zone_meaning(r.zone)])

    grid = snap.grid
    if grid is None:
        grid_rows: list[list[object]] = [[f"This season has {snap.team_count} teams, too many for a grid "
                                          f"(the limit is {fd.MAX_GRID_TEAMS})."]]
    else:
        grid_rows = [["Home \\ Away", *grid.column_labels]]
        for label, cells in zip(grid.row_labels, grid.cells):
            grid_rows.append([label, *(" / ".join(_csv_grid_text(f) for f in cell.fixtures) for cell in cells)])

    about: list[list[object]] = [["Field", "Value"], *([label, value] for label, value in snap.details)]
    about += [["Reader warning", warning] for warning in snap.warnings]
    return {"Results": results, "Table": table, "Grid": grid_rows, "About": about}


def _csv_score(f: Fixture) -> str:
    kind = fd.result_kind(f)
    if kind == fd.SCHEDULED:
        return ""
    if kind == fd.UNAVAILABLE:
        return "n/a"
    return f"{f.home_goals}{EN_DASH}{f.away_goals}"


def _csv_grid_text(f: Fixture) -> str:
    if fd.result_kind(f) == fd.SCHEDULED:
        return f.date.isoformat() if f.date else "tbc"
    return _csv_score(f)


# --------------------------------------------------------------------------- Excel

TABLE_HEADERS = ("Pos", "Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts", "Form")
RESULT_HEADERS = ("Date", "KO", "Home", "Score", "Away", "Round")
NOTE_GREY = "#555555"
HEADER_BG = "#e5e7eb"
CENTRE = Alignment(horizontal="center", vertical="center")
THIN = Side(style="thin", color="FF9CA3AF")


# --------------------------------------------------------------------------- copy for a post


@dataclass(frozen=True, slots=True)
class Post:
    """One "Copy for a post" item: the same content as Markdown (Reddit, Discord) and as HTML (rich editors)."""

    title: str
    markdown: str
    html: str


class _Strong(str):
    """A cell to show in bold: the followed club."""


def _md_cell(cell: object) -> str:
    text = str(cell).replace("|", "\\|")
    return f"**{text}**" if isinstance(cell, _Strong) else text


def _html_cell(cell: object, tag: str = "td") -> str:
    text = html.escape(str(cell))
    return f"<{tag}><b>{text}</b></{tag}>" if isinstance(cell, _Strong) else f"<{tag}>{text}</{tag}>"


def _post(title: str, header: Sequence[str], align: str, rows: Sequence[Sequence[object]], footer: str,
          after: str = "") -> Post:
    """The same rows as a Markdown table and as a plain HTML table (no styles: forums strip them), with an
    optional line after the table."""
    markdown = [f"**{title}**", "", "| " + " | ".join(header) + " |", align]
    markdown += ["| " + " | ".join(_md_cell(c) for c in row) + " |" for row in rows]
    markdown += (["", after] if after else []) + ["", f"*{footer}*"]
    page = [f"<p><b>{html.escape(title)}</b></p>", "<table>", "<thead>",
            "<tr>" + "".join(_html_cell(h, "th") for h in header) + "</tr>", "</thead>", "<tbody>"]
    page += ["<tr>" + "".join(_html_cell(c) for c in row) + "</tr>" for row in rows]
    page += ["</tbody>", "</table>"] + ([f"<p>{html.escape(after)}</p>"] if after else [])
    page += [f"<p><i>{html.escape(footer)}</i></p>"]
    return Post(title, "\n".join(markdown), "\n".join(page))


def post_table(snap: Snapshot) -> Post:
    """The league table, for a post."""
    rows = []
    for _, group in snap.standings.groups:
        for r in group:
            gd = r.goal_difference
            rows.append([r.position, _Strong(r.team) if r.team_id == snap.focus else r.team, r.played, r.won, r.drawn,
                         r.lost, r.goals_for, r.goals_against, f"{gd:+d}" if gd else "0", r.points, " ".join(r.form)])
    return _post(f"{snap.title} {snap.season_label}",
                 ["Pos", "Club", "P", "W", "D", "L", "GF", "GA", "GD", "Pts", "Form"],
                 "|--:|:--|--:|--:|--:|--:|--:|--:|--:|--:|:--|", rows, _post_footer(snap))


def post_team_results(snap: Snapshot) -> Post | None:
    """The followed club's played matches with running points, its goals first; None without one."""
    if snap.focus is None:
        return None
    rows = []
    for r in snap.focus_results:
        f = r.fixture
        if f is None or not f.played:
            continue
        home = f.home_team_id == snap.focus
        mine, theirs = (f.home_goals, f.away_goals) if home else (f.away_goals, f.home_goals)
        score = f"{mine}-{theirs}" if fd.has_score(f) else "n/a"
        rows.append([r.date, r.away if home else r.home, "H" if home else "A", score, r.result, r.points])
    after = ""
    coming = fd.next_match(snap.fixtures, snap.focus)
    if coming is not None:
        home = coming.home_team_id == snap.focus
        opponent = snap.labels.get(coming.away_team_id if home else coming.home_team_id, "")
        when = f", {coming.date:%a} {coming.date.day} {coming.date:%b}" if coming.date else ""
        after = f"Next: {opponent} ({'H' if home else 'A'}){when}"
    return _post(f"{snap.focus_label}: {snap.title} {snap.season_label}",
                 ["Date", "Opponent", "H/A", "Score", "Res", "Pts"], "|:--|:--|:-:|:-:|:-:|--:|", rows,
                 _post_footer(snap), after)


def post_recent_results(snap: Snapshot) -> Post | None:
    """The latest group of the Results grouping (week, matchday or date) with a played match; None if none."""
    groups: list[tuple[str, list[fd.TimelineRow]]] = []
    for r in snap.results:
        if r.is_heading:
            groups.append((r.heading.split("   ·   ")[0], []))
        elif groups:
            groups[-1][1].append(r)
    latest = next(((heading, rows) for heading, rows in reversed(groups)
                   if any(r.fixture is not None and r.fixture.played for r in rows)), None)
    if latest is None:
        return None
    heading, rows = latest
    return _post(f"{snap.title} {snap.season_label}: {heading}", ["Date", "Home", "Score", "Away"],
                 "|:--|--:|:-:|:--|", [[r.date, r.home, r.score, r.away] for r in rows], _post_footer(snap))


def _post_footer(snap: Snapshot) -> str:
    """How complete the data behind a post is, so a reader is never misled by a missing score."""
    return f"In-game date {dict(snap.details)['In-game date']} · {snap.coverage.describe()}"


def workbook(snap: Snapshot) -> Workbook:
    """Table, Grid, Results, the followed team's results when one is followed, and About."""
    book = Workbook()
    table = book.active
    table.title = "Table"
    _xl_table(table, snap)
    _xl_grid(book.create_sheet("Grid"), snap)
    _xl_results(book.create_sheet("Results"), snap, snap.results, team=False)
    if snap.focus is not None:
        name = _sheet_name(snap.focus_label, {"Table", "Grid", "Results", "About"})
        _xl_results(book.create_sheet(name), snap, snap.focus_results, team=True)
    _xl_about(book.create_sheet("About"), snap)
    return book


@lru_cache(maxsize=None)
def _fill(colour: str) -> PatternFill:
    argb = "FF" + colour.lstrip("#").upper()
    return PatternFill(fill_type="solid", start_color=argb, end_color=argb)


@lru_cache(maxsize=None)
def _font(colour: str | None = None, bold: bool = False, size: float | None = None, italic: bool = False) -> Font:
    return Font(color=("FF" + colour.lstrip("#").upper()) if colour else None, bold=bold, size=size, italic=italic)


def _paint(cell, colours: tuple[str | None, str | None], *, bold: bool = False) -> None:
    background, text = colours
    if background:
        cell.fill = _fill(background)
    if text or bold:
        cell.font = _font(text, bold)


def _sheet_top(sheet: Worksheet, snap: Snapshot, heading: str, notes: Iterable[str]) -> int:
    """Title, source and notes at the top of a sheet. Returns the row for the column headers."""
    sheet.cell(row=1, column=1, value=f"{snap.title} {snap.season_label}: {heading}").font = _font(bold=True, size=14)
    sheet.cell(row=2, column=1, value=snap.source_line).font = _font(NOTE_GREY)
    row = 3
    for note in notes:
        if note:
            sheet.cell(row=row, column=1, value=note).font = _font(NOTE_GREY, italic=True)
            row += 1
    return row + 1


def _header_row(sheet: Worksheet, row: int, headers: Sequence[str], *, left: Iterable[int] = ()) -> None:
    """Column headers, centred apart from the columns in left (1-based), which hold names."""
    left = set(left)
    for column, text in enumerate(headers, start=1):
        cell = sheet.cell(row=row, column=column, value=text)
        cell.fill = _fill(HEADER_BG)
        cell.font = _font(bold=True)
        cell.border = Border(bottom=THIN)
        cell.alignment = Alignment(horizontal="left") if column in left else CENTRE


def _heading_row(sheet: Worksheet, row: int, text: str, width: int, heading: tuple[str, str]) -> None:
    for column in range(1, width + 1):
        sheet.cell(row=row, column=column).fill = _fill(heading[0])
    sheet.cell(row=row, column=1, value=text).font = _font(heading[1], bold=True)


def _widths(sheet: Worksheet, widths: Sequence[float]) -> None:
    for column, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width


def _text_width(texts: Iterable[object], minimum: float = 6, maximum: float = 48) -> float:
    widest = max((len(str(text)) for text in texts if text is not None), default=0)
    return min(max(minimum, widest + 2), maximum)


def _xl_table(sheet: Worksheet, snap: Snapshot) -> None:
    standings, theme = snap.standings, snap.theme
    row = _sheet_top(sheet, snap, "table",
                     [snap.coverage.describe(), standings.note, standings.zones_note, table_legend(snap)])
    header = row
    _header_row(sheet, row, TABLE_HEADERS, left=[2])
    width = len(TABLE_HEADERS)
    for title, rows in standings.groups:
        if title:
            row += 1
            _heading_row(sheet, row, title, width, theme.heading)
        for r in rows:
            row += 1
            values = (r.position, r.team, r.played, r.won, r.drawn, r.lost, r.goals_for, r.goals_against,
                      r.goal_difference, r.points, " ".join(r.form))
            for column, value in enumerate(values, start=1):
                cell = sheet.cell(row=row, column=column, value=value)
                if column != 2:
                    cell.alignment = CENTRE
                if r.team_id == snap.focus:
                    _paint(cell, theme.focus, bold=True)
            sheet.cell(row=row, column=9).number_format = "+0;-0;0"
            if r.zone in theme.zones:
                _paint(sheet.cell(row=row, column=1), theme.zones[r.zone], bold=True)
    teams = [r.team for _, rows in standings.groups for r in rows]
    _widths(sheet, [6, _text_width(teams, 18)] + [6] * 8 + [7, 14])
    sheet.freeze_panes = sheet.cell(row=header + 1, column=1)


def _xl_grid(sheet: Worksheet, snap: Snapshot) -> None:
    grid = snap.grid
    notes = [GRID_NOTE, f"{snap.focus_label} is highlighted in blue." if snap.focus is not None else ""]
    row = _sheet_top(sheet, snap, "fixture grid", notes)
    if grid is None:
        sheet.cell(row=row, column=1, value=f"This season has {snap.team_count} teams, too many for a grid "
                                            f"(the limit is {fd.MAX_GRID_TEAMS}).")
        return
    top = row
    colours, focus = snap.theme.colours, snap.theme.focus
    _header_row(sheet, top, ["Home \\ Away", *grid.column_labels], left=[1])
    focus_index = grid.team_ids.index(snap.focus) if snap.focus in grid.team_ids else None
    for r, (label, cells) in enumerate(zip(grid.row_labels, grid.cells), start=1):
        name = sheet.cell(row=top + r, column=1, value=label)
        name.font = _font(bold=True)
        for c, item in enumerate(cells, start=2):
            cell = sheet.cell(row=top + r, column=c, value=item.text or None)
            cell.alignment = CENTRE
            if item.kind in colours:
                _paint(cell, colours[item.kind])
        if focus_index == r - 1:
            _paint(name, focus, bold=True)
    if focus_index is not None:
        _paint(sheet.cell(row=top, column=focus_index + 2), focus, bold=True)
    widths = [_text_width(grid.row_labels, 18)]
    for c, label in enumerate(grid.column_labels):
        widths.append(_text_width([label] + [cells[c].text for cells in grid.cells], 7, 24))
    _widths(sheet, widths)
    sheet.freeze_panes = sheet.cell(row=top + 1, column=2)


def _xl_results(sheet: Worksheet, snap: Snapshot, rows: Sequence[fd.TimelineRow], *, team: bool) -> None:
    headers = RESULT_HEADERS + (("Res", "Pts") if team else ())
    if team:
        notes = [f"{snap.focus_label}: {snap.focus_coverage.describe()}",
                 f"Res and Pts are for {snap.focus_label}: 3 points for a win, 1 for a draw. * = a played match "
                 "has no recoverable score, so the total is a minimum.", NA_NOTE]
    else:
        notes = [snap.coverage.describe(), GROUPING_NOTES.get(snap.group_by, ""), NA_NOTE]
    row = _sheet_top(sheet, snap, f"{snap.focus_label} results" if team else "results", notes)
    header = row
    colours, name_ink = snap.theme.colours, palette.ink_on_white(snap.theme.focus)    # the sheet itself is white
    _header_row(sheet, row, headers, left=[3, 5])
    for item in rows:
        row += 1
        if item.is_heading:
            _heading_row(sheet, row, item.heading, len(headers), snap.theme.heading)
            continue
        f = item.fixture
        values = [f.date, f.kick_off_time, item.home, item.score, item.away, item.round]
        if team:
            values += [item.result, int(item.points) if item.points.isdigit() else item.points]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=column, value=value if value != "" else None)
            if column not in (3, 5):
                cell.alignment = CENTRE
        sheet.cell(row=row, column=1).number_format = "ddd d mmm yyyy"
        sheet.cell(row=row, column=2).number_format = "hh:mm"
        if team and item.result:
            _paint(sheet.cell(row=row, column=4), colours[item.result])
            _paint(sheet.cell(row=row, column=7), colours[item.result])
        elif item.kind in (fd.UNAVAILABLE, fd.SCHEDULED):
            _paint(sheet.cell(row=row, column=4), colours[item.kind])
        if snap.focus is not None:
            for column, team_id in ((3, item.home_id), (5, item.away_id)):
                if team_id == snap.focus:
                    sheet.cell(row=row, column=column).font = _font(name_ink, bold=True)
    names = [item.home for item in rows] + [item.away for item in rows]
    _widths(sheet, [16, 7, _text_width(names, 18), 8, _text_width(names, 18), 14, 6, 6][:len(headers)])
    sheet.freeze_panes = sheet.cell(row=header + 1, column=1)


def _xl_about(sheet: Worksheet, snap: Snapshot) -> None:
    sheet.cell(row=1, column=1, value=f"{snap.title} {snap.season_label}: about this export").font = _font(bold=True, size=14)
    wrap = Alignment(wrap_text=True, vertical="top")
    row = 3
    for label, value in snap.details:
        sheet.cell(row=row, column=1, value=label).font = _font(bold=True)
        sheet.cell(row=row, column=1).alignment = Alignment(vertical="top")
        sheet.cell(row=row, column=2, value=value).alignment = wrap
        row += 1
    if snap.warnings:
        row += 1
        sheet.cell(row=row, column=1, value="Reader warnings").font = _font(bold=True)
        for warning in snap.warnings:
            sheet.cell(row=row, column=2, value=warning).alignment = wrap
            row += 1
    _widths(sheet, [18, 110])


_UNSAFE_IN_SHEETS = re.compile(r"[\[\]:*?/\\]")


def _sheet_name(label: str, taken: set[str]) -> str:
    """A worksheet name Excel accepts: at most 31 characters, none of []:*?/\\, not already used."""
    name = _UNSAFE_IN_SHEETS.sub("-", label).strip("' ")[:31].strip()
    if not name or name.casefold() in {t.casefold() for t in taken}:
        return "Followed team"
    return name


# --------------------------------------------------------------------------- web page


def web_page(snap: Snapshot) -> str:
    """A standalone page: its styles and a small team filter are built in, nothing is fetched."""
    e = html.escape
    sections = [("table", "Table"), ("grid", "Grid"), ("results", "Results")]
    if snap.focus is not None:
        sections.append(("team", f"{snap.focus_label} results"))
    sections.append(("about", "About this export"))
    notes = [snap.coverage.describe()] + ([UNVERIFIED] if snap.unverified else [])
    parts = [
        "<!doctype html>",
        '<html lang="en-GB">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{e(snap.title)} {e(snap.season_label)} · Box2Box</title>",
        f"<style>{_css(snap.theme)}</style>",
        "</head>",
        "<body>",
        "<main>",
        f"<h1>{e(snap.title)} <span>{e(snap.season_label)}</span></h1>",
        f'<p class="meta">{e(snap.source_line)}</p>',
        '<ul class="notes">' + "".join(f"<li>{e(note)}</li>" for note in notes) + "</ul>",
        "<nav>" + "".join(f'<a href="#{key}">{e(name)}</a>' for key, name in sections) + "</nav>",
        _html_table(snap),
        _html_grid(snap),
        _html_results(snap, "results", "Results", snap.results, team=False),
    ]
    if snap.focus is not None:
        parts.append(_html_results(snap, "team", f"{snap.focus_label} results", snap.focus_results, team=True))
    parts += [
        _html_about(snap),
        "<footer>Made with Box2Box, which reads Football Manager saves with fmsave and never changes them.</footer>",
        "</main>",
        f"<script>{_FILTER_SCRIPT}</script>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts) + "\n"


def _kind_class(kind: str) -> str:
    return "k-" + {"?": "q"}.get(kind, kind)


def _attr(name: str, value: str) -> str:
    """' class="c"', or '' when there is no value."""
    return f' {name}="{html.escape(value, quote=True)}"' if value else ""


def _header_cells(headers: Sequence[str], names: Iterable[str]) -> str:
    """Header cells, centred apart from the ones holding names."""
    names = set(names)
    return "".join(f"<th{_attr('class', '' if h in names else 'c')}>{html.escape(h)}</th>" for h in headers)


# The page's own colours are CSS variables, written from the theme by _css below.
_BASE_CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 14px/1.45 "Segoe UI", system-ui, sans-serif; }
main { max-width: 1600px; margin: 0 auto; padding: 20px 16px 40px; }
h1 { font-size: 26px; margin: 0 0 4px; } h1 span { color: var(--muted); font-weight: 400; }
h2 { font-size: 19px; color: var(--section); margin: 32px 0 6px; }
.meta, .notes, .note, footer { color: var(--muted); }
.notes { margin: 8px 0 0; padding-left: 18px; } .note { margin: 0 0 8px; font-size: 13px; }
nav { margin: 14px 0 0; display: flex; flex-wrap: wrap; gap: 6px 16px; }
nav a, a { color: var(--link); }
.scroll { overflow: auto; max-width: 100%; max-height: 85vh; }
table { border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { border: 1px solid var(--grid); padding: 3px 8px; white-space: nowrap; }
thead th { background: var(--head); position: sticky; top: 0; z-index: 1; }
td.c, th.c { text-align: center; }
table.grid td { text-align: center; min-width: 52px; }
table.grid tbody th { text-align: left; background: var(--head); position: sticky; left: 0; }
table.grid thead th:first-child { left: 0; z-index: 2; }
input[type=search] { background: var(--field); color: inherit; border: 1px solid var(--field-border); border-radius: 6px;
  padding: 6px 10px; width: min(320px, 100%); margin: 0 0 10px; font: inherit; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; } dt { font-weight: 600; } dd { margin: 0; }
footer { margin-top: 36px; font-size: 13px; }
"""


def _css(theme: palette.Theme) -> str:
    """The page's stylesheet in a theme's colours: variables for the page itself, then a class for
    each result, the headings, the followed team and each zone."""
    variables = {"bg": theme.table[0], "text": theme.table[1], "muted": theme.page_muted, "section": theme.section,
                 "link": theme.link, "grid": theme.grid_line, "head": theme.sheet_heading[0],
                 "field": theme.page_field[0], "field-border": theme.page_field[1]}
    root = ":root { color-scheme: dark; " + " ".join(f"--{name}: {value.lower()};" for name, value in variables.items()) + " }"
    rules = [root, _BASE_CSS]
    for kind, (background, text) in theme.colours.items():
        rules.append(f".{_kind_class(kind)} {{ background: {background};{f' color: {text};' if text else ''} }}")
    rules.append(f"tr.heading td {{ background: {theme.heading[0]}; color: {theme.heading[1]}; font-weight: 600; }}")
    rules.append(f"tr.focus td, tr th.focus, thead th.focus {{ background: {theme.focus[0]}; color: {theme.focus[1]}; "
                 "font-weight: 600; }")
    rules.append("td.team-focus { color: var(--link); font-weight: 600; }")
    for zone, (background, text) in theme.zones.items():
        # Same specificity as the focus row's rule and later, so a zone keeps its colour there too.
        rules.append(f"tr td.z-{zone} {{ background: {background}; color: {text}; font-weight: 600; }}")
    return "\n".join(rules)


def _html_table(snap: Snapshot) -> str:
    e = html.escape
    standings = snap.standings
    out = ['<section id="table">', "<h2>Table</h2>"]
    for note in (standings.note, standings.zones_note, table_legend(snap)):
        if note:
            out.append(f'<p class="note">{e(note)}</p>')
    out.append('<div class="scroll"><table class="standings"><thead><tr>'
               + _header_cells(TABLE_HEADERS, ["Team"]) + "</tr></thead><tbody>")
    for title, rows in standings.groups:
        if title:
            out.append(f'<tr class="heading"><td colspan="{len(TABLE_HEADERS)}">{e(title)}</td></tr>')
        for r in rows:
            zone = f" z-{r.zone}" if r.zone in snap.theme.zones else ""
            focus = _attr("class", "focus" if r.team_id == snap.focus else "")
            gd = r.goal_difference
            cells = [f'<td class="c{zone}">{r.position}</td>', f"<td>{e(r.team)}</td>"]
            cells += [f'<td class="c">{value}</td>' for value in
                      (r.played, r.won, r.drawn, r.lost, r.goals_for, r.goals_against, f"{gd:+d}" if gd else "0",
                       r.points)]
            cells.append(f'<td class="c">{e(" ".join(r.form))}</td>')
            out.append(f"<tr{focus}>{''.join(cells)}</tr>")
    out.append("</tbody></table></div></section>")
    return "\n".join(out)


def _html_grid(snap: Snapshot) -> str:
    e = html.escape
    grid = snap.grid
    out = ['<section id="grid">', "<h2>Fixture grid</h2>", f'<p class="note">{e(GRID_NOTE)}</p>']
    if grid is None:
        out.append(f'<p>This season has {snap.team_count} teams, too many for a grid '
                   f'(the limit is {fd.MAX_GRID_TEAMS}).</p></section>')
        return "\n".join(out)
    focus_index = grid.team_ids.index(snap.focus) if snap.focus in grid.team_ids else None
    head = "".join(f"<th{_attr('class', 'c focus' if i == focus_index else 'c')}>{e(label)}</th>"
                   for i, label in enumerate(grid.column_labels))
    out.append(f'<div class="scroll"><table class="grid"><thead><tr><th>Home \\ Away</th>{head}</tr></thead><tbody>')
    for r, (label, cells) in enumerate(zip(grid.row_labels, grid.cells)):
        row_head = f"<th{_attr('class', 'focus' if r == focus_index else '')}>{e(label)}</th>"
        tds = "".join(f"<td{_attr('class', _kind_class(cell.kind) if cell.kind in snap.theme.colours else '')}>{e(cell.text)}</td>"
                      for cell in cells)
        out.append(f"<tr>{row_head}{tds}</tr>")
    out.append("</tbody></table></div></section>")
    return "\n".join(out)


def _html_results(snap: Snapshot, key: str, title: str, rows: Sequence[fd.TimelineRow], *, team: bool) -> str:
    e = html.escape
    headers = RESULT_HEADERS + (("Res", "Pts") if team else ())
    if team:
        notes = [f"{snap.focus_label}: {snap.focus_coverage.describe()}",
                 f"Res and Pts are for {snap.focus_label}: 3 points for a win, 1 for a draw. * = a played match "
                 "has no recoverable score, so the total is a minimum."]
    else:
        notes = [GROUPING_NOTES.get(snap.group_by, ""), NA_NOTE]
    out = [f'<section id="{key}">', f"<h2>{e(title)}</h2>"]
    out += [f'<p class="note">{e(note)}</p>' for note in notes if note]
    if not team:
        out.append('<input type="search" id="filter" placeholder="Show one team’s matches" aria-label="Filter by team">')
    out.append('<div class="scroll"><table class="results"><thead><tr>'
               + _header_cells(headers, ["Home", "Away"]) + "</tr></thead><tbody>")
    for item in rows:
        if item.is_heading:
            out.append(f'<tr class="heading"><td colspan="{len(headers)}">{e(item.heading)}</td></tr>')
            continue
        if team and item.result:
            score_kind = item.result
        else:
            score_kind = item.kind if item.kind in (fd.UNAVAILABLE, fd.SCHEDULED) else ""
        followed = snap.focus is not None
        home_class = "team-focus" if followed and item.home_id == snap.focus else ""
        away_class = "team-focus" if followed and item.away_id == snap.focus else ""
        cells = [f'<td class="c">{e(item.date)}</td>', f'<td class="c">{e(item.time)}</td>',
                 f"<td{_attr('class', home_class)}>{e(item.home)}</td>",
                 f"<td{_attr('class', 'c ' + _kind_class(score_kind) if score_kind else 'c')}>{e(item.score)}</td>",
                 f"<td{_attr('class', away_class)}>{e(item.away)}</td>",
                 f'<td class="c">{e(item.round)}</td>']
        if team:
            cells += [f"<td{_attr('class', 'c ' + _kind_class(item.result) if item.result else 'c')}>{e(item.result)}</td>",
                      f'<td class="c">{e(item.points)}</td>']
        out.append(f"<tr{_attr('data-teams', f'{item.home}|{item.away}'.casefold())}>{''.join(cells)}</tr>")
    out.append("</tbody></table></div></section>")
    return "\n".join(out)


def _html_about(snap: Snapshot) -> str:
    e = html.escape
    out = ['<section id="about">', "<h2>About this export</h2>", "<dl>"]
    out += [f"<dt>{e(label)}</dt><dd>{e(value)}</dd>" for label, value in snap.details]
    out.append("</dl>")
    if snap.warnings:
        out.append("<h3>Reader warnings</h3><ul>" + "".join(f"<li>{e(w)}</li>" for w in snap.warnings) + "</ul>")
    out.append("</section>")
    return "\n".join(out)


# Shows one team's matches in the Results section; the page works the same without it.
_FILTER_SCRIPT = """
const box = document.getElementById("filter");
if (box) box.addEventListener("input", () => {
  const needle = box.value.trim().toLowerCase();
  const body = document.querySelector("#results tbody");
  let heading = null, shown = 0;
  const close = () => { if (heading) heading.hidden = Boolean(needle) && shown === 0; };
  for (const row of body.rows) {
    if (row.classList.contains("heading")) { close(); heading = row; shown = 0; continue; }
    const hit = !needle || row.dataset.teams.includes(needle);
    row.hidden = !hit;
    if (hit) shown++;
  }
  close();
});
"""


# --------------------------------------------------------------------------- helpers


def _when(f: Fixture) -> tuple:
    return (f.date is None, f.date or dt.date.min, f.kick_off_time is None, f.kick_off_time or dt.time.min)


def _long_date(day: dt.date) -> str:
    return f"{day.day} {day:%B %Y}"
