# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""The Yearbook's page model as pages to read in the window: a heading, the lines the PDF would print, a table of the
same columns, and the footnotes that travel with it. No UI code and no second layout: the wording comes from yearbook
(the same functions the PDF uses), so the sheet cannot disagree with the book.
"""

from __future__ import annotations

from dataclasses import dataclass

import yearbook as yb


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
