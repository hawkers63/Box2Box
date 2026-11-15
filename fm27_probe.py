# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""FM27 fixture probe.

Reads a Football Manager save with fmsave and reports how much fixture and
result data can be recovered, so the output can be compared against the game.
It never modifies the save.

Usage (Python 3.12 or newer, with fmsave installed):

    python fm27_probe.py "C:\\path\\to\\copy_of_save.fm"

Options:
    --competition ID   competition id to detail (default: the one where your
                       managed club has most fixtures)
    --season YEAR      season start year to detail (default: latest with results)
    --club TEXT        club name to follow instead of the managed club
    --names FILE       competition names CSV for fmsave (optional)
    --out FILE         report file (default: fm27_probe_report.txt beside the script)
"""

from __future__ import annotations

import argparse
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

if sys.version_info < (3, 12):
    sys.exit(f"Python 3.12 or newer is needed; this is {sys.version.split()[0]}.")

try:
    import fmsave
except ImportError:
    sys.exit('fmsave is not installed. Run:  pip install fmsave')


class Report:
    """Collects lines, printing them and keeping them for the report file."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def heading(self, text: str) -> None:
        self.add()
        self.add(text)
        self.add("=" * len(text))

    def table(self, headers: list[str], rows: list[list[object]]) -> None:
        cells = [[("" if v is None else str(v)) for v in row] for row in rows]
        widths = [len(h) for h in headers]
        for row in cells:
            for i, value in enumerate(row):
                widths[i] = max(widths[i], len(value))
        self.add("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
        self.add("  ".join("-" * w for w in widths))
        for row in cells:
            self.add("  ".join(v.ljust(w) for v, w in zip(row, widths)))


def has_score(fx) -> bool:
    return fx.home_goals is not None and fx.away_goals is not None


def score_text(fx) -> str:
    if has_score(fx):
        return f"{fx.home_goals}-{fx.away_goals}"
    return "result unavailable" if fx.played else "not played"


def club_label(name, team_id) -> str:
    return name if name else f"team {team_id}"


def comp_label(comp_id, comp_names: dict) -> str:
    if comp_id is None:
        return "(no competition)"
    name = comp_names.get(comp_id)
    return f"{comp_id} {name}" if name else str(comp_id)


def involves(fx, team_ids: set[int]) -> bool:
    return fx.home_team_id in team_ids or fx.away_team_id in team_ids


def try_read(report: Report, label: str, reader):
    """Run one fmsave reader, reporting a failure instead of stopping."""
    try:
        return list(reader())
    except Exception as exc:  # each reader can fail on its own
        report.add(f"{label}: could not be read ({type(exc).__name__}: {exc})")
        return None


def run(args: argparse.Namespace, report: Report) -> None:
    path = Path(args.save)
    report.add(f"fmsave {getattr(fmsave, '__version__', '?')}, Python {sys.version.split()[0]}")
    report.add(f"Save file: {path.name}")

    open_kwargs = {"competition_names": args.names} if args.names else {}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with fmsave.open(path, **open_kwargs) as save:
            info = save.info
            report.heading("Save")
            report.add(f"Game:         {info.game}")
            report.add(f"Build:        {info.build}")
            report.add(f"Known build:  {'yes' if info.known_build else 'NO - layouts are borrowed, treat everything as unverified'}")
            report.add(f"In-game date: {info.game_date}")

            managed = try_read(report, "Managed club", save.managed_clubs) or []
            clubs = try_read(report, "Clubs", save.clubs) or []
            fixtures = try_read(report, "Fixtures", save.fixtures)
            competitions = try_read(report, "Competitions", save.competitions) or []
            tables = try_read(report, "League tables", save.league_tables) or []
            stats = try_read(report, "Team match stats", save.team_match_stats)

    comp_names = {c.id: c.name for c in competitions if c.name}

    # --- which club to follow -------------------------------------------
    follow_uid, follow_name = None, None
    if args.club:
        wanted = args.club.casefold()
        matches = [c for c in clubs if wanted in (c.name.casefold(), c.short_name.casefold())]
        if not matches:
            matches = [c for c in clubs if wanted in c.name.casefold()]
        if len(matches) == 1:
            follow_uid, follow_name = matches[0].uid, matches[0].name
        elif matches:
            report.add(f"--club '{args.club}' matches {len(matches)} clubs; be more specific: "
                       + ", ".join(sorted(c.name for c in matches)[:10]))
        else:
            report.add(f"--club '{args.club}' matches no club in the save.")
    elif managed:
        follow_uid, follow_name = managed[0].club_uid, managed[0].club_name
    follow_teams: set[int] = set()
    if follow_uid is not None:
        for club in clubs:
            if club.uid == follow_uid:
                follow_teams = {t.team_id for t in club.teams if not t.is_affiliate}
    report.add(f"Club followed: {follow_name or 'none found'}")

    if not fixtures:
        report.heading("Result")
        report.add("No fixtures were recovered from this save, so the viewer cannot be built on it as it stands.")
        _warnings(report, caught)
        return

    # --- all fixtures ---------------------------------------------------
    played = [f for f in fixtures if f.played]
    scored = [f for f in played if has_score(f)]
    dates = sorted(f.date for f in fixtures if f.date)
    report.heading("All fixtures in the save")
    report.add(f"Fixtures:                     {len(fixtures)}")
    report.add(f"Played:                       {len(played)}")
    report.add(f"Played with a decoded score:  {len(scored)}")
    report.add(f"Played, result unavailable:   {len(played) - len(scored)}")
    report.add(f"Not yet played:               {len(fixtures) - len(played)}")
    if dates:
        report.add(f"Date range:                   {dates[0]} to {dates[-1]}")
    report.add(f"Fixtures with no date:        {sum(1 for f in fixtures if not f.date)}")
    report.add(f"Fixtures with no competition: {sum(1 for f in fixtures if f.competition_id is None)}")

    # --- per competition ------------------------------------------------
    by_comp: dict = defaultdict(list)
    for f in fixtures:
        by_comp[f.competition_id].append(f)
    rows = []
    for comp_id, items in by_comp.items():
        comp_played = [f for f in items if f.played]
        teams = {f.home_team_id for f in items} | {f.away_team_id for f in items}
        mine = sum(1 for f in items if involves(f, follow_teams))
        seasons = sorted({f.season_start_year for f in items if f.season_start_year})
        sample = Counter(club_label(f.home_club_short_name or f.home_club_name, f.home_team_id) for f in items)
        rows.append([
            comp_label(comp_id, comp_names), len(items), len(comp_played),
            sum(1 for f in comp_played if has_score(f)), len(teams), mine,
            ",".join(map(str, seasons)), ", ".join(n for n, _ in sample.most_common(3)),
        ])
    rows.sort(key=lambda r: (-r[5], -r[1]))
    report.heading("Competitions (your club's first, then by size; top 25)")
    report.table(["Competition", "Fixtures", "Played", "Scored", "Teams", "Yours", "Seasons", "Example home clubs"], rows[:25])
    report.add(f"({len(by_comp)} competitions hold fixtures. Competition names need a names CSV; ids are shown otherwise.)")

    # --- choose competition and season ----------------------------------
    comp_id = args.competition
    if comp_id is None:
        mine_counts = Counter(f.competition_id for f in fixtures
                              if involves(f, follow_teams) and f.competition_id is not None)
        if mine_counts:
            comp_id = mine_counts.most_common(1)[0][0]
        else:
            sized = [(len(v), k) for k, v in by_comp.items() if k is not None]
            comp_id = max(sized)[1] if sized else None
    chosen = by_comp.get(comp_id, [])
    if not chosen:
        report.add(f"No fixtures found for competition {comp_id}.")
        _warnings(report, caught)
        return

    season = args.season
    if season is None:
        with_results = sorted({f.season_start_year for f in chosen if f.season_start_year and f.played})
        any_season = sorted({f.season_start_year for f in chosen if f.season_start_year})
        season = (with_results or any_season or [None])[-1]
    if season is not None:
        chosen = [f for f in chosen if f.season_start_year == season]

    c_played = [f for f in chosen if f.played]
    c_scored = [f for f in c_played if has_score(f)]
    teams = {f.home_team_id for f in chosen} | {f.away_team_id for f in chosen}
    pairings = Counter((f.home_team_id, f.away_team_id) for f in chosen)
    report.heading(f"Detail: competition {comp_label(comp_id, comp_names)}, season starting {season or 'unknown'}")
    report.add(f"Fixtures:                    {len(chosen)}")
    report.add(f"Played:                      {len(c_played)}")
    report.add(f"Played with a decoded score: {len(c_scored)}")
    report.add(f"Played, result unavailable:  {len(c_played) - len(c_scored)}")
    report.add(f"Teams:                       {len(teams)}")
    report.add(f"Home/away pairings that occur more than once: {sum(1 for n in pairings.values() if n > 1)}")
    report.add(f"Fixtures with a round index: {sum(1 for f in chosen if f.round_index is not None)}")

    def result_rows(items):
        return [[f.date, f.round_index,
                 club_label(f.home_club_name, f.home_team_id), score_text(f),
                 club_label(f.away_club_name, f.away_team_id)] for f in items]

    ordered = sorted(chosen, key=lambda f: (f.date is None, f.date, f.kick_off_time is None, f.kick_off_time))
    mine = [f for f in ordered if involves(f, follow_teams)]
    if mine:
        report.heading(f"{follow_name}: every fixture in this competition (compare with the game)")
        report.table(["Date", "Round", "Home", "Score", "Away"], result_rows(mine))
    recent = [f for f in ordered if f.played][-20:]
    if recent:
        report.heading("Last 20 played matches in this competition (compare a few with the game)")
        report.table(["Date", "Round", "Home", "Score", "Away"], result_rows(recent))

    # --- league table as the save stores it -----------------------------
    comp_tables = [t for t in tables if t.competition_id == comp_id]
    if comp_tables:
        biggest = max(comp_tables, key=lambda t: t.club_count)
        report.heading("League table stored in the save (should match the game's table)")
        report.table(["Pos", "Club", "P", "W", "D", "L", "GF", "GA", "Pts"],
                     [[r.position, club_label(r.club_name, r.team_id), r.played, r.won, r.drawn,
                       r.lost, r.goals_for, r.goals_against, r.points] for r in biggest.rows])
        if len(comp_tables) > 1:
            report.add(f"({len(comp_tables)} tables name this competition; the largest is shown.)")
    else:
        report.add()
        report.add(f"No stored league table names competition {comp_id} ({len(tables)} tables in the save).")

    # --- match statistics coverage --------------------------------------
    report.heading("Match statistics (xG) coverage")
    if stats is None:
        report.add("Not available for this save.")
    else:
        keys = {(s.competition_id, s.home_team_id, s.away_team_id, s.date) for s in stats}
        covered = sum(1 for f in c_played
                      if (f.competition_id, f.home_team_id, f.away_team_id, f.date) in keys)
        report.add(f"Matches with a kept report in the whole save: {len(keys)}")
        report.add(f"In the detailed competition: {covered} of {len(c_played)} played matches have xG.")

    _warnings(report, caught)


def _warnings(report: Report, caught) -> None:
    report.heading("Reader warnings")
    if not caught:
        report.add("None.")
    seen = set()
    for w in caught:
        text = f"{w.category.__name__}: {w.message}"
        if text not in seen:
            seen.add(text)
            report.add(f"- {text}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Report fixture and result coverage in an FM26/FM27 save.")
    parser.add_argument("save", help="path to a COPY of the .fm save file")
    parser.add_argument("--competition", type=int, help="competition id to detail")
    parser.add_argument("--season", type=int, help="season start year to detail")
    parser.add_argument("--club", help="club name to follow instead of the managed club")
    parser.add_argument("--names", help="competition names CSV for fmsave")
    parser.add_argument("--out", help="report file path")
    args = parser.parse_args()

    report = Report()
    try:
        run(args, report)
    except FileNotFoundError:
        report.add(f"File not found: {args.save}")
    except fmsave.FmsaveError as exc:
        report.add(f"fmsave could not read this save ({type(exc).__name__}): {exc}")

    out = Path(args.out) if args.out else Path(__file__).with_name("fm27_probe_report.txt")
    out.write_text("\n".join(report.lines) + "\n", encoding="utf-8")
    print(f"\nReport written to {out}")


if __name__ == "__main__":
    main()
