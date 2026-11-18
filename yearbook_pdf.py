# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Draws the Yearbook page model (yearbook.py) as a PDF with reportlab: A4 portrait, one light, ink-friendly
style, no club badges or tint. The file is written to a temporary name and moved into place, so a failure
never leaves a half-written book and never disturbs an earlier one.
"""

from __future__ import annotations

import math
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

import yearbook as yb

FONT, BOLD = "DejaVuSans", "DejaVuSans-Bold"
INK, MUTED, RULE = "#1a1a1a", "#555555", "#bbbbbb"
# Form letters in three colours that read on white paper (each is at least 4.5:1 against white).
FORM_INK = {"W": "#1b6e2e", "D": "#7a5c00", "L": "#a8261e"}
# Light tints for a table's position cell, one per zone, that black figures read on.
ZONE_TINT = {"promotion": "#bfe3c7", "playoff": "#f1dfa6", "relegation": "#f0bcb6",
             "ucl": "#b9d8f0", "europa": "#d7e8c0"}


class BookDocTemplate(BaseDocTemplate):
    """A document whose flowables may carry an `_outline` = (level, title): the PDF's contents. The bookmark lands on
    the page the flowable was drawn on."""

    def afterFlowable(self, flowable) -> None:
        entry = getattr(flowable, "_outline", None)
        if not entry:
            return
        if entry is getattr(self, "_outline_last", None):
            return
        self._outline_last = entry
        level, title = entry
        self._outline_depth = getattr(self, "_outline_depth", -1)
        level = min(level, self._outline_depth + 1)                 # an outline may not skip a level
        key = f"outline{getattr(self, '_outline_count', 0)}"
        self._outline_count = getattr(self, "_outline_count", 0) + 1
        self._outline_depth = level
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(title, key, level, closed=False)


def _fonts_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))     # a frozen build unpacks its data files here
    return base / "fonts"


def _register_fonts() -> None:
    if FONT in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont(FONT, str(_fonts_dir() / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(BOLD, str(_fonts_dir() / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=BOLD, italic=FONT, boldItalic=BOLD)


def _styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName=FONT, textColor=colors.HexColor(INK))
    return {
        "title": ParagraphStyle("title", fontName=BOLD, fontSize=26, leading=32, alignment=TA_CENTER,
                                textColor=colors.HexColor(INK), spaceAfter=10),
        "line": ParagraphStyle("line", fontSize=10, leading=15, alignment=TA_CENTER, spaceAfter=4, **base),
        "heading": ParagraphStyle("heading", fontName=BOLD, fontSize=13, leading=17, alignment=TA_CENTER,
                                  textColor=colors.HexColor(INK), spaceBefore=4, spaceAfter=6),
        "small": ParagraphStyle("small", fontSize=7.5, leading=10, textColor=colors.HexColor(MUTED), fontName=FONT),
        "cell": ParagraphStyle("cell", fontSize=9, leading=11, **base),
        "home": ParagraphStyle("home", fontSize=9, leading=11, alignment=TA_RIGHT, **base),
    }


def _form(letters: str) -> str:
    """Form as coloured letters that read on white paper."""
    return "".join(f'<font color="{FORM_INK[c]}">{c}</font>' if c in FORM_INK else escape(c) for c in letters)


def side_text(match: yb.BookMatch, side: str) -> str:
    """A team's name as printed: escaped for the PDF, with "*" after it when it went through a level tie."""
    return escape(yb.side_label(match, side))


def _matches(matches, styles) -> Table:
    rows = [[m.date_text, Paragraph(side_text(m, "home"), styles["home"]), m.score,
             Paragraph(side_text(m, "away"), styles["cell"]), Paragraph(escape(m.note), styles["small"])]
            for m in matches]
    table = Table(rows, colWidths=[15 * mm, 48 * mm, 14 * mm, 48 * mm, 49 * mm], hAlign="CENTER")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), FONT), ("FONTSIZE", (0, 0), (0, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(MUTED)),
        ("FONTNAME", (2, 0), (2, -1), BOLD), ("FONTSIZE", (2, 0), (2, -1), 10), ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
    ]))
    return table


def table_note(lines) -> str:
    """The small note under a table: it is calculated, and what any shading, movement or star means."""
    return yb.table_note(lines)


MOVE_INK = {"▲": FORM_INK["W"], "▼": FORM_INK["L"]}      # a rise and a fall; anything else is muted


def _move(text: str) -> str:
    """A movement as coloured text: the win ink for a rise, the loss ink for a fall, muted otherwise."""
    return f'<font color="{MOVE_INK.get(text[:1], MUTED)}">{escape(text)}</font>'


def _standings(lines, styles) -> Table:
    """A table with its movement and PPG columns only where the lines carry them. A marked club is bold with a
    rule under its row."""
    moves, ppg = any(t.movement for t in lines), any(t.ppg for t in lines)
    rows = [list(yb.standings_head(lines))]
    for t in lines:
        name = f"<b>{escape(t.team)}</b>" if t.marked else escape(t.team)
        rows.append(([Paragraph(_move(t.movement), styles["cell"])] if moves else []) +
                    [str(t.pos), Paragraph(name, styles["cell"]), t.played, t.won, t.drawn, t.lost, t.goals_for,
                     t.goals_against, f"{t.goal_difference:+d}" if t.goal_difference else "0", t.points] +
                    ([t.ppg] if ppg else []) + [Paragraph(_form(t.form), styles["cell"])])
    widths = ([9 * mm] if moves else []) + [7 * mm, 50 * mm] + [8.5 * mm] * 7 + [10 * mm] + \
             ([11 * mm] if ppg else []) + [24 * mm]
    if not moves and not ppg:                                   # the plain table keeps its wider name and form
        widths = [8 * mm, 52 * mm] + [9 * mm] * 7 + [11 * mm, 27 * mm]
    first = 1 if moves else 0                                   # the column of "#"
    pts = first + 9
    table = Table(rows, colWidths=widths, hAlign="CENTER", repeatRows=1)
    zones = [("BACKGROUND", (first, i), (first, i), colors.HexColor(ZONE_TINT[t.zone]))
             for i, t in enumerate(lines, start=1) if t.zone in ZONE_TINT]
    marked = [("LINEBELOW", (0, i), (-1, i), 0.6, colors.HexColor(INK)) for i, t in enumerate(lines, start=1) if t.marked]
    table.setStyle(TableStyle(zones + [
        ("FONTNAME", (0, 0), (-1, 0), BOLD), ("FONTNAME", (0, 1), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (pts, 1), (pts, -1), BOLD), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("ALIGN", (first + 2, 0), (-2, -1), "CENTER"), ("ALIGN", (0, 0), (first, -1), "CENTER"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(INK)),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#dddddd")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
    ] + marked))
    return table


def _record(lines, styles) -> Table:
    """A home or away record: places, results and goals, with no form."""
    rows = [list(yb.RECORD_HEAD)] + \
           [[str(t.pos), Paragraph(f"<b>{escape(t.team)}</b>" if t.marked else escape(t.team), styles["cell"]), t.played,
             t.won, t.drawn, t.lost, t.goals_for, t.goals_against, t.points] for t in lines]
    table = Table(rows, colWidths=[8 * mm, 52 * mm] + [9 * mm] * 6 + [11 * mm], hAlign="CENTER", repeatRows=1)
    zones = [("BACKGROUND", (0, i), (0, i), colors.HexColor(ZONE_TINT[t.zone]))
             for i, t in enumerate(lines, start=1) if t.zone in ZONE_TINT]
    marked = [("LINEBELOW", (0, i), (-1, i), 0.6, colors.HexColor(INK)) for i, t in enumerate(lines, start=1) if t.marked]
    table.setStyle(TableStyle(zones + [
        ("FONTNAME", (0, 0), (-1, 0), BOLD), ("FONTNAME", (0, 1), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (8, 1), (8, -1), BOLD), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("ALIGN", (2, 0), (8, -1), "CENTER"), ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(INK)),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#dddddd")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
    ] + marked))
    return table


# The places grid ("How they stood") is drawn on a landscape page at PLACES_FONT; a row that will not fit is split
# into equal halves (thirds, ...) of the weeks, never into a smaller type and never by dropping a week or a club.
PLACES_FONT = 7
PLACES_NAME, PLACES_NOW = 36 * mm, 10 * mm
PLACES_CELL = 12.0                                   # the least a two-digit place needs at PLACES_FONT, in points
LANDSCAPE_FRAME_WIDTH = A4[1] - 36 * mm - 12         # the landscape text area, less the frame's own padding
FRAME_TOP, FRAME_SIDE, FRAME_BOTTOM = 16 * mm, 18 * mm, 18 * mm


def places_chunks(weeks: int, width: float = LANDSCAPE_FRAME_WIDTH) -> list[tuple[int, int]]:
    """The (start, end) week ranges of a places grid: the whole season when every week fits at PLACES_FONT, else
    the fewest equal parts that each fit."""
    capacity = max(1, int((width - PLACES_NAME - PLACES_NOW) // PLACES_CELL))
    parts = math.ceil(weeks / capacity)
    size = math.ceil(weeks / parts)
    return [(a, min(a + size, weeks)) for a in range(0, weeks, size)]


def _places_tables(page, styles) -> list[Table]:
    """One table for each chunk of weeks: the club, its place after each matchweek (blank before it played), and
    its latest place shaded by zone."""
    small = ParagraphStyle("places", parent=styles["cell"], fontSize=PLACES_FONT, leading=PLACES_FONT + 1.5)
    tables = []
    for first, last in places_chunks(len(page.matchweeks)):
        weeks = page.matchweeks[first:last]
        cell = min((LANDSCAPE_FRAME_WIDTH - PLACES_NAME - PLACES_NOW) / len(weeks), 7 * mm)
        rows = [[""] + [str(w) for w in weeks] + ["Now"]]
        for r in page.rows:
            rows.append([Paragraph(f"<b>{escape(r.team)}</b>" if r.marked else escape(r.team), small)] +
                        ["" if p is None else str(p) for p in r.places[first:last]] + [str(r.now)])
        table = Table(rows, colWidths=[PLACES_NAME] + [cell] * len(weeks) + [PLACES_NOW], hAlign="CENTER", repeatRows=1)
        now = len(weeks) + 1
        zones = [("BACKGROUND", (now, i), (now, i), colors.HexColor(ZONE_TINT[r.zone]))
                 for i, r in enumerate(page.rows, start=1) if r.zone in ZONE_TINT]
        marked = [("LINEBELOW", (0, i), (-1, i), 0.6, colors.HexColor(INK)) for i, r in enumerate(page.rows, start=1)
                  if r.marked]
        table.setStyle(TableStyle(zones + [
            ("FONTNAME", (0, 0), (-1, 0), BOLD), ("FONTNAME", (0, 1), (-1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, -1), PLACES_FONT), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
            ("FONTNAME", (now, 1), (now, -1), BOLD), ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(INK)),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#dddddd")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.3), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3),
            ("LEFTPADDING", (1, 0), (-1, -1), 1), ("RIGHTPADDING", (1, 0), (-1, -1), 1),
        ] + marked))
        tables.append(table)
    return tables


def _places_parts(page, styles) -> list[list]:
    """The parts of each landscape page of a places grid: heading, table and a note."""
    note = yb.places_note(page)
    parts = []
    for (first, last), table in zip(places_chunks(len(page.matchweeks)), _places_tables(page, styles)):
        weeks = page.matchweeks[first:last]
        parts.append([Paragraph(f"{escape(page.competition)} · How they stood, matchweeks {weeks[0]}–{weeks[-1]}",
                                styles["heading"]), table, Spacer(1, 3 * mm), Paragraph(escape(note), styles["small"])])
    return parts


MOVE_WITHIN_DAYS = 3        # only a block this close before a matchweek may follow it
FRAME_WIDTH, FRAME_HEIGHT = A4[0] - 36 * mm, A4[1] - 34 * mm      # the text area of a page


def _block_parts(page, styles) -> list:
    """The parts of a small block (a cup day, or a postponed league match played late)."""
    if isinstance(page, yb.CupBlock):
        note = [Paragraph(escape(page.footnote), styles["small"])] if page.footnote else []
        if page.table:                      # a league phase: its table after the day's results, cut to the top places
            note += [Spacer(1, 4 * mm), _standings(page.table, styles),
                     Paragraph(escape(yb.cut_table_note(page.table_note, page.table)), styles["small"])]
        title = escape(page.heading)
    else:
        note, title = [], f"{escape(page.competition)} · {escape(page.heading)}"
    return [Paragraph(title, styles["heading"]), _matches(page.matches, styles), *note, Spacer(1, 4 * mm)]


def _matchweek_parts(page, styles) -> list:
    """The parts of a full matchweek: heading, results and table, kept together."""
    return [Paragraph(f"{escape(page.competition)} · {escape(page.heading)}", styles["heading"]),
            _matches(page.matches, styles), Spacer(1, 6 * mm), _standings(page.table, styles),
            Paragraph(escape(yb.cut_table_note(page.table_note, page.table)), styles["small"]), Spacer(1, 8 * mm)]


def _height(parts: list) -> float:
    return sum(part.wrap(FRAME_WIDTH, 10 ** 6)[1] for part in parts)


def order_for_pages(pages: Sequence) -> list:
    """The pages in the order they are printed. A matchweek and its table are never split, so small blocks that
    come just before a full matchweek would leave a mostly empty page when the two cannot share one: in that case
    the matchweek goes first and the blocks follow it (a few days out of date order, but no gap)."""
    _register_fonts()
    styles = _styles()
    ordered: list = []
    pending: list = []
    for page in pages:
        full = isinstance(page, yb.LeaguePage) and bool(page.table)
        small = isinstance(page, yb.CupBlock) or (isinstance(page, yb.LeaguePage) and not page.table)
        if small:
            pending.append(page)
        elif full and pending:
            near = [b for b in pending if (page.when - b.when).days <= MOVE_WITHIN_DAYS]
            early = [b for b in pending if b not in near]                  # a season opener keeps its place
            together = sum(_height(_block_parts(b, styles)) for b in near) + _height(_matchweek_parts(page, styles))
            ordered += [*early, page, *near] if together > FRAME_HEIGHT else [*early, *near, page]
            pending = []
        else:
            ordered += [*pending, page]
            pending = []
    return ordered + pending


def _flow(book: yb.Yearbook) -> list:
    styles = _styles()
    flow: list = []

    def new_page() -> None:
        if flow and not isinstance(flow[-1], PageBreak):
            flow.append(PageBreak())

    def switch_to(template: str) -> None:
        """Start a new page in the named page template (portrait or landscape)."""
        if flow and isinstance(flow[-1], PageBreak):
            flow.insert(len(flow) - 1, NextPageTemplate(template))
        else:
            flow.extend([NextPageTemplate(template), PageBreak()])

    seen: set[str] = set()

    def outlined(flowable, level: int, title: str):
        """Bookmark a flowable. A KeepTogether is handed to the document as its parts, so its first part carries the
        same entry (the document skips an entry it has just seen)."""
        entry = (level, title)
        flowable._outline = entry
        if isinstance(flowable, KeepTogether) and flowable._content:
            flowable._content[0]._outline = entry
        return flowable

    def competition_entry(flowable, name: str):
        """Bookmark a competition at its first page; its play-off rounds belong to it."""
        base = name.removesuffix(" play-offs")
        if base not in seen:
            seen.add(base)
            outlined(flowable, 1, base)
        return flowable

    for page in order_for_pages(book.pages):
        if isinstance(page, yb.TitlePage):
            heading = outlined(Paragraph(f"Football Yearbook {escape(page.season_label)}", styles["title"]), 0,
                               f"Football Yearbook {page.season_label}")
            flow += [Spacer(1, 60 * mm), heading,
                     Spacer(1, 8 * mm)] + [Paragraph(escape(line), styles["line"]) for line in page.coverage_lines]
            new_page()
        elif isinstance(page, yb.LeaguePage) and page.table:       # a matchweek and its table stay together
            flow.append(competition_entry(KeepTogether(_matchweek_parts(page, styles)), page.competition))
        elif isinstance(page, (yb.LeaguePage, yb.CupBlock)):      # a cup day, or a postponed match played late
            flow.append(competition_entry(KeepTogether(_block_parts(page, styles)), page.competition))
        elif isinstance(page, yb.PlacesPage):
            switch_to("landscape")
            for number, parts in enumerate(_places_parts(page, styles)):
                if number:
                    flow.append(PageBreak())
                keep = KeepTogether(parts)
                flow.append(outlined(keep, 1, f"{page.competition}: How they stood") if not number else keep)
            switch_to("portrait")
        elif isinstance(page, yb.FinalTablesPage):
            new_page()
            splits = {entry[0]: entry for entry in page.splits}
            strips = dict(page.strips)
            first_table = True
            for name, lines in page.tables:
                strip = ([Paragraph(f"{escape(name)} · from the results", styles["heading"])] +
                         [Paragraph(escape(text), styles["cell"]) for text in strips[name]]) if strips.get(name) else []
                final = KeepTogether([Paragraph(f"{escape(name)} · final table", styles["heading"]),
                                      _standings(lines, styles), Paragraph(table_note(lines), styles["small"]),
                                      *strip, Spacer(1, 8 * mm)])
                flow.append(outlined(final, 1, "Final tables") if first_table else final)
                first_table = False
                if name in splits:
                    _, _, home, away = splits[name]
                    for kind, record in (("home", home), ("away", away)):
                        flow += [KeepTogether([Paragraph(f"{escape(name)} · {kind} record", styles["heading"]),
                                               _record(record, styles), Spacer(1, 4 * mm)])]
                    flow += [Paragraph(yb.SPLITS_NOTE, styles["small"]), Spacer(1, 8 * mm)]
    while flow and isinstance(flow[-1], PageBreak):          # a page break at the very end would print a blank page
        flow.pop()
    return flow


def render(book: yb.Yearbook, path: Path) -> None:
    """Write the book to `path`. Built under a temporary name beside it and moved into place only when whole; on any
    failure the temporary file is removed and an earlier book at `path` is left as it was."""
    _register_fonts()
    path = Path(path)
    scrap = path.with_name(path.name + ".part")
    try:
        doc = BookDocTemplate(str(scrap), pagesize=A4, title=f"Football Yearbook {book.season_label}",
                              author="Box2Box")

        def footer(canvas, _doc) -> None:
            if canvas.getPageNumber() == 1:                      # the title page carries none
                return
            width = canvas._pagesize[0]
            canvas.saveState()
            canvas.setFont(FONT, 7.5)
            canvas.setFillColor(colors.HexColor(MUTED))
            canvas.drawString(FRAME_SIDE, 10 * mm, f"Box2Box · Football Yearbook {book.season_label}")
            canvas.drawRightString(width - FRAME_SIDE, 10 * mm, f"Page {canvas.getPageNumber()}")
            canvas.restoreState()

        wide, high = A4
        doc.addPageTemplates([
            PageTemplate("portrait", [Frame(FRAME_SIDE, FRAME_BOTTOM, wide - 2 * FRAME_SIDE,
                                            high - FRAME_TOP - FRAME_BOTTOM, id="portrait")], onPage=footer, pagesize=A4),
            PageTemplate("landscape", [Frame(FRAME_SIDE, FRAME_BOTTOM, high - 2 * FRAME_SIDE,
                                             wide - FRAME_TOP - FRAME_BOTTOM, id="landscape")], onPage=footer,
                         pagesize=landscape(A4))])
        doc.build(_flow(book))
        os.replace(scrap, path)
    except BaseException:
        scrap.unlink(missing_ok=True)
        raise
