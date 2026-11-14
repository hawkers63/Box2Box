# Box2Box roadmap

Last updated: 14 November 2026

The order is the user's: fix what is broken, then exports, then analysis, then keeping history
across saves. Every phase ends the same way: the tests pass, and the work has been checked against
a real save as well as the made-up test data. Sources: `notes/notes_01.txt` to `notes_04.txt`.

| Phase | What | State |
| --- | --- | --- |
| 1 | Fixes: play-off zones, Competitions tab, left-hand list | Done, 14 Nov 2026 |
| 2 | Exports: Excel, HTML, CSV | **Next** |
| 3 | Analysis: form, xG | Planned |
| 4 | History across saves | Planned |

## Done so far

**v0.1, FM Review** (notes_01, notes_02)
- Reads a save with fmsave on a background thread. A failed import leaves the open save untouched.
- Results in date order, grouped by week, matchday or date, with a followed team's results and
  running points.
- Fixture grid: home teams down the side, every meeting kept in its cell, and a row for teams that
  have only played away.
- League table: the game's stored table where it covers the season, otherwise worked out from the
  results.
- Coverage shown throughout: played, still to play, and played with no recoverable score ("n/a").
- Competition names in `competition_names.csv`, keyed on database id. Save probe: `fm27_probe.py`.

**v0.2, Box2Box** (notes_03, notes_04)
- Rebrand, settings migration and the `Box2Box.bat` launcher.
- Competitions hub with categories, entrants, fixtures and season progress.
- Vibrant grid palette and the followed-club view.
- Zone colours, and Home, Away and Form tables.
- Test isolation fix.

**Phase 1: fixes** (14 November 2026)
- Zones now come from the save's own competition rules. The Championship shows 1st–2nd promoted,
  3rd–8th in the play-offs and 22nd–24th relegated.
- Fixed the Competitions tab crash on teams the save cannot resolve; better categories.
- The left-hand list now opens a competition from the hub. In the hub, a click selects and a
  double-click opens. Column-header clicks no longer change the followed team.
- Git repository, `CLAUDE.md` and this roadmap. 47 tests.

## Phase 2: Exports (next)

Goal: get what is on screen out of the app in a form that can be shared, with its caveats attached.

- **CSV**: results, table and grid for the selected competition and season. Write UTF-8 with a BOM
  so Excel shows names such as Kroměříž correctly.
- **Excel (.xlsx)**, as notes_03 planned:
  - Standings, with zone fills and the form string.
  - Fixture Grid, with cell fills matching the app.
  - Results, with week or round headings.
- **HTML**: one standalone file with its CSS (and a small filter script) built in. It should match
  the app's colours and open anywhere without Python.
- **Every export states**:
  - the save, in-game date, competition and season;
  - the coverage line, e.g. "552 fixtures · 0 played · 552 to play";
  - whether the zones are the game's or estimated;
  - the fmsave version, and the unverified-build warning when it applies.
- **Exports what you are looking at**: the current competition, season, followed team, grouping
  and table split.
- **Responsive**: exports run on a worker thread, so the window never freezes.

Done when:
- The export data is shaped in pure code, in `fm_data.py` or a new `export.py`, and unit-tested
  without a window.
- A workbook opened in Excel shows the app's colours, and the CSVs open cleanly in Excel.
- Exports from a real save have been compared with the app by eye.

To settle first:
- One workbook per competition and season, or one for the whole save?
- The default export folder, e.g. `Documents\Box2Box`.
- Add `openpyxl` (or XlsxWriter), pinned, to `requirements.txt`; pandas is already installed.

## Phase 3: Analysis

Goal: form and expected goals, never claiming more than the save holds.

- **Form**:
  - form strips with opponent, venue and score;
  - streaks (unbeaten, winning, without a win), points per game, and goals for and against;
  - totals marked incomplete wherever a played match has no recoverable score.
- **League position by matchday**: rebuild the table after each round under stated rules
  (3 points for a win, then goal difference, then goals scored). It can differ from the game's
  table where head-to-head or deductions decide; matching the game is a separate check.
- **xG** from `team_match_stats()`, which gives two rows per match report the save kept:
  - join to fixtures, rejecting or reporting any ambiguous match;
  - show xG scorelines, e.g. "Sheffield Utd [1.82] 2–1 [0.45] Leeds", and over- or
    under-performance;
  - always show the coverage, e.g. "xG for 18 of 30 played matches";
  - never fill in missing values.
- **Records**: clean-sheet leaders, longest streaks, best attack and meanest defence (notes_03).
- **Head-to-head explorer**: any two clubs across every season and competition the save holds.

Done when: every figure shows its coverage and nothing is filled in for matches the save lacks.

Note: every save so far is pre-season (mid-July 2026), so no English league match has been played.
Form and xG need a save from later in the season to check against. Leagues already under way
abroad (Argentina, Brazil, MLS) can serve until then.

## Phase 4: History across saves

Goal: keep results that later saves no longer hold, and compare seasons.

- **A local archive** of imported fixtures, e.g. SQLite next to the app, with the import details
  for each save: file, build, in-game date, fmsave version and warnings.
- **Fixture identity**: fmsave gives fixtures no unique id. Proposed key: competition database id,
  season, home team, away team, and which meeting it is. A match moved to a new date is the same
  fixture.
- **Merge rules**:
  - a newer save wins;
  - a played result is never overwritten by "not played" or by a missing score;
  - conflicts are reported, not hidden.
- **Remember competition rules** learnt from later saves, e.g. League One and League Two zones once
  their tables exist, and apply them to pre-season saves.
- **Comparisons**: position charts, season against season, and a club's history.

Done when:
- Importing the same saves in any order gives the same archive.
- A failed import leaves the archive as it was.

## Parked ideas

From notes_03, not yet scheduled:
- Cup explorer: rounds, two-legged ties with aggregate scores, and a bracket view.
- Grid: crosshair highlighting of the hovered row and column, and richer cell tooltips.
- Form badges in the table, with tooltips for opponent and score.
- Markdown export for the SI forums and Reddit.
- A Streamlit web version (notes_01). Not planned while the desktop app covers the need.

## Known limitations

- **Unverified build**: the saves are FM27 build 27.0.1+2503222, which fmsave reads with borrowed
  27.0.0 layouts. Treat values as unconfirmed until they are checked against the game.
- **Competition names**: the save holds none. They are added in the app ("Name this competition…").
- **Estimated zones**:
  - League One and League Two, until their tables exist: they share a calendar, so their rules
    cannot be told apart before the season starts.
  - The Champions League and Europa League places of a 20-team top division.
- **Calculated tables** can differ from the game's when head-to-head or points deductions decide.
  The game's stored table is used whenever it covers the season.
- **Reserve sides** appear under their parent club's name in the hub's example clubs, e.g. Jong PSV
  appears as PSV.

## Keeping this file current

Update it whenever a phase or a notable item is finished, and when new notes change the plan. The
"Let's get started." routine in `CLAUDE.md` reads it to choose the next piece of work.
