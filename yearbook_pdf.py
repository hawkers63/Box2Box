# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Draws the Yearbook page model (yearbook.py) as a PDF with reportlab: A4 portrait, one light, ink-friendly
style, no club badges or tint. The file is written to a temporary name and moved into place, so a failure
never leaves a half-written book and never disturbs an earlier one.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import yearbook as yb

FONT, BOLD = "DejaVuSans", "DejaVuSans-Bold"
INK, MUTED, RULE = "#1a1a1a", "#555555", "#bbbbbb"
# Form letters in three colours that read on white paper (each is at least 4.5:1 against white).
FORM_INK = {"W": "#1b6e2e", "D": "#7a5c00", "L": "#a8261e"}


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


def _matches(matches, styles) -> Table:
    rows = [[m.date_text, Paragraph(escape(m.home), styles["home"]), m.score, Paragraph(escape(m.away), styles["cell"]),
             Paragraph(escape(m.note), styles["small"])] for m in matches]
    table = Table(rows, colWidths=[15 * mm, 48 * mm, 14 * mm, 48 * mm, 49 * mm], hAlign="CENTER")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), FONT), ("FONTSIZE", (0, 0), (0, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(MUTED)),
        ("FONTNAME", (2, 0), (2, -1), BOLD), ("FONTSIZE", (2, 0), (2, -1), 10), ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _standings(lines, styles) -> Table:
    head = ["#", "Team", "P", "W", "D", "L", "F", "A", "GD", "Pts", "Last six"]
    rows = [head] + [[str(t.pos), Paragraph(escape(t.team), styles["cell"]), t.played, t.won, t.drawn, t.lost,
                      t.goals_for, t.goals_against, f"{t.goal_difference:+d}" if t.goal_difference else "0",
                      t.points, Paragraph(_form(t.form), styles["cell"])] for t in lines]
    table = Table(rows, colWidths=[8 * mm, 52 * mm] + [9 * mm] * 7 + [11 * mm, 27 * mm], hAlign="CENTER", repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), BOLD), ("FONTNAME", (0, 1), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (9, 1), (9, -1), BOLD), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("ALIGN", (2, 0), (9, -1), "CENTER"), ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(INK)),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#dddddd")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def _flow(book: yb.Yearbook) -> list:
    styles = _styles()
    flow: list = []

    def new_page() -> None:
        if flow and not isinstance(flow[-1], PageBreak):
            flow.append(PageBreak())

    for page in book.pages:
        if isinstance(page, yb.TitlePage):
            flow += [Spacer(1, 60 * mm), Paragraph(f"Football Yearbook {escape(page.season_label)}", styles["title"]),
                     Spacer(1, 8 * mm)] + [Paragraph(escape(line), styles["line"]) for line in page.coverage_lines]
            new_page()
        elif isinstance(page, yb.LeaguePage) and page.table:
            new_page()
            flow += [Paragraph(f"{escape(page.competition)} · {escape(page.heading)}", styles["heading"]),
                     _matches(page.matches, styles), Spacer(1, 6 * mm), _standings(page.table, styles),
                     Paragraph("Table calculated from the results.", styles["small"]), Spacer(1, 8 * mm)]
        elif isinstance(page, yb.LeaguePage):                              # a postponed match, played late
            flow.append(KeepTogether([Paragraph(f"{escape(page.competition)} · {escape(page.heading)}", styles["heading"]),
                                      _matches(page.matches, styles), Spacer(1, 4 * mm)]))
        elif isinstance(page, yb.CupBlock):
            flow.append(KeepTogether([Paragraph(escape(page.heading), styles["heading"]),
                                      _matches(page.matches, styles), Spacer(1, 4 * mm)]))
        elif isinstance(page, yb.FinalTablesPage):
            new_page()
            for name, lines in page.tables:
                flow += [KeepTogether([Paragraph(f"{escape(name)} · final table", styles["heading"]),
                                       _standings(lines, styles), Spacer(1, 8 * mm)])]
    return flow


def render(book: yb.Yearbook, path: Path) -> None:
    """Write the book to `path`. Built under a temporary name beside it and moved into place only when whole; on any
    failure the temporary file is removed and an earlier book at `path` is left as it was."""
    _register_fonts()
    path = Path(path)
    scrap = path.with_name(path.name + ".part")
    try:
        doc = SimpleDocTemplate(str(scrap), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                                bottomMargin=18 * mm, title=f"Football Yearbook {book.season_label}", author="Box2Box")

        def footer(canvas, _doc) -> None:
            canvas.saveState()
            canvas.setFont(FONT, 7.5)
            canvas.setFillColor(colors.HexColor(MUTED))
            canvas.drawString(18 * mm, 10 * mm, f"Box2Box · Football Yearbook {book.season_label}")
            canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {canvas.getPageNumber()}")
            canvas.restoreState()

        doc.build(_flow(book), onFirstPage=lambda c, d: None, onLaterPages=footer)
        os.replace(scrap, path)
    except BaseException:
        scrap.unlink(missing_ok=True)
        raise
