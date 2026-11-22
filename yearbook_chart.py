# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""The season trajectory chart's geometry and wording, shared by the reader's canvas and the PDF so the two draw
the same places on the same dates. No UI code and no PDF code: it turns a yearbook.Trajectory into coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass

import yearbook as yb

HIT_RADIUS = 14.0            # a hover finds a point this close (in pixels or points)


@dataclass(frozen=True, slots=True)
class ZoneBand:
    zone: str
    label: str
    top: float
    bottom: float


@dataclass(frozen=True, slots=True)
class ChartLayout:
    width: float
    height: float
    left: float
    right: float
    top: float
    bottom: float
    points: tuple[tuple[yb.TrajectoryPoint, float, float], ...]       # only points with a place
    segments: tuple[tuple[tuple[float, float], ...], ...]             # polylines: never across a gap
    gap_xs: tuple[float, ...]                                         # where a table printed with no place for the club
    zones: tuple[ZoneBand, ...]
    y_ticks: tuple[tuple[int, float], ...]
    x_ticks: tuple[tuple[str, float], ...]

    def nearest(self, x: float, y: float, radius: float = HIT_RADIUS) -> yb.TrajectoryPoint | None:
        best, found = radius ** 2, None
        for point, px, py in self.points:
            d = (px - x) ** 2 + (py - y) ** 2
            if d <= best:
                best, found = d, point
        return found


def _zone_label(zone: str) -> str:
    name = yb.ZONE_NAMES.get(zone, zone)
    return name if "estimated" in name else f"{name} (estimated)"


def layout(chart: yb.Trajectory, width: float, height: float, margin_left: float = 34, margin_right: float = 14,
           margin_top: float = 12, margin_bottom: float = 30) -> ChartLayout:
    """Coordinates for a chart in a box of `width` by `height`, with y growing downwards: first place at the top
    edge of the plot, last place at the bottom, and x proportional to the date each table is calculated to."""
    left, right, top, bottom = margin_left, width - margin_right, margin_top, height - margin_bottom
    days = [p.through for p in chart.points]
    first, last = min(days), max(days)
    span = (last - first).days

    def x_of(day) -> float:
        return (left + right) / 2 if span == 0 else left + (right - left) * (day - first).days / span

    places = max(chart.clubs, 2)

    def y_of(place: float) -> float:
        return top + (bottom - top) * (place - 1) / (places - 1)

    plotted = tuple((p, x_of(p.through), y_of(p.place)) for p in chart.points if p.place is not None)
    coordinates = {p.matchweek: (x, y) for p, x, y in plotted}
    segments = tuple(tuple(coordinates[p.matchweek] for p in run) for run in yb.trajectory_segments(chart))
    half = 0.5
    zones = tuple(ZoneBand(zone, _zone_label(zone), max(top, y_of(a - half)), min(bottom, y_of(b + half)))
                  for zone, a, b in chart.zones)
    step = max(1, round(places / 5))
    ticks = tuple((n, y_of(n)) for n in sorted({1, *range(step, places + 1, step), places}))
    x_ticks = tuple((f"{p.matchweek} ┬À {p.through.day} {p.through:%b}", x_of(p.through)) for p in chart.points)
    return ChartLayout(width, height, left, right, top, bottom, plotted, segments,
                       tuple(x_of(p.through) for p in chart.points if p.place is None), zones, ticks, x_ticks)


def point_text(point: yb.TrajectoryPoint) -> str:
    """What a hover says about one table: the place and the club's results on that matchweek's page, as a list
    and nothing more (a rise or fall is never put down to a result: rivals' results move the table too)."""
    when = f"Matchweek {point.matchweek}, to {yb._day(point.through)} {point.through:%b}"
    if point.place is None:
        return f"{when}: no place, the club had not yet played."
    if not point.results:
        return f"{when}: {yb.ordinal(point.place)}. No result for the club is printed on that matchweek's page."
    results = "; ".join(f"{m.home} {m.score} {m.away}" for m in point.results)
    return f"{when}: {yb.ordinal(point.place)}. Results that matchweek: {results}."
