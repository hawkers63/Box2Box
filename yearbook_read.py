# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""The Yearbook's page model as pages to read in the window: a heading, the lines the PDF would print, a table of the
same columns, and the footnotes that travel with it. No UI code and no second layout: the wording comes from yearbook
(the same functions the PDF uses), so the sheet cannot disagree with the book.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import archive as arch
import yearbook as yb

STRIP_SPAN = 7               # chapters drawn in the strip at once: the current one and its neighbours
STRIP_CHARS = 22             # a chapter's name in the strip is cut to this many characters
BOOKMARK_LIMIT = 50          # bookmarks kept in the settings file; the oldest go first
PAGE_KEY_LIMIT = 200         # a longer page key in the settings file is not one this program wrote
SPREAD, SINGLE = "spread", "single"


@dataclass(frozen=True, slots=True)
class ReadPage:
    kind: str                                  # title, league, cup, places, final, home or away
    competition: str
    heading: str
    lines: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    notes: tuple[str, ...] = ()
    marked_rows: tuple[int, ...] = ()          # rows to show in bold
    page_key: str = ""                         # what the page shows, by archive identity; never its place in the book
    chart: yb.Trajectory | None = None         # a trajectory page's chart, drawn by the window from yearbook_chart


def league_key(page: yb.LeaguePage) -> str:
    key = f"league/{page.competition_key}/{page.matchweek}"
    return f"{key}/rescheduled/{page.when.isoformat()}" if page.rescheduled else key


def cup_key(page: yb.CupBlock) -> str:
    return f"cup/{page.competition_key}/{page.when.isoformat()}/{page.round_name}/{page.leg}"


def _match_line(m: yb.BookMatch) -> str:
    return (f"{m.date_text}   " if m.date_text else "") + \
        f"{yb.side_label(m, 'home')} {m.score} {yb.side_label(m, 'away')}" + (f"   {m.note}" if m.note else "")


def _standings(lines) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...], tuple[int, ...]]:
    return (yb.standings_head(lines), tuple(yb.standings_values(t, lines) for t in lines),
            tuple(i for i, t in enumerate(lines) if t.marked))


def _base(competition: str) -> str:
    return competition.removesuffix(" play-offs")


def read_pages(book: yb.Yearbook) -> tuple[list[ReadPage], list[tuple[str, int]]]:
    """(pages, contents): the book's pages in order, and (label, page index) for each place worth jumping to: the
    title page, each competition at its first page (its play-off rounds belong to it), each league's places grid and
    the final tables."""
    pages: list[ReadPage] = []
    contents: list[tuple[str, int]] = []
    seen: set[str] = set()

    def enter(label: str) -> None:
        if label not in seen:
            seen.add(label)
            contents.append((label, len(pages)))

    for page in book.pages:
        if isinstance(page, yb.TitlePage):
            enter("Title page")
            pages.append(ReadPage("title", "", f"Football Yearbook {page.season_label}", tuple(page.coverage_lines),
                                  page_key="title"))
        elif isinstance(page, yb.LeaguePage):
            enter(_base(page.competition))
            head, rows, marked = _standings(page.table) if page.table else ((), (), ())
            pages.append(ReadPage("league", page.competition, f"{page.competition} · {page.heading}",
                                  tuple(_match_line(m) for m in page.matches), head, rows,
                                  (yb.cut_table_note(page.table_note, page.table),) if page.table else (), marked,
                                  league_key(page)))
        elif isinstance(page, yb.CupBlock):
            enter(_base(page.competition))
            head, rows, marked = _standings(page.table) if page.table else ((), (), ())
            notes = ((page.footnote,) if page.footnote else ()) + \
                ((yb.cut_table_note(page.table_note, page.table),) if page.table else ())
            pages.append(ReadPage("cup", page.competition, page.heading, tuple(_match_line(m) for m in page.matches),
                                  head, rows, notes, marked, cup_key(page)))
        elif isinstance(page, yb.PlacesPage):
            enter(f"{page.competition}: How they stood")
            rows = tuple((r.team, *("" if p is None else str(p) for p in r.places), str(r.now)) for r in page.rows)
            pages.append(ReadPage("places", page.competition,
                                  f"{page.competition} · How they stood, matchweeks {page.matchweeks[0]}–{page.matchweeks[-1]}",
                                  (), ("Team", *(str(w) for w in page.matchweeks), "Now"), rows, (yb.places_note(page),),
                                  tuple(i for i, r in enumerate(page.rows) if r.marked), f"places/{page.competition_key}"))
        elif isinstance(page, yb.HonoursPage):
            enter("Honours")
            pages.append(ReadPage("honours", "", "Honours",
                                  tuple(f"{e.competition}: {line}" for e in page.entries for line in e.lines), (), (),
                                  page.notes, page_key="honours"))
        elif isinstance(page, yb.TrajectoryPage):
            enter(f"{page.club}: Season trajectory")
            if not page.charts:
                pages.append(ReadPage("trajectory", "", f"{page.club} ┬À Season trajectory", (page.note,),
                                      page_key="trajectory/note"))
            for n, chart in enumerate(page.charts):
                rows = tuple((str(p.matchweek), f"{yb._day(p.through)} {p.through:%b}", "" if p.place is None else str(p.place))
                             for p in chart.points)
                pages.append(ReadPage("trajectory", chart.competition,
                                      f"{page.club} ┬À Season trajectory ┬À {chart.competition}", (), ("Matchweek", "To", "Place"),
                                      rows, (yb.TRAJECTORY_NOTE,), page_key=f"trajectory/{chart.competition_key or n}", chart=chart))
        elif isinstance(page, yb.FinalTablesPage):
            keys = dict(page.keys)
            strips = dict(page.strips)
            splits = {entry[0]: entry for entry in page.splits}
            xg_notes = dict(page.xg_notes)
            for name, lines in page.tables:
                enter("Final tables")
                head, rows, marked = _standings(lines)
                pages.append(ReadPage("final", name, f"{name} · final table", tuple(strips.get(name, ())), head, rows,
                                      (yb.final_note(lines, xg_notes.get(name, "")),), marked,
                                      f"final/{keys.get(name, 0)}"))
                if name in splits:
                    _, _, home, away = splits[name]
                    for kind, record in (("home", home), ("away", away)):
                        pages.append(ReadPage(kind, name, f"{name} · {kind} record", (), yb.RECORD_HEAD,
                                              tuple(yb.record_values(t) for t in record), (yb.SPLITS_NOTE,),
                                              tuple(i for i, t in enumerate(record) if t.marked),
                                              f"{kind}/{keys.get(name, 0)}"))
    return pages, contents


@dataclass(frozen=True, slots=True)
class Volume:
    """One season's book as the reader shows it, tied to the archive snapshot it was built from: saving it saves
    exactly this book, whatever the archive has banked since."""

    season: int
    archive_id: str                            # the playthrough (Archive.identity)
    coverage: arch.BookCoverage                # the archive's coverage of the season when the book was built
    book: yb.Yearbook
    pages: tuple[ReadPage, ...]
    contents: tuple[tuple[str, int], ...]

    @property
    def season_label(self) -> str:
        return self.book.season_label

    @property
    def edition(self) -> str:
        return self.coverage.last_date.isoformat() if self.coverage.last_date else "unknown"

    @property
    def edition_label(self) -> str:
        d = self.coverage.last_date
        return f"{d.day} {d:%b %Y}" if d else "date unknown"

    def matches(self, coverage: arch.BookCoverage) -> bool:
        """Whether the archive's coverage now is the one this book was built from: the same saves over the same
        span. Whether the season is still in progress is the book's own judgement, so it is not compared."""
        a, b = self.coverage, coverage
        return (a.saves, a.first_date, a.last_date, a.gaps) == (b.saves, b.first_date, b.last_date, b.gaps)


def volume(book: yb.Yearbook, season: int, archive_id: str, coverage: arch.BookCoverage) -> Volume:
    pages, contents = read_pages(book)
    return Volume(season, archive_id, coverage, book, tuple(pages), tuple(contents))


def spreads(count: int) -> list[tuple[int, ...]]:
    """The reader's spreads: the title page alone, then the pages two by two, an odd last page alone. A reader
    spread is two pages of this window side by side, never two printed pages of the PDF."""
    return [(0,)] + [tuple(range(i, min(i + 2, count))) for i in range(1, count, 2)] if count else []


def spread_at(index: int, count: int) -> tuple[int, ...]:
    index = max(0, min(index, count - 1))
    return (0,) if index == 0 else ((index, index + 1)[:min(2, count - index)] if index % 2 else (index - 1, index))


def spread_label(spread: Sequence[int], count: int) -> str:
    if len(spread) == 1:
        return f"Page {spread[0] + 1} of {count}"
    return f"Pages {spread[0] + 1}–{spread[-1] + 1} of {count} · reader spread"


def strip_window(count: int, current: int, span: int = STRIP_SPAN) -> tuple[int, int]:
    """(start, stop) of the chapters the strip draws: `span` of them around the current one, no more."""
    start = max(0, min(current - span // 2, count - span))
    return start, min(count, start + span)


def strip_text(label: str) -> str:
    return label if len(label) <= STRIP_CHARS else label[:STRIP_CHARS - 1].rstrip() + "…"


def page_index(pages: Sequence[ReadPage], page_key: str | None) -> int | None:
    if not page_key:
        return None
    return next((i for i, p in enumerate(pages) if p.page_key == page_key), None)


def reader_mode(value: object) -> str:
    return SPREAD if value == SPREAD else SINGLE


def _slot(archive_id: str, season: int) -> str:
    return f"{archive_id}|{season}"


def _good(entry: object) -> bool:
    return (isinstance(entry, dict) and isinstance(entry.get("page_key"), str)
            and 0 < len(entry["page_key"]) <= PAGE_KEY_LIMIT and isinstance(entry.get("edition", ""), str))


def read_bookmark(stored: object, archive_id: str, season: int) -> str | None:
    """The page key bookmarked for a playthrough's season, or None when the settings hold none in a shape this
    program writes. It is looked up by key, so a newer edition of the same volume reopens at the same page."""
    if not isinstance(stored, dict):
        return None
    entry = stored.get(_slot(archive_id, season))
    return entry["page_key"] if _good(entry) else None


def with_bookmark(stored: object, archive_id: str, season: int, edition: str, page_key: str) -> dict:
    """A new settings value with this bookmark added last; badly shaped entries are dropped and only the newest
    BOOKMARK_LIMIT are kept. The value passed in is not changed."""
    kept = {k: dict(v) for k, v in stored.items() if isinstance(k, str) and _good(v)} if isinstance(stored, dict) else {}
    slot = _slot(archive_id, season)
    kept.pop(slot, None)
    kept[slot] = {"edition": edition, "page_key": page_key}
    return dict(list(kept.items())[-BOOKMARK_LIMIT:])